"""Bounded per-instance subgraphs — the working set the friction query needs.

Why this module exists
----------------------
The friction metric is defined over the *set of all bounded paths* (length
``<= maxLen``, either direction, over ``CALLS`` / ``HAS_METHOD`` / ``INHERITS``)
between an instance's fix-site set and its test-target set. Loading the whole
django repository into the engine makes that path enumeration explode and every
full-graph ``algo.MSpaths`` call exceeds the engine's 29999 ms query timeout
(see ``docs/engine-scaling.md``).

The key observation is a **working-set** one, not a shortcut. Every node that can
possibly lie on a bounded fix->test path is within ``maxLen`` hops of an
endpoint. So the induced subgraph on the ``maxLen``-hop neighbourhood of
``fix_sites UNION test_targets`` contains *every* path the metric is defined
over — loading the rest of django cannot change the answer, it only makes the
server-side traversal explode. The two operations are not the same size:

* Computing the neighbourhood is a cheap **BFS reachability** question — "which
  nodes are within ``maxLen`` undirected hops of a seed" — linear in edges, done
  once, offline, here.
* Enumerating the bounded **path set** between two node sets is combinatorially
  far larger (``~(branching factor)^maxLen`` walks) and is what the engine does
  server-side in one round trip, over the small subgraph this module carves out.

So this is a decision about *what to resident-load*, chosen so the server-side
answer is provably identical to the full-graph answer — **except** where a
budget cap truncates the neighbourhood. A budget-truncated neighbourhood may omit
real paths; that is a genuine bias (the same one the fidelity guard exists to
catch), so truncation is recorded in the stats and never hidden.

Budgets
-------
The node/edge budgets come from ``docs/engine-scaling.md`` (the corrected
size-ceiling sweep against the *healthy* live engine): ``<= 16_000`` nodes and
``<= 24_000`` traversed-relation edges per instance (both-degree <= 3) keep
``maxLen 6`` answerable in ~1.5 s cold — a ~20x margin under the 30 s timeout.
Those are exported here as ``NODE_BUDGET`` / ``EDGE_BUDGET``.

The earlier ``150`` / ``200`` ceiling this module once carried was an artifact of
a *degraded object store* (SlateDB LocalFileSystem write failure, see the scaling
doc's Finding 3), not a property of the engine, and is retracted. The generous
budget is a ceiling, not a target: any genuinely hub-heavy neighbourhood that
would still time out at ``maxLen 6`` is recorded as "no engine path", never forced
under by lowering ``maxLen``.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Iterable, Sequence

from friction.parsing.calls import Edge

# The relationship types the friction path query actually traverses. Only these
# define the neighbourhood; DEFINED_IN / IMPORTS / COVERS are structural and are
# not walked by algo.MSpaths for the metric, so they do not expand the working
# set. Callers filter to these before BFS.
TRAVERSED_TYPES: tuple[str, ...] = ("CALLS", "HAS_METHOD", "INHERITS")

# From docs/engine-scaling.md (corrected, healthy-store sweep): the generous
# budget for maxLen 6 with a ~20x latency margin. Replaces the retracted
# 150/200 ceiling that was measured against a degraded store.
NODE_BUDGET = 16_000
EDGE_BUDGET = 24_000


def _undirected_adjacency(edges: Sequence[Edge]) -> dict[int, set[int]]:
    adj: dict[int, set[int]] = defaultdict(set)
    for e in edges:
        adj[e.src].add(e.dst)
        adj[e.dst].add(e.src)
    return adj


def _induced_edges(edges: Sequence[Edge], nodes: set[int]) -> list[Edge]:
    """Every edge whose *both* endpoints are in ``nodes`` (the induced subgraph)."""
    return [e for e in edges if e.src in nodes and e.dst in nodes]


def _seed_connectivity(adj: dict[int, set[int]], kept: set[int],
                       seeds: Sequence[int]) -> tuple[int, int, int]:
    """Connected-component analysis of the seeds *within the kept subgraph*.

    Returns ``(seed_components, seed_pairs_total, seed_pairs_connected)``:
    how many distinct components hold at least one seed, the total number of
    seed pairs, and how many of those pairs land in the same component (i.e. are
    reachable from each other through kept nodes). An isolated seed is its own
    singleton component and connects to nothing.
    """
    seen: dict[int, int] = {}
    comp = 0
    for start in kept:
        if start in seen:
            continue
        # BFS the component containing `start`, restricted to kept nodes.
        q = deque([start])
        seen[start] = comp
        while q:
            u = q.popleft()
            for v in adj.get(u, ()):  # neighbours
                if v in kept and v not in seen:
                    seen[v] = comp
                    q.append(v)
        comp += 1

    seed_list = [s for s in seeds if s in kept]
    comp_of_seed = [seen[s] for s in seed_list]
    distinct = len(set(comp_of_seed))
    n = len(seed_list)
    pairs_total = n * (n - 1) // 2
    # pairs in the same component
    per_comp: dict[int, int] = defaultdict(int)
    for c in comp_of_seed:
        per_comp[c] += 1
    pairs_connected = sum(k * (k - 1) // 2 for k in per_comp.values())
    return distinct, pairs_total, pairs_connected


def induced_neighbourhood(edges: Sequence[Edge], seed_ids: Iterable[int],
                          hops: int, node_budget: int,
                          edge_budget: int) -> tuple[list[Edge], dict]:
    """BFS the ``hops``-hop undirected neighbourhood of ``seed_ids`` over ``edges``.

    ``edges`` must already be filtered to the traversed relation types (the
    caller does this; see ``TRAVERSED_TYPES``). Expansion proceeds hop by hop
    over the undirected view. Before a hop is added, its nodes and the resulting
    induced-edge count are checked against ``node_budget`` / ``edge_budget``; if
    either would be exceeded the hop is **not** added, ``truncated`` is set, and
    expansion stops. A budget-truncated neighbourhood may omit real fix->test
    paths — that bias is reported, not hidden.

    Seeds are always present in the kept node set, even when they are isolated or
    unreachable from one another, so the returned subgraph always addresses every
    endpoint the query needs.

    Returns ``(kept_edges, stats)``. ``stats['kept_node_ids']`` is the full kept
    node set (including isolated seeds) so the row builder can emit every node;
    callers that serialise the stats should drop that key.
    """
    if hops < 0:
        raise ValueError("hops must be non-negative")

    seeds = list(dict.fromkeys(seed_ids))  # de-dup, preserve order
    adj = _undirected_adjacency(edges)

    kept: set[int] = set(seeds)
    frontier: set[int] = set(seeds)
    hops_completed = 0
    truncated = False
    node_budget_hit = False
    edge_budget_hit = False

    # A dense seed set can already exceed the edge budget before any expansion.
    # Seeds are non-negotiable (the query must address them), so we keep them and
    # surface the overflow as a truncation signal rather than dropping a seed.
    if len(_induced_edges(edges, kept)) > edge_budget:
        edge_budget_hit = True
        truncated = True

    if not truncated:
        for h in range(hops):
            nxt: set[int] = set()
            for u in frontier:
                for v in adj.get(u, ()):  # undirected neighbours
                    if v not in kept:
                        nxt.add(v)
            if not nxt:
                break  # neighbourhood fully explored — natural stop, not truncation
            prospective = kept | nxt
            if len(prospective) > node_budget:
                node_budget_hit = True
                truncated = True
                break
            if len(_induced_edges(edges, prospective)) > edge_budget:
                edge_budget_hit = True
                truncated = True
                break
            kept = prospective
            frontier = nxt
            hops_completed = h + 1

    kept_edges = _induced_edges(edges, kept)
    seed_components, seed_pairs_total, seed_pairs_connected = _seed_connectivity(
        adj, kept, seeds)

    stats = {
        "hops_requested": hops,
        "hops_completed": hops_completed,
        "truncated": truncated,
        "node_budget_hit": node_budget_hit,
        "edge_budget_hit": edge_budget_hit,
        "nodes": len(kept),
        "edges": len(kept_edges),
        "seeds": len(seeds),
        "seeds_in_subgraph": len([s for s in seeds if s in kept]),
        "seed_components": seed_components,
        "seed_pairs_total": seed_pairs_total,
        "seed_pairs_connected": seed_pairs_connected,
        "kept_node_ids": sorted(kept),
    }
    return kept_edges, stats


def build_subgraph_rows(table: dict[int, dict], seed_ids: Iterable[int],
                        kept_edges: Sequence[Edge],
                        band_base: int) -> dict[str, list[dict]]:
    """Turn a kept subgraph into node/edge rows ready for ``friction.loader.load``.

    ``table`` maps a raw (un-banded) node id to its node-property row — the same
    schema ``friction.loader.emit_ndjson`` writes: ``{"label", "id", "sid", ...}``,
    with optional ``file_id``. It is a lightweight symbol table; here it is built
    by reading the instance's existing NDJSON (so django is not re-parsed), but
    any id->row mapping works.

    The emitted node set is ``endpoints(kept_edges) UNION seed_ids`` — the union
    guarantees isolated seeds (an unreachable fix/test node with no traversed
    edge) are still loaded, so the query can address them even though no path
    runs through them.

    Every id, ``sid``, ``file_id`` and edge endpoint is shifted into
    ``band_base`` so the subgraph occupies a disjoint id band, exactly as the
    full-graph loader bands instances.

    (The task sketched this second argument as ``edges``; the node set genuinely
    needs the seed ids, since an isolated seed appears in no edge, so the seed id
    list is passed here.)
    """
    seeds = list(dict.fromkeys(seed_ids))
    node_ids: set[int] = set(seeds)
    for e in kept_edges:
        node_ids.add(e.src)
        node_ids.add(e.dst)

    node_rows: list[dict] = []
    for nid in sorted(node_ids):
        base_row = table.get(nid)
        if base_row is None:
            # A seed with no row in the table would be unloadable; skip it rather
            # than emit a label-less node. (Does not happen for real instances:
            # every fix/test id is a Function in the table.)
            continue
        row = dict(base_row)
        new_id = nid + band_base
        row["id"] = new_id
        row["sid"] = str(new_id)
        if row.get("file_id") is not None:
            row["file_id"] = row["file_id"] + band_base
        node_rows.append(row)

    edge_rows: list[dict] = []
    for e in kept_edges:
        edge_rows.append({
            "src": e.src + band_base,
            "dst": e.dst + band_base,
            "type": e.type,
            "weight": e.weight,
        })

    return {"nodes": node_rows, "edges": edge_rows}

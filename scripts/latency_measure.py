#!/usr/bin/env python
"""Measure BOTH queries on ONE graph at django scale — the honest latency ratio.

This closes the scale-mismatch in the older README claim, which quoted the
`count(*)` reachability band (3-12 ms) from a 1000-node out-degree-3 synthetic
graph and the `algo.MSpaths` 30 s timeout from the ~34 000-node django graph, as
if the two were "the same density". They were two different graphs at two
different scales, and the ~2,500x that fell out of putting them side by side was
an artifact of the mismatch. This script runs BOTH queries on the SAME graph, at
django-like scale AND django-like density, and records the honest ratio.

The graph: one synthetic call-graph-shaped graph in a fresh id band
(base 45_000_000_000):
    nodes        = 34 000            (django's ~34k-node call graph)
    both-degree  = 2.9               (django's CALLS+HAS_METHOD+INHERITS density;
                                      out-degree 1.45, ~49 300 directed edges)
built by the same Pareto generator the engine-scaling sweep uses, so a few hubs
emit many calls and most nodes are near-leaves — the real call-graph shape.

Two query families, timed on that one graph:

  (a) Bounded reachable-set size — the tractable substitute the project ships:
        MATCH (s {id:N})-[:CALLS*1..k]->(n) RETURN count(*)
      cost is O(edges) per hop bounded by the VISITED SET. Timed k=1..6, cold,
      from the graph's busiest hub (the hardest source for the cheap query) and
      from a representative mid-graph source.

  (b) The intractable original — bounded path ENUMERATION:
        CALL algo.MSpaths({... maxLen: 6, pairwise: true, relDirection: 'both',
                           pathCount: 20 ...})
      cost is bounded by the PATH COUNT, which the graph does not bound. Timed
      cold between connected mid-graph seed sets (it completes, returning paths)
      and from a hub seed set (it is REJECTED by the engine's admission control
      when the path frontier exceeds 250 000 — it never returns).

Writes docs/latency.json (machine-readable; viz.py reads it for the plot) and
prints the numbers for docs/latency.md.

Usage (engine must be up — ./setup.sh / just up):

    uv run python -m scripts.latency_measure               # loads + measures
    uv run python -m scripts.latency_measure --skip-load   # band already resident
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from friction.client import connect, EngineError
from friction.config import Settings
from friction.loader import edge_statement
from friction.paths import build_mspaths_cypher
from friction.probe import load_capabilities
from friction import reach

from scripts.engine_scaling_sweep import gen_call_graph, _chunks

CAPS_PATH = Path("docs/engine-capabilities.md")
OUT_JSON = Path("docs/latency.json")

# A fresh id band, disjoint from every other band in the live `default` graph
# (instance bands 1e10/2e10; scaling-sweep bands 7.1e9+; reach test 4.1e10). The
# base sits in the 45e9 family the audit prescribed; the exact offset keeps every
# query string never-before-run so each measurement is genuinely COLD (the engine
# caches result strings — see docs/engine-scaling.md Finding 0).
BASE = 45_200_000_000
DEFAULT_NODES = 34_000
DEFAULT_BOTH_DEGREE = 2.9   # django CALLS+HAS_METHOD+INHERITS; out-degree = bd/2
MAX_K = 6
TIMEOUT_MS = 29_999         # the engine's hard per-query timeout
FRONTIER_CAP = 250_000      # the engine's path-frontier admission-control cap
BATCH = 1000
SEED = 20260816


def _node_statement(caps) -> str:
    if caps.node_loader_form != "merge_set_label":
        raise ValueError(
            f"unexpected node loader form {caps.node_loader_form!r}; "
            "only 'merge_set_label' is proven on this build")
    return "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Function, n.sid = row.sid"


def load_graph(transport, caps, base: int, n: int,
               edges: list[tuple[int, int]]) -> None:
    node_stmt = _node_statement(caps)
    node_rows = [{"id": base + i, "sid": str(base + i)} for i in range(n)]
    for chunk in _chunks(node_rows, BATCH):
        transport.query(node_stmt, {"rows": chunk})
    edge_stmt = edge_statement(caps, "CALLS")
    edge_rows = [{"src": base + s, "dst": base + d} for s, d in edges]
    for chunk in _chunks(edge_rows, BATCH):
        transport.query(edge_stmt, {"rows": chunk})


def _build_nx(edges, n):
    import networkx as nx
    g = nx.DiGraph()
    g.add_nodes_from(range(n))
    g.add_edges_from(edges)
    return g


def _reach_by_hop(g, u: int, k: int):
    """(reachable set, per-hop new-node sets) for a source, walk semantics."""
    reachable: set[int] = set()
    hops: list[set[int]] = []
    frontier = {u}
    for _ in range(k):
        nxt: set[int] = set()
        for x in frontier:
            nxt.update(g.successors(x))
        reachable |= nxt
        hops.append(set(nxt))
        frontier = nxt
        if not frontier:
            break
    return reachable, hops


def choose_sources(g, n: int):
    """Deterministically pick the busiest hub and a representative mid-graph
    source, plus a connected seed set for the completing MSpaths run.

    * hub               = the node with the largest 6-hop reachable set (the
                          hardest source for count(*), and the seed that makes
                          MSpaths' frontier explode).
    * mid source        = the node whose 6-hop reachable set is the median among
                          nodes that reach a non-trivial set (>10). A typical
                          well-connected function, not the global hub.
    * mid seed set      = mid source + up to 2 of its successors that still emit
                          edges (MSpaths sources), and 3 nodes 4..6 hops
                          downstream (MSpaths targets), so real directed paths of
                          length <= 6 connect the two sets.
    """
    scored = []
    for u in range(n):
        if g.out_degree(u) == 0:
            continue
        size = len(_reach_by_hop(g, u, MAX_K)[0])
        if size > 1:
            scored.append((size, u))
    scored.sort(reverse=True)
    hub = scored[0][1]

    nontrivial = [(s, u) for s, u in scored if s > 10]
    nontrivial.sort()  # ascending by reach size
    mid_size, mid = nontrivial[len(nontrivial) // 2]

    _, mid_hops = _reach_by_hop(g, mid, MAX_K)
    succ = [v for v in g.successors(mid) if g.out_degree(v) > 0][:2]
    mid_src = [mid] + succ
    deep: set[int] = set()
    for hi in range(3, len(mid_hops)):   # hops 4..6 (0-indexed 3..5)
        deep |= mid_hops[hi]
    deep.discard(mid)
    mid_dst = sorted(deep)[:3]

    # Hub enumeration case: a SINGLE hub source to one target a few hops out.
    # relDirection 'both' from a 1000+-out-degree hub explodes the path frontier
    # past the engine's 250 000 admission cap, so this is the "enumeration cannot
    # even answer" witness — deterministic for a hub this dense.
    _, hub_hops = _reach_by_hop(g, hub, MAX_K)
    hub_target = sorted(hub_hops[1])[0] if len(hub_hops) > 1 else hub
    hub_src = [hub]
    hub_dst = [hub_target]

    return {
        "hub": hub, "hub_reach6": scored[0][0],
        "mid": mid, "mid_reach6": mid_size,
        "mid_src": mid_src, "mid_dst": mid_dst,
        "hub_src": hub_src, "hub_dst": hub_dst,
    }


def measure_reach(transport, source_local: int) -> list[dict]:
    """count(*) reachable-set size at k=1..MAX_K, each timed cold + independently."""
    rows = []
    source_id = BASE + source_local
    for k in range(1, MAX_K + 1):
        cypher = reach.build_reach_cypher(source_id, "CALLS", k, "out")
        start = time.perf_counter()
        result = transport.query(cypher)
        millis = (time.perf_counter() - start) * 1000.0
        rows.append({"k": k, "millis": round(millis, 2),
                     "size": reach._count(result)})
    return rows


def measure_mspaths(transport, caps, settings, src_local, dst_local) -> dict:
    src = [BASE + u for u in src_local]
    dst = [BASE + u for u in dst_local]
    cypher = build_mspaths_cypher(caps, settings, ("CALLS",), src, dst)
    start = time.perf_counter()
    try:
        result = transport.query(cypher)
    except EngineError as exc:
        millis = (time.perf_counter() - start) * 1000.0
        msg = str(exc)
        rejected = "admission control" in msg
        return {"millis": round(millis, 2), "answered": False,
                "rejected_admission_control": rejected,
                "timed_out": ("imeout" in msg.lower() or "erminated" in msg),
                "paths": 0, "error": msg[:200],
                "source_ids": src, "target_ids": dst}
    millis = (time.perf_counter() - start) * 1000.0
    return {"millis": round(millis, 2),
            "answered": millis < TIMEOUT_MS,
            "rejected_admission_control": False,
            "timed_out": millis >= TIMEOUT_MS,
            "paths": len(result),
            "source_ids": src, "target_ids": dst}


def main() -> None:
    ap = argparse.ArgumentParser(prog="latency_measure")
    ap.add_argument("--nodes", type=int, default=DEFAULT_NODES)
    ap.add_argument("--both-degree", type=float, default=DEFAULT_BOTH_DEGREE)
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--skip-load", action="store_true",
                    help="graph already resident in the band (edges use CREATE, "
                         "so re-loading would duplicate them); measure only")
    args = ap.parse_args()

    n, both_degree = args.nodes, args.both_degree
    out_degree = both_degree / 2.0
    edges = gen_call_graph(n, out_degree, SEED)

    settings = Settings.from_env()
    settings = Settings(**{**settings.__dict__, "max_len": MAX_K})
    caps = load_capabilities(CAPS_PATH)
    transport = connect(settings, prefer="bolt")

    try:
        if args.skip_load:
            print(f"[load] SKIPPED — measuring the graph already resident in "
                  f"band {BASE} ({n} nodes / {len(edges)} edges).")
        else:
            print(f"[load] {n} nodes / {len(edges)} edges "
                  f"(both-degree {both_degree}, out-degree {out_degree:g}) "
                  f"into band {BASE} ...")
            load_graph(transport, caps, BASE, n, edges)

        print("[pick] choosing hub + representative sources (networkx) ...")
        g = _build_nx(edges, n)
        sel = choose_sources(g, n)
        print(f"    hub local={sel['hub']} reach6={sel['hub_reach6']}; "
              f"mid local={sel['mid']} reach6={sel['mid_reach6']}")

        print(f"[reach] count(*) from HUB id={BASE + sel['hub']} k=1..{MAX_K} ...")
        reach_hub = measure_reach(transport, sel["hub"])
        for r in reach_hub:
            print(f"    k={r['k']}: {r['millis']} ms  (set size {r['size']})")

        print(f"[reach] count(*) from MID id={BASE + sel['mid']} k=1..{MAX_K} ...")
        reach_mid = measure_reach(transport, sel["mid"])
        for r in reach_mid:
            print(f"    k={r['k']}: {r['millis']} ms  (set size {r['size']})")

        print(f"[enum] MSpaths maxLen {MAX_K} from MID connected seeds ...")
        enum_mid = measure_mspaths(transport, caps, settings,
                                   sel["mid_src"], sel["mid_dst"])
        print(f"    {enum_mid['millis']} ms  answered={enum_mid['answered']} "
              f"paths={enum_mid['paths']}")

        print(f"[enum] MSpaths maxLen {MAX_K} from HUB seed set ...")
        enum_hub = measure_mspaths(transport, caps, settings,
                                   sel["hub_src"], sel["hub_dst"])
        tag = ("REJECTED (admission control)"
               if enum_hub["rejected_admission_control"]
               else ("TIMED OUT" if enum_hub["timed_out"] else "completed"))
        print(f"    {enum_hub['millis']} ms  {tag} paths={enum_hub['paths']}")

        hub_ms = [r["millis"] for r in reach_hub]
        mid_ms = [r["millis"] for r in reach_mid]
        reach_hub_max = max(hub_ms)
        reach_mid_min, reach_mid_max = min(mid_ms), max(mid_ms)

        # Ratio, honest, at TWO operating points on the one graph:
        #  * typical: enumeration between connected mid seeds vs a typical count(*)
        #    probe (the mid source's own band). This is the "same intuition, two
        #    queries" comparison the substrate claim is about.
        #  * hub (conservative): enumeration vs count(*)'s HARDEST case (the
        #    busiest hub). If enumeration timed out, the ratio is a lower bound.
        enum_mid_ms = enum_mid["millis"] if enum_mid["answered"] else TIMEOUT_MS
        typical_lo = round(enum_mid_ms / reach_mid_max, 1)
        typical_hi = round(enum_mid_ms / reach_mid_min, 1)
        if enum_mid["answered"]:
            ratio, ratio_kind = round(enum_mid_ms / reach_hub_max, 1), "measured"
        else:
            ratio, ratio_kind = round(TIMEOUT_MS / reach_hub_max, 1), "lower_bound"

        payload = {
            "graph": {
                "nodes": n, "edges": len(edges),
                "both_degree": both_degree, "out_degree": out_degree,
                "band": BASE, "seed": SEED,
                "generator": "scripts.engine_scaling_sweep.gen_call_graph "
                             "(Pareto out-degree; hubs + near-leaves)",
                "note": "one graph at django scale (~34k nodes) and django "
                        "density (both-degree ~2.9); both queries run on it.",
            },
            "reach_count_star": {
                "query_shape": "MATCH (s {id:N})-[:CALLS*1..k]->(n) RETURN count(*)",
                "direction": "out",
                "cost_bound": "visited SET (<= graph size)",
                "hub": {
                    "source_id": BASE + sel["hub"], "reach6_nodes": sel["hub_reach6"],
                    "rows": reach_hub,
                    "min_millis": min(hub_ms), "max_millis": max(hub_ms),
                },
                "mid": {
                    "source_id": BASE + sel["mid"], "reach6_nodes": sel["mid_reach6"],
                    "rows": reach_mid,
                    "min_millis": min(mid_ms), "max_millis": max(mid_ms),
                },
            },
            "mspaths_enumeration": {
                "query_shape": "CALL algo.MSpaths({... maxLen: 6, pairwise: true, "
                               "relDirection: 'both', pathCount: 20 ...})",
                "max_len": MAX_K,
                "cost_bound": "path COUNT (unbounded by the graph)",
                "mid_connected_seeds": enum_mid,
                "hub_seed_set": enum_hub,
            },
            "ratio": {
                "value": ratio,
                "kind": ratio_kind,
                "definition": "MSpaths(mid connected seeds) millis / slowest "
                              "count(*) probe on the graph (busiest hub, k=6)",
                "typical_operating_point": {
                    "range_x": [typical_lo, typical_hi],
                    "definition": "MSpaths(mid connected seeds) millis / a typical "
                                  "count(*) probe (mid source, min..max ms)",
                },
                "hub_same_source": {
                    "count_star_max_millis": reach_hub_max,
                    "enumeration": ("timed_out_30s" if enum_hub["timed_out"]
                                    else ("rejected_admission_control"
                                          if enum_hub["rejected_admission_control"]
                                          else "completed_%sms" % enum_hub["millis"])),
                    "note": "from the SAME busiest-hub source, count(*) completes "
                            "while enumeration " + (
                                "times out at the 30,000 ms ceiling and never "
                                "returns" if enum_hub["timed_out"] else
                                ("is rejected by admission control (frontier > %d) "
                                 "and never returns" % FRONTIER_CAP
                                 if enum_hub["rejected_admission_control"]
                                 else "costs %s ms" % enum_hub["millis"])),
                },
            },
            "timeout_ceiling_millis": TIMEOUT_MS,
            "frontier_cap": FRONTIER_CAP,
            "engine_commit": (Path("docs/pinned-engine-commit.txt").read_text().strip()
                              if Path("docs/pinned-engine-commit.txt").exists() else None),
        }
        Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\n[ratio] MSpaths(mid) {enum_mid['millis']} ms vs slowest "
              f"count(*) {reach_hub_max} ms => "
              f"{'>=' if ratio_kind == 'lower_bound' else '~'}{round(ratio, 1)}x")
        print(f"wrote {args.out}")
    finally:
        transport.close()


if __name__ == "__main__":
    main()

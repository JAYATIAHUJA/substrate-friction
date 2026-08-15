"""Fold dynamic COVERS edges into the type-resolved arm B graph, then re-measure
directed test->fix connectivity.

The tracer (:mod:`friction.trace`) emits ``COVERS`` edges keyed by
``path/to/file.py::co_name`` -- a *file* and a *bare function name*. Arm B nodes
are SCIP canonical symbols, ``<module>::<Class>#<member>``. To fold one graph
into the other both must live in a single identity space, so this module maps
COVERS endpoints through the SAME normalizers the delta analysis uses
(:mod:`friction.identity`): arm B nodes via :func:`identity.normalize_scip`,
COVERS endpoints via :func:`identity.normalize_qualname`.

That join is honest but lossy in one specific, reported way. Python's ``co_name``
is the bare method name with no enclosing class (``__call__``, not
``URLValidator.__call__``), while SCIP keeps the class. A module-level function
rejoins its symbol exactly; a *method* cannot. The mapping success rate is
therefore reported, loudly, alongside every connectivity number: an unmapped
COVERS edge is not a connectivity improvement, and pretending otherwise would be
the exact kind of dishonest measurement this project exists to avoid.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from friction import identity
from friction.connectivity import ConnectivityReport, connected_within, load_graph

DEFAULT_PREFIX = "data.repos.django."


def merge_covers(static_edges, covers_edges):
    """Union static and dynamic edges into one provenance-tagged edge list.

    Both inputs are iterables of ``(src, dst)`` in the *same* node-id space (map
    COVERS strings with :func:`map_covers_to_ids` first). An edge already present
    statically keeps ``source='static'``; a dynamic edge not seen statically is
    added as ``source='dynamic'``. Duplicates are collapsed, never double-counted.

    Returns ``(merged, stats)`` where ``merged`` is ``list[(src, dst, source)]``.
    """
    static_set: set[tuple] = set()
    merged: list[tuple] = []
    for s, d in static_edges:
        if (s, d) in static_set:
            continue
        static_set.add((s, d))
        merged.append((s, d, "static"))

    added = dup = 0
    dyn_seen: set[tuple] = set()
    for s, d in covers_edges:
        if (s, d) in static_set:
            dup += 1
            continue
        if (s, d) in dyn_seen:
            dup += 1
            continue
        dyn_seen.add((s, d))
        merged.append((s, d, "dynamic"))
        added += 1

    stats = {
        "static": len(static_set),
        "dynamic_added": added,
        "dynamic_duplicate": dup,
        "total": len(merged),
    }
    return merged, stats


def graph_from_merged(merged) -> nx.DiGraph:
    """Directed graph carrying edge provenance in the ``source`` attribute."""
    g = nx.DiGraph()
    for s, d, source in merged:
        g.add_edge(s, d, source=source)
    return g


def covers_identity(node: str) -> str | None:
    """A tracer ``path::name`` node -> the shared ``scope::leaf`` identity.

    Reuses :func:`identity.normalize_qualname`: the file path becomes a dotted
    module and the bare name is appended, exactly as a tree-sitter qualname would
    read for a *module-level* symbol.
    """
    path, sep, name = node.partition("::")
    if not sep:
        return None
    if path.endswith(".py"):
        path = path[:-3]
    module = path.replace("/", ".")
    dotted = f"{module}.{name}" if name else module
    return identity.normalize_qualname(dotted)


def build_identity_index(nodes_path: Path,
                         prefix: str = DEFAULT_PREFIX) -> dict[str, set[int]]:
    """arm B ``nodes.ndjson`` -> {shared identity -> set(node id)}."""
    index: dict[str, set[int]] = {}
    with Path(nodes_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            ident = identity.normalize_scip(n["qual"], prefix)
            if ident is None:
                continue
            index.setdefault(ident, set()).add(int(n["id"]))
    return index


def _lax_node_key(qual: str, prefix: str) -> tuple[str, str] | None:
    """arm B qual -> (module_no_prefix, bare_final_name), dropping the class.

    The deliberate counterpart to the strict SCIP identity: it discards the
    enclosing class so it can meet the tracer's class-free ``co_name`` halfway.
    Higher recall, but ambiguous when two classes in one module share a member
    name -- so it is reported as a *sensitivity* fold, never as the headline.
    """
    module, sep, rest = qual.partition("::")
    if not sep:
        return None
    if module.startswith(prefix):
        module = module[len(prefix):]
    rest = rest.rstrip("().#")
    if "#" in rest:
        name = rest.rsplit("#", 1)[-1]
    else:
        name = rest.rsplit(".", 1)[-1] if "." in rest else rest
    return (module, name)


def _lax_covers_key(node: str) -> tuple[str, str] | None:
    """tracer ``path::co_name`` -> (module_dotted, co_name)."""
    path, sep, name = node.partition("::")
    if not sep:
        return None
    if path.endswith(".py"):
        path = path[:-3]
    return (path.replace("/", "."), name)


def build_lax_index(nodes_path: Path,
                    prefix: str = DEFAULT_PREFIX) -> dict[tuple[str, str], set[int]]:
    """arm B ``nodes.ndjson`` -> {(module, bare_name) -> set(node id)}."""
    index: dict[tuple[str, str], set[int]] = {}
    with Path(nodes_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n = json.loads(line)
            k = _lax_node_key(n["qual"], prefix)
            if k is None:
                continue
            index.setdefault(k, set()).add(int(n["id"]))
    return index


def map_covers_lax(covers_edges, lax_index):
    """Map COVERS edges by (module, bare_name), ignoring class. Same return
    shape as :func:`map_covers_to_ids`."""
    mapped: list[tuple[int, int]] = []
    edges = edges_mapped = 0
    endpoints = endpoints_mapped = 0
    for s, d in covers_edges:
        edges += 1
        endpoints += 2
        s_ids = lax_index.get(_lax_covers_key(s), set())
        d_ids = lax_index.get(_lax_covers_key(d), set())
        if s_ids:
            endpoints_mapped += 1
        if d_ids:
            endpoints_mapped += 1
        if s_ids and d_ids:
            edges_mapped += 1
            for a in s_ids:
                for b in d_ids:
                    mapped.append((a, b))
    stats = {
        "covers_edges": edges,
        "covers_edges_mapped": edges_mapped,
        "endpoints": endpoints,
        "endpoints_mapped": endpoints_mapped,
        "expanded_edges": len(mapped),
    }
    return mapped, stats


def map_covers_to_ids(covers_edges, index: dict[str, set[int]]):
    """Map string COVERS edges into arm B node ids via the identity index.

    Returns ``(mapped, stats)``. ``mapped`` is the list of ``(src_id, dst_id)``
    integer edges for every COVERS edge whose BOTH endpoints resolved (an edge is
    expanded across all ids sharing an identity). ``stats`` reports the mapping
    success rate -- the number that decides whether COVERS folds in at all.
    """
    mapped: list[tuple[int, int]] = []
    edges = edges_mapped = 0
    endpoints = endpoints_mapped = 0
    for s, d in covers_edges:
        edges += 1
        endpoints += 2
        s_ids = index.get(covers_identity(s) or "", set())
        d_ids = index.get(covers_identity(d) or "", set())
        if s_ids:
            endpoints_mapped += 1
        if d_ids:
            endpoints_mapped += 1
        if s_ids and d_ids:
            edges_mapped += 1
            for a in s_ids:
                for b in d_ids:
                    mapped.append((a, b))
    stats = {
        "covers_edges": edges,
        "covers_edges_mapped": edges_mapped,
        "endpoints": endpoints,
        "endpoints_mapped": endpoints_mapped,
        "expanded_edges": len(mapped),
    }
    return mapped, stats


def _load_covers(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [tuple(e) for e in payload.get("covers", [])]


def connectivity_with_covers(manifest_path: Path, arms_root: Path,
                             covers_root: Path,
                             prefix: str = DEFAULT_PREFIX,
                             mapping: str = "scip") -> ConnectivityReport:
    """Re-measure arm B ``test->fix`` connectivity with COVERS folded in.

    Only instances that carry both endpoints AND have a persisted COVERS trace
    are counted, so the before/after comparison is over the SAME instance set.
    The per-instance record additionally carries ``test_to_fix_static`` (the
    baseline for that instance) and the mapping stats, so the report can state
    exactly how much of any change is real folded-in structure vs a bookkeeping
    artefact.
    """
    manifest_path = Path(manifest_path)
    arms_root = Path(arms_root)
    covers_root = Path(covers_root)

    per_instance: dict[str, dict] = {}
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            iid = record["instance_id"]
            entry = record.get("arm_b") or {}
            fix = list(entry.get("fix_site_ids") or [])
            test = list(entry.get("test_target_ids") or [])
            if not fix or not test:
                continue
            covers_path = covers_root / f"{iid}.json"
            edges_path = arms_root / iid / "arm_b" / "edges.ndjson"
            nodes_path = arms_root / iid / "arm_b" / "nodes.ndjson"
            if not covers_path.exists() or not edges_path.exists():
                continue

            g = load_graph(edges_path)
            static_before = connected_within(g, test, fix, 6, undirected=False)

            covers = _load_covers(covers_path)
            if mapping == "lax":
                mapped, mstats = map_covers_lax(
                    covers, build_lax_index(nodes_path, prefix))
            else:
                mapped, mstats = map_covers_to_ids(
                    covers, build_identity_index(nodes_path, prefix))
            merged, mergestats = merge_covers(g.edges(), mapped)
            gm = graph_from_merged(merged)

            per_instance[iid] = {
                "test_to_fix_static": static_before,
                "test_to_fix": connected_within(gm, test, fix, 6, undirected=False),
                "fix_to_test": connected_within(gm, fix, test, 6, undirected=False),
                "undirected_6": connected_within(gm, fix, test, 6, undirected=True),
                "undirected_10": connected_within(gm, fix, test, 10, undirected=True),
                "n_fix": len(fix),
                "n_test": len(test),
                "static_edges": g.number_of_edges(),
                "dynamic_edges_added": mergestats["dynamic_added"],
                "covers_map_rate": mstats,
            }

    def _count(key: str) -> int:
        return sum(1 for r in per_instance.values() if r[key] is True)

    report = ConnectivityReport(
        n=len(per_instance),
        fix_to_test=_count("fix_to_test"),
        test_to_fix=_count("test_to_fix"),
        undirected_6=_count("undirected_6"),
        undirected_10=_count("undirected_10"),
        per_instance=per_instance,
    )
    return report

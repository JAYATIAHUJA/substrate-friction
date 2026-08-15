"""Distil the 4.0 GB working corpus (``data/instances/arms/``) into the shipped
payload (``data/shipped/arms/``, <= 50 MB) a judge's clean clone actually needs.

WHAT IS CUT AND WHY
-------------------
``data/instances/arms/<id>/`` holds, per instance: the full ``index.scip`` (~67 MB
each, the pyright SCIP index) and the *complete* arm-A and arm-B call graphs
(``arm_a``/``arm_b`` ``nodes.ndjson`` + ``edges.ndjson``). That is ~4.0 GB across
50 instances and none of it is needed to *run* the product:

* ``friction compare`` / ``list`` / ``delta`` / ``eval`` are cache-backed — they
  read only ``arms/manifest.jsonl`` + ``arms/path_stats.json`` + the ``docs/``
  reports, never a graph. So the cache is shipped whole.
* To *live-load* an arm into the engine and run one real ``algo.MSpaths``, only
  the bounded neighbourhood the query is defined over is needed. Every node that
  can lie on a bounded fix->test path is within ``maxLen`` hops of an endpoint
  (see ``friction.subgraph``), so the induced ``maxLen``-hop neighbourhood of the
  endpoints — capped at the engine's real envelope (``NODE_BUDGET`` /
  ``EDGE_BUDGET``) — is a faithful, resident-loadable slice.

So this ships, per instance, the induced neighbourhood of ``fix_site_ids UNION
test_target_ids`` for BOTH arms, gzipped, in the arms' own disjoint id bands (so
every id in the shipped manifest still addresses a loaded node). The full
per-arm graphs, the ``.scip`` indexes, and the django checkout are NOT shipped;
they are regeneration inputs (``scripts/build_arms.py`` rebuilds them).

HONESTY NOTE recorded in the manifest we copy: arm B neighbourhoods are
budget-TRUNCATED (arm B is ~4x denser; the maxLen-6 neighbourhood exceeds the
24k-edge budget), so a live query on a shipped arm-B slice is NOT the full-graph
object ``path_stats.json`` measured — the faithful live demonstration is arm A
(sparse, untruncated). Arm B's full-graph unanswerability is the *cached*
measurement, not something re-derivable from the shipped truncated slice.

Run:  uv run python scripts/distil_shipped.py
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

from friction.parsing.calls import Edge
from friction.subgraph import (
    EDGE_BUDGET,
    NODE_BUDGET,
    TRAVERSED_TYPES,
    induced_neighbourhood,
)

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "data" / "instances" / "arms"
DST = REPO / "data" / "shipped" / "arms"
HOPS = 6  # settings.max_len — the length the friction path query is bounded to


def _read_manifest(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            out[rec["instance_id"]] = rec
    return out


def _neighbourhood(inst_dir: Path, arm_key: str, seeds: list[int]) -> tuple[list[dict], list[dict], bool]:
    d = inst_dir / arm_key
    nodes: dict[int, dict] = {}
    for line in (d / "nodes.ndjson").open(encoding="utf-8"):
        o = json.loads(line)
        nodes[o["id"]] = o
    edges: list[Edge] = []
    for line in (d / "edges.ndjson").open(encoding="utf-8"):
        o = json.loads(line)
        if o["type"] in TRAVERSED_TYPES:
            edges.append(Edge(o["src"], o["dst"], o["type"], o.get("weight", 1)))
    kept_edges, stats = induced_neighbourhood(edges, seeds, HOPS, NODE_BUDGET, EDGE_BUDGET)
    kept_ids = set(stats["kept_node_ids"])
    node_rows = [nodes[i] for i in sorted(kept_ids) if i in nodes]
    edge_rows = [{"src": e.src, "dst": e.dst, "type": e.type, "weight": e.weight}
                 for e in kept_edges]
    return node_rows, edge_rows, bool(stats["truncated"])


def _write_gz(rows: list[dict], path: Path) -> int:
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path.stat().st_size


def main() -> None:
    manifest = _read_manifest(SRC / "manifest.jsonl")
    if DST.exists():
        # Only clear the per-instance neighbourhood dirs; keep nothing stale.
        for child in DST.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
    DST.mkdir(parents=True, exist_ok=True)

    # The cache the CLI reads, verbatim.
    shutil.copy2(SRC / "manifest.jsonl", DST / "manifest.jsonl")
    shutil.copy2(SRC / "path_stats.json", DST / "path_stats.json")

    total = 0
    n_trunc_a = n_trunc_b = 0
    per_inst = []
    for iid, rec in manifest.items():
        inst_dir = SRC / iid
        out_dir = DST / iid
        out_dir.mkdir(parents=True, exist_ok=True)
        all_nodes: list[dict] = []
        all_edges: list[dict] = []
        for arm_key in ("arm_a", "arm_b"):
            seeds = [int(x) for x in (rec[arm_key].get("fix_site_ids") or [])]
            seeds += [int(x) for x in (rec[arm_key].get("test_target_ids") or [])]
            nr, er, trunc = _neighbourhood(inst_dir, arm_key, seeds)
            all_nodes += nr
            all_edges += er
            if trunc and arm_key == "arm_a":
                n_trunc_a += 1
            if trunc and arm_key == "arm_b":
                n_trunc_b += 1
        nb = _write_gz(all_nodes, out_dir / "nodes.ndjson.gz")
        eb = _write_gz(all_edges, out_dir / "edges.ndjson.gz")
        total += nb + eb
        per_inst.append((iid, len(all_nodes), len(all_edges), nb + eb))

    print(f"distilled {len(manifest)} instances (both arms) -> {DST}")
    print(f"total neighbourhood payload: {total / 1e6:.2f} MB gzipped")
    print(f"arm A truncated: {n_trunc_a}/{len(manifest)}   "
          f"arm B truncated: {n_trunc_b}/{len(manifest)}")


if __name__ == "__main__":
    main()

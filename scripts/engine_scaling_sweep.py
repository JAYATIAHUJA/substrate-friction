#!/usr/bin/env python
"""Engine scaling sweep for the friction query, against a live HydraDB node.

This is the committed, runnable reproduction of the table in
``docs/engine-scaling.md`` (Finding 1). It generates call-graph-shaped synthetic
graphs, loads each into its own disjoint id band, and times the REAL friction
query shape — ``algo.MSpaths`` with ``pairwise: true``, ``relDirection: 'both'``,
``pathCount: 20`` and ``sourceValues``/``targetValues`` inlined as Cypher string
literals against the ``sid`` property — cold and warm, at maxLen 4/5/6.

PROVENANCE OF THE COMMITTED TABLE. The numbers currently in
``docs/engine-scaling.md`` were produced by an earlier, equivalent harness
(``scaling.py`` + ``sweep_healthy.py``) that lived in the build session's
scratchpad and was not committed. This script is a faithful re-implementation of
that harness: same generator contract, same degree convention, same id-band
placement, and the same inlined-literal MSpaths query built by
``friction.paths.build_mspaths_cypher``. Re-running it against the pinned engine
build reproduces the same table shape; the individual milliseconds will differ
run-to-run because cost is dominated by interior seed placement (the doc records
a 1-2 order-of-magnitude placement swing at large n).

Usage (engine must be up — see ``./setup.sh`` / ``just up``)::

    uv run python -m scripts.engine_scaling_sweep            # full sweep, writes JSON
    uv run python scripts/engine_scaling_sweep.py --smoke    # one small cell, ~seconds
    uv run python scripts/engine_scaling_sweep.py \
        --nodes 500,2000 --both-degrees 3 --max-lens 4,5,6

The default sweep writes ``docs/plots/engine_scaling_sweep_results.json`` and
prints the markdown tables to stdout. It does NOT overwrite the prose in
``docs/engine-scaling.md``; paste/compare by hand so a fresh run never silently
rewrites a committed number.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from friction.client import connect
from friction.config import Settings
from friction.loader import edge_statement
from friction.paths import build_mspaths_cypher
from friction.probe import Capabilities, load_capabilities

# --- sweep grid (matches docs/engine-scaling.md Finding 1) --------------------
NODE_COUNTS = [500, 2_000, 8_000, 16_000, 34_000]
BOTH_DEGREES = [2, 3, 4]          # undirected (in+out) degree; out_degree = bd/2
MAX_LENS = [4, 5, 6]
REL_TYPES = ("CALLS",)            # synthetic graphs carry a single CALLS relation
SEEDS_PER_SIDE = 3               # 3 source ids x 3 target ids -> 9 pairs, pairwise
BAND_BASE = 7_100_000_000
BAND_STRIDE = 50_000_000          # wider than the largest graph (34 000 nodes)
BATCH_SIZE = 1000                # engine admission control rejects > 1024/UNWIND

CAPS_PATH = Path("docs/engine-capabilities.md")
RESULTS_PATH = Path("docs/plots/engine_scaling_sweep_results.json")


def gen_call_graph(n: int, out_degree: float, seed: int) -> list[tuple[int, int]]:
    """Directed call-graph-shaped edge list over node ids ``0..n-1``.

    Out-degree is Pareto-weighted (a few hubs emit many calls); targets are
    random (small-world; cycles arise naturally). Total edges = round(out_degree
    * n), so ``out_degree = both_degree / 2`` gives an undirected/both-direction
    degree of ~both_degree. Mirrors the retracted-and-corrected sweep's
    ``gen_call_graph(n, out_degree, seed)`` generator.
    """
    rng = random.Random(seed)
    total_edges = round(out_degree * n)
    # Pareto(alpha) weights make a heavy-tailed source distribution (hubs).
    weights = [rng.paretovariate(1.5) for _ in range(n)]
    cum: list[float] = []
    running = 0.0
    for w in weights:
        running += w
        cum.append(running)
    total_w = cum[-1]

    def pick_source() -> int:
        target = rng.random() * total_w
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        return lo

    edges: set[tuple[int, int]] = set()
    guard = 0
    while len(edges) < total_edges and guard < total_edges * 20 + 100:
        guard += 1
        src = pick_source()
        dst = rng.randrange(n)
        if dst != src:
            edges.add((src, dst))
    return list(edges)


def _node_statement(caps: Capabilities) -> str:
    """Minimal Function upsert (id + string sid only) in the one proven form.

    The synthetic graphs need only ``id`` and ``sid``; the full loader's
    NODE_PROPS carry django-specific columns that do not apply here. This mirrors
    ``loader.NODE_FORMS['merge_set_label']`` exactly, restricted to sid.
    """
    if caps.node_loader_form != "merge_set_label":
        raise ValueError(
            f"unexpected node loader form {caps.node_loader_form!r}; "
            "only 'merge_set_label' is proven on this build — re-probe the engine")
    return "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Function, n.sid = row.sid"


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def load_graph(transport, caps: Capabilities, base: int,
               n: int, edges: list[tuple[int, int]]) -> None:
    """Load one synthetic graph into the id band starting at ``base``."""
    node_stmt = _node_statement(caps)
    node_rows = [{"id": base + i, "sid": str(base + i)} for i in range(n)]
    for chunk in _chunks(node_rows, BATCH_SIZE):
        transport.query(node_stmt, {"rows": chunk})

    edge_stmt = edge_statement(caps, "CALLS")
    edge_rows = [{"src": base + s, "dst": base + d} for s, d in edges]
    for chunk in _chunks(edge_rows, BATCH_SIZE):
        transport.query(edge_stmt, {"rows": chunk})


def pick_seeds(base: int, n: int, seed: int) -> tuple[list[int], list[int]]:
    """3 source + 3 target ids from the graph interior (not the 0 -> n-1 corner)."""
    rng = random.Random(seed ^ 0x5EED)
    interior = list(range(n // 10, n - n // 10)) or list(range(n))
    picks = rng.sample(interior, min(2 * SEEDS_PER_SIDE, len(interior)))
    src = [base + p for p in picks[:SEEDS_PER_SIDE]]
    dst = [base + p for p in picks[SEEDS_PER_SIDE:2 * SEEDS_PER_SIDE]]
    return src, dst


def time_query(transport, cypher: str) -> tuple[float, int]:
    start = time.perf_counter()
    rows = transport.query(cypher)
    millis = (time.perf_counter() - start) * 1000.0
    return round(millis, 2), len(rows)


def run_cell(transport, caps: Capabilities, settings: Settings,
             n: int, both_degree: int, band_index: int) -> dict:
    base = BAND_BASE + band_index * BAND_STRIDE
    out_degree = both_degree / 2.0
    seed = 1_000 + band_index
    edges = gen_call_graph(n, out_degree, seed)
    load_graph(transport, caps, base, n, edges)
    src, dst = pick_seeds(base, n, seed)

    cell: dict = {
        "nodes": n, "edges": len(edges), "both_degree": both_degree,
        "band": base, "cold": {}, "warm": {}, "rows": {},
    }
    for max_len in MAX_LENS:
        local = Settings(**{**settings.__dict__, "max_len": max_len})
        cypher = build_mspaths_cypher(caps, local, REL_TYPES, src, dst)
        cold_ms, cold_rows = time_query(transport, cypher)   # first run: cold
        warm_ms, _ = time_query(transport, cypher)           # immediate re-run: warm
        cell["cold"][max_len] = cold_ms
        cell["warm"][max_len] = warm_ms
        cell["rows"][max_len] = cold_rows
    return cell


def render_tables(cells: list[dict]) -> str:
    lines: list[str] = []
    for bd in sorted({c["both_degree"] for c in cells}):
        lines.append(f"\n**both-degree {bd}** (out-degree {bd / 2:g}):\n")
        lines.append("| nodes | edges | band | maxLen 4 | maxLen 5 | maxLen 6 |")
        lines.append("|------:|------:|-----:|---------:|---------:|---------:|")
        for c in [c for c in cells if c["both_degree"] == bd]:
            cold = c["cold"]
            lines.append(
                f"| {c['nodes']:>6} | {c['edges']:>6} | {c['band']} | "
                f"{cold.get(4, '—')} | {cold.get(5, '—')} | {cold.get(6, '—')} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(prog="engine_scaling_sweep")
    parser.add_argument("--nodes", help="comma list, e.g. 500,2000")
    parser.add_argument("--both-degrees", help="comma list, e.g. 2,3,4")
    parser.add_argument("--max-lens", help="comma list, e.g. 4,5,6")
    parser.add_argument("--smoke", action="store_true",
                        help="one tiny cell (500 nodes / bd 2) for a fast liveness check")
    parser.add_argument("--out", default=str(RESULTS_PATH))
    args = parser.parse_args()

    global MAX_LENS
    nodes = [int(x) for x in args.nodes.split(",")] if args.nodes else list(NODE_COUNTS)
    bds = [int(x) for x in args.both_degrees.split(",")] if args.both_degrees else list(BOTH_DEGREES)
    if args.max_lens:
        MAX_LENS = [int(x) for x in args.max_lens.split(",")]
    if args.smoke:
        nodes, bds, MAX_LENS = [500], [2], [4]

    settings = Settings.from_env()
    caps = load_capabilities(CAPS_PATH)
    transport = connect(settings, prefer="bolt")

    cells: list[dict] = []
    band_index = 0
    try:
        for bd in bds:
            for n in nodes:
                cell = run_cell(transport, caps, settings, n, bd, band_index)
                band_index += 1
                cells.append(cell)
                print(f"[done] {n} nodes / bd {bd} / band {cell['band']}: "
                      f"cold {cell['cold']}")
    finally:
        transport.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cells, indent=2))
    print(render_tables(cells))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()

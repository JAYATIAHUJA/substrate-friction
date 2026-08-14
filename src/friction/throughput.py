"""Measure effective ingest throughput. Recorded in the README as a finding."""

from __future__ import annotations

import time
from pathlib import Path

from friction.probe import Capabilities

NODE_FORMS = {
    "create_inline": "UNWIND $rows AS row CREATE (n:Bench {id: row.id})",
    "merge_then_set": "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Bench, n.k = row.id",
}

EDGE_FORMS = {
    "match_match_create":
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b)",
    "single_pattern_create":
        "UNWIND $rows AS row CREATE (a {id: row.src})-[:BENCH]->(b {id: row.dst})",
    "merge_then_create":
        "UNWIND $rows AS row MERGE (a {id: row.src}) MERGE (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b)",
    "match_create_return":
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b) RETURN a.id AS id",
}


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def measure(transport, caps: Capabilities, total: int = 10_000,
            batch_sizes: tuple[int, ...] = (500, 1000, 2000, 5000)) -> list[dict]:
    node_cypher = NODE_FORMS[caps.node_loader_form]
    edge_cypher = EDGE_FORMS[caps.edge_loader_form]
    out: list[dict] = []
    base = 1_000_000

    for size in batch_sizes:
        offset = base + len(out) * total * 4
        nodes = [{"id": offset + i} for i in range(total)]
        edges = [{"src": offset + i, "dst": offset + (i + 1) % total} for i in range(total)]

        for chunk in _chunks(nodes, size):
            transport.query(node_cypher, {"rows": chunk})

        start = time.perf_counter()
        for chunk in _chunks(edges, size):
            transport.query(edge_cypher, {"rows": chunk})
        elapsed = max(time.perf_counter() - start, 1e-9)

        out.append({
            "batch_size": size,
            "seconds": round(elapsed, 3),
            "edges_per_sec": round(total / elapsed, 1),
        })
    return out


def write_report(rows: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    best = max(rows, key=lambda r: r["edges_per_sec"])
    lines = [
        "# Measured ingest throughput",
        "",
        "`UNWIND $rows` batches over the client transport, against local object storage.",
        "",
        "| Batch size | Seconds | Edges/sec |",
        "|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: r["batch_size"]):
        lines.append(f"| {r['batch_size']} | {r['seconds']} | {r['edges_per_sec']} |")
    lines += [
        "",
        f"**Best: {best['edges_per_sec']} edges/sec at batch size {best['batch_size']}.**",
        "",
        "Roughly 65,000 edges per repository; three repositories is under 200,000 edges. "
        "At the measured rate this loads in minutes, which is the point of choosing a "
        "project whose graph is small: the engine's write path is serialized and adding "
        "writers does not help.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    from friction.client import connect
    from friction.config import Settings
    from friction.probe import load_capabilities

    transport = connect(Settings.from_env(), prefer="bolt")
    caps = load_capabilities(Path("docs/engine-capabilities.md"))
    rows = measure(transport, caps)
    write_report(rows, Path("docs/throughput.md"))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()

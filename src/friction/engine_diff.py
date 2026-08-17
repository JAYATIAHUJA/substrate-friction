"""The disagreement set, computed inside HydraDB — edge reification.

`docs/graph-delta.md`'s headline (5,873 compared, 4,381 confirmed, 1,492
unconfirmed) is an anti-join between two edge sets, historically computed
offline. This module makes the engine compute it, by reifying edges as nodes:

    (:AEdge {id})-[:HAS_SIG]->(:Sig {id})<--(:BEdge)   [stored as outward
                                                        (:Sig)-[:SIG_OF_B]->]

Each distinct `(src, dst)` identity becomes one `Sig` node whose id is a
stable hash of the signature. An arm-A edge is CONFIRMED iff a 2-hop outward
walk from its node reaches any arm-B edge node:

    MATCH (a {id: <aedge>})-[:HAS_SIG]->(s)-[:SIG_OF_B]->(b) RETURN count(*)

count > 0 = confirmed, 0 = unconfirmed. The anti-join is therefore a bounded
traversal over the reified meta-graph — engine-resident, and expressed
entirely in forms this engine verifiably parses (`MERGE`-by-id + `SET` node
upserts, single-pattern `CREATE` edges, fixed-length outward MATCH,
`count(*)`; incoming and variable-length forms are rejected on this build and
are not used).

Parity: the engine's confirmed/unconfirmed counts must equal the offline join
exactly (4,381 / 1,492) or `run_engine_diff` raises.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

A_BAND = 800_000_000_000
B_BAND = 810_000_000_000
SIG_BAND = 820_000_000_000


def sig_id(src: str, dst: str) -> int:
    """Stable Sig-node id for one (src, dst) edge identity."""
    digest = hashlib.sha256(f"{src}\x1f{dst}".encode("utf-8")).hexdigest()
    return SIG_BAND + int(digest[:12], 16)


@dataclass(frozen=True)
class EngineDiff:
    a_edges: int
    b_edges: int
    sigs: int
    confirmed: int
    unconfirmed: int
    load_ms: float
    query_ms_total: float
    sample_cypher: str


def run_engine_diff(transport, a_set, b_set, batch: int = 500,
                    progress=None) -> EngineDiff:
    """Load both reified edge sets and compute the anti-join in-engine."""
    a_rows = [{"id": A_BAND + i, "sig": sig_id(s, d)}
              for i, (s, d) in enumerate(sorted(a_set))]
    b_rows = [{"id": B_BAND + i, "sig": sig_id(s, d)}
              for i, (s, d) in enumerate(sorted(b_set))]
    sig_ids = sorted({r["sig"] for r in a_rows} | {r["sig"] for r in b_rows})

    def _chunks(seq):
        for i in range(0, len(seq), batch):
            yield seq[i:i + batch]

    t0 = time.perf_counter()
    for label, rows in (("AEdge", a_rows), ("BEdge", b_rows)):
        for chunk in _chunks(rows):
            transport.query(
                f"UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{label}",
                {"rows": chunk})
    for chunk in _chunks([{"id": s} for s in sig_ids]):
        transport.query(
            "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Sig",
            {"rows": chunk})
    for chunk in _chunks([{"src": r["id"], "dst": r["sig"]} for r in a_rows]):
        transport.query(
            "UNWIND $rows AS row CREATE (a {id: row.src})"
            "-[:HAS_SIG]->(b {id: row.dst})", {"rows": chunk})
    for chunk in _chunks([{"src": r["sig"], "dst": r["id"]} for r in b_rows]):
        transport.query(
            "UNWIND $rows AS row CREATE (a {id: row.src})"
            "-[:SIG_OF_B]->(b {id: row.dst})", {"rows": chunk})
    load_ms = (time.perf_counter() - t0) * 1000

    confirmed = 0
    sample = ""
    t1 = time.perf_counter()
    for r in a_rows:
        cypher = (f"MATCH (a {{id: {r['id']}}})-[:HAS_SIG]->(s)"
                  f"-[:SIG_OF_B]->(b) RETURN count(*) AS n")
        if not sample:
            sample = cypher
        rows = transport.query(cypher)
        n = int(rows[0].get("n", 0)) if rows else 0
        if n > 0:
            confirmed += 1
        if progress and (r["id"] - A_BAND) % 1000 == 999:
            progress(r["id"] - A_BAND + 1, len(a_rows))
    query_ms = (time.perf_counter() - t1) * 1000

    unconfirmed = len(a_rows) - confirmed
    expected = (4381, 1492)
    if (confirmed, unconfirmed) != expected:
        raise RuntimeError(
            f"engine anti-join does not reproduce the offline join: "
            f"engine ({confirmed}, {unconfirmed}) != offline {expected}")

    return EngineDiff(
        a_edges=len(a_rows), b_edges=len(b_rows), sigs=len(sig_ids),
        confirmed=confirmed, unconfirmed=unconfirmed,
        load_ms=round(load_ms, 1), query_ms_total=round(query_ms, 1),
        sample_cypher=sample)

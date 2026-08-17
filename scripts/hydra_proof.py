#!/usr/bin/env python
"""Prove a real round trip against the pinned open-source engine.

Writes two nodes and an edge, then reads them back with the gate's own bounded
backwards walk, and fails loudly if either leg does not work. Exists so CI can
distinguish "the engine container started" from "the engine actually serves
reads and writes" — a distinction this project learned the hard way
(issue #81: reads keep serving after the write path has degraded).
"""

from __future__ import annotations

import sys

from friction.client import connect
from friction.config import Settings
from friction.gate import build_selection_cypher


def main() -> int:
    transport = connect(Settings.from_env(), prefer="bolt")
    print(f"transport: {transport.name}")

    # The verified loader forms (see friction.loader): MERGE-by-id with SET,
    # then MATCH/MATCH/CREATE for the edge. MERGE followed by RETURN does not
    # parse on this build.
    transport.query("UNWIND $rows AS row MERGE (n {id: row.id}) "
                    "SET n:Probe, n.sid = row.sid",
                    {"rows": [{"id": 990001, "sid": "probe-1"},
                              {"id": 990002, "sid": "probe-2"}]})
    # Edge: the live engine's accepted form is the one-hop directed CREATE
    # (see loader.EDGE_FORMS["single_pattern_create"]).
    transport.query("UNWIND $rows AS row "
                    "CREATE (a {id: row.src})-[:CALLS]->(b {id: row.dst})",
                    {"rows": [{"src": 990002, "dst": 990001}]})
    # ...and the reversed relation the backwards walk runs over. The engine
    # rejects incoming variable-length patterns ("variable-length MATCH
    # requires a fixed source id"), so ingest materialises CALLED_BY.
    transport.query("UNWIND $rows AS row "
                    "CREATE (a {id: row.src})-[:CALLED_BY]->(b {id: row.dst})",
                    {"rows": [{"src": 990001, "dst": 990002}]})

    rows = transport.query(build_selection_cypher(990001, "CALLED_BY", 6))
    ids = {int(r["id"]) for r in rows if r.get("id") is not None}
    transport.close()

    if 990002 not in ids:
        print(f"FAIL: backwards walk did not reach the caller; got {ids}")
        return 1
    print(f"OK: backwards walk reached {sorted(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

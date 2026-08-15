"""Bounded-hop reachable-set sizes — the metric that cannot explode.

v2 asked the engine to ENUMERATE bounded paths between two node sets. That is
#P-complete in general (Valiant 1979) and blew up as (branching factor)^maxLen:
on a 79k-edge django graph it answered 3 of 28 instances.

This asks a different question with the same intuition. `MATCH (s)-[:R*1..k]->(n)
RETURN count(n)` lowers, in this engine, to MatchReachable -> ReachableVertices ->
reachable_count_in_hop_range_at (src/shard/query.rs:1008), which runs the masked
GrB_mxv BFS in src/sparse_kernel/graphblas.rs. Cost is O(m) per hop bounded by the
VISITED SET, not by walk volume. The frontier is finite; the path set is not.

Note the engine rejects DISTINCT inside an aggregate, so the query is a plain
count() and we rely on the reachable-set semantics of the lowered plan. Engine
issues #69 (same-frontier edge dropping) and #71 (fixed-hop vs range semantics)
both sit under exactly this call, which is why Task 1 Step 6 validates every
result against a networkx reference before anything downstream trusts it.

DEVIATION FROM PLAN (verified against engine v0.1.1, commit 02a40025, on
2026-08-15): the plan's `RETURN count(n)` is REJECTED by this build the moment a
variable-length (or any) traversal precedes it — it raises the misleading generic
error "property values support integer, float, boolean, and string literals".
`count(*)` and `count(n.id)` are accepted and return the *distinct* reachable-set
size (dedup confirmed: at k=4 count(*)=117, strictly below the 120 length-<=4
walk count, so it is counting the visited SET, not walks). We therefore emit
`RETURN count(*)`. The reachable-set semantics the plan relies on hold exactly:
the query returns |{n : there is a directed walk of length in [1,k] from s to n}|,
which INCLUDES s itself when a return cycle of length <= k exists — validated
against a walk-correct networkx reference at k=1..6 with zero mismatches. (The
plan's own Step-6 reference, a union of `descendants_at_distance`, is subtly wrong
for the source-on-cycle case and spuriously reports a 1-node mismatch at k=6; the
engine is right, the plan's oracle was not. This is neither #69 nor #71.)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from friction.client import EngineError


@dataclass(frozen=True)
class ReachProfile:
    hops: list[int]
    sizes: list[int]
    millis: float
    answered: bool


def build_reach_cypher(node_id: int, rel_type: str, k: int, direction: str) -> str:
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise TypeError(f"node id must be an integer, got {type(node_id).__name__}")
    if not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer (the bound is mandatory)")
    if "|" in rel_type:
        raise ValueError("variable-length patterns are single-typed")
    pattern = (f"-[:{rel_type}*1..{k}]->" if direction == "out"
               else f"<-[:{rel_type}*1..{k}]-")
    # count(*) not count(n): this engine build rejects count(<var>) after a
    # traversal. count(*) over the deduplicated frontier is the reachable-set size.
    return f"MATCH (s {{id: {node_id}}}){pattern}(n) RETURN count(*) AS n"


def _count(rows) -> int:
    if not rows:
        return 0
    row = rows[0]
    if isinstance(row, dict):
        for v in row.values():
            if isinstance(v, int):
                return v
    return 0


def reachable_count(transport, node_id: int, rel_type: str, k: int,
                    direction: str = "out") -> int:
    return _count(transport.query(build_reach_cypher(node_id, rel_type, k, direction)))


def profile(transport, node_id: int, rel_type: str, max_k: int,
            direction: str = "out") -> ReachProfile:
    hops, sizes = [], []
    start = time.perf_counter()
    try:
        for k in range(1, max_k + 1):
            sizes.append(reachable_count(transport, node_id, rel_type, k, direction))
            hops.append(k)
    except EngineError:
        return ReachProfile([], [], round((time.perf_counter() - start) * 1000, 2), False)
    return ReachProfile(hops, sizes, round((time.perf_counter() - start) * 1000, 2), True)


def bidirectional(transport, fix_ids: list[int], test_ids: list[int],
                  rel_type: str, max_k: int) -> dict:
    """Forward profiles from the fix sites, backward profiles from the tests.

    The pair is what carries the structure: forward growth measures how far a
    change can propagate, backward growth measures how much must hold for the
    tests to pass, and their meeting is where the two concerns collide.
    """
    forward = [profile(transport, i, rel_type, max_k, "out") for i in fix_ids]
    backward = [profile(transport, i, rel_type, max_k, "in") for i in test_ids]
    return {"forward": forward, "backward": backward,
            "fix_ids": list(fix_ids), "test_ids": list(test_ids)}

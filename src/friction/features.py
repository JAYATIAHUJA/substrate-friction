"""The hedged secondary metric: structure features from bounded reachability.

Every feature here is derived from **bounded-hop reachable-set sizes and node
degrees** on the offline networkx call graph. Nothing enumerates paths. Path
enumeration between node sets is #P-complete (Valiant 1979) and, measured on this
corpus in v2, timed out at 30 s where the reachability form answers in ~12 ms;
`friction.reach` runs the same bounded-ball query in the engine. This module is
the offline twin used for evaluation, computed with an explicit BFS so the k
bound is visible and the result is reproducible without a running node.

DIRECTION IS NOT OPTIONAL — it is the whole point. Measured on the 44 arm-B
instances with both endpoints mapped, at 6 hops:

* **fix -> test** directed: **0/44 (0%)** — code does not call its tests.
* **test -> fix** directed: **24/44 (55%)** — the natural direction; tests call
  code.
* **undirected** (`relDirection: 'both'`): **43/44 (98%)** — but this means
  "shares a neighbourhood", NOT "the test exercises this code".

Because a single number computed in the wrong direction silently measures the
wrong thing, EVERY feature records which direction produced it:

* ``fwd_growth``     — ball grown OUTWARD (successors) from the FIX sites.
* ``bwd_growth``     — ball grown INWARD (predecessors) from the TEST targets.
* ``overlap_ratio``  — Jaccard of the outward-fix ball and the inward-test ball.
* ``fanin``          — IN-degree (callers) of the fix sites.
* ``test_to_fix_hops`` — shortest DIRECTED hop count test -> fix, else -1.
* ``undirected_hops``  — shortest UNDIRECTED hop count (the weaker relation), else -1.

GROWTH FORMULA (stated so a reviewer can check it). The ball at hop i is the set
of nodes within i hops of the endpoint set in the given direction; ``b_i`` is its
size, and ``b_0`` is the number of endpoint nodes present in the graph. Growth is
the **geometric mean of the per-hop expansion ratios** over the full bound::

    growth = (b_maxk / b_0) ** (1 / maxk)          # b_0 >= 1, else 0.0

This is the k-th root of the total expansion, i.e. the geometric mean of
``b_1/b_0, b_2/b_1, ..., b_maxk/b_(maxk-1)``. ``maxk >= 1`` always (the bound is
mandatory), so the exponent is never ``1/0``, and no term is raised to the power
0. A chain expands by +1 per hop and scores near 1; a tangled, high-fan-out
neighbourhood scores well above 1. When the endpoint set is empty or absent from
the graph (``b_0 == 0``) growth is 0.0, never an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import networkx as nx

FEATURE_NAMES: tuple[str, ...] = (
    "fwd_growth",
    "bwd_growth",
    "overlap_ratio",
    "fanin",
    "test_to_fix_hops",
    "undirected_hops",
)


@dataclass(frozen=True)
class V4Features:
    fwd_growth: float        # outward from FIX sites
    bwd_growth: float        # inward from TEST targets
    overlap_ratio: float     # |fwd ball ∩ bwd ball| / |fwd ∪ bwd|
    fanin: float             # in-degree (callers) of the FIX sites
    test_to_fix_hops: int    # directed test -> fix, or -1 within max_k
    undirected_hops: int     # undirected, or -1 within max_k
    fix_count: int           # context, not scored
    test_count: int          # context, not scored


def _clean_ids(ids: Iterable[int]) -> list[int]:
    # dedup, preserve order, coerce to int
    return list(dict.fromkeys(int(x) for x in ids))


def _ball(g: nx.DiGraph, sources: Iterable[int], max_k: int,
          direction: str) -> tuple[list[int], set[int]]:
    """Return (sizes, final_ball). ``sizes[i]`` is |ball at hop i| for i in
    0..max_k. ``direction`` is 'out' (successors), 'in' (predecessors), or
    'both'. The ball includes the sources themselves at hop 0."""
    present = {s for s in sources if s in g}
    sizes = [len(present)]
    frontier = set(present)
    visited = set(present)
    for _ in range(max_k):
        nxt: set[int] = set()
        for u in frontier:
            if direction in ("out", "both"):
                nxt.update(g.successors(u))
            if direction in ("in", "both"):
                nxt.update(g.predecessors(u))
        nxt -= visited
        visited |= nxt
        sizes.append(len(visited))
        if not nxt:
            # Saturated: pad the remaining hops with the settled size so the
            # exponent in the growth formula always sees a full 0..max_k range.
            while len(sizes) < max_k + 1:
                sizes.append(len(visited))
            break
        frontier = nxt
    return sizes, visited


def _growth(sizes: list[int], max_k: int) -> float:
    """Geometric mean per-hop expansion: (b_maxk / b_0) ** (1/max_k)."""
    b0 = sizes[0]
    if b0 <= 0:
        return 0.0
    bk = sizes[-1]
    return (bk / b0) ** (1.0 / max_k)


def _shortest_hops(g: nx.DiGraph, srcs: Iterable[int], dsts: Iterable[int],
                   max_k: int, undirected: bool) -> int:
    """Shortest hop count from any src to any dst within max_k, else -1.

    Directed follows successors; undirected follows successors and predecessors.
    An overlapping endpoint counts as distance 0. Returns -1 when either set is
    empty or the target is not reached within the bound — never raises."""
    src_set = {int(s) for s in srcs}
    dst_set = {int(d) for d in dsts}
    if not src_set or not dst_set:
        return -1
    if src_set & dst_set:
        return 0
    frontier = {s for s in src_set if s in g}
    visited = set(frontier)
    for hop in range(1, max_k + 1):
        nxt: set[int] = set()
        for u in frontier:
            nxt.update(g.successors(u))
            if undirected:
                nxt.update(g.predecessors(u))
        nxt -= visited
        if not nxt:
            return -1
        if nxt & dst_set:
            return hop
        visited |= nxt
        frontier = nxt
    return -1


def compute(g: nx.DiGraph, fix_ids: Iterable[int], test_ids: Iterable[int],
            max_k: int = 6) -> V4Features:
    """Compute the directional structure features on an offline call graph.

    ``g`` is a networkx DiGraph (edge A->B means A calls B). ``fix_ids`` are the
    patched-code sites, ``test_ids`` the test targets. No path enumeration: every
    feature comes from bounded balls (``_ball``) or bounded shortest-hop BFS."""
    fix = _clean_ids(fix_ids)
    test = _clean_ids(test_ids)

    fwd_sizes, fwd_ball = _ball(g, fix, max_k, "out")   # outward from fix
    bwd_sizes, bwd_ball = _ball(g, test, max_k, "in")   # inward from tests

    union = len(fwd_ball | bwd_ball)
    overlap = (len(fwd_ball & bwd_ball) / union) if union else 0.0

    fanin = sum(g.in_degree(f) for f in fix if f in g)

    return V4Features(
        fwd_growth=_growth(fwd_sizes, max_k),
        bwd_growth=_growth(bwd_sizes, max_k),
        overlap_ratio=overlap,
        fanin=float(fanin),
        test_to_fix_hops=_shortest_hops(g, test, fix, max_k, undirected=False),
        undirected_hops=_shortest_hops(g, test, fix, max_k, undirected=True),
        fix_count=len(fix),
        test_count=len(test),
    )


def as_row(f: V4Features) -> dict[str, float]:
    """The scored feature vector: one float per name in FEATURE_NAMES. The
    context counts (fix_count, test_count) stay off the scored row on purpose —
    they describe the instance, they are not friction signals."""
    return {name: float(getattr(f, name)) for name in FEATURE_NAMES}

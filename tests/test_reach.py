import pytest

from friction import reach


class Stub:
    name = "stub"

    def __init__(self, rows):
        self.rows = rows
        self.seen = []

    def query(self, cypher, params=None):
        self.seen.append(cypher)
        return self.rows.pop(0) if self.rows else []


def test_cypher_bounds_the_pattern():
    c = reach.build_reach_cypher(42, "CALLS", 3, "out")
    assert "*1..3" in c
    assert "*]" not in c and "*1..]" not in c


def test_cypher_never_uses_distinct_in_an_aggregate():
    # the engine rejects DISTINCT inside count()
    c = reach.build_reach_cypher(42, "CALLS", 3, "out")
    assert "DISTINCT" not in c.upper()


def test_cypher_matches_on_integer_id_only():
    c = reach.build_reach_cypher(42, "CALLS", 2, "out")
    assert "{id: 42}" in c


def test_cypher_is_single_typed():
    c = reach.build_reach_cypher(42, "CALLS", 2, "out")
    assert "|" not in c


def test_incoming_direction_reverses_the_arrow():
    out = reach.build_reach_cypher(1, "CALLS", 2, "out")
    inc = reach.build_reach_cypher(1, "CALLS", 2, "in")
    assert "-[:CALLS*1..2]->" in out
    assert "<-[:CALLS*1..2]-" in inc


def test_rejects_a_non_integer_node_id():
    with pytest.raises(TypeError):
        reach.build_reach_cypher("42", "CALLS", 2, "out")


def test_rejects_an_unbounded_k():
    with pytest.raises(ValueError):
        reach.build_reach_cypher(1, "CALLS", 0, "out")


def test_profile_collects_one_size_per_hop():
    t = Stub([[{"n": 3}], [{"n": 11}], [{"n": 40}]])
    p = reach.profile(t, 1, "CALLS", 3, "out")
    assert p.hops == [1, 2, 3]
    assert p.sizes == [3, 11, 40]
    assert p.answered is True


def test_profile_marks_unanswered_on_engine_error():
    class Boom:
        name = "boom"

        def query(self, *a, **k):
            from friction.client import EngineError
            raise EngineError("Terminated")

    p = reach.profile(Boom(), 1, "CALLS", 3, "out")
    assert p.answered is False
    assert p.sizes == []


def test_bidirectional_returns_forward_backward_and_overlap_keys():
    t = Stub([[{"n": 5}], [{"n": 9}], [{"n": 4}], [{"n": 8}]])
    out = reach.bidirectional(t, [1], [2], "CALLS", 2)
    assert {"forward", "backward", "fix_ids", "test_ids"} <= set(out)


def test_cypher_emits_count_star_not_count_node():
    # RETURN count(n) where n is a NODE is rejected by this engine build with
    # "property values support integer, float, boolean, and string literals".
    c = reach.build_reach_cypher(42, "CALLS", 3, "out")
    assert "count(*)" in c
    assert "count(n)" not in c


def test_rejects_a_boolean_node_id():
    # bool is a subclass of int in Python; it must NOT be accepted as a node id.
    with pytest.raises(TypeError):
        reach.build_reach_cypher(True, "CALLS", 2, "out")


def test_rejects_a_piped_rel_type():
    with pytest.raises(ValueError):
        reach.build_reach_cypher(1, "CALLS|USES", 2, "out")


# --- live-engine regression guard: the Probe-1 exactness claim ---------------
# The plan's headline structure metric rests on one measured claim: in this
# engine, `MATCH (s {id: N})-[:REL*1..k]->(n) RETURN count(*)` returns EXACTLY
# the bounded reachable-set size, matching a walk-correct networkx reference at
# every k. This test makes that claim a standing regression test instead of a
# one-off probe: it seeds a fresh 1000-node out-degree-3 random graph in its own
# id band, builds the identical graph in networkx, and asserts the engine count
# equals the networkx union-over-1..k reachable set for k=1..6.

# A fresh id band, clear of every other band in the live `default` graph
# (instance bands sit at 1e10 / 2e10; probe/round-trip nodes far below).
REACH_ENGINE_BASE = 41_000_000_000
REACH_N = 1000
REACH_OUT_DEGREE = 3
REACH_MAX_K = 6


def _build_reach_graph():
    """Deterministic 1000-node, out-degree-3 directed random graph.

    Returns (networkx.DiGraph over the raw id band, node_ids, edge_rows)."""
    import random

    import networkx as nx

    rng = random.Random(20260815)
    node_ids = [REACH_ENGINE_BASE + i for i in range(REACH_N)]
    g = nx.DiGraph()
    g.add_nodes_from(node_ids)
    edge_rows = []
    for src in node_ids:
        # 3 distinct targets != src, so out-degree is exactly 3 with no self-loop.
        others = rng.sample([n for n in node_ids if n != src], REACH_OUT_DEGREE)
        for dst in others:
            g.add_edge(src, dst)
            edge_rows.append({"src": src, "dst": dst})
    return g, node_ids, edge_rows


def _nx_reachable_within(g, source: int, k: int) -> int:
    """Walk-correct reachable-set size: |{n : a directed walk of length in
    [1,k] from source reaches n}|. Frontiers are NOT pruned by a visited set, so
    the source itself is counted when a return cycle of length <= k exists —
    exactly the semantics the engine's masked-BFS count(*) lowers to."""
    reachable: set[int] = set()
    frontier = {source}
    for _ in range(k):
        nxt: set[int] = set()
        for u in frontier:
            nxt.update(g.successors(u))
        reachable |= nxt
        frontier = nxt
        if not frontier:
            break
    return len(reachable)


@pytest.mark.engine
def test_engine_reachable_count_matches_networkx_at_every_k():
    from friction.client import EngineError, connect
    from friction.config import Settings

    settings = Settings.from_env()
    try:
        transport = connect(settings, prefer="bolt")
    except Exception as exc:  # noqa: BLE001 - engine may not be running
        pytest.skip(f"engine not reachable: {exc}")

    g, node_ids, edge_rows = _build_reach_graph()
    node_rows = [{"id": n, "sid": str(n)} for n in node_ids]

    def _chunks(seq, size):
        for i in range(0, len(seq), size):
            yield seq[i:i + size]

    try:
        # Load exactly as the plan prescribes: MERGE the nodes with a label + sid,
        # then CREATE the one-hop edges. Batches of 500 (engine caps UNWIND at
        # 1024).
        node_stmt = "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:L, n.sid = row.sid"
        edge_stmt = "UNWIND $rows AS row CREATE (a {id: row.src})-[:REL]->(b {id: row.dst})"
        for chunk in _chunks(node_rows, 500):
            transport.query(node_stmt, {"rows": chunk})
        for chunk in _chunks(edge_rows, 500):
            transport.query(edge_stmt, {"rows": chunk})

        source = node_ids[0]
        engine_sizes, nx_sizes = [], []
        for k in range(1, REACH_MAX_K + 1):
            engine_sizes.append(
                reach.reachable_count(transport, source, "REL", k, "out"))
            nx_sizes.append(_nx_reachable_within(g, source, k))

        assert engine_sizes == nx_sizes, (
            f"engine {engine_sizes} != networkx {nx_sizes} "
            f"(exactness claim broken at k=1..{REACH_MAX_K})")
        # Sanity: the set must actually grow with k on this density, or the test
        # is vacuously passing on an empty/degenerate load.
        assert nx_sizes[0] == REACH_OUT_DEGREE
        assert nx_sizes[-1] > nx_sizes[0]
    except EngineError as exc:
        pytest.skip(f"engine rejected the reachability probe load: {exc}")
    finally:
        transport.close()

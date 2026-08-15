import math

import networkx as nx
import pytest

from friction import features
from friction.features import FEATURE_NAMES, as_row, compute


def _chain(*ids):
    g = nx.DiGraph()
    for a, b in zip(ids, ids[1:]):
        g.add_edge(a, b)
    return g


def _tangled(root, fanout, depth):
    """A branching tree rooted at `root`: each node gets `fanout` children for
    `depth` levels. Node ids are assigned densely from root+1."""
    g = nx.DiGraph()
    counter = [root + 1]
    frontier = [root]
    g.add_node(root)
    for _ in range(depth):
        nxt = []
        for u in frontier:
            for _ in range(fanout):
                v = counter[0]
                counter[0] += 1
                g.add_edge(u, v)
                nxt.append(v)
        frontier = nxt
    return g


def test_all_named_features_present_and_finite():
    g = _chain(1, 2, 3, 4, 5)
    f = compute(g, fix_ids=[1], test_ids=[5], max_k=6)
    row = as_row(f)
    for name in FEATURE_NAMES:
        assert name in row, f"{name} missing from as_row"
        assert math.isfinite(row[name]), f"{name} is not finite: {row[name]}"
    # context counts live on the dataclass
    assert f.fix_count == 1
    assert f.test_count == 1


def test_as_row_values_are_floats():
    g = _chain(1, 2, 3)
    row = as_row(compute(g, [1], [3], max_k=6))
    assert all(isinstance(v, float) for v in row.values())


def test_tangled_scores_higher_growth_than_chain():
    chain = _chain(1, 2, 3, 4, 5, 6, 7)
    tangled = _tangled(1, fanout=3, depth=6)
    f_chain = compute(chain, fix_ids=[1], test_ids=[7], max_k=6)
    f_tangled = compute(tangled, fix_ids=[1], test_ids=[1], max_k=6)
    assert f_tangled.fwd_growth > f_chain.fwd_growth


def test_growth_is_monotone_in_ball_size():
    # Same source, same k, but the second graph reaches strictly more nodes.
    small = _tangled(1, fanout=2, depth=6)
    big = _tangled(1, fanout=4, depth=6)
    f_small = compute(small, fix_ids=[1], test_ids=[1], max_k=6)
    f_big = compute(big, fix_ids=[1], test_ids=[1], max_k=6)
    assert f_big.fwd_growth > f_small.fwd_growth


def test_growth_never_raises_a_term_to_the_power_zero():
    # A single isolated fix site: ball never grows, growth is well-defined (1.0),
    # not a 0**? or ?**0 blow-up.
    g = nx.DiGraph()
    g.add_node(1)
    g.add_node(2)
    f = compute(g, fix_ids=[1], test_ids=[2], max_k=6)
    assert math.isfinite(f.fwd_growth)
    assert f.fwd_growth == pytest.approx(1.0)


def test_disconnected_endpoints_give_minus_one_hops_and_zero_overlap():
    # Two disjoint components; fix in one, test in the other.
    g = nx.DiGraph()
    g.add_edge(1, 2)      # fix component
    g.add_edge(100, 101)  # test component
    f = compute(g, fix_ids=[1], test_ids=[101], max_k=6)
    assert f.test_to_fix_hops == -1
    assert f.undirected_hops == -1
    assert f.overlap_ratio == 0.0
    # and it did not raise


def test_empty_endpoint_sets_are_handled():
    g = _chain(1, 2, 3)
    f_no_fix = compute(g, fix_ids=[], test_ids=[3], max_k=6)
    assert f_no_fix.fix_count == 0
    assert f_no_fix.fwd_growth == 0.0
    assert f_no_fix.fanin == 0.0
    assert f_no_fix.test_to_fix_hops == -1
    assert f_no_fix.overlap_ratio == 0.0

    f_no_test = compute(g, fix_ids=[1], test_ids=[], max_k=6)
    assert f_no_test.test_count == 0
    assert f_no_test.bwd_growth == 0.0
    assert f_no_test.test_to_fix_hops == -1

    f_none = compute(g, fix_ids=[], test_ids=[], max_k=6)
    assert math.isfinite(f_none.fwd_growth)
    assert f_none.test_to_fix_hops == -1


def test_fanin_counts_in_edges_of_fix_sites():
    # Node 5 has three callers (in-degree 3); node 6 has one.
    g = nx.DiGraph()
    for u in (1, 2, 3):
        g.add_edge(u, 5)
    g.add_edge(4, 6)
    f = compute(g, fix_ids=[5], test_ids=[6], max_k=6)
    assert f.fanin == 3.0
    f2 = compute(g, fix_ids=[5, 6], test_ids=[6], max_k=6)
    assert f2.fanin == 4.0


def test_test_to_fix_minus_one_when_only_undirected_path_exists():
    # Edge points the WRONG way: fix -> test (code calls test). The directed
    # test -> fix relation is therefore unreachable, but the undirected one is 1.
    g = nx.DiGraph()
    g.add_edge(200, 300)  # fix(200) -> test(300)
    f = compute(g, fix_ids=[200], test_ids=[300], max_k=6)
    assert f.test_to_fix_hops == -1
    assert f.undirected_hops >= 1


def test_test_to_fix_at_least_one_when_directed_path_exists():
    # Edge points the RIGHT way: test -> fix (test calls code).
    g = nx.DiGraph()
    g.add_edge(300, 200)  # test(300) -> fix(200)
    f = compute(g, fix_ids=[200], test_ids=[300], max_k=6)
    assert f.test_to_fix_hops == 1
    assert f.undirected_hops == 1


def test_test_to_fix_hops_respects_max_k():
    g = _chain(300, 301, 302, 303, 200)  # test 300 ... fix 200 at distance 4
    near = compute(g, fix_ids=[200], test_ids=[300], max_k=6)
    assert near.test_to_fix_hops == 4
    far = compute(g, fix_ids=[200], test_ids=[300], max_k=3)
    assert far.test_to_fix_hops == -1


def test_overlap_ratio_is_a_fraction_in_unit_interval():
    g = _tangled(1, fanout=2, depth=4)
    # test target inside the same component so balls overlap
    leaves = [n for n in g if g.out_degree(n) == 0]
    f = compute(g, fix_ids=[1], test_ids=[leaves[0]], max_k=6)
    assert 0.0 <= f.overlap_ratio <= 1.0


def test_feature_names_are_the_six_directional_features():
    assert FEATURE_NAMES == (
        "fwd_growth",
        "bwd_growth",
        "overlap_ratio",
        "fanin",
        "test_to_fix_hops",
        "undirected_hops",
    )

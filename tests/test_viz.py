from friction import viz
from friction.paths import PathSet


LOW = PathSet([[1, 2, 3]], [2.0], "c", 1.0, False)
HIGH = PathSet([[1, 2, 3], [1, 4, 3], [1, 5, 6, 3]], [2.0, 2.0, 3.0], "c", 1.0, False)


def test_roles_assigned_to_endpoints_and_intermediates():
    g = viz.build_subgraph(LOW, [1], [3])
    assert g.nodes[1]["role"] == "fix"
    assert g.nodes[3]["role"] == "test"
    assert g.nodes[2]["role"] == "intermediate"


def test_all_intermediate_nodes_are_labelled_intermediate():
    g = viz.build_subgraph(HIGH, [1], [3])
    for node in (2, 4, 5, 6):
        assert g.nodes[node]["role"] == "intermediate"
    assert g.nodes[1]["role"] == "fix"
    assert g.nodes[3]["role"] == "test"


def test_edge_participation_counts_paths_using_that_edge():
    g = viz.build_subgraph(HIGH, [1], [3])
    assert g[2][3]["participation"] == 1
    assert g.number_of_edges() >= 5


def test_edge_participation_accumulates_over_shared_edges():
    # Two paths share the 1->2 edge; participation must count both.
    shared = PathSet([[1, 2, 3], [1, 2, 4, 3]], [2.0, 3.0], "c", 1.0, False)
    g = viz.build_subgraph(shared, [1], [3])
    assert g[1][2]["participation"] == 2
    assert g[2][3]["participation"] == 1


def test_high_friction_subgraph_is_denser_than_low():
    low = viz.build_subgraph(LOW, [1], [3])
    high = viz.build_subgraph(HIGH, [1], [3])
    assert high.number_of_edges() > low.number_of_edges()


def test_denser_path_set_yields_more_edges_and_nodes():
    sparse = viz.build_subgraph(LOW, [1], [3])
    dense = viz.build_subgraph(HIGH, [1], [3])
    assert dense.number_of_nodes() > sparse.number_of_nodes()
    assert dense.number_of_edges() > sparse.number_of_edges()


def test_empty_path_set_yields_empty_graph():
    g = viz.build_subgraph(PathSet([], [], "", 0.0, False), [1], [3])
    assert g.number_of_nodes() == 0
    assert g.number_of_edges() == 0


def test_render_pair_writes_a_png(tmp_path):
    out = viz.render_pair(LOW, HIGH, tmp_path / "pair.png",
                          labels=("friction 0.21 — SAFE", "friction 0.79 — HUMAN"))
    assert out.exists() and out.stat().st_size > 0


def test_render_truncation_writes_a_png(tmp_path):
    engine = PathSet([[1, 2, 3]], [2.0], "c", 1.0, True)
    full = PathSet([[1, 2, 3], [1, 4, 3], [1, 5, 6, 3], [1, 7, 8, 9, 3]],
                   [2.0, 2.0, 3.0, 4.0], "c", 1.0, False)
    out = viz.render_truncation(engine, full, tmp_path / "truncation.png",
                                labels=("engine (pathCount cap)", "full enumeration"),
                                fix_ids=[1], test_ids=[3])
    assert out.exists() and out.stat().st_size > 0


def test_render_pair_writes_a_png_with_empty_low_panel(tmp_path):
    # An instance with no bounded paths must still render (empty panel), not crash.
    empty = PathSet([], [], "", 0.0, False)
    out = viz.render_pair(empty, HIGH, tmp_path / "pair_empty.png",
                          labels=("no paths", "high friction"))
    assert out.exists() and out.stat().st_size > 0

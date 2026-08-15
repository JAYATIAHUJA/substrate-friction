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


# --- two-arm figures -------------------------------------------------------

# A tiny arm-A neighbourhood with a mix of confirmed and unconfirmed edges.
A_EDGES = [
    ("m::f", "m::g", True),
    ("m::f", "m::extend", False),   # the name-match artifact
    ("m::g", "m::h", True),
    ("m::g", "m::lower", False),
]
B_EDGES = [("m::f", "m::g"), ("m::g", "m::h"), ("m::g", "m::k")]
ROLES = {"m::f": "fix", "m::g": "intermediate", "m::h": "intermediate",
         "m::extend": "intermediate", "m::lower": "intermediate", "m::k": "intermediate"}
COUNTS = {"n_a_edges": 4, "n_confirmed": 2, "n_unconfirmed": 2, "n_b_edges": 3}


def test_arm_a_graph_carries_confirmed_flag():
    g = viz.arm_a_graph(A_EDGES)
    assert g.number_of_edges() == 4
    assert g["m::f"]["m::g"]["confirmed"] is True
    assert g["m::f"]["m::extend"]["confirmed"] is False


def test_confirmed_subgraph_is_strictly_smaller_than_full():
    full = viz.arm_a_graph(A_EDGES)
    sub = viz.confirmed_subgraph(full)
    assert sub.number_of_edges() < full.number_of_edges()
    assert sub.number_of_edges() == 2


def test_arm_a_graph_empty_input_yields_empty_graph():
    g = viz.arm_a_graph([])
    assert g.number_of_nodes() == 0
    assert g.number_of_edges() == 0
    # An empty arm-A graph has an empty confirmed subgraph, not an exception.
    assert viz.confirmed_subgraph(g).number_of_edges() == 0


def test_render_arms_writes_a_png(tmp_path):
    out = viz.render_arms(A_EDGES, B_EDGES, ROLES, tmp_path / "arms.png",
                          "demo instance", COUNTS)
    assert out.exists() and out.stat().st_size > 0


def test_render_arms_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_arms([], [], {}, tmp_path / "arms_empty.png", "empty",
                          {"n_a_edges": 0, "n_confirmed": 0, "n_unconfirmed": 0,
                           "n_b_edges": 0})
    assert out.exists() and out.stat().st_size > 0


def test_render_offenders_writes_a_png(tmp_path):
    offenders = [("extend", 139), ("lower", 125), ("cursor", 54), ("search", 31)]
    out = viz.render_offenders(offenders, tmp_path / "offenders.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_offenders_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_offenders([], tmp_path / "offenders_empty.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_density_writes_a_png(tmp_path):
    rows = [
        {"instance": "django__django-1", "a_edges": 19815, "b_edges": 79447,
         "a_answered": True, "b_answered": False},
        {"instance": "django__django-2", "a_edges": 19000, "b_edges": 60000,
         "a_answered": False, "b_answered": False},
        {"instance": "django__django-3", "a_edges": 16000, "b_edges": 24000,
         "a_answered": True, "b_answered": True},
    ]
    out = viz.render_density(rows, tmp_path / "density.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_density_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_density([], tmp_path / "density_empty.png")
    assert out.exists() and out.stat().st_size > 0


def test_parse_offenders_reads_committed_report_verbatim():
    # The figure must show the reported facts, not re-rounded ones: extend(139)
    # tops the committed graph-delta table and cursor(54) is the counter-example.
    from pathlib import Path

    rows = viz._parse_offenders(Path("docs/graph-delta.md"))
    d = dict(rows)
    assert rows[0] == ("extend", 139)
    assert d["lower"] == 125
    assert d["cursor"] == 54


# --- prune.png (the money shot) --------------------------------------------

def test_render_prune_writes_a_png(tmp_path):
    out = viz.render_prune(A_EDGES, ROLES, tmp_path / "prune.png",
                           "demo instance", COUNTS)
    assert out.exists() and out.stat().st_size > 0


def test_render_prune_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_prune([], {}, tmp_path / "prune_empty.png", "empty",
                           {"n_a_edges": 0, "n_confirmed": 0, "n_unconfirmed": 0})
    assert out.exists() and out.stat().st_size > 0


def test_pruned_edge_set_is_strictly_smaller_than_full():
    # The confirmed (pruned) graph the money shot draws on the right must be a
    # strict subset of the full name-matched graph on the left.
    full = viz.arm_a_graph(A_EDGES)
    pruned = viz.confirmed_subgraph(full)
    assert pruned.number_of_edges() < full.number_of_edges()


# --- direction.png ----------------------------------------------------------

def test_render_direction_writes_a_png(tmp_path):
    bars = [("fix→test", 0.0, "backwards"), ("test→fix", 55.0, "natural"),
            ("undirected", 98.0, "broad")]
    out = viz.render_direction(bars, tmp_path / "direction.png", n=44)
    assert out.exists() and out.stat().st_size > 0


def test_render_direction_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_direction([], tmp_path / "direction_empty.png", n=0)
    assert out.exists() and out.stat().st_size > 0


# --- latency.png ------------------------------------------------------------

def test_render_latency_writes_a_png(tmp_path):
    rows = [(1, 4), (2, 2), (3, 4), (4, 3), (5, 7), (6, 12)]
    out = viz.render_latency(rows, 30000, tmp_path / "latency.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_latency_empty_input_still_writes_a_png(tmp_path):
    out = viz.render_latency([], 30000, tmp_path / "latency_empty.png")
    assert out.exists() and out.stat().st_size > 0


def test_generate_latency_reads_committed_json_not_a_hardcoded_list(tmp_path):
    """Finding-C regression guard: the per-k reachability latency MUST come from
    the committed docs/latency.json, never a hardcoded literal. Point viz at a
    temp JSON with sentinel values and assert those exact values flow through —
    a re-hardcoded list would ignore them and fail this test."""
    import json

    from pathlib import Path

    sentinel = {
        "graph": {"nodes": 34000, "both_degree": 2.9},
        "reach_count_star": {
            "mid": {"source_id": 1, "reach6_nodes": 36, "min_millis": 3.3,
                    "max_millis": 7.7,
                    "rows": [{"k": k, "millis": float(k) + 0.5, "size": k}
                             for k in range(1, 7)]},
            "hub": {"source_id": 2, "reach6_nodes": 12710, "min_millis": 30.0,
                    "max_millis": 6505.73, "rows": []},
        },
        "mspaths_enumeration": {
            "mid_connected_seeds": {"millis": 14539.21, "answered": True},
        },
        "timeout_ceiling_millis": 29999,
    }
    jf = tmp_path / "latency.json"
    jf.write_text(json.dumps(sentinel))

    lat = viz.load_latency(Path(jf))
    assert lat["reach_rows"] == [(k, float(k) + 0.5) for k in range(1, 7)]
    assert lat["enum_ms"] == 14539.21
    assert lat["hub_max_ms"] == 6505.73

    # And the shipped docs/latency.json must exist and drive the real figure —
    # the values must NOT be the retracted hardcoded [(1,4),(2,2),(3,4),...] list.
    shipped = viz.load_latency()
    assert shipped["reach_rows"], "docs/latency.json missing or empty"
    assert shipped["reach_rows"] != [(1, 4), (2, 2), (3, 4), (4, 3), (5, 7), (6, 12)]


def test_generate_latency_figure_writes_png_from_committed_json():
    out = viz.generate_latency_figure()
    assert out.exists() and out.stat().st_size > 0


# --- demo.html --------------------------------------------------------------

_DEMO_GRAPH = {
    "instance": "django__django-11490",
    "depth": 2,
    "fix_names": ["get_combinator_sql"],
    "nodes": [
        {"id": "m::get_combinator_sql", "label": "get_combinator_sql", "role": "fix"},
        {"id": "m::extend", "label": "extend", "role": "intermediate"},
        {"id": "m::get_order_by", "label": "get_order_by", "role": "intermediate"},
    ],
    "edges": [
        {"id": "a0", "source": "m::get_combinator_sql", "target": "m::get_order_by",
         "arm": "a", "confirmed": True},
        {"id": "a1", "source": "m::get_combinator_sql", "target": "m::extend",
         "arm": "a", "confirmed": False},
        {"id": "b0", "source": "m::get_combinator_sql", "target": "m::get_order_by",
         "arm": "b", "confirmed": True},
    ],
    "n_a_edges": 2, "n_confirmed": 1, "n_unconfirmed": 1, "n_b_edges": 1,
}


def test_render_demo_html_is_written_and_self_contained(tmp_path):
    out = viz.render_demo_html(_DEMO_GRAPH, tmp_path / "demo.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    # Vendored cytoscape, inlined — never a CDN URL.
    assert "cytoscape" in html.lower()
    assert 'version="3.30.2"' in html  # the real library, not a stub
    for cdn in ("unpkg.com", "cdnjs.cloudflare", "jsdelivr.net"):
        assert cdn not in html
    # No network fetches at all.
    assert "fetch(" not in html


def test_demo_html_embeds_the_inline_graph_json(tmp_path):
    out = viz.render_demo_html(_DEMO_GRAPH, tmp_path / "demo.html")
    html = out.read_text(encoding="utf-8")
    assert "const DATA =" in html
    # The real node identities are embedded, not fetched.
    assert "get_combinator_sql" in html
    assert '"arm":"a"' in html or '"arm": "a"' in html


def test_demo_html_carries_the_ceiling_caveat(tmp_path):
    out = viz.render_demo_html(_DEMO_GRAPH, tmp_path / "demo.html")
    html = out.read_text(encoding="utf-8")
    assert "CEILING" in html
    assert "cursor" in html
    assert "0.746" in html


def test_render_demo_html_without_vendor_still_writes(tmp_path):
    # A partial checkout missing the vendored lib must not crash the generator.
    out = viz.render_demo_html(_DEMO_GRAPH, tmp_path / "demo.html",
                               vendor_js=tmp_path / "absent.js")
    assert out.exists() and out.stat().st_size > 0


def test_build_demo_graph_edges_split_by_arm():
    # Uses the committed shipped/instances arms data via the real join.
    g = viz.build_demo_graph("django__django-11490", 2)
    assert g["n_a_edges"] > 0
    assert g["n_unconfirmed"] > 0
    arms = {e["arm"] for e in g["edges"]}
    assert arms == {"a", "b"}
    # Every node referenced by an edge is present in the node list.
    ids = {n["id"] for n in g["nodes"]}
    for e in g["edges"]:
        assert e["source"] in ids and e["target"] in ids

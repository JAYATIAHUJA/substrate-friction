from pathlib import Path

from friction.namematch import graph as N

FIXTURE = Path(__file__).parent / "fixtures" / "scip_pkg"


def test_name_match_links_a_reference_to_a_same_named_definition():
    edges, _ = N.build(FIXTURE)
    pairs = {(e.src, e.dst) for e in edges}
    assert any(dst.endswith("::lower") for _, dst in pairs)


def test_name_match_reproduces_the_false_edge_it_is_meant_to_model():
    """s.lower() must WRONGLY bind to the module-level lower — that is the point."""
    edges, _ = N.build(FIXTURE)
    wrong = [e for e in edges if e.src.endswith("::shout") and e.dst.endswith("::lower")]
    assert wrong, "arm A must reproduce the name-collision edge, or it is not a fair control"


def test_denylist_suppresses_known_builtins():
    edges, _ = N.build(FIXTURE, stdlib_denylist={"lower"})
    assert not [e for e in edges if e.dst.endswith("::lower")]


def test_stats_report_rule_provenance():
    _, stats = N.build(FIXTURE)
    assert "by_rule" in stats
    assert set(stats["by_rule"]) <= {"module_local", "self_method", "import_alias", "bare_name"}


def test_default_denylist_contains_common_builtins():
    assert {"super", "len", "str", "list"} <= set(N.DEFAULT_DENYLIST)


def test_no_self_edges():
    edges, _ = N.build(FIXTURE)
    assert all(e.src != e.dst for e in edges)

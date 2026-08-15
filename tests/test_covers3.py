"""Fold dynamic COVERS edges into the arm B graph and re-measure connectivity."""
from friction import covers3


def test_disconnected_static_graph_becomes_connected_via_covers():
    # test node 10 reaches nothing statically; fix is node 2.
    static = [(1, 2)]
    merged, _ = covers3.merge_covers(static, [])
    g0 = covers3.graph_from_merged(merged)
    from friction.connectivity import connected_within
    assert connected_within(g0, [10], [2], k=6, undirected=False) is False

    # a COVERS edge from the test (10) into the call graph (1) bridges it.
    merged2, _ = covers3.merge_covers(static, [(10, 1)])
    g1 = covers3.graph_from_merged(merged2)
    assert connected_within(g1, [10], [2], k=6, undirected=False) is True


def test_provenance_is_preserved():
    merged, stats = covers3.merge_covers([(1, 2)], [(10, 1)])
    g = covers3.graph_from_merged(merged)
    assert g[1][2]["source"] == "static"
    assert g[10][1]["source"] == "dynamic"
    assert stats["static"] == 1 and stats["dynamic_added"] == 1


def test_duplicate_edge_is_not_double_counted():
    merged, stats = covers3.merge_covers([(1, 2)], [(1, 2), (1, 2)])
    # the (1,2) edge appears once, tagged static (it was already there).
    assert merged == [(1, 2, "static")]
    assert stats["dynamic_added"] == 0
    assert stats["dynamic_duplicate"] == 2
    assert stats["total"] == 1


def test_covers_identity_matches_module_level_function():
    # a module-level function joins the SCIP identity space exactly.
    prefix = "data.repos.django."
    from friction import identity
    scip = identity.normalize_scip(
        "data.repos.django.django.urls.base::set_script_prefix", prefix)
    cov = covers3.covers_identity("django/urls/base.py::set_script_prefix")
    assert scip == cov == "django.urls.base::set_script_prefix"


def test_covers_identity_loses_class_qualification_for_methods():
    # DELIBERATE, DOCUMENTED LIMITATION: the tracer records co_name (the bare
    # method name) with no class, so a class method cannot rejoin its SCIP
    # class-qualified symbol. This is why the mapping rate is reported honestly.
    from friction import identity
    scip = identity.normalize_scip(
        "data.repos.django.django.core.validators::URLValidator#__call__().",
        "data.repos.django.")
    cov = covers3.covers_identity("django/core/validators.py::__call__")
    assert scip == "django.core.validators.URLValidator::__call__"
    assert cov == "django.core.validators::__call__"
    assert scip != cov


def test_strict_identity_matches_a_qualified_class_method():
    # Once the tracer class-qualifies co_name (Class.method), the SAME strict
    # covers_identity join that a module-level function used now lands a method
    # on its SCIP symbol -- this is the identity fix the RED verdict hinged on.
    from friction import identity
    prefix = "data.repos.django."
    scip = identity.normalize_scip(
        "data.repos.django.django.core.validators::URLValidator#__call__().",
        prefix)
    cov = covers3.covers_identity(
        "django/core/validators.py::URLValidator.__call__")
    assert scip == cov == "django.core.validators.URLValidator::__call__"


def test_lax_join_recovers_a_class_method_the_strict_join_drops(tmp_path):
    # one arm B class method + one module-level function
    nodes = tmp_path / "nodes.ndjson"
    nodes.write_text(
        '{"id": 20000000001, "qual": '
        '"data.repos.django.django.core.validators::URLValidator#__call__()."}\n'
        '{"id": 20000000002, "qual": '
        '"data.repos.django.tests.v.tests::VTests#test_call()."}\n')
    lax = covers3.build_lax_index(nodes)
    mapped, stats = covers3.map_covers_lax(
        [("tests/v/tests.py::test_call", "django/core/validators.py::__call__")],
        lax)
    # the strict join drops both endpoints (class lost); the lax join recovers them
    assert stats["covers_edges_mapped"] == 1
    assert mapped == [(20000000002, 20000000001)]

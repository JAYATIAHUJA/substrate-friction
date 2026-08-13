from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve, resolve_with_stats, _build_enclosing_index

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def _table_and_edges():
    table = parse_repo(FIXTURE, repo_code=1)
    return table, resolve(FIXTURE, table)


def test_direct_call_edge_exists():
    table, edges = _table_and_edges()
    q = {f.qualname: f.id for f in table.functions}
    calls = {(e.src, e.dst) for e in edges if e.type == "CALLS"}
    assert (q["mod_a.Widget.render"], q["mod_a.helper"]) in calls


def test_self_method_call_resolves_within_class():
    table, edges = _table_and_edges()
    q = {f.qualname: f.id for f in table.functions}
    calls = {(e.src, e.dst) for e in edges if e.type == "CALLS"}
    assert (q["mod_a.Widget.draw"], q["mod_a.Widget.render"]) in calls


def test_has_method_edges_link_class_to_methods():
    table, edges = _table_and_edges()
    cls = {c.qualname: c.id for c in table.classes}
    fn = {f.qualname: f.id for f in table.functions}
    hm = {(e.src, e.dst) for e in edges if e.type == "HAS_METHOD"}
    assert (cls["mod_a.Widget"], fn["mod_a.Widget.render"]) in hm


def test_inherits_edge_between_classes():
    table, edges = _table_and_edges()
    cls = {c.qualname: c.id for c in table.classes}
    inh = {(e.src, e.dst) for e in edges if e.type == "INHERITS"}
    assert (cls["mod_b.FancyWidget"], cls["mod_a.Widget"]) in inh


def test_defined_in_edges_link_functions_to_files():
    table, edges = _table_and_edges()
    file_ids = {f.id for f in table.files}
    di = [e for e in edges if e.type == "DEFINED_IN"]
    assert di and all(e.dst in file_ids for e in di)


def test_imports_edge_between_files():
    table, edges = _table_and_edges()
    files = {f.path: f.id for f in table.files}
    imp = {(e.src, e.dst) for e in edges if e.type == "IMPORTS"}
    assert (files["mod_b.py"], files["mod_a.py"]) in imp


def test_no_self_loops_and_no_duplicate_edges():
    _, edges = _table_and_edges()
    assert all(e.src != e.dst for e in edges)
    keys = [(e.src, e.dst, e.type) for e in edges]
    assert len(keys) == len(set(keys))


def test_stats_report_resolution_rate():
    table = parse_repo(FIXTURE, repo_code=1)
    _, stats = resolve_with_stats(FIXTURE, table)
    assert stats.call_sites > 0
    assert 0.0 <= stats.resolution_rate <= 1.0


def test_enclosing_index_picks_inner_nested_function(tmp_path):
    src = (
        "def outer(x):\n"          # line 1
        "    def inner(y):\n"      # line 2
        "        return y\n"       # line 3
        "    return inner(x)\n"    # line 4
    )
    (tmp_path / "nest.py").write_text(src)
    table = parse_repo(tmp_path, repo_code=1)

    by_qual = {f.qualname: f.id for f in table.functions}
    outer_id = by_qual["nest.outer"]
    inner_id = by_qual["nest.inner"]

    file_id = next(f.id for f in table.files if f.path == "nest.py")
    index = _build_enclosing_index(table)

    # A line inside the inner def is enclosed by BOTH functions; the
    # smallest-span (innermost) one must win.
    assert index.find(file_id, 3) == inner_id
    # A line only inside the outer def resolves to the outer function.
    assert index.find(file_id, 1) == outer_id
    assert index.find(file_id, 4) == outer_id
    # A file with no functions / a line outside any span -> None.
    assert index.find(file_id, 999) is None
    assert index.find(-1, 3) is None

from pathlib import Path
from friction.parsing.symbols import parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_extracts_files_classes_and_functions():
    table = parse_repo(FIXTURE, repo_code=1)
    paths = {f.path for f in table.files}
    assert {"mod_a.py", "mod_b.py", "test_mod_a.py"} <= paths
    assert {c.name for c in table.classes} == {"Widget", "FancyWidget"}
    names = {f.name for f in table.functions}
    assert {"helper", "render", "draw", "build", "test_render_positive"} <= names


def test_qualnames_disambiguate_same_named_methods():
    table = parse_repo(FIXTURE, repo_code=1)
    quals = {f.qualname for f in table.functions}
    assert "mod_a.Widget.render" in quals
    assert "mod_b.FancyWidget.render" in quals


def test_ids_are_unique_positive_integers():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = [s.id for s in table.files + table.classes + table.functions]
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, int) and i >= 0 for i in ids)


def test_test_functions_flagged():
    table = parse_repo(FIXTURE, repo_code=1)
    by_name = {f.name: f for f in table.functions}
    assert by_name["test_render_positive"].is_test is True
    assert by_name["helper"].is_test is False


def test_cyclomatic_counts_decision_points():
    table = parse_repo(FIXTURE, repo_code=1)
    by_qual = {f.qualname: f for f in table.functions}
    assert by_qual["mod_a.helper"].cyclomatic == 2       # base 1 + one if
    assert by_qual["mod_a.Widget.draw"].cyclomatic == 3  # base 1 + for + if


def test_line_ranges_are_sane():
    table = parse_repo(FIXTURE, repo_code=1)
    for f in table.functions:
        assert f.line_start >= 1
        assert f.line_end >= f.line_start


def test_class_bases_recorded():
    table = parse_repo(FIXTURE, repo_code=1)
    fancy = next(c for c in table.classes if c.name == "FancyWidget")
    assert "Widget" in fancy.bases

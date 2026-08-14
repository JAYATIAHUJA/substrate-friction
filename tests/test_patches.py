from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing import patches

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"

PATCH = """diff --git a/mod_a.py b/mod_a.py
--- a/mod_a.py
+++ b/mod_a.py
@@ -1,4 +1,5 @@
 def helper(x):
     if x > 0:
         return x
+    # changed
     return -x
"""


def test_changed_ranges_extracts_post_image_lines():
    ranges = patches.changed_ranges(PATCH)
    assert "mod_a.py" in ranges
    assert ranges["mod_a.py"]


def test_fix_site_ids_maps_to_enclosing_function():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.fix_site_ids(PATCH, table)
    q = {f.qualname: f.id for f in table.functions}
    assert q["mod_a.helper"] in ids


def test_fix_site_ids_returns_empty_for_unknown_file():
    table = parse_repo(FIXTURE, repo_code=1)
    other = PATCH.replace("mod_a.py", "not_here.py")
    assert patches.fix_site_ids(other, table) == []


def test_test_target_ids_matches_pytest_node_ids():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.test_target_ids(
        ["test_mod_a.py::test_render_positive"], table
    )
    q = {f.qualname: f.id for f in table.functions}
    assert ids == [q["test_mod_a.test_render_positive"]]


def test_test_target_ids_matches_bare_function_names():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.test_target_ids(["test_render_positive"], table)
    assert len(ids) == 1


# --- parse_test_identifier -------------------------------------------------

def test_parse_test_identifier_pytest_node_id():
    assert patches.parse_test_identifier(
        "test_mod_a.py::test_render_positive"
    ) == (None, "test_render_positive")


def test_parse_test_identifier_pytest_with_class():
    assert patches.parse_test_identifier(
        "tests/test_x.py::MyTests::test_it"
    ) == ("MyTests", "test_it")


def test_parse_test_identifier_pytest_parametrised():
    assert patches.parse_test_identifier(
        "test_x.py::test_it[case-1]"
    ) == (None, "test_it")


def test_parse_test_identifier_django_format():
    assert patches.parse_test_identifier(
        "test_render_positive (sample_pkg.test_mod_a.SomeTests)"
    ) == ("sample_pkg.test_mod_a.SomeTests", "test_render_positive")


def test_parse_test_identifier_django_method_repeated_in_parens():
    # Newer Django/unittest repeats the method inside the parens.
    assert patches.parse_test_identifier(
        "test_it (a.b.C.test_it)"
    ) == ("a.b.C", "test_it")


def test_parse_test_identifier_bare_name():
    assert patches.parse_test_identifier(
        "test_render_positive"
    ) == (None, "test_render_positive")


# --- test_target_ids: django + suffix + ambiguity --------------------------

def test_test_target_ids_resolves_django_format():
    table = parse_repo(FIXTURE, repo_code=1)
    q = {f.qualname: f.id for f in table.functions}
    ids = patches.test_target_ids(["render (mod_a.Widget)"], table)
    assert ids == [q["mod_a.Widget.render"]]


def test_test_target_ids_suffix_matches_across_path_prefix():
    table = parse_repo(FIXTURE, repo_code=1)
    q = {f.qualname: f.id for f in table.functions}
    # The django dotted name 'Widget' omits the 'mod_a' module prefix that
    # parse_repo bakes into the qualname; suffix matching on dot boundaries
    # must still land on Widget.render and NOT on FancyWidget.render.
    ids = patches.test_target_ids(["render (Widget)"], table)
    assert ids == [q["mod_a.Widget.render"]]


def test_test_target_ids_ambiguous_bare_name_returns_nothing():
    table = parse_repo(FIXTURE, repo_code=1)
    # 'render' is defined on both Widget (mod_a) and FancyWidget (mod_b);
    # a wrong test target is worse than a missing one, so return nothing.
    assert patches.test_target_ids(["render"], table) == []


def test_test_target_ids_strips_parametrised_bracket():
    table = parse_repo(FIXTURE, repo_code=1)
    q = {f.qualname: f.id for f in table.functions}
    ids = patches.test_target_ids(
        ["test_mod_a.py::test_render_positive[x-1]"], table
    )
    assert ids == [q["test_mod_a.test_render_positive"]]

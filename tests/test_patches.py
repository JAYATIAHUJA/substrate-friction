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

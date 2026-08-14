"""Unit tests for the pure parts of friction.annotate.

The git-checkout / parse orchestration (build_annotations) needs a real clone
and is not exercised here; the helpers below are covered against the shared
sample_pkg fixture and synthetic instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from friction.annotate import (
    annotate_instance,
    patch_line_count,
    repo_loc,
    sanity_report,
)
from friction.parsing.symbols import parse_repo

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


@dataclass
class FakeInstance:
    instance_id: str
    repo: str = "django/django"
    base_commit: str = "deadbeef"
    patch: str = ""
    fail_to_pass: list = field(default_factory=list)


# --- patch_line_count -----------------------------------------------------

def test_patch_line_count_counts_added_and_removed():
    patch = (
        "diff --git a/f.py b/f.py\n"
        "--- a/f.py\n+++ b/f.py\n"
        "@@ -1,2 +1,3 @@\n"
        " context\n-old\n+new1\n+new2\n"
    )
    # one removed (-old) + two added (+new1,+new2); headers excluded
    assert patch_line_count(patch) == 3


def test_patch_line_count_ignores_file_headers():
    # +++ and --- headers must not be miscounted as +/- content lines
    assert patch_line_count(PATCH) == 1  # only the single '+    # changed'


def test_patch_line_count_empty():
    assert patch_line_count("") == 0


# --- repo_loc -------------------------------------------------------------

def test_repo_loc_sums_file_loc():
    table = parse_repo(FIXTURE, repo_code=1)
    assert repo_loc(table) == sum(f.loc for f in table.files)
    assert repo_loc(table) > 0


# --- annotate_instance ----------------------------------------------------

def test_annotate_instance_offsets_fix_sites_into_band():
    table = parse_repo(FIXTURE, repo_code=1)
    inst = FakeInstance("x__1", patch=PATCH, fail_to_pass=[])
    resolved_by = {"sysA": {"x__1"}, "sysB": set()}
    base = 100_000_000
    rec = annotate_instance(inst, table, base, "g_deadbeef", resolved_by)

    q = {f.qualname: f.id for f in table.functions}
    assert rec["fix_site_ids"] == [q["mod_a.helper"] + base]
    assert rec["graph"] == "g_deadbeef"
    assert rec["repo"] == "django/django"
    assert rec["repo_loc"] == repo_loc(table)
    assert rec["patch_lines"] == 1


def test_annotate_instance_failed_label_is_not_in_resolved():
    table = parse_repo(FIXTURE, repo_code=1)
    inst = FakeInstance("x__1", patch=PATCH)
    resolved_by = {"solved": {"x__1"}, "unsolved": {"other"}}
    rec = annotate_instance(inst, table, 0, "g", resolved_by)
    # resolved by 'solved' -> not failed; absent from 'unsolved' -> failed
    assert rec["failed"] == {"solved": False, "unsolved": True}


def test_annotate_instance_test_targets_resolve_pytest_nodeid():
    table = parse_repo(FIXTURE, repo_code=1)
    inst = FakeInstance("x__1", patch="",
                        fail_to_pass=["test_mod_a.py::test_render_positive"])
    rec = annotate_instance(inst, table, 5, "g", {})
    q = {f.qualname: f.id for f in table.functions}
    assert rec["test_target_ids"] == [q["test_mod_a.test_render_positive"] + 5]


# --- sanity_report --------------------------------------------------------

def test_sanity_report_both_above_threshold_is_sane():
    ann = {
        f"i{k}": {"fix_site_ids": [1], "test_target_ids": [2]}
        for k in range(8)
    }
    ann["i8"] = {"fix_site_ids": [], "test_target_ids": []}
    ann["i9"] = {"fix_site_ids": [], "test_target_ids": []}
    rep = sanity_report(ann)
    assert rep["pct_nonempty_fix_sites"] == 80.0
    assert rep["pct_nonempty_test_targets"] == 80.0
    assert rep["mapping_sane"] is True


def test_sanity_report_one_below_threshold_not_sane():
    ann = {
        f"i{k}": {"fix_site_ids": [1], "test_target_ids": []}
        for k in range(10)
    }
    rep = sanity_report(ann)
    assert rep["pct_nonempty_fix_sites"] == 100.0
    assert rep["pct_nonempty_test_targets"] == 0.0
    assert rep["mapping_sane"] is False


def test_sanity_report_empty_is_not_sane():
    rep = sanity_report({})
    assert rep["mapping_sane"] is False
    assert rep["n_instances"] == 0

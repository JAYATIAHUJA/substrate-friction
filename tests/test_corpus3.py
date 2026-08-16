"""Unit tests for the pure logic in scripts/build_corpus3.py.

Covers the three pieces the plan flags as needing tests: repo selection,
manifest resume, and per-repo aggregation -- plus the deterministic build
ordering. No clone, no SWE-bench download, no engine required.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_corpus3 as bc  # noqa: E402


@dataclass
class FakeInstance:
    instance_id: str
    repo: str = "x/x"
    fail_to_pass: list = field(default_factory=list)


def test_repo_short_strips_org():
    assert bc.repo_short("sphinx-doc/sphinx") == "sphinx"
    assert bc.repo_short("django/django") == "django"
    assert bc.repo_short("scikit-learn/scikit-learn") == "scikit-learn"


def test_select_target_repos_picks_k_largest_excluding_django():
    counts = {
        "django/django": 231, "sympy/sympy": 75, "sphinx-doc/sphinx": 44,
        "matplotlib/matplotlib": 34, "scikit-learn/scikit-learn": 32,
    }
    got = bc.select_target_repos(counts, exclude={"django"}, k=3)
    assert got == ["sympy", "sphinx", "matplotlib"]


def test_select_target_repos_breaks_ties_by_name():
    counts = {"aaa/aaa": 10, "bbb/bbb": 10, "ccc/ccc": 5}
    assert bc.select_target_repos(counts, exclude=set(), k=2) == ["aaa", "bbb"]


def test_completed_ids_reads_manifest_and_ignores_torn_line(tmp_path):
    m = tmp_path / "manifest.jsonl"
    m.write_text(
        json.dumps({"instance_id": "a"}) + "\n"
        + json.dumps({"instance_id": "b"}) + "\n"
        + '{"instance_id": "c", "arm_b": {trunc'  # torn crash line
    )
    assert bc.completed_ids(m) == {"a", "b"}


def test_completed_ids_absent_file_is_empty(tmp_path):
    assert bc.completed_ids(tmp_path / "nope.jsonl") == set()


def test_plan_prefers_parseable_fail_to_pass_then_id_order():
    insts = [
        FakeInstance("z-unparseable", fail_to_pass=[]),
        FakeInstance("m-parseable", fail_to_pass=["t/x.py::C::test_a"]),
        FakeInstance("a-parseable", fail_to_pass=["t/x.py::C::test_b"]),
    ]
    ordered = [i.instance_id for i in bc.plan_repo_instances(insts, limit=None)]
    # both parseable come first, alphabetised; unparseable last.
    assert ordered == ["a-parseable", "m-parseable", "z-unparseable"]


def test_plan_respects_limit():
    insts = [FakeInstance(f"i{n}", fail_to_pass=["t.py::C::test"]) for n in range(5)]
    assert len(bc.plan_repo_instances(insts, limit=2)) == 2


def test_usable_requires_both_endpoints():
    both = {"arm_b": {"fix_site_ids": [1], "test_target_ids": [2]}}
    fix_only = {"arm_b": {"fix_site_ids": [1], "test_target_ids": []}}
    neither = {"arm_b": {"fix_site_ids": [], "test_target_ids": []}}
    assert bc._usable(both) is True
    assert bc._usable(fix_only) is False
    assert bc._usable(neither) is False


def test_aggregate_by_repo_counts_and_medians():
    records = [
        {"repo": "sympy", "seconds": 100.0, "comparable": True,
         "arm_a": {"fix_site_ids": [1], "test_target_ids": [2]},
         "arm_b": {"nodes": 100, "edges": 300,
                   "fix_site_ids": [1], "test_target_ids": [2]}},
        {"repo": "sympy", "seconds": 50.0, "comparable": False,
         "arm_a": {"fix_site_ids": [], "test_target_ids": []},
         "arm_b": {"nodes": 200, "edges": 500,
                   "fix_site_ids": [1], "test_target_ids": []}},  # fix only
        {"repo": "matplotlib", "seconds": 20.0, "comparable": False,
         "arm_a": {"fix_site_ids": [], "test_target_ids": []},
         "arm_b": {"nodes": 10, "edges": 20,
                   "fix_site_ids": [], "test_target_ids": []}},
    ]
    agg = bc.aggregate_by_repo(records)
    assert agg["sympy"]["built"] == 2
    assert agg["sympy"]["usable_arm_b"] == 1   # only the first has both endpoints
    assert agg["sympy"]["usable_arm_a"] == 1
    assert agg["sympy"]["comparable"] == 1
    assert agg["sympy"]["median_nodes_arm_b"] == 150   # median(100,200)
    assert agg["sympy"]["median_edges_arm_b"] == 400   # median(300,500)
    assert agg["sympy"]["wall_seconds"] == 150.0
    assert agg["matplotlib"]["built"] == 1
    assert agg["matplotlib"]["usable_arm_b"] == 0


def test_aggregate_empty_is_empty():
    assert bc.aggregate_by_repo([]) == {}

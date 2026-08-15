import json

import pytest

from friction import arms
from friction.scip.extract import CallEdge, Def
from friction.parsing.symbols import FileSym, FunctionSym, SymbolTable


# --- bands ----------------------------------------------------------------

def test_bands_are_disjoint_between_arms():
    b = arms.bands_for(0)
    assert b.arm_b - b.arm_a >= 10_000_000_000


def test_bands_are_disjoint_between_instances():
    a, b = arms.bands_for(0), arms.bands_for(1)
    assert b.arm_a - a.arm_a == 10_000_000
    assert b.arm_b - a.arm_b == 10_000_000


def test_bands_clear_every_band_used_by_v1():
    # v1 occupied 1e8..5.9e8, 2.0e9..2.49e9, 3.0e9..3.49e9, 4.0e9..4.49e9,
    # and sweeps at 5e9/6e9/7.1e9/8e9/9e9/9.5e9.
    assert arms.bands_for(0).arm_a >= 10_000_000_000


# --- emit_arm -------------------------------------------------------------

def test_emit_assigns_contiguous_ids_within_a_band(tmp_path):
    edges = [CallEdge("m::f().", "m::g().", False, 2),
             CallEdge("m::g().", "m::h().", False, 1)]
    stats = arms.emit_arm(edges, band=10_000_000_000, out_dir=tmp_path)
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    ids = [int(l.split('"id": ')[1].split(",")[0])
           for l in (tmp_path / "nodes.ndjson").read_text().splitlines()]
    assert all(10_000_000_000 <= i < 10_010_000_000 for i in ids)


def test_emit_writes_sid_as_a_string(tmp_path):
    arms.emit_arm([CallEdge("m::f().", "m::g().", False, 1)], 10_000_000_000, tmp_path)
    row = json.loads((tmp_path / "nodes.ndjson").read_text().splitlines()[0])
    assert isinstance(row["sid"], str)


def test_emit_is_deterministic(tmp_path):
    e = [CallEdge("m::b().", "m::a().", False, 1), CallEdge("m::a().", "m::c().", False, 1)]
    s1 = arms.emit_arm(e, 10_000_000_000, tmp_path / "one")
    s2 = arms.emit_arm(e, 10_000_000_000, tmp_path / "two")
    assert (tmp_path / "one" / "nodes.ndjson").read_text() == \
           (tmp_path / "two" / "nodes.ndjson").read_text()
    assert s1 == s2


def test_emit_exposes_qual_to_id_matching_the_written_ids(tmp_path):
    e = [CallEdge("m::f().", "m::g().", False, 1)]
    stats = arms.emit_arm(e, 10_000_000_000, tmp_path)
    id_by_qual = stats["id_by_qual"]
    rows = [json.loads(l) for l in (tmp_path / "nodes.ndjson").read_text().splitlines()]
    for r in rows:
        assert id_by_qual[r["qual"]] == r["id"]


# --- endpoint mapping: arm A ----------------------------------------------

def _table_with_target():
    """A one-file table whose only function spans lines 10..20."""
    table = SymbolTable()
    table.files.append(FileSym(id=0, path="pkg/mod.py", repo=0, loc=50))
    table.functions.append(FunctionSym(
        id=1, name="target", qualname="pkg.mod.target", file_id=0,
        line_start=10, line_end=20, cyclomatic=1, is_test=False, class_id=None))
    return table


_PATCH_HITS_TARGET = (
    "diff --git a/pkg/mod.py b/pkg/mod.py\n"
    "--- a/pkg/mod.py\n"
    "+++ b/pkg/mod.py\n"
    "@@ -14,2 +14,3 @@\n"
    " context_line\n"
    "+added_line\n"
    " another_context\n"
)


def test_arm_a_maps_a_fix_site_that_lands_in_a_known_def():
    table = _table_with_target()
    # arm A emits `module::name` identities, so the node qual is pkg.mod::target.
    id_by_qual = {"pkg.mod::target": 10_000_000_005}
    out = arms.map_arm_a_endpoints(table, _PATCH_HITS_TARGET, [], id_by_qual)
    assert out["fix_site_ids"] == [10_000_000_005]
    assert out["unmapped_fix_sites"] == 0


def test_arm_a_counts_a_fix_site_absent_from_the_edge_graph():
    table = _table_with_target()
    out = arms.map_arm_a_endpoints(table, _PATCH_HITS_TARGET, [], {})
    assert out["fix_site_ids"] == []
    assert out["unmapped_fix_sites"] == 1


_PATCH_MODULE_LEVEL = (
    "diff --git a/pkg/mod.py b/pkg/mod.py\n"
    "--- a/pkg/mod.py\n"
    "+++ b/pkg/mod.py\n"
    "@@ -40,1 +40,2 @@\n"
    " context_line\n"
    "+added_line\n"
)


def test_arm_a_counts_a_fix_hunk_outside_every_def():
    # Finding 1: a hunk landing outside every def (module-level change) must be
    # COUNTED, not reported as unmapped_fix_sites=0. Only def spans 10..20.
    table = _table_with_target()
    out = arms.map_arm_a_endpoints(table, _PATCH_MODULE_LEVEL, [],
                                   {"pkg.mod::target": 10_000_000_005})
    assert out["fix_site_ids"] == []
    assert out["unmapped_fix_sites"] == 1


def test_arm_a_counts_a_test_target_that_resolves_to_no_function():
    # Finding 1: a FAIL_TO_PASS entry naming a test with no physical def must be
    # counted. The only function is pkg.mod.target (not a test).
    table = _table_with_target()
    out = arms.map_arm_a_endpoints(table, "", ["test_nope (pkg.mod.Missing)"],
                                   {"pkg.mod::target": 10_000_000_005})
    assert out["test_target_ids"] == []
    assert out["unmapped_test_targets"] == 1


# --- endpoint mapping: arm B ----------------------------------------------

def _def(symbol, path, start, end, canonical, kind="function"):
    return Def(symbol=symbol, path=path, start=start, end=end,
               canonical=canonical, kind=kind)


def test_arm_b_fix_site_uses_innermost_containment():
    # method spans 0-based lines 9..19 inside a class spanning 5..25.
    method = _def("scip-python python p 1 `pkg.mod`/C#target().",
                  "pkg/mod.py", 9, 19, "pkg.mod::C#target().")
    klass = _def("scip-python python p 1 `pkg.mod`/C#",
                 "pkg/mod.py", 5, 25, "pkg.mod::C#", kind="class")
    canons = arms.fix_site_canonicals([klass, method], _PATCH_HITS_TARGET)
    # changed line is 1-based 15 -> 0-based 14, inside the method, not just the class
    assert canons == ["pkg.mod::C#target()."]


def test_arm_b_maps_fix_site_canonical_to_a_band_id():
    method = _def("scip-python python p 1 `pkg.mod`/C#target().",
                  "pkg/mod.py", 9, 19, "pkg.mod::C#target().")
    out = arms.map_arm_b_endpoints([method], _PATCH_HITS_TARGET, [],
                                   {"pkg.mod::C#target().": 20_000_000_003})
    assert out["fix_site_ids"] == [20_000_000_003]
    assert out["unmapped_fix_sites"] == 0


def test_arm_b_test_target_matches_class_and_method():
    tdef = _def("scip-python python p 1 `tests.foo`/MyTest#test_it().",
                "tests/foo.py", 3, 8, "tests.foo::MyTest#test_it().")
    canons = arms.test_target_canonicals([tdef], ["test_it (tests.foo.MyTest)"])
    assert canons == ["tests.foo::MyTest#test_it()."]


def test_arm_b_test_target_rejects_a_same_named_method_in_another_class():
    right = _def("scip-python python p 1 `tests.foo`/MyTest#test_it().",
                 "tests/foo.py", 3, 8, "tests.foo::MyTest#test_it().")
    wrong = _def("scip-python python p 1 `tests.foo`/OtherTest#test_it().",
                 "tests/foo.py", 20, 25, "tests.foo::OtherTest#test_it().")
    canons = arms.test_target_canonicals([right, wrong],
                                         ["test_it (tests.foo.MyTest)"])
    assert canons == ["tests.foo::MyTest#test_it()."]


def test_arm_b_counts_unmapped_test_targets():
    tdef = _def("scip-python python p 1 `tests.foo`/MyTest#test_it().",
                "tests/foo.py", 3, 8, "tests.foo::MyTest#test_it().")
    out = arms.map_arm_b_endpoints([tdef], "", ["test_it (tests.foo.MyTest)"], {})
    assert out["test_target_ids"] == []
    assert out["unmapped_test_targets"] == 1


def test_arm_b_counts_a_test_target_that_yields_no_canonical():
    # Finding 1: an inherited test method. FAIL_TO_PASS names SubTest, but only
    # the parent BaseTest has a physical def, so the exact class-leaf match finds
    # NO canonical. Previously this returned unmapped_test_targets=0 (invisible);
    # it must now be counted even though the parent def IS a known node.
    tdef = _def("scip-python python p 1 `tests.foo`/BaseTest#test_it().",
                "tests/foo.py", 3, 8, "tests.foo::BaseTest#test_it().")
    out = arms.map_arm_b_endpoints(
        [tdef], "", ["test_it (tests.foo.SubTest)"],
        {"tests.foo::BaseTest#test_it().": 20_000_000_003})
    assert out["test_target_ids"] == []
    assert out["unmapped_test_targets"] == 1


def test_arm_b_counts_a_fix_hunk_outside_every_def():
    # Finding 1: the patch changes 0-based line 14, but the only def spans 30..40,
    # so no canonical is produced. Must be counted, not reported as 0.
    other = _def("scip-python python p 1 `pkg.mod`/C#other().",
                 "pkg/mod.py", 30, 40, "pkg.mod::C#other().")
    out = arms.map_arm_b_endpoints([other], _PATCH_HITS_TARGET, [],
                                   {"pkg.mod::C#other().": 20_000_000_003})
    assert out["fix_site_ids"] == []
    assert out["unmapped_fix_sites"] == 1


# --- cross-arm comparability (Finding 2) ----------------------------------

def test_endpoints_comparable_requires_both_arms_mapped():
    both = {"fix_site_ids": [1], "test_target_ids": [2]}
    assert arms.endpoints_comparable(both, both) is True


def test_endpoints_not_comparable_when_one_arm_has_no_test_targets():
    # The inherited-test asymmetry: arm A resolved a (wrong-class) test target,
    # arm B resolved none. The instance must be flagged non-comparable so Task 8
    # excludes it from the path-structure delta rather than comparing 1 vs 0.
    arm_a = {"fix_site_ids": [1], "test_target_ids": [2]}
    arm_b = {"fix_site_ids": [9], "test_target_ids": []}
    assert arms.endpoints_comparable(arm_a, arm_b) is False


def test_endpoints_not_comparable_when_fix_sites_missing_in_an_arm():
    arm_a = {"fix_site_ids": [], "test_target_ids": [2]}
    arm_b = {"fix_site_ids": [9], "test_target_ids": [8]}
    assert arms.endpoints_comparable(arm_a, arm_b) is False

"""Tests for the gate: selection, recall audit, verdict, arm comparison."""

import json

import networkx as nx
import pytest

from friction.gate import (
    ArmComparison,
    RecallAudit,
    SAFE_SKIP_RECALL,
    SelectionResult,
    audit_recall,
    build_selection_cypher,
    compare_arms,
    gate,
    select_tests,
    split_of,
)


def _chain() -> nx.DiGraph:
    """test(1) -> helper(2) -> fix(3);  unrelated test(4) -> other(5)."""
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 3)
    g.add_edge(4, 5)
    return g


# ── selection ────────────────────────────────────────────────────────────


def test_selects_a_test_two_hops_upstream_of_the_change():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=6)
    assert result.selected == frozenset({1})


def test_does_not_select_a_test_beyond_the_bound():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=1)
    assert result.selected == frozenset()


def test_walks_predecessors_not_successors():
    # From the test end, the fix is NOT upstream: nothing should be selected.
    result = select_tests(_chain(), changed_ids=[1], candidate_test_ids=[3], k=6)
    assert result.selected == frozenset()


def test_graph_complete_is_true_when_the_walk_exhausts_before_the_bound():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=6)
    assert result.graph_complete is True


def test_graph_complete_is_false_when_the_bound_cuts_the_walk():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=1)
    assert result.graph_complete is False


def test_a_changed_node_that_is_itself_a_test_is_selected():
    result = select_tests(_chain(), changed_ids=[1], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset({1})


def test_a_changed_node_absent_from_the_graph_selects_nothing():
    result = select_tests(_chain(), changed_ids=[999], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset()


def test_empty_change_set_selects_nothing_and_is_not_graph_complete():
    result = select_tests(_chain(), changed_ids=[], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset()
    assert result.graph_complete is False


def test_a_cycle_terminates():
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 1)
    g.add_edge(2, 3)
    result = select_tests(g, changed_ids=[3], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset({1})


def test_bound_must_be_a_positive_integer():
    with pytest.raises(ValueError):
        select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1], k=0)
    with pytest.raises(ValueError):
        select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1], k=True)


# ── audit ────────────────────────────────────────────────────────────────


def _write_instance(root, instance_id, edges, arm="arm_b"):
    d = root / instance_id / arm
    d.mkdir(parents=True, exist_ok=True)
    with (d / "edges.ndjson").open("w", encoding="utf-8") as fh:
        for src, dst in edges:
            fh.write(json.dumps({"src": src, "dst": dst}) + "\n")


def _manifest(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_audit_counts_a_reachable_guarding_test_as_a_hit(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 2), (2, 3)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-1",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 1 and audit.hits == 1
    assert audit.recall == 1.0
    assert audit.misses == ()


def test_audit_counts_an_unreachable_guarding_test_as_a_miss(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-2", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-2",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 1 and audit.hits == 0
    assert audit.misses == ("django__django-2",)


def test_audit_skips_instances_with_an_empty_endpoint_set(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-3", [(1, 2)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-3",
                    "arm_b": {"fix_site_ids": [], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 0
    assert audit.recall == 0.0


def test_audit_skips_an_instance_whose_graph_file_is_absent(tmp_path):
    arms = tmp_path / "arms"
    arms.mkdir()
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-4",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    assert audit_recall(mf, arms, arm="arm_b", k=6).n == 0


def test_audit_groups_by_repo_prefix(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-5", [(1, 3)])
    _write_instance(arms, "sympy__sympy-6", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-5",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "sympy__sympy-6",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.per_repo["django"] == (1, 1)
    assert audit.per_repo["sympy"] == (0, 1)
    assert audit.n == 2 and audit.hits == 1


# ── verdict ──────────────────────────────────────────────────────────────


def _audit(hits, n, arm="arm_b", k=6):
    return RecallAudit(arm=arm, k=k, n=n, hits=hits, misses=(), per_repo={})


def test_recall_below_the_bar_forces_a_full_run():
    verdict = gate(_audit(hits=24, n=44))
    assert verdict.decision == "RUN_FULL"
    assert "0.545" in verdict.reason
    assert "45%" in verdict.reason


def test_recall_at_or_above_the_bar_permits_a_skip():
    assert gate(_audit(hits=96, n=100)).decision == "SKIP_SAFE"
    assert gate(_audit(hits=95, n=100)).decision == "SKIP_SAFE"


def test_an_unmeasured_graph_never_permits_a_skip():
    verdict = gate(_audit(hits=0, n=0))
    assert verdict.decision == "RUN_FULL"
    assert "unmeasured" in verdict.reason


def test_the_default_bar_is_stated_and_strict():
    assert SAFE_SKIP_RECALL == 0.95


def test_the_verdict_carries_its_provenance():
    verdict = gate(_audit(hits=24, n=44, arm="arm_a", k=6))
    assert verdict.arm == "arm_a"
    assert verdict.k == 6
    assert verdict.n == 44


# ── paired arm comparison ────────────────────────────────────────────────


def test_paired_comparison_uses_only_instances_measurable_on_both_arms(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    _write_instance(arms, "django__django-2", [(1, 3)], arm="arm_b")

    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-1",
         "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "django__django-2",
         "arm_a": {"fix_site_ids": [], "test_target_ids": []},
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])

    cmp_ = compare_arms(mf, arms, k=6)
    assert cmp_.n_paired == 1
    assert cmp_.both_hit == 1


def test_paired_comparison_classifies_the_four_cells(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(9, 8)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    _write_instance(arms, "django__django-2", [(9, 8)], arm="arm_a")
    _write_instance(arms, "django__django-2", [(9, 8)], arm="arm_b")

    mf = tmp_path / "manifest.jsonl"
    rows = [{"instance_id": i,
             "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
             "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}
            for i in ("django__django-1", "django__django-2")]
    _manifest(mf, rows)

    cmp_ = compare_arms(mf, arms, k=6)
    assert cmp_.n_paired == 2
    assert (cmp_.b_only, cmp_.neither, cmp_.a_only, cmp_.both_hit) == (1, 1, 0, 0)
    assert cmp_.b_recall == 0.5 and cmp_.a_recall == 0.0
    assert cmp_.recall_delta == 0.5


def test_p_value_is_one_when_no_instance_discriminates(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-1",
                    "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    cmp_ = compare_arms(mf, arms, k=6)
    assert cmp_.a_only == 0 and cmp_.b_only == 0
    assert cmp_.p_value == 1.0


# ── cypher ───────────────────────────────────────────────────────────────


def test_selection_cypher_walks_predecessors():
    q = build_selection_cypher(42, "CALLED_BY", 6)
    assert "-[:CALLED_BY*1..6]->" in q
    assert "{id: 42}" in q


def test_selection_cypher_never_counts_a_node():
    q = build_selection_cypher(42, "CALLED_BY", 6)
    assert "count(n)" not in q
    assert "DISTINCT" not in q
    assert "RETURN n.id" in q


def test_selection_cypher_requires_a_bound_and_an_integer_id():
    with pytest.raises(ValueError):
        build_selection_cypher(42, "CALLED_BY", 0)
    with pytest.raises(TypeError):
        build_selection_cypher("42", "CALLED_BY", 6)


# ── pinned split ─────────────────────────────────────────────────────────


def test_split_assignment_is_deterministic(tmp_path):
    p = tmp_path / "split.json"
    p.write_text(json.dumps({"assignments": {"django__django-1": "sealed"}}),
                 encoding="utf-8")
    assert split_of("django__django-1", p) == "sealed"
    assert split_of("django__django-1", p) == "sealed"


def test_an_unlisted_instance_is_not_silently_assigned(tmp_path):
    p = tmp_path / "split.json"
    p.write_text(json.dumps({"assignments": {}}), encoding="utf-8")
    assert split_of("django__django-99", p) is None


def test_audit_can_be_restricted_to_one_half(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 3)])
    _write_instance(arms, "django__django-2", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-1",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "django__django-2",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])
    sp = tmp_path / "split.json"
    sp.write_text(json.dumps({"assignments": {
        "django__django-1": "sealed", "django__django-2": "dev"}}),
        encoding="utf-8")

    sealed = audit_recall(mf, arms, "arm_b", 6, split="sealed", split_path=sp)
    dev = audit_recall(mf, arms, "arm_b", 6, split="dev", split_path=sp)
    both = audit_recall(mf, arms, "arm_b", 6)

    assert sealed.n == 1 and sealed.hits == 1 and sealed.split == "sealed"
    assert dev.n == 1 and dev.hits == 0
    assert both.n == 2


# ── live in-engine parity ────────────────────────────────────────────────


@pytest.mark.engine
def test_live_selection_matches_the_offline_walk():
    from pathlib import Path

    from friction.client import connect
    from friction.config import Settings
    from friction.gate import _iter_manifest, live_selection

    try:
        transport = connect(Settings.from_env(), prefer="bolt")
    except Exception as exc:  # noqa: BLE001 - engine may not be running
        pytest.skip(f"engine not reachable: {exc}")

    root = Path("data/shipped/arms")
    record = next(r for r in _iter_manifest(root / "manifest.jsonl")
                  if r["instance_id"] == "django__django-11551")
    try:
        out = live_selection(transport, record, root, "arm_b", 6,
                             band_offset=910_000_000_000)
    finally:
        transport.close()

    assert out["parity"] is True
    assert out["queries"] and out["queries"][0]["engine_ms"] < 1000
    assert out["dropped_guarding_tests"] == 1


def test_sig_id_is_stable_and_banded():
    from friction.engine_diff import SIG_BAND, sig_id
    a = sig_id("m::f", "m::g")
    assert a == sig_id("m::f", "m::g")
    assert a != sig_id("m::g", "m::f")
    assert a >= SIG_BAND

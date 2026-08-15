import pytest

from friction import delta as D
from friction.namematch.graph import NameEdge
from friction.scip.extract import CallEdge


def A(*pairs):
    return [NameEdge(s, d, 1, "bare_name") for s, d in pairs]


def B(*pairs):
    return [CallEdge(s, d, False, 1) for s, d in pairs]


def test_identical_arms_give_perfect_agreement():
    r = D.compare(A(("f", "g")), B(("f", "g")))
    assert r.precision_a == 1.0 and r.recall_a == 1.0 and r.jaccard == 1.0


def test_disjoint_arms_give_zero_agreement():
    r = D.compare(A(("f", "g")), B(("x", "y")))
    assert r.precision_a == 0.0 and r.recall_a == 0.0 and r.jaccard == 0.0


def test_precision_is_fraction_of_arm_a_edges_confirmed_by_arm_b():
    r = D.compare(A(("f", "g"), ("f", "h")), B(("f", "g")))
    assert r.precision_a == 0.5
    assert r.recall_a == 1.0
    assert r.only_a == 1


def test_recall_counts_true_edges_arm_a_missed():
    r = D.compare(A(("f", "g")), B(("f", "g"), ("f", "h")))
    assert r.recall_a == 0.5
    assert r.only_b == 1


def test_external_arm_b_edges_are_excluded_from_the_comparison():
    b = [CallEdge("f", "builtins::str#lower().", True, 1)]
    r = D.compare(A(("f", "g")), b)
    assert r.only_b == 0


def test_worst_offenders_ranks_targets_by_unconfirmed_edge_count():
    a = A(("f1", "super"), ("f2", "super"), ("f3", "super"), ("f4", "g"))
    r = D.compare(a, B(("f4", "g")))
    assert r.worst_offenders[0] == ("super", 3)


def test_empty_arms_do_not_divide_by_zero():
    r = D.compare([], [])
    assert r.precision_a == 0.0 and r.jaccard == 0.0


def test_write_report_states_precision(tmp_path):
    r = D.compare(A(("f", "g"), ("f", "h")), B(("f", "g")))
    p = tmp_path / "graph-delta.md"
    D.write_report(r, {"repo": "django"}, p)
    assert "0.5" in p.read_text()

import pytest

from friction import evaluate
from friction.metric import Components


def row(iid, f1, failed, loc=1000, patch_lines=10):
    return evaluate.InstanceRow(
        instance_id=iid, repo="r",
        components=Components(f1, f1, f1, 0.5, 0.0, f1),
        failed={"sysA": failed}, repo_loc=loc, patch_lines=patch_lines,
    )


def test_auc_is_one_for_perfect_separation():
    assert evaluate.auc([0.1, 0.2, 0.8, 0.9], [False, False, True, True]) == 1.0


def test_auc_is_half_for_no_signal():
    # NOTE: the brief shipped labels [F, T, F, T] here and asserted 0.5, but on
    # ascending scores that arrangement is partially separable and roc_auc_score
    # correctly returns 0.75 (verified independently). A genuine no-signal
    # arrangement — positives symmetric about the score median — is [F, T, T, F],
    # which does yield 0.5. The label list is corrected so the test checks what
    # its name claims; the implementation under test is unchanged.
    value = evaluate.auc([0.1, 0.2, 0.3, 0.4], [False, True, True, False])
    assert value == pytest.approx(0.5)


def test_auc_returns_nan_when_one_class_missing():
    import math
    assert math.isnan(evaluate.auc([0.1, 0.2], [True, True]))


def test_point_biserial_returns_r_and_p():
    r, p = evaluate.point_biserial([0.1, 0.2, 0.8, 0.9], [False, False, True, True])
    assert r > 0.9
    assert 0.0 <= p <= 1.0


def test_verdict_thresholds():
    assert evaluate.verdict(0.70) == "GO"
    assert evaluate.verdict(0.60) == "WEAK"
    assert evaluate.verdict(0.50) == "NO-GO"


def test_verdict_boundaries_are_inclusive_at_go():
    assert evaluate.verdict(0.65) == "GO"
    assert evaluate.verdict(0.55) == "WEAK"


def test_component_aucs_reports_every_component():
    rows = [row("a", 0.1, False), row("b", 0.9, True),
            row("c", 0.2, False), row("d", 0.8, True)]
    aucs = evaluate.component_aucs(rows, "sysA")
    assert set(aucs) == {"f1", "f2", "f3", "f4", "f5", "f6"}
    assert aucs["f1"] == 1.0


def test_fit_weights_reports_train_and_test_separately():
    rows = [row(f"i{i}", i / 20, i > 10) for i in range(20)]
    weights, train_auc, test_auc = evaluate.fit_weights(rows, "sysA", seed=0)
    assert set(weights) == {"f1", "f2", "f3", "f4", "f5", "f6"}
    assert 0.0 <= train_auc <= 1.0
    assert 0.0 <= test_auc <= 1.0


def test_confounds_reports_size_and_patch_correlations():
    rows = [row(f"i{i}", i / 10, i > 5, loc=1000 * i, patch_lines=i)
            for i in range(1, 11)]
    out = evaluate.confounds(rows, "sysA")
    assert "friction_vs_repo_loc" in out
    assert "friction_vs_patch_lines" in out
    assert -1.0 <= out["friction_vs_repo_loc"] <= 1.0


def test_write_report_states_the_verdict(tmp_path):
    rows = [row("a", 0.1, False), row("b", 0.9, True)]
    results = {"system": "sysA", "auc": 0.75, "verdict": "GO",
               "point_biserial_r": 0.6, "point_biserial_p": 0.04,
               "component_aucs": {"f1": 0.75}, "confounds": {},
               "weights": evaluate.EQUAL, "train_auc": 0.8, "test_auc": 0.7,
               "per_system_auc": {"sysA": 0.75}}
    path = tmp_path / "evaluation.md"
    evaluate.write_report(rows, results, path)
    text = path.read_text()
    assert "GO" in text and "0.75" in text

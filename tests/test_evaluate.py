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


def crow(iid, comps, failed, system="sysA", loc=1000, patch_lines=10):
    """Row with each component set explicitly (comps is a 6-tuple)."""
    return evaluate.InstanceRow(
        instance_id=iid, repo="r", components=Components(*comps),
        failed={system: failed}, repo_loc=loc, patch_lines=patch_lines,
    )


def test_fit_weights_preserves_protective_coefficient_sign():
    # f1 is protective: high for resolved, low for failed. The old abs()-ing
    # path reported it as positive friction; sign must now be preserved.
    rows = []
    for i in range(10):
        rows.append(crow(f"r{i}", (0.9, 0.0, 0.0, 0.5, 0.0, 0.0), False))
    for i in range(10):
        rows.append(crow(f"f{i}", (0.1, 0.0, 0.0, 0.5, 0.0, 0.0), True))
    weights, _, _ = evaluate.fit_weights(rows, "sysA", seed=1)
    assert weights["f1"] < 0.0  # protective -> negative weight, not abs()'d


def test_fit_weights_uses_score_f4_convention():
    # Convergence (low f4) predicts failure. score() inverts f4, so the fitted
    # f4 weight must come out positive under the same convention.
    rows = []
    for i in range(10):
        rows.append(crow(f"r{i}", (0.0, 0.0, 0.0, 0.9, 0.0, 0.0), False))
    for i in range(10):
        rows.append(crow(f"f{i}", (0.0, 0.0, 0.0, 0.1, 0.0, 0.0), True))
    weights, _, _ = evaluate.fit_weights(rows, "sysA", seed=1)
    assert weights["f4"] > 0.0


def test_confounds_reports_direct_predictor_aucs():
    # patch_lines separates the classes perfectly; its standalone AUC is 1.0.
    rows = [row(f"i{i}", 0.5, i > 5, loc=1000, patch_lines=i) for i in range(1, 11)]
    out = evaluate.confounds(rows, "sysA")
    assert "repo_loc_auc" in out and "patch_lines_auc" in out
    assert out["patch_lines_auc"] == 1.0


def test_confounds_honours_the_system_argument():
    rows = [
        evaluate.InstanceRow("a", "r", Components(0.5, 0.5, 0.5, 0.5, 0, 0.5),
                             {"sysA": False, "sysB": True}, 100, 1),
        evaluate.InstanceRow("b", "r", Components(0.5, 0.5, 0.5, 0.5, 0, 0.5),
                             {"sysA": True, "sysB": False}, 900, 9),
        evaluate.InstanceRow("c", "r", Components(0.5, 0.5, 0.5, 0.5, 0, 0.5),
                             {"sysA": False, "sysB": True}, 100, 1),
        evaluate.InstanceRow("d", "r", Components(0.5, 0.5, 0.5, 0.5, 0, 0.5),
                             {"sysA": True, "sysB": False}, 900, 9),
    ]
    a = evaluate.confounds(rows, "sysA")["repo_loc_auc"]
    b = evaluate.confounds(rows, "sysB")["repo_loc_auc"]
    # Labels are flipped between systems, so the same feature's AUC must flip.
    assert a != b


def test_sensitivity_excluded_reports_auc_both_ways():
    kept = [row("k0", 0.1, False), row("k1", 0.9, True),
            row("k2", 0.2, False), row("k3", 0.8, True)]
    # Excluded: failure-heavy, zero friction by construction.
    excluded = [row("e0", 0.0, True), row("e1", 0.0, True),
                row("e2", 0.0, False)]
    out = evaluate.sensitivity_excluded(kept, excluded, "sysA")
    assert out["kept_auc"] == 1.0  # clean separation on the kept set
    assert out["included_auc"] < out["kept_auc"]  # counter-evidence pulls it down
    assert out["excluded"] == {"n": 3, "failed": 2, "resolved": 1}


def test_write_report_flags_a_missing_exclusion_record(tmp_path):
    rows = [row("a", 0.1, False), row("b", 0.9, True)]
    results = {"system": "sysA", "auc": 0.75, "verdict": "GO",
               "point_biserial_r": 0.6, "point_biserial_p": 0.04,
               "component_aucs": {"f1": 0.75}, "confounds": {},
               "weights": evaluate.EQUAL, "train_auc": 0.8, "test_auc": 0.7,
               "per_system_auc": {"sysA": 0.75}}
    path = tmp_path / "evaluation.md"
    evaluate.write_report(rows, results, path)
    text = path.read_text()
    assert "Excluded instances" in text
    assert "No exclusion record" in text


def test_write_report_discloses_excluded_instances(tmp_path):
    kept = [row("a", 0.1, False), row("b", 0.9, True)]
    excluded = [row("django__django-1", 0.0, True),
                row("django__django-2", 0.0, True)]
    sens = evaluate.sensitivity_excluded(kept, excluded, "sysA")
    results = {"system": "sysA", "auc": 0.75, "verdict": "GO",
               "point_biserial_r": 0.6, "point_biserial_p": 0.04,
               "component_aucs": {"f1": 0.75}, "confounds": {},
               "weights": evaluate.EQUAL, "train_auc": 0.8, "test_auc": 0.7,
               "per_system_auc": {"sysA": 0.75},
               "sensitivity": sens, "excluded_instances": excluded}
    path = tmp_path / "evaluation.md"
    evaluate.write_report(kept, results, path)
    text = path.read_text()
    assert "django__django-1" in text and "django__django-2" in text
    assert f"{sens['included_auc']:.3f}" in text
    assert "2 failed" in text or "2 failed and 0 resolved" in text


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

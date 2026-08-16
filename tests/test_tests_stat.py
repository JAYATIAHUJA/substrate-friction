"""Tests for friction.tests_stat: DeLong, LR test, power, leave-one-repo-out.

Pure statistical logic, so these are deterministic and hermetic — no corpus,
no network, no engine.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from friction import tests_stat


# --------------------------------------------------------------------------
# DeLong test for two correlated AUCs.
# --------------------------------------------------------------------------

def test_delong_recovers_the_two_aucs():
    # a separates the labels perfectly (AUC 1.0); b is reversed (AUC 0.0).
    y = [0, 0, 0, 1, 1, 1]
    a = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
    b = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    res = tests_stat.delong_test(y, a, b)
    assert res.auc_a == pytest.approx(1.0)
    assert res.auc_b == pytest.approx(0.0)
    # a is strictly better than b, so z should be strongly positive.
    assert res.z > 0
    assert 0.0 <= res.p <= 1.0


def test_delong_identical_predictors_have_zero_difference():
    y = [0, 1, 0, 1, 1, 0, 1, 0]
    a = [0.2, 0.6, 0.3, 0.9, 0.7, 0.1, 0.8, 0.4]
    res = tests_stat.delong_test(y, a, list(a))
    assert res.auc_a == pytest.approx(res.auc_b)
    assert res.p == pytest.approx(1.0, abs=1e-9)  # no difference at all


def test_delong_single_class_is_nan_not_crash():
    res = tests_stat.delong_test([1, 1, 1], [0.1, 0.2, 0.3], [0.3, 0.2, 0.1])
    assert math.isnan(res.p)


# --------------------------------------------------------------------------
# Likelihood-ratio test: does adding a feature to a baseline model help?
# --------------------------------------------------------------------------

def test_lr_test_detects_an_informative_added_feature():
    # y is a clean function of the feature; the baseline is pure noise.
    y = [0, 0, 0, 0, 1, 1, 1, 1] * 4
    feat = [0.0, 0.1, 0.2, 0.3, 0.7, 0.8, 0.9, 1.0] * 4
    noise = [0.5] * len(y)
    res = tests_stat.lr_test(y, base=[noise], full=[noise, feat])
    assert res.df == 1
    assert res.stat > 0
    assert res.p < 0.05


def test_lr_test_uninformative_feature_is_not_significant():
    y = [0, 1] * 20
    base = [1.0] * len(y)
    useless = [0.123] * len(y)  # constant: adds nothing
    res = tests_stat.lr_test(y, base=[base], full=[base, useless])
    assert res.p > 0.05


# --------------------------------------------------------------------------
# required_n: sample size to distinguish two correlated AUCs.
# --------------------------------------------------------------------------

def test_required_n_matches_published_power_figure():
    # The plan cites ~610 instances to detect +0.05 AUC at rho=0.5 relative to
    # the published ~0.787 text baseline. The formula should land in that region.
    n = tests_stat.required_n(0.787, 0.837, 0.5)
    assert 500 <= n <= 700


def test_required_n_grows_as_the_effect_shrinks():
    big = tests_stat.required_n(0.65, 0.75, 0.5)
    small = tests_stat.required_n(0.65, 0.70, 0.5)
    assert small > big


def test_required_n_grows_as_correlation_falls():
    high_rho = tests_stat.required_n(0.65, 0.70, 0.8)
    low_rho = tests_stat.required_n(0.65, 0.70, 0.2)
    assert low_rho > high_rho


# --------------------------------------------------------------------------
# leave_one_repo_out: train on the other repos, test on the held-out one.
# --------------------------------------------------------------------------

def _separable_frame(repos=(("alpha", 0.0), ("beta", 10.0), ("gamma", 20.0))):
    rows = []
    # In every repo, a high `sig` value means failure. A model trained on the
    # other repos should therefore generalise to the held-out repo.
    for repo, base in repos:
        for i in range(10):
            failed = i >= 5
            rows.append({"repo": repo, "sig": base + (i * 1.0),
                         "failed": failed})
    return pd.DataFrame(rows)


def test_loro_holds_out_each_repo_and_reports_pooled():
    df = _separable_frame()
    out = tests_stat.leave_one_repo_out(df, ["sig"])
    assert set(out["per_repo"]) == {"alpha", "beta", "gamma"}
    assert out["per_repo_n"] == {"alpha": 10, "beta": 10, "gamma": 10}
    # Signal generalises across repos, so held-out AUCs clear 0.5.
    for repo in ("alpha", "beta", "gamma"):
        assert out["per_repo"][repo] > 0.5
    assert 0.0 <= out["pooled_auc"] <= 1.0


def test_loro_single_class_heldout_repo_is_nan_not_crash():
    df = _separable_frame()
    # Make every gamma instance a failure -> held-out gamma has one label class,
    # but alpha and beta still have both classes in their training folds.
    df.loc[df["repo"] == "gamma", "failed"] = True
    out = tests_stat.leave_one_repo_out(df, ["sig"])
    assert math.isnan(out["per_repo"]["gamma"])
    # alpha is still well-defined and pooled is still computed.
    assert not math.isnan(out["per_repo"]["alpha"])

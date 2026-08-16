"""Statistical tests for the fair-test evaluation (Task 5).

Four pieces, each answering a question the n=44 single-repo evaluation could not:

* :func:`delong_test` — is the best feature's AUC different from the best
  baseline's AUC on the *same* instances? DeLong's test accounts for the
  correlation between two AUCs measured on one sample (Sun & Xu 2014, the fast
  O(n log n) form).
* :func:`lr_test` — does adding the feature to a logistic model that already
  has the baseline improve the fit beyond chance? A nested likelihood-ratio
  test, complementary to DeLong.
* :func:`required_n` — how many instances would it take to resolve a given AUC
  gap between two correlated predictors? The Hanley–McNeil large-sample
  variance, so the power statement is a number and not a hand-wave.
* :func:`leave_one_repo_out` — train on the other repos, test on the held-out
  one, for each repo in turn. This is the split the build spec asked for: it
  cannot memorise repo identity, which is itself a strong difficulty proxy.

No statsmodels dependency (it is not installed); the logistic fits use
scikit-learn and the variances use closed forms.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------
# DeLong test for two correlated ROC AUCs.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DelongResult:
    auc_a: float
    auc_b: float
    var_a: float
    var_b: float
    cov_ab: float
    z: float
    p: float


def _midrank(x: np.ndarray) -> np.ndarray:
    """Mid-ranks of ``x`` (ties share the average rank), 1-based."""
    order = np.argsort(x)
    z = x[order]
    n = len(x)
    t = np.zeros(n, dtype=float)
    i = 0
    while i < n:
        j = i
        while j < n and z[j] == z[i]:
            j += 1
        t[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    out = np.empty(n, dtype=float)
    out[order] = t
    return out


def _fast_delong(preds: np.ndarray, m: int):
    """Fast DeLong structural components for ``k`` predictors.

    ``preds`` is ``k x (m+n)`` with the ``m`` positive-class columns first.
    Returns ``(aucs, covariance)`` where covariance is ``k x k``.
    """
    n = preds.shape[1] - m
    k = preds.shape[0]
    pos = preds[:, :m]
    neg = preds[:, m:]
    tx = np.empty([k, m])
    ty = np.empty([k, n])
    tz = np.empty([k, m + n])
    for r in range(k):
        tx[r, :] = _midrank(pos[r, :])
        ty[r, :] = _midrank(neg[r, :])
        tz[r, :] = _midrank(preds[r, :])
    aucs = tz[:, :m].sum(axis=1) / m / n - (m + 1.0) / 2.0 / n
    v01 = (tz[:, :m] - tx) / n
    v10 = 1.0 - (tz[:, m:] - ty) / m
    # np.cov needs >1 observation per row; guard the degenerate case.
    sx = np.cov(v01) if m > 1 else np.zeros((k, k))
    sy = np.cov(v10) if n > 1 else np.zeros((k, k))
    sx = np.atleast_2d(sx)
    sy = np.atleast_2d(sy)
    cov = sx / m + sy / n
    return aucs, cov


def _nan_delong() -> DelongResult:
    nan = float("nan")
    return DelongResult(nan, nan, nan, nan, nan, nan, nan)


def delong_test(y, a, b) -> DelongResult:
    """DeLong's test of ``AUC(a) - AUC(b)`` on the same labelled sample ``y``.

    ``y`` is the truth (positive class is truthy, e.g. ``failed=True``); ``a``
    and ``b`` are two score vectors. Returns the two AUCs, their variances and
    covariance, the z statistic for their difference, and a two-sided p-value.
    A single-class ``y`` (AUC undefined) yields an all-NaN result rather than an
    error. ``z`` is oriented so ``z > 0`` means ``a`` scores the higher AUC.
    """
    y = np.asarray(list(y))
    a = np.asarray(list(a), dtype=float)
    b = np.asarray(list(b), dtype=float)
    yb = np.asarray([1 if bool(v) else 0 for v in y], dtype=int)
    m = int(yb.sum())
    if m == 0 or m == len(yb):
        return _nan_delong()

    order = np.argsort(-yb, kind="stable")  # positives (1) first
    preds = np.vstack([a[order], b[order]])
    aucs, cov = _fast_delong(preds, m)

    var_a = float(cov[0, 0])
    var_b = float(cov[1, 1])
    cov_ab = float(cov[0, 1])
    var_diff = var_a + var_b - 2 * cov_ab
    diff = float(aucs[0] - aucs[1])
    if var_diff <= 0:
        # Identical (or perfectly correlated equal-variance) predictors: no
        # resolvable difference. z=0, p=1 when the AUCs coincide.
        z = 0.0 if abs(diff) < 1e-12 else math.copysign(float("inf"), diff)
        p = 1.0 if abs(diff) < 1e-12 else 0.0
        return DelongResult(float(aucs[0]), float(aucs[1]), var_a, var_b,
                            cov_ab, z, p)

    z = diff / math.sqrt(var_diff)
    p = _two_sided_p(z)
    return DelongResult(float(aucs[0]), float(aucs[1]), var_a, var_b, cov_ab,
                        float(z), float(p))


def _two_sided_p(z: float) -> float:
    # 2 * (1 - Phi(|z|)) via the error function, no scipy needed.
    return math.erfc(abs(z) / math.sqrt(2.0))


# --------------------------------------------------------------------------
# Nested likelihood-ratio test between two logistic models.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class LRResult:
    ll_base: float
    ll_full: float
    stat: float
    df: int
    p: float


def _logit_loglik(y: np.ndarray, cols: list) -> float:
    """Fitted log-likelihood of an (unregularised) logistic model with an
    intercept and the given predictor columns. Constant/collinear columns are
    tolerated; the fit maximises the Bernoulli likelihood by Newton steps."""
    y = y.astype(float)
    n = len(y)
    if cols:
        X = np.column_stack([np.ones(n)] + [np.asarray(c, dtype=float) for c in cols])
    else:
        X = np.ones((n, 1))
    # Standardise non-intercept columns for numerical stability.
    Xs = X.copy()
    for j in range(1, Xs.shape[1]):
        col = Xs[:, j]
        sd = col.std()
        if sd > 0:
            Xs[:, j] = (col - col.mean()) / sd
    beta = np.zeros(Xs.shape[1])
    for _ in range(100):
        eta = Xs @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30)))
        w = np.clip(p * (1 - p), 1e-9, None)
        grad = Xs.T @ (y - p)
        hess = (Xs * w[:, None]).T @ Xs
        try:
            step = np.linalg.solve(hess + 1e-8 * np.eye(Xs.shape[1]), grad)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    eta = Xs @ beta
    p = np.clip(1.0 / (1.0 + np.exp(-np.clip(eta, -30, 30))), 1e-12, 1 - 1e-12)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def lr_test(y, base: list, full: list) -> LRResult:
    """Likelihood-ratio test of ``full`` (base predictors + extra) vs ``base``.

    ``base`` and ``full`` are lists of equal-length predictor columns (an
    intercept is always added on top). ``full`` must nest ``base``. Returns the
    two fitted log-likelihoods, the LR statistic ``2*(ll_full - ll_base)``, its
    degrees of freedom (``len(full) - len(base)``), and the chi-square p-value.
    """
    y = np.asarray([1 if bool(v) else 0 for v in y], dtype=int)
    df = len(full) - len(base)
    ll_base = _logit_loglik(y, list(base))
    ll_full = _logit_loglik(y, list(full))
    stat = max(0.0, 2.0 * (ll_full - ll_base))
    p = float("nan") if df <= 0 else _chi2_sf(stat, df)
    return LRResult(ll_base, ll_full, float(stat), int(df), float(p))


def _chi2_sf(stat: float, df: int) -> float:
    """Upper-tail chi-square probability via the regularised gamma function."""
    from math import gamma, exp, log

    # Use the lower regularised incomplete gamma P(df/2, stat/2); sf = 1 - P.
    a = df / 2.0
    x = stat / 2.0
    if x <= 0:
        return 1.0
    if x < a + 1.0:
        # Series expansion for the lower incomplete gamma.
        term = 1.0 / a
        total = term
        n = a
        for _ in range(500):
            n += 1.0
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        p_lower = total * exp(-x + a * log(x) - _lgamma(a))
        return max(0.0, min(1.0, 1.0 - p_lower))
    # Continued fraction for the upper incomplete gamma (Lentz).
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    q_upper = exp(-x + a * log(x) - _lgamma(a)) * h
    return max(0.0, min(1.0, q_upper))


def _lgamma(a: float) -> float:
    return math.lgamma(a)


# --------------------------------------------------------------------------
# Sample size to resolve an AUC difference between two correlated predictors.
# --------------------------------------------------------------------------

def _z_from_p(p: float) -> float:
    # Inverse normal CDF via the same NormalDist scipy-free path used elsewhere.
    from statistics import NormalDist
    return NormalDist().inv_cdf(p)


def _hanley_c(auc: float) -> float:
    """Hanley–McNeil large-sample AUC variance coefficient (var ~ C/m per group
    with balanced classes): ``Q1 + Q2 - 2*auc**2``."""
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    return q1 + q2 - 2 * auc * auc


def required_n(auc0: float, auc1: float, rho: float,
               alpha: float = 0.05, power: float = 0.8) -> int:
    """Total balanced-class sample size to detect ``|auc1 - auc0|`` between two
    correlated AUCs (correlation ``rho``) at the given two-sided ``alpha`` and
    ``power``. Hanley–McNeil variance; returns the total n (both classes).

    Sanity anchor: ``required_n(0.787, 0.837, 0.5) ~ 584``, matching the plan's
    cited "~610 instances for +0.05 AUC at rho=0.5" against the published text
    baseline.
    """
    delta = abs(auc1 - auc0)
    if delta <= 0:
        return 10 ** 9
    za = _z_from_p(1 - alpha / 2)
    zb = _z_from_p(power)
    c0 = _hanley_c(auc0)
    c1 = _hanley_c(auc1)
    var_num = c0 + c1 - 2 * rho * math.sqrt(max(c0, 0.0) * max(c1, 0.0))
    var_num = max(var_num, 0.0)
    m = ((za + zb) ** 2) * var_num / (delta * delta)  # per class
    return int(math.ceil(2 * m))


# --------------------------------------------------------------------------
# Leave-one-repo-out evaluation.
# --------------------------------------------------------------------------

def _auc(scores, labels) -> float:
    from friction.evaluate import auc
    return auc(list(scores), [bool(v) for v in labels])


def leave_one_repo_out(df, feature_cols, label_col: str = "failed",
                       repo_col: str = "repo", reg_c: float = 1.0) -> dict:
    """Leave-one-repo-out logistic evaluation.

    For each repo in ``df[repo_col]``: fit a standardised logistic model on all
    OTHER repos' instances over ``feature_cols``, predict on the held-out repo,
    and record the held-out AUC. Also returns the pooled AUC over all held-out
    predictions concatenated, and the mean of the well-defined per-repo AUCs.

    A held-out repo with a single label class (AUC undefined) is reported as
    ``nan`` and excluded from the mean, but its predictions still enter the
    pool. Training folds with a single label class are skipped (nan).
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    feature_cols = list(feature_cols)
    repos = sorted(map(str, df[repo_col].unique()))
    per_repo: dict[str, float] = {}
    per_repo_n: dict[str, int] = {}
    pooled_scores: list[float] = []
    pooled_labels: list[int] = []

    for held in repos:
        te = df[df[repo_col].astype(str) == held]
        tr = df[df[repo_col].astype(str) != held]
        per_repo_n[held] = int(len(te))
        ytr = tr[label_col].astype(int).to_numpy()
        yte = te[label_col].astype(int).to_numpy()
        if len(te) == 0 or len(set(ytr.tolist())) < 2:
            per_repo[held] = float("nan")
            continue
        scaler = StandardScaler().fit(tr[feature_cols].to_numpy(dtype=float))
        x_tr = scaler.transform(tr[feature_cols].to_numpy(dtype=float))
        x_te = scaler.transform(te[feature_cols].to_numpy(dtype=float))
        clf = LogisticRegression(max_iter=2000, C=reg_c)
        clf.fit(x_tr, ytr)
        p = clf.predict_proba(x_te)[:, 1]
        pooled_scores.extend(p.tolist())
        pooled_labels.extend(yte.tolist())
        per_repo[held] = (_auc(p, yte)
                          if len(set(yte.tolist())) == 2 else float("nan"))

    valid = [v for v in per_repo.values() if not math.isnan(v)]
    pooled = (_auc(pooled_scores, pooled_labels)
              if len(set(pooled_labels)) == 2 else float("nan"))
    return {
        "per_repo": per_repo,
        "per_repo_n": per_repo_n,
        "pooled_auc": pooled,
        "mean_per_repo_auc": (sum(valid) / len(valid)) if valid else float("nan"),
        "n": int(len(df)),
        "feature_cols": feature_cols,
    }

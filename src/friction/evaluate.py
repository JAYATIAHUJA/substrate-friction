"""Does friction predict agent failure? Answer it honestly, then report it
whichever way it went.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from scipy.stats import pointbiserialr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from friction.metric import COMPONENT_NAMES, EQUAL_WEIGHTS, Components, score

EQUAL = dict(EQUAL_WEIGHTS)


@dataclass(frozen=True)
class InstanceRow:
    instance_id: str
    repo: str
    components: Components
    failed: dict[str, bool]
    repo_loc: int
    patch_lines: int


def auc(scores: list[float], failed: list[bool]) -> float:
    labels = [1 if f else 0 for f in failed]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def point_biserial(scores: list[float], failed: list[bool]) -> tuple[float, float]:
    labels = [1 if f else 0 for f in failed]
    if len(set(labels)) < 2:
        return float("nan"), float("nan")
    result = pointbiserialr(labels, scores)
    return float(result.correlation), float(result.pvalue)


def _scores(rows: list[InstanceRow], weights: dict[str, float]) -> list[float]:
    return [score(r.components, weights) for r in rows]


def _labels(rows: list[InstanceRow], system: str) -> list[bool]:
    return [r.failed.get(system, False) for r in rows]


def component_aucs(rows: list[InstanceRow], system: str) -> dict[str, float]:
    labels = _labels(rows, system)
    out: dict[str, float] = {}
    for name in COMPONENT_NAMES:
        values = [getattr(r.components, name) for r in rows]
        if name == "f4":
            values = [1.0 - v for v in values]
        out[name] = auc(values, labels)
    return out


def _feature_row(components) -> list[float]:
    """Feature vector in the exact convention score() uses: f4 is inverted so
    convergence (paths funnelling through shared nodes) reads as higher friction,
    matching the scored blend. Training on raw f4 while scoring on (1 - f4) is
    the incoherence this replaces."""
    values = components.as_dict()
    values["f4"] = 1.0 - values["f4"]
    return [values[n] for n in COMPONENT_NAMES]


def fit_weights(rows: list[InstanceRow], system: str,
                seed: int = 0) -> tuple[dict[str, float], float, float]:
    """Fit on a train split, report on a held-out split. Never fit and report
    on the same data. Coefficient sign is preserved (a protective component
    keeps a negative weight instead of being folded into positive friction), and
    both AUCs come from the fitted model's own predict_proba rather than a
    re-derived, sign-stripped linear blend."""
    indexed = list(range(len(rows)))
    random.Random(seed).shuffle(indexed)
    split = max(1, int(len(indexed) * 0.7))
    train_idx, test_idx = indexed[:split], indexed[split:]
    if not test_idx:
        return dict(EQUAL), float("nan"), float("nan")

    def matrix(idx):
        return [_feature_row(rows[i].components) for i in idx]

    def target(idx):
        return [1 if rows[i].failed.get(system, False) else 0 for i in idx]

    y_train = target(train_idx)
    if len(set(y_train)) < 2:
        return dict(EQUAL), float("nan"), float("nan")

    model = LogisticRegression(max_iter=2000)
    model.fit(matrix(train_idx), y_train)

    coefs = model.coef_[0]
    magnitude = sum(abs(c) for c in coefs) or 1.0
    # Sign preserved: reports the direction the model actually found.
    weights = {n: float(c) / magnitude for n, c in zip(COMPONENT_NAMES, coefs)}

    train_prob = [float(p) for p in model.predict_proba(matrix(train_idx))[:, 1]]
    test_prob = [float(p) for p in model.predict_proba(matrix(test_idx))[:, 1]]
    return weights, auc(train_prob, [bool(v) for v in y_train]), \
        auc(test_prob, [bool(v) for v in target(test_idx)])


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return float("nan") if dx == 0 or dy == 0 else num / (dx * dy)


def confounds(rows: list[InstanceRow], system: str) -> dict[str, float]:
    """Correlate friction with size proxies AND test whether those proxies
    predict failure directly. A correlation alone cannot rule a confound in or
    out: if repo LOC neither correlates with friction nor predicts failure, it
    is not confounding anything. The direct-predictor AUCs make that visible.
    The `system` argument selects the ground-truth labels for those AUCs."""
    scores = _scores(rows, EQUAL)
    labels = _labels(rows, system)
    repo_loc = [float(r.repo_loc) for r in rows]
    patch_lines = [float(r.patch_lines) for r in rows]
    return {
        "friction_vs_repo_loc": _pearson(scores, repo_loc),
        "friction_vs_patch_lines": _pearson(scores, patch_lines),
        "repo_loc_auc": auc(repo_loc, labels),
        "patch_lines_auc": auc(patch_lines, labels),
    }


def label_distribution(rows: list[InstanceRow], system: str) -> dict[str, int]:
    labels = _labels(rows, system)
    failed = sum(1 for f in labels if f)
    return {"n": len(rows), "failed": failed, "resolved": len(rows) - failed}


def sensitivity_excluded(kept: list[InstanceRow], excluded: list[InstanceRow],
                         system: str) -> dict:
    """Report the equal-weights AUC both ways: on the kept set alone, and with
    the excluded (empty-endpoint, zero-friction-by-construction) instances added
    back at minimum friction.

    The excluded set is failure-heavy and low-friction, i.e. counter-evidence.
    Dropping it silently flatters the metric, so the honest number is the one
    that includes it. `included_auc` places every excluded instance at score 0.0
    (the floor the metric assigns when there are no paths)."""
    kept_scores = _scores(kept, EQUAL)
    kept_labels = _labels(kept, system)
    all_scores = kept_scores + [0.0] * len(excluded)
    all_labels = kept_labels + _labels(excluded, system)
    return {
        "kept": label_distribution(kept, system),
        "excluded": label_distribution(excluded, system),
        "kept_auc": auc(kept_scores, kept_labels),
        "included_auc": auc(all_scores, all_labels),
    }


def verdict(auc_value: float) -> str:
    if math.isnan(auc_value):
        return "NO-GO"
    if auc_value >= 0.65:
        return "GO"
    if auc_value >= 0.55:
        return "WEAK"
    return "NO-GO"


def plot(rows: list[InstanceRow], system: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scores = _scores(rows, EQUAL)
    labels = _labels(rows, system)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    resolved = [s for s, f in zip(scores, labels) if not f]
    failed = [s for s, f in zip(scores, labels) if f]
    ax.hist([resolved, failed], bins=12, stacked=False,
            label=[f"resolved by {system}", f"failed by {system}"])
    ax.set_xlabel("Friction score (equal weights)")
    ax.set_ylabel("Instances")
    ax.set_title(f"Friction vs outcome — n={len(rows)}, AUC={auc(scores, labels):.3f}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _exclusion_section(results: dict) -> str:
    """Markdown block (trailing blank line included) disclosing which instances
    were dropped and how the AUC moves when they are added back. Present whether
    or not exclusion data was supplied — silence is not an option here."""
    sens = results.get("sensitivity")
    excluded = results.get("excluded_instances", [])
    system = results.get("system", "")
    lines = ["## Excluded instances", ""]
    if sens is None and not excluded:
        lines += [
            "No exclusion record was supplied to this report. If any instances were "
            "dropped for empty endpoint sets, disclose their count, names, and label "
            "distribution here. A bare \"n/n usable\" without this section is not an "
            "acceptable summary.",
            "",
        ]
        return "\n".join(lines) + "\n"

    kept = sens["kept"] if sens else {}
    exc = sens["excluded"] if sens else label_distribution(excluded, system)
    lines += [
        f"{exc['n']} instance(s) were excluded because an endpoint set was empty, "
        f"making their friction zero by construction. Of those, {exc['failed']} "
        f"failed and {exc['resolved']} were resolved — a failure-heavy, low-friction "
        "group that is counter-evidence to the hypothesis, so dropping it flatters "
        "the result.",
        "",
    ]
    if excluded:
        names = ", ".join(f"`{r.instance_id}`" for r in excluded)
        lines += [f"Excluded: {names}.", ""]
    if sens:
        lines += [
            "| Set | AUC |",
            "|---|---|",
            f"| kept only (n={kept.get('n', '?')}) | {sens['kept_auc']:.3f} |",
            f"| including excluded at minimum friction "
            f"(n={kept.get('n', 0) + exc['n']}) | {sens['included_auc']:.3f} |",
            "",
            "The included-at-minimum-friction row is the honest headline; the "
            "kept-only row is shown only so the flattering effect of exclusion is "
            "visible.",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_report(rows: list[InstanceRow], results: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Evaluation",
        "",
        f"**Verdict: {results['verdict']}** — AUC {results['auc']:.3f} "
        f"on n={len(rows)} instances, ground truth `{results['system']}`.",
        "",
        f"Point-biserial r = {results['point_biserial_r']:.3f} "
        f"(p = {results['point_biserial_p']:.4f}).",
        "",
        "## Per-component AUC",
        "",
        "| Component | AUC |",
        "|---|---|",
    ]
    for name, value in results["component_aucs"].items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += [
        "",
        "If one component's AUC matches or beats the composite, that is the actual",
        "finding and it is reported as such rather than buried under a blend.",
        "",
        "## Weights",
        "",
        f"Fitted on a 70% train split, evaluated on the held-out 30%. "
        f"Train AUC {results['train_auc']:.3f}, held-out AUC {results['test_auc']:.3f}.",
        "",
        "| Component | Weight |",
        "|---|---|",
    ]
    for name, value in results["weights"].items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += ["", "## Confound checks", "", "| Check | Value |", "|---|---|"]
    for name, value in results["confounds"].items():
        lines.append(f"| {name.replace('_', ' ')} | {value:.3f} |")
    lines += [
        "",
        "A high correlation with repo LOC would mean friction is a size proxy; a high",
        "correlation with patch line count would mean it is a patch-size proxy. The",
        "`*_auc` rows go further: they report whether repo LOC or patch size predict",
        "failure *directly*. A proxy that does not itself predict failure cannot be",
        "confounding the result. All are reported whether or not they flatter it.",
        "",
        _exclusion_section(results),
        "## Stability across systems",
        "",
        "| System | AUC |",
        "|---|---|",
    ]
    for system, value in results["per_system_auc"].items():
        lines.append(f"| `{system}` | {value:.3f} |")
    lines += [
        "",
        "A result that holds for only one published system is measuring that system's",
        "quirks, not the code.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")

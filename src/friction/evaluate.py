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


def fit_weights(rows: list[InstanceRow], system: str,
                seed: int = 0) -> tuple[dict[str, float], float, float]:
    """Fit on a train split, report on a held-out split. Never fit and report
    on the same data."""
    indexed = list(range(len(rows)))
    random.Random(seed).shuffle(indexed)
    split = max(1, int(len(indexed) * 0.7))
    train_idx, test_idx = indexed[:split], indexed[split:]
    if not test_idx:
        return dict(EQUAL), float("nan"), float("nan")

    def matrix(idx):
        return [[getattr(rows[i].components, n) for n in COMPONENT_NAMES] for i in idx]

    def target(idx):
        return [1 if rows[i].failed.get(system, False) else 0 for i in idx]

    y_train = target(train_idx)
    if len(set(y_train)) < 2:
        return dict(EQUAL), float("nan"), float("nan")

    model = LogisticRegression(max_iter=2000)
    model.fit(matrix(train_idx), y_train)

    coefs = model.coef_[0]
    magnitude = sum(abs(c) for c in coefs) or 1.0
    weights = {n: abs(c) / magnitude for n, c in zip(COMPONENT_NAMES, coefs)}

    train_scores = [score(rows[i].components, weights) for i in train_idx]
    test_scores = [score(rows[i].components, weights) for i in test_idx]
    return weights, auc(train_scores, [bool(v) for v in y_train]), \
        auc(test_scores, [bool(v) for v in target(test_idx)])


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
    scores = _scores(rows, EQUAL)
    return {
        "friction_vs_repo_loc": _pearson(scores, [float(r.repo_loc) for r in rows]),
        "friction_vs_patch_lines": _pearson(scores, [float(r.patch_lines) for r in rows]),
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
    lines += ["", "## Confound checks", "", "| Check | Pearson r |", "|---|---|"]
    for name, value in results["confounds"].items():
        lines.append(f"| {name.replace('_', ' ')} | {value:.3f} |")
    lines += [
        "",
        "A high correlation with repo LOC would mean friction is a size proxy; a high",
        "correlation with patch line count would mean it is a patch-size proxy. Both",
        "are reported whether or not they flatter the result.",
        "",
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

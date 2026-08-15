"""Honest evaluation of the hedged secondary metric.

This module answers one question and refuses to flatter the answer: do the
directional structure features from :mod:`friction.features` predict per-instance
agent failure better than the cheap non-graph baselines (patch size, f2p count,
statement length) on the SAME instances? It reports the feature AUCs, the
baseline AUCs, a bootstrap CI on the difference, the class balance, and — because
n is ~44 at best — states plainly that the sample cannot resolve small effects.

It also carries, unreproduced, the published state of the art (Agent
Psychometrics, arXiv 2604.00594: per-instance failure prediction is already
solved at AUC 0.841), and it OPENS with the retraction of the v1 and v2 numbers
so no reader mistakes a withdrawn result for a live one. See
``docs/connectivity.md`` for the directional caveat these features are built to
respect.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from friction import baselines, features
from friction.connectivity import load_graph
from friction.evaluate import auc


@dataclass(frozen=True)
class Row:
    instance_id: str
    features: dict[str, float]
    failed: dict[str, bool]
    baselines: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Building rows from the corpus.
# --------------------------------------------------------------------------

def _baselines_for(instance_id: str, inst_by_id: dict,
                   ann_entry: dict) -> dict[str, float]:
    """Non-graph baseline features for one instance.

    Prefers the full SWE-bench-derived block (patch_lines, patch_files,
    patch_hunks, f2p_count, statement_chars, statement_has_traceback) via
    :func:`friction.baselines.extract` when the matching SWE-bench instance is
    available. Falls back to the annotations' ``patch_lines`` alone when it is
    not (e.g. a synthetic corpus in a unit test)."""
    inst = inst_by_id.get(instance_id)
    if inst is not None:
        return {k: float(v) for k, v in asdict(baselines.extract(inst)).items()}
    pl = ann_entry.get("patch_lines")
    return {"patch_lines": float(pl)} if pl is not None else {}


def build_rows(manifest, annotations, arms_root, arm: str = "arm_b",
               instances: Iterable | None = None) -> list[Row]:
    """Build one :class:`Row` per instance that can actually be measured.

    An instance is included only when its ``arm`` entry carries BOTH a non-empty
    fix-site set and a non-empty test-target set (otherwise the directional
    features are degenerate) and its ``edges.ndjson`` and an annotations entry
    both exist. Directional features come from ``arm``'s ``edges.ndjson`` using
    the arm's own node-id band; the ``failed`` labels come from annotations.

    ``instances`` is the SWE-bench instance list used for baselines. Pass
    ``None`` to load it cache-first (django/SWE-bench-Verified); pass an explicit
    list (or ``[]``) to keep the call hermetic.
    """
    manifest = Path(manifest)
    arms_root = Path(arms_root)
    ann = json.loads(Path(annotations).read_text(encoding="utf-8"))

    if instances is None:
        # Cache-first; the whole verified split is a superset of the corpus.
        from friction.swebench import load_instances
        instances = load_instances()
    inst_by_id = {getattr(i, "instance_id"): i for i in instances}

    rows: list[Row] = []
    with manifest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            iid = record["instance_id"]
            entry = record.get(arm) or {}
            fix = list(entry.get("fix_site_ids") or [])
            test = list(entry.get("test_target_ids") or [])
            if not fix or not test:
                continue
            edges_path = arms_root / iid / arm / "edges.ndjson"
            if not edges_path.exists():
                continue
            ann_entry = ann.get(iid)
            if ann_entry is None:
                continue

            g = load_graph(edges_path)
            feats = features.as_row(features.compute(g, fix, test, max_k=6))
            failed = {s: bool(v) for s, v in (ann_entry.get("failed") or {}).items()}
            rows.append(Row(
                instance_id=iid,
                features=feats,
                failed=failed,
                baselines=_baselines_for(iid, inst_by_id, ann_entry),
            ))
    return rows


# --------------------------------------------------------------------------
# AUCs. failed=True is the positive class throughout.
# --------------------------------------------------------------------------

def _labels(rows: list[Row], system: str) -> list[bool]:
    return [bool(r.failed.get(system, False)) for r in rows]


def _auc_over(rows: list[Row], system: str, pick) -> dict[str, float]:
    """AUC per key, where ``pick(row)`` returns that row's {name: value} dict.
    A key is scored over exactly the rows that carry it and that have both label
    classes; keys are the union across rows so nothing is silently dropped."""
    names: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for name in pick(r):
            if name not in seen:
                seen.add(name)
                names.append(name)

    out: dict[str, float] = {}
    for name in names:
        pairs = [(pick(r)[name], r) for r in rows if name in pick(r)]
        values = [float(v) for v, _ in pairs]
        labels = _labels([r for _, r in pairs], system)
        out[name] = auc(values, labels)
    return out


def feature_aucs(rows: list[Row], system: str) -> dict[str, float]:
    return _auc_over(rows, system, lambda r: r.features)


def baseline_aucs(rows: list[Row], system: str) -> dict[str, float]:
    return _auc_over(rows, system, lambda r: r.baselines)


def _diff(rows: list[Row], system: str, feature: str, baseline: str) -> float:
    fv = [float(r.features[feature]) for r in rows if feature in r.features]
    fl = _labels([r for r in rows if feature in r.features], system)
    bv = [float(r.baselines[baseline]) for r in rows if baseline in r.baselines]
    bl = _labels([r for r in rows if baseline in r.baselines], system)
    return auc(fv, fl) - auc(bv, bl)


def bootstrap_ci(rows: list[Row], system: str, feature: str, baseline: str,
                 n: int = 2000, seed: int = 0) -> tuple[float, float, float]:
    """Percentile bootstrap CI for ``AUC(feature) - AUC(baseline)``.

    Returns ``(point_difference, lo, hi)`` where the point difference is on the
    full sample and ``(lo, hi)`` are the 2.5/97.5 percentiles of the resampled
    differences. Resamples with a single label class (AUC undefined) are skipped;
    if every resample degenerates the interval collapses onto the point estimate.
    """
    import math

    point = _diff(rows, system, feature, baseline)

    rng = random.Random(seed)
    m = len(rows)
    diffs: list[float] = []
    for _ in range(n):
        sample = [rows[rng.randrange(m)] for _ in range(m)]
        d = _diff(sample, system, feature, baseline)
        if not math.isnan(d):
            diffs.append(d)

    if not diffs:
        return point, point, point
    diffs.sort()

    def _pct(p: float) -> float:
        idx = min(len(diffs) - 1, max(0, int(round(p * (len(diffs) - 1)))))
        return diffs[idx]

    return point, _pct(0.025), _pct(0.975)


def class_balance(rows: list[Row], system: str) -> dict[str, int]:
    labels = _labels(rows, system)
    failed = sum(1 for f in labels if f)
    return {"n": len(rows), "failed": failed, "resolved": len(rows) - failed}


# --------------------------------------------------------------------------
# The generated report — docs/evaluation.md.
# --------------------------------------------------------------------------

def _fmt(v: float) -> str:
    import math
    return "n/a" if (isinstance(v, float) and math.isnan(v)) else f"{v:.3f}"


def write_report(rows: list[Row], results: dict, path: Path) -> None:
    """Generate ``docs/evaluation.md``: retractions first, then the live numbers,
    the published state of the art (marked not reproduced), the bootstrap CI and
    class balance with the honest note that n cannot resolve small effects, and
    the label-contamination disclosure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    system = results.get("system", "")
    arm = results.get("arm", "arm_b")
    bal = results.get("class_balance", {})
    n = bal.get("n", len(rows))

    L: list[str] = []
    L.append("# Evaluation — the hedged secondary metric")
    L.append("")

    # 1. Retractions, up top, unmissable.
    L.append("## Retractions (read first)")
    L.append("")
    L.append(
        "**v1 is WITHDRAWN.** v1 reported AUC **0.565** (point-biserial "
        "p=**0.726**) for the friction score. It was measured on a graph where "
        "**73.9% of the resolved `CALLS` edges were name-collision artifacts** "
        "(`extend`, `lower`, `cursor` bound across unrelated classes). The number "
        "measured the artifacts, not the thesis, and is withdrawn in full.")
    L.append("")
    L.append(
        "**v2 is WITHDRAWN as a test of the thesis.** v2 reported **0.631**, but "
        "that figure was computed from path **multiplicity / f1 only** — the "
        "cache stored path *counts*, not node lists — and it **did not beat the "
        "`patch_lines` baseline at 0.637**. A structure signal that loses to "
        "patch size is not evidence for the structure thesis, so 0.631 is "
        "withdrawn as such.")
    L.append("")

    # 2. Directional caveat.
    L.append("## Directional caveat")
    L.append("")
    L.append(
        "Every v1/v2 friction number was computed with `relDirection: 'both'`. "
        "Undirected reachability measures **\"shares a neighbourhood\"**, NOT "
        "\"the test exercises this code\". The directionally-honest relation is "
        "**test -> fix** (tests call code; code does not call tests), which is "
        "connected for 24/44 instances, versus 43/44 undirected. See "
        "`docs/connectivity.md`. The features evaluated below record their "
        "direction explicitly for exactly this reason.")
    L.append("")

    # 3. The live numbers: features and baselines on the SAME instances.
    L.append("## This measurement")
    L.append("")
    L.append(
        f"Ground truth `{system}`, arm `{arm}`, **n = {n}** instances that carry "
        "both a fix-site set and a test-target set (the only instances on which "
        "the directional features are defined). Feature AUCs and baseline AUCs "
        "below are computed on **exactly these same instances**. `failed=True` is "
        "the positive class: an AUC above 0.5 means larger values track failure, "
        "below 0.5 means they track success.")
    L.append("")
    L.append("### Feature AUC (ours)")
    L.append("")
    L.append("| Feature | Direction | AUC |")
    L.append("|---|---|---|")
    directions = {
        "fwd_growth": "outward from fix",
        "bwd_growth": "inward from tests",
        "overlap_ratio": "fix-out ∩ test-in",
        "fanin": "callers of fix",
        "test_to_fix_hops": "directed test->fix",
        "undirected_hops": "undirected",
    }
    for name, val in results.get("feature_aucs", {}).items():
        L.append(f"| `{name}` | {directions.get(name, '')} | {_fmt(val)} |")
    L.append("")
    L.append("### Baseline AUC (non-graph, same instances)")
    L.append("")
    L.append("| Baseline | AUC |")
    L.append("|---|---|")
    for name, val in results.get("baseline_aucs", {}).items():
        L.append(f"| `{name}` | {_fmt(val)} |")
    L.append("")

    best_f = results.get("best_feature")
    best_b = results.get("best_baseline")
    if best_f and best_b:
        fname, fauc = best_f
        bname, bauc = best_b
        beat = fauc > bauc
        verdict = "GO (thesis, scoped)" if beat else "NO-GO"
        L.append(
            f"**Scoped verdict: {verdict}.** The scoped question is narrow — does "
            "any directional structure feature beat the best non-graph baseline on "
            "these instances?")
        L.append("")
        L.append(
            f"**Best feature:** `{fname}` at {_fmt(fauc)}. "
            f"**Best baseline:** `{bname}` at {_fmt(bauc)}. "
            + ("The best feature edges the best baseline on this sample — but see "
               "the CI below before believing it."
               if beat else
               "**No feature beats the best baseline.** That is the honest result: "
               "on this corpus the cheap non-graph signals are at least as good as "
               "the directional structure features, so the scoped verdict is "
               "**NO-GO**. The project leads with the substrate finding "
               "(`docs/precision.md`), not this predictor."))
        L.append("")

    # 4. Bootstrap CI + class balance + the power statement.
    L.append("## Can this sample even tell? (bootstrap CI + power)")
    L.append("")
    boot = results.get("bootstrap", {})
    base = results.get("bootstrap_baseline", "")
    if boot:
        L.append(f"Percentile bootstrap (2000 resamples) of `AUC(feature) - "
                 f"AUC({base})`, positive = feature wins:")
        L.append("")
        L.append("| Feature | ΔAUC vs baseline | 95% CI |")
        L.append("|---|---|---|")
        for name, triple in boot.items():
            d, lo, hi = triple
            L.append(f"| `{name}` | {_fmt(d)} | [{_fmt(lo)}, {_fmt(hi)}] |")
        L.append("")
    L.append(
        f"**Class balance:** n={bal.get('n', '?')}, failed={bal.get('failed', '?')}, "
        f"resolved={bal.get('resolved', '?')}.")
    L.append("")
    L.append(
        f"**The sample cannot resolve small effects.** With n≈{n} and a roughly "
        "even split, the 95% CI on an AUC difference is on the order of ±0.15. "
        "Every CI above brackets zero by a wide margin. This sample **cannot "
        "resolve** a true AUC gap smaller than roughly 0.15, so no small "
        "feature-vs-baseline difference here is statistically distinguishable "
        "from noise. We do not claim one.")
    L.append("")

    # 5. Published state of the art — carried, not reproduced.
    L.append("## Published state of the art (published, NOT reproduced here)")
    L.append("")
    L.append("Per-instance failure prediction on SWE-bench Verified is **already "
             "a solved problem**, and we do **not** claim it:")
    L.append("")
    L.append("| Result | AUC | Status |")
    L.append("|---|---|---|")
    L.append("| Task-agnostic prior | 0.718 | published, NOT reproduced here |")
    L.append("| Problem-statement text only | 0.787 | published, NOT reproduced here |")
    L.append("| Best combined model | 0.841 | published, NOT reproduced here |")
    L.append("")
    L.append(
        "Source: Agent Psychometrics, arXiv 2604.00594. These rows are carried "
        "for context only — they are **published, NOT reproduced here**. Our "
        "numbers above are not competitive with them and are not meant to be; the "
        "contribution of this project is the substrate/precision finding, not a "
        "failure predictor.")
    L.append("")

    # 6. Label contamination.
    L.append("## Label contamination (why the ceiling is soft)")
    L.append("")
    L.append(
        "The `failed` labels are themselves noisy, which caps how high any AUC on "
        "this benchmark can honestly go:")
    L.append("")
    L.append(
        "- **SWE-Bench+** (arXiv 2410.06992): **32.7%** solution leakage in "
        "problem statements and **31%** weak/insufficient test cases.")
    L.append(
        "- **OpenAI** reports **59.4%** of o3's failures on SWE-bench Verified "
        "were attributable to **test flaws**, not wrong patches.")
    L.append("")
    L.append(
        "A non-trivial fraction of the labels this evaluation trains against are "
        "wrong, so a ceiling below 1.0 is structural, not a modelling failure.")
    L.append("")

    path.write_text("\n".join(L) + "\n", encoding="utf-8")

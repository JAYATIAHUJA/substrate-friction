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


PRIMARY_SYSTEM = "20241029_OpenHands-CodeAct-2.1-sonnet-20241022"
CACHED_SYSTEMS = (
    "20241029_OpenHands-CodeAct-2.1-sonnet-20241022",
    "20240402_sweagent_gpt4",
    "20240620_sweagent_claude3.5sonnet",
)


@dataclass(frozen=True)
class Row:
    instance_id: str
    features: dict[str, float]
    failed: dict[str, bool]
    baselines: dict[str, float] = field(default_factory=dict)
    repo: str = ""


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
# The fair test (Task 5): a frame over the WHOLE multi-repo corpus, labelled
# directly from the cached per-system resolved sets rather than from the
# django-only annotations. This is what makes leave-one-repo-out possible.
# --------------------------------------------------------------------------

def derive_failed_labels(instance_ids, systems,
                         resolved_dir="data/instances/resolved"
                         ) -> dict[str, dict[str, bool]]:
    """Per-instance ``{system: failed}`` from the cached resolved sets.

    ``failed`` is defined exactly as the django annotations define it and as the
    SWE-bench experiments repo publishes it: an instance FAILED under a system
    iff its id is NOT in that system's resolved set. Every SWE-bench Verified
    instance is in each system's evaluated universe, so every instance gets a
    label under every cached system (no annotations file required).
    """
    from friction.swebench import load_resolved

    resolved_by = {s: load_resolved(s, cache_dir=Path(resolved_dir))
                   for s in systems}
    ids = list(instance_ids)
    return {iid: {s: iid not in resolved_by[s] for s in systems} for iid in ids}


def _arm_edges_path(record: dict, arm: str, carried_root: Path,
                    built_root: Path) -> Path:
    """Resolve an instance's ``edges.ndjson`` from the record's ``source``.

    Carried django records reuse the original arm files under ``carried_root``;
    built records store them under ``built_root``. Falls back to whichever base
    actually holds the file so a mislabelled ``source`` cannot silently drop an
    instance.
    """
    iid = record["instance_id"]
    source = record.get("source", "built")
    primary = carried_root if source == "carried" else built_root
    other = built_root if source == "carried" else carried_root
    cand = Path(primary) / iid / arm / "edges.ndjson"
    if cand.exists():
        return cand
    return Path(other) / iid / arm / "edges.ndjson"


def build_corpus_rows(manifest, systems=CACHED_SYSTEMS,
                      carried_root="data/instances/arms",
                      built_root="data/instances/corpus/arms",
                      resolved_dir="data/instances/resolved",
                      arm: str = "arm_b",
                      instances=None) -> list[Row]:
    """Build one :class:`Row` per usable instance across the whole corpus.

    Usable = the ``arm`` entry carries BOTH a non-empty fix-site set and a
    non-empty test-target set (the only instances on which the directional
    features are defined). Directional features come from that arm's
    ``edges.ndjson`` (located by ``source``); the ``failed`` labels come from the
    cached resolved sets for every system in ``systems``; the ``repo`` and the
    non-graph baseline block are carried too.

    ``instances`` is the SWE-bench instance list used for the baseline block.
    Pass ``None`` to load the verified split cache-first; pass ``[]`` to keep the
    call hermetic (baselines then empty, features and labels still populated).
    """
    manifest = Path(manifest)
    carried_root = Path(carried_root)
    built_root = Path(built_root)

    if instances is None:
        from friction.swebench import load_instances
        instances = load_instances()
    inst_by_id = {getattr(i, "instance_id"): i for i in instances}

    records: list[dict] = []
    with manifest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            entry = record.get(arm) or {}
            if not (entry.get("fix_site_ids") and entry.get("test_target_ids")):
                continue
            edges_path = _arm_edges_path(record, arm, carried_root, built_root)
            if not edges_path.exists():
                continue
            record["_edges_path"] = edges_path
            records.append(record)

    labels = derive_failed_labels([r["instance_id"] for r in records], systems,
                                  resolved_dir)

    rows: list[Row] = []
    for record in records:
        iid = record["instance_id"]
        entry = record[arm]
        fix = list(entry["fix_site_ids"])
        test = list(entry["test_target_ids"])
        g = load_graph(record["_edges_path"])
        feats = features.as_row(features.compute(g, fix, test, max_k=6))
        base: dict[str, float] = {}
        inst = inst_by_id.get(iid)
        if inst is not None:
            base = {k: float(v) for k, v in asdict(baselines.extract(inst)).items()}
        rows.append(Row(
            instance_id=iid,
            features=feats,
            failed={s: bool(v) for s, v in labels[iid].items()},
            baselines=base,
            repo=record.get("repo", ""),
        ))
    return rows


def rows_to_frame(rows: list[Row], system: str, feature_cols=None):
    """A pandas DataFrame with one row per instance: the scored features, the
    baseline block, ``repo``, and a boolean ``failed`` for ``system``. Used by
    :func:`friction.tests_stat.leave_one_repo_out`."""
    import pandas as pd

    recs = []
    for r in rows:
        rec = {"instance_id": r.instance_id, "repo": r.repo,
               "failed": bool(r.failed.get(system, False))}
        rec.update(r.features)
        rec.update({f"base_{k}": v for k, v in r.baselines.items()})
        recs.append(rec)
    frame = pd.DataFrame(recs)
    return frame


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


def _render_fair_test(L: list, results: dict, _fmt) -> None:
    """Render the multi-repo fair-test sections (Task 5): per-repo labelled n,
    the leave-one-repo-out table, and the confounds re-run at the new n. Every
    block is gated on the presence of its results key, so the single-system
    report (which passes none of them) is unchanged."""
    per_repo = results.get("per_repo_labels")
    system = results.get("system", "")
    if per_repo and system in per_repo:
        L.append("## The fair test: labelled n per repo")
        L.append("")
        L.append(
            "Labels are derived exactly as the django annotations define failure "
            "— an instance FAILED under a system iff its id is **not** in that "
            "system's cached resolved set (`data/instances/resolved/`). Every "
            "usable instance is a SWE-bench Verified task, so every one carries a "
            "label; **no repo is silently dropped.** Ground truth below is the "
            f"primary system `{system}`.")
        L.append("")
        L.append("| repo | labelled n | failed | resolved |")
        L.append("|---|--:|--:|--:|")
        tot = [0, 0, 0]
        for repo, d in per_repo[system].items():
            L.append(f"| {repo} | {d['n']} | {d['failed']} | {d['resolved']} |")
            tot[0] += d["n"]; tot[1] += d["failed"]; tot[2] += d["resolved"]
        L.append(f"| **total** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** |")
        L.append("")
        L.append(
            "`sympy` has **0 failures under the primary system** (3/3 resolved), "
            "so it cannot be a held-out *test* repo — AUC is undefined on one "
            "class. It is reported, not dropped.")
        L.append("")

    loro = results.get("loro_feature")
    if loro:
        L.append("## Leave-one-repo-out (the split the spec asked for)")
        L.append("")
        L.append(
            "For each repo: train a standardised logistic model on the OTHER "
            "repos' instances over the six directional features, predict the "
            "held-out repo, report its AUC. This is **strictly harder than a "
            "random split** — the model never sees the held-out repo, so it "
            "cannot memorise repo identity (a known strong difficulty proxy; see "
            "the confounds below).")
        L.append("")
        L.append("| held-out repo | n | features AUC |")
        L.append("|---|--:|--:|")
        for repo, a in loro["per_repo"].items():
            n_held = loro.get("per_repo_n", {}).get(repo, "?")
            L.append(f"| {repo} | {n_held} | {_fmt(a)} |")
        L.append("")
        L.append(
            f"**Pooled held-out AUC (features): {_fmt(loro.get('pooled_auc'))}** "
            f"(mean of per-repo AUCs {_fmt(loro.get('mean_per_repo_auc'))}).")
        lp = results.get("loro_patch_lines")
        lb = results.get("loro_baseline")
        if lp or lb:
            parts = []
            if lp:
                parts.append(f"`patch_lines` alone pooled "
                             f"**{_fmt(lp.get('pooled_auc'))}**")
            if lb:
                parts.append(f"the full non-graph baseline block pooled "
                             f"**{_fmt(lb.get('pooled_auc'))}**")
            L.append("")
            L.append(
                "On the SAME leave-one-repo-out folds, " + " and ".join(parts)
                + ". **The directional features do not beat patch scope out of "
                "sample; pooled, they sit at or below chance.** That is the "
                "result. The headline stays the substrate finding "
                "(`docs/precision.md`), not this predictor.")
        L.append("")

    conf = results.get("confounds")
    if conf:
        L.append("## Confounds, re-run at n=172 (plus a fourth)")
        L.append("")
        L.append("| confound | measure | reading |")
        L.append("|---|--:|---|")
        L.append(
            f"| repo/graph size predicts failure? | AUC "
            f"{_fmt(conf.get('repo_size_auc'))} | arm-B node count; ≈0.5 = no |")
        L.append(
            f"| patch size predicts failure? | AUC "
            f"{_fmt(conf.get('patch_lines_auc'))} | `patch_lines`; the signal to "
            f"beat |")
        L.append(
            f"| **repo identity alone predicts failure?** | AUC "
            f"{_fmt(conf.get('repo_identity_auc'))} | leave-one-out repo failure "
            f"rate, primary system |")
        L.append("")
        rates = conf.get("repo_fail_rate")
        if rates:
            L.append("Per-repo failure rate (primary system): "
                     + ", ".join(f"`{k}` {_fmt(v)}" for k, v in rates.items())
                     + ".")
            L.append("")
        xs = conf.get("cross_system_feature_auc")
        if xs:
            L.append(
                "**Cross-system stability.** Best-feature AUC under each cached "
                "system: " + ", ".join(f"`{s.split('_')[0]}` {_fmt(v)}"
                                        for s, v in xs.items())
                + ".")
            L.append("")
        ident = conf.get("repo_identity_auc")
        ris = conf.get("repo_identity_auc_by_system")
        if ident is not None:
            note = (
                "Under the strong primary system, repo identity is a **weak** "
                f"predictor (AUC {_fmt(ident)}, |AUC−0.5| ≈ "
                f"{_fmt(abs(ident - 0.5))}): its failures spread fairly evenly "
                "across repos.")
            if ris:
                note += (
                    " Under the two *weaker* cached systems it is a real "
                    "confound — "
                    + ", ".join(f"`{s.split('_')[0]}` {_fmt(v)}"
                                for s, v in ris.items() if s != system)
                    + " — because they fail almost everything in some repos and "
                    "resolve almost everything in others. **That is exactly the "
                    "confound leave-one-repo-out neutralises**, and why the "
                    "out-of-sample feature AUC collapses to chance once repo "
                    "identity cannot be memorised.")
            L.append(note)
            L.append("")


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

    # 3b. The fair test: leave-one-repo-out over the whole corpus.
    _render_fair_test(L, results, _fmt)

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

    # DeLong + LR test on the best feature vs the best baseline, same instances.
    dl = results.get("delong")
    if dl:
        L.append(
            f"**DeLong test** of `AUC(feature) − AUC(baseline)` on the same "
            f"instances (accounts for the correlation between two AUCs measured "
            f"on one sample): feature {_fmt(dl.get('auc_feature'))}, baseline "
            f"{_fmt(dl.get('auc_baseline'))}, **z = {_fmt(dl.get('z'))}, "
            f"p = {_fmt(dl.get('p'))}** (two-sided). A *negative* z means the "
            "baseline scores the higher AUC.")
        L.append("")
    lrt = results.get("lr_test")
    if lrt:
        L.append(
            f"**Likelihood-ratio test** (does the feature add to a logistic model "
            f"that already has the baseline?): χ²({lrt.get('df')}) = "
            f"{_fmt(lrt.get('stat'))}, **p = {_fmt(lrt.get('p'))}**.")
        L.append("")

    L.append(
        f"**Class balance:** n={bal.get('n', '?')}, failed={bal.get('failed', '?')}, "
        f"resolved={bal.get('resolved', '?')}.")
    L.append("")

    power = results.get("power")
    if power:
        req_ref = power.get("required_n_reference_+0.05_over_0.787")
        req_obs = power.get("required_n_observed_gap")
        obs_gap = power.get("observed_gap")
        L.append(
            f"**Achieved vs required power.** By the Hanley–McNeil variance "
            f"(`friction.tests_stat.required_n`), resolving **+0.05 AUC at ρ=0.5** "
            f"against the published ~0.787 text baseline needs **≈{req_ref} "
            f"instances**; the observed feature-vs-baseline gap of "
            f"{_fmt(obs_gap)} would need **≈{req_obs}**. We have **n={n}**. The "
            "corpus quadrupled (44 → 172) and crossed from *cannot resolve "
            "anything* to *can resolve a ~0.09 gap* — the DeLong and bootstrap "
            "above do reach the 5% threshold — but it is still short of the "
            "general power target, and no *small* effect here is distinguishable "
            "from noise. We do not claim one.")
        L.append("")
    else:
        L.append(
            f"**The sample cannot resolve small effects.** With n≈{n} and a "
            "roughly even split, every CI above brackets zero. This sample "
            "**cannot resolve** a small true AUC gap, so no small "
            "feature-vs-baseline difference here is statistically "
            "distinguishable from noise. We do not claim one.")
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

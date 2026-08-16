"""Task 5 — the fair test: leave-one-repo-out over the whole 172-instance corpus.

Computes every number the completion plan's Task 5 asks for and writes a machine
-readable results blob to scratch, plus regenerates docs/evaluation.md via
friction.evaluate4.write_report. Run: uv run python scripts/run_fair_test.py
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from friction import evaluate4, tests_stat
from friction.evaluate import auc
from friction.evaluate4 import CACHED_SYSTEMS, PRIMARY_SYSTEM

MANIFEST = Path("data/instances/corpus/manifest.jsonl")
RESOLVED = Path("data/instances/resolved")
FEATURE_NAMES = ("fwd_growth", "bwd_growth", "overlap_ratio", "fanin",
                 "test_to_fix_hops", "undirected_hops")


def _nodes_by_id() -> dict[str, int]:
    out = {}
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[r["instance_id"]] = int(r.get("arm_b", {}).get("nodes", 0))
    return out


def main() -> None:
    print("Building corpus rows over all usable instances ...")
    rows = evaluate4.build_corpus_rows(MANIFEST, systems=CACHED_SYSTEMS,
                                       resolved_dir=RESOLVED)
    print(f"  built {len(rows)} rows")
    nodes = _nodes_by_id()

    # ---- 1. labelled n per repo, per system ------------------------------
    per_repo_labels = {}
    for sysname in CACHED_SYSTEMS:
        d = defaultdict(lambda: [0, 0])
        for r in rows:
            d[r.repo][0] += 1
            if r.failed.get(sysname):
                d[r.repo][1] += 1
        per_repo_labels[sysname] = {k: {"n": v[0], "failed": v[1],
                                        "resolved": v[0] - v[1]}
                                    for k, v in sorted(d.items())}

    # ---- 2. pooled feature AUCs + baseline AUCs (primary) ----------------
    feat_aucs = evaluate4.feature_aucs(rows, PRIMARY_SYSTEM)
    base_aucs = evaluate4.baseline_aucs(rows, PRIMARY_SYSTEM)
    # best by distance from 0.5 (a feature that tracks success is still signal),
    # but for the headline "beats baseline" comparison we use raw AUC>0.5 too.
    best_feature = max(feat_aucs.items(), key=lambda kv: kv[1])
    best_baseline = max(base_aucs.items(), key=lambda kv: kv[1])

    # ---- 3. leave-one-repo-out (features) --------------------------------
    frame = evaluate4.rows_to_frame(rows, PRIMARY_SYSTEM)
    loro_feat = tests_stat.leave_one_repo_out(frame, list(FEATURE_NAMES))
    base_cols = [c for c in frame.columns if c.startswith("base_")]
    loro_base = tests_stat.leave_one_repo_out(frame, base_cols)
    loro_patch = tests_stat.leave_one_repo_out(frame, ["base_patch_lines"])

    # ---- 4. confounds at the new n ---------------------------------------
    labels_primary = [r.failed.get(PRIMARY_SYSTEM, False) for r in rows]
    repo_size = [float(nodes.get(r.instance_id, 0)) for r in rows]
    patch_lines = [float(r.baselines.get("patch_lines", 0.0)) for r in rows]
    repo_size_auc = auc(repo_size, labels_primary)
    patch_lines_auc = auc(patch_lines, labels_primary)

    # cross-system stability: best feature AUC under each system + label agreement
    xsys_feat_auc = {s: evaluate4.feature_aucs(rows, s).get(best_feature[0])
                     for s in CACHED_SYSTEMS}
    # pairwise label agreement across systems
    agree = {}
    for i, s1 in enumerate(CACHED_SYSTEMS):
        for s2 in CACHED_SYSTEMS[i + 1:]:
            same = sum(1 for r in rows
                       if r.failed.get(s1) == r.failed.get(s2))
            agree[f"{s1}|{s2}"] = same / len(rows)

    # repo identity as a predictor: leave-one-instance-out repo failure rate
    repo_fail = defaultdict(lambda: [0, 0])  # repo -> [failed, total]
    for r in rows:
        repo_fail[r.repo][1] += 1
        if r.failed.get(PRIMARY_SYSTEM):
            repo_fail[r.repo][0] += 1
    repo_rate = {k: v[0] / v[1] for k, v in repo_fail.items()}
    # leave-one-out score for each instance = repo rate excluding this instance
    ident_scores = []
    for r in rows:
        f, t = repo_fail[r.repo]
        yi = 1 if r.failed.get(PRIMARY_SYSTEM) else 0
        loo = (f - yi) / (t - 1) if t > 1 else f / t
        ident_scores.append(loo)
    repo_identity_auc = auc(ident_scores, labels_primary)

    # repo identity as a predictor under EVERY cached system (it is a confound
    # for the weaker systems — the reason the split exists).
    repo_identity_by_system = {}
    for sysname in CACHED_SYSTEMS:
        rf = defaultdict(lambda: [0, 0])
        for r in rows:
            rf[r.repo][1] += 1
            if r.failed.get(sysname):
                rf[r.repo][0] += 1
        sc, lb = [], []
        for r in rows:
            fcnt, tcnt = rf[r.repo]
            yi = 1 if r.failed.get(sysname) else 0
            sc.append((fcnt - yi) / (tcnt - 1) if tcnt > 1 else fcnt / tcnt)
            lb.append(bool(r.failed.get(sysname)))
        repo_identity_by_system[sysname] = auc(sc, lb)

    # ---- 5. DeLong + bootstrap on best feature vs best baseline ----------
    fvals = [r.features[best_feature[0]] for r in rows]
    bvals = [r.baselines[best_baseline[0]] for r in rows]
    delong = tests_stat.delong_test(labels_primary, fvals, bvals)
    boot_point, boot_lo, boot_hi = evaluate4.bootstrap_ci(
        rows, PRIMARY_SYSTEM, best_feature[0], best_baseline[0], n=2000, seed=0)
    lr = tests_stat.lr_test(labels_primary, base=[bvals], full=[bvals, fvals])

    # ---- 6. power --------------------------------------------------------
    # required n to resolve the observed |feature - baseline| gap at rho=0.5,
    # and the plan's reference (+0.05 over the published 0.787 text baseline).
    obs_gap = abs(best_feature[1] - best_baseline[1])
    req_observed = (tests_stat.required_n(best_baseline[1], best_feature[1], 0.5)
                    if obs_gap > 0 else None)
    req_reference = tests_stat.required_n(0.787, 0.837, 0.5)

    results = {
        "n": len(rows),
        "system": PRIMARY_SYSTEM,
        "arm": "arm_b",
        "per_repo_labels": per_repo_labels,
        "feature_aucs": feat_aucs,
        "baseline_aucs": base_aucs,
        "best_feature": list(best_feature),
        "best_baseline": list(best_baseline),
        "loro_feature": loro_feat,
        "loro_baseline": loro_base,
        "loro_patch_lines": loro_patch,
        "confounds": {
            "repo_size_auc": repo_size_auc,
            "patch_lines_auc": patch_lines_auc,
            "repo_identity_auc": repo_identity_auc,
            "repo_identity_auc_by_system": repo_identity_by_system,
            "repo_fail_rate": repo_rate,
            "cross_system_feature_auc": xsys_feat_auc,
            "cross_system_label_agreement": agree,
        },
        "delong": {
            "auc_feature": delong.auc_a, "auc_baseline": delong.auc_b,
            "z": delong.z, "p": delong.p,
        },
        "lr_test": {"stat": lr.stat, "df": lr.df, "p": lr.p},
        "bootstrap": {best_feature[0]: (boot_point, boot_lo, boot_hi)},
        "bootstrap_baseline": best_baseline[0],
        "power": {
            "observed_gap": obs_gap,
            "required_n_observed_gap": req_observed,
            "required_n_reference_+0.05_over_0.787": req_reference,
        },
        "class_balance": {
            "n": len(rows),
            "failed": sum(1 for f in labels_primary if f),
            "resolved": sum(1 for f in labels_primary if not f),
        },
    }

    out = Path("/private/tmp/claude-501/-Users-cruzer-Desktop-Hackathon/"
               "60b45b25-ec97-4c90-a007-eefe363648c5/scratchpad/fair_test.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nWrote {out}\n")

    # Regenerate docs/evaluation.md from the same results.
    evaluate4.write_report(rows, results, Path("docs/evaluation.md"))
    print("Regenerated docs/evaluation.md")

    # human-readable dump
    def f(x):
        return "n/a" if (isinstance(x, float) and math.isnan(x)) else (
            f"{x:.3f}" if isinstance(x, float) else str(x))

    print("=== labelled n per repo (primary system) ===")
    for repo, d in per_repo_labels[PRIMARY_SYSTEM].items():
        print(f"  {repo:11s} n={d['n']:3d} failed={d['failed']:3d} "
              f"resolved={d['resolved']:3d}")
    print(f"\nclass balance: {results['class_balance']}")
    print("\n=== pooled feature AUCs (primary) ===")
    for k, v in sorted(feat_aucs.items(), key=lambda kv: -kv[1]):
        print(f"  {k:18s} {f(v)}")
    print("=== pooled baseline AUCs (primary) ===")
    for k, v in sorted(base_aucs.items(), key=lambda kv: -kv[1]):
        print(f"  {k:22s} {f(v)}")
    print(f"\nbest_feature = {best_feature[0]} {f(best_feature[1])} | "
          f"best_baseline = {best_baseline[0]} {f(best_baseline[1])}")
    print("\n=== leave-one-repo-out (features) ===")
    for repo, a in loro_feat["per_repo"].items():
        print(f"  {repo:11s} heldout_n={loro_feat['per_repo_n'][repo]:3d} "
              f"AUC={f(a)}")
    print(f"  pooled AUC          = {f(loro_feat['pooled_auc'])}")
    print(f"  mean per-repo AUC   = {f(loro_feat['mean_per_repo_auc'])}")
    print(f"  LORO baseline block pooled AUC = {f(loro_base['pooled_auc'])}")
    print(f"  LORO patch_lines pooled AUC    = {f(loro_patch['pooled_auc'])}")
    print("\n=== confounds ===")
    print(f"  repo_size_auc      = {f(repo_size_auc)}")
    print(f"  patch_lines_auc    = {f(patch_lines_auc)}")
    print(f"  repo_identity_auc  = {f(repo_identity_auc)}  (LOO repo failure rate)")
    print(f"  per-repo failure rate: "
          + ", ".join(f"{k}={f(v)}" for k, v in repo_rate.items()))
    print(f"  cross-system best-feature AUC: "
          + ", ".join(f"{s.split('_')[0]}={f(v)}"
                      for s, v in xsys_feat_auc.items()))
    print(f"  cross-system label agreement: "
          + ", ".join(f"{k.split('|')[0].split('_')[0]}~"
                      f"{k.split('|')[1].split('_')[0]}={f(v)}"
                      for k, v in agree.items()))
    print("\n=== DeLong (best feature vs best baseline) ===")
    print(f"  AUC feature={f(delong.auc_a)} baseline={f(delong.auc_b)} "
          f"z={f(delong.z)} p={f(delong.p)}")
    print(f"  LR test: stat={f(lr.stat)} df={lr.df} p={f(lr.p)}")
    print(f"  bootstrap ΔAUC(feature-baseline) = {f(boot_point)} "
          f"[{f(boot_lo)}, {f(boot_hi)}]")
    print("\n=== power ===")
    print(f"  observed gap = {f(obs_gap)}  required n = {req_observed}")
    print(f"  reference (+0.05 over 0.787, rho=0.5) required n = {req_reference}")
    print(f"  actual n = {len(rows)}")


if __name__ == "__main__":
    main()

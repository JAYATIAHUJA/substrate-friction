# Evaluation — the hedged secondary metric

## Retractions (read first)

**v1 is WITHDRAWN.** v1 reported AUC **0.565** (point-biserial p=**0.726**) for the friction score. It was measured on a graph where **73.9% of the resolved `CALLS` edges were name-collision artifacts** (`extend`, `lower`, `cursor` bound across unrelated classes). The number measured the artifacts, not the thesis, and is withdrawn in full.

**v2 is WITHDRAWN as a test of the thesis.** v2 reported **0.631**, but that figure was computed from path **multiplicity / f1 only** — the cache stored path *counts*, not node lists — and it **did not beat the `patch_lines` baseline at 0.637**. A structure signal that loses to patch size is not evidence for the structure thesis, so 0.631 is withdrawn as such.

## Directional caveat

Every v1/v2 friction number was computed with `relDirection: 'both'`. Undirected reachability measures **"shares a neighbourhood"**, NOT "the test exercises this code". The directionally-honest relation is **test -> fix** (tests call code; code does not call tests), which is connected for 24/44 instances, versus 43/44 undirected. See `docs/connectivity.md`. The features evaluated below record their direction explicitly for exactly this reason.

## This measurement

Ground truth `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`, arm `arm_b`, **n = 172** instances that carry both a fix-site set and a test-target set (the only instances on which the directional features are defined). Feature AUCs and baseline AUCs below are computed on **exactly these same instances**. `failed=True` is the positive class: an AUC above 0.5 means larger values track failure, below 0.5 means they track success.

### Feature AUC (ours)

| Feature | Direction | AUC |
|---|---|---|
| `fwd_growth` | outward from fix | 0.481 |
| `bwd_growth` | inward from tests | 0.462 |
| `overlap_ratio` | fix-out ∩ test-in | 0.500 |
| `fanin` | callers of fix | 0.567 |
| `test_to_fix_hops` | directed test->fix | 0.513 |
| `undirected_hops` | undirected | 0.520 |

### Baseline AUC (non-graph, same instances)

| Baseline | AUC |
|---|---|
| `patch_lines` | 0.656 |
| `patch_files` | 0.541 |
| `patch_hunks` | 0.613 |
| `f2p_count` | 0.568 |
| `statement_chars` | 0.600 |
| `statement_has_traceback` | 0.494 |

**Scoped verdict: NO-GO.** The scoped question is narrow — does any directional structure feature beat the best non-graph baseline on these instances?

**Best feature:** `fanin` at 0.567. **Best baseline:** `patch_lines` at 0.656. **No feature beats the best baseline.** That is the honest result: on this corpus the cheap non-graph signals are at least as good as the directional structure features, so the scoped verdict is **NO-GO**. The project leads with the substrate finding (`docs/precision.md`), not this predictor.

## The fair test: labelled n per repo

Labels are derived exactly as the django annotations define failure — an instance FAILED under a system iff its id is **not** in that system's cached resolved set (`data/instances/resolved/`). Every usable instance is a SWE-bench Verified task, so every one carries a label; **no repo is silently dropped.** Ground truth below is the primary system `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`.

| repo | labelled n | failed | resolved |
|---|--:|--:|--:|
| django | 44 | 21 | 23 |
| matplotlib | 33 | 16 | 17 |
| pytest | 19 | 10 | 9 |
| requests | 8 | 4 | 4 |
| sphinx | 44 | 26 | 18 |
| sympy | 3 | 0 | 3 |
| xarray | 21 | 9 | 12 |
| **total** | **172** | **86** | **86** |

`sympy` has **0 failures under the primary system** (3/3 resolved), so it cannot be a held-out *test* repo — AUC is undefined on one class. It is reported, not dropped.

## Leave-one-repo-out (the split the spec asked for)

For each repo: train a standardised logistic model on the OTHER repos' instances over the six directional features, predict the held-out repo, report its AUC. This is **strictly harder than a random split** — the model never sees the held-out repo, so it cannot memorise repo identity (a known strong difficulty proxy; see the confounds below).

| held-out repo | n | features AUC |
|---|--:|--:|
| django | 44 | 0.494 |
| matplotlib | 33 | 0.474 |
| pytest | 19 | 0.444 |
| requests | 8 | 0.688 |
| sphinx | 44 | 0.551 |
| sympy | 3 | n/a |
| xarray | 21 | 0.620 |

**Pooled held-out AUC (features): 0.483** (mean of per-repo AUCs 0.545).

On the SAME leave-one-repo-out folds, `patch_lines` alone pooled **0.628** and the full non-graph baseline block pooled **0.599**. **The directional features do not beat patch scope out of sample; pooled, they sit at or below chance.** That is the result. The headline stays the substrate finding (`docs/precision.md`), not this predictor.

## Confounds, re-run at n=172 (plus a fourth)

| confound | measure | reading |
|---|--:|---|
| repo/graph size predicts failure? | AUC 0.487 | arm-B node count; ≈0.5 = no |
| patch size predicts failure? | AUC 0.656 | `patch_lines`; the signal to beat |
| **repo identity alone predicts failure?** | AUC 0.382 | leave-one-out repo failure rate, primary system |

Per-repo failure rate (primary system): `django` 0.477, `sphinx` 0.591, `sympy` 0.000, `matplotlib` 0.485, `requests` 0.500, `pytest` 0.526, `xarray` 0.429.

**Cross-system stability.** Best-feature AUC under each cached system: `20241029` 0.567, `20240402` 0.586, `20240620` 0.477.

Under the strong primary system, repo identity is a **weak** predictor (AUC 0.382, |AUC−0.5| ≈ 0.118): its failures spread fairly evenly across repos. Under the two *weaker* cached systems it is a real confound — `20240402` 0.596, `20240620` 0.613 — because they fail almost everything in some repos and resolve almost everything in others. **That is exactly the confound leave-one-repo-out neutralises**, and why the out-of-sample feature AUC collapses to chance once repo identity cannot be memorised.

## Can this sample even tell? (bootstrap CI + power)

Percentile bootstrap (2000 resamples) of `AUC(feature) - AUC(patch_lines)`, positive = feature wins:

| Feature | ΔAUC vs baseline | 95% CI |
|---|---|---|
| `fanin` | -0.089 | [-0.178, -0.003] |

**DeLong test** of `AUC(feature) − AUC(baseline)` on the same instances (accounts for the correlation between two AUCs measured on one sample): feature 0.567, baseline 0.656, **z = -1.996, p = 0.046** (two-sided). A *negative* z means the baseline scores the higher AUC.

**Likelihood-ratio test** (does the feature add to a logistic model that already has the baseline?): χ²(1) = 2.566, **p = 0.109**.

**Class balance:** n=172, failed=86, resolved=86.

**Achieved vs required power.** By the Hanley–McNeil variance (`friction.tests_stat.required_n`), resolving **+0.05 AUC at ρ=0.5** against the published ~0.787 text baseline needs **≈584 instances**; the observed feature-vs-baseline gap of 0.089 would need **≈310**. We have **n=172**. The corpus quadrupled (44 → 172) and crossed from *cannot resolve anything* to *can resolve a ~0.09 gap* — the DeLong and bootstrap above do reach the 5% threshold — but it is still short of the general power target, and no *small* effect here is distinguishable from noise. We do not claim one.

## Published state of the art (published, NOT reproduced here)

Per-instance failure prediction on SWE-bench Verified is **already a solved problem**, and we do **not** claim it:

| Result | AUC | Status |
|---|---|---|
| Task-agnostic prior | 0.718 | published, NOT reproduced here |
| Problem-statement text only | 0.787 | published, NOT reproduced here |
| Best combined model | 0.841 | published, NOT reproduced here |

Source: Agent Psychometrics, arXiv 2604.00594. These rows are carried for context only — they are **published, NOT reproduced here**. Our numbers above are not competitive with them and are not meant to be; the contribution of this project is the substrate/precision finding, not a failure predictor.

## Label contamination (why the ceiling is soft)

The `failed` labels are themselves noisy, which caps how high any AUC on this benchmark can honestly go:

- **SWE-Bench+** (arXiv 2410.06992): **32.7%** solution leakage in problem statements and **31%** weak/insufficient test cases.
- **OpenAI** reports **59.4%** of o3's failures on SWE-bench Verified were attributable to **test flaws**, not wrong patches.

A non-trivial fraction of the labels this evaluation trains against are wrong, so a ceiling below 1.0 is structural, not a modelling failure.


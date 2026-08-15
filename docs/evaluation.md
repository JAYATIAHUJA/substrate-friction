# Evaluation — the hedged secondary metric

## Retractions (read first)

**v1 is WITHDRAWN.** v1 reported AUC **0.565** (point-biserial p=**0.726**) for the friction score. It was measured on a graph where **73.9% of the resolved `CALLS` edges were name-collision artifacts** (`extend`, `lower`, `cursor` bound across unrelated classes). The number measured the artifacts, not the thesis, and is withdrawn in full.

**v2 is WITHDRAWN as a test of the thesis.** v2 reported **0.631**, but that figure was computed from path **multiplicity / f1 only** — the cache stored path *counts*, not node lists — and it **did not beat the `patch_lines` baseline at 0.637**. A structure signal that loses to patch size is not evidence for the structure thesis, so 0.631 is withdrawn as such.

## Directional caveat

Every v1/v2 friction number was computed with `relDirection: 'both'`. Undirected reachability measures **"shares a neighbourhood"**, NOT "the test exercises this code". The directionally-honest relation is **test -> fix** (tests call code; code does not call tests), which is connected for 24/44 instances, versus 43/44 undirected. See `docs/connectivity.md`. The features evaluated below record their direction explicitly for exactly this reason.

## This measurement

Ground truth `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`, arm `arm_b`, **n = 44** instances that carry both a fix-site set and a test-target set (the only instances on which the directional features are defined). Feature AUCs and baseline AUCs below are computed on **exactly these same instances**. `failed=True` is the positive class: an AUC above 0.5 means larger values track failure, below 0.5 means they track success.

### Feature AUC (ours)

| Feature | Direction | AUC |
|---|---|---|
| `fwd_growth` | outward from fix | 0.436 |
| `bwd_growth` | inward from tests | 0.500 |
| `overlap_ratio` | fix-out ∩ test-in | 0.500 |
| `fanin` | callers of fix | 0.509 |
| `test_to_fix_hops` | directed test->fix | 0.518 |
| `undirected_hops` | undirected | 0.508 |

### Baseline AUC (non-graph, same instances)

| Baseline | AUC |
|---|---|
| `patch_lines` | 0.613 |
| `patch_files` | 0.573 |
| `patch_hunks` | 0.533 |
| `f2p_count` | 0.653 |
| `statement_chars` | 0.590 |
| `statement_has_traceback` | 0.528 |

**Scoped verdict: NO-GO.** The scoped question is narrow — does any directional structure feature beat the best non-graph baseline on these instances?

**Best feature:** `test_to_fix_hops` at 0.518. **Best baseline:** `f2p_count` at 0.653. **No feature beats the best baseline.** That is the honest result: on this corpus the cheap non-graph signals are at least as good as the directional structure features, so the scoped verdict is **NO-GO**. The project leads with the substrate finding (`docs/precision.md`), not this predictor.

## Can this sample even tell? (bootstrap CI + power)

Percentile bootstrap (2000 resamples) of `AUC(feature) - AUC(patch_lines)`, positive = feature wins:

| Feature | ΔAUC vs baseline | 95% CI |
|---|---|---|
| `fwd_growth` | -0.177 | [-0.446, 0.105] |
| `bwd_growth` | -0.113 | [-0.279, 0.052] |
| `overlap_ratio` | -0.113 | [-0.279, 0.052] |
| `fanin` | -0.104 | [-0.279, 0.078] |
| `test_to_fix_hops` | -0.095 | [-0.299, 0.113] |
| `undirected_hops` | -0.105 | [-0.355, 0.136] |

**Class balance:** n=44, failed=21, resolved=23.

**The sample cannot resolve small effects.** With n≈44 and a roughly even split, the 95% CI on an AUC difference is on the order of ±0.15. Every CI above brackets zero by a wide margin. This sample **cannot resolve** a true AUC gap smaller than roughly 0.15, so no small feature-vs-baseline difference here is statistically distinguishable from noise. We do not claim one.

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


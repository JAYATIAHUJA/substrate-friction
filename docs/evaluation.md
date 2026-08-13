# Evaluation

**Verdict: WEAK** — AUC 0.567 on n=43 instances, ground truth `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`.

Point-biserial r = 0.047 (p = 0.7668).

## Read this first: two verdicts, not one

This run separates a **substrate** question from a **science** question, because
they answer differently.

1. **Can the HydraDB engine compute the friction metric on real graphs?**
   **No — hard NO-GO.** At the metric's defined `maxLen=6`, `relDirection=both`,
   `algo.MSpaths` exceeds the engine's non-negotiable 29999 ms query timeout on
   **every** full-django graph (43/43 usable instances, even at 1 fix site × 1
   test target). The fidelity guard measured engine **recall = 0.000** against
   the networkx reference (0 engine paths vs 42,200 reference paths over 20
   instances). Raising `pathCount` to 50 and 100 does **not** help: the timeout
   is in traversal, not in the output budget, so a larger budget only adds work.
   See `docs/fidelity.md`.

2. **Does the friction metric itself predict agent failure?**
   The AUC/point-biserial/confound numbers below are computed from the
   **networkx reference path enumeration** — the identical bounded path set the
   metric is defined over, and the same set the fidelity guard treats as ground
   truth — precisely because the engine cannot return it. On that reference the
   composite is a **WEAK 0.567**, but the point-biserial correlation is
   **not statistically significant (r = 0.047, p = 0.77)**: this is, honestly, a
   near-null. The best single component (`f2`, mean fix→test path length) scores
   **0.648, beating the composite 0.567** — so the small amount of signal that
   exists lives in one component, not the blend, and it is still below the 0.65
   GO line. Held-out AUC (0.722) sits above train AUC (0.558) only because the
   30% split is 13 instances and is dominated by sampling noise; it is not
   evidence of a strong model.

   Reference enumeration was given the **same 30 s budget the engine had** and
   capped at 50,000 paths per instance for tractability; instances hitting the
   cap are flagged, and F1 (path multiplicity) on those is a lower bound.

**Net:** the substrate cannot deliver the product as designed, and even with a
perfect path oracle the metric's predictive signal is weak and not significant.
Direction is as hypothesised (higher friction → more failure) but the effect is
indistinguishable from zero.

## Per-component AUC

| Component | AUC |
|---|---|
| `f1` | 0.545 |
| `f2` | 0.648 |
| `f3` | 0.579 |
| `f4` | 0.450 |
| `f5` | 0.500 |
| `f6` | 0.518 |

If one component's AUC matches or beats the composite, that is the actual
finding and it is reported as such rather than buried under a blend.

## Weights

Fitted on a 70% train split, evaluated on the held-out 30%. Train AUC 0.558, held-out AUC 0.722.

| Component | Weight |
|---|---|
| `f1` | 0.344 |
| `f2` | 0.254 |
| `f3` | 0.269 |
| `f4` | 0.121 |
| `f5` | 0.000 |
| `f6` | 0.011 |

## Confound checks

| Check | Pearson r |
|---|---|
| friction vs repo loc | 0.014 |
| friction vs patch lines | 0.171 |

A high correlation with repo LOC would mean friction is a size proxy; a high
correlation with patch line count would mean it is a patch-size proxy. Both
are reported whether or not they flatter the result.

## Stability across systems

| System | AUC |
|---|---|
| `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` | 0.567 |
| `20240620_sweagent_claude3.5sonnet` | 0.693 |
| `20240402_sweagent_gpt4` | 0.570 |

A result that holds for only one published system is measuring that system's
quirks, not the code.

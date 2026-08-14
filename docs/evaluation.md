# Evaluation

## Read this first — the headline is a truncation artifact, and the null holds

- The engine was queried at **maxLen 6**, the metric's definition, for all **43** endpoint-bearing instances.
- It **completed** the friction query for **23** of them and **could not answer 20** — **16 hit the 29999 ms timeout** and **4 exhausted the memory pool** on the dense 6-hop traversal. Those 20 are recorded as ENGINE-UNANSWERED and are **not** back-filled from any reference.
- Of the 23 answered, 16 returned at least one path; the rest returned zero (fix and test disconnected within the subgraph).

**Equal-weights friction AUC over the 23 engine-answered instances = 0.780** (point-biserial r=0.428, p=0.0416). Taken alone this looks strong. **It is not a real result.** Two independent checks show it is an artifact of the engine's `pathCount = 20` truncation:

1. **Fidelity recall = 0.0264** — over the same instances the engine returned 1021 paths where the full networkx enumeration over the identical edge set finds 38720. The engine sees 2.6% of the paths (validity precision 1.0: the ones it does return are all real). The metric is defined over path multiplicity, so at 2.6% recall it is scoring truncation noise, not structure.
2. **Re-scoring the SAME 23 instances from the full reference enumeration (reference-derived, no pathCount cap) gives AUC 0.576** (r=0.119, p=0.587) — the signal collapses to a null. Same instances, same edges, same maxLen; the only thing removed is the truncation. And over **all 43 endpoint-bearing instances the reference gives AUC 0.565** (r=0.055, p=0.726), which reproduces the prior full-graph baseline (AUC ~0.567, a clean null) on the real substrate.

**Verdict: NO-GO.** The friction metric does not predict agent failure. The engine-computed 0.780 is a demonstrated `pathCount` truncation artifact; the truncation-free measurement on the identical data is a null (0.565, p=0.726). A null confirmed on the real engine substrate is the honest result, and it agrees with the prior reference baseline. Nothing was tuned, dropped, or reframed to move a number in either direction.

## Engine query latency

- Friction path query (`algo.MSpaths`, the metric-defining query), answered instances only: median **14614.5 ms**, p95 **29041.27 ms**, max **29948.75 ms** (n=23). This is the cost of computing friction for one instance, and it sits at the engine's 29999 ms ceiling.
- Fan-in query (`algo.SSpaths`, maxLen 1) is sub-second and never failed.
- All engine queries pooled: median **18.21 ms**, p95 **30011.13 ms**, max **30015.39 ms** (n=87). The low pooled median is the cheap fan-in queries; it does not represent the cost of the metric.

## Subgraph completeness

**pct_untruncated = 0%** (0/50). Every subgraph hit its node budget before completing 6 hops (hops_completed 3-5), so even a successful engine query traverses a partial neighborhood. This is the second truncation in the stack (budget truncation of the subgraph, on top of pathCount truncation of the result).

## Fidelity

### a. Engine vs reference on the SAME subgraph (pathCount truncation)

Over 22 answered instances with a fully-enumerable reference (1 excluded because the reference enumeration hit its cap): engine returned **1021** paths, the reference found **38720**. Overlap recall = **0.0264**, validity precision = **1.0**. Largest shortfall: `django__django-11740`. Recall this far below 0.9 is the fidelity guard firing: the metric as the engine computes it is pathCount-truncated and its correlation cannot be believed. See `docs/fidelity.md`.

### b. Engine-on-subgraph vs reference on the FULL graph (budget truncation)

Of **36** endpoint-bearing instances whose fix and test are connected within 6 hops in the FULL repo graph, the engine returned a path for only **16** (cohort connectivity recall **0.4444**) — the rest were lost to a timeout, an OOM, or a subgraph budget that dropped the connecting hop. Restricted to instances the engine actually answered, connectivity recall is **1.0** (16/16): when the query finishes, the budgeted subgraph did preserve the short connections. The cost of truncation is concentrated in the ~half of instances the engine cannot answer at all.

**Verdict: NO-GO** — friction score vs failure AUC **0.780** on n=23 engine-answered instances (ground truth `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`), but this is a pathCount truncation artifact (fidelity recall 0.0264); the truncation-free number is a null (0.565). Scored components are engine-derived; the 0.576/0.565 comparison figures are reference-derived and labelled as such.

## Per-component AUC (engine-answered instances)

| Component | AUC |
|---|---|
| `f1` | 0.606 |
| `f2` | 0.788 |
| `f3` | 0.799 |
| `f4` | 0.553 |
| `f5` | 0.500 |
| `f6` | 0.591 |

Best single component: **`f3`** (AUC 0.799). These per-component AUCs inherit the same pathCount-truncation artifact as the composite and should not be read as evidence on their own.

## Weights (fitted, train-only) 

Logistic fit on a 70% train split, evaluated on the held-out 30%. Train AUC 0.898, **held-out AUC 0.542** — with n=23 the fitted model does not generalise beyond chance, independent of the truncation issue.

| Component | Weight |
|---|---|
| `f1` | 0.282 |
| `f2` | 0.251 |
| `f3` | 0.295 |
| `f4` | 0.164 |
| `f5` | 0.000 |
| `f6` | 0.008 |

## Confound checks

| Check | Value |
|---|---|
| friction vs repo loc | -0.113 |
| friction vs patch lines | 0.379 |
| repo loc auc | 0.568 |
| patch lines auc | 0.640 |

friction-vs-repo-loc and friction-vs-patch-lines are Pearson correlations; the `*_auc` rows report whether repo LOC or patch size predict failure directly. Patch size predicts failure at AUC 0.640 on this subset — a plainer predictor than friction, and a reminder the answered subset is small and selected.

## Excluded / unanswered instances

- **20 engine-unanswered** (timeout/OOM at maxLen 6): not scored, not substituted. This is ~half the endpoint-bearing cohort; the answered set is therefore a sample selected for cheap traversability, and the headline AUC must be read in that light.
- **7 empty-endpoint** instances (an endpoint set is empty → zero friction by construction): 4 failed, 3 resolved.

| Set | AUC |
|---|---|
| engine-answered only (n=23) | 0.780 |
| + empty-endpoint at minimum friction (n=30) | 0.631 |

Adding the empty-endpoint instances back at minimum friction moves the engine number from 0.780 to 0.631; neither survives the fidelity check above.

## Stability across systems (engine-answered instances)

| System | AUC |
|---|---|
| `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` | 0.780 |
| `20240402_sweagent_gpt4` | 0.836 |
| `20240620_sweagent_claude3.5sonnet` | 0.770 |

The across-system agreement is on the same truncation-artifact substrate, so it shows the artifact is stable, not that the metric is.

## Reproducibility

Every number here is regenerated by `uv run python -m friction.harness` from `data/instances/subgraphs.json`, `data/instances/annotations.json`, the per-instance `subgraphs/<id>/edges.ndjson` and `graphs/<id>/edges.ndjson`, and the live engine (recorded to `data/instances/engine_cache.json`; `FRICTION_REQUERY=1` forces a fresh pass). No figure is hand-entered.

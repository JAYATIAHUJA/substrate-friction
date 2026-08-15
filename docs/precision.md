# What name matching costs

Arm A is a name-matched call graph, built the way the widely-used repo-graph tools (Aider, RepoGraph, LocAgent) build one. Arm B is type-resolved via `scip-python` (pyright). Same django commit, same definitions, joined into one node space by `friction.identity`. Every number in the measured table below is parsed from the committed `docs/graph-delta.md`, not recomputed here, so this page cannot drift from that report.

## Measured (ours, reproducible)

| Measure | Value |
|---|---|
| Arm A edges confirmed by arm B | **4381** |
| Arm A edges arm B does not have | **1492** |
| Arm B edges arm A missed | **8064** |
| Arm A edges compared (in scope) | **5873** |
| Arm A precision (ceiling) | **0.746** |
| Arm A recall of arm B | **0.352** |
| Jaccard | 0.3143 |

## Where arm A's unconfirmed edges point

These are container-method name collisions: `list.extend` bound to a GIS class, `str.lower` bound to `django.template.defaultfilters.lower`.

| Target name | Unconfirmed edges |
|---|---|
| `extend` | 139 |
| `lower` | 125 |
| `cursor` | 54 |
| `import_module` | 33 |
| `search` | 31 |
| `split_contents` | 29 |
| `fetchall` | 28 |
| `time` | 28 |
| `insert` | 24 |
| `compile_filter` | 23 |
| `db_manager` | 22 |
| `wraps` | 22 |
| `next` | 21 |
| `max` | 20 |
| `min` | 16 |
| `geodetic` | 15 |
| `get_compiler` | 14 |
| `order_by` | 14 |
| `quote` | 13 |
| `delete_first_token` | 13 |

## The ceiling is honest in both directions

Arm-A precision is reported as a **ceiling**, and the direction of the bias is stated both ways. pyright emits no occurrence when a receiver's type is unknown, so arm B **under-reports** rather than inventing edges. An arm-A edge missing from arm B is therefore either a genuine false positive OR a call pyright declined to resolve.

The `cursor` family — **54** unconfirmed arm-A edges pointing at `BaseDatabaseWrapper.cursor()` — is the honest counter-example. These are real `self.connection.cursor()` calls where the receiver is untyped, so pyright emits nothing and arm B under-reports. Here arm A was **right** and the type-resolved graph is the incomplete one. This is exactly why 0.746 is a floor on true precision, not a cap: **true precision is >= 0.746, never <=**. Read the ceiling in both directions — some unconfirmed edges are arm A's errors, and some are arm B's omissions.

## What the wrong edges cost

Projected localization cost of a name-matched graph of this quality: **1.2pp to 2.0pp** of resolve rate (interval `[0.0119, 0.0197]` as a fraction of instances). This is an interval, never a point estimate.

- **Basis.** ANALOGY to ARISE (arXiv 2605.03117); this is NOT a measurement we performed. ARISE improved call-graph edge quality on SWE-bench Lite and moved end-to-end resolve 17.3%->22.0% (+4.7pp) and Function Recall@1 0.43->0.60. We map our measured edge quality onto that published band. We did not run SWE-bench and measured no resolve-rate delta ourselves.
- **Assumption.** Assumes ARISE's published edge-quality->resolve elasticity transfers to a name-matched vs type-resolved graph on the same Python task family. The low bound charges only the unconfirmed-edge fraction (1-precision=0.254); the high bound compounds it with the missed-true-edge fraction (1-recall=0.648), capped at ARISE's full +4.7pp band. Because arm-A precision is a CEILING (pyright under-reports untyped receivers, so the true wrong fraction is <= 1-precision), both bounds are conservative. Reported as fractions of resolve rate: multiply by 100 for percentage points.

This page does **not** claim we measured a resolve-rate delta. We did not run SWE-bench. The interval above is a projection under the stated assumption, anchored to a published ablation.

## Published anchors (published, not reproduced here)

- **ARISE** (arXiv 2605.03117): richer structural + data-flow edges lift Function Recall@1 0.43->0.60 and end-to-end resolve 17.3%->22.0% on SWE-bench Lite. *Published, not reproduced here* — it is the band our cost projection is mapped onto by analogy.
- **SHERLOC** (arXiv 2606.24820): +5.95pp mean across 10 backbone x framework cells, and poor localization causes NEGATIVE transfer (a model can lose 4-5pp under unfiltered localization). *Published, not reproduced here.*
- **RGFL** (arXiv 2601.18044): counterfactual localization substitution attributes wrong-element localization to 53% of unresolved instances (wrong file 13%, wrong line 84%). *Published, not reproduced here.*


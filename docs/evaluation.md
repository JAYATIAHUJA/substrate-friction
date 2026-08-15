# Evaluation

## RETRACTION — v1's null is withdrawn

v1 reported **AUC 0.565 / p=0.726** and presented it as a test of the thesis that call-graph *friction* predicts SWE-bench agent failure. That measurement was taken on a tree-sitter, name-matched call graph in which **73.9% of the resolved CALLS edges were name-collision artifacts** — a "bare name is globally unique -> resolve it" fallback wired `super()` to `loader_tags.py::BlockNode.super` 1,321 times, `.lower()` to `defaultfilters.lower` 259 times, `.extend()` to a GIS class 222 times (see `docs/call-resolution-audit.md`). A metric measured on a graph that is three-quarters fiction did not test the thesis; it measured name collisions. **v1's AUC 0.565 / p=0.726 is retracted.** Retracting it loudly is worth more than the original claim. The v1 subgraph analysis is preserved, retracted, in `docs/evaluation-v1-retracted.md`.

This file replaces it with an evaluation on a *type-resolved* substrate.

## What was actually measured

- **50 django instances**, of which **28 are `comparable`** (both arms mapped the fix and test endpoints onto the same identities — the only cohort on which an arm-A-vs-arm-B contrast is meaningful).
- Two call graphs per instance: **arm A** = name-matched (what Aider / RepoGraph / LocAgent build), **arm B** = type-resolved via `scip-python` (pyright-backed).
- Friction is computed from the committed path_stats.json (pinned live-engine run). That cache stores per-arm path COUNTS, not node lists, so only f1 (multiplicity) is reconstructable offline; the equal-weights score is therefore monotone in f1 and AUC(friction) == AUC(f1). f2-f6 require a live path-list pass not run here. (The run was assembled across wiped local-backend generations because the store holds only ~13 instances per generation.)

**Limitation — no per-instance store-generation record.** The committed `path_stats.json` was assembled across several wiped local-backend store generations (the local backend holds only ~13 instances / 26 arms per ~3 GB generation), but it records **no generation tag** per instance or arm — and no run log, measurement timestamp, or batch boundary survives in the committed data from which one could be recovered. It therefore cannot be verified from committed data that an instance's arm A and arm B were measured in the *same* store generation, and answered-vs-timeout status is exactly what selects the n = 18 headline cohort, so within-instance A-vs-B comparability is **unverified**. Mitigating evidence: the arm-B failures are frontier admission-control OOM (`actual 250001 exceeds limit 250000`) and traversal-stage timeouts — density signals that reflect the type-resolved graph itself, independent of any store bloat — and each generation was kept under 3 GB, so the measured asymmetry is not plausibly an artifact of generation drift. No generation tag is fabricated to paper over the gap.

## The comparison table (all AUC vs `failed`, positive class = failure)

Headline set: **arm A engine-answered, comparable cohort** (n = 18); friction and the cheap baselines are scored on the *same* instances. `failed` ground truth = `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`.

| Predictor | AUC | n | note |
|---|---|---|---|
| Friction, arm A (name-matched; f1/path-multiplicity only) | 0.631 | 18 | 16 of 18 answered instances had >=1 bounded path |
| Friction, arm B (type-resolved; f1/path-multiplicity only) | 0.500 | 3 | only 3 of 28 comparable instances were engine-answerable (24 of the other 25 timed out at 29999 ms, 1 hit a memory-pool OOM) |
| `patch_lines` | 0.637 | 18 | scope baseline |
| `patch_files` | 0.581 | 18 | scope baseline |
| `f2p_count` | 0.569 | 18 | fail-to-pass count |
| `statement_chars` | 0.562 | 18 | problem-statement length |
| Published: statement text only (arXiv 2604.00594) | 0.787 | — | **published, NOT reproduced here** |
| Published: best combined (arXiv 2604.00594) | 0.841 | — | **published, NOT reproduced here** |

The two published rows are context from the literature, not measurements from this project; they are marked so no reader mistakes them for ours.

## The three questions that decide whether this is a finding

**1. Does arm B beat arm A?  UNDETERMINED.** 
arm B answered only 3 of 28 comparable instances (< 10); its AUC is not a measurement. The type-resolved graph is denser and its bounded fix->test enumeration is engine-unanswerable on all but a handful of instances: of the 25 unanswered comparable instances, 24 timed out at 29999 ms and 1 hit a frontier admission-control memory-pool OOM (`actual 250001 exceeds limit 250000`). So at maxLen 6 the type-resolved arm is *engine-unanswerable at cohort scale*. That the richer graph is the one the engine cannot traverse is itself an honest result — but it means the headline arm-B-vs-arm-A comparison cannot be made on this hardware, and we do not manufacture one from n = 3.

**2. Does either beat `patch_lines`?  NO.** Friction arm A scores AUC 0.631 against `patch_lines` 0.637 on the same 18 instances (difference -0.006). Path multiplicity (friction f1 — the only component reconstructable from the cached counts) adds nothing over raw patch scope; the cheapest possible predictor is at least as good. Arm B cannot be entered into this comparison (question 1).

**3. Is n big enough to say anything?  NO.** Bootstrap 95% CI on AUC(friction arm A) - AUC(`patch_lines`) over the 18 shared instances (8 failed / 10 resolved — the class split is not degenerate) is **[-0.472, 0.435]** (point -0.006, 2000 resamples). The interval spans zero and most of the achievable range. Underpowered by roughly an order of magnitude; a real effect below ~0.1 AUC cannot be resolved at this n.

## Verdict

**NO-GO on the prediction thesis.** Read the scope precisely: what was actually tested on this substrate is **path multiplicity — friction component f1 alone**. Only f1 is reconstructable from the committed `path_stats.json`, which caches per-arm path COUNTS, not the path node lists that f2-f6 (mean length, distinct intermediates, convergence, cyclic pressure, and the fan-in component) require; **f2-f6 were not computed on this substrate**, and with equal weights the friction score is monotone in f1, so AUC(friction) == AUC(f1). On that basis: **path multiplicity does not beat patch scope** (arm A AUC 0.631 vs `patch_lines` 0.637 on the same 18 instances), the type-resolved arm B is not engine-answerable at cohort scale (only 3 of 28 comparable instances answered; 24 timed out and 1 hit a memory-pool OOM), and **n = 18 is too small to resolve anything** (the bootstrap CI spans zero and most of the achievable range). This is *not* a demonstration that graph structure fails to predict failure — the multi-component structure (f2-f6) was never measured here. The v1 null is retracted, and the honest replacement is not a positive result. The *supporting* structural finding — that a name-matched graph's edges have a precision ceiling of 0.746 against the type-resolved graph (Task 6, `docs/graph-delta.md`) — stands on its own as the measurement of what name matching costs; it is not rescued into a prediction claim it cannot support.

## Label contamination — a limit of the ground truth, not the metric

SWE-Bench+ (arXiv 2410.06992) measured **32.7% solution leakage** and **31% weak tests** on SWE-bench, and OpenAI reports **59.4%** of o3 failures on SWE-bench Verified were test flaws and no longer recommends the benchmark. A structural feature that correlated with test weakness would be predicting label noise, not agent difficulty. This is a limitation of the ground truth, not of the metric, and it is stated here so no AUC in this file is read as cleaner than the labels underneath it.

## Reproducibility

Every number above is regenerated by `uv run python -m friction.harness` from `data/instances/arms/path_stats.json` (the committed, pinned live-engine path structure), `data/instances/arms/manifest.jsonl`, `data/instances/annotations.json`, and the offline-cached SWE-bench Verified rows under `data/swebench`. The engine is **not** re-queried; the path structure is read from the committed cache exactly as the task specifies for an engine-down run. No figure is hand-entered.

## Appendix pointer — the retracted v1 truncation analysis

For completeness, the v1 subgraph/engine analysis (the demonstrated `pathCount` truncation artifact and its fidelity guard) is regenerated into `docs/evaluation-v1-retracted.md`: engine-computed AUC 0.780 shown to be a truncation artifact (fidelity recall on that run was the guard's trigger), collapsing to AUC 0.565 truncation-free. It is retained, retracted, as evidence — not as a result.

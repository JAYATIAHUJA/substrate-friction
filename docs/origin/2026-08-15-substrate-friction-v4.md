# Substrate Friction v4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship a working graph-precision measurement product on HydraDB that shows what name-matched code graphs cost — with the fix-site↔test friction predictor as an explicitly hedged secondary result.

**Architecture:** Two call graphs of the same commit — **arm A** name-matched (what Aider/RepoGraph/LocAgent build) and **arm B** type-resolved via `scip-python` — both resident in HydraDB in disjoint id bands. All structure metrics use **in-engine bounded reachability** (`count(*)` over `[:REL*1..k]`), which is measured exact and flat in k. The product is a CLI + HTTP API + visualization that shows a wrong edge being pruned and what it costs.

**Tech Stack:** Python 3.12 + `uv`, pytest, `scip-python`, HydraDB (Bolt), NetworkX, SciPy, FastAPI, Cytoscape.js, scikit-learn, statsmodels, Docker + MinIO.

---

## MEASURED FACTS — probed on this machine, 2026-08-15

Everything below was run, not read. These supersede all prior plans.

### Probe 1 — in-engine reachability: **BRANCH A CONFIRMED**

Synthetic graph, 3,000 nodes / 8,989 edges, **out-degree 3 — the exact density at which `algo.MSpaths` timed out at 30,000 ms in v2.**

| k | engine `count(*)` | networkx | match | ms |
|---|---|---|---|---|
| 1 | 3 | 3 | OK | 4 |
| 2 | 12 | 12 | OK | 2 |
| 3 | 39 | 39 | OK | 4 |
| 4 | 117 | 117 | OK | 3 |
| 5 | 330 | 330 | OK | 7 |
| 6 | 834 | 834 | OK | **12** |

**Exact at every k. Latency flat.** 12 ms where path enumeration took 30,000 ms and failed — a 2,500× difference on identical density. Engine issues #69/#71 do **not** bite this path: `*1..k` is a genuine union over 1..k, and no same-frontier edges are dropped.

**Critical syntax finding:** `RETURN count(n)` where `n` is a **node** is REJECTED — *"property values support integer, float, boolean, and string literals"*. The working form is **`RETURN count(*)`**. Also verified working: `RETURN n.id`, `RETURN n.sid`, `collect(n.id)`, and fixed-hop `*3`. The v3 plan's keystone query would not have parsed.

### Probe 2 — connectivity: the framing works, but only one direction does

44 of 50 instances have both endpoints mapped in arm B. Bounded at 6 hops:

| Direction | Connected | Note |
|---|---|---|
| **fix → test** (directed) | **0/44 (0%)** | Backwards. Code does not call tests. |
| **test → fix** (directed) | **24/44 (55%)** | The natural direction: tests call code. |
| **undirected** (`relDirection: 'both'`) | **43/44 (98%)** | Weaker semantics, near-total coverage. |

Arm A: 27/30 (90%) undirected, 0% directed fix→test.

**Consequences.** The original spec's `sourceValues: $fixSiteIds → targetValues: $testTargetIds` is directionally wrong; every v1/v2 friction number was computed on `relDirection: 'both'`, which silently means *"share a neighbourhood"*, not *"the test exercises this code."* The clean directed semantic is **test → fix at 55%**, and the 43-point gap to 98% is exactly the pytest fixture / `setUp` / parametrize / framework-dispatch closure that static call graphs cannot see. Report **both**, and label them differently.

### Carried forward from v2 (measured, still valid)

- **Name-match precision ceiling 0.746** against type resolution; recall 0.352; Jaccard 0.314. Offenders: `extend`(139), `lower`(125), `cursor`(54). `cursor` is the honest counter-example where arm A was **right** and pyright under-reported, so precision is a **ceiling**.
- `scip-python` indexes django in ~24–38 s, **no dependency install** (pyright bundles typeshed). `super()` → `builtins/super#`; untyped receiver → **no** occurrence (missing edge, never wrong edge).
- Endpoint mapping: arm B 44/50, arm A 30/50.
- Engine: `max_query_intermediate_rows` 250,000; `max_query_runtime_ms` 30,000; `UNWIND` caps at 1,024 rows; Bolt mandatory for `$params`; only graph `default` reachable; `relDirection` case-insensitive (`both`/`BOTH` parse, `in`/`IN` rejected); `pathCount: 20` truncates and **manufactured** a false AUC 0.780 at 2.6% recall.
- `CLOUD_PROVIDER=local` degrades silently under sustained writes while reads keep serving ([#81](https://github.com/hydra-db/hydradb/issues/81)).

### Published anchors (cite; do not reproduce)

- **ARISE** (arXiv 2605.03117): richer edges lift Function Recall@1 **0.43→0.60**, resolve **17.3%→22.0%** on SWE-bench Lite. *This is the citation that turns "wrong edges" into "wrong edges cost resolve rate."*
- **SHERLOC** (arXiv 2606.24820): +5.95 pp mean across 10 backbone×framework cells; bad localization causes **negative transfer**.
- **RGFL** (arXiv 2601.18044): wrong element implicated in **53%** of unresolved instances.
- **Agent Psychometrics** (arXiv 2604.00594): per-instance failure prediction is **solved** — AUC **0.841**; text-only **0.787**; task-agnostic prior **0.718**. Do not claim this problem.
- **GRADE** (arXiv 2606.22741): predicts failure from the **agent's run graph** — adjacent, not ours.
- Label contamination: SWE-Bench+ (arXiv 2410.06992) 32.7% leakage / 31% weak tests; OpenAI 59.4% of o3 failures were test flaws.
- Judging: sponsor says *"we care about working, thoughtful products, not just benchmark scores."* At the comparable GitLab AI Hackathon 2026, **GraphDev — a code-graph change-impact tool — won the Anthropic Grand Prize**. **Weight ~50% of effort on the product layer.**

---

## Global Constraints

- **Every structure query uses `count(*)`, never `count(<node>)`.** Never `count(DISTINCT …)`.
- Variable-length patterns: mandatory upper bound, single-typed, integer-`id` node matching.
- `algo.*` `sourceValues` are **lists of strings inlined as literals** on the `sid` property; `SSpaths` needs an integer `sourceNode` **and** an explicit `pathCount`.
- No metric may enumerate paths at query time. No truncating estimator without a stated bound.
- Report `test → fix` (directed, clean) and `undirected` (broad) as **separate, differently-labelled** measures. Never present undirected reachability as "the test exercises this code."
- Wipe `hydradb-data` before heavy loading; never trust read health as liveness.
- Do not claim per-instance failure prediction as novel. Do not hide a negative result.
- Public repo, OSI LICENSE, no participant commit before 2026-08-12, form `forms.gle/GrMYKxLj9zPQcqqc8`.

---

## Tasks

### Task 1 — `reach.py`: in-engine bounded reachability
`build_reach_cypher(node_id, rel_type, k, direction)` emitting `count(*)`; `reachable_count`; `profile` (sizes at k=1..K); `bidirectional`. Tests: bound is mandatory; no `DISTINCT`; integer id only; single-typed; `in` reverses the arrow; non-integer id raises. **Then re-run the Probe-1 table as an `@pytest.mark.engine` test so the exactness claim is a standing regression test, not a one-off.**

### Task 2 — `connectivity.py`: the framing measurement, productised
`connected_within(g, src, dst, k, undirected)`; `measure_corpus(manifest) -> ConnectivityReport` reporting directed test→fix, directed fix→test, and undirected at k=6 and k=10. Generates `docs/connectivity.md` with the 0% / 55% / 98% table and the fixture-gap explanation. This is a **finding in its own right** — nobody has published it.

### Task 3 — `precision.py`: what name matching costs, joined to consequence
Reuse `identity.py` + `delta.py`. Add `cost_projection(precision, recall)` mapping the measured 0.746/0.352 onto ARISE's ablation band, reported as an **interval with the assumption stated**, never a point estimate. Generates `docs/precision.md`.

### Task 4 — `features.py`: the hedged secondary metric
From reachability profiles only: `fwd_growth`, `bwd_growth`, `overlap_ratio`, `fanin`, `test_to_fix_hops`, `undirected_hops`. No path enumeration. Every value labelled with which direction produced it.

### Task 5 — `evaluate.py`: honest evaluation
AUC per feature against per-instance labels; the `patch_lines` / `patch_files` / `f2p_count` / `statement_chars` baseline block on the same instances; published 0.718/0.787/0.841 rows marked **published, not reproduced**; bootstrap CI; class balance. Retract v1's 0.565 and v2's f1-only 0.631 explicitly.

### Task 6 — `api.py`: FastAPI wrapper
`GET /check/{instance_id}`, `GET /compare/{instance_id}`, `GET /precision`, `GET /health`. Same logic as the CLI. Judging asks for "real ingestion and retrieval workflows" — this is that.

### Task 7 — `cli.py`: the gate
`friction check` (feature bars, score, recommendation, **the Cypher and the measured latency**), `friction compare` (arm A vs arm B), `friction precision`, `friction connectivity`, `friction list`. Falls back to `data/shipped` when `data/instances` is absent.

### Task 8 — `viz.py` + Cytoscape.js: the money shot
Three figures **and** an interactive HTML page: (1) arm A vs arm B on the same neighbourhood with unconfirmed edges in red; (2) the offender bar chart with `cursor(54)` annotated as the counter-example; (3) a live prune animation — `super()` → `BlockNode.super` ×1,321 removed. Cytoscape.js over Sigma.js: these are small contrast subgraphs.

### Task 9 — packaging
`setup.sh` + `docker-compose.yml` + shipped payload ≤50 MB with omissions named. Clean-clone timing reported honestly.

### Task 10 — README + video
Lead with the substrate finding and the ARISE-anchored consequence. State plainly that prediction is solved at 0.841 and we do not claim it. "How HydraDB is used": the `count(*)` reachability form, the measured 12 ms at k=6 versus the 30,000 ms enumeration timeout, both arms resident at once. Limitations: precision is a ceiling; 55% vs 98% directional gap; fixture edges absent; Python only; n and its power.

---

## Self-Review

**Spec coverage.** Original spec Parts 1–5 → Tasks 1–4 with the metric reformulated (path enumeration is #P-complete and measured-impossible here). Part 6 go/no-go → Task 5. Part 7 product → Tasks 6–9. Part 9 Common Cause → **dropped with cause**: tried in v2, its top result was the `super()` artifact. Parts 10–12 → Global Constraints.

**Deliberate departures.** (a) `algo.MSpaths` is no longer primary — measured at 30 s timeout vs 12 ms for reachability. (b) Headline inverted to the substrate finding, because prediction is solved at 0.841 and the substrate result is ours. (c) Directed semantics corrected: fix→test is 0%, test→fix is 55%.

**Placeholders.** Tasks 1–5 have complete interfaces; 6–10 give exact files and acceptance criteria and modify existing v2 modules the implementer reads first.

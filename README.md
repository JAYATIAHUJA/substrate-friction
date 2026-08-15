# Substrate Friction

**Every AI coding agent that reads your repository builds a graph of it first. Aider's repo map, RepoGraph, and LocAgent all build that graph by matching identifier _names_. We measured what that costs: on django, a name-matched graph's edges have a precision ceiling of 0.746 against a type-resolved graph — and the type-resolved graph is the one the engine cannot traverse.**

That is the finding. It is a measurement of the substrate every localization and retrieval tool in this space stands on, and it holds regardless of what you build on top. The rest of this project — a friction metric, a prediction gate, an evaluation — is the scaffolding that produced the measurement and a secondary, honestly-null prediction result reported below without dressing it up.

---

## What this is

Take one SWE-bench django ticket. It has **fix sites** (functions the gold patch edits) and **test targets** (functions the failing tests exercise). To reason about that ticket structurally you first need a call graph — and how you _build_ that graph is a choice with consequences that nobody in this space has measured against a type-resolved reference on real code.

We build the same repository two ways and compare them edge-for-edge:

- **Arm A — name-matched.** A call `x.foo()` becomes an edge to _every_ function named `foo`, resolved by identifier name. This is how Aider's repo map, RepoGraph (arXiv 2410.14684), and LocAgent (arXiv 2503.09089) build their graphs.
- **Arm B — type-resolved.** The same repository indexed with `scip-python` (pyright-backed), so `x.foo()` resolves to `foo` on the _actual static type_ of `x`, or to nothing when the receiver's type is unknown.

Same repo, same commit, same extraction of definitions. Only the edge-resolution strategy differs. The whole project runs both arms simultaneously against one graph engine (HydraDB) and measures the difference.

---

## The substrate finding — what name matching costs

On django (commit `b9cf764`), arm A produced **18,774** call edges. Restricting to edges whose source is in scope and mappable onto the shared identity space leaves **5,873** arm-A edges to compare against arm B's **12,445** internal edges. Of the compared arm-A edges:

| Measure | Value |
|---|---:|
| Confirmed by arm B (both) | **4,381** |
| In arm A only (`only_a`) | **1,492** |
| In arm B only (`only_b`) | **8,064** |
| **Arm A precision (ceiling)** | **0.746** |
| Arm A recall of arm B | **0.352** |
| Jaccard | 0.3143 |

**A quarter of a name-matched graph's in-scope edges do not survive contact with type resolution.** These are not random. They cluster on container-method names that collide across the codebase:

| Target name | Unconfirmed edges | What it actually is |
|---|---:|---|
| `extend` | 139 | `list.extend` name-bound to a GIS class |
| `lower` | 125 | `str.lower` bound to `django.template.defaultfilters.lower` |
| `cursor` | 54 | (see counter-example below) |
| `import_module` | 33 | |
| `search` | 31 | |
| `split_contents` | 29 | |
| `fetchall` | 28 | |
| `time` | 28 | |
| `insert` | 24 | |
| `compile_filter` | 23 | |

A name-matched builder cannot tell `list.extend` from a GIS method called `extend`; it draws an edge to both. On this repository that guess is wrong at least a quarter of the time.

### 0.746 is a ceiling — honest in both directions

pyright emits **no** occurrence when a receiver's type is unknown; it never invents an edge. So an arm-A edge missing from arm B is _either_ a genuine false positive _or_ a real call that pyright declined to resolve. The direction of arm B's bias is known (it under-reports), so **true precision is somewhat _above_ 0.746**, not below.

The `cursor` block of **54** unconfirmed edges is the clean counter-example. These point at `BaseDatabaseWrapper.cursor` and are real calls to `self.connection.cursor()` where `.connection` is untyped, so pyright emits nothing and arm B under-reports. **Here arm A was right and the type-resolved reference is the one that is incomplete.** We report the ceiling as a ceiling precisely so this case is not hidden: the number bounds one direction and the bias bounds the other.

_Source: `docs/graph-delta.md`. Reproduce: `uv run python scripts/graph_delta.py --repo data/repos/django --out docs/graph-delta.md`._

### A second finding that stands: endpoint mapping

For the prediction task you need to resolve both a ticket's fix-site endpoints and its test-target endpoints onto the graph. Across 50 django instances, **arm B resolves both endpoints on 44/50; arm A on 30/50.** The type-resolved graph places the ticket on the graph 47% more often. _(Computed from `data/instances/arms/manifest.jsonl`.)_

---

## The density paradox — the graph worth having is the one you cannot query

Type resolution does not just move edges around; it makes the graph far denser. Over the 50 instances, arm B is **~4x denser than arm A** — median **79,447** edges vs **19,815** (ratio 4.01) — because pyright resolves inheritance, cross-module dispatch, and method calls a name matcher never connects.

That density is exactly what breaks the query. The friction metric is a bounded path enumeration (`algo.MSpaths`, `maxLen 6`) between the fix-site and test-target sets. Of the **28 comparable** instances (both arms mapped both endpoints):

- **Arm A** (sparse, 19,815-edge median): answered at cohort scale.
- **Arm B** (dense, 79,447-edge median): answered **only 3** at `maxLen 6`. **24 timed out** at the engine's 29,999 ms ceiling and **1 hit a memory-pool OOM** (`actual 250001 exceeds limit 250000`).

This is genuine density, not a query, band, or id bug: arm B returns real bounded paths on the 3 small graphs it does complete. The engine's own scaling sweep confirms the mechanism — cost is `(both-degree)^maxLen`, so 4x the edge density at 6 hops is the exponential wall (`docs/engine-scaling.md`, Finding 2).

**So the richer, more correct graph — the one that maps endpoints better and does not fabricate edges — is the one the engine cannot traverse at `maxLen 6` on this hardware.** That tension is the interesting engineering fact underneath the whole space: the graph you want is the graph you can't afford to query.

---

## Novelty — what we do and do not claim

**We do not claim to predict per-instance agent failure. That problem is already solved.** Agent Psychometrics (arXiv 2604.00594) reports **AUC 0.841** on SWE-bench Verified, and **0.787 from the problem-statement text alone** — a task-agnostic prior already sits near 0.718. A structure-only call-graph signal has no room to be the story, and we do not pretend it is.

The contribution is the **substrate measurement**: name-matched code graphs, the ones every agent tooling paper builds on, cost you a precision ceiling of 0.746 and half the endpoint coverage, and the corrected substrate is the one the engine cannot traverse. Nobody in this space had measured that against a type-resolved reference on real code. That is what this project is for.

### Pre-empting the reviewer: why call-graph structure at all?

ARISE (arXiv 2605.03117) found that **def-use slices beat call-graph topology for localization.** A reviewer will rightly ask why we measured call-graph structure. Two reasons: (1) call graphs are what the deployed tools actually build (Aider, RepoGraph, LocAgent), so a call-graph substrate measurement speaks directly to shipped systems; and (2) the name-matched-vs-type-resolved question is orthogonal to slices-vs-topology — a def-use slice is still only as sound as the edges it slices over, and those edges are name-matched in every tool above. **Def-use slices are the obvious next comparison**, and this measurement is what it should be compared against.

---

## Setup

```bash
git clone <repo> && cd substrate-friction
./setup.sh    # brings up the engine, installs the package editable, loads the
              # shipped working set, and warms one real live algo.MSpaths query
```

`setup.sh` is one command from a clean clone; `just` is not required. The headline commands are cache-backed — they read the committed `data/…/arms/{manifest.jsonl,path_stats.json}` and the `docs/` reports and need no live engine. The engine load exists only to warm one real query and to reproduce the primitives below.

**Pinned HydraDB engine commit:** `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1, AGPL-3.0). Every engine number in this README was measured against that build; `docs/pinned-engine-commit.txt` carries the hash. The traversal needs a large Rust stack, set in `docker-compose.yml`:

```
export RUST_MIN_STACK=33554432
```

| Recipe | Does |
|---|---|
| `just up` / `just down` | start / tear down the engine (+ MinIO) via docker compose |
| `just test` | run the suite (`pytest -m "not engine"`) |
| `just probe` | re-measure the engine's capability table |

---

## How HydraDB is used

Which graph-native primitives, where, what breaks without them, and why a vector index structurally cannot do this.

### (a) Which primitives, where

**`algo.MSpaths` with `pairwise: true` — the metric-defining query, run per arm.** It computes every bounded path from the fix-site set to the test-target set in **one server-side round trip**. Both arms are resident in the engine simultaneously in disjoint id bands (arm A at `1e10 + idx·1e7`, arm B at `2e10 + idx·1e7`), so the two-arm comparison is a single-engine operation. `sourceValues`/`targetValues` are lists of **strings** matched against a string `sid` property and **inlined as Cypher literals** (this build rejects a Bolt `$parameter` list on `algo.*` set queries).

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Function', sourceProperty: 'sid', sourceValues: ['…fix sids…'],
  targetLabel: 'Function', targetProperty: 'sid', targetValues: ['…test sids…'],
  relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS'],
  relDirection: 'both', maxLen: 6, pairwise: true, pathCount: 20
}) YIELD path, pathCost RETURN path, pathCost
```

Measured cost on real django code graphs (arm-A answered instances, n=23): **median 14,614.5 ms, p95 29,041.27 ms, max 29,948.75 ms** at `maxLen 6` — sitting right on the engine's 29,999 ms ceiling (`docs/evaluation-v1-retracted.md` latency block; healthy-store sweep in `docs/engine-scaling.md`). On the healthy store the same query shape answers a 16,000-node / ~24,000-edge graph at `maxLen 6` in **~1.5 s** and a 34,000-node / 68,000-edge graph in ~7.5–17.8 s depending on seed placement.

**`algo.SSpaths` with an integer `sourceNode` and explicit `pathCount` — fan-in (component F6).** `SSpaths` demands one **integer** `sourceNode` (a string is rejected) and needs an explicit `pathCount` or it returns only the single shortest path. Fan-in over the fix sites issues one such query per site and unions the direct callers client-side. Sub-second; never failed.

**`UNWIND $rows` batched loading over Bolt — ingest.** `MERGE`/`CREATE` one hop per batch; measured at **22,249.5 edges/sec at batch size 500** (`docs/throughput.md`). HTTP cannot carry `$params`, so ingest is Bolt-only; `UNWIND` caps at the build's `max_parameters` (1024 default).

### (b) What breaks without it

Without a server-side multi-source/multi-target path primitive, friction for one ticket is **N×M client round trips** — one query per (fix-site, test-target) pair. A 3-fix × 7-test ticket becomes 21 round trips; at this build's per-call latency the gate stops being something you can sit in a workflow. `MSpaths` with `pairwise: true` collapses all N×M pairs into one round trip the engine plans and executes once — and does it for _both arms_ held resident at the same time.

### (c) Why a vector index structurally cannot do this

Friction is defined over the **set of bounded paths between two node sets**. Paths do not exist in a vector space. Two functions with near-identical text sit adjacent in embedding space while lying on completely disconnected execution paths; the embedding is blind to precisely the property being measured. No nearest-neighbour retrieval recovers "how many bounded call-graph paths connect these two functions, how long, how convergent, how cyclic" — that is a graph traversal over a specific edge set, which is why the substrate is a graph engine and why the whole name-matched-vs-type-resolved comparison (the thing every edge count above depends on) is only expressible as a query over resolved edges.

---

## The metric

Six components, computed from the returned path set, then min-max normalised across the instance set (the engine has no `min`/`max` aggregate, so normalisation is client-side):

| # | Component | Definition |
|---|---|---|
| F1 | Path multiplicity | paths returned ÷ (fix sites × test targets) |
| F2 | Mean path length | mean edge count over the returned paths |
| F3 | Intermediate spread | count of distinct intermediate functions across all paths |
| F4 | Convergence | distinct intermediates ÷ total intermediates (inverted in the score: convergence drives friction up) |
| F5 | Cyclic pressure | fraction of returned paths that revisit a node |
| F6 | Fan-in load | direct-caller count of the fix sites (`SSpaths` fan-in) |

**Scope caveat, stated up front:** the committed `path_stats.json` caches per-arm path _counts_, not the path node lists that F2–F6 require. So on this substrate **only F1 (path multiplicity) was actually computed.** With equal weights the score is monotone in F1, so `AUC(friction) == AUC(F1)`. Everything in the evaluation below is an F1 / path-multiplicity result; F2–F6 were not measured here.

---

## Evaluation — the prediction result is a scoped NO-GO

**Ground truth.** SWE-bench Verified django instances; pass/fail labels from `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` (primary). Headline cohort: arm-A engine-answered, comparable instances, **n=18**. All predictors scored on the _same_ instances.

| Predictor | AUC | n | note |
|---|---:|---:|---|
| Friction, arm A (name-matched; F1 / path-multiplicity only) | **0.631** | 18 | 16 of 18 had ≥1 bounded path |
| Friction, arm B (type-resolved; F1 only) | 0.500 | **3** | undetermined — only 3 of 28 comparable were engine-answerable (24 timed out, 1 OOM) |
| `patch_lines` | **0.637** | 18 | scope baseline |
| `patch_files` | 0.581 | 18 | scope baseline |
| `f2p_count` | 0.569 | 18 | fail-to-pass count |
| `statement_chars` | 0.562 | 18 | problem-statement length |
| Statement text only (arXiv 2604.00594) | 0.787 | — | **published, NOT reproduced here** |
| Best combined (arXiv 2604.00594) | 0.841 | — | **published, NOT reproduced here** |

The two published rows are literature context, not our measurements, and are marked so no reader mistakes them for ours.

**Read the result precisely:**

1. **Does path multiplicity beat patch scope? No.** Arm A F1 scores 0.631 vs `patch_lines` 0.637 on the same 18 instances (difference **−0.006**). The cheapest possible predictor is at least as good.
2. **Does arm B beat arm A? Undetermined.** Arm B answered only 3 of 28 comparable instances — not a measurement. This is the density paradox again: the better graph is the one the engine cannot traverse at cohort scale.
3. **Is n big enough to say anything? No.** Bootstrap 95% CI on `AUC(arm A) − AUC(patch_lines)` over the 18 shared instances (class split **8 failed / 10 resolved** — not degenerate) is **[−0.472, 0.435]** (point −0.006, 2000 resamples). Underpowered by roughly an order of magnitude.

**Verdict: NO-GO on the prediction thesis** — and scoped exactly. The honest claim is _"path multiplicity does not beat patch scope, and n=18 is too small to resolve anything."_ This is **not** a demonstration that structure fails to predict failure: F2–F6 were never measured on this substrate, and per-instance failure prediction is already solved by others (0.841) anyway. The substrate finding above stands on its own and is not rescued into a prediction claim it cannot support.

_Source: `docs/evaluation.md`. Reproduce: `uv run python -m friction.harness`._

---

## The v1 retraction

v1 of this project reported **AUC 0.565 / p=0.726** and presented it as a test of the thesis. It was measured on a name-matched graph in which **73.9% of the resolved CALLS edges were name-collision artifacts** — a "bare name is globally unique → resolve it" fallback wired `super()` to `loader_tags.BlockNode.super` **1,321 times**, `.lower()` to `defaultfilters.lower`, `.extend()` to a GIS class (`docs/call-resolution-audit.md`). A metric measured on a graph that is three-quarters fiction did not test the thesis; it measured name collisions. **v1's AUC 0.565 / p=0.726 is withdrawn.** The retracted analysis is preserved in `docs/evaluation-v1-retracted.md`. Retracting it loudly is worth more than the original claim — and it is itself evidence for the substrate finding: a name-matched graph really is that noisy.

---

## Limitations

- **Precision is a ceiling.** Arm B under-reports on untyped receivers (`cursor(54)`), so 0.746 bounds one direction; the true value is somewhat higher. Stated in both directions above.
- **Dynamic dispatch is invisible to both arms.** Runtime-resolved calls (`getattr`, registries, duck typing on unknown types) are edges neither arm draws.
- **Python only.** The type-resolved arm depends on `scip-python`/pyright; nothing here is cross-language yet.
- **`maxLen 6`.** The metric is a bounded enumeration; paths longer than 6 hops are not counted, and the bound is what makes arm B unanswerable.
- **F1 only on this substrate.** Only path multiplicity was computed; F2–F6 require path node lists the cache does not hold. Every AUC here is an F1 result.
- **n=18, single repository.** The prediction cohort is underpowered by ~10x and is django alone; a real effect below ~0.1 AUC cannot be resolved.
- **Label contamination.** SWE-Bench+ (arXiv 2410.06992) measured **32.7% solution leakage** and **31% weak tests**; OpenAI reports **59.4%** of o3 failures on Verified were test flaws and no longer recommends the benchmark. A feature correlating with test weakness would predict label noise, not difficulty.
- **No per-instance store-generation record.** `path_stats.json` was assembled across wiped local-backend store generations with no generation tag, so within-instance arm-A-vs-arm-B store comparability is unverified (`docs/evaluation.md`). The arm-B failures are frontier OOM and traversal timeouts — density signals intrinsic to the graph, not plausibly generation drift — but the gap is stated, not papered over.

Every number in this README traces to `docs/graph-delta.md`, `docs/evaluation.md`, `docs/engine-scaling.md`, `docs/throughput.md`, `docs/call-resolution-audit.md`, or the committed `data/instances/arms/manifest.jsonl`.

---

## Upstream contributions

Two contributions to `github.com/hydra-db/hydradb`, surfaced by this project:

- **Issue #81** — manifest GC fails under the documented `CLOUD_PROVIDER=local` (`LocalFileSystem` does not implement `PutMode::Update`): after enough sustained writes every write fails permanently while reads keep serving, so a read-only health check reports the node healthy while it is silently write-dead (`docs/engine-scaling.md`, Finding 3).
- **PR #82** — cypher-compat docs covering 7 measured behaviours of the pinned build (inlined-literal set queries, `SSpaths` integer `sourceNode`, and the rest documented in `docs/engine-capabilities.md`).

---

## Attribution

- **HydraDB** graph engine, pinned at `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1), **AGPL-3.0** — the graph substrate every measurement runs against.
- **`scip-python`** 0.6.6 (pyright-backed) — the type-resolved arm B index.
- **SWE-bench Verified** and the `SWE-bench/experiments` submissions — ground-truth instances and agent pass/fail labels.
- Cited literature, all published-not-reproduced: Agent Psychometrics (arXiv 2604.00594), RepoGraph (arXiv 2410.14684), LocAgent (arXiv 2503.09089), ARISE (arXiv 2605.03117), SWE-Bench+ (arXiv 2410.06992).

## License

This project is **MIT** (see `LICENSE`). The HydraDB engine it queries is **AGPL-3.0** and is used as a pinned external service, not vendored into this source tree; its license governs the engine binary independently of this project's MIT grant.

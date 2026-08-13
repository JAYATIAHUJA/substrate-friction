# Substrate Friction

**A graph-native gate that asks whether the call-graph structure between a bug's fix sites and its tests predicts whether an AI coding agent will fail on the ticket — and finds, on the real engine substrate, that it does not.**

Every other tool in this space is trying to make coding agents *succeed* — better retrieval, better context, better prompts. This asks the inverted and much cheaper question: which tickets should we not give them at all? The honest answer this project measured is reported first, below, whichever way it went — and it went against the thesis.

---

## The result — lead with the null

We asked whether the graph structure between a bug's fix sites and its tests predicts whether an AI coding agent will fail on it. **It does not.**

> **AUC 0.565, r = 0.055, p = 0.726**, across **43** SWE-bench Verified django instances and **three** published agent systems, with **three** confound checks. A clean null.

Two independent routes reach the same null on the same substrate:

| Measurement | Instances | AUC | r | p |
|---|---:|---:|---:|---:|
| **Reference-derived, full path enumeration (headline)** | 43 endpoint-bearing | **0.565** | 0.055 | 0.726 |
| Reference-derived, restricted to engine-answered | 23 | 0.576 | 0.119 | 0.587 |
| Prior independent baseline over full-repo graphs | — | ~0.567 | 0.047 | 0.77 |

The engine run confirms the reference run: two independent routes, the same null. Nothing was tuned, dropped, or reframed to move a number in either direction. **Verdict: NO-GO.**

## The methodological finding — the most interesting thing this produced

Along the way the engine handed us a confident-looking positive:

> **Engine-computed AUC 0.780** (r = 0.428, p = 0.0416). Taken alone it looks like a strong result. **It is an artifact of the engine's `pathCount = 20` truncation.**

At `pathCount = 20` the engine sees **2.6 %** of the paths that exist between those node sets — it returned **1021** paths where full enumeration over the **identical** edge set finds **38 720** (fidelity recall **0.0264**, validity precision **1.0**: every path it returns is real, it just sees 1/38th of them). The friction metric is defined over path *multiplicity*, so scoring it off that 2.6 % sample **manufactured a correlation that vanishes the moment the truncation is removed** — the same 23 instances, same edges, same `maxLen`, re-scored from full enumeration, collapse to AUC 0.576 (p = 0.587).

That is a general warning for anyone scoring a graph metric off capped path queries: **truncated path sampling can manufacture a confident-looking correlation where none exists.**

---

## What this is — the gate, running

`friction check` scores one instance against the live engine and prints the six-component breakdown, the score, the Cypher it ran, the measured latency, and — because the finding is a null — a caveat that the score should not be trusted. Two real runs against `bolt://127.0.0.1:7687` (engine commit `02a40025`):

```
  django__django-11885
  subgraph: 4835 nodes / 8105 edges   (queried at maxLen 6)

  Fix sites:     10 function(s)
  Test targets:  1 function(s)
  ────────────────────────────────────────────────────
  Path multiplicity    F1   1.00  ████████████
  Mean path length     F2   0.86  ██████████··
  Intermediate spread  F3   0.67  ████████····
  Convergence          F4   0.08  █···········
  Cyclic pressure      F5   0.00  ············
  Fan-in load          F6   0.02  ············
  ────────────────────────────────────────────────────
  FRICTION SCORE             0.58   band: MEDIUM
  Illustrative failure prob: 58%
  Recommendation (illustrative): agent with human review of the patch

  Engine returned 200 path(s).
  ⚠ TRUNCATED at the pathCount cap: the engine returned 200 paths,
    at or above its pathCount cap, so this score is computed off a
    truncated sample. Cohort fidelity recall is 0.0264 (2.6%) —
    full enumeration finds far more. Do not trust this score.

  Cypher (algo.MSpaths, one server-side round trip):
    CALL algo.MSpaths({sourceLabel: 'Function', sourceProperty: 'sid',
    sourceValues: ['4430000650', '4430006119', … , '4430006128'],
    targetLabel: 'Function', targetProperty: 'sid',
    targetValues: ['4430016687'], relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS'],
    relDirection: 'both', maxLen: 6, pairwise: true, pathCount: 20})
    YIELD path, pathCost RETURN path, pathCost
  Measured latency: 11751.65 ms  (cohort median 14,614 ms, p95 29,041 ms at maxLen 6).
  ────────────────────────────────────────────────────
  CAVEAT — READ BEFORE TRUSTING THE SCORE ABOVE
  On the real engine substrate this metric does NOT predict agent
  failure: AUC 0.565, r=0.055, p=0.726 (a clean null).
  The confident-looking engine signal (AUC 0.780) is a
  demonstrated artifact of the engine's pathCount cap — full path
  enumeration over the identical edges finds ~38x more paths
  (fidelity recall 0.0264). The score is illustrative, not a
  validated failure probability. See: friction eval / friction fidelity.
```

The gate is a working graph query whose own output the project shows should not be trusted at `pathCount = 20`. Saying that plainly, on screen, is the point: a gate that printed a recommendation without the caveat would launder the null into false confidence.

`friction list` shows every instance and its engine answerability; `friction eval` and `friction fidelity` print the recorded verdict and the truncation evidence verbatim from `docs/`.

---

## The thesis

Take one SWE-bench ticket. It has a set of **fix sites** (functions the gold patch edits) and a set of **test targets** (functions the failing tests exercise). Build the repository's function-level call graph and look at the **set of bounded paths** between those two node sets. The bet: when fix and test are separated by many long, convergent, cyclic paths through many intermediate functions — high *friction* — an autonomous agent is more likely to fail, because it has to reason across more of the call graph to connect the change to the behaviour under test.

This is a bet, and the go/no-go result is reported above whichever way it went. It went NO-GO. The graph structure between fix and test does not predict agent failure on this cohort. That is the finding, and it is a useful one: it says a plausible, cheap, structure-only signal is not there, and it shows *how* a truncated graph query can fake it being there.

---

## Setup

```bash
git clone <repo> && cd substrate-friction
./setup.sh            # brings up the engine, installs the package, loads the
                      # shipped pre-built subgraphs, warms a real `friction check`
```

`setup.sh` is one command from a clean clone; `just` is **not** required. The engine container is configured (in `docker-compose.yml`) with the large Rust stack the traversal needs:

```
export RUST_MIN_STACK=33554432
```

Convenience recipes (`justfile`):

| Recipe | Does |
|---|---|
| `just up` / `just down` | start / tear down the engine (+ MinIO) via docker compose |
| `just install` | `uv sync --extra dev` |
| `just test` | run the suite (`pytest -m "not engine"`) — **213 pass** |
| `just test-engine` | the 8 engine-marked tests (need a live node) |
| `just probe` | re-measure the engine's capability table |

**Pinned HydraDB engine commit:** `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1, AGPL-3.0). Every number in this README was measured against that build; `docs/pinned-engine-commit.txt` carries the hash.

---

## How HydraDB is used

This is the criterion-#2 section: which graph-native primitives, where, what breaks without them, and why a vector index structurally cannot do the job.

### (a) Which primitives, where

**`algo.MSpaths` with `pairwise: true` — the metric-defining query.** It computes every bounded path from the fix-site set to the test-target set in **one server-side round trip**. `sourceValues`/`targetValues` are lists of **strings** matched against a string `sid` property and **inlined as Cypher literals** (the pinned build rejects a Bolt `$parameter` there with "composite parameter is only supported as an UNWIND input"). The capability probe confirmed `pairwise` **is** available on this build (`docs/engine-capabilities.md`: `"pairwise_supported": true`), so it is used; without it the same call still returns bounded paths between the two sets and only F1's normalisation changes.

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Function', sourceProperty: 'sid', sourceValues: ['…fix sids…'],
  targetLabel: 'Function', targetProperty: 'sid', targetValues: ['…test sids…'],
  relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS'],
  relDirection: 'both', maxLen: 6, pairwise: true, pathCount: 20
}) YIELD path, pathCost RETURN path, pathCost
```

Measured cost of this query on real django code graphs (answered instances, n = 23): **median 14 614.5 ms, p95 29 041.27 ms, max 29 948.75 ms** at `maxLen 6` — it sits right on the engine's 29 999 ms ceiling.

**`algo.SSpaths` with an integer `sourceNode`, `relDirection: 'incoming'`, `maxLen: 1` — fan-in (F6).** `SSpaths` does not accept the `MSpaths` origin spelling: it demands one **integer** `sourceNode` (a string is rejected with "sourceNode must be an integer node id"), and it needs an explicit `pathCount` or it returns only the single shortest path. Fan-in over a set of fix sites therefore issues one such query per site and unions the direct callers client-side. This query is **sub-second and never failed**.

**`UNWIND $rows` batched loading over Bolt — ingest.** `MERGE (n {id: row.id}) SET n:Label, …` for nodes and `CREATE (a {id: row.src})-[:REL]->(b {id: row.dst})` for edges, one hop per batch (the probe established these are the only forms this build accepts). Measured at **22 249.5 edges/sec at batch size 500** (`docs/throughput.md`).

**Honesty in the same breath:** at `maxLen 6` the engine answered only **23 of 43** endpoint-bearing instances. **16 hit the 29 999 ms server timeout** and **4 exhausted the memory pool** (`Neo.TransientError.General.MemoryPoolOutOfMemory`) on the dense 6-hop traversal. The unanswered 20 are recorded as ENGINE-UNANSWERED and are never back-filled from any reference.

### (b) What breaks without it

Without a server-side multi-source/multi-target path primitive, friction for one ticket is **N × M client round trips** — one query per (fix-site, test-target) pair. A modest 3-fix × 7-test ticket becomes 21 separate round trips; at this build's per-call latency the gate stops being something you can sit in a workflow. `MSpaths` with `pairwise: true` collapses all N × M pairs into a single round trip that the engine plans and executes once.

### (c) Why a vector index structurally cannot do this

Friction is defined over the **set of paths between two node sets**. Paths do not exist in a vector space. Two functions with near-identical text sit adjacent in embedding space while lying on completely disconnected execution paths — the embedding is blind to precisely the property being measured. No amount of nearest-neighbour retrieval recovers "how many bounded call-graph paths connect these two functions, how long, how convergent, how cyclic." That is a graph traversal, and it is why the substrate is a graph engine rather than a vector store — even though, as the evaluation shows, the signal itself turned out not to be predictive.

---

## The metric

Six components, computed from the returned path set, then min-max normalised across the instance set (the engine has no `min`/`max` aggregate, so normalisation happens client-side):

| # | Component | Definition |
|---|---|---|
| F1 | Path multiplicity | paths returned ÷ (fix sites × test targets) |
| F2 | Mean path length | mean edge count over the returned paths |
| F3 | Intermediate spread | count of distinct intermediate functions across all paths |
| F4 | Convergence | distinct intermediates ÷ total intermediates (inverted in the score: convergence drives friction up) |
| F5 | Cyclic pressure | fraction of returned paths that revisit a node |
| F6 | Fan-in load | direct-caller count of the fix sites (`SSpaths` fan-in) |

Per-component AUC over the engine-answered instances (`docs/evaluation.md`):

| Component | AUC |
|---|---:|
| F1 | 0.606 |
| F2 | 0.788 |
| F3 | 0.799 |
| F4 | 0.553 |
| F5 | 0.500 |
| F6 | 0.591 |

Best single component is **F3 (0.799)** — but these per-component AUCs inherit the **same `pathCount`-truncation artifact** as the composite and are not evidence on their own. A logistic model fitted on a 70 % train split scores train AUC 0.898 but **held-out AUC 0.542**: with n = 23 the fitted model does not generalise beyond chance, independent of the truncation issue.

---

## Evaluation

**Ground truth.** SWE-bench Verified, 231 django instances, 50 built into per-instance subgraphs. Pass/fail labels come from three published systems in `SWE-bench/experiments`: `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` (**primary**), `20240620_sweagent_claude3.5sonnet`, and `20240402_sweagent_gpt4`.

**The null (headline).** Reference-derived, full path enumeration with no truncation, all 43 endpoint-bearing instances: **AUC 0.565, r = 0.055, p = 0.726**. Restricted to the 23 engine-answered instances the reference gives AUC 0.576 (p = 0.587). The prior full-repo baseline was ~0.567 — the same null on a different route.

**The truncation artifact.** Engine-computed AUC is 0.780 (p = 0.0416) but is a demonstrated `pathCount = 20` artifact — see the fidelity numbers below. Removing only the truncation, on the same 23 instances and same edges, collapses it to 0.576 (p = 0.587).

**Fidelity — the guard firing.**
- *pathCount truncation (same subgraph, same question):* over 22 answered instances with a fully-enumerable reference (1 excluded — its reference enumeration hit its own cap), the engine returned **1021** paths where the reference found **38 720**. Overlap recall **0.0264**, validity precision **1.0**. Largest shortfall: `django__django-11740`. Recall this far below 0.9 is the guard: a path-multiplicity metric scored off 2.6 % of the paths is scoring truncation noise.
- *budget truncation (subgraph vs full graph):* of **36** instances whose fix and test connect within 6 hops in the full repo graph, the engine returned a path for **16** (cohort connectivity recall **0.4444**); restricted to answered instances it is **16/16 = 1.0**. When the query finishes, the budgeted subgraph did preserve the short connections; the cost lands as the ~half of instances the engine cannot answer at all.

**Three confound checks** (`docs/evaluation.md`):

| Check | Value | Reading |
|---|---:|---|
| friction vs repo LOC (Pearson) | −0.113 | friction is **not** a repo-size proxy |
| friction vs patch lines (Pearson) | 0.379 | mild link to patch size |
| repo LOC → failure (AUC) | 0.568 | repo size alone predicts about as weakly as friction |
| patch lines → failure (AUC) | **0.640** | **patch size predicts failure better than friction does** |

**Sensitivity / excluded instances.** 20 engine-unanswered (timeout/OOM) are not scored and not substituted — the answered set is a sample selected for cheap traversability, and the engine's 0.780 must be read in that light. 7 empty-endpoint instances (an endpoint set is empty → zero friction by construction; 4 failed, 3 resolved) are excluded from the scored set; adding them back at minimum friction moves the engine number from 0.780 (n = 23) to 0.631 (n = 30). **Neither survives the fidelity check.** Across systems the engine number is stable (0.780 / 0.836 / 0.770) — which shows the *artifact* is stable, not that the metric is.

Plots: `docs/plots/correlation.png` (friction vs outcome) is regenerated by `uv run python -m friction.harness`; `docs/plots/pair.png` (the demo pair) and `docs/plots/truncation.png` (engine vs full enumeration) are regenerated by `uv run python -m friction.viz` (`friction.viz.generate_demo_figures`). Every figure is generated from the caches by code; none is hand-entered.

---

## Limitations

- **Static call resolution resolves 22.27 % of call sites on django** (188 312 sites, 41 929 resolved). Audited in `docs/call-resolution-audit.md`: this is explainable, not a defect. **34.3 %** of all call sites are duck-typed dispatch on statically-unknown receivers (`x.m()` — unresolvable without type inference), **11.7 %** are builtins/stdlib/third-party correctly out of scope, **8.7 %** are module-level calls with no enclosing function to be a caller node, and **11.1 %** are class instantiations the function→function model deliberately omits. Genuinely reachable misses are only ~**0.65 %**; fixing all three known resolver gaps raises the rate only to ~23 %. Missing `CALLS` edges from dynamic dispatch are therefore inherent to AST-based Python call-graph extraction, and the graph is sparse *by the nature of static Python*, not by a bug.
- **`COVERS` (test → target) over-approximates real coverage**: a static test-to-function association is broader than the functions a test actually exercises at runtime.
- **Python only**, single project (django). The engine's serialized write path means adding writers does not help, which is part of why a small-graph project was chosen.
- **Subgraph truncation.** The per-instance subgraphs are budget-limited BFS balls: **0 of 50 complete all 6 hops** (17 reach 3 hops, 32 reach 4, 1 reaches 5; median 8 672 nodes / 14 283 edges). Every engine query traverses a partial neighbourhood — a second truncation stacked on top of `pathCount`.
- **The `maxLen 6` bound.** Every path query carries a mandatory `maxLen`; 6 is the signal-bearing depth for the metric, and cost grows ≈ (both-degree)^maxLen, so 6 is where django-scale graphs sit on the 30 s ceiling. Lowering it to make a query answerable would truncate exactly the long fix→test paths the metric exists to measure, so unanswered instances are recorded as "no engine path" rather than forced under budget.
- **Path fidelity.** As above, engine recall vs full enumeration is **0.0264** at `pathCount 20` — the single most important limitation, and the reason the engine's own headline number is not trusted.

---

## The object-store defect and the retracted scaling ceiling

This is a genuine, reproducible engine finding handed back to the sponsor, and it is why the project's numbers were **validated rather than assumed**.

**The defect.** The engine's own documented local configuration (`CLOUD_PROVIDER=local`, straight from its README) uses a SlateDB `LocalFileSystem` backend that does not implement conditional puts. After enough sustained writes to trigger a compaction/manifest update (≈ 6 GB of writes, reached by an earlier full-repo build across the 50 graphs), the write path fails permanently:

```
object store error: Operation `put_opts` with mode `PutMode::Update`
not yet implemented by LocalFileSystem(file:///data/graph)
```

From that point **all writes fail permanently** (a restart just reloads the same broken store) — **but reads and `algo.*` traversals keep working**, while query latency also collapses by orders of magnitude. The node keeps serving, so it *looks* healthy: a monitoring check that only reads reports it alive while it is silently write-dead and far slower. Do not rely on read health as a liveness signal.

**The retraction it forced.** An earlier version of this project measured a "150-node traversal ceiling" against exactly that degraded store and wrongly concluded the engine could not compute the metric at scale. It could — the ceiling was the broken object store, not the engine. `docs/engine-scaling.md` carries the retraction in full. On a **healthy** store the corrected sweep (real friction-query shape, `algo.MSpaths`, `pairwise: true`, cold timings) is:

| nodes | edges | maxLen 6 (both-degree ≈ 3, the django operating point) |
|------:|------:|---:|
| 500 | 746 | 191 ms |
| 2 000 | 2 999 | 782 ms |
| 8 000 | 11 998 | 797 ms |
| 16 000 | 23 999 | **1 458 ms** (recommended budget) |
| 34 000 | 50 998 | 27 620 ms (full django scale, on the 30 s ceiling) |

The binding constraint is walk volume ≈ (both-degree)^maxLen, **not** node count: at both-degree ≤ 2 there is effectively no ceiling to 34 000 nodes (every maxLen-6 cell ≤ 571 ms). Real django's traversed density is both-degree ≈ 2.9. **Mitigation:** keep the working set small, or point the node at an S3-compatible backend (the compose file already runs MinIO for exactly this) which *does* implement conditional puts.

---

## Measured throughput

The engineering finding of the ingest path — `UNWIND $rows` batches over Bolt against local object storage (`docs/throughput.md`):

| Batch size | Seconds | Edges/sec |
|---:|---:|---:|
| 250 | 0.634 | 15 783.7 |
| **500** | **0.449** | **22 249.5** |
| 1 000 | 1.03 | 9 712.1 |

Best is **22 249.5 edges/sec at batch size 500**. Roughly 65 000 edges per repository, so three repositories is under 200 000 edges — minutes to load. The engine's write path is serialized; adding writers does not help, which is why the project deliberately targets a small graph.

---

## Attribution

- **[SWE-bench](https://github.com/SWE-bench/SWE-bench)** and **[SWE-bench/experiments](https://github.com/SWE-bench/experiments)** — the Verified split and the published agent trajectories used as ground truth.
- **[tree-sitter](https://tree-sitter.github.io/tree-sitter/)** — Python parsing for symbol and call extraction.
- **HydraDB** — the graph engine, pinned at commit `02a40025d2d57e97ab2754c8256219cdbfeab379`, **AGPL-3.0**. The object-store defect and the corrected scaling sweep above are contributed back.
- **Claude** (Anthropic) — used as a coding assistant while building this project.

---

## License

This project's code is **MIT** (`LICENSE`). The HydraDB engine it runs against is **AGPL-3.0** and is credited above; this repository does not vendor or redistribute the engine, it connects to a separately-run node at `bolt://127.0.0.1:7687`.

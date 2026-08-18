# SUBSTRATE FRICTION — BUILD SPECIFICATION
### Hack Hydra · Track 02B · Code as Graphs

**This document is the complete brief. Build what it describes.** It contains the intent, the competitive reasoning, the engine's hard constraints, the exact data model, every query, the algorithms, the evaluation plan, the demo, and the fallbacks. Read all of Part 1 before writing any code — the engine has restrictions that will silently break naive implementations, and this project has a **day-two go/no-go test** that determines whether it proceeds at all.

---

# PART 1 — CONTEXT AND CONSTRAINTS

## 1.1 What we are building, in one sentence

A pre-flight check that looks at the *structure* of the code around a bug and predicts **whether an AI coding agent will fail on it** — before the agent burns tokens trying.

## 1.2 The thesis

Every tool in this space is trying to make coding agents *succeed*: better retrieval, better context, better prompts. The state of the art is strong — LocAgent reports 92.7% file-level localization accuracy on SWE-bench-Lite (arXiv 2503.09089), SweRank and SWE-Debate push further.

**We are not competing on that. We are asking the inverted question: where will the agent fail, and can we know before it tries?**

The claim: **structural properties of the code around a fix site predict agent failure.** Specifically, when the paths between the code that must change and the tests that validate it are numerous, long, cyclic, and spread across many intermediate nodes, the agent cannot assemble coherent context and its patch fails. That tangle is measurable, and it is measurable *as a graph property* — not as a text property, and therefore not as anything an embedding can capture.

The product: a triage gate. Ticket comes in, friction is computed, and the system says *route this to a human* or *safe for the agent*.

## 1.3 Why this wins the track

Judging is **two-stage**: entries are ranked within their track first, and **only the top entry per track advances**. You compete against Track 02B, not the field.

- **Track 02B is likely the emptiest field in the event.** Teams assume SWE-bench is heavy and stay away. The ones who do enter will build code-graph retrieval — "beat similarity search for context" — which is the track's default reading.
- **We are the only entry not trying to help the agent.** That reframe is the whole differentiator.
- **The output is immediately, obviously useful.** Every engineering manager wants to know which tickets *not* to give the robot. It needs no explanation.
- **The data is tiny.** One repository is roughly 15,000 nodes and 65,000 edges. On an engine with a serialized write path and no bulk loader, this is a decisive structural advantage — ingest cannot kill this project.

Judging criteria and how we hit each:

| Criterion | How we address it |
|---|---|
| Technical execution | AST parsing, graph construction, a real correlation study, a working gate |
| **Use of HydraDB and graph-native approaches** | ~75% of the system is bounded pairwise path traversal. The friction metric *is* a path computation. |
| Product completeness and usability | A CLI/API gate a judge can run against a real issue |
| Quality of results | Measured correlation against real SWE-bench outcomes, with a stated baseline |
| Originality | Nobody predicts agent failure from code structure |

## 1.4 The risk, stated bluntly

**The correlation may not exist.** This is a genuine intellectual bet, not a formality.

Reasons it might fail:
- Many SWE-bench instances are single-line fixes in simple code, which flattens the signal
- Agent failure is often driven by ambiguous *issue text*, not by code structure
- The friction metric may just be a proxy for "big repo," which tells you nothing useful

**Because of this, Part 6 defines a day-two GO/NO-GO test.** Run it before building anything else. If the correlation is flat, Part 9 defines exactly what to pivot to — and that pivot is thesis-certain and reuses everything already built.

**Do not skip the go/no-go. Do not build the UI first.**

## 1.5 Engine constraints — READ BEFORE WRITING ANY QUERY

We build on the **open-source engine** at `github.com/hydra-db/hydradb`. A separate hosted product exists at `api.hydradb.com` with vector search, embeddings, and connectors — **that is a different system and is not what is judged. Do not use it.**

The open-source engine is Rust, AGPL-3.0, an object-store-native graph database on SlateDB over S3-compatible storage, with SuiteSparse GraphBLAS traversal, Bolt 5.x (Neo4j drivers work), and an HTTPS API at `POST /v1/graphs/{graph}/query`.

**It has no vector index, no embeddings, no semantic search, no BM25, no full-text index, no temporal types, and no transactions.**

### Cypher subset — violations are parse errors

| Area | Rule |
|---|---|
| Node matching | **Integer `id` only.** A node with labels or non-id properties must be named. |
| `WHERE` | Only `=`, `<>`, `<`, `>`, `<=`, `>=`, `STARTS WITH`. **No `IN`, `CONTAINS`, `ENDS WITH`, `IS NULL`.** |
| `RETURN` | **`RETURN *` unsupported.** |
| Aggregates | `count`, `sum`, `avg`, `collect` only. **No `min`, no `max`, no `count(DISTINCT)`.** |
| `MERGE` | **id-only.** No `ON CREATE` / `ON MATCH`. |
| `WITH` | **Pass-through only** — no projection, no aliasing. |
| Variable-length paths | **Upper bound mandatory.** `*1..3` works; bare `*` and `*1..` are rejected at parse time. |
| Relationship patterns | Directed and **single-typed**. No `[:CALLS\|IMPORTS*..3]`. |
| Statements | **One per request.** No multi-statement transactions. |
| Property types | **int, float, bool, string only.** No temporal types — encode all time as integer epochs. |

**Direct consequences for this build:**
- Function and file names are **properties, never match keys**. Maintain a `symbol name → integer id` dictionary in the parser.
- The friction score is computed **client-side** from `collect()`ed paths. The engine finds the paths; you do the arithmetic. There is no `min`/`max`, so path-length extremes are computed in your code.
- You cannot traverse `CALLS` and `IMPORTS` in one variable-length pattern. Either run separate queries per edge type, or pass multiple types to `relTypes` in the `algo.*` procedures — which **do** accept a list.

### Path procedures — the crown jewels

| Procedure | Shape |
|---|---|
| `algo.SPpaths` | single source → single target |
| `algo.SSpaths` | single source → all reachable |
| `algo.MSpaths` | **many sources → many targets**, with a `pairwise` mode |

Config keys: `sourceNode`, `targetNode`, `sourceLabel`, `sourceProperty`, `sourceValues`, `targetValues`, `relTypes`, `relDirection`, `maxLen`, `pathCount`.
Yields: `path`, `pathWeight`, `pathCost`.

**`algo.MSpaths` with `pairwise: true` is the heart of this project.** Friction is defined over *all paths between the set of fix sites and the set of tests*. That is a many-to-many path query, computed server-side in one round trip. Doing it client-side would be N×M separate calls.

**Verify the exact `relDirection` enum value in `cypher-compat.md` before writing code.** Sources disagree on `'in'` / `'incoming'` / `'INCOMING'`.

### Performance and operational facts

- **Writes are serialized** at roughly 200–227 commits/sec, flat regardless of writer count. Bulk loading is `UNWIND $rows` batches through the Bolt/HTTP client — the in-process shard API rejects `UNWIND`. **There is no bulk loader.** (For this project the graph is small enough that this barely matters — that is the point.)
- Reads are sub-millisecond to low-millisecond **warm against local object storage**. The same cold query from a laptop to real S3 has been measured at **~27 seconds**. **Demo against local MinIO with a warm cache.**
- **`export RUST_MIN_STACK=33554432`** or the node serves `/readyz` and then aborts on the first query.
- Use **`just` recipes**, never bare `cargo`.
- Requires `libcypher-parser` and SuiteSparse GraphBLAS.
- **`main` is force-pushed frequently. Pin a commit and record it in the README.**
- Beyond ~3 hops traversal tends toward the whole connected component. In a call graph this happens fast — **bound `maxLen` at 5 or 6 and justify it.**

---

# PART 2 — DATA

## 2.1 Source

**SWE-bench Verified** — 500 human-validated instances (a curated subset of SWE-bench, Jimenez et al. 2023). Preferred because the instances are confirmed solvable, which removes a confound: a failure means the agent failed, not that the task was impossible.

**SWE-bench Lite** — 300 instances, lighter, acceptable if Verified is too heavy to set up.

Each instance provides:
- `repo` and `base_commit` — the exact code state
- `problem_statement` — the issue text
- `patch` — the gold fix (tells you the **fix sites**)
- `test_patch` — the tests that validate it (tells you the **test targets**)
- `FAIL_TO_PASS` / `PASS_TO_PASS` — test identifiers

**Outcome labels** — the dependent variable — come from the public SWE-bench leaderboard, which publishes per-instance resolution for many submitted systems. Pick 2–3 published systems and use their per-instance pass/fail as ground truth.

## 2.2 Repository selection

Pick **3–5 repositories** that appear frequently in SWE-bench and are pure Python (parsing simplicity): `django`, `sympy`, `scikit-learn`, `matplotlib`, `astropy` are the usual heavy hitters.

For each repo, check out the relevant `base_commit`. Different instances of the same repo use different commits — either build one graph per commit (accurate, more ingest) or one graph per repo at a representative commit (approximate, faster). **Start with per-repo approximation; upgrade only if the correlation looks promising.**

## 2.3 Scale targets

| Item | Per repo |
|---|---|
| Function nodes | ~10,000–20,000 |
| Class nodes | ~1,500–3,000 |
| File nodes | ~500–2,000 |
| Test nodes | ~2,000–5,000 |
| CALLS edges | ~40,000–80,000 |
| Other edges | ~15,000–25,000 |

**Roughly 65,000 edges per repository.** Three repos is under 200,000 edges total. This loads in minutes even on a serialized write path.

---

# PART 3 — GRAPH DATA MODEL

All ids are non-negative integers assigned by the parser. All property values are int, float, bool, or string.

## 3.1 Nodes

```
Function {
  id: int,
  name: string,          // display only, never matched on
  file_id: int,
  line_start: int,
  line_end: int,
  cyclomatic: int,       // computed by the parser
  is_test: bool
}

Class {
  id: int,
  name: string,
  file_id: int
}

File {
  id: int,
  path: string,          // display only
  repo: int,             // integer-coded repo
  loc: int
}

Test {
  id: int,
  name: string,
  file_id: int
}

ConfigKey {
  id: int,
  key: string,
  file_id: int
}
```

## 3.2 Edges

```
(:Function)-[:CALLS {call_count: int}]->(:Function)
(:Function)-[:DEFINED_IN]->(:File)
(:Class)-[:HAS_METHOD]->(:Function)
(:Class)-[:INHERITS]->(:Class)
(:File)-[:IMPORTS]->(:File)
(:Test)-[:COVERS]->(:Function)
(:Function)-[:READS_CONFIG]->(:ConfigKey)
```

**`COVERS` is the important one and the hardest to get right.** Two options:
1. **Static (default):** a test calls a function, transitively, within `maxLen: 3`. Derive it in the parser from the call graph.
2. **Dynamic (better, slower):** run the test suite with `coverage.py` and record actual coverage. More accurate, but requires executing each repo's suite.

Start static. Upgrade only if the correlation is weak and you suspect `COVERS` quality is the reason.

## 3.3 Instance annotation (not stored in the graph)

For each SWE-bench instance, keep a side-table in your harness:

```
instance_id       → string
repo              → int
fix_site_ids      → [int]   // functions touched by the gold patch
test_target_ids   → [int]   // functions in FAIL_TO_PASS
resolved_by       → {system: bool}   // ground-truth outcomes
```

Fix sites are derived by parsing the gold patch's diff hunks and mapping changed line ranges to `Function` nodes via `line_start`/`line_end`.

---

# PART 4 — INGEST

## 4.1 Pipeline

```
Repo @ base_commit
   ↓
[1] tree-sitter parse (Python)      → AST per file
   ↓
[2] Extract symbols                 → Function / Class / File / Test / ConfigKey
   ↓
[3] Resolve calls                   → CALLS edges (static resolution)
   ↓
[4] Derive COVERS                   → Test → Function within 3 hops
   ↓
[5] Assign integer ids              → symbol dictionary
   ↓
[6] Emit NDJSON row batches
   ↓
[7] UNWIND $rows loader over Bolt   → HydraDB
```

**Everything before step 7 is offline.** Pre-stage as newline-delimited JSON so the loader is pure I/O.

## 4.2 Loader pattern

```cypher
UNWIND $rows AS row
CREATE (f:Function {id: row.id, name: row.name, file_id: row.file_id,
                    line_start: row.ls, line_end: row.le,
                    cyclomatic: row.cc, is_test: row.is_test})
```

```cypher
UNWIND $rows AS row
MATCH (a:Function {id: row.src})
MATCH (b:Function {id: row.dst})
CREATE (a)-[:CALLS {call_count: row.n}]->(b)
```

All nodes before any edges.

## 4.3 Day-one throughput measurement

Same protocol as any project on this engine: `UNWIND` 10,000 edges at batch sizes 500 / 1,000 / 2,000 / 5,000, record wall-clock, compute edges/sec, and record it in the README as a measured finding.

**For this project the expected answer is "fast enough not to matter."** If it isn't, cut to one repository.

## 4.4 Known parsing limitations — declare these

- **Dynamic dispatch** (duck typing, `getattr`, decorators) will produce missing `CALLS` edges. Fall back to conservative type-bound edges.
- **Third-party code** is excluded — skip `site-packages`, `vendor/`, `node_modules/`.
- **Static coverage approximation** overestimates `COVERS` relative to real execution.

State all three in the README. They are honest limitations, not flaws.

---

# PART 5 — THE FRICTION METRIC

This is the technical heart. Define it precisely, compute it entirely from path queries, and report every component separately so a skeptic can see which part carries the signal.

## 5.1 The core query

For one SWE-bench instance, with `fix_site_ids` and `test_target_ids`:

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Function', sourceProperty: 'id', sourceValues: $fixSiteIds,
  targetLabel: 'Function', targetProperty: 'id', targetValues: $testTargetIds,
  relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS'],
  relDirection: 'BOTH',
  maxLen: 6, pairwise: true, pathCount: 20
}) YIELD path, pathWeight, pathCost
RETURN collect(path) AS paths, collect(pathCost) AS costs
```

One call. All fix sites against all test targets. Everything below is computed client-side from that result.

## 5.2 The six components

| # | Component | Definition | Intuition |
|---|---|---|---|
| **F1** | Path multiplicity | Number of distinct paths returned, normalised by pairs | Many routes = many ways to be wrong |
| **F2** | Mean path length | Average hop count | Long chains = context assembly is hard |
| **F3** | Intermediate spread | Count of distinct intermediate nodes across all paths | Wide blast area = large context needed |
| **F4** | Convergence ratio | `F3 / total nodes on all paths` | Low ratio = paths funnel through few nodes (easier) |
| **F5** | Cyclic pressure | Fraction of paths revisiting a node, or paths existing in both directions between the same pair | Cycles defeat linear reasoning |
| **F6** | Fan-in load | Sum of in-degree of fix-site functions | Many callers = many ways to break something else |

**F6 needs its own query:**

```cypher
CALL algo.SSpaths({
  sourceLabel: 'Function', sourceProperty: 'id', sourceValues: $fixSiteIds,
  relTypes: ['CALLS'], relDirection: 'INCOMING',
  maxLen: 1, pathCount: 500
}) YIELD path
RETURN count(path) AS fan_in
```

## 5.3 The score

Normalise each component to 0–1 across the instance set (z-score then clamp, or min-max — computed client-side, since the engine has no `min`/`max`).

```
Friction = w1·F1 + w2·F2 + w3·F3 + w4·(1−F4) + w5·F5 + w6·F6
```

**Do not hand-tune the weights and present it as a discovery.** Fit them on a training split, evaluate on a held-out split, and report both. If you have too few instances to split, use equal weights and say so — an unweighted score that correlates is more credible than a tuned one that overfits.

**Report every component's individual correlation.** If one component carries all the signal, that is the actual finding, and it is more interesting than a composite.

---

# PART 6 — THE GO/NO-GO TEST ⚠️

**Run this on day two, before building anything else.** It determines whether the project proceeds.

## 6.1 Protocol

1. Pick **one** repository well represented in SWE-bench (django is the usual choice).
2. Parse it, build the graph, load it. One repo only.
3. Take **50 instances** from that repo with known outcomes from the public leaderboard.
4. Compute Friction for all 50.
5. Compute the correlation between Friction and failure. Report **point-biserial correlation** and **AUC** for predicting failure.

## 6.2 Decision rule

| Result | Action |
|---|---|
| **AUC ≥ 0.65** | **GO.** Signal is real. Build the full project. |
| **AUC 0.55–0.65** | **Weak.** Check whether one component alone does better. If yes, drop the composite and build around that single component. If no → pivot. |
| **AUC < 0.55** | **NO-GO.** The thesis does not hold. Pivot immediately per Part 9. |

## 6.3 Confounds to check before believing a positive

- **Does Friction just measure repo size?** Correlate Friction with repo LOC. If they track closely, you have a size proxy, not a structural finding. Normalise by repo size and re-run.
- **Does Friction just measure patch size?** Correlate with the gold patch's line count. If the correlation is with patch size, say so — it is still a useful predictor, but it is a *different* claim and must be framed honestly.
- **Is it stable across systems?** Check the correlation against 2–3 different published agents' outcomes. If it only holds for one, it is measuring that agent's quirks, not the code.

**Report all three confound checks in the README regardless of outcome.** This is what separates a credible result from a lucky one.

---

# PART 7 — THE PRODUCT

## 7.1 The gate

A CLI and a small HTTP API:

```
$ friction check --repo django --issue 15738

  Fix sites (predicted):     3 functions
  Test targets:              7 functions
  ─────────────────────────────────────
  Path multiplicity   F1     0.82  ████████▏
  Mean path length    F2     0.71  ███████▏
  Intermediate spread F3     0.90  █████████
  Convergence         F4     0.34  ███▍
  Cyclic pressure     F5     0.88  ████████▊
  Fan-in load         F6     0.65  ██████▌
  ─────────────────────────────────────
  FRICTION SCORE            0.79  HIGH

  ⚠  Predicted agent failure probability: 78%
  →  RECOMMENDATION: route to human engineer

  Query: CALL algo.MSpaths({...}) — 1 round trip, 34ms
```

**Print the Cypher and the timing.** A judge assessing "use of HydraDB" needs to see the engine working.

## 7.2 The visualization

One view: the subgraph between fix sites and tests, rendered. Fix sites in blue, tests in green, intermediates in grey, edges weighted by path participation. High-friction instances look like a hairball; low-friction ones look like a clean line. **The visual difference between a high- and low-friction instance is the demo.**

## 7.3 Setup — ship your own one-command install

There is no official one-command setup for the engine. **Build one.** `docker-compose.yml` bringing up `graph-node` + MinIO + the loader + a pre-parsed graph, plus `./setup.sh`, targeting **under 60 seconds to a working `friction check`**.

Ship the pre-parsed graph as a data file so judges don't have to run tree-sitter over Django.

## 7.4 Demo video — ≤3:00, hard stop

Order is specified: problem → project → demo → HydraDB.

| Time | Content |
|---|---|
| 0:00–0:25 | **Problem.** "Everyone is trying to make coding agents smarter. Nobody is asking the cheaper question: which tickets should we not give them at all?" |
| 0:25–0:40 | **What we built.** Substrate Friction, on self-hosted open-source HydraDB. One command. |
| 0:40–1:20 | **MONEY SHOT.** Two issues side by side. Run the gate on both. First: friction 0.21, clean thin graph, **SAFE FOR AGENT**. Second: friction 0.79, the graph explodes into a hairball, **ROUTE TO HUMAN**. Then reveal the ground truth: the agent solved the first and failed the second. *"We knew before it tried."* |
| 1:20–1:50 | **The evidence.** The correlation plot across 50+ instances. AUC. The confound checks. *"This isn't repo size and it isn't patch size — we checked."* |
| 1:50–2:30 | **Why HydraDB.** `algo.MSpaths` pairwise: all fix sites against all test targets in one server-side call. Show the query and the 34ms. *"Friction is a path computation. Without many-to-many bounded traversal this is 21 separate round trips per ticket."* |
| 2:30–3:00 | **Results and limits.** AUC, sample size, stated limitations. Repo link. Stop. |

## 7.5 README — required sections

1. **What this is**
2. **The thesis** — inverted question, in plain language
3. **Setup** — copy-pasteable, `export RUST_MIN_STACK=33554432`, `just` recipes, **pinned HydraDB commit hash**
4. **How HydraDB is used** — the section that wins criterion #2:
   - Which primitives, where: `algo.MSpaths` with `pairwise: true` computes all fix-site↔test paths in one call; `algo.SSpaths` computes fan-in
   - What breaks without it: N×M client round trips per ticket; the gate becomes too slow to sit in a workflow
   - Why a vector index categorically cannot do this: friction is defined over *the set of paths between two node sets*. Paths do not exist in a vector space. Two functions with near-identical text sit adjacent in embedding space while being in completely disconnected execution paths — the embedding is blind to exactly the property we measure.
5. **The metric** — all six components, defined
6. **Evaluation** — AUC, sample size, **all three confound checks**, and the negative results
7. **Limitations** — dynamic dispatch, static coverage approximation, single-language, `maxLen` bound
8. **Measured throughput**
9. **Attribution** — SWE-bench, tree-sitter, leaderboard data, LLM APIs, AI coding assistants
10. **License** — OSI-approved LICENSE in repo root

---

# PART 8 — SCHEDULE

Deadline: **20 August 2026, 11:59 PM PT** = **21 August, 12:29 PM IST**.

| Day | Deliverable |
|---|---|
| **Day 1** | Node on local MinIO with `RUST_MIN_STACK`. Cypher round-trip. Throughput measured. Fresh public repo + license. Engine commit pinned. SWE-bench Verified downloaded. One repo parsed with tree-sitter. |
| **Day 2** | Graph loaded for one repo. Fix sites and test targets extracted for 50 instances. **RUN THE GO/NO-GO TEST (Part 6). Decide before day three.** |
| **Day 3** | GO: expand to 3 repos, compute friction across 150+ instances, run confound checks. NO-GO: pivot per Part 9. |
| **Day 4** | Weight fitting on a train/test split. Correlation plot. AUC locked. |
| **Day 5** | CLI gate + visualization. Query and timing displayed. |
| **Day 6** | **HARD FEATURE FREEZE, end of day.** Numbers locked. README written. |
| **Day 7** | Docker compose + `setup.sh` + pre-parsed graph shipped. Clean-clone test on another machine. Record video twice. |
| **Day 8** | Polish, edit, **submit early**. Verify every link in incognito. |
| **Day 9** | Buffer only. |

---

# PART 9 — THE PIVOT (if go/no-go fails)

If AUC < 0.55, **do not try to rescue the thesis.** Pivot on day three. Everything already built — parser, graph, loader, path queries — carries over completely.

## Pivot target: COMMON CAUSE

**Thesis-certain. Retrospective instead of prospective.**

**The idea:** Take many past bugs in a repository. Trace each one's path from entry point to fix site. Find the intermediate node that appears on the **most independent bug paths**. That is the load-bearing structural element — fix it once, prevent the most future incidents.

**Why it's safe:** it makes no predictive claim. It measures something that demonstrably exists — which nodes lie on the most historical incident paths.

**Same graph. Same query, different inputs:**

```cypher
CALL algo.MSpaths({
  sourceLabel: 'Function', sourceProperty: 'id', sourceValues: $issueEntryPoints,
  targetLabel: 'Function', targetProperty: 'id', targetValues: $fixSites,
  relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS'],
  relDirection: 'BOTH', maxLen: 6, pairwise: true, pathCount: 10
}) YIELD path
RETURN collect(path) AS incident_paths
```

Tally intermediate-node frequency across *independent* instances client-side. Rank. The top node is the common cause.

**Validation:** hold out 20% of instances. Does the top-ranked node from the training set also appear on held-out incident paths more than chance? Baseline: PageRank, raw in-degree, global betweenness.

**Framing:** aviation crash investigation. Investigators don't fix individual crashes — they find the *latent condition* shared across many. That is exactly what this computes, for code.

**Money shot:** fifty red threads from unrelated bugs fan across the repo graph, then all bend through one node that flares white. *"Fifty incidents. One load-bearing wall."*

**Honest caveat to state:** with only dozens of instances the top node may be unstable. Report confidence intervals, not a single name.

---

# PART 10 — FAILURE MODES

| Risk | Mitigation |
|---|---|
| **The correlation isn't there** | The go/no-go test on day two. Pivot to Common Cause on day three. Zero wasted work. |
| Friction is a size proxy | Confound check §6.3. Normalise by repo LOC and re-run. |
| Friction is a patch-size proxy | Confound check §6.3. If true, reframe honestly as a different claim. |
| Only works for one agent | Test against 2–3 published systems. If it's agent-specific, say so. |
| Dynamic dispatch breaks the call graph | Conservative type-bound fallback edges. Declare the limitation. |
| Too few instances to split train/test | Use equal weights, state it, report unweighted correlation. |
| `maxLen` too low → no paths; too high → everything connects | Tune on the pilot repo. Report the chosen bound and why. |
| Cold-storage latency in the demo | Local MinIO, warm cache, rehearsed path. |
| Hitting unsupported Cypher | `cypher-compat.md` open. Integer ids only. Bound every path. |
| Judges can't reproduce | Ship compose + `setup.sh` + **pre-parsed graph**, so nobody runs tree-sitter over Django live. |

---

# PART 11 — DEFINITION OF DONE

- [ ] Public GitHub repo, OSI license, **no commits before the build window opened**
- [ ] `./setup.sh` gives a working `friction check` from a clean clone in under 60 seconds
- [ ] Go/no-go test run and **its result reported**, whichever way it went
- [ ] Friction computed across 150+ instances (or Common Cause across equivalent), with train/test split
- [ ] **All three confound checks run and reported**
- [ ] CLI prints score breakdown, recommendation, **the Cypher, and the timing**
- [ ] Visualization contrasts a high-friction and a low-friction instance
- [ ] Video ≤ 3:00, correct order, money shot before 1:20
- [ ] README has all ten sections from §7.5, including limitations and negative results
- [ ] Pinned engine commit recorded
- [ ] Submitted early with every link verified in incognito

---

# PART 12 — ANTI-GOALS

**Do not:**
- Use the hosted product at `api.hydradb.com` or any of its features. Different system, not judged.
- **Try to beat LocAgent's 92.7% localization accuracy.** That is not this project. We predict failure; we do not do retrieval.
- Build a code-search or context-retrieval tool. That is the track's default and what everyone else will submit.
- Skip the go/no-go test. It exists precisely because the thesis might be wrong.
- Hand-tune weights and present the fit as a discovery.
- Hide a negative result. A clearly-reported null finding with three confound checks is more credible than a hedged positive, and judges can tell the difference.
- Use `IN`, `CONTAINS`, `min()`, `max()`, `RETURN *`, unbounded `*`, or multi-typed variable-length patterns. They will not parse.
- Match nodes on strings. Integer ids only.
- Parse more than one language. Python only; say so.
- Add a seventh friction component. Six, then freeze.

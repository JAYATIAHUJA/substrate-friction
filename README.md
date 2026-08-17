# Substrate Friction

[![HydraDB verify](https://github.com/areycruzer/substrate-friction/actions/workflows/hydra-verify.yml/badge.svg)](https://github.com/areycruzer/substrate-friction/actions/workflows/hydra-verify.yml)

**Before your tool skips a test, measure the graph it trusted.**

Graph-based test selection is a good idea: build a call graph, walk backwards
from the change, run the tests it reaches, skip the rest. It is also unsafe in a
way that is invisible from inside the tool — the walk can be provably complete
with respect to the graph while the graph is missing the edge that mattered.
**An extractor cannot fail-closed on an edge it never knew existed.**

`friction gate` measures the thing that is load-bearing: **what fraction of
tests known to guard a fix does this graph let you reach?** The label is free —
SWE-bench's `FAIL_TO_PASS` test *is* the test that guards the fix.
On **172 labelled SWE-bench instances across 7 repositories** (study S1,
`docs/studies.md`; emitted by `scripts/gate_corpus.py`). One sentence so no
two numbers in this README can read as a contradiction: **the type-resolved
graph reaches the guarding test 0.545 of the time on django and 0.419 pooled
across all 7 repos — the per-repo spread (1.00 down to 0.00) is itself the
finding.** Django-only figures appear below wherever a section predates the
corpus run; every figure names its scope.

| Graph | Recall of the guarding test | Safe to skip? |
|---|---|---|
| Name-matched — the class Aider, RepoGraph and LocAgent build | **0.314** (37/118) | **No** |
| Type-resolved — scip-python / pyright | **0.419** (72/172) | **No** |
| Type-resolved + dynamic execution traces (django subset) | **0.67** (12/18) | **No** |

Per-repo spread is enormous — django 24/44, xarray 19/21, **matplotlib 0/33 and
pytest 0/19** (guarding tests in a *different graph component*: dynamic dispatch
is invisible to both extractors), and two tiny repos at 1.0 (requests 8/8,
sympy 3/3 — n too small to clear any bar). Full table: [`docs/gate.md`](docs/gate.md).

The 7-repo corpus itself (~4.5 GB of graphs and SCIP indexes) cannot ship in a
50 MB payload; what ships is its committed output — per-instance outcomes in
`data/shipped/gate-results.json`, re-derivable by `friction verify` — with the
cut documented in [`data/shipped/README.md`](data/shipped/README.md).

Bar for skipping: 0.95 (a CLI flag). Nothing measured here comes close, and the
ranking does not depend on where the bar sits. Full report: [`docs/gate.md`](docs/gate.md).

```bash
friction gate --arm arm_b                      # exits 1: RUN_FULL
friction gate --instance django__django-10097  # the replay: graph-complete walk,
                                               # 0 of 370 guarding tests selected
friction gate --repo <path> --changed <file>   # gate YOUR repo (prior stated as a prior)
friction gate --instance ... --live            # the same replay executed IN the engine:
                                               # graph loaded live, walk in ~1-3 ms,
                                               # engine/offline parity asserted
```

**"Use a better extractor" is not a fix.** The full name-match → pyright
type-resolution upgrade moves paired recall by **+0.071** (n=28, exact McNemar
p=0.73). Sui et al. (ICSE 2020) reported the same separation for Java: precision
and recall of a static analysis are separate concerns. The measurement behind
that claim, and everything under it, is below.

---

## The substrate measurement behind the gate

**Every AI coding agent that reads your repository builds a graph of it first — and Aider's repo map, RepoGraph, and LocAgent all build that graph by matching identifier _names_. We built both arms of the same django commit — one name-matched, one type-resolved — and measured what name matching costs: a precision ceiling of `0.746`, recall `0.352` of the true graph, Jaccard `0.3143`. A quarter of a name-matched graph's in-scope edges do not survive contact with type resolution, and they fail in a structured, nameable way.**

![Pruning wrong edges on django-11490](docs/plots/prune.png)

_Above: the fix-site neighbourhood of `get_combinator_sql()` in `django__django-11490`. The name-matched arm draws **21** edges; type resolution confirms **12** and leaves **9** unconfirmed (red). **Four of those nine** red edges are one collision — `list.extend` name-bound to a GIS class. This is the whole thesis in one picture, and it is the `docs/demo.html` money shot._

This is a measurement of the **substrate** every localization and retrieval tool in this space stands on. It holds regardless of what you build on top. Everything else here — a directional connectivity finding, a graph engine used the way graphs want to be used, and an honestly-null failure predictor — is the scaffolding that produced the measurement and the results it produced along the way, reported without dressing up.

---

## What this is

Take one SWE-bench django ticket. To reason about it structurally you first need a call graph, and _how you build that graph_ is a choice with consequences nobody in this space has measured against a type-resolved reference on real code. We build the same repository two ways and compare them edge-for-edge:

- **Arm A — name-matched.** A call `x.foo()` becomes an edge to _every_ function named `foo`. This is how Aider's repo map, RepoGraph (arXiv 2410.14684), and LocAgent (arXiv 2503.09089) build their graphs.
- **Arm B — type-resolved.** The same repository indexed with `scip-python` (pyright-backed), so `x.foo()` resolves to `foo` on the _actual static type_ of `x`, or to nothing when the receiver's type is unknown.

Same repo, same commit, same extraction of definitions. Only edge resolution differs. Both arms are resident in one HydraDB engine at once, in disjoint id bands, so the comparison is a single-engine operation.

### Quickstart

```bash
git clone <repo> && cd substrate-friction
./setup.sh                                   # engine up, package installed, shipped
                                             # working set loaded, live gate warmed
friction check   --issue django__django-10554   # THE GATE: real count(*) Cypher + latency
friction compare --issue django__django-10973   # arm A (name-matched) vs arm B (type-resolved)
```

`setup.sh` runs from a clean clone with no manual steps (cold: about 77 s to a working gate — honest, not sub-60s). `friction compare`, `precision`, `connectivity`, `eval`, and `list` are cache-backed and read the committed `docs/` reports and `data/…/arms/` caches; they need no live engine. Only `friction check` and `friction serve` touch the running engine.

**CLI:** `friction gate / check / compare / precision / connectivity / eval / list / serve`.
**API:** `GET /health /gate /gate/{id} /instances /check/{id} /compare/{id} /precision /connectivity`.

### Use it from a coding agent (MCP)

The 2026 abstention literature (AgentAbstain, ReDAct) has agents defer on their
own *internal* uncertainty — and finds that ability does not scale with model
size. The gate supplies the missing **external** signal: a measured statement
about the graph an agent's conclusion rests on. Any agent conclusion built on a
graph traversal — affected tests, blast radius, related files — inherits that
graph's recall.

```json
{"mcpServers": {"substrate-friction": {"command": "friction-mcp"}}}
```

Two task-shaped tools (several targets per call, one round trip):
`gate_check` — is a skip defensible on this graph class? — and `gate_explain` —
replay labelled instances, dropped guarding tests and the engine Cypher
included. Runs against the open-source engine and the committed corpus; no
hosted service, no credentials.

### The pinned split

`data/shipped/split.json` pins a dev/sealed partition by `sha256(instance_id)`,
committed **before** the measurement. There are no fitted parameters in the
selector, so this is not a train/test split — it tests whether choices made
while looking at django (the hop bound, the identity join) hold on unseen
instances. They do: dev 0.548 vs sealed 0.538 on arm B (`docs/gate.md`).

---

## Finding 1 — the substrate: what name matching costs

On django (commit `b9cf764`), arm A produced 18,774 call edges. Restricting to edges whose source is in scope and mappable onto the shared identity space leaves **5,873** arm-A edges to compare against arm B's internal edges:

| Measure | Value |
|---|---:|
| Compared (in scope) | **5,873** |
| Confirmed by arm B (both) | **4,381** |
| In arm A only, unconfirmed | **1,492** |
| True edges arm A missed (only in arm B) | **8,064** |
| **Arm A precision (ceiling)** | **0.746** |
| Arm A recall of the true graph | **0.352** |
| Jaccard | **0.3143** |

The unconfirmed edges are not random. They cluster on container-method names that collide across the codebase:

![Where the unconfirmed edges point](docs/plots/offenders.png)

| Target | Unconfirmed | What it actually is |
|---|---:|---|
| `extend` | **139** | `list.extend` name-bound to a GIS class |
| `lower` | **125** | `str.lower` bound to `django.template.defaultfilters.lower` |
| `cursor` | **54** | the counter-example — see below |
| `import_module` | **33** | |
| `search` | **31** | |

A name matcher cannot tell `list.extend` from a GIS method called `extend`; it draws an edge to both. (In v1's tree-sitter graph the same failure wired Python's builtin `super()` to `django/template/loader_tags.py::BlockNode.super` **1,321 times** — see the retraction below.)

### `0.746` is a ceiling — read it in both directions

pyright emits **no** occurrence when a receiver's type is unknown; it never invents an edge. So an arm-A edge missing from arm B is _either_ a genuine false positive _or_ a real call pyright declined to resolve. The direction of arm B's bias is fixed: it under-reports. Therefore **true precision is `>= 0.746`, never `<=`.** State it that way every time the number appears.

The `cursor` block of **54** unconfirmed edges is the clean counter-example: real `self.connection.cursor()` calls on an untyped receiver, where pyright emits nothing and arm B under-reports. **Here arm A was right and the type-resolved graph is the incomplete one.** We report the ceiling as a ceiling precisely so this case is not hidden.

### What the wrong edges cost — a projection, not a measurement

Projected localization cost of a name-matched graph of this quality: **1.2pp to 2.0pp** of resolve rate (interval `[0.0119, 0.0197]` as a fraction of instances). This is **an analogy to ARISE's published ablation band, not a resolve-rate delta we measured** — we did not run SWE-bench.

- **Basis.** ARISE (arXiv 2605.03117) improved call-graph edge quality on SWE-bench Lite and moved end-to-end resolve **17.3% → 22.0%** and Function Recall@1 **0.43 → 0.60**. We map our measured edge quality onto that band by analogy, the way ARISE's own band is stated as an interval.
- **Corroborating, cited not reproduced.** SHERLOC (arXiv 2606.24820): +5.95pp mean and _negative_ transfer from bad localization. RGFL (arXiv 2601.18044): wrong-element localization implicated in **53%** of unresolved instances.

_Source: `docs/precision.md`, `docs/graph-delta.md`. Reproduce: `uv run python scripts/graph_delta.py --repo data/repos/django --out docs/graph-delta.md`._

---

## Finding 2 — direction: the relation every prior version measured backwards

Nobody has published this. Measured over 44 django instances that carry both a fix-site set and a test-target set, bounded at 6 hops:

![The direction finding](docs/plots/direction.png)

| Direction | Connected | What it means |
|---|---:|---|
| **fix → test** (directed) | **0/44 (0%)** | Code does not call tests. The direction every prior spec used was backwards. |
| **test → fix** (directed) | **24/44 (55%)** | The clean semantic: tests call the code they exercise. |
| **undirected** | **43/44 (98%)** | "Shares a neighbourhood" — _not_ "the test exercises this code." |

Two consequences. First, `fix → test` is `0/44` because production code has no edge to the test that guards it; the natural directed relation is `test → fix` at **55%**. Second, the jump from `55%` to `98%` is the pytest fixture / `setUp` / `parametrize` / framework-dispatch closure: a test reaches its code through dispatch that a static call graph structurally cannot record. Dropping direction recovers those instances, but it recovers them by measuring a weaker, symmetric relation.

**Every v1/v2 friction number used `relDirection: 'both'`** and therefore measured the weaker "shares a neighbourhood" property, never directed `test → fix` coverage. Report the two measures separately; never present the undirected number as evidence a test covers a fix.

_Source: `docs/connectivity.md`._

---

## Dynamic COVERS — the edge type the spec called the hardest, and what it actually recovers

The build spec named an executed `Test -> Function` edge — "COVERS" — **"the important one and the hardest to get right."** It had never been built. `src/friction/trace.py` and `src/friction/covers3.py` now build it: each instance's own `FAIL_TO_PASS` tests run under `sys.settrace` at the instance's `base_commit`, in a `uv`-provisioned interpreter matching that instance's django version (django 3.0 cannot import on the 3.12 host — it needs 3.9), and the **executed** `Test -> Function` call edges are recorded and folded into the type-resolved arm B graph.

- **18 instances traced live, all succeeded.**
- Representative cost: `django__django-11163` = **5,921** call edges / **3,215** functions entered / **6.9 s**; `django__django-10880` = **4,603** edges / **2,629** functions / **3.3 s**. The tracer runs at **~2 s per test module**.
- **63%** of fix sites have their module executed by the tests.

### The identity correction — reported, not hidden

The first run recorded each executed function by its bare `co_name` (`save`, `__call__`), but arm B's nodes are SCIP **class-qualified** symbols. Only a module-level function could ever rejoin, so **69 of 23,043 COVERS edges mapped (0.3%)** and the connectivity gate read a false RED — no improvement. Qualifying the names (prefer `co_qualname` on 3.11+, otherwise reconstruct the class from `self`, or `cls` for a classmethod) lifted strict edge mapping from **0.3% to 27.6%** — about **90x**. This is the same class of error this project has retracted before — a false result produced by a naming artifact, not a property of the tests — so it is recorded here as a correction rather than quietly replaced.

### The gate, after the fix (18 instances, directed test -> fix)

| Corpus | test -> fix |
|---|---|
| Traced subset (18), static only | **11/18 (61%)** |
| Traced subset (18), + COVERS (strict SCIP identity, qualified tracer) | **12/18 (67%)** &nbsp; &larr; **AMBER** |

Folding COVERS in moves the gate by **+1** instance: `django__django-11265` flips disconnected -> connected. The improvement is **real and modest** — not a multiplier. **`61% -> 67%` does not rescue the prediction thesis, and we do not claim it does**; the headline remains the substrate finding.

### The residual, diagnosed not hand-waved

27.6% is not higher because `type(self).__name__` gives the **runtime subclass**, while the executed code object's file is the **base-class definition site** — so those edges key to a class SCIP does not have at that path. Closing that gap needs MRO-based definition-site resolution. The remainder is `<module>` import bodies and staticmethods.

**The finding this supports — the contribution.** Static call graphs miss executed `test -> code` relationships, and even dynamic tracing only partially recovers them, because **runtime class identity and definition-site identity disagree**. That is a substrate observation, and it is the same spine as the headline: what a name-matched graph costs. COVERS does not change the headline; it corroborates it from the dynamic side.

_Source: `docs/covers.md`, `src/friction/trace.py`, `src/friction/covers3.py`._

---

## The restored graph schema — all 5 spec node types, all 7 spec edge types

The build spec asked for **five node types** and **seven edge types**; the shipped graph had carried exactly two (`Function` nodes, `CALLS` edges — the emitter kept only those). Arm B now emits and round-trips all of them. Per-instance census, type-resolved arm B, `django__django-10097`:

| Node type | count | | Edge type | count |
|---|---:|---|---|---:|
| `File` | 1,680 | | `CALLS` | 57,314 |
| `Class` | 8,043 | | `DEFINED_IN` | 22,459 |
| `Function` | 7,592 | | `HAS_METHOD` | 20,832 |
| `Test` | 14,867 | | `INHERITS` | 6,639 |
| `ConfigKey` | 145 | | `IMPORTS` | 4,999 |
| | | | `READS_CONFIG` | 608 |
| | | | `COVERS` | 36 |

`COVERS` at **36** against **57,314** `CALLS` is a **sparse dynamic overlay**, not graph-wide coverage: it says "this test executed this function" for a small, honestly-counted set folded in by `friction.covers3`, and **must never be read as "the suite covers the code."** `READS_CONFIG` (~608 edges over ~145 distinct `ConfigKey`s per instance) is static and substantial, nowhere near zero. `Test` nodes outnumber `Function` nodes because django's suite is enormous — every `test_*` method under a `tests/` root is a `Test`.

_Source: `docs/schema.md`, `src/friction/arms.py` (`emit_typed_arm`), `src/friction/loader.py`._

---

## Finding 3 — the engine: bounded reachability stays cheap and always returns where path enumeration hits the 30 s wall

The metric v2 asked for — the number of bounded paths between two node sets — is **#P-complete** (Valiant 1979). It is not slow; it is intractable, and on a dense django graph the engine's `algo.MSpaths` enumeration hit the hard **30,000 ms** timeout.

The fix is to ask a different, tractable question with the same intuition: **bounded reachable-set size**, computed in-engine as a masked-BFS `count(*)`.

```cypher
MATCH (s {id: 41000000000})-[:CALLS*1..6]->(n) RETURN count(*) AS n
```

Against a walk-correct networkx reference this is **exact at every k** — a standing `@pytest.mark.engine` test on a 1,000-node out-degree-3 graph. Its cost is bounded by the visited **set** (≤ graph size), not by walk volume, so it always returns. Measured honestly on **one 34,000-node graph at django density** (both-degree ≈ 2.9), `count(*)` answers in **6–10 ms** from a typical source and up to **6.5 s** from the busiest hub (which reaches 12,710 nodes), while `algo.MSpaths` path enumeration on that **same graph** costs **~15 s** from mid-graph seeds and **~24 s** from a hub — grazing the **30 s** ceiling, and timing out on it in other cold runs. The honest ratio is **~1,500–2,300× at the typical operating point, and unbounded — enumeration times out — at the busiest source** (`docs/latency.md`). The two graphs are kept distinct: at 1,000 nodes enumeration finishes in ~200 ms and does not time out; the 30,000 ms timeout is the ~34,000-node django graph. The earlier single "~2,500×" came from comparing those two different graphs and is retracted.

![Reachability latency vs the enumeration wall](docs/plots/latency.png)

The exactness claim is a standing `@pytest.mark.engine` regression test: it seeds a fresh 1,000-node out-degree-3 graph, rebuilds it in networkx, and asserts the engine's `count(*)` equals the reachable-set size at every `k = 1..6` — zero mismatches. When the gate runs `friction check` it issues that same query live and **prints its own measured latency — run `friction check` to see yours** on your store.

**A syntax finding that matters:** `RETURN count(n)` where `n` is a node is **rejected** by this build the moment a traversal precedes it (`"property values support integer, float, boolean, and string literals"`). The working form is `RETURN count(*)`; `count(n.id)` also works. The keystone query only parses in the `count(*)` form.

### How HydraDB is used

**Both arms resident at once, in disjoint id bands.** Arm A and arm B of the same commit live in one `default` graph in non-overlapping integer-`id` bands, so "diff the name-matched graph against the type-resolved graph" is a single-engine operation, not a cross-database join. Every edge count in Finding 1 depends on this.

**Bounded reachability, in-engine.** `MATCH (s {id:N})-[:CALLS*1..k]->(n) RETURN count(*)` lowers to a masked GraphBLAS BFS whose cost is `O(m)` per hop, bounded by the _visited set_, not by walk volume. The frontier is finite; the path set is not. That is why the cost is bounded by the reachable-set size and always returns — flat in `k` for a typical source, and still only a few seconds from the busiest hub (`docs/latency.md`) — where enumeration is exponential in `k`. The variable-length pattern carries a mandatory upper bound, is single-typed, and matches on integer `id`.

**Why a vector index structurally cannot do this.** The relations here — a bounded reachable set, a directed `test → fix` connection, the confirmed-vs-unconfirmed edge split — are defined over **reachable sets and cuts in a specific edge set.** Paths and cuts do not exist in an embedding space. Two functions with near-identical text sit adjacent in vector space while lying on completely disconnected call paths; nearest-neighbour retrieval is blind to precisely the property being measured. No embedding recovers "how many bounded call-graph paths connect these two nodes, and in which direction" — that is a graph traversal over resolved edges, which is why the substrate is a graph engine.

_Source: `docs/latency.md` (both queries measured on one django-scale graph; reproduce with `uv run python -m scripts.latency_measure`), `src/friction/reach.py`, `tests/test_reach.py` (`@pytest.mark.engine`), `docs/engine-scaling.md`. Pinned engine commit `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1, AGPL-3.0), recorded in `docs/pinned-engine-commit.txt`._

---

## The honest secondary result — the friction predictor is a scoped, and now SIGNIFICANT, NO-GO

We also asked whether directional structure features predict per-instance agent failure. **They do not — and with the corpus quadrupled from one repo to seven, we can now say so at a significance threshold instead of shrugging.** Ground truth: `20241029_OpenHands-CodeAct-2.1-sonnet-20241022`, **`n = 172` across 7 repos** (each carrying both a fix-site and a test-target set), class balance **86 failed / 86 resolved**. `failed=True` is the positive class.

The scoped question is now a **leave-one-repo-out** test — train on the other repos, predict the held-out one — so the model can never memorise repo identity (a known difficulty proxy).

| Measure (same instances) | Value |
|---|---:|
| Pooled held-out AUC, our features | **0.483** (at or below chance) |
| Pooled held-out AUC, `patch_lines` | **0.628** |
| Best feature in-sample (`fanin`) | 0.567 |
| Best baseline in-sample (`patch_lines`) | 0.656 |
| DeLong `AUC(fanin) − AUC(patch_lines)` | **z = −1.996, p = 0.046** |
| Bootstrap ΔAUC (`fanin` − `patch_lines`) | **−0.089, 95% CI [−0.178, −0.003]** |

Per-repo held-out AUC: django `0.494` | matplotlib `0.474` | pytest `0.444` | requests `0.688` | sphinx `0.551` | xarray `0.620` | sympy n/a (0 failures, single class).

**This is a stronger result than the earlier inconclusive shrug, and we say so plainly.** At `n=44` the difference could not be resolved and every CI bracketed zero. At `n=172`, **patch scope significantly beats the directional metric** — DeLong `p = 0.046`, and the bootstrap 95% CI on the gap excludes zero, sitting below it. Out of sample the features collapse to at-or-below chance. Patch size wins; the structure loses, significantly.

**The repo-identity confound, and why leave-one-repo-out is the honest split.** Repo identity alone predicts failure under the two weaker cached systems (AUC `0.596`, `0.613`) though **not** under the strong primary (`0.382`) — exactly the confound leave-one-repo-out neutralises, and precisely why the in-sample `0.567` collapses to `0.483` out of sample once repo identity cannot be memorised.

**No small effect is claimed.** By the Hanley–McNeil variance, resolving the observed `0.089` gap needs ~310 instances; the general `+0.05` target needs ~584; we have 172. The gap **is** resolved (DeLong and bootstrap both reach the 5% threshold), but no smaller effect is distinguishable from noise here, and we claim none. The project leads with the substrate finding, not this predictor.

### Two retractions

- **v1 is WITHDRAWN.** v1 reported AUC **0.565** / p=**0.726**. It was measured on a graph where **73.9%** of the resolved `CALLS` edges were name-collision artifacts (`super()` → `BlockNode.super` **1,321** times, `.lower()` → a template filter, `.extend()` → a GIS class). It measured the artifacts, not the thesis.
- **v2 is WITHDRAWN as a test of the thesis.** v2 reported **0.631**, but that was f1 / path-multiplicity _only_ (the cache stored path counts, not node lists), and it **lost to `patch_lines` at 0.637.** A structure signal that loses to patch size is not evidence for the structure thesis.

_Source: `docs/evaluation.md`, `docs/evaluation-v1-retracted.md`. Reproduce: `uv run python -m friction.harness`._

---

## What we tried first, and why it failed

This started as a different product: predict from graph structure whether an AI
agent would fail a task, and route the hard ones to a human. We built it and
measured it. Pooled leave-one-repo-out AUC across 7 repos: **0.483** — at or
below chance. The best structural feature lost to counting the lines in the
patch. Two earlier figures were retracted for measurement defects; the full
record is in `docs/evaluation.md` and stays in the repo rather than deleted.

The target was wrong. A call graph carries no information about whether a
language model will succeed. The gate asks the graph to report a property of
*itself* — deterministic, and measurable. That failure is why the gate exists.

---

## What we do not claim

**We do not claim to predict per-instance agent failure. That problem is already solved.** Agent Psychometrics (arXiv 2604.00594) reports AUC **0.841** on SWE-bench Verified, **0.787 from the problem-statement text alone**, with a task-agnostic prior already at **0.718**. Our structure-only features are not competitive and are not meant to be — these rows are **published, not reproduced by us.** GRADE (arXiv 2606.22741) predicts failure from the _agent's run graph_ — adjacent to us, and it de-risks the mechanism while leaving the static repository call graph unclaimed. The contribution here is the **substrate measurement**, which nobody in this space had made against a type-resolved reference on real code.

**Label contamination caps any AUC on this benchmark.** SWE-Bench+ (arXiv 2410.06992) measured **32.7%** solution leakage and **31%** weak tests; OpenAI reports **59.4%** of o3's failures on Verified were test flaws, not wrong patches. A ceiling below 1.0 is structural.

---

## Where this sits in the field

The full placement — 25 years of safe regression-test selection (Rothermel &
Harrold 1998; Legunsen FSE 2016), call-graph recall studies (Sui ICSE 2020;
PyCG ICSE 2021; *Total Recall?* ISSTA 2024), the 2026 agent-abstention
literature, and the category incumbent whose otherwise-exemplary benchmarks
measure everything downstream of its graph and never the graph itself — is in
[`docs/related-work.md`](docs/related-work.md). What was reused from whom, and
what deliberately was not, is in [`docs/reuse-policy.md`](docs/reuse-policy.md).

Two honest qualifications made there and repeated here: coverage-backed
selection (which the strongest incumbent uses for its test recommendations) is
genuinely stronger than static-graph selection, and our figures are **not
comparable** to PyCG's 70% or Java's 0.884 — those measure single-edge
presence; we measure bounded transitive reachability of a labelled pair, a
harder relation.

---

## Limitations

- **The CI engine job is disclosed as failing.** The pinned engine bootstraps a
  fresh store cleanly on macOS/Docker Desktop but dies with `IsADirectory` on
  the GitHub runner's filesystem. The badge covers the `tests` job (the full pytest suite +
  the gate verdict reproduced in CI); the Bolt round trip
  (`scripts/hydra_proof.py` — write via the verified loader forms, walk via
  `CALLED_BY`) is proven against the running engine locally, and the CI job
  that attempts it is `continue-on-error` with the cause written in the
  workflow, not hidden.


- **Precision is a ceiling.** Arm B under-reports on untyped receivers (`cursor(54)`), so `0.746` bounds one direction; true precision is `>= 0.746`, never `<=`.
- **The directional gap is real.** `fix → test` is `0/44`, `test → fix` is `24/44 (55%)`, undirected is `43/44 (98%)` — and the `55% → 98%` gap is fixture / `setUp` / `parametrize` / dispatch edges a static call graph structurally cannot see.
- **Python only.** The type-resolved arm depends on `scip-python`/pyright.
- **`maxLen 6`.** Reachability is bounded at 6 hops.
- **Seven repos, unevenly weighted, and underpowered for a small general effect.** The fair test is `n = 172` across 7 repos (django 44, sphinx 44, matplotlib 33, xarray 21, pytest 19, requests 8, sympy 3), scored leave-one-repo-out so repo identity cannot be memorised. It is powered to resolve the observed ~0.09 patch-scope gap (`p = 0.046`) but **not** a general `+0.05` AUC effect (~584 instances needed). The big scientific repos (sympy, and the piloted scikit-learn / astropy) are under-represented because a full scip type-index of them runs ~12–18+ min/instance; sympy is capped at 3. Every instance is a SWE-bench Verified task.
- **COVERS is partial.** The dynamic tracer maps only **27.6%** of executed `Test -> Function` edges into strict SCIP identity; the unmapped majority is the runtime-class-vs-definition-site mismatch (`type(self).__name__` is the runtime subclass, not the code object's definition site) plus `<module>` import bodies and staticmethods, which needs MRO-based definition-site resolution to close. Folding COVERS in moves the directed gate `11/18 -> 12/18` (`61% -> 67%`), a real but modest gain that does not rescue the predictor.
- **Label contamination** (above): a non-trivial fraction of the `failed` labels are wrong.
- **Arm B under-reports on untyped receivers** — the same property that makes precision a ceiling also means arm B is not ground truth, only a type-resolved reference.

Every latency figure in this README traces to `docs/latency.md` (measured on one django-scale graph); every other number traces to `docs/precision.md`, `docs/graph-delta.md`, `docs/connectivity.md`, `docs/evaluation.md`, `docs/engine-scaling.md`, `src/friction/reach.py`, `tests/test_reach.py`, or `docs/demo.html`. The one exception is the **v1 name-collision counts** (e.g. `super()` → `BlockNode.super` **1,321×**): those are v1 tree-sitter build-log figures, recorded in the retraction string in `src/friction/harness.py`, and are **not** recomputable from committed data — the v1 name-matched caches are gitignored, so they are cited as build-log figures, not as reproducible measurements.

---

## Upstream contributions

Four contributions to `github.com/hydra-db/hydradb`, surfaced by this project:

- **[Issue #81](https://github.com/hydra-db/hydradb/issues/81)** — manifest GC fails under the documented `CLOUD_PROVIDER=local`: after enough sustained writes every write fails permanently while reads keep serving, so a read-only health check reports the node healthy while it is silently write-dead.
- **[PR #82](https://github.com/hydra-db/hydradb/pull/82)** — cypher-compatibility docs covering 7 measured behaviours of the pinned build (inlined-literal set queries, `count(*)` vs rejected `count(n)`, `SSpaths` integer `sourceNode`, and the rest).
- **[Issue #101](https://github.com/hydra-db/hydradb/issues/101)** — fresh-store bootstrap fails on Linux CI runners (`IsADirectory`) while identical config bootstraps on macOS; the documented cause of this repo's disclosed-red engine CI job, with a public repro workflow.
- **[Issue #102](https://github.com/hydra-db/hydradb/issues/102)** — proposal for an `algo.RecallCert` procedure: in-engine certification of a selection result against labels, with `friction gate` as the motivating consumer.

---

## Attribution

- **HydraDB** graph engine, pinned at `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1), **AGPL-3.0** — the graph substrate every measurement runs against.
- **SWE-bench** and the **SWE-bench/experiments** submissions — ground-truth instances and agent pass/fail labels.
- **`scip-python`** (pyright-backed) — the type-resolved arm B index.
- **tree-sitter** — the name-matched arm A parse.
- **Cytoscape.js** (MIT) — the offline interactive graph in `docs/demo.html` (vendored, no CDN).
- Cited literature, all published-not-reproduced: Agent Psychometrics (arXiv 2604.00594), GRADE (arXiv 2606.22741), ARISE (arXiv 2605.03117), SHERLOC (arXiv 2606.24820), RGFL (arXiv 2601.18044), RepoGraph (arXiv 2410.14684), LocAgent (arXiv 2503.09089), SWE-Bench+ (arXiv 2410.06992).
- **Claude** (Anthropic) assisted in building and measuring this project.

## License

This project is **MIT** (see `LICENSE`). The HydraDB engine it queries is **AGPL-3.0** and is used as a pinned external service, not vendored into this source tree; its license governs the engine binary independently of this project's MIT grant.

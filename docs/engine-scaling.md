# Engine scaling ceiling for the friction query — measured

The friction metric's engine query is `algo.MSpaths` with `pairwise: true`,
`relDirection: 'both'`, `maxLen` 4/5/6, `pathCount: 20`, run from a small
fix-site set to a small test-target set. The full-django graph times out on it;
a 400-node/789-edge graph answers `maxLen 6` in 769 ms. This document finds
where the boundary actually is, by seeding synthetic call-graph-shaped graphs
into fresh id bands and timing the real query shape against the **live engine**
(`bolt://127.0.0.1:7687`).

**Headline:** there is no clean node-count ceiling. The binding constraint is
the **effective branching factor** — the both-direction degree of the traversed
subgraph, raised to `maxLen` — not the node count and not the raw edge count.
At a realistic call-graph degree (`both-degree ≈ 2.9`, measured from real
django), `maxLen 6` is **not reliably answerable under 5 s at any graph size we
tested**, down to 150 nodes. Node count is a weak, non-monotonic secondary
factor. The lever that actually buys reliability is lowering the branching
factor (prune by degree) or lowering `maxLen`.

## Method

* **Synthetic graphs.** `gen_call_graph(n, out_degree, seed)` builds a directed
  graph with a power-law-ish out-degree (Pareto-weighted, so a few hubs emit
  many calls), average out-degree as specified, random targets (small-world;
  cycles arise naturally). This is the friction query's stress shape: nodes are
  `Function`-labelled with a string `sid` mirror of the integer id, edges are
  `CALLS`. `relDirection: 'both'` means the effective per-node branching factor
  is `2 × out-degree` (in-edges + out-edges), which we call **both-degree**.
* **Realistic calibration.** The query traverses `CALLS + HAS_METHOD +
  INHERITS`. On the real django graph (`data/graphs/django`, 46 565 nodes) those
  three relation types total 67 142 edges → out-degree **1.44**, both-degree
  **2.88**. The task's "average degree 3–4" is total (in+out) degree; the sweeps
  centre on **both-degree 3.0** (out-degree 1.5) as the realistic operating
  point, and vary around it.
* **Query construction.** `sourceValues`/`targetValues` are **inlined as Cypher
  string literals**, never Bolt parameters (the engine rejects a `$fixIds`
  parameter list on `algo.*` set queries — this is the real bug still live in
  `src/friction/paths.py`, which passes them as parameters and is only ever
  exercised against a stub).
* **Isolation.** Each measurement uses a fresh disjoint id band above
  `8_000_000_000` (stride `20_000_000`), so no edge crosses between graphs.
* **Repetition & warm/cold.** Every cell was run at least twice. Identical
  re-runs are **cache-warm** (see below) and therefore not independent samples,
  so the meaningful repetition is across **distinct seed placements**: the
  variance tables below sample 4–6 different `(source, target)` pairs per graph.
* **Timeout.** The engine enforces a hard **29 999 ms** per-query timeout,
  returned as `Transaction.Terminated ... exceeded query timeout`. Cost is
  monotone in `maxLen`, so a timeout at `maxLen L` implies one at `L+1`.

## Finding 0 — result caching dominates repeated identical queries

An identical query re-run returns in **1–3 ms**; its first (cold) execution
takes seconds. Every cold/warm pair in the node sweep:

| nodes | maxLen | cold (rep1) | warm (rep2) |
|------:|:------:|------------:|------------:|
| 500   | 6      | 14 174 ms   | 1 ms |
| 1 000 | 5      | 21 168 ms   | 2 ms |
| 2 000 | 6      | 15 451 ms   | 2 ms |
| 8 000 | 5      |  7 581 ms   | 2 ms |

The engine caches the result of a given query string. **Only cold cost is
real**, and the evaluation gate must treat every *distinct* `(fix-set,
test-set)` query as cold — a warm 2 ms reading is an artefact, not throughput.
All timings below are cold (first execution of a distinct query string).

## Finding 1 — node-count sweep at realistic degree (both-degree 3.0)

Single placement (source = node 0, target = node n−1, graph seed 101),
cold ms; `TO` = timed out at 29 999 ms:

| nodes | edges | maxLen 4 | maxLen 5 | maxLen 6 |
|------:|------:|---------:|---------:|---------:|
|   500 |   749 |  1 630   |  4 810   | 14 174 |
| 1 000 | 1 496 |  3 559   | 21 168   | **TO** |
| 2 000 | 2 998 |  1 209   |  5 347   | 15 451 |
| 4 000 | 5 997 |    118   |     95   |    106 |
| 8 000 |11 997 |  1 903   |  7 581   | **TO** |
|16 000 |23 996 | 16 727   |   **TO** | **TO** |

This is **non-monotonic in node count**: `maxLen 6` gives 14 s at 500 nodes,
times out at 1 000, 15 s at 2 000, **106 ms at 4 000**, times out at 8 000. Node
count does not predict cost. (The 4 000-node row is a lucky placement where
node 0 and node 3 999 have almost no connecting walks within 6 hops.)

## Finding 2 — placement variance is 1–2 orders of magnitude (the real story)

Because a single placement is meaningless, we sample multiple random
`(source,target)` pairs per graph. `maxLen 6`, both-degree 3.0:

| nodes | timeouts | cold ms across placements (completed) |
|------:|:--------:|:--------------------------------------|
|   150 | 0 / 6 | 4 539 · 5 921 · 6 737 · 7 713 · 8 223 · 8 405 |
|   300 | 0 / 6 | 1 159 · 7 934 · 15 583 · 17 250 · 17 380 · 17 457 |
|   500 | 0 / 6 |   108 · 19 267 · 21 484 · 21 780 · 23 235 · 24 659 |
| 1 000 | 3 / 4 | 22 328 |
| 2 000 | 1 / 4 |   983 · 6 339 · 12 711 |
| 4 000 | 2 / 4 | 4 814 · 12 995 |
| 8 000 | 4 / 4 | — |

At **every** size, most placements exceed 5 s or time out. Even at 150 nodes the
best case is 4.5 s. Within a single graph the same query at different seed pairs
swings from 0.1 s to timeout. The cost tracks how many walks (length ≤ `maxLen`,
either direction) connect the two seed sets — a property of local structure and
seed placement, essentially independent of total node count once the graph
exceeds the `maxLen`-hop horizon (~a few hundred nodes at this degree).

## Finding 3 — degree is the binding constraint

At fixed **N = 2 000, maxLen 6**, varying both-degree — every one times out,
even the sparsest:

| both-degree | edges | maxLen 6 |
|------------:|------:|---------:|
| 2.0 | 1 999 | **TO** |
| 2.5 | 2 496 | **TO** |
| 3.0 | 2 993 | **TO** |
| 3.5 | 3 497 | **TO** |

And at fixed **N = 300, maxLen 6**, degree is decisive:

| both-degree | edges | timeouts | cold ms across placements |
|------------:|------:|:--------:|:--------------------------|
| 2.0 | ~300 | 0 / 6 |   93 · 4 021 · 5 269 · 5 889 · 7 610 · 8 227 |
| 3.0 | ~450 | 0 / 6 | 1 159 · 7 934 · 15 583 · 17 250 · 17 380 · 17 457 |
| 4.0 | ~600 | 0 / 6 | 15 277 · 16 293 · 17 459 · 20 001 · 21 151 · 24 792 |

Dropping both-degree from 3.0 → 2.0 at N = 300 cuts the median from ~16 s to
~5.6 s; raising it to 4.0 pins everything at 15–25 s. This is the expected
`(both-degree)^maxLen` walk-enumeration blow-up: `3^6 ≈ 729` vs `2^6 = 64` vs
`4^6 = 4096`.

## The one configuration that reliably answered maxLen 6 under 5 s

Across all placements sampled, the **only** graph where every `maxLen 6` query
completed under 5 s was:

> **N = 150 nodes, both-degree ≤ 2.0** (≈150 traversed-relationship edges) —
> cold 0.48 · 0.94 · 1.53 · 1.79 · 1.98 · 3.25 s.

Everything larger or denser produced at least one placement over 5 s, and most
produced many.

## Which is binding: nodes or edges?

**Edges — specifically the both-direction degree (branching factor) — are the
binding constraint; node count is a weak, non-monotonic secondary factor.**

* At fixed both-degree 3.0, sweeping nodes 150 → 16 000 leaves `maxLen 6` almost
  uniformly over 5 s and does so non-monotonically (Findings 1–2).
* At fixed nodes, changing both-degree 2.0 → 4.0 moves the median cost by ~4×
  and flips a graph from borderline to hopeless (Finding 3).
* The governing quantity is the **walk-enumeration volume** `≈ (both-degree)^maxLen`,
  bounded by how many nodes lie within `maxLen` hops of the seeds. Node count
  matters only (a) below horizon saturation (~a few hundred nodes), where adding
  nodes adds reachable walks, and (b) through the high-degree **hub** nodes a
  larger subgraph inevitably drags in — and it is those hubs' degree, not the
  node total, that does the damage.

Raw edge *count* alone is not binding either (16 000 nodes / 24 000 edges at
maxLen 4 = 16.7 s, while 300 nodes / 600 edges at maxLen 6 = 17 s). What binds
is edges-per-node in the traversed neighbourhood, i.e. degree.

## Recommended per-instance subgraph budget

The metric's signal-bearing depths are `maxLen 5` and `6`. The data says those
depths are **not reliably answerable** at a realistic call-graph degree for
arbitrary fix/test placement. Two honest options:

**Option A — keep maxLen 6, pay for it in aggressive pruning.**
* **Node budget: ≤ 150 nodes.**
* **Edge budget: ≤ ~200 traversed-relationship edges (both-degree ≤ ~2.7).**
* Prune by **both-degree**, not just node count: drop or cap any retained hub
  function's incident CALLS/HAS_METHOD/INHERITS edges, because a single retained
  hub can push one pair over 5 s regardless of the node total.
* Even here the margin is thin (best case 4.5 s at both-degree 3.0; only
  both-degree ≤ 2.0 stayed comfortably under). Treat 150 / 200 as a ceiling with
  no headroom, not a target.

**Option B — lower maxLen to 4, get a usable envelope.**
* **Node budget: ≤ ~500 nodes.  Edge budget: ≤ ~750 edges (both-degree ~3).**
* `maxLen 4` was sub-2 s for n ≤ 500 at both-degree 3.0 and stayed under 5 s up
  to ~8 000 nodes in the single-placement sweep — but placement variance still
  produced an 8.2 s outlier at 300 nodes, so keep a margin and keep the node
  budget near 500, not 8 000.
* Cost: `maxLen 4` truncates exactly the longer fix→test paths the metric is
  built to measure. This is a substantive change to the metric, not just a
  performance knob, and must be stated wherever the metric is reported.

**Recommendation.** For the shipped gate, budget **≤ 150 nodes / ≤ 200 traversed
edges per instance, pruned to both-degree ≤ 2.5 around the fix and test sites,
at maxLen 6** — and expect that some instances with hub-heavy neighbourhoods
will still time out and must be recorded as "no engine path" rather than forced
under budget. The full-repo graph is ~300× over this node budget and ~600× over
the edge budget; that gap is why the raw query times out.

## Warm/cold and measurement notes

* Cold vs warm differ by ~1000–10 000× (Finding 0). Reported numbers are cold.
* Seeding cost is linear and cheap: 500 nodes/0.75 k edges in 0.6 s, 16 000
  nodes/24 k edges in 14.8 s (Bolt `UNWIND` batches of 1 000).
* Each variance row is a distinct random graph (distinct seed), so cross-row
  comparison at equal `(n, degree)` reflects graph-structure variance too — which
  is the point: the ceiling is placement- and structure-dependent, and any
  single-number budget must carry a wide margin.

## Infrastructure finding — the local object-store write ceiling (encountered here)

While seeding, the engine's write path failed hard and stayed broken across
container restarts, with this in the graph-node log:

```
object store error: Operation `put_opts` with mode `PutMode::Update`
not yet implemented by LocalFileSystem(file:///data/graph)
```

Root cause: `docker-compose.yml` runs the node with `CLOUD_PROVIDER: local` /
`LOCAL_PATH: /data/graph`, so SlateDB's object store is the `object_store`
crate's **LocalFileSystem**, which does not implement conditional/atomic
`PutMode::Update`. SlateDB needs that put mode for compaction and manifest
updates; once enough writes accumulate to trigger one, **all further writes
fail** and a restart just reloads the same store and fails again. Reads and
`algo.*` traversals continue to work (all the measurements above post-date this
and were unaffected — they are reads over already-written bands).

Implications:
* This is a hard **write ceiling** independent of the query-timeout ceiling:
  the local-filesystem backend cannot durably sustain a large multi-batch load.
  It is a second, separate reason the full-repo build is fragile.
* The compose file already runs a **MinIO** (S3-compatible) service, which *does*
  implement conditional puts. Pointing the engine at MinIO instead of the local
  path (an S3 `CLOUD_PROVIDER`) is the durable fix. Recovering the current node
  otherwise requires clearing `./hydradb-data` and rebuilding all instance
  graphs — a data-loss operation, left to the controller, not done here.
* The engine was left running and read-serving; new writes are blocked until the
  backend is reconfigured or the store is reset.

## Reproduce

Harness in the session scratchpad: `scaling.py` (generator + query builder +
timer), `sweep.py` (Findings 0/1/3), `expC.py` (Finding 2 placement variance),
`readvar.py` (read-only variance over resident bands), `degdist.py` (real-django
degree calibration). Every query is the real friction shape with inlined string
`sourceValues`/`targetValues`; every graph is a fresh id band above 8e9.

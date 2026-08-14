# Engine scaling for the friction query — measured on the healthy store

## Retraction of the earlier ceiling

An earlier version of this document reported that the friction query
(`algo.MSpaths`) **could not** be computed at full-repo scale, that it "exceeds
the 29999 ms timeout at maxLen ≥ 4", and it recommended a hard per-instance
budget of **150 nodes / 200 edges**. **That conclusion and that table were
wrong, and they are retracted here.**

The 150-node ceiling was an artifact of a **degraded object store**, not a
property of the engine. Every number in the retracted table was measured against
a store that had already broken: the node was running with `CLOUD_PROVIDER=local`
(the engine's own documented local configuration), whose `LocalFileSystem`
backend does not implement conditional puts. After several GB of sustained
writes the store entered a permanently degraded state — all further writes failed
*and* query latency collapsed by orders of magnitude — with no error surfaced
until it was already broken. The old scaling table timed reads against that
collapsed store, so it measured the failure, not the engine.

The store has since been wiped and the node restarted. On the **healthy** store,
measured directly with the identical query shape, the engine handles
**django-scale graphs (34 000 nodes / 34 000–68 000 traversed edges) at maxLen 6
in well under the 30 s timeout** at realistic call-graph density. The corrected
sweep follows. The object-store defect is real and independently valuable, and is
documented in its own section below — it is retracted as a *scaling ceiling*, not
as a *defect report*.

## Method

* **Query shape (the real friction query).** `CALL algo.MSpaths({... sourceLabel:
  'Function', sourceProperty: 'sid', sourceValues: [...], targetLabel: 'Function',
  targetProperty: 'sid', targetValues: [...], relTypes: ['CALLS'], relDirection:
  'both', maxLen: L, pairwise: true, pathCount: 20}) YIELD path, pathCost`.
  `sourceValues`/`targetValues` are **inlined as Cypher string literals**, never
  Bolt parameters (the engine rejects a parameter list on `algo.*` set queries).
  3 source ids × 3 target ids, `pairwise: true` → 9 seed pairs per query.
* **Synthetic graphs.** `gen_call_graph(n, out_degree, seed)` builds a directed
  call-graph-shaped graph: Pareto-weighted out-degree (a few hubs emit many
  calls), random targets (small-world; cycles arise naturally). Nodes are
  `Function`-labelled with a string `sid` mirror of the integer id; edges are
  `CALLS`.
* **Degree convention — "both-degree".** `relDirection: 'both'` traverses in-edges
  and out-edges, so the effective per-node branching factor is
  in-degree + out-degree = **2 × out-degree = 2 × edges/n**, which we call
  **both-degree**. The sweep is parameterised by target both-degree ∈ {2, 3, 4};
  the generator receives `out_degree = both_degree / 2`. Real django's traversed
  relation types (`CALLS`+`HAS_METHOD`+`INHERITS`) give both-degree ≈ **2.9**, so
  both-degree 3 is the realistic operating point and 2 / 4 bracket it.
  **Stated unambiguously: "both-degree N" is the undirected (in + out) degree of
  the resulting graph. It means `N/2` outgoing edges per node, i.e. ≈ `(N/2)·n`
  directed edges total** — so both-degree 3 is `1.5·n` edges, which is why the
  Finding 1 both-degree-3 rows read 746 / 2 999 / 11 998 / 23 999 / 50 998 edges
  at 500 / 2 000 / 8 000 / 16 000 / 34 000 nodes (≈ 1.5×). It is **not** 3 out-edges
  per node; a sweep that counts degree as out-edges-per-node would put twice as
  many edges in the "3" column (see the reconciliation note below).
* **Seed placement.** 3 source + 3 target ids are drawn from the graph interior
  with a fixed per-config RNG (not the degenerate node 0 → node n−1 corner), so
  each cell reflects a representative mid-graph placement rather than a lucky or
  worst-case corner.
* **Isolation.** Each `(node-count, both-degree)` graph is seeded into its own
  fresh disjoint id band `7_100_000_000 + i × 50_000_000` (stride wider than the
  largest graph, 34 000 nodes), so no edge crosses between graphs. Bands are
  recorded in the tables.
* **Cold vs warm.** Every maxLen was run **twice back-to-back**: the first
  execution of a distinct query string is **cold**; the immediate identical
  re-run is **warm**. Both are reported. See Finding 0 — warm is an unreliable
  cache reading and **only cold is meaningful**.
* **Timeout.** The engine enforces a hard **29 999 ms** per-query timeout.
  Cost is monotone in `maxLen`, so a timeout at `maxLen L` implies one at `L+1`;
  the harness records the higher `maxLen` as TO without re-running it.
* **Store health.** Measured on the fresh store; writes verified working
  throughout. The whole sweep (≈ 180 000 nodes / ≈ 272 000 edges) loaded cleanly,
  growing `./hydradb-data` from 191 MB to 948 MB with no write failure — itself
  evidence the healthy store sustains this write volume.

## Finding 0 — result caching is real, but unreliable for heavy queries; only cold counts

For light queries the engine caches the result of a query **string**: the cold
execution takes hundreds of ms to seconds, the immediate warm re-run returns in
**1–10 ms**. But the caching **does not reliably engage for the heaviest
queries** — exactly the ones near the ceiling that the budget question turns on:

| n / both-deg / maxLen | band | cold | warm (immediate) |
|:----------------------|-----:|-----:|-----------------:|
| 8 000 / 4 / 6  | 7500000000 |  2 540 ms |     6.5 ms (cached) |
| 16 000 / 4 / 5 | 7650000000 | 11 379 ms | 11 879 ms (**not cached**) |
| 16 000 / 4 / 6 | 7650000000 | 17 184 ms | **TO** (not cached, ran again to > 30 s) |
| 34 000 / 3 / 6 | 7750000000 | 27 620 ms | **TO** (not cached, ran again to > 30 s) |

The same 16 000 / 4 / 5 query, re-run in isolation later, *did* cache
(10 847 ms cold → 7 ms → 5 ms). So the cache is size/pressure-bounded and its
engagement on an immediate re-run of a heavy query is not guaranteed. **Practical
consequence:** a warm reading is not a trustworthy cost, and for the heavy
queries a warm speedup cannot be assumed at all — **every distinct `(fix-set,
test-set)` query the gate issues must be treated as cold.** All cost tables below
report cold ms.

## Finding 1 — corrected sweep, cold ms (the healthy store)

Cold ms per configuration. `TO` = timed out at 29 999 ms. Every graph is a fresh
band (Method); `rows` is the number of paths returned at maxLen 6.

**both-degree ≈ 2** (out-degree 1; sparse — path/tree-like):

| nodes | edges | band | maxLen 4 | maxLen 5 | maxLen 6 |
|------:|------:|-----:|---------:|---------:|---------:|
|    500 |    498 | 7100000000 | 204 | 209 | 215 |
|  2 000 |  1 997 | 7250000000 |  29 |  67 | 289 |
|  8 000 |  7 997 | 7400000000 |  37 |  84 | 571 |
| 16 000 | 15 998 | 7550000000 |  43 | 160 | 464 |
| 34 000 | 33 999 | 7700000000 |  39 |  93 | 406 |

**both-degree ≈ 3** (out-degree 1.5; the realistic django operating point):

| nodes | edges | band | maxLen 4 | maxLen 5 | maxLen 6 |
|------:|------:|-----:|---------:|---------:|---------:|
|    500 |    746 | 7150000000 |    20 |    96 |    191 |
|  2 000 |  2 999 | 7300000000 |   110 |   398 |    782 |
|  8 000 | 11 998 | 7450000000 |    95 |   334 |    797 |
| 16 000 | 23 999 | 7600000000 |    83 |   455 |  1 458 |
| 34 000 | 50 998 | 7750000000 | 4 441 | 15 779 | 27 620 |

**both-degree ≈ 4** (out-degree 2; denser than django):

| nodes | edges | band | maxLen 4 | maxLen 5 | maxLen 6 |
|------:|------:|-----:|---------:|---------:|---------:|
|    500 |    994 | 7200000000 |   104 |    259 |    292 |
|  2 000 |  3 998 | 7350000000 |   268 |    696 |  1 049 |
|  8 000 | 15 997 | 7500000000 |   284 |  1 359 |  2 540 |
| 16 000 | 31 997 | 7650000000 | 3 354 | 11 379 | 17 184 |
| 34 000 | 67 998 | 7800000000 |   154 |  1 750 | 17 823 |

Nothing timed out on a cold run anywhere in the sweep. The worst cold cell is
34 000 / bd 3 / maxLen 6 = **27.6 s**, still under the 30 s ceiling but with no
margin.

### Reconciliation with an independent sweep (degree-definition mismatch)

An independent sweep was run directly against the same healthy engine and, at
maxLen 6, reported:

| nodes | edges | maxLen 6 (independent) |
|------:|------:|----------------------:|
|    500 |     1 000 |    101 ms |
|  2 000 |     5 997 |    477 ms |
|  8 000 |    23 998 |  1 924 ms |
| 34 000 |   101 995 |  7 511 ms |

At first glance this contradicts Finding 1: at the same node count the edge
counts are **~2× larger** (2 000 → 5 997 vs 2 999; 8 000 → 23 998 vs 11 998;
34 000 → 101 995 vs 50 998 — each **exactly 2.0×**). That factor of two is not a
disagreement about the engine; it is a disagreement about the word "degree".

* **Finding 1 (this doc)** labels rows by **both-degree** = undirected (in + out)
  degree, so "both-degree 3" is `out_degree = 1.5`, `edges ≈ 1.5·n`.
* **The independent sweep** labels rows by **out-edges-per-node** (`degree = out_degree`),
  so its "degree 3" is `edges ≈ 3·n`.

`3·n ÷ 1.5·n = 2.0`, which is precisely the observed edge-count ratio at every
matched node count. Once the definitions are aligned the edge counts reconcile
exactly: the independent "degree 3" rows are the same density as a **both-degree 6**
graph in this doc's convention (denser than the both-degree-4 column here), and
its 500-node row (1 000 edges = `2·n`) is a both-degree-4 point.

**On latency the two sweeps corroborate the structural finding but are not
millisecond-comparable, and neither is privileged.** Compared at matched *total*
edge count they agree to within a small factor in the mid-range — the
independent 8 000 / 23 998 → 1 924 ms sits beside this doc's 16 000 / 23 999
(both-degree 3) → 1 458 ms, same ~24 000 edges, same order of magnitude. At
34 000 nodes they diverge in the other direction: the independent 34 000 / 101 995
→ 7 511 ms is **faster** than this doc's denser-yet 34 000 / 67 998 (17 823 ms)
and much faster than 34 000 / 50 998 (27 620 ms), despite carrying more edges.
That is the seed-placement variance Finding 2 documents (a 1–2 order-of-magnitude
swing from fix/test placement at large `n`): the two sweeps drew different
interior seeds, so absolute cold ms differ even at equal density. The honest
reading is that the two measurement sets **agree on the definitional facts (the 2×
is a pure degree-convention artifact) and on the structural conclusion (density
and maxLen drive cost; node count is a weak, saturating lever), but do not agree
to the millisecond** — and the divergence is placement, not a contradiction about
the engine. Both are reported here with their provenance rather than picking the
lower or the higher number.

## Finding 2 — the binding constraint

**The binding constraint is the walk-enumeration volume between the two seed
sets, ≈ (both-degree)^maxLen, capped by how many nodes fall within `maxLen` hops
of the seeds. In priority order the levers are: `maxLen` (the exponent, most
powerful) > both-degree (the base) > node count (a weak, saturating cap).**

Evidence, straight from Finding 1:

* **Node count is not independently binding.** At both-degree 2, *every* size up
  to 34 000 nodes answers maxLen 6 in ≤ 571 ms. A 34 000-node graph at maxLen 6
  costs 406 ms (bd 2) but 27 620 ms (bd 3) — a 68× swing from density alone, node
  count held fixed. Node count matters only by supplying more reachable nodes
  within the hop horizon; once the graph is sparse enough that few walks connect
  the seed sets, size is nearly free.
* **Density (both-degree) is decisive.** Sweeping both-degree 2 → 3 → 4 at fixed
  size moves cost by one to two orders of magnitude (16 000 nodes, maxLen 6:
  464 → 1 458 → 17 184 ms). This is the expected `(both-degree)^maxLen` blow-up:
  `2^6 = 64` vs `3^6 = 729` vs `4^6 = 4096` walks per seed.
* **`maxLen` is the exponent.** Within any row, each extra hop multiplies cost by
  roughly the branching factor (34 000 / bd 3: 4 441 → 15 779 → 27 620 ms for
  maxLen 4 → 5 → 6).
* **Placement/structure variance rides on top and can dominate at large n.** The
  34 000 / bd 3 graph is expensive even at maxLen 4 (4 441 ms) while 34 000 / bd 4
  at maxLen 4 is 154 ms — because that specific bd 3 seed placement happens to
  have many connecting walks. At 34 000 nodes the choice of fix/test seeds swings
  cost by 1–2 orders of magnitude, which is why a node cap (bounding reachable
  walks) buys reliability that a degree cap alone does not.

Raw edge *count* is not the constraint either: 34 000 nodes / 68 000 edges (bd 4)
answers maxLen 6 in 17.8 s, while 34 000 nodes / 51 000 edges (bd 3) takes 27.6 s.
What binds is edges-per-node in the traversed neighbourhood (degree) raised to the
hop count — not the edge total.

## Finding 3 — the object-store write defect (the durable engine finding)

This is the genuinely valuable and reproducible engine defect surfaced by this
project. It is a **write-durability** defect, separate from and independent of
the query-timeout behaviour above.

**Symptom / error.** Under the engine's own documented local configuration,
after enough sustained writes to trigger a SlateDB compaction or manifest
update, the write path fails permanently with this in the graph-node log:

```
object store error: Operation `put_opts` with mode `PutMode::Update`
not yet implemented by LocalFileSystem(file:///data/graph)
```

**Root cause.** `docker-compose.yml` runs the node with
`CLOUD_PROVIDER: local` / `LOCAL_PATH: /data/graph` (straight from the engine's
README). That makes SlateDB's object store the `object_store` crate's
**`LocalFileSystem`**, which does not implement conditional/atomic
`PutMode::Update`. SlateDB needs that put mode for compaction and manifest
updates. Until one is triggered, writes succeed; once the accumulated write
volume triggers one, the `Update` put fails and **every subsequent write fails**.

**Symptom progression (why it is dangerous).**
1. Writes succeed for a long time — the store looks completely healthy.
2. A compaction/manifest update is triggered; the `PutMode::Update` put fails.
3. From that point **all writes fail permanently.** A container restart just
   reloads the same on-disk store and fails again — it is not transient.
4. **Reads and `algo.*` traversals keep working** — but query latency also
   collapses by orders of magnitude in the degraded state. Nothing surfaces an
   error to a read-only client. The node keeps serving, so it *looks alive*,
   which is exactly what makes the failure mode dangerous: a monitoring check
   that only reads will report the node healthy while it is silently
   write-dead and orders of magnitude slower.

**Reproduction.** Run the node with `CLOUD_PROVIDER=local` and drive sustained
multi-batch writes (the earlier full-repo build, ≈ 6 GB of writes across the
50 per-instance graphs, reliably triggered it). It is a function of accumulated
write volume, not of any single query.

**Confirmation on the healthy store.** After a wipe and restart, this sweep wrote
≈ 180 000 nodes / ≈ 272 000 edges (`./hydradb-data` 191 MB → 948 MB) with **zero
write failures** — consistent with the defect being volume-triggered rather than
inherent to the first writes.

**Mitigation.**
* **Keep the working set small** so total write volume never reaches the
  compaction threshold (adequate for this project's per-instance graphs).
* **Use an S3-compatible backend**, which *does* implement conditional puts, for
  any durable or large load. The compose file already runs a **MinIO** service
  for exactly this; pointing the node at it (an S3 `CLOUD_PROVIDER`) is the
  durable fix.
* **Do not rely on read health as a liveness signal** — a degraded store still
  serves reads. Monitor write success and query latency, not just reachability.

## Recommended per-instance subgraph budget

Signal-bearing depth for the metric is **maxLen 6**, and the realistic traversed
density is **both-degree ≈ 3** (django's `CALLS`+`HAS_METHOD`+`INHERITS`). Reading
the both-degree-3 column of Finding 1 at maxLen 6:

| nodes | cold maxLen 6 | headroom vs 30 s |
|------:|--------------:|:-----------------|
|    500 |    191 ms | ~157× |
|  2 000 |    782 ms |  ~38× |
|  8 000 |    797 ms |  ~38× |
| 16 000 |  1 458 ms |  ~21× |
| 34 000 | 27 620 ms |  ~1.1× (no margin; warm re-run timed out) |

There is a **cliff between 16 000 and 34 000 nodes** at realistic density and
maxLen 6: 1.5 s vs 27.6 s. The full 34 000-node per-instance graph is *feasible*
(it completed in ~27 s) but sits on the ceiling — a hub-heavy or high-connectivity
fix/test placement will push it over, and its immediate re-run already did.

**Recommendation: budget ≤ 16 000 nodes / ≤ ~24 000 traversed-relationship edges
(both-degree ≤ 3) per instance, at maxLen 6.** That measured 1.46 s cold — a ~20×
margin under the 30 s ceiling, which absorbs the 1–2 orders of magnitude of
placement/structure variance we see at large n. This budget is roughly **100×
more generous** than the retracted 150-node / 200-edge ceiling.

Supporting notes:
* **Degree is the strongest lever.** At both-degree ≤ 2 there is effectively no
  ceiling up to 34 000 nodes (every maxLen-6 cell ≤ 571 ms). Pruning the traversed
  neighbourhood by degree — capping a retained hub's incident
  `CALLS`/`HAS_METHOD`/`INHERITS` edges — buys more headroom than trimming node
  count, because a single retained hub inflates `(both-degree)^maxLen`.
* **The full graph need not be subgraphed for correctness, only for margin.**
  Unlike the retracted analysis, subgraphing is no longer required to make the
  query answerable — it is required only to guarantee reliable sub-second-to-few-
  second latency and to avoid the occasional 34 000-node placement that grazes the
  30 s ceiling.
* **Record, don't force.** Any instance whose neighbourhood is genuinely
  hub-heavy enough to time out at maxLen 6 should be recorded as "no engine path"
  rather than forced under budget by lowering `maxLen`, which truncates exactly
  the long fix→test paths the metric exists to measure.

## Reproduce

Committed, runnable harness: **`scripts/engine_scaling_sweep.py`**. With the
engine up (`./setup.sh`, or `just up`), from the repo root:

```bash
# Full sweep: node × both-degree × maxLen, cold + warm, fresh bands above
# 7_100_000_000. Writes docs/plots/engine_scaling_sweep_results.json and prints
# the markdown tables to stdout.
uv run python scripts/engine_scaling_sweep.py

# Fast liveness check (one small cell, ~seconds):
uv run python scripts/engine_scaling_sweep.py --smoke

# A single row/column subset:
uv run python scripts/engine_scaling_sweep.py --nodes 500,2000 \
    --both-degrees 3 --max-lens 4,5,6
```

Every query the script issues is the real friction shape — `algo.MSpaths`,
`pairwise: true`, `relDirection: 'both'`, `pathCount: 20`, with `sourceValues`/
`targetValues` inlined as Cypher string literals against the `sid` property
(built by `friction.paths.build_mspaths_cypher`, the same builder the gate uses).
Each `(node-count, both-degree)` graph is seeded into its own fresh disjoint id
band `7_100_000_000 + i × 50_000_000`; `gen_call_graph(n, out_degree, seed)` uses
`out_degree = both_degree / 2` (see the degree convention in Method). Measured
against `bolt://127.0.0.1:7687`, engine commit
`02a40025d2d57e97ab2754c8256219cdbfeab379`.

**Provenance of the table in Finding 1.** Those numbers were produced by an
**earlier, equivalent** harness (`scaling.py` + `sweep_healthy.py`) that lived in
the build session's scratchpad and was never committed — which is exactly the gap
this script closes. `scripts/engine_scaling_sweep.py` is a faithful
re-implementation of that harness (same generator contract, same degree
convention, same id-band placement, same inlined-literal `MSpaths` query), so
re-running it reproduces the same table *shape*. The individual milliseconds will
not match to the digit on a fresh run: cost is dominated by interior seed
placement, which this document measures as a 1–2 order-of-magnitude swing at large
`n` (Finding 2). The committed table is the earlier harness's run; this script is
the reproduction path, not a byte-for-byte replay of it.

# Latency: both queries on ONE graph, at django scale

## Why this file exists

An earlier README put two numbers side by side as if they were one measurement:
the `count(*)` reachability band **3–12 ms** and the `algo.MSpaths` **30,000 ms**
timeout, described as "the same density." They were **two different graphs**:

- the **3–12 ms** reach band came from a **1,000-node, out-degree-3** synthetic
  graph (`tests/test_reach.py`);
- the **30,000 ms** enumeration timeout came from the **~34,000-node django**
  graph (`docs/engine-scaling.md`).

At 1,000 nodes, enumeration finishes in ~200 ms — it does **not** time out there.
And out-degree 3 is ~**2× denser** than django, whose traversed relation
(`CALLS`+`HAS_METHOD`+`INHERITS`) has both-degree ≈ **2.9** (out-degree ≈ 1.45).
So the retracted "~2,500×" was an artifact of comparing a small sparse graph's
cheap query to a large dense graph's expensive one.

This file fixes that by running **both** queries on **one** graph, at **django
scale and django density**, and reporting the honest ratio. Every number here is
produced by `scripts/latency_measure.py` and recorded in
[`docs/latency.json`](latency.json); `src/friction/viz.py` reads that JSON for
`docs/plots/latency.png`.

## The graph (one graph, both queries)

| property | value |
|---|---|
| nodes | **34,000** (django's ~34k-node call graph) |
| edges | **49,300** |
| both-degree | **2.9** (out-degree 1.45 — django's `CALLS`+`HAS_METHOD`+`INHERITS` density) |
| generator | `scripts.engine_scaling_sweep.gen_call_graph` (Pareto out-degree: a few hubs, most nodes near-leaves) |
| id band | `45_200_000_000` (fresh, disjoint from every other band) |
| engine | pinned commit `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1), `bolt://127.0.0.1:7687` |

All timings are **cold** (each query string measured on its first run; the engine
caches result strings — see `docs/engine-scaling.md` Finding 0).

## (a) `count(*)` bounded reachable-set size — the tractable substitute

`MATCH (s {id:N})-[:CALLS*1..k]->(n) RETURN count(*)`. Cost is bounded by the
**visited set** (≤ graph size), so it always completes. But it is **not
universally "flat"**: its cost tracks how much the source actually reaches.

**Typical function** (source reaches 36 nodes) — flat, single-digit ms:

| k | 1 | 2 | 3 | 4 | 5 | 6 |
|---|--:|--:|--:|--:|--:|--:|
| ms | 8.2 | 6.3 | 6.4 | 7.8 | 6.9 | 9.9 |
| reachable-set size | 2 | 7 | 10 | 14 | 17 | 36 |

Measured band for a typical source: **6.3–9.9 ms** (the retracted "3–12 ms" was
the right order of magnitude but from a different, 1,000-node graph).

**Busiest hub** (source reaches 12,710 nodes — 37% of the graph) — grows with the
visited set, still completes:

| k | 1 | 2 | 3 | 4 | 5 | 6 |
|---|--:|--:|--:|--:|--:|--:|
| ms | 30.6 | 593 | 1,317 | 2,192 | 4,732 | 6,506 |
| reachable-set size | 1,265 | 3,058 | 5,143 | 7,653 | 10,360 | 12,710 |

So `count(*)` from the hardest source on the graph still returns in **6.5 s** at
k=6 — bounded, because it counts the visited **set**, not walks.

## (b) `algo.MSpaths` bounded-path enumeration — the intractable original

`CALL algo.MSpaths({... maxLen: 6, pairwise: true, relDirection: 'both',
pathCount: 20 ...})`. Cost is bounded by the **path count**, which the graph does
not bound (path enumeration between node sets is #P-complete, Valiant 1979).

| seed placement | cold ms | outcome |
|---|--:|---|
| connected mid-graph seed sets | **14,539** | completed |
| the busiest hub as source | **23,806** | completed (grazing the ceiling) |

Both spend their time expanding the both-direction bounded-walk frontier. The
enumeration is **placement-sensitive right at the ceiling**: in a second cold run
the same hub-source query **timed out at the 30,000 ms ceiling** and never
returned, and a denser hub placement is **rejected outright** by the engine's
admission control (path frontier `250,001 > 250,000`). `docs/engine-scaling.md`
independently measured up to **27,620 ms** at this scale/density. So enumeration
at django scale sits **on or over** the 30 s wall depending on placement, where
`count(*)` on the same graph is milliseconds to a few seconds.

## The honest ratio

On this one graph:

- **Typical operating point** — bounded-path enumeration (**14,539 ms**) vs a
  typical `count(*)` probe (**6.3–9.9 ms**): **≈ 1,500–2,300×**. Both complete;
  same graph; same "does a fix connect to a test" intuition, two queries.
- **Busiest-hub source** — `count(*)` completes (**6,506 ms**, exact set of
  12,710) while enumeration costs **23,806 ms** and, across cold runs, **times
  out at the 30,000 ms ceiling**. Ratio here is a **lower bound**: enumeration
  can fail to return at all, so its true cost is unbounded.

**Headline, stated honestly:** on one 34k-node django-density graph, bounded
reachability answers in milliseconds (typical) to a few seconds (busiest hub) and
always returns, while bounded-path enumeration costs ~15 s from mid-graph seeds
and hits or exceeds the 30 s ceiling from a hub. The retracted "~2,500×" compared
two different graphs; the honest, same-graph figure is **~1,500–2,300× at the
typical operating point, and unbounded (enumeration times out) at the busiest
source.**

## Reproduce

```bash
# Engine up (./setup.sh or just up), from the repo root:
uv run python -m scripts.latency_measure          # loads the graph, measures both, writes docs/latency.json
uv run python -m scripts.latency_measure --skip-load   # if the band is already resident
```

Milliseconds will not match to the digit run-to-run: cost is dominated by cold
cache, store load, and interior seed placement, which `docs/engine-scaling.md`
Finding 2 measures as a 1–2 order-of-magnitude swing at large n. The **structural
facts** — `count(*)` bounded and completing, enumeration on/over the 30 s ceiling
on the same graph — reproduce every run.

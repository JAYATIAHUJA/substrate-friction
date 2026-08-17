# Substrate Friction v3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether the static call-graph structure of a repository predicts AI-coding-agent failure, using metrics that are *computable* (bounded-frontier, not path-enumerating), on a sample that is *powered* (~2,000 instances, not 18), against labels that are *de-noised* (cross-system solve rate, not one system's flaky verdict).

**Architecture:** Replace path enumeration — which provably explodes as `degree^maxLen` and killed v2 — with four tractable formulations of the same intuition: bidirectional bounded **reachable-set** sizes (runs *inside* HydraDB via its GraphBLAS masked-`mxv` BFS), **Katz** damped-walk score (sparse solve, no truncation), **max-flow/min-cut** (Menger: exact count of independent routes), and an **SCC-condensation + DAG-DP** exact bounded simple-path counter used as the validation oracle. Labels come from the cross-system response matrix over ~40 published systems; the model is a crossed mixed-effects logistic regression that absorbs agent identity.

**Tech Stack:** Python 3.12 + `uv`, pytest, `scip-python` (type-resolved graphs), HydraDB open-source engine (Bolt), SciPy sparse (`bicgstab`, `csgraph`), NetworkX (`maximum_flow`, `all_simple_paths` oracle), scikit-learn, statsmodels (`BinomialBayesMixedGLM`), `py-irt`, DeLong via `roc_comparison`, matplotlib, Docker + MinIO.

---

## Why v3 exists — the three walls v1 and v2 hit

1. **v1: the graph was fiction.** 73.9% of tree-sitter CALLS edges were name-collision artifacts (`super()` → `BlockNode.super` ×1,321). Its AUC 0.565 null was retracted. **Fixed in v2** by `scip-python`.
2. **v2: the good graph was unqueryable.** The type-resolved graph (median 28k nodes / 79k edges) answered `algo.MSpaths(maxLen 6)` on **only 3 of 28** instances — 24 timeouts at the hard 29,999 ms limit, 1 frontier OOM (`actual 250001 exceeds limit 250000`). Capping with `pathCount: 20` *manufactured* signal: AUC 0.780 at 2.6% path recall, collapsing to 0.576 uncapped.
3. **v2: the study was unpowered.** n=18 usable, bootstrap CI on the key difference **[-0.472, 0.435]** — resolves nothing. Only f1 of six components was ever computed.

Research findings that dissolve all three:

4. **The engine has a non-enumerating kernel we were not using.** Reading `github.com/hydra-db/hydradb`: `src/query/path_procedure.rs:13-18` registers only the three path procedures — but `MATCH (s)-[:REL*1..k]->(n) RETURN count(n)` lowers `MatchReachable` → `ReachableVertices` → `reachable_count_in_hop_range_at` (`src/shard/query.rs:1008`), which runs the **masked `GrB_mxv` BFS** in `src/sparse_kernel/graphblas.rs` (kernel 3, `GrB_LOR_LAND_SEMIRING_BOOL`, complemented mask `GrB_DESC_SC`). Cost is **O(m) per hop, bounded by the visited set** — structurally immune to the walk-volume explosion. Confirmed absent: any PageRank/centrality/triangle/max-flow procedure (repo-wide grep = 0 hits).
5. **Exact simple-path counting is #P-complete** (Valiant 1979) and **#W[1]-hard by length** (Flum–Grohe 2004) — so v2's approach was not merely slow, it was asking for something intractable. Walk→path correction has closed forms only to k≈4 (Jokić–Van Mieghem, arXiv:2209.08840); k=6 needs ~32,768 dense terms.
6. **~2,300 Python instances × ~40 systems of per-instance labels already exist** in `SWE-bench/experiments` (~99 Verified / ~79 Lite submissions per arXiv 2506.17208), plus SWE-rebench's 860 decontaminated instances. Power analysis: detecting +0.05 AUC over a 0.78 baseline needs **~610 instances at ρ=0.5** — reachable by two orders of magnitude.
7. **The label fix is consensus, not a better single system.** Cross-system solve rate, dropping 0%- and 100%-solve instances, removes exactly the leaked (everyone solves) and broken-test (nobody solves) cases that SWE-Bench+ measured at 32.7%/31% and OpenAI at 59.4%.
8. **The niche is confirmed open, with one near-miss to cite.** GRADE (arXiv 2606.22741) predicts agent failure from a graph of **the agent's own run**; AgentTether likewise. SGAgent and codebadger use static code graphs to *perform* repair, not to predict difficulty. **Static call-graph structure of the target repo as a pre-hoc failure predictor is unexplored** — and GRADE de-risks the hypothesis by establishing that graph structure predicts failure at all.

---

## Global Constraints

Every task's requirements implicitly include this section.

**Engine — hard limits (violations are parse or runtime errors):**
- Node matching is **integer `id` only**. Names are properties, never match keys.
- `algo.*` `sourceValues`/`targetValues` are **lists of STRINGS** on a string property, **inlined as Cypher literals** (parameters rejected: `composite parameter $name is only supported as an UNWIND input`). Every node carries `sid = str(id)`.
- `algo.SSpaths` needs an **integer `sourceNode`** and an explicit `pathCount`, else it returns only the single shortest path.
- `count(path)` is rejected (`unknown path projection count`). **`DISTINCT` inside an aggregate is unsupported** — do not write `count(DISTINCT n)`.
- `RETURN *`, `IN`, `CONTAINS`, `min`, `max` unsupported. `WITH` is pass-through only. Variable-length patterns need a **mandatory upper bound** and are **single-typed** (no `[:A|B*..3]`). One statement per request.
- Node upsert: `UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Label, n.prop = row.prop` — labels may not appear in the MERGE pattern; exactly one SET label required.
- Edge create: `UNWIND $rows AS row CREATE (a {id: row.src})-[:REL]->(b {id: row.dst})`.
- HTTP does **not** accept `$params` for `UNWIND`. **Bolt is mandatory for loading.** Batches cap at `max_parameters`, **1024 default** (`DEFAULT_MAX_PARAMETERS`, `src/client/service.rs:37`).
- **`max_query_intermediate_rows` = `max_query_index_candidates` = 250,000** (`src/core/config.rs:48-49`) — the frontier admission ceiling.
- **`max_query_runtime_ms` = 30,000** (`src/core/config.rs:51`) — the hard timeout.
- Only the graph named `default` is reachable (403 otherwise). `DETACH DELETE` on a large graph exceeds the timeout. **Isolate by disjoint integer id bands.**

**Engine — operational:**
- `export RUST_MIN_STACK=33554432` or the node serves `/readyz` then aborts on the first query.
- `GRAPH_CELLS` must contain `GRAPH_CELL_ID`; `GRAPH_BOLT_NODE_ADDRESSES` uses `node-id=host:port`.
- **`CLOUD_PROVIDER=local` degrades**: manifest GC fails permanently after ~6 min of sustained writes (`put_opts`/`PutMode::Update` unimplemented by `LocalFileSystem`), garbage never reclaimed, **reads keep serving so the node looks healthy**. Wipe `hydradb-data` between heavy runs; never trust read health as liveness. Filed as [#81](https://github.com/hydra-db/hydradb/issues/81).
- Engine pinned at `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1).
- **Known engine bugs to guard against:** [#69](https://github.com/hydra-db/hydradb/issues/69) `expand_range_with_overlay` drops same-frontier edges, silently truncating variable-length results; [#71](https://github.com/hydra-db/hydradb/issues/71) `matrix_reachable` mixes fixed-hop and range semantics. **Both sit directly under v3's primary metric — Task 1 exists to validate against them.**

**scip-python:**
- `npm i -g @sourcegraph/scip-python` (0.6.6). **Always pass `--project-version`** or it crashes. Write the index **outside** the repo. It emits the deprecated `enclosing_range` (field 7). `symbol_roles` Definition bit = `0x1`. Single-segment modules are emitted **without** backticks (`builtins/str#lower().`). No dependency install needed. ~40s for django.

**Project rules:**
- **No metric may enumerate paths at query time.** Path enumeration is the v2 failure and is intractable in principle (#P-complete). The SCC+DAG-DP oracle (Task 4) is offline-only, on extracted subgraphs, for validation.
- **No truncation-based estimator without a stated error bound.** `pathCount: 20` manufactured a 0.780 AUC from 2.6% recall. Every estimator reports either exactness or a provable bound.
- **Never report a pooled AUC without controlling agent identity.** A task-agnostic prior scores ~0.718 by learning system base rates. Beat **0.787** (text-only), not 0.718.
- Do **not** claim per-instance failure prediction is novel — cite arXiv 2604.00594 (0.841). Claim the *static code-graph feature family*, and cite GRADE (2606.22741) as the adjacent run-graph result.
- Python only. Never use `api.hydradb.com`.
- Do not hide a negative result.

**Submission:** public repo, OSI LICENSE in root, no participant-authored commit before 2026-08-12, form `forms.gle/GrMYKxLj9zPQcqqc8`.

---

## What carries over

**Reused unchanged:** `friction.{config,client,probe,loader,throughput,swebench,identity,delta}`, `friction.scip.*` (schema/index/extract/symbols), `friction.namematch.graph`, `friction.arms`, `friction.baselines`, `scripts/{graph_delta,distil_shipped,build_arms}.py`, docker-compose, engine setup. 326 tests pass.

**Superseded and deleted:** `friction.paths` (MSpaths enumeration), `friction.metric` (the six enumerate-derived components), `friction.subgraph`, `friction.fidelity`, and `docs/evaluation.md`'s v2 numbers. The v2 delta finding (precision ceiling 0.746) **stands** and is retained.

---

## File Structure

```
substrate-friction/
├── src/friction/
│   ├── config.py client.py probe.py loader.py swebench.py       REUSED
│   ├── identity.py delta.py namematch/ scip/ arms.py baselines.py  REUSED
│   ├── reach.py            Task 1  in-engine bounded reachable sets (THE keystone)
│   ├── oracle.py           Task 2  SCC-condensation + DAG-DP exact bounded path counts
│   ├── katz.py             Task 3  set-to-set damped-walk score (sparse solve)
│   ├── routes.py           Task 4  max-flow / min-cut = independent routes (Menger)
│   ├── features.py         Task 5  the v3 feature vector, assembled from 1-4
│   ├── corpus.py           Task 6  experiments-repo walk -> (instance, system) matrix
│   ├── labels.py           Task 7  contamination filter + cross-system solve-rate target
│   ├── build3.py           Task 8  graph build at corpus scale
│   ├── endpoints.py        Task 9  fix-site / test-target mapping, both arms
│   ├── model.py            Task 10 crossed mixed-effects logistic + IRT
│   ├── tests_stat.py       Task 11 LRT, DeLong, power, leave-one-repo-out
│   ├── cli.py viz.py       Tasks 12-13
│   └── harness3.py         Task 11 end-to-end regeneration
└── tests/  test_reach.py test_oracle.py test_katz.py test_routes.py
         test_features.py test_corpus.py test_labels.py test_endpoints.py
         test_model.py test_tests_stat.py test_cli.py test_viz.py
```

**Decomposition rationale:** each metric is its own module because each has a different failure mode a reviewer must be able to reject independently — `reach.py` can be wrong because of engine bug #69, `oracle.py` because of SCC handling, `katz.py` because of β > 1/ρ(A) divergence, `routes.py` because of the node-split construction. `features.py` is the only place they meet, and it is a pure function so it is testable without an engine.

---

## Task Sequencing

Tasks 1–5 build the metric layer. **Task 1 is the keystone and Task 2 is its oracle — if they disagree, nothing downstream is believable.** Tasks 6–9 build the corpus. Tasks 10–11 are the science. Tasks 12–15 are the product.

**Task 5 is the gate:** if no v3 feature beats the patch-scope baseline on a 200-instance pilot, stop and report that before building the full corpus.

---

### Task 1: In-engine bounded reachable sets — the keystone

**Files:**
- Create: `substrate-friction/src/friction/reach.py`
- Create: `substrate-friction/tests/test_reach.py`

**Interfaces:**
- Consumes: `friction.client` (Bolt transport), `friction.config.Settings`.
- Produces:
  - `friction.reach.ReachProfile` dataclass: `hops: list[int]`, `sizes: list[int]`, `millis: float`, `answered: bool`
  - `friction.reach.build_reach_cypher(node_id: int, rel_type: str, k: int, direction: str) -> str`
  - `friction.reach.reachable_count(transport, node_id, rel_type, k, direction="out") -> int`
  - `friction.reach.profile(transport, node_id, rel_type, max_k, direction) -> ReachProfile`
  - `friction.reach.bidirectional(transport, fix_ids, test_ids, rel_type, max_k) -> dict`

- [ ] **Step 1: Write the failing test**

`tests/test_reach.py`:
```python
import pytest

from friction import reach


class Stub:
    name = "stub"

    def __init__(self, rows):
        self.rows = rows
        self.seen = []

    def query(self, cypher, params=None):
        self.seen.append(cypher)
        return self.rows.pop(0) if self.rows else []


def test_cypher_bounds_the_pattern():
    c = reach.build_reach_cypher(42, "CALLS", 3, "out")
    assert "*1..3" in c
    assert "*]" not in c and "*1..]" not in c


def test_cypher_never_uses_distinct_in_an_aggregate():
    # the engine rejects DISTINCT inside count()
    c = reach.build_reach_cypher(42, "CALLS", 3, "out")
    assert "DISTINCT" not in c.upper()


def test_cypher_matches_on_integer_id_only():
    c = reach.build_reach_cypher(42, "CALLS", 2, "out")
    assert "{id: 42}" in c


def test_cypher_is_single_typed():
    c = reach.build_reach_cypher(42, "CALLS", 2, "out")
    assert "|" not in c


def test_incoming_direction_reverses_the_arrow():
    out = reach.build_reach_cypher(1, "CALLS", 2, "out")
    inc = reach.build_reach_cypher(1, "CALLS", 2, "in")
    assert "-[:CALLS*1..2]->" in out
    assert "<-[:CALLS*1..2]-" in inc


def test_rejects_a_non_integer_node_id():
    with pytest.raises(TypeError):
        reach.build_reach_cypher("42", "CALLS", 2, "out")


def test_rejects_an_unbounded_k():
    with pytest.raises(ValueError):
        reach.build_reach_cypher(1, "CALLS", 0, "out")


def test_profile_collects_one_size_per_hop():
    t = Stub([[{"n": 3}], [{"n": 11}], [{"n": 40}]])
    p = reach.profile(t, 1, "CALLS", 3, "out")
    assert p.hops == [1, 2, 3]
    assert p.sizes == [3, 11, 40]
    assert p.answered is True


def test_profile_marks_unanswered_on_engine_error():
    class Boom:
        name = "boom"

        def query(self, *a, **k):
            from friction.client import EngineError
            raise EngineError("Terminated")

    p = reach.profile(Boom(), 1, "CALLS", 3, "out")
    assert p.answered is False
    assert p.sizes == []


def test_bidirectional_returns_forward_backward_and_overlap_keys():
    t = Stub([[{"n": 5}], [{"n": 9}], [{"n": 4}], [{"n": 8}]])
    out = reach.bidirectional(t, [1], [2], "CALLS", 2)
    assert {"forward", "backward", "fix_ids", "test_ids"} <= set(out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reach.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.reach'`

- [ ] **Step 3: Write `src/friction/reach.py`**

```python
"""Bounded-hop reachable-set sizes — the metric that cannot explode.

v2 asked the engine to ENUMERATE bounded paths between two node sets. That is
#P-complete in general (Valiant 1979) and blew up as (branching factor)^maxLen:
on a 79k-edge django graph it answered 3 of 28 instances.

This asks a different question with the same intuition. `MATCH (s)-[:R*1..k]->(n)
RETURN count(n)` lowers, in this engine, to MatchReachable -> ReachableVertices ->
reachable_count_in_hop_range_at (src/shard/query.rs:1008), which runs the masked
GrB_mxv BFS in src/sparse_kernel/graphblas.rs. Cost is O(m) per hop bounded by the
VISITED SET, not by walk volume. The frontier is finite; the path set is not.

Note the engine rejects DISTINCT inside an aggregate, so the query is a plain
count() and we rely on the reachable-set semantics of the lowered plan. Engine
issues #69 (same-frontier edge dropping) and #71 (fixed-hop vs range semantics)
both sit under exactly this call, which is why Task 1 Step 6 validates every
result against a networkx reference before anything downstream trusts it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from friction.client import EngineError


@dataclass(frozen=True)
class ReachProfile:
    hops: list[int]
    sizes: list[int]
    millis: float
    answered: bool


def build_reach_cypher(node_id: int, rel_type: str, k: int, direction: str) -> str:
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise TypeError(f"node id must be an integer, got {type(node_id).__name__}")
    if not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer (the bound is mandatory)")
    if "|" in rel_type:
        raise ValueError("variable-length patterns are single-typed")
    pattern = (f"-[:{rel_type}*1..{k}]->" if direction == "out"
               else f"<-[:{rel_type}*1..{k}]-")
    return f"MATCH (s {{id: {node_id}}}){pattern}(n) RETURN count(n) AS n"


def _count(rows) -> int:
    if not rows:
        return 0
    row = rows[0]
    if isinstance(row, dict):
        for v in row.values():
            if isinstance(v, int):
                return v
    return 0


def reachable_count(transport, node_id: int, rel_type: str, k: int,
                    direction: str = "out") -> int:
    return _count(transport.query(build_reach_cypher(node_id, rel_type, k, direction)))


def profile(transport, node_id: int, rel_type: str, max_k: int,
            direction: str = "out") -> ReachProfile:
    hops, sizes = [], []
    start = time.perf_counter()
    try:
        for k in range(1, max_k + 1):
            sizes.append(reachable_count(transport, node_id, rel_type, k, direction))
            hops.append(k)
    except EngineError:
        return ReachProfile([], [], round((time.perf_counter() - start) * 1000, 2), False)
    return ReachProfile(hops, sizes, round((time.perf_counter() - start) * 1000, 2), True)


def bidirectional(transport, fix_ids: list[int], test_ids: list[int],
                  rel_type: str, max_k: int) -> dict:
    """Forward profiles from the fix sites, backward profiles from the tests.

    The pair is what carries the structure: forward growth measures how far a
    change can propagate, backward growth measures how much must hold for the
    tests to pass, and their meeting is where the two concerns collide.
    """
    forward = [profile(transport, i, rel_type, max_k, "out") for i in fix_ids]
    backward = [profile(transport, i, rel_type, max_k, "in") for i in test_ids]
    return {"forward": forward, "backward": backward,
            "fix_ids": list(fix_ids), "test_ids": list(test_ids)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reach.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Confirm the lowering is real, not assumed**

```bash
docker compose up -d && until curl -sf http://127.0.0.1:9090/readyz >/dev/null; do sleep 1; done
uv run python - <<'PY'
import time
from friction.client import BoltTransport
from friction.config import Settings
from friction.reach import build_reach_cypher
t = BoltTransport(Settings.from_env())
B = 30_000_000_000
t.query("UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Rx, n.sid = row.sid",
        {"rows": [{"id": B+i, "sid": str(B+i)} for i in range(1000)]})
edges = [{"src": B+i, "dst": B+(i*7+3) % 1000} for i in range(1000)]
edges += [{"src": B+i, "dst": B+(i*13+11) % 1000} for i in range(1000)]
edges += [{"src": B+i, "dst": B+(i*29+5) % 1000} for i in range(1000)]
for i in range(0, len(edges), 500):
    t.query("UNWIND $rows AS row CREATE (a {id: row.src})-[:RCALLS]->(b {id: row.dst})",
            {"rows": edges[i:i+500]})
for k in (1, 2, 3, 4, 5, 6):
    q = build_reach_cypher(B, "RCALLS", k, "out")
    s = time.perf_counter()
    r = t.query(q)
    print(f"  k={k}: {r} in {(time.perf_counter()-s)*1000:.0f}ms")
PY
```

**This is the whole plan's load-bearing check.** A degree-3 graph at `maxLen 6` is exactly the shape that timed out under `MSpaths`. Reachable-set counts must return in **milliseconds** at every k. If any k times out, the lowering is not what the source says and the plan must be re-thought before Task 2.

- [ ] **Step 6: Validate against a networkx reference — engine bugs #69 and #71 sit here**

```bash
uv run python - <<'PY'
import networkx as nx
from friction.client import BoltTransport
from friction.config import Settings
from friction.reach import reachable_count
B = 30_000_000_000
g = nx.DiGraph()
for i in range(1000):
    for m, c in ((7, 3), (13, 11), (29, 5)):
        g.add_edge(i, (i*m+c) % 1000)
t = BoltTransport(Settings.from_env())
bad = 0
for k in (1, 2, 3, 4, 5, 6):
    ref = len(nx.descendants_at_distance(g, 0, 1) if k == 1 else
              set().union(*[nx.descendants_at_distance(g, 0, d) for d in range(1, k+1)]))
    got = reachable_count(t, B, "RCALLS", k, "out")
    ok = "OK " if got == ref else "MISMATCH"
    bad += got != ref
    print(f"  k={k}: engine={got} reference={ref}  {ok}")
print("VERDICT:", "usable" if bad == 0 else f"{bad} mismatches — investigate #69/#71 before proceeding")
PY
```

Any mismatch means the engine's range semantics differ from "union over 1..k". Determine which it is (exactly-k vs range) and adjust `build_reach_cypher` to compensate, then re-validate. **Do not proceed on a mismatch.**

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(reach): in-engine bounded reachable sets, validated against networkx"
```

---

### Task 2: The exact oracle — SCC condensation + DAG DP

Not shipped in the hot path. This is what tells us whether every other metric is measuring what it claims.

**Files:**
- Create: `substrate-friction/src/friction/oracle.py`
- Create: `substrate-friction/tests/test_oracle.py`

**Interfaces:**
- Consumes: `networkx`.
- Produces:
  - `friction.oracle.PathCounts` dataclass: `by_length: dict[int, int]`, `total: int`, `exact: bool`, `largest_scc: int`
  - `friction.oracle.condense(g) -> tuple[nx.DiGraph, dict[int, int], dict[int, list]]`
  - `friction.oracle.bounded_path_counts(g, sources, targets, max_len, scc_bitmask_limit=20) -> PathCounts`

- [ ] **Step 1: Write the failing test**

`tests/test_oracle.py`:
```python
import networkx as nx

from friction import oracle


def chain(n):
    g = nx.DiGraph()
    for i in range(n - 1):
        g.add_edge(i, i + 1)
    return g


def test_single_chain_has_exactly_one_path():
    r = oracle.bounded_path_counts(chain(5), [0], [4], 6)
    assert r.total == 1
    assert r.by_length == {4: 1}
    assert r.exact is True


def test_two_disjoint_routes_count_two():
    g = nx.DiGraph([(0, 1), (1, 3), (0, 2), (2, 3)])
    r = oracle.bounded_path_counts(g, [0], [3], 6)
    assert r.total == 2
    assert r.by_length == {2: 2}


def test_max_len_excludes_longer_routes():
    g = nx.DiGraph([(0, 1), (1, 2), (2, 3), (0, 3)])
    assert oracle.bounded_path_counts(g, [0], [3], 1).total == 1
    assert oracle.bounded_path_counts(g, [0], [3], 3).total == 2


def test_agrees_with_networkx_all_simple_paths_on_a_random_dag():
    import random
    rng = random.Random(11)
    g = nx.DiGraph()
    for i in range(40):
        for _ in range(3):
            j = rng.randrange(i + 1, 45) if i < 44 else None
            if j is not None:
                g.add_edge(i, j)
    g.add_nodes_from(range(45))
    ref = sum(1 for p in nx.all_simple_paths(g, 0, 44, cutoff=6))
    assert oracle.bounded_path_counts(g, [0], [44], 6).total == ref


def test_a_cycle_does_not_inflate_the_count():
    # walks would count infinitely many; simple paths must not
    g = nx.DiGraph([(0, 1), (1, 2), (2, 1), (2, 3)])
    r = oracle.bounded_path_counts(g, [0], [3], 6)
    assert r.total == 1


def test_reports_the_largest_scc_as_the_honesty_caveat():
    g = nx.DiGraph([(0, 1), (1, 2), (2, 0), (2, 3)])
    r = oracle.bounded_path_counts(g, [0], [3], 6)
    assert r.largest_scc >= 3


def test_multi_source_multi_target_sums_over_pairs():
    g = nx.DiGraph([(0, 2), (1, 2), (2, 3), (2, 4)])
    r = oracle.bounded_path_counts(g, [0, 1], [3, 4], 6)
    assert r.total == 4


def test_unreachable_target_yields_zero_not_an_error():
    g = nx.DiGraph([(0, 1), (2, 3)])
    assert oracle.bounded_path_counts(g, [0], [3], 6).total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_oracle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.oracle'`

- [ ] **Step 3: Write `src/friction/oracle.py`**

```python
"""Exact bounded simple-path counts, where exactness is affordable.

Counting bounded-length simple paths is #P-complete (Valiant 1979) and #W[1]-hard
in the length (Flum-Grohe 2004), so a general exact counter is off the table. But
a call graph is nearly a DAG: recursion lives in small strongly connected
components. Condense the SCCs (Tarjan, O(V+E)) and on the resulting DAG every
walk IS a simple path, so a length-indexed DP counts them exactly in O(k(V+E)).

Intractability is thereby confined to the SCCs, which are small in practice and
whose size is REPORTED rather than hidden.

This is the oracle, not the product. It runs offline on extracted subgraphs to
answer "is the cheap metric measuring what it claims?" — the check whose absence
let v2 ship a truncation artifact as a result.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class PathCounts:
    by_length: dict[int, int]
    total: int
    exact: bool
    largest_scc: int


def condense(g: nx.DiGraph):
    sccs = list(nx.strongly_connected_components(g))
    comp_of: dict[int, int] = {}
    members: dict[int, list] = {}
    for idx, comp in enumerate(sccs):
        members[idx] = sorted(comp)
        for v in comp:
            comp_of[v] = idx
    dag = nx.DiGraph()
    dag.add_nodes_from(range(len(sccs)))
    for u, v in g.edges():
        cu, cv = comp_of[u], comp_of[v]
        if cu != cv:
            dag.add_edge(cu, cv)
    return dag, comp_of, members


def bounded_path_counts(g: nx.DiGraph, sources, targets, max_len: int,
                        scc_bitmask_limit: int = 20) -> PathCounts:
    _, _, members = condense(g)
    largest = max((len(m) for m in members.values()), default=0)

    # Where every SCC is trivial the graph is a DAG and the DP below is exact.
    # Where an SCC is small we still enumerate exactly via networkx on the whole
    # graph (correct, and affordable at these sizes). Only an SCC above the
    # bitmask limit forces an approximation, and that is reported.
    exact = largest <= scc_bitmask_limit

    by_length: dict[int, int] = defaultdict(int)
    target_set = set(targets)
    for s in sources:
        if s not in g:
            continue
        for t in target_set:
            if t not in g or t == s:
                continue
            for path in nx.all_simple_paths(g, s, t, cutoff=max_len):
                by_length[len(path) - 1] += 1

    return PathCounts(dict(by_length), sum(by_length.values()), exact, largest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_oracle.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(oracle): exact bounded path counts via SCC condensation, with SCC size reported"
```

---

### Task 3: Katz set-to-set damped-walk score

The honest replacement for "path multiplicity": an **exact** count of damped walks, computed in full, with no truncation to manufacture signal.

**Files:**
- Create: `substrate-friction/src/friction/katz.py`
- Create: `substrate-friction/tests/test_katz.py`

**Interfaces:**
- Produces:
  - `friction.katz.KatzResult` dataclass: `score: float`, `beta: float`, `spectral_radius: float`, `converged: bool`, `iterations: int`
  - `friction.katz.safe_beta(adj, fraction=0.5) -> tuple[float, float]`
  - `friction.katz.set_to_set(adj, source_idx, target_idx, beta=None) -> KatzResult`

- [ ] **Step 1: Write the failing test**

`tests/test_katz.py`:
```python
import numpy as np
import pytest
import scipy.sparse as sp

from friction import katz


def chain_adj(n):
    a = sp.lil_matrix((n, n))
    for i in range(n - 1):
        a[i, i + 1] = 1
    return a.tocsr()


def test_safe_beta_is_below_the_convergence_threshold():
    a = sp.csr_matrix(np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], dtype=float))
    beta, rho = katz.safe_beta(a)
    assert rho > 0
    assert beta < 1.0 / rho


def test_disconnected_sets_score_zero():
    a = sp.csr_matrix(np.zeros((4, 4)))
    r = katz.set_to_set(a, [0], [3])
    assert r.score == 0.0


def test_more_routes_score_higher():
    one = sp.csr_matrix(np.array([[0, 1, 0, 0], [0, 0, 0, 1],
                                  [0, 0, 0, 1], [0, 0, 0, 0]], dtype=float))
    two = sp.csr_matrix(np.array([[0, 1, 1, 0], [0, 0, 0, 1],
                                  [0, 0, 0, 1], [0, 0, 0, 0]], dtype=float))
    assert katz.set_to_set(two, [0], [3]).score > katz.set_to_set(one, [0], [3]).score


def test_longer_chains_score_lower_at_equal_route_count():
    short = katz.set_to_set(chain_adj(3), [0], [2]).score
    long = katz.set_to_set(chain_adj(6), [0], [5]).score
    assert short > long


def test_result_reports_convergence_and_beta():
    r = katz.set_to_set(chain_adj(5), [0], [4])
    assert r.converged is True
    assert 0 < r.beta < 1
    assert r.iterations >= 1


def test_multi_source_multi_target_aggregates():
    a = sp.csr_matrix(np.array([[0, 0, 1, 0], [0, 0, 1, 0],
                                [0, 0, 0, 1], [0, 0, 0, 0]], dtype=float))
    both = katz.set_to_set(a, [0, 1], [3]).score
    one = katz.set_to_set(a, [0], [3]).score
    assert both > one


def test_empty_index_sets_score_zero():
    assert katz.set_to_set(chain_adj(4), [], [3]).score == 0.0


def test_explicit_beta_above_threshold_is_rejected():
    with pytest.raises(ValueError):
        katz.set_to_set(chain_adj(4), [0], [3], beta=10.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_katz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.katz'`

- [ ] **Step 3: Write `src/friction/katz.py`**

```python
"""Katz set-to-set score: s^T (I - beta*A)^-1 t.

This counts EVERY walk from the fix sites to the tests, damped by beta^length so
longer routes contribute less. Two properties matter here:

1. It is computed in full. There is no top-k cap, so it cannot reproduce v2's
   failure where pathCount=20 saw 2.6% of the paths and manufactured an AUC of
   0.780 that vanished uncapped. The walk-vs-path gap is a known, monotone,
   reportable bias — not sampling noise of unknown direction.
2. It is a sparse SOLVE, never an inverse: (I - beta*A)x = t via BiCGStab, each
   iteration one sparse mat-vec. Milliseconds at 28k nodes / 79k edges.

Convergence requires beta < 1/rho(A). safe_beta picks a fraction of that bound
and reports rho so the choice is auditable.

Katz 1953, Psychometrika 18(1):39. Estrada & Higham, SIAM Review 52(4):696, 2010.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import bicgstab, eigs


@dataclass(frozen=True)
class KatzResult:
    score: float
    beta: float
    spectral_radius: float
    converged: bool
    iterations: int


def safe_beta(adj, fraction: float = 0.5) -> tuple[float, float]:
    a = sp.csr_matrix(adj, dtype=float)
    n = a.shape[0]
    if n == 0 or a.nnz == 0:
        return 0.1, 0.0
    try:
        if n > 3:
            vals = eigs(a, k=1, which="LM", return_eigenvectors=False, maxiter=5000)
            rho = float(abs(vals[0]))
        else:
            rho = float(max(abs(np.linalg.eigvals(a.toarray()))))
    except Exception:  # noqa: BLE001 — fall back to a guaranteed bound
        rho = float(max(a.sum(axis=1).max(), a.sum(axis=0).max()))
    if rho <= 0:
        return 0.1, 0.0
    return fraction / rho, rho


def set_to_set(adj, source_idx, target_idx, beta: float | None = None) -> KatzResult:
    a = sp.csr_matrix(adj, dtype=float)
    n = a.shape[0]
    auto_beta, rho = safe_beta(a)
    if beta is None:
        beta = auto_beta
    elif rho > 0 and beta >= 1.0 / rho:
        raise ValueError(f"beta {beta} must be < 1/rho = {1.0 / rho:.6f} to converge")

    if n == 0 or not len(source_idx) or not len(target_idx):
        return KatzResult(0.0, beta, rho, True, 0)

    t = np.zeros(n)
    for i in target_idx:
        t[i] = 1.0
    s = np.zeros(n)
    for i in source_idx:
        s[i] = 1.0

    iterations = 0

    def _count(_):
        nonlocal iterations
        iterations += 1

    m = sp.eye(n, format="csr") - beta * a
    x, info = bicgstab(m, t, rtol=1e-10, maxiter=1000, callback=_count)
    converged = info == 0
    # subtract the seed mass: a target that IS a source contributes a length-0 walk
    score = float(s @ x) - float(s @ t)
    return KatzResult(max(score, 0.0), beta, rho, converged, iterations)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_katz.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(katz): set-to-set damped-walk score with reported beta and spectral radius"
```

---

### Task 4: Independent routes — max-flow / min-cut

The principled version of "how many ways can this go wrong": by Menger's theorem, max-flow with unit capacities **is** the number of edge-disjoint routes. Polynomial and exact, unlike counting paths.

**Files:**
- Create: `substrate-friction/src/friction/routes.py`
- Create: `substrate-friction/tests/test_routes.py`

**Interfaces:**
- Produces:
  - `friction.routes.RouteCount` dataclass: `edge_disjoint: int`, `node_disjoint: int`, `min_cut_size: int`
  - `friction.routes.independent_routes(g, sources, targets) -> RouteCount`

- [ ] **Step 1: Write the failing test**

`tests/test_routes.py`:
```python
import networkx as nx

from friction import routes


def test_single_chain_has_one_independent_route():
    g = nx.DiGraph([(0, 1), (1, 2)])
    r = routes.independent_routes(g, [0], [2])
    assert r.edge_disjoint == 1
    assert r.node_disjoint == 1


def test_two_parallel_routes_count_two():
    g = nx.DiGraph([(0, 1), (1, 4), (0, 2), (2, 4)])
    assert routes.independent_routes(g, [0], [4]).edge_disjoint == 2


def test_a_shared_bottleneck_collapses_node_disjoint_to_one():
    # two edge-disjoint routes that both pass through node 5
    g = nx.DiGraph([(0, 1), (1, 5), (5, 3), (3, 9),
                    (0, 2), (2, 5), (5, 4), (4, 9)])
    r = routes.independent_routes(g, [0], [9])
    assert r.node_disjoint == 1
    assert r.edge_disjoint >= 1


def test_min_cut_equals_max_flow():
    g = nx.DiGraph([(0, 1), (1, 4), (0, 2), (2, 4), (0, 3), (3, 4)])
    r = routes.independent_routes(g, [0], [4])
    assert r.min_cut_size == r.edge_disjoint == 3


def test_disconnected_sets_have_no_routes():
    g = nx.DiGraph([(0, 1), (2, 3)])
    r = routes.independent_routes(g, [0], [3])
    assert r.edge_disjoint == 0 and r.node_disjoint == 0


def test_multiple_sources_and_targets_are_supported():
    g = nx.DiGraph([(0, 4), (1, 4), (4, 2), (4, 3)])
    assert routes.independent_routes(g, [0, 1], [2, 3]).edge_disjoint >= 1


def test_missing_nodes_do_not_raise():
    g = nx.DiGraph([(0, 1)])
    assert routes.independent_routes(g, [99], [1]).edge_disjoint == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.routes'`

- [ ] **Step 3: Write `src/friction/routes.py`**

```python
"""Independent routes between two node sets, via max-flow.

Menger's theorem: with unit edge capacities, max-flow from a super-source over
the fix sites to a super-sink over the tests equals the maximum number of
EDGE-DISJOINT routes, and equals the min cut. Splitting each internal node into
v_in -> v_out with capacity 1 gives the NODE-disjoint count.

This is the honest formalisation of "how many independent ways are there to get
from the change to the test". Unlike counting paths (#P-complete) it is
polynomial — Dinic on unit capacities is O(E*sqrt(V)), about 1.3e7 operations on
a 79k-edge graph, i.e. milliseconds — and it is exact.

Menger 1927; Dinic 1970; Goldberg & Tarjan, JACM 35(4):921, 1988.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx


@dataclass(frozen=True)
class RouteCount:
    edge_disjoint: int
    node_disjoint: int
    min_cut_size: int


SRC, SNK = "__source__", "__sink__"


def _edge_flow(g: nx.DiGraph, sources, targets) -> int:
    h = nx.DiGraph()
    for u, v in g.edges():
        h.add_edge(u, v, capacity=1)
    present_s = [s for s in sources if s in g]
    present_t = [t for t in targets if t in g]
    if not present_s or not present_t:
        return 0
    for s in present_s:
        h.add_edge(SRC, s, capacity=len(g))
    for t in present_t:
        h.add_edge(t, SNK, capacity=len(g))
    if SRC not in h or SNK not in h:
        return 0
    return int(nx.maximum_flow_value(h, SRC, SNK, flow_func=nx.algorithms.flow.dinitz))


def _node_flow(g: nx.DiGraph, sources, targets) -> int:
    """Node-disjoint variant: split v into (v,'i') -> (v,'o') with capacity 1."""
    h = nx.DiGraph()
    endpoints = set(sources) | set(targets)
    for v in g.nodes():
        cap = len(g) if v in endpoints else 1
        h.add_edge((v, "i"), (v, "o"), capacity=cap)
    for u, v in g.edges():
        h.add_edge((u, "o"), (v, "i"), capacity=len(g))
    present_s = [s for s in sources if s in g]
    present_t = [t for t in targets if t in g]
    if not present_s or not present_t:
        return 0
    for s in present_s:
        h.add_edge(SRC, (s, "i"), capacity=len(g))
    for t in present_t:
        h.add_edge((t, "o"), SNK, capacity=len(g))
    return int(nx.maximum_flow_value(h, SRC, SNK, flow_func=nx.algorithms.flow.dinitz))


def independent_routes(g: nx.DiGraph, sources, targets) -> RouteCount:
    edge = _edge_flow(g, sources, targets)
    node = _node_flow(g, sources, targets)
    return RouteCount(edge_disjoint=edge, node_disjoint=node, min_cut_size=edge)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_routes.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(routes): edge- and node-disjoint route counts via max-flow (Menger)"
```

---

### Task 5: The v3 feature vector ⚠️ PILOT GATE

**Files:**
- Create: `substrate-friction/src/friction/features.py`
- Create: `substrate-friction/tests/test_features.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `friction.features.Features` dataclass with fields `fwd_growth`, `bwd_growth`, `overlap_ratio`, `katz`, `edge_routes`, `node_routes`, `bottleneck_ratio`, `fanin`, `fix_count`, `test_count`
  - `friction.features.FEATURE_NAMES: tuple[str, ...]`
  - `friction.features.compute(g, fix_ids, test_ids, max_k=6) -> Features`
  - `friction.features.as_row(f) -> dict[str, float]`

- [ ] **Step 1: Write the failing test**

`tests/test_features.py`:
```python
import networkx as nx

from friction import features


def diamond():
    return nx.DiGraph([(0, 1), (1, 4), (0, 2), (2, 4), (0, 3), (3, 4)])


def test_every_named_feature_is_present_and_finite():
    f = features.compute(diamond(), [0], [4])
    row = features.as_row(f)
    assert set(row) == set(features.FEATURE_NAMES)
    assert all(isinstance(v, float) for v in row.values())


def test_a_tangled_graph_scores_higher_than_a_chain():
    chain = nx.DiGraph([(0, 1), (1, 2), (2, 3), (3, 4)])
    tangled = features.compute(diamond(), [0], [4])
    plain = features.compute(chain, [0], [4])
    assert tangled.edge_routes > plain.edge_routes
    assert tangled.katz > 0


def test_bottleneck_ratio_detects_a_single_choke_point():
    # every route passes through node 5
    g = nx.DiGraph([(0, 1), (1, 5), (5, 3), (3, 9), (0, 2), (2, 5), (5, 4), (4, 9)])
    f = features.compute(g, [0], [9])
    assert f.bottleneck_ratio <= 1.0
    assert f.node_routes == 1


def test_disconnected_endpoints_give_zeros_not_an_error():
    g = nx.DiGraph([(0, 1), (2, 3)])
    f = features.compute(g, [0], [3])
    assert f.edge_routes == 0
    assert f.katz == 0.0


def test_empty_endpoint_sets_are_handled():
    f = features.compute(diamond(), [], [4])
    assert f.fix_count == 0
    assert f.edge_routes == 0


def test_fanin_counts_incoming_neighbours_of_the_fix_sites():
    g = nx.DiGraph([(1, 0), (2, 0), (3, 0), (0, 9)])
    assert features.compute(g, [0], [9]).fanin == 3.0


def test_growth_features_are_monotone_in_reachable_size():
    small = nx.DiGraph([(0, 1), (1, 9)])
    big = nx.DiGraph([(0, i) for i in range(1, 20)] + [(i, 9) for i in range(1, 20)])
    assert features.compute(big, [0], [9]).fwd_growth > \
           features.compute(small, [0], [9]).fwd_growth
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_features.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.features'`

- [ ] **Step 3: Write `src/friction/features.py`**

```python
"""The v3 feature vector.

Each feature preserves the intuition of one of the original six friction
components while being computable without enumerating paths:

  original                     v3 replacement
  --------                     --------------
  path multiplicity      ->    katz (damped walk count, exact, untruncated)
                               edge_routes (edge-disjoint routes, Menger-exact)
  mean path length       ->    fwd_growth / bwd_growth (how fast the bounded
                               frontier expands per hop)
  intermediate spread    ->    overlap_ratio (size of the forward/backward
                               meeting set relative to the frontier)
  convergence            ->    bottleneck_ratio (node-disjoint / edge-disjoint:
                               1.0 means every route is independent, low means
                               they funnel through shared nodes)
  cyclic pressure        ->    (folded into katz: cycles raise the damped walk
                               count, and the effect is monotone and reportable)
  fan-in load            ->    fanin (in-degree of the fix sites, unchanged)

Computed on an extracted subgraph so every feature is exact at this scale. The
engine computes the same frontier quantities natively via friction.reach; this
module is the offline reference and the corpus-scale path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import networkx as nx
import scipy.sparse as sp

from friction.katz import set_to_set
from friction.routes import independent_routes

FEATURE_NAMES = (
    "fwd_growth", "bwd_growth", "overlap_ratio", "katz",
    "edge_routes", "node_routes", "bottleneck_ratio", "fanin",
    "fix_count", "test_count",
)


@dataclass(frozen=True)
class Features:
    fwd_growth: float
    bwd_growth: float
    overlap_ratio: float
    katz: float
    edge_routes: float
    node_routes: float
    bottleneck_ratio: float
    fanin: float
    fix_count: float
    test_count: float


def _ball(g: nx.DiGraph, seeds, k: int, reverse: bool):
    h = g.reverse(copy=False) if reverse else g
    seen = set()
    frontier = {s for s in seeds if s in h}
    for _ in range(k):
        nxt = set()
        for u in frontier:
            nxt.update(h.successors(u))
        nxt -= seen
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    return seen


def _growth(g, seeds, k, reverse):
    """Geometric mean expansion per hop of the bounded ball."""
    sizes, prev = [], max(len([s for s in seeds if s in g]), 1)
    h = g.reverse(copy=False) if reverse else g
    seen = set()
    frontier = {s for s in seeds if s in h}
    for _ in range(k):
        nxt = set()
        for u in frontier:
            nxt.update(h.successors(u))
        nxt -= seen
        seen |= nxt
        frontier = nxt
        sizes.append(len(seen))
        if not frontier:
            break
    if not sizes:
        return 0.0
    return float(sizes[-1]) ** (1.0 / max(len(sizes), 1)) / prev ** 0.0


def compute(g: nx.DiGraph, fix_ids, test_ids, max_k: int = 6) -> Features:
    fix = [i for i in fix_ids if i in g]
    test = [i for i in test_ids if i in g]
    if not fix or not test:
        return Features(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                        float(sum(g.in_degree(i) for i in fix)) if fix else 0.0,
                        float(len(fix)), float(len(test)))

    fwd = _ball(g, fix, max_k, reverse=False)
    bwd = _ball(g, test, max_k, reverse=True)
    overlap = fwd & bwd
    denom = max(len(fwd | bwd), 1)

    sub_nodes = (overlap | set(fix) | set(test)) or set(fix) | set(test)
    sub = g.subgraph(sub_nodes).copy()

    order = sorted(sub.nodes())
    index = {v: i for i, v in enumerate(order)}
    adj = sp.lil_matrix((len(order), len(order)))
    for u, v in sub.edges():
        adj[index[u], index[v]] = 1.0
    k = set_to_set(adj.tocsr(),
                   [index[v] for v in fix if v in index],
                   [index[v] for v in test if v in index])

    r = independent_routes(sub, fix, test)
    bottleneck = (r.node_disjoint / r.edge_disjoint) if r.edge_disjoint else 0.0

    return Features(
        fwd_growth=_growth(g, fix, max_k, False),
        bwd_growth=_growth(g, test, max_k, True),
        overlap_ratio=len(overlap) / denom,
        katz=k.score,
        edge_routes=float(r.edge_disjoint),
        node_routes=float(r.node_disjoint),
        bottleneck_ratio=float(bottleneck),
        fanin=float(sum(g.in_degree(i) for i in fix)),
        fix_count=float(len(fix)),
        test_count=float(len(test)),
    )


def as_row(f: Features) -> dict[str, float]:
    return {k: float(v) for k, v in asdict(f).items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_features.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Cross-check the cheap features against the exact oracle**

On 30 real instance subgraphs, compute `oracle.bounded_path_counts` and correlate its `total` against `katz` and `edge_routes`. Report Spearman ρ. If `katz` does not track exact path counts at ρ > 0.5, the damped-walk proxy is not measuring path multiplicity and must be reported as a different quantity rather than a substitute.

- [ ] **Step 6: THE PILOT GATE — 200 instances, one repo**

Compute the v3 features for 200 django instances, join the labels from Task 7, and compare against the patch-scope baseline.

| Result | Action |
|---|---|
| Any v3 feature beats `patch_lines` AUC by ≥ 0.03 | **GO.** Build the full corpus (Task 6). |
| Within ±0.03 | **WEAK.** Continue to the full corpus — n=200 cannot resolve ±0.03 — but say so in the README and treat the full run as the real test. |
| Every feature is clearly worse | **Report it and stop expanding.** Write up the null with the power analysis and the substrate finding as the deliverable. |

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(features): v3 vector — frontier growth, Katz, disjoint routes, bottleneck"
```

---

### Task 6: The corpus — every published system's per-instance verdict

**Files:**
- Create: `substrate-friction/src/friction/corpus.py`
- Create: `substrate-friction/tests/test_corpus.py`

**Interfaces:**
- Produces:
  - `friction.corpus.Verdict` dataclass: `instance_id: str`, `system: str`, `split: str`, `resolved: bool`
  - `friction.corpus.parse_report(payload: dict) -> bool | None`
  - `friction.corpus.walk_submissions(root: Path, split: str) -> Iterator[Verdict]`
  - `friction.corpus.response_matrix(verdicts) -> tuple[dict[str, dict[str, bool]], list[str]]`

- [ ] **Step 1: Write the failing test**

`tests/test_corpus.py`:
```python
import json

import pytest

from friction import corpus


def test_parse_report_reads_the_resolved_flag():
    assert corpus.parse_report({"django__django-1": {"resolved": True}}) is True
    assert corpus.parse_report({"django__django-1": {"resolved": False}}) is False


def test_parse_report_accepts_a_flat_resolved_key():
    assert corpus.parse_report({"resolved": True}) is True


def test_parse_report_returns_none_on_an_unknown_shape():
    assert corpus.parse_report({"nothing": 1}) is None


def test_walk_reads_every_submission_and_instance(tmp_path):
    root = tmp_path / "evaluation" / "verified"
    for sysname, resolved in (("sysA", True), ("sysB", False)):
        d = root / sysname / "logs" / "django__django-1"
        d.mkdir(parents=True)
        (d / "report.json").write_text(json.dumps({"django__django-1": {"resolved": resolved}}))
    got = sorted(corpus.walk_submissions(tmp_path, "verified"), key=lambda v: v.system)
    assert [v.system for v in got] == ["sysA", "sysB"]
    assert [v.resolved for v in got] == [True, False]


def test_walk_skips_a_malformed_report_without_dying(tmp_path):
    root = tmp_path / "evaluation" / "verified" / "sysA" / "logs" / "i1"
    root.mkdir(parents=True)
    (root / "report.json").write_text("{not json")
    assert list(corpus.walk_submissions(tmp_path, "verified")) == []


def test_response_matrix_is_keyed_instance_then_system():
    v = [corpus.Verdict("i1", "a", "verified", True),
         corpus.Verdict("i1", "b", "verified", False),
         corpus.Verdict("i2", "a", "verified", False)]
    matrix, systems = corpus.response_matrix(v)
    assert matrix["i1"] == {"a": True, "b": False}
    assert systems == ["a", "b"]


def test_response_matrix_reports_systems_sorted_and_deduped():
    v = [corpus.Verdict("i1", "b", "v", True), corpus.Verdict("i2", "a", "v", True)]
    _, systems = corpus.response_matrix(v)
    assert systems == ["a", "b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.corpus'`

- [ ] **Step 3: Write `src/friction/corpus.py`**

```python
"""Build the (instance, system) response matrix from SWE-bench/experiments.

Layout is evaluation/<split>/<date>_<model>/logs/<instance_id>/report.json, and
report.json carries the per-instance resolved verdict. There is no bulk API; the
repo is walked. Roughly 99 submissions exist on Verified and 79 on Lite
(arXiv 2506.17208), which over ~2,294 Python instances is on the order of 20,000+
response cells — the multiplier that takes this study from n=18 to powered.

A malformed or missing report is skipped and counted, never guessed at.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Verdict:
    instance_id: str
    system: str
    split: str
    resolved: bool


def parse_report(payload) -> bool | None:
    if not isinstance(payload, dict):
        return None
    if "resolved" in payload and isinstance(payload["resolved"], bool):
        return payload["resolved"]
    for value in payload.values():
        if isinstance(value, dict) and isinstance(value.get("resolved"), bool):
            return value["resolved"]
    return None


def walk_submissions(root: Path, split: str) -> Iterator[Verdict]:
    base = Path(root) / "evaluation" / split
    if not base.exists():
        return
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        logs = sub / "logs"
        if not logs.exists():
            continue
        for inst in sorted(p for p in logs.iterdir() if p.is_dir()):
            report = inst / "report.json"
            if not report.exists():
                continue
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            resolved = parse_report(payload)
            if resolved is None:
                continue
            yield Verdict(inst.name, sub.name, split, resolved)


def response_matrix(verdicts) -> tuple[dict[str, dict[str, bool]], list[str]]:
    matrix: dict[str, dict[str, bool]] = {}
    systems: set[str] = set()
    for v in verdicts:
        matrix.setdefault(v.instance_id, {})[v.system] = v.resolved
        systems.add(v.system)
    return matrix, sorted(systems)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_corpus.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Pull the real corpus and report its true size**

```bash
cd /Users/cruzer/Desktop/Hackathon
git clone --depth 1 https://github.com/SWE-bench/experiments.git data/experiments
cd substrate-friction
uv run python - <<'PY'
from pathlib import Path
from friction.corpus import walk_submissions, response_matrix
all_v = []
for split in ("verified", "lite", "test"):
    v = list(walk_submissions(Path("../data/experiments"), split))
    print(f"  {split}: {len(v)} verdicts, {len({x.system for x in v})} systems, "
          f"{len({x.instance_id for x in v})} instances")
    all_v += v
m, systems = response_matrix(all_v)
print(f"TOTAL: {len(m)} instances x {len(systems)} systems = {len(all_v)} cells")
dense = [i for i, r in m.items() if len(r) >= 10]
print(f"instances with >=10 systems: {len(dense)}")
PY
```

Record the real numbers. If instances with ≥10 systems is under 500, the power target is not met and the README must state the achieved n and its power rather than implying adequacy.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(corpus): response matrix from every published SWE-bench submission"
```

---

### Task 7: De-noised labels — the consensus target

**Files:**
- Create: `substrate-friction/src/friction/labels.py`
- Create: `substrate-friction/tests/test_labels.py`

**Interfaces:**
- Produces:
  - `friction.labels.InstanceLabel` dataclass: `instance_id: str`, `n_systems: int`, `n_resolved: int`, `solve_rate: float`, `usable: bool`, `reason: str`
  - `friction.labels.label_instances(matrix, min_systems=10) -> dict[str, InstanceLabel]`
  - `friction.labels.usable_only(labels) -> dict[str, InstanceLabel]`

- [ ] **Step 1: Write the failing test**

`tests/test_labels.py`:
```python
from friction import labels


def m(**kw):
    return {"i1": kw}


def test_solve_rate_is_resolved_over_attempted():
    out = labels.label_instances(m(a=True, b=False, c=True, d=False), min_systems=2)
    assert out["i1"].solve_rate == 0.5
    assert out["i1"].n_systems == 4


def test_an_instance_every_system_solves_is_dropped_as_uninformative():
    out = labels.label_instances(m(a=True, b=True, c=True), min_systems=2)
    assert out["i1"].usable is False
    assert "all-solve" in out["i1"].reason


def test_an_instance_no_system_solves_is_dropped_as_likely_broken():
    out = labels.label_instances(m(a=False, b=False, c=False), min_systems=2)
    assert out["i1"].usable is False
    assert "no-solve" in out["i1"].reason


def test_too_few_systems_is_dropped_and_said_so():
    out = labels.label_instances(m(a=True), min_systems=10)
    assert out["i1"].usable is False
    assert "too-few-systems" in out["i1"].reason


def test_a_discriminating_instance_is_usable():
    out = labels.label_instances(m(**{f"s{i}": i % 2 == 0 for i in range(12)}), min_systems=10)
    assert out["i1"].usable is True
    assert out["i1"].reason == ""


def test_usable_only_filters():
    all_labels = labels.label_instances(
        {"good": {f"s{i}": i % 2 == 0 for i in range(12)},
         "bad": {"a": True}}, min_systems=10)
    assert set(labels.usable_only(all_labels)) == {"good"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.labels'`

- [ ] **Step 3: Write `src/friction/labels.py`**

```python
"""Cross-system solve rate as the label — de-noising by consensus.

Any single system's verdict is ~30% noise: SWE-Bench+ (arXiv 2410.06992)
measured 32.7% solution leakage and 31% weak tests, and OpenAI found 59.4% of
o3's failures on Verified were test flaws, which is why they no longer recommend
the benchmark.

Consensus across ~40 systems fixes the two failure modes structurally rather
than by trusting a cleaner source:
  * a LEAKED instance is solved by nearly everyone -> solve rate ~1.0 -> dropped
  * a BROKEN-TEST instance is solved by nobody     -> solve rate ~0.0 -> dropped
What remains is the discriminating middle, which is exactly the population where
"is this hard?" is a meaningful question. This is what IRT does implicitly by
fitting a difficulty per item, and Agent Psychometrics excludes zero-solve tasks
for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstanceLabel:
    instance_id: str
    n_systems: int
    n_resolved: int
    solve_rate: float
    usable: bool
    reason: str


def label_instances(matrix: dict[str, dict[str, bool]],
                    min_systems: int = 10) -> dict[str, InstanceLabel]:
    out: dict[str, InstanceLabel] = {}
    for iid, responses in matrix.items():
        n = len(responses)
        k = sum(1 for v in responses.values() if v)
        rate = k / n if n else 0.0
        if n < min_systems:
            reason = f"too-few-systems ({n} < {min_systems})"
        elif k == n:
            reason = "all-solve (uninformative; likely leaked or trivial)"
        elif k == 0:
            reason = "no-solve (uninformative; likely broken tests)"
        else:
            reason = ""
        out[iid] = InstanceLabel(iid, n, k, rate, reason == "", reason)
    return out


def usable_only(labels: dict[str, InstanceLabel]) -> dict[str, InstanceLabel]:
    return {k: v for k, v in labels.items() if v.usable}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_labels.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Report the label distribution honestly**

Run the labeller over the real matrix and write `docs/labels.md`: total instances, dropped for too-few-systems / all-solve / no-solve with counts, and the surviving n with its solve-rate histogram. The all-solve and no-solve counts are themselves a measurement of benchmark contamination — report them beside SWE-Bench+'s 32.7%/31% for comparison.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(labels): consensus solve-rate target, contamination-dropped and disclosed"
```

---

### Task 8: Graph build at corpus scale

**Files:**
- Create: `substrate-friction/src/friction/build3.py`
- Create: `substrate-friction/scripts/build_corpus.py`
- Create: `substrate-friction/tests/test_build3.py`

**Interfaces:**
- Consumes: `friction.scip.*`, `friction.swebench`, `friction.build` (`_checkout`, `_restore`, `apply_test_patch`).
- Produces:
  - `friction.build3.build_one(instance, repo_root, out_dir) -> dict`
  - `friction.build3.load_graph(out_dir) -> networkx.DiGraph`

- [ ] **Step 1: Write the failing test**

`tests/test_build3.py`:
```python
import json

import networkx as nx

from friction import build3


def test_load_graph_reads_edges_into_a_digraph(tmp_path):
    (tmp_path / "edges.ndjson").write_text(
        json.dumps({"src": "m::a().", "dst": "m::b().", "weight": 2}) + "\n" +
        json.dumps({"src": "m::b().", "dst": "m::c().", "weight": 1}) + "\n")
    g = build3.load_graph(tmp_path)
    assert isinstance(g, nx.DiGraph)
    assert g.number_of_edges() == 2
    assert g["m::a()."]["m::b()."]["weight"] == 2


def test_load_graph_skips_external_edges(tmp_path):
    (tmp_path / "edges.ndjson").write_text(
        json.dumps({"src": "m::a().", "dst": "builtins::str#lower().",
                    "weight": 1, "external": True}) + "\n")
    assert build3.load_graph(tmp_path).number_of_edges() == 0


def test_load_graph_on_a_missing_file_returns_an_empty_graph(tmp_path):
    assert build3.load_graph(tmp_path).number_of_nodes() == 0


def test_load_graph_is_deterministic(tmp_path):
    (tmp_path / "edges.ndjson").write_text(
        json.dumps({"src": "b", "dst": "a", "weight": 1}) + "\n" +
        json.dumps({"src": "a", "dst": "c", "weight": 1}) + "\n")
    assert sorted(build3.load_graph(tmp_path).edges()) == \
           sorted(build3.load_graph(tmp_path).edges())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build3.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.build3'`

- [ ] **Step 3: Write `src/friction/build3.py`**

```python
"""Per-instance type-resolved graph build, at corpus scale.

scip-python indexes a repository in ~40s with NO dependency install (pyright
bundles typeshed), which is what makes thousands of per-instance builds
affordable. The graph is stored as NDJSON edges keyed by canonical symbol, so a
networkx DiGraph is a cheap load and every feature in Task 5 runs offline.

Unlike v2 this does NOT emit into engine id bands by default. The corpus study is
offline; the engine path (friction.reach) is exercised on the demo instances and
on the validation subset, which is where the graph-native claim is actually made.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx


def load_graph(out_dir: Path) -> nx.DiGraph:
    g = nx.DiGraph()
    path = Path(out_dir) / "edges.ndjson"
    if not path.exists():
        return g
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    for r in sorted(rows, key=lambda r: (r["src"], r["dst"])):
        if r.get("external"):
            continue
        g.add_edge(r["src"], r["dst"], weight=int(r.get("weight", 1)))
    return g


def build_one(instance, repo_root: Path, out_dir: Path) -> dict:
    from friction.build import _checkout, _restore, apply_test_patch
    from friction.scip.extract import extract_edges
    from friction.scip.index import index_repo
    from friction.scip.schema import load_index

    repo_root, out_dir = Path(repo_root), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _restore(repo_root)
    _checkout(repo_root, instance.base_commit)
    patched = apply_test_patch(repo_root, instance.test_patch)
    try:
        scip_out = out_dir / "index.scip"
        index_repo(repo_root, scip_out, name=instance.repo.split("/")[-1],
                   version=instance.base_commit[:12])
        edges, stats = extract_edges(load_index(scip_out))
        with (out_dir / "edges.ndjson").open("w", encoding="utf-8") as fh:
            for e in edges:
                fh.write(json.dumps({"src": e.src, "dst": e.dst,
                                     "weight": e.weight,
                                     "external": e.dst_external}) + "\n")
        scip_out.unlink(missing_ok=True)   # the .scip is 20MB+; the edges are not
    finally:
        _restore(repo_root)
    return {"instance_id": instance.instance_id, "base_commit": instance.base_commit,
            "test_patch_applied": patched, **stats}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_build3.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Write the resumable batch runner and launch it**

`scripts/build_corpus.py` — argparse `--limit`, `--repos`, `--resume`; loops usable instances, calls `build_one`, appends one JSON line per instance to `data/corpus/manifest.jsonl`, skipping ids already present. Delete `index.scip` after extraction (20 MB × thousands is not affordable). Launch under `nohup`, poll the log.

Report: instances built, median edges, wall clock per instance, total disk.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(build3): corpus-scale type-resolved graph builds"
```

---

### Task 9: Endpoint mapping

**Files:**
- Create: `substrate-friction/src/friction/endpoints.py`
- Create: `substrate-friction/tests/test_endpoints.py`

**Interfaces:**
- Produces:
  - `friction.endpoints.Endpoints` dataclass: `fix: list[str]`, `test: list[str]`, `fix_unmapped: int`, `test_unmapped: int`
  - `friction.endpoints.map_fix_sites(patch, defs) -> tuple[list[str], int]`
  - `friction.endpoints.map_test_targets(fail_to_pass, defs) -> tuple[list[str], int]`
  - `friction.endpoints.resolve(instance, scip_index) -> Endpoints`

- [ ] **Step 1: Write the failing test**

`tests/test_endpoints.py`:
```python
from friction import endpoints
from friction.scip.extract import Def

PATCH = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -10,3 +10,4 @@ class C:
     def f(self):
         pass
+        # changed
"""

DEFS = [
    Def("sym-f", "m.py", 8, 14, "m::C#f().", "function"),
    Def("sym-g", "m.py", 20, 30, "m::C#g().", "function"),
    Def("sym-t", "tests/test_m.py", 1, 9, "tests.test_m::T#test_a().", "function"),
]


def test_fix_sites_map_a_hunk_into_the_enclosing_definition():
    got, unmapped = endpoints.map_fix_sites(PATCH, DEFS)
    assert "m::C#f()." in got
    assert unmapped == 0


def test_fix_sites_prefer_the_innermost_definition():
    inner = Def("sym-i", "m.py", 11, 13, "m::C#f()/inner().", "function")
    got, _ = endpoints.map_fix_sites(PATCH, DEFS + [inner])
    assert "m::C#f()/inner()." in got


def test_a_hunk_in_an_unknown_file_is_counted_as_unmapped():
    got, unmapped = endpoints.map_fix_sites(PATCH.replace("m.py", "zz.py"), DEFS)
    assert got == []
    assert unmapped >= 1


def test_test_targets_match_a_django_style_identifier():
    got, unmapped = endpoints.map_test_targets(["test_a (tests.test_m.T)"], DEFS)
    assert got == ["tests.test_m::T#test_a()."]
    assert unmapped == 0


def test_test_targets_match_a_pytest_node_id():
    got, _ = endpoints.map_test_targets(["tests/test_m.py::T::test_a"], DEFS)
    assert got == ["tests.test_m::T#test_a()."]


def test_an_ambiguous_bare_name_is_not_guessed():
    twin = Def("s2", "other.py", 1, 5, "other::T#test_a().", "function")
    got, unmapped = endpoints.map_test_targets(["test_a"], DEFS + [twin])
    assert got == []
    assert unmapped == 1


def test_unmapped_counts_are_reported_not_silent():
    got, unmapped = endpoints.map_test_targets(["nope (a.b.C)"], DEFS)
    assert got == [] and unmapped == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_endpoints.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.endpoints'`

- [ ] **Step 3: Write `src/friction/endpoints.py`**

```python
"""Map an instance's gold patch and FAIL_TO_PASS tests onto graph nodes.

Both halves failed differently in earlier versions and both failures were
silent, so unmapped endpoints are COUNTED and returned rather than dropped:
  * fix sites: hunk post-image line ranges intersected against SCIP definition
    enclosing_ranges, innermost containment wins.
  * test targets: FAIL_TO_PASS identifiers come in two dialects — the Django
    runner's "method (dotted.module.Class)" and pytest's "path::Class::method".
    v1 handled only the second and mapped 0 of 50 django instances.

An ambiguous bare name resolves to nothing. A wrong endpoint silently poisons
every feature computed from it; a missing one is merely a smaller n.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from unidiff import PatchSet

_DJANGO = re.compile(r"^(?P<method>[\w]+)\s*\((?P<dotted>[\w.]+)\)\s*$")


@dataclass(frozen=True)
class Endpoints:
    fix: list[str]
    test: list[str]
    fix_unmapped: int
    test_unmapped: int


def _norm(path: str) -> str:
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def map_fix_sites(patch: str, defs) -> tuple[list[str], int]:
    by_path: dict[str, list] = {}
    for d in defs:
        by_path.setdefault(d.path, []).append(d)

    hits: list[str] = []
    unmapped = 0
    try:
        ps = PatchSet(patch)
    except Exception:  # noqa: BLE001 — a malformed diff maps to nothing
        return [], 1

    for pf in ps:
        path = _norm(pf.path)
        candidates = by_path.get(path)
        if candidates is None:
            unmapped += 1
            continue
        for hunk in pf:
            lines = [ln.target_line_no for ln in hunk
                     if ln.is_added and ln.target_line_no is not None]
            if not lines:
                lines = [ln.target_line_no for ln in hunk
                         if ln.target_line_no is not None]
            if not lines:
                continue
            lo, hi = min(lines) - 1, max(lines) - 1   # SCIP ranges are 0-based
            best = None
            for d in candidates:
                if d.start <= hi and lo <= d.end:
                    if best is None or (d.end - d.start) < (best.end - best.start):
                        best = d
            if best is None:
                unmapped += 1
            elif best.canonical not in hits:
                hits.append(best.canonical)
    return hits, unmapped


def _parse_identifier(raw: str) -> tuple[str | None, str]:
    raw = raw.strip()
    m = _DJANGO.match(raw)
    if m:
        return m.group("dotted"), m.group("method")
    if "::" in raw:
        parts = [p for p in raw.split("::") if p]
        method = parts[-1].split("[")[0]
        scope = [p for p in parts[:-1] if not p.endswith(".py")]
        head = parts[0]
        dotted = head[:-3].replace("/", ".") if head.endswith(".py") else ""
        if scope:
            dotted = f"{dotted}.{'.'.join(scope)}" if dotted else ".".join(scope)
        return (dotted or None), method
    return None, raw.split("[")[0]


def map_test_targets(fail_to_pass, defs) -> tuple[list[str], int]:
    hits: list[str] = []
    unmapped = 0
    for raw in fail_to_pass:
        dotted, method = _parse_identifier(raw)
        matches = []
        for d in defs:
            leaf = d.canonical.rsplit("#", 1)[-1].rstrip("().")
            if leaf != method:
                continue
            if dotted:
                flat = d.canonical.replace("::", ".").replace("#", ".")
                if not flat.startswith(dotted.split(".")[0]) and \
                        dotted.split(".")[-1] not in flat:
                    continue
            matches.append(d.canonical)
        unique = sorted(set(matches))
        if len(unique) == 1:
            if unique[0] not in hits:
                hits.append(unique[0])
        else:
            unmapped += 1
    return hits, unmapped


def resolve(instance, defs) -> Endpoints:
    fix, fu = map_fix_sites(instance.patch, defs)
    test, tu = map_test_targets(instance.fail_to_pass, defs)
    return Endpoints(fix, test, fu, tu)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_endpoints.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Report the real mapping rate and hand-verify three instances**

Run over the built corpus. Report the percentage of instances with ≥1 fix site AND ≥1 test target — this is the true usable n. Then print, for three instances, the mapped function names beside the gold patch hunk ranges and the FAIL_TO_PASS identifiers, so the mapping is checkable by eye rather than assumed.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(endpoints): both identifier dialects, unmapped counted not dropped"
```

---

### Task 10: The model — crossed mixed effects

**Files:**
- Create: `substrate-friction/src/friction/model.py`
- Create: `substrate-friction/tests/test_model.py`

**Interfaces:**
- Produces:
  - `friction.model.FitResult` dataclass: `params: dict[str, float]`, `loglike: float`, `n_obs: int`, `n_instances: int`, `n_systems: int`, `converged: bool`
  - `friction.model.long_form(features, matrix, labels) -> pandas.DataFrame`
  - `friction.model.fit_mixed(df, feature_cols) -> FitResult`
  - `friction.model.instance_difficulty(matrix) -> dict[str, float]`

- [ ] **Step 1: Write the failing test**

`tests/test_model.py`:
```python
import pandas as pd

from friction import model


def test_long_form_has_one_row_per_instance_system_cell():
    feats = {"i1": {"katz": 1.0}, "i2": {"katz": 2.0}}
    matrix = {"i1": {"a": True, "b": False}, "i2": {"a": False}}
    labels = {"i1": True, "i2": True}
    df = model.long_form(feats, matrix, labels)
    assert len(df) == 3
    assert set(df.columns) >= {"instance", "system", "resolved", "katz"}


def test_long_form_excludes_unusable_instances():
    feats = {"i1": {"katz": 1.0}, "i2": {"katz": 2.0}}
    matrix = {"i1": {"a": True}, "i2": {"a": False}}
    df = model.long_form(feats, matrix, {"i1": True, "i2": False})
    assert set(df["instance"]) == {"i1"}


def test_resolved_is_coded_one_for_success():
    feats = {"i1": {"katz": 1.0}}
    df = model.long_form(feats, {"i1": {"a": True, "b": False}}, {"i1": True})
    assert sorted(df["resolved"]) == [0, 1]


def test_instance_difficulty_is_one_minus_solve_rate():
    d = model.instance_difficulty({"i1": {"a": True, "b": False, "c": False}})
    assert abs(d["i1"] - (2 / 3)) < 1e-9


def test_fit_reports_the_grouping_counts():
    df = pd.DataFrame({
        "instance": [f"i{i//4}" for i in range(40)],
        "system": [f"s{i%4}" for i in range(40)],
        "resolved": [i % 3 == 0 for i in range(40)],
        "katz": [float(i % 7) for i in range(40)],
    })
    r = model.fit_mixed(df, ["katz"])
    assert r.n_obs == 40
    assert r.n_instances == 10
    assert r.n_systems == 4
    assert "katz" in r.params


def test_fit_on_a_degenerate_single_class_does_not_crash():
    df = pd.DataFrame({"instance": ["i1"] * 6, "system": [f"s{i}" for i in range(6)],
                       "resolved": [1] * 6, "katz": [1.0] * 6})
    r = model.fit_mixed(df, ["katz"])
    assert r.converged is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.model'`

- [ ] **Step 3: Write `src/friction/model.py`**

```python
"""Crossed mixed-effects logistic regression on the (instance, system) matrix.

Each instance is attempted by many systems, so the data are crossed repeated
measures. A pooled AUC over that structure silently rewards a model that learns
each SYSTEM's base rate — which is why a task-agnostic predictor scores ~0.718 on
SWE-bench Verified and why any headline AUC must be read against 0.787 (text
features) rather than chance.

    resolved_ij ~ graph_features_i + baselines_i + (1 | instance_i) + (1 | system_j)

The (1|system) term absorbs agent identity, so a feature coefficient estimates
task-difficulty signal net of who attempted it. statsmodels'
BinomialBayesMixedGLM fits crossed random effects variationally; R's lme4::glmer
is the field standard if a cross-check is wanted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FitResult:
    params: dict[str, float]
    loglike: float
    n_obs: int
    n_instances: int
    n_systems: int
    converged: bool


def long_form(features: dict[str, dict[str, float]],
              matrix: dict[str, dict[str, bool]],
              usable: dict[str, bool]) -> pd.DataFrame:
    rows = []
    for iid, responses in matrix.items():
        if not usable.get(iid):
            continue
        feats = features.get(iid)
        if feats is None:
            continue
        for system, resolved in responses.items():
            rows.append({"instance": iid, "system": system,
                         "resolved": int(bool(resolved)), **feats})
    return pd.DataFrame(rows)


def instance_difficulty(matrix: dict[str, dict[str, bool]]) -> dict[str, float]:
    """1 - solve rate. The empirical analogue of an IRT difficulty parameter."""
    out = {}
    for iid, responses in matrix.items():
        n = len(responses)
        out[iid] = 1.0 - (sum(1 for v in responses.values() if v) / n) if n else 0.0
    return out


def fit_mixed(df: pd.DataFrame, feature_cols: list[str]) -> FitResult:
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    n_inst = df["instance"].nunique()
    n_sys = df["system"].nunique()
    if df["resolved"].nunique() < 2:
        return FitResult({}, float("nan"), len(df), n_inst, n_sys, False)

    work = df.copy()
    for c in feature_cols:
        sd = work[c].std()
        work[c] = (work[c] - work[c].mean()) / sd if sd and sd > 0 else 0.0

    formula = "resolved ~ " + (" + ".join(feature_cols) if feature_cols else "1")
    vc = {"instance": "0 + C(instance)", "system": "0 + C(system)"}
    try:
        m = BinomialBayesMixedGLM.from_formula(formula, vc, work)
        res = m.fit_vb(verbose=False)
        params = {name: float(val) for name, val in
                  zip(res.model.exog_names, res.params[:len(res.model.exog_names)])}
        loglike = float(getattr(res, "logposterior", np.nan))
        converged = True
    except Exception:  # noqa: BLE001 — reported, never silently succeeded
        params, loglike, converged = {}, float("nan"), False
    return FitResult(params, loglike, len(df), n_inst, n_sys, converged)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(model): crossed mixed-effects logistic absorbing agent identity"
```

---

### Task 11: The tests that decide it

**Files:**
- Create: `substrate-friction/src/friction/tests_stat.py`
- Create: `substrate-friction/src/friction/harness3.py`
- Create: `substrate-friction/tests/test_tests_stat.py`
- Create (generated): `docs/evaluation.md`, `docs/power.md`, `docs/plots/v3.png`

**Interfaces:**
- Produces:
  - `friction.tests_stat.delong_test(y, score_a, score_b) -> tuple[float, float]` — (z, p) for correlated AUCs
  - `friction.tests_stat.lr_test(ll_reduced, ll_full, df) -> tuple[float, float]`
  - `friction.tests_stat.required_n(auc0, auc1, rho, alpha=0.05, power=0.8) -> int`
  - `friction.tests_stat.leave_one_repo_out(df, feature_cols) -> dict[str, float]`

- [ ] **Step 1: Write the failing test**

`tests/test_tests_stat.py`:
```python
import math

import numpy as np

from friction import tests_stat as T


def test_delong_on_identical_scores_gives_no_difference():
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.2, 0.8, 0.9])
    z, p = T.delong_test(y, s, s.copy())
    assert abs(z) < 1e-6
    assert p > 0.99


def test_delong_detects_a_clearly_better_predictor():
    y = np.array([0] * 30 + [1] * 30)
    good = np.concatenate([np.linspace(0, .4, 30), np.linspace(.6, 1, 30)])
    bad = np.random.RandomState(0).rand(60)
    z, p = T.delong_test(y, good, bad)
    assert z > 0
    assert p < 0.05


def test_lr_test_is_zero_when_the_models_fit_equally():
    stat, p = T.lr_test(-100.0, -100.0, 1)
    assert stat == 0.0
    assert p > 0.99


def test_lr_test_rejects_when_the_full_model_fits_much_better():
    stat, p = T.lr_test(-100.0, -90.0, 1)
    assert math.isclose(stat, 20.0)
    assert p < 0.001


def test_required_n_grows_as_the_effect_shrinks():
    big = T.required_n(0.78, 0.88, rho=0.5)
    small = T.required_n(0.78, 0.83, rho=0.5)
    assert small > big


def test_required_n_matches_the_published_ballpark():
    # +0.05 over 0.78 at rho=0.5 needs roughly 600 instances
    n = T.required_n(0.78, 0.83, rho=0.5)
    assert 300 < n < 1200


def test_higher_correlation_between_predictors_needs_fewer_instances():
    assert T.required_n(0.78, 0.83, rho=0.7) < T.required_n(0.78, 0.83, rho=0.3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tests_stat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.tests_stat'`

- [ ] **Step 3: Write `src/friction/tests_stat.py`**

```python
"""The hypothesis tests, and the power calculation that should have run first.

v2 reported a bootstrap CI of [-0.472, 0.435] at n=18 — an interval spanning
nearly the whole achievable range, which resolves nothing. The power arithmetic
below says detecting +0.05 AUC over a 0.78 baseline needs roughly 600 instances
at rho=0.5. Running it BEFORE the study is the difference between a result and a
shrug.

Two tests, because they answer different questions:
  * DeLong: are these two AUCs different, given they score the SAME instances and
    are therefore correlated? (DeLong et al., Biometrics 44(3):837, 1988)
  * Likelihood ratio: does the graph feature block add explanatory power to the
    mixed model, over and above the baselines?
"""

from __future__ import annotations

import math

import numpy as np
from scipy import stats


def _auc_and_variance(y, s):
    y = np.asarray(y).astype(int)
    s = np.asarray(s, dtype=float)
    pos, neg = s[y == 1], s[y == 0]
    m, n = len(pos), len(neg)
    if m == 0 or n == 0:
        return float("nan"), float("nan"), 0, 0
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    auc = (gt + 0.5 * eq) / (m * n)
    q1 = auc / (2 - auc)
    q2 = 2 * auc * auc / (1 + auc)
    var = (auc * (1 - auc) + (m - 1) * (q1 - auc ** 2) + (n - 1) * (q2 - auc ** 2)) / (m * n)
    return auc, max(var, 1e-12), m, n


def delong_test(y, score_a, score_b) -> tuple[float, float]:
    """z and p for two CORRELATED AUCs on the same samples."""
    a, va, _, _ = _auc_and_variance(y, score_a)
    b, vb, _, _ = _auc_and_variance(y, score_b)
    if math.isnan(a) or math.isnan(b):
        return float("nan"), float("nan")
    r = float(np.corrcoef(np.asarray(score_a, dtype=float),
                          np.asarray(score_b, dtype=float))[0, 1])
    if not math.isfinite(r):
        r = 0.0
    se = math.sqrt(max(va + vb - 2 * r * math.sqrt(va * vb), 1e-12))
    z = (a - b) / se
    return z, 2 * (1 - stats.norm.cdf(abs(z)))


def lr_test(ll_reduced: float, ll_full: float, df: int) -> tuple[float, float]:
    stat = max(2.0 * (ll_full - ll_reduced), 0.0)
    return stat, float(stats.chi2.sf(stat, df))


def required_n(auc0: float, auc1: float, rho: float,
               alpha: float = 0.05, power: float = 0.8) -> int:
    """Instances needed to detect auc1 - auc0, Hanley-McNeil variance, balanced."""
    def var(a, m):
        q1 = a / (2 - a)
        q2 = 2 * a * a / (1 + a)
        return (a * (1 - a) + (m - 1) * (q1 - a ** 2) + (m - 1) * (q2 - a ** 2)) / (m * m)

    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    delta = abs(auc1 - auc0)
    if delta <= 0:
        return 10 ** 9
    m = 10
    for _ in range(200):
        se = math.sqrt(max(var(auc0, m) + var(auc1, m) - 2 * rho *
                           math.sqrt(var(auc0, m) * var(auc1, m)), 1e-15))
        need = ((z_a + z_b) * se / delta) ** 2
        new_m = max(10, int(math.ceil(m * need)))
        if abs(new_m - m) <= 1:
            m = new_m
            break
        m = int((m + new_m) / 2) if new_m > m else max(10, new_m)
    return int(2 * m)


def leave_one_repo_out(df, feature_cols: list[str]) -> dict[str, float]:
    """AUC per held-out repo, so repo identity cannot be memorised."""
    from sklearn.linear_model import LogisticRegression

    out: dict[str, float] = {}
    df = df.copy()
    df["repo"] = df["instance"].str.split("__").str[0]
    for repo in sorted(df["repo"].unique()):
        train, test = df[df["repo"] != repo], df[df["repo"] == repo]
        if train["resolved"].nunique() < 2 or test["resolved"].nunique() < 2:
            continue
        m = LogisticRegression(max_iter=2000)
        m.fit(train[feature_cols].fillna(0.0), train["resolved"])
        p = m.predict_proba(test[feature_cols].fillna(0.0))[:, 1]
        auc, _, _, _ = _auc_and_variance(test["resolved"].values, p)
        out[repo] = float(auc)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tests_stat.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Write `harness3.py` and generate `docs/power.md` FIRST**

Before any result, write `docs/power.md`: `required_n` at ρ ∈ {0.3, 0.5, 0.7} for +0.03 / +0.05 / +0.10 over 0.78, beside the achieved n from Tasks 6–9. If the achieved n is below the requirement, the README states the study is underpowered for effects below X — computed, not guessed.

- [ ] **Step 6: Generate `docs/evaluation.md`**

Required content: the achieved n and how it was reached; the v3 feature AUCs; the baseline block (`patch_lines`, `patch_files`, `f2p_count`, `statement_chars`) on the same instances; the published rows **0.718 / 0.787 / 0.841** marked *published, not reproduced*; the DeLong test of the best v3 feature against the best baseline; the LRT of the full vs reduced mixed model; leave-one-repo-out AUCs; and the v1/v2 retraction. Every number regenerated by `uv run python -m friction.harness3`.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat(stats): DeLong, LRT, power analysis, leave-one-repo-out"
```

---

### Task 12: CLI

**Files:** modify `src/friction/cli.py`, `tests/test_cli.py`

- [ ] **Step 1: `friction check --issue <id>`** — prints the v3 feature breakdown with bars, the predicted difficulty, the recommendation, **the exact Cypher issued to the engine for the reachability profile, and the measured latency**. This is the criterion-2 evidence and must show the engine working.
- [ ] **Step 2: `friction explain --issue <id>`** — prints, per feature, the value beside the corpus percentile, so a number is interpretable without the paper.
- [ ] **Step 3: `friction eval` / `friction power` / `friction delta`** — print the generated docs.
- [ ] **Step 4: Tests** — every feature label appears; the Cypher and latency print; unknown subcommand returns non-zero; paths fall back to `data/shipped` when `data/corpus` is absent; an engine-unreachable instance prints a clean line, never a fabricated score.
- [ ] **Step 5:** Run for real on two instances and paste the output. Commit.

---

### Task 13: Visualisation

**Files:** modify `src/friction/viz.py`, `tests/test_viz.py`

- [ ] **Step 1: `docs/plots/frontier.png`** — the bidirectional frontier: forward ball from the fix sites, backward ball from the tests, their overlap highlighted. This is what the metric actually measures and it has never been drawn.
- [ ] **Step 2: `docs/plots/routes.png`** — a low-bottleneck instance beside a high-bottleneck one, with the min cut drawn. The visual difference between "one way through" and "many independent ways" is the demo.
- [ ] **Step 3: `docs/plots/power.png`** — required n vs detectable effect, with v2's n=18 and v3's achieved n marked. It makes the central methodological point in one image.
- [ ] **Step 4: Tests** — each writes a non-empty PNG; empty input yields an empty figure rather than raising. `python -m friction.viz` regenerates all three from committed caches. Commit.

---

### Task 14: Packaging

**Files:** `setup.sh`, `docker-compose.yml`, `data/shipped/`, `scripts/distil_shipped.py`

- [ ] **Step 1:** Ship the corpus feature table, labels, and the demo instances' graphs — **≤ 50 MB**, gzipped, with exactly what is omitted named in `data/shipped/README.md`. The full corpus will be gigabytes; do not ship it, and do not imply it is there.
- [ ] **Step 2:** `setup.sh` — clean clone to a working `friction check` with no manual steps: dirs, dev token, `chmod` for UID 10001, stack up, wait `/readyz`, `uv sync`, **install the package editable** (the console script is dead otherwise), probe, load the demo graphs, warm one query. No dependency on `just`.
- [ ] **Step 3:** Document the `CLOUD_PROVIDER=local` degradation ([#81](https://github.com/hydra-db/hydradb/issues/81)) in `docker-compose.yml` and note the shipped working set is deliberately small to stay clear of it.
- [ ] **Step 4:** Time it from a clean clone in a temp dir and report the real seconds. Commit.

---

### Task 15: README and video

**Files:** `README.md`, `docs/video-script.md`

- [ ] **Step 1: Lead with what is actually new.** The honest framing, in order: (a) we built the first *type-resolved* call graphs for SWE-bench instances and measured what the ecosystem's name-matched graphs cost — precision ceiling **0.746**, `list.extend` bound to a GIS class 139 times; (b) we replaced path enumeration, which is **#P-complete** and answered only 3 of 28 instances, with bounded-frontier metrics that run **inside** the engine's GraphBLAS kernel; (c) we tested the structural thesis at n≈X with consensus labels, and here is the answer.

- [ ] **Step 2: State the novelty precisely, with the near-miss.** Per-instance failure prediction is solved — cite arXiv 2604.00594 (**0.841**; text-only **0.787**; task-agnostic prior **0.718**). **GRADE** (arXiv 2606.22741) predicts agent failure from a graph of *the agent's own run* and shows dependency structure beats run size. Ours is the *static call graph of the target repository*, available **pre-hoc**. Say that difference plainly; it is the whole claim.

- [ ] **Step 3: "How HydraDB is used."** `MATCH (s)-[:CALLS*1..k]->(n) RETURN count(n)` lowers to `MatchReachable` → `ReachableVertices` → `reachable_count_in_hop_range_at` (`src/shard/query.rs:1008`) → the masked `GrB_mxv` BFS in `src/sparse_kernel/graphblas.rs`. Give the real Cypher and the real latency. Explain what breaks without it: enumerating the same structure is #P-complete and empirically times out at 30 s on 24 of 28 instances. Explain why a vector index cannot do it: the quantity is defined over *reachable sets and cuts*, which do not exist in an embedding space.

- [ ] **Step 4: Limitations, all of them.** Arm B under-reports on untyped receivers (precision is a **ceiling**, and `cursor(54)` is the counter-example where name matching was right); dynamic dispatch invisible; Python only; `maxLen 6`; Katz counts *walks* not simple paths (monotone, reportable bias — with the oracle correlation from Task 5 Step 5 quantifying it); consensus labels inherit whatever all 40 systems share; achieved n and its power from `docs/power.md`.

- [ ] **Step 5: Upstream contributions** — [#81](https://github.com/hydra-db/hydradb/issues/81) and [#82](https://github.com/hydra-db/hydradb/pull/82), a few lines.

- [ ] **Step 6: Video, ≤ 3:00** — problem → project → demo → HydraDB. Money shot at 0:45: `friction check` on two instances, the frontier figure, and the reveal. At 1:50: the Cypher, the millisecond timing, and the line *"the previous version asked this engine to enumerate paths; that problem is #P-complete and it timed out on 24 of 28 tickets. This asks for the frontier instead, and it answers in milliseconds."* Per-section word counts at ~150 wpm; tag every `[STILL]` and `[B-ROLL]`.

- [ ] **Step 7: Pre-submission checklist** — public repo; OSI LICENSE; no participant commit before 2026-08-12; clean-clone `setup.sh` on a second machine; links checked in an incognito window; video under 3:00; form `forms.gle/GrMYKxLj9zPQcqqc8`. Commit.

---

## Self-Review

**1. Spec coverage.** Original spec → v3 mapping. Part 2 (data) → Tasks 6–8, scaled from 50 to ~2,000 instances. Part 3 (model) → Task 8 + `friction.scip.*` (reused). Part 4 (ingest) → Task 8; the `UNWIND` loader is reused for the demo path only. Part 5 (the six friction components) → **Task 5, reformulated**: each component keeps its intuition but gains a computable definition, because the originals were defined over an enumeration that is #P-complete. Part 6 (go/no-go) → **Task 5 Step 6**, moved after the metric is computable — v2's gate fired on an artifact. Part 7 (product) → Tasks 12–15. Part 9 (Common Cause) → **dropped, with cause**: attempted in v2, its top result was `loader_tags.py::super` at 21/36 instances, the same name-collision artifact, so it inherits the substrate defect. Part 10 (failure modes) → Global Constraints + the Task 1 validation and Task 5 gate. Part 11 (done) → Task 15 Step 7. Part 12 (anti-goals) → Global Constraints.

**Deliberate departures, each with a reason:** (a) `algo.MSpaths` is no longer the primary engine call — it is intractable at this graph's density and the spec's "crown jewel" framing predates that measurement; the reachability kernel is *more* graph-native, being the raw GraphBLAS BFS. (b) The thesis is demoted from headline to hypothesis-under-test, because per-instance prediction is solved at 0.841. (c) n rises from 50 to ~2,000 because the power arithmetic says 50 cannot resolve the effect. (d) Labels become cross-system consensus rather than 2–3 published systems, because single-system verdicts are ~30% noise.

**2. Placeholder scan.** Tasks 1–11 carry complete code. Tasks 12–15 give exact files, commands, required content and acceptance criteria but not full bodies, because they modify existing v2 modules the implementer will read first. The one data-dependent residue is "n≈X" in Task 15 Step 1, which Task 11 measures; Task 11 Step 5 requires `docs/power.md` to be written *before* results so X is interpretable when it lands.

**3. Type consistency.** `ReachProfile(hops, sizes, millis, answered)` is used identically in `reach` and `features`. `PathCounts(by_length, total, exact, largest_scc)` only in `oracle`. `KatzResult(score, beta, spectral_radius, converged, iterations)` in `katz` and consumed as `.score` in `features`. `RouteCount(edge_disjoint, node_disjoint, min_cut_size)` in `routes`, consumed as `.edge_disjoint`/`.node_disjoint` in `features`. `Features`/`FEATURE_NAMES` shared by `features`, `model`, `tests_stat`, `cli`, `viz`. `Verdict(instance_id, system, split, resolved)` in `corpus` feeds `response_matrix`, whose `dict[str, dict[str, bool]]` is exactly what `labels.label_instances` and `model.long_form` consume. `Def(symbol, path, start, end, canonical, kind)` is the existing v2 dataclass reused unchanged by `endpoints`.

---

## What the research changed

- **The keystone.** `MATCH (s)-[:R*1..k]->(n) RETURN count(n)` lowers to `matrix_reachable` → masked `GrB_mxv` BFS (`src/shard/query.rs:1008`, `src/sparse_kernel/graphblas.rs`): **O(m) per hop bounded by the visited set**, not by walk volume. The engine exposes exactly three `algo.*` procedures, all path-enumerating (`src/query/path_procedure.rs:13-18`); repo-wide grep for pagerank/centrality/triangle/maxflow = **0 hits**. The hard limits are `max_query_intermediate_rows` = 250,000 and `max_query_runtime_ms` = 30,000 (`src/core/config.rs:48-51`).
- **v2 was not slow, it was intractable.** Exact bounded simple-path counting is **#P-complete** (Valiant 1979) and **#W[1]-hard** in the length (Flum–Grohe 2004). Walk→path correction has closed forms only to k≈4 (Jokić–Van Mieghem, arXiv:2209.08840); k=6 needs ~32,768 dense terms.
- **The replacements are principled, not hacks.** Katz (Katz 1953; Estrada–Higham, *SIAM Review* 52(4):696) counts damped walks exactly via one sparse solve. Max-flow = edge-disjoint routes by **Menger's theorem**, exact in O(E√V) (Dinic). Colour-coding (Alon–Yuster–Zwick, JACM 42(4):844) is the FPT fallback if approximate path counts are ever needed.
- **The corpus exists.** `SWE-bench/experiments` holds ~99 Verified / ~79 Lite submissions (arXiv 2506.17208) over ~2,294 Python instances — 20,000+ response cells. Plus SWE-rebench's 860 decontaminated instances (arXiv 2505.20411) as a held-out benchmark.
- **Power, computed.** +0.05 AUC over 0.78 needs **~610 instances at ρ=0.5** (~370 at ρ=0.7, ~1,000 at ρ→0). v2's n=18 was ~34× short.
- **Labels de-noise by consensus.** Dropping 0%- and 100%-solve instances removes leaked and broken-test cases structurally — the failure modes SWE-Bench+ measured at 32.7%/31% (arXiv 2410.06992) and OpenAI at 59.4%.
- **The niche is open and de-risked.** **GRADE** (arXiv 2606.22741) predicts agent failure from the *agent's run graph* and shows dependency structure beats run size — establishing the mechanism while leaving the *static repository call graph* unclaimed. AgentTether (2607.06273) is also run-graph; SGAgent (2602.23647) and codebadger (2603.24837) use code graphs to *perform* repair, not predict difficulty.

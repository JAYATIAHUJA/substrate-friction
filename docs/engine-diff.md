# The disagreement set, computed in the engine

`friction diff --live` makes HydraDB itself compute this project's headline
measurement — the arm A vs arm B anti-join behind `docs/graph-delta.md` —
instead of an offline script. Run 2026-08-18 against the digest-pinned engine;
the numbers below are that run's output, and the command **refuses to print**
any result that does not exactly reproduce the committed offline join.

## Method: edge reification

The engine's dialect has no anti-join, no `count(DISTINCT …)`, and rejects
incoming and variable-length-unanchored patterns. The measurement is expressed
in forms this build verifiably parses:

1. Every compared **edge becomes a node**: `(:AEdge {id})` in band
   `800000000000`, `(:BEdge {id})` in `810000000000`.
2. Every distinct `(src, dst)` edge identity becomes one `(:Sig {id})` node in
   band `820000000000`, id = sha256 of the signature — deterministic keying at
   ingest, exactly like any property.
3. Structure: `(:AEdge)-[:HAS_SIG]->(:Sig)` and `(:Sig)-[:SIG_OF_B]->(:BEdge)`
   (the second stored outward because the engine rejects incoming patterns).
4. The anti-join is then, per arm-A edge, a **2-hop bounded outward
   traversal**:

```cypher
MATCH (a {id: 800000000000})-[:HAS_SIG]->(s)-[:SIG_OF_B]->(b) RETURN count(*) AS n
```

`n > 0` = confirmed by arm B; `n = 0` = unconfirmed. "Name-matched edges with
no type-resolved confirmation" is computed by the graph engine as graph
structure.

## The run

| | |
|---|---|
| arm-A edge-nodes reified | 5,873 |
| arm-B edge-nodes reified | 58,006 |
| Sig nodes | 59,498 |
| load time (batched MERGE/CREATE, 500/stmt) | 11.4 s |
| anti-join queries | 5,873 |
| anti-join total / per edge | 11.8 s / **2.0 ms** |
| **CONFIRMED** (engine) | **4,381** |
| **UNCONFIRMED** (engine) | **1,492** |
| parity with `docs/graph-delta.md` (4,381 / 1,492) | **EXACT — enforced by exception, not observed** |

## What this establishes

- The headline measurement is **engine-resident**: a judge can wipe the store,
  run `friction diff --live`, and watch HydraDB reproduce the number that the
  whole project stands on.
- The same discipline as `friction gate --instance --live`: every live path
  must agree exactly with its offline counterpart or it refuses to answer.

## Engine findings this run adds to the record

- Fixed-length multi-hop outward patterns (`-[:R]->()-[:S]->()`) parse and
  answer in ~2 ms at this scale.
- The reified load (123k nodes, ~76k edges) went through the verified loader
  forms without tripping the issue-#81 degradation on a fresh store.
- Incoming variable-length patterns remain rejected ("variable-length MATCH
  requires a fixed source id"), which is why `SIG_OF_B` is materialised
  outward — the same workaround as the gate's `CALLED_BY`.

Reproduce (regeneration machine — needs the local scip index):

```bash
docker compose down -v && rm -rf hydradb-data && mkdir -p hydradb-data/graph
docker compose up -d && sleep 12
uv run friction diff --live
```

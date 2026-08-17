# The certified graph: edges with receipts

`data/shipped/consensus.json` (emitted by `scripts/build_consensus.py`, which
refuses to run unless the arm join reproduces `docs/graph-delta.md` exactly)
is the product end-state in miniature: every compared call edge of the pinned
django commit, labelled with how much to believe it.

| Trust | Edges | Meaning |
|---|---|---|
| `confirmed` | 4,381 | both extraction arms agree |
| `name_only` | 1,492 | name-matched only, unconfirmed by type resolution (collision classes in `docs/edge-taxonomy.md`) |
| `b_only` (counted, not enumerated) | 58,006-space recall gap | type-resolved edges name matching misses entirely |

Agents consume it over MCP:

```
graph_query(symbols=["get_combinator_sql"], trust="any")
```

Every response carries the source commit, the engine image digest, the trust
census, and per-edge arm provenance. The difference from a raw repo map is the
point of the whole project: an agent reading this graph knows exactly which
edges are load-bearing and which are name-collision guesses — a graph with
receipts instead of a graph with confidence.

Scope, disclosed: this ships the **cached** consensus for the pinned commit
(the abort-clause variant of the full in-engine consensus server, which is in
`docs/future-work.md`). The derivation is committed, reproduction-gated, and
the same join the engine itself reproduces live in `docs/engine-diff.md`.

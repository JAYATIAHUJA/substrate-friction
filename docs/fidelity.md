# Path fidelity vs a networkx reference — and a substrate blocker

Same edge set, same `maxLen`, same relationship types, `relDirection=both`
(matched by an undirected reference). Any shortfall is the engine's traversal or
a result budget, not a different question.

## Result: engine recall = 0.000

| Quantity | Value |
|---|---|
| Instances compared | 20 |
| Paths returned by the engine | **0** |
| Paths found by the reference | **42,200** |
| Recall (fraction of reference paths the engine returned) | **0.000** |
| Instances missing ≥1 reference path | 18 (the other 2 are genuinely disconnected: reference also found 0) |

The engine returned **zero** paths not because the paths do not exist — the
reference proves 32 to 4,677 simple paths per instance exist at `maxLen=6` — but
because **`algo.MSpaths` exceeds the engine's hard 29999 ms query timeout on
every full-django graph** and is terminated before emitting any row. This is
not the truncation the guard was built to catch (over-return masking a
shortfall); it is total non-completion.

Verified on all 43 usable instances (path query attempted per instance): 43/43
terminate with `Neo.ClientError.Transaction.Terminated … exceeded query timeout
after 29999 ms`. Endpoint count does not matter — a 1-fix-site × 1-test-target
instance times out identically to a 15×22 one.

## maxLen is the driver, and the signal lives where the engine dies

Single instance `django__django-10880` (1 fix site, 1 test target, 122,781 edges):

| maxLen | engine | reference paths |
|---|---|---|
| 2 | 0.5 s, 0 paths | 0 |
| 3 | 24.5 s, 0 paths | 0 |
| 4 | **timeout** | 1 |
| 5 | **timeout** | 469 (at 6) |
| 6 (metric default) | **timeout** | 469 |

The frontier of an undirected depth-6 traversal over ~120k edges explodes. The
only depths the engine can complete (2–3) contain essentially no fix→test paths,
and every depth that contains paths (4–6) times out. There is no `maxLen` at
which the engine both completes and returns non-trivial paths.

## The `pathCount` escalation does not rescue it

The guard's rule is: if recall < 0.9, raise `HYDRA_PATH_COUNT` and re-run.
Done, and it does not help — because `pathCount` bounds *output*, and the query
dies during *traversal* before producing output:

| Instance | pathCount=20 | pathCount=50 | pathCount=100 |
|---|---|---|---|
| django__django-11095 | timeout, 0 paths | timeout, 0 paths | timeout, 0 paths |
| django__django-11133 | timeout, 0 paths | timeout, 0 paths | timeout, 0 paths |

Raising the output budget can only add work to a query that never reaches the
output stage. Recall stays 0.000 before and after.

## Consequence for the evaluation

Because engine recall is 0, no friction score can be computed from the engine
for any instance. The AUC in `docs/evaluation.md` is therefore computed from the
**networkx reference enumeration** — the exact bounded path set the metric is
defined over — so the *scientific* question ("does friction predict failure?")
still gets a real, if near-null, answer. The *substrate* question ("can HydraDB
compute it?") is answered here, and the answer is no at the pinned parameters.

# Fix-site <-> test-target connectivity

Measured statically over each instance's `edges.ndjson` with a bounded BFS (networkx, not the engine — this is a property of the built graph). An instance is counted only when its arm carries both a non-empty fix-site set and a non-empty test-target set.

- **arm B** (type-resolved via `scip-python`): 44 instances with both endpoints.
- **arm A** (name-matched): 30 instances with both endpoints.

## Direction table (arm B, bounded at 6 hops)

| Direction | Connected | Note |
|---|---|---|
| **fix -> test** (directed) | **0/44 (0%)** | Backwards. Code does not call tests. |
| **test -> fix** (directed) | **24/44 (55%)** | The natural direction: tests call code. |
| **undirected** (`relDirection: 'both'`) | **43/44 (98%)** | Weaker semantics, near-total coverage. |

Undirected at 10 hops: 43/44 (98%).

## arm A (name-matched)

| Direction | Connected |
|---|---|
| fix -> test (directed) | 0/30 (0%) |
| test -> fix (directed) | 15/30 (50%) |
| undirected @6 | 27/30 (90%) |
| undirected @10 | 27/30 (90%) |

## What these numbers mean

**fix -> test is 0/44 (0%) because code does not call tests.** The original spec's `sourceValues: $fixSiteIds -> targetValues: $testTargetIds` runs the relation the wrong way down the call graph. Production code has no edge to the test that guards it; the test has an edge to the code. So the directed measure that carries signal is **test -> fix**.

**The jump from directed test -> fix (24/44 (55%)) to undirected (43/44 (98%)) is the fixture closure.** The missing edges are the pytest fixture / `setUp` / `parametrize` / framework-dispatch machinery: a test reaches the code it exercises through dispatch a static call graph never records. Dropping direction recovers those instances, but it recovers them by measuring a weaker relation.

**Undirected reachability means "shares a neighbourhood", NOT "the test exercises this code".** Two nodes are undirected-connected whenever any chain of calls in either direction links them; that is a symmetric, much looser property than "this test runs this code". Report the two measures separately and never present the undirected number as evidence that a test covers a fix.

**Consequence for v1/v2.** Every v1/v2 friction number was computed with `relDirection: 'both'` — i.e. on the undirected relation. Those numbers measured the weaker "shares a neighbourhood" property, not directed test -> fix coverage. The clean directed semantic is **test -> fix at 24/44 (55%)**; the undirected 43/44 (98%) is a different, broader claim.


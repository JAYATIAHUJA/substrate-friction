# Path fidelity vs a networkx reference

Two checks, both over the same maxLen and relationship types the engine used.

## a. Engine vs reference on the SAME subgraph edge set

This isolates the engine's `pathCount = 20` result cap: same graph, same question.

- Answered instances with a fully-enumerable reference: **22** (1 excluded — reference enumeration hit its cap)
- Paths returned by the engine: **1021**
- Paths found by the reference: **38720**
- Overlap recall (reference paths the engine returned): **0.0264**
- Validity precision (engine paths that are real reference paths): **1.0**
- Largest single shortfall: `django__django-11740`

Recall is overlap-based, bounded in [0, 1]; an engine that over-returns cannot inflate it. Precision 1.0 with recall far below 0.9 means the engine returns a correct but tiny subset of the true paths. Because the friction metric is built from path multiplicity, any correlation the engine result shows is truncation-dominated and must not be believed — this is the guard firing, exactly as designed.

## b. Engine-on-subgraph vs reference on the FULL repo graph

This quantifies what the subgraph node budget costs. The subgraphs are budget-limited BFS balls: **pct_untruncated = 0%** (0/50 completed all 6 hops).

- Endpoint-bearing instances reachable within 6 hops in the FULL graph: **36**
- Of those, engine returned a path (cohort): **16** → connectivity recall **0.4444**
- Restricted to engine-answered instances: **16/16** → connectivity recall **1.0**

When the engine query finishes, the budgeted subgraph preserved the short fix→test connections (answered connectivity recall is high). The truncation cost lands as the ~half of reachable instances the engine cannot answer at all (timeout/OOM), which drops cohort connectivity recall well below 1.0.

# Path fidelity vs a networkx reference

Same edge set, same `maxLen`, same relationship types. Any shortfall is
the engine's traversal or a result budget, not a different question.

- Instances compared: **43**
- Paths returned by the engine: **0**
- Paths found by the reference: **1090**
- Recall (fraction of reference paths the engine returned): **0.0**
- Instances missing at least one reference path: **18**
- Largest single shortfall: `django__django-11276`

Recall is measured by overlap: for each instance the engine's paths are
intersected with the reference's paths. An engine that over-returns paths
cannot inflate this number above 1.0, and returning the right *count* of
wrong paths scores zero — so the `< 0.9` rule below cannot be defeated by
over-return, only satisfied by actually returning the reference paths.

The reference is undirected, matching an engine run with `relDirection=BOTH`,
so any shortfall is truncation, not a direction mismatch.

Why this matters: F1 (path multiplicity) and F3 (intermediate spread) are
counts of returned paths. Truncation does not add symmetric noise — it
biases high-friction instances downward, which is the direction that would
suppress the very signal this project tests for. If recall is below ~0.9,
raise `pathCount` and re-run before believing any correlation result.

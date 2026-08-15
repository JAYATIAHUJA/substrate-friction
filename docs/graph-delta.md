# What name matching costs

Arm A is a name-matched call graph, built the way the widely-used
repo-graph tools build one. Arm B is type-resolved via scip-python
(pyright). Same repository, same commit, same extraction of definitions.

| Measure | Value |
|---|---|
| Arm A edges confirmed by arm B | **4381** |
| Arm A edges arm B does not have | **1492** |
| Arm B edges arm A missed | **8064** |
| Arm A precision (ceiling) | **0.746** |
| Arm A recall of arm B | **0.352** |
| Jaccard | 0.3143 |

## Where arm A's unconfirmed edges point

| Target name | Unconfirmed edges |
|---|---|
| `extend` | 139 |
| `lower` | 125 |
| `cursor` | 54 |
| `import_module` | 33 |
| `search` | 31 |
| `split_contents` | 29 |
| `fetchall` | 28 |
| `time` | 28 |
| `insert` | 24 |
| `compile_filter` | 23 |
| `wraps` | 22 |
| `db_manager` | 22 |
| `next` | 21 |
| `max` | 20 |
| `min` | 16 |
| `geodetic` | 15 |
| `order_by` | 14 |
| `get_compiler` | 14 |
| `quote` | 13 |
| `reload_model` | 13 |

## How to read precision

Arm A precision is a **ceiling**, not a point estimate. pyright emits no
occurrence when a receiver's type is unknown, so arm B under-reports
rather than inventing edges. An arm-A edge missing from arm B is either a
genuine false positive or a case pyright declined to resolve. The direction
of the bias is known and stated; the exact split is not claimed.

- repo: django
- commit: b9cf764be62e77b4777b3a75ec256f6209a57671
- arm_a_edges_total: 18774
- arm_a_edges_compared (django-sourced, mapped): 5873
- arm_a_edges_excluded_out_of_scope (test/docs-sourced): 12901
- arm_a_nodes_failed_to_map: 0
- arm_b_internal_edges: 12445
- arm_b_edges_failed_to_map: 0
- identity_join: arm A tree-sitter qualnames and arm B SCIP canonical forms were mapped into one shared `scope::leaf` space; scip-python rooted module names at the constant prefix 'data.repos.django.', discovered from doc paths and stripped
- scope_note: scip-python was run --target-only django, so arm B contains only django-package definitions; arm A was restricted to django-sourced edges so both arms share the same universe of possible callers. Precision is unchanged at 0.746 (src-scoped) vs 0.756 (both-endpoints-scoped).
- precision_reading: CEILING: pyright emits no occurrence for untyped receivers, so arm B under-reports; true precision is <= this value.

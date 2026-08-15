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
| `db_manager` | 22 |
| `wraps` | 22 |
| `next` | 21 |
| `max` | 20 |
| `min` | 16 |
| `geodetic` | 15 |
| `get_compiler` | 14 |
| `order_by` | 14 |
| `quote` | 13 |
| `delete_first_token` | 13 |

## How to read precision

Arm A precision is a **ceiling**, not a point estimate. pyright emits no
occurrence when a receiver's type is unknown, so arm B under-reports
rather than inventing edges. An arm-A edge missing from arm B is either a
genuine false positive or a case pyright declined to resolve. The direction
of the bias is known and stated; the exact split is not claimed.

## Provenance and the 229-edge discrepancy

Two earlier figures exist for this same comparison: **0.746** (the build-session scratchpad) and **0.707** (an adversarial reviewer's independent reconstruction). Both reproduced the compared-edge count and the offender table exactly, but their intersections differed by **229 edges** (both=4381 vs 4152).

The cause is the package-`__init__` collapse in the identity join. A symbol defined in `pkg/__init__.py` is written `pkg.__init__.Symbol` by tree-sitter (arm A keeps the file stem as a module segment) but `pkg.Symbol` by scip-python (arm B folds a package's `__init__` into the package module). The reviewer's reconstruction did not apply that collapse to the arm-A side, so 229 edges with an endpoint in a package `__init__.py` — e.g. `django.conf.__init__.Settings.__init__` vs `django.conf.Settings.__init__` — failed to join and dropped from the intersection into `only_a`. The committed `friction.identity` applies the collapse symmetrically to both arms (it is a no-op on arm B, which never emits the segment), which is the correct Python-module semantics: `pkg/__init__.py` *is* the `pkg` module. The committed number below is the pinned result.

## Counter-example: the ceiling is honest in both directions

A block of **54** unconfirmed arm-A edges points at `django.db.backends.base.base.BaseDatabaseWrapper::cursor`. This is not the largest offender family — `list.extend` name collisions are — and that is the point: here the edges are not name-match noise but real calls to `connection.cursor()` where the receiver's type is resolved at runtime, so pyright emits no occurrence and arm B under-reports. Here arm A was **right** and the type-resolved reference is the one that is incomplete. This is exactly why arm A precision is reported as a ceiling and not a point estimate: an arm-A edge missing from arm B can be a genuine false positive *or* a case pyright declined to resolve, and this target is a clear instance of the latter.

- repo: django
- commit: b9cf764be62e77b4777b3a75ec256f6209a57671
- arm_a_edges_total: 18774
- arm_a_edges_compared (source in scope, mapped): 5873
- arm_a_edges_excluded_out_of_scope (test/docs-sourced): 12901
- arm_a_nodes_failed_to_map: 0
- arm_b_internal_edges: 12445
- arm_b_edges_compared (mapped): 12445
- arm_b_edges_failed_to_map: 0
- identity_join: arm A tree-sitter qualnames and arm B SCIP canonical forms mapped into one shared `scope::leaf` space via friction.identity; scip-python module prefix 'data.repos.django.' discovered from document paths and stripped; package-__init__ modules collapsed symmetrically (the 229-edge fix, see below)
- scope_note: scip-python was run --target-only django, so arm B contains only django-package definitions; arm A was restricted to django-sourced edges so both arms share one universe of callers.
- precision_reading: CEILING: pyright emits no occurrence for untyped receivers, so arm B under-reports and never invents an edge; an arm-A edge missing from arm B may still be a real call. Therefore true precision is >= this value, never <= it. See the cursor(54) counter-example, where arm A was right and arm B was incomplete.
- reproduce: uv run python scripts/graph_delta.py --repo data/repos/django --out docs/graph-delta.md

# Dynamic COVERS edges vs the connectivity gate

`friction.trace` runs each instance's own `FAIL_TO_PASS` test modules under `sys.settrace` in a uv-provisioned interpreter matching that django version, at the instance's `base_commit` with its `test_patch` applied, and records **executed** `Test -> Function` call edges. `friction.covers3` folds those edges into the type-resolved arm B graph and re-measures the clean directed signal, `test -> fix`.

## Before / after (directed test -> fix, bounded at 6 hops)

| Corpus | test -> fix |
|---|---|
| Committed static baseline (all 44 arm B instances) | **24/44 (55%)** |
| Traced subset, static only (44 instances) | 24/44 (55%) |
| Traced subset, **with COVERS (strict SCIP identity)** | **24/44 (55%)** |
| Traced subset, with COVERS (lax module+name, sensitivity) | 28/44 (64%) |

Delta from folding COVERS in: **+0** instances (strict), **+4** (lax). Instances that flipped disconnected -> connected: strict none, lax ['django__django-11265', 'django__django-11790', 'django__django-11880', 'django__django-12039'].

## COVERS mapping success rate — read this before the table above

COVERS edges are keyed by `path/to/file.py::co_name`; arm B nodes are SCIP `<module>::<Class>#<member>` symbols. Both are mapped into one identity space with `friction.identity`'s normalizers. The join is honest but lossy in one specific way: Python's `co_name` is the **bare method name with no class**, so a module-level function rejoins its symbol exactly but a class *method* cannot.

| Metric | Strict SCIP identity | Lax (module, name) |
|---|---|---|
| COVERS edges with BOTH endpoints mapped | 69/23043 (0%) | 14319/23043 (62%) |
| COVERS endpoints mapped | 5246/46086 (11%) | 37053/46086 (80%) |
| dynamic edges folded into arm B graphs | 35 | 39242 |

**An unmapped COVERS edge is not a connectivity improvement.** The low edge-level mapping rate is a direct consequence of tracer granularity (`co_name`), not of the tests failing to exercise the code — the raw per-instance traces show the fix module is executed in most cases (see the fix-site coverage column in the run log).

## Verdict

**Strict SCIP-identity fold -> RED <60%: test->fix 24/44 (55%) -> 24/44 (55%) (delta +0). Only 69/23043 (0%) of COVERS edges rejoin the class-qualified SCIP symbols the type-resolved graph is built from, because the tracer records co_name (the bare method, no class), so almost nothing folds in and connectivity is unchanged. Lax (module,name) sensitivity fold -> AMBER 60-80%: 24/44 (55%) -> 28/44 (64%) (delta +4; 4 instances flip). CONCLUSION: the executed Test->Function edges DO carry test->fix signal, but it is recoverable only under a class-agnostic identity relaxation the pipeline does not use; in the graph's own identity space COVERS is NOT the blocker. The actionable lever is a class-qualified tracer (co_qualname), which would let the strict fold capture what the lax fold approximates. Corpus expansion (Task 4) is independent either way.**

Directed `test -> fix` moved from 24/44 (55%) to 24/44 (55%) on the traced subset once COVERS was folded in. Instances that flipped from disconnected to connected: none.

## Per-instance detail

| instance | static test->fix | +COVERS | dyn edges | edge map rate |
|---|---|---|---|---|
| django__django-10097 | False | False | 5 | 11/5362 (0%) |
| django__django-10554 | True | True | 1 | 2/421 (0%) |
| django__django-10880 | False | False | 0 | 0/476 (0%) |
| django__django-10973 | True | True | 0 | 0/9 (0%) |
| django__django-11066 | False | False | 0 | 0/86 (0%) |
| django__django-11087 | True | True | 2 | 3/316 (1%) |
| django__django-11095 | True | True | 0 | 0/187 (0%) |
| django__django-11099 | True | True | 0 | 0/133 (0%) |
| django__django-11119 | True | True | 0 | 0/61 (0%) |
| django__django-11133 | True | True | 0 | 0/220 (0%) |
| django__django-11138 | False | False | 4 | 4/387 (1%) |
| django__django-11149 | False | False | 0 | 0/447 (0%) |
| django__django-11163 | True | True | 1 | 1/1060 (0%) |
| django__django-11179 | True | True | 2 | 3/302 (1%) |
| django__django-11206 | True | True | 0 | 0/16 (0%) |
| django__django-11211 | False | False | 0 | 0/803 (0%) |
| django__django-11239 | True | True | 0 | 0/11 (0%) |
| django__django-11265 | False | False | 1 | 1/297 (0%) |
| django__django-11276 | True | True | 8 | 29/3035 (1%) |
| django__django-11292 | False | False | 1 | 1/156 (1%) |
| django__django-11299 | True | True | 0 | 0/317 (0%) |
| django__django-11333 | True | True | 0 | 0/10 (0%) |
| django__django-11400 | True | True | 0 | 0/529 (0%) |
| django__django-11433 | False | False | 1 | 1/1067 (0%) |
| django__django-11490 | False | False | 1 | 2/414 (0%) |
| django__django-11532 | False | False | 0 | 0/329 (0%) |
| django__django-11551 | False | False | 0 | 0/295 (0%) |
| django__django-11555 | False | False | 0 | 0/193 (0%) |
| django__django-11728 | True | True | 0 | 0/36 (0%) |
| django__django-11734 | False | False | 3 | 3/2010 (0%) |
| django__django-11740 | True | True | 0 | 0/590 (0%) |
| django__django-11749 | True | True | 1 | 1/170 (1%) |
| django__django-11790 | False | False | 0 | 0/450 (0%) |
| django__django-11815 | False | False | 0 | 0/213 (0%) |
| django__django-11820 | True | True | 0 | 1/357 (0%) |
| django__django-11848 | True | True | 0 | 0/81 (0%) |
| django__django-11880 | False | False | 0 | 0/787 (0%) |
| django__django-11885 | True | True | 2 | 3/339 (1%) |
| django__django-11951 | False | False | 2 | 2/135 (1%) |
| django__django-11964 | True | True | 0 | 0/79 (0%) |
| django__django-11999 | True | True | 0 | 0/167 (0%) |
| django__django-12039 | False | False | 0 | 1/132 (1%) |
| django__django-12050 | True | True | 0 | 0/332 (0%) |
| django__django-12125 | False | False | 0 | 0/226 (0%) |


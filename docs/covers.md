# Dynamic COVERS edges vs the connectivity gate

`friction.trace` runs each instance's own `FAIL_TO_PASS` test modules under `sys.settrace` in a uv-provisioned interpreter matching that django version, at the instance's `base_commit` with its `test_patch` applied, and records **executed** `Test -> Function` call edges. `friction.covers3` folds those edges into the type-resolved arm B graph and re-measures the clean directed signal, `test -> fix`.

## Correction: an earlier run measured 0.3% mapping because of an identity bug

> **This section records a corrected measurement rather than quietly replacing it.**
>
> The first COVERS run recorded each executed function by its bare `co_name`
> (`save`, `__init__`, `__call__`) — the method name **with no enclosing class**.
> Arm B nodes are SCIP canonical symbols, which *are* class-qualified
> (`django.core.validators.URLValidator::__call__`). Under the strict join a
> module-level function rejoined its symbol but a *method* never could, so only
> **69 / 23,043 (0.3%)** of COVERS edges mapped and the strict gate read RED with
> a **+0** connectivity delta. That RED was an **artifact of the tracer's naming,
> not a property of the tests** — the same class of error that once made this
> project report a fake AUC from truncated path sampling.
>
> The fix (`trace.qualified_name`): prefer `co_qualname` (Python 3.11+, which
> reads `Class.method` directly); on the 3.8/3.9/3.10 guests these django
> versions actually run under, reconstruct the class from `self` (or `cls` for a
> classmethod) in the traced frame's locals; a genuinely module-level function
> keeps its bare name. The tracer now emits `<relpath>::<Class>.<name>`, and
> `covers3.covers_identity` joins that against SCIP's `module::Class#member()`
> shape. The numbers below are the **re-measured** result on freshly re-traced
> instances.

## Before / after (directed test -> fix, bounded at 6 hops)

Re-traced subset: **18 django instances**, each traced fresh in a throwaway
`--shared` clone with the editable install refreshed per `base_commit`.

| Corpus | test -> fix |
|---|---|
| Traced subset (18), static only | **11/18 (61%)** |
| Traced subset (18), **with COVERS (strict SCIP identity, qualified tracer)** | **12/18 (67%)** |
| Traced subset (18), with COVERS (lax module+name, sensitivity) | 12/18 (67%) |

Delta from folding COVERS in: **+1** instance (both strict and lax). Instance that flipped disconnected -> connected: `django__django-11265` (strict and lax alike).

## COVERS mapping success rate — read this before the table above

COVERS edges are keyed by `path/to/file.py::Class.name`; arm B nodes are SCIP `<module>::<Class>#<member>` symbols. Both map into one identity space via `friction.identity`.

| Metric | Strict SCIP identity (qualified) | Lax (module, name) | Strict, OLD unqualified run |
|---|---|---|---|
| COVERS edges with BOTH endpoints mapped | **3492 / 12635 (27.6%)** | 7806 / 12635 (61.8%) | 69 / 23043 (0.3%) |
| COVERS endpoints mapped | 14822 / 25270 (58.7%) | 20081 / 25270 (79.5%) | 5246 / 46086 (11%) |
| dynamic edges folded into arm B graphs | 2462 | 19949 | 35 |

**The identity fix moved strict edge mapping from 0.3% to 27.6% — a ~90x lift — putting the strict join within reach of what the lax join approximates.** An unmapped COVERS edge is still not a connectivity improvement, so the residual gap is stated honestly below.

### Why the residual 72% still does not map (concrete diagnosis)

Diagnosed on `django__django-11163` (170/1109 mapped), classifying every unmapped edge by which endpoint failed: **source-only miss 115, destination-only miss 742, both miss 82**. The destination misses dominate, and they are a *different* bug from the one just fixed — the reconstruction is correct but the target symbol legitimately is not in SCIP's definition-keyed space:

1. **Runtime class vs definition site (the big one).** `type(self).__name__` is the *runtime* subclass, but the executed code object's file is where the method is *defined* — a base class or a decorator module. Example: `django/utils/deconstruct.py::FileSystemStorage.__new__` reconstructs to `django.utils.deconstruct.FileSystemStorage::__new__`, which SCIP does not have — SCIP keys the method at its definition site (`@deconstructible`'s inner class), not at the runtime subclass. The **34-point gap between lax (61.8%) and strict (27.6%)** is exactly this population: module + bare name agree, but the class does not.
2. **Import-time module bodies.** Edges whose source is `tests/…::<module>` (code run at import) pass the `tests/` source filter but have no function symbol to rejoin.
3. **Static methods** (no `self`/`cls`, so the class cannot be reconstructed) and **nested local functions** (`Outer.<locals>.inner`), neither of which is a SCIP member symbol.

None of these is the bare-name bug; each is an inherent limitation of frame-based reconstruction against a definition-keyed index. Closing them would need a definition-site lookup (map the runtime class up its MRO to the class that actually defines the code object), which is future work, not a correctness fix to the current measurement.

## Verdict

**Strict SCIP-identity fold, qualified tracer -> AMBER (60-80%): test->fix 11/18 (61%) -> 12/18 (67%), delta +1, one instance flips disconnected->connected. Strict edge mapping is now 3492/12635 (27.6%), up ~90x from the 0.3% the unqualified tracer produced, and the earlier RED verdict is retracted as an identity artifact. The executed Test->Function edges DO carry test->fix signal and it is now recoverable in the graph's own strict identity space, not only under the class-agnostic lax relaxation. The improvement is real but modest: COVERS is not a dramatic connectivity multiplier on this subset. The remaining unmapped majority is a distinct runtime-class-vs-definition-site limitation (quantified as the 34pp lax-minus-strict gap), not a naming bug. Corpus expansion (Task 4) is independent either way.**

## Per-instance detail (strict, qualified tracer)

| instance | static test->fix | +COVERS | dyn edges | edge map rate |
|---|---|---|---|---|
| django__django-10097 | False | False | 1038 | 1617/6903 (23%) |
| django__django-10554 | True | True | 193 | 200/448 (45%) |
| django__django-10880 | False | False | 154 | 155/553 (28%) |
| django__django-10973 | True | True | 0 | 6/9 (67%) |
| django__django-11066 | False | False | 32 | 40/92 (43%) |
| django__django-11087 | True | True | 60 | 89/328 (27%) |
| django__django-11095 | True | True | 21 | 59/198 (30%) |
| django__django-11099 | True | True | 20 | 46/155 (30%) |
| django__django-11119 | True | True | 8 | 15/61 (25%) |
| django__django-11133 | True | True | 64 | 135/223 (61%) |
| django__django-11138 | False | False | 122 | 189/464 (41%) |
| django__django-11149 | False | False | 81 | 176/475 (37%) |
| django__django-11163 | True | True | 136 | 170/1109 (15%) |
| django__django-11179 | True | True | 55 | 84/312 (27%) |
| django__django-11206 | True | True | 2 | 8/16 (50%) |
| django__django-11211 | False | False | 304 | 324/941 (34%) |
| django__django-11239 | True | True | 0 | 7/11 (64%) |
| django__django-11265 | False | **True** | 172 | 172/337 (51%) |

Aggregate: static 11/18 (61%) -> +COVERS 12/18 (67%); strict edge map 3492/12635 (27.6%); 2462 dynamic edges folded.

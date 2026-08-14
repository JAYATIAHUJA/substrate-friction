# Call-resolution audit (django CALLS edges)

**Question.** `friction.parsing.calls.resolve_with_stats` resolves ~22% of call
sites on django. The plan expected 50–70%. Is the graph pathologically sparse, or
is the low rate a legitimate consequence of statically-unresolvable calls (stdlib,
third-party, duck typing) that are correctly excluded?

**Answer (verdict up front).** 22% is *acceptable and explainable*. The dominant
unresolved mass is duck-typed method dispatch on statically-unknown receivers
(~34% of all call sites) plus builtins/stdlib/third-party (~20%) plus module-level
calls that have no caller node (~9%) plus class instantiations the model
deliberately does not draw as function→function edges (~11%). None of these are
resolver bugs. There **is** one genuine, systematic correctness defect — a
spurious `.__init__` component in package qualnames — but its yield is small
(~0.2pp). The only path to a materially higher rate is following re-export chains
through `__init__.py`, which is a larger change. Details and numbers below.

---

## Method

The 22.27% figure in the plan was measured at an instance `base_commit`
(188,312 call sites / 41,929 resolved). This audit re-ran the *exact* resolution
logic of `resolve_with_stats` over the working `data/repos/django` tree
(detached HEAD `5573a54d40`), instrumented to record every **unresolved** call
site with its syntactic form and its import context, then classified all of them.

Reproduced baseline on this tree: **28,230 / 126,191 = 22.37%** resolved.
The call-site count differs from the plan's (different commit) but the *rate* is
identical to two significant figures (22.27% vs 22.37%), so the classification
below is representative of the reported number.

Every classifier bucket is disjoint; the 15 buckets sum exactly to the 97,961
unresolved call sites.

---

## Classification of all 97,961 unresolved call sites

| count | % of all sites | % of unresolved | bucket | what it actually is |
|------:|---:|---:|---|---|
| 20,417 | 16.18% | 20.84% | `self.attr()`, attr is no known method | duck / dynamic — property, attribute assigned in `__init__`, or method inherited from a **third-party / stdlib** base. No django class defines this name. |
| 12,387 | 9.82% | 12.64% | `var.method()` | duck typing — receiver is a local variable of unknown static type |
| 10,930 | 8.66% | 11.16% | module-level call, no enclosing function | **structural** — a CALLS edge needs a caller *function* node; top-level calls have none |
| 10,132 | 8.03% | 10.34% | bare builtin `len()/str()/isinstance()…` | out of scope (builtin) |
| 9,649 | 7.65% | 9.85% | `from <third-party> import f; f()` | out of scope (third-party import) |
| 9,343 | 7.40% | 9.54% | `from django… import Name; Name()` | **mostly class constructors + re-exports** (see below), *not* a plain miss |
| 8,075 | 6.40% | 8.24% | `a.b.c()` attribute chain | duck typing — intermediate types unknown |
| 5,336 | 4.23% | 5.45% | `mod.attr()`, mod imported from django | **mixed**: constructors, module-func calls (fixable), singletons |
| 5,156 | 4.09% | 5.26% | `from <stdlib> import f; f()` | out of scope (stdlib import) |
| 2,410 | 1.91% | 2.46% | `f().method()` chained call | duck typing — return type unknown |
| 2,335 | 1.85% | 2.38% | bare name, not a def anywhere | dynamic — locally-bound callable / comprehension var |
| 1,011 | 0.80% | 1.03% | `self.method()`, method exists elsewhere | **real miss candidate** — inheritance (see Fix INHERITS) |
| 543 | 0.43% | 0.55% | bare name matches an ambiguous django def | not safely resolvable (ambiguous) |
| 226 | 0.18% | 0.23% | callee is subscript/lambda/call literal | dynamic |
| 11 | 0.01% | 0.01% | `cls.method()`, method exists elsewhere | real miss candidate (inheritance) |

### Rolled up into the four categories the task asked for

- **stdlib / third-party import (correctly out of scope):** 14,805 provable
  (9,649 third-party + 5,156 stdlib) = **11.7% of all call sites**. This is a
  *floor*, not a ceiling: a large share of the duck-typing buckets also target
  stdlib/third-party receivers (`response.json()`, `self.assertEqual()`,
  `logger.info()`), but that cannot be proven statically, so they are counted as
  duck typing instead.
- **method call on a receiver of unknown static type (duck typing):** 43,289 =
  **34.3% of all call sites** — the single largest category by far. This is the
  well-known ceiling of AST-based Python call-graph extraction: `x.m()` cannot be
  resolved without inferring the type of `x`.
- **target IS defined in django but the resolver missed it (real miss):** the
  three `real-miss` buckets total 16,244 raw, **but only ~820 of those are
  genuinely fixable function→function edges** (measured below). The rest are class
  constructors (~10,400 — a modeling choice, not a bug) and re-exports / ambiguous
  names (~5,000).
- **decorator-wrapped / getattr / dynamic / builtin:** 12,693 =
  **10.1% of all call sites** (10,132 builtins + 2,335 unbound bare names + 226
  exotic callees).
- **structural (not in the task's four, but real):** 10,930 module-level calls
  (**8.7%**) can never form an edge — there is no caller function to be the source.
- **class instantiation `ClassName(...)` (design choice):** 13,965 unresolved
  calls (**11.1%**) invoke a known django *class*. The model draws a function→function
  call graph and deliberately does not emit an instantiation edge to `__init__`.
  This is defensible but is the largest single lever if constructor edges are ever
  wanted (see below).

---

## The one genuine systematic defect: `.__init__` in package qualnames

`friction.parsing.symbols._module_name` computes a module name by stripping the
`.py` suffix and joining path parts. For a package initializer
`django/utils/translation/__init__.py` it yields the module name
`django.utils.translation.__init__`, so every symbol defined **directly in a
package `__init__.py`** gets a qualname like
`django.utils.translation.__init__.gettext`.

But the resolver's import path builds its lookup key from the *import statement*:
`from django.utils.translation import gettext` → it queries
`fn_by_qual["django.utils.translation.gettext"]`, which does not exist. Every such
call silently misses.

- Blast radius: **354 function defs across 22 packages** carry a spurious
  `.__init__.` in their qualname.
- Concrete miss: `django/contrib/admin/models.py:132`, call text `gettext`
  (also lines 129, and helpers.py:304/307). Import is
  `from django.utils.translation import gettext`; the def lives at
  `django/utils/translation/__init__.py` with qualname
  `django.utils.translation.__init__.gettext`; the resolver looks up
  `django.utils.translation.gettext` → miss. **Why:** the `.__init__` suffix on
  the package qualname is never present in the `from pkg import name` lookup key.

---

## Other concrete real misses (file · line · call · should-match · why)

1. **Module-function call not handled at all.**
   `django/contrib/admin/filters.py:300` — `timezone.now()`.
   Import `from django.utils import timezone`; target is
   `django.utils.timezone.now` (a real def). **Why it misses:** the `attribute`
   branch only tries `self.`, a unique `ClassName.`, a `ClassName().` constructor,
   and a unique bare-suffix fallback. It has *no* case for "obj is an imported
   module → look up `{module}.{attr}`", so every `module.func()` falls through.
   Same pattern: `django/contrib/admin/utils.py:427` — `formats.localize()` →
   `django.utils.formats.localize`.

2. **`self.method()` defined on an ancestor class (INHERITS gap).**
   `django/contrib/admin/options.py:2030` — `self.get_readonly_fields()` inside a
   `ModelAdmin` method; the method is defined on the ancestor
   `django.contrib.admin.options.BaseModelAdmin.get_readonly_fields`. **Why it
   misses:** the `self.` branch only checks the caller's *own* class qualname
   (`owner.qualname + '.' + attr`); it never walks `INHERITS` up to base classes.
   Same pattern: `options.py:2028` `self.get_exclude()`, `options.py:1907`
   `self.has_change_permission()`, `filters.py:127` `self.expected_parameters()`
   → `ListFilter.expected_parameters`.

3. **Re-export through `__init__.py`.**
   `django/contrib/admin/models.py:147` — `reverse(...)`, imported
   `from django.urls import reverse`. `reverse` is defined in
   `django/urls/base.py` and only *re-exported* by `django/urls/__init__.py`
   (`from .base import reverse`). Neither `django.urls.reverse` nor
   `django.urls.__init__.reverse` is a *def* — it is an import alias — so even the
   `.__init__` fix above does not catch it. **Why it misses:** the resolver does
   not follow re-export chains (`from .submodule import X` inside a package init).

---

## Measured yield of candidate fixes (do NOT implement here)

Each fix was simulated against the recorded unresolved set (exact qualname
membership test), so these are floors, not guesses.

| fix | mechanism | additional resolved | new rate |
|---|---|--:|--:|
| **A — strip `.__init__`** | treat a package `__init__.py` module as the package name in `_module_name` (or add an `.__init__`-stripped fallback key) | +225 | 22.55% |
| **B — module-attribute calls** | add an `attribute` case: if `obj` is an imported module (plain `import a.b.c [as X]`, or `from pkg import submod`), resolve `{module}.{attr}`; fold in the `.__init__` fallback | +470 | ~22.7% |
| **INHERITS — `self.method()` up the base chain** | when `self.attr` misses on the own class, walk `INHERITS` (bases already in the graph) and take the first ancestor that defines `attr` | +123 (112 self + 11 cls) | — |
| **A + B combined** | (disjoint syntactic forms) | +695 | **22.92%** |

Notes on the ceiling:
- The INHERITS walk only recovers **112 / 683** eligible `self.X()` misses; the
  other ~570 resolve to a base that is third-party or `object` (e.g.
  `TestCase`, `dict`), so they are genuinely unresolvable. Yield is real but capped.
- **Re-export following** is the only lever with a materially larger payoff:
  ~1,156 function-name re-exports (and ~4,969 *class* re-exports if constructor
  edges are added) currently miss because the symbol is imported-and-re-exported
  by a package `__init__.py` rather than defined there. Recovering these requires
  parsing `from .sub import X` statements inside init files and following the
  alias to the defining module — a bounded but non-trivial change, out of scope
  for this diagnostic task.
- **Constructor edges** (`ClassName()` → the class, or its `__init__`) would move
  ~13,965 calls (11.1%) but change the graph's semantics from a pure function
  call graph to a call+instantiation graph; that is a modeling decision, not a
  bug fix.

**Bottom line for the README.** The 22% resolution rate is honest and mostly
structural: ~34% of all call sites are duck-typed dispatch that no AST-based
resolver can resolve without type inference, ~20% are builtins/stdlib/third-party
correctly out of scope, ~9% are module-level calls with no caller, and ~11% are
class instantiations the model does not draw. The resolver has one real
correctness bug (the `.__init__` package-qualname mismatch) and two conservative
gaps (no module-function resolution, no INHERITS walk), but fixing all three
raises the rate only to ~23%. Every path measurement in the project rests on a
graph that is sparse *by the nature of static Python*, not by a defect — and that
sparsity should be stated plainly as a limitation, with the duck-typing ceiling
named as the reason.

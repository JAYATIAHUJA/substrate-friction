# Substrate Friction — Completion Plan (the missing 15%)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close the four gaps between the shipped project and the build spec — dynamic `COVERS` edges, the missing node/edge types, a corpus of 150+ instances across multiple repos, and a real train/test split — so the original thesis finally gets a *fair* test.

**Architecture:** A per-instance dynamic tracer runs the instance's own `FAIL_TO_PASS` tests under `sys.settrace` at its `base_commit`, in a uv-provisioned interpreter matching that django version, and records real `Test→Function` `COVERS` edges. Those edges are unioned into the type-resolved arm B graph. The corpus then expands to 4 repos and 150+ instances, and the evaluation re-runs with a repo-held-out split.

**Tech Stack:** Python 3.12 host + uv-managed 3.8/3.9/3.10 guests, `sys.settrace`, scip-python, NetworkX, HydraDB (Bolt), scikit-learn, statsmodels, pytest.

---

## MEASURED — probed on this machine, 2026-08-16

**The crux is confirmed feasible.** Django 3.0 at base commit `b9cf764be6`, interpreter provisioned with `uv venv --python 3.9`, package installed with `uv pip install -e .`:

```
python runtests.py --settings=test_sqlite --parallel=1 dispatch
  -> suite runs clean: test DBs created and destroyed, 0 issues
```

With a `sys.settrace` tracer wrapped around the same run, scoped to `django/`:

```
TRACED 3431 call edges | 2333 functions entered | 2.0s
```

**2 seconds per test module, on the interpreter that django version actually needs.** These are *executed* edges — they include the pytest/`setUp`/framework-dispatch paths that a static call graph structurally cannot see, which is the leading hypothesis for why `test→fix` connectivity was only 55%.

Interpreter mapping (verified available via `uv python list`): 3.8, 3.9, 3.10, 3.11, 3.12. Django 1.11–2.2 → 3.8; 3.0–3.2 → 3.9; 4.0–4.1 → 3.10; 4.2–5.0 → 3.11/3.12.

### What is currently missing, verified against the shipped payload

```
node labels in data/shipped: {'Function': ...}       <- only Function
edge types  in data/shipped: {'CALLS': ...}          <- only CALLS
COVERS      : exists in dead v1 code, unused
ConfigKey / READS_CONFIG : absent entirely
corpus      : 50 instances, 1 repo (django)
train/test  : none (n=44 too small)
```

Spec Part 3.2 calls `COVERS` *"the important one and the hardest to get right."* It was never built.

---

## Global Constraints

- Every constraint from the v4 plan still binds: `count(*)` never `count(<node>)`; no `DISTINCT` in an aggregate; bounded single-typed variable-length patterns; integer-`id` matching; `algo.*` values are inlined string lists; Bolt for `UNWIND`; batches ≤1024; graph `default` only; disjoint id bands.
- **Report `test→fix` (directed) and `undirected` separately, always.** Undirected means "shares a neighbourhood," never "the test exercises this code." `COVERS` edges are the first thing in this project that *does* mean the latter — say so precisely, and never retro-apply that meaning to the static results.
- **Never mutate the working django clone's state destructively.** Trace in a throwaway `--shared` clone; restore on every exit path.
- No metric may enumerate paths at query time.
- Wipe `hydradb-data` before heavy loading; read health is not liveness ([#81](https://github.com/hydra-db/hydradb/issues/81)).
- Do not hide a negative result. If `COVERS` does not rescue the thesis, that is the finding.

---

## Tasks

### Task 1 — `trace.py`: dynamic COVERS edges ⚠️ the one that matters

**Files:** create `src/friction/trace.py`, `tests/test_trace.py`

**Interfaces:**
- `TraceResult` dataclass: `edges: list[tuple[str, str]]`, `functions: int`, `seconds: float`, `ok: bool`, `error: str`
- `python_for_django(version: tuple[int, int]) -> str` — django version → interpreter ("3.8"/"3.9"/"3.10"/"3.12")
- `django_version(repo: Path) -> tuple[int, int]` — parse `VERSION` from `django/__init__.py`
- `provision(repo: Path, py: str) -> Path` — `uv venv --python <py>` + `uv pip install -e .`; returns the interpreter path
- `trace_tests(repo: Path, interpreter: Path, test_labels: list[str], timeout: int = 300) -> TraceResult`
- `covers_edges(trace: TraceResult, test_prefixes: tuple[str, ...] = ("tests/",)) -> list[tuple[str, str]]` — keep only edges whose **source** is a test function, transitively closed to depth 1 from the test entry

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
import pytest
from friction import trace


def test_django_version_maps_to_an_interpreter():
    assert trace.python_for_django((2, 2)) == "3.8"
    assert trace.python_for_django((3, 0)) == "3.9"
    assert trace.python_for_django((4, 0)) == "3.10"
    assert trace.python_for_django((4, 2)) == "3.12"


def test_unknown_future_version_falls_back_to_newest():
    assert trace.python_for_django((9, 9)) == "3.12"


def test_covers_keeps_only_edges_originating_at_a_test():
    tr = trace.TraceResult(
        edges=[("tests/test_a.py::test_one", "django/db/models.py::save"),
               ("django/db/models.py::save", "django/db/base.py::_do_insert")],
        functions=3, seconds=1.0, ok=True, error="")
    got = trace.covers_edges(tr)
    assert got == [("tests/test_a.py::test_one", "django/db/models.py::save")]


def test_covers_is_empty_when_nothing_originates_at_a_test():
    tr = trace.TraceResult(edges=[("django/a.py::f", "django/b.py::g")],
                           functions=2, seconds=0.1, ok=True, error="")
    assert trace.covers_edges(tr) == []


def test_trace_result_reports_failure_without_raising():
    tr = trace.TraceResult([], 0, 0.0, False, "boom")
    assert tr.ok is False and tr.error == "boom"


@pytest.mark.engine
def test_trace_a_real_django_module(tmp_path):
    """The probe, as a standing regression test. Needs a django clone."""
    repo = Path("data/repos/django")
    if not repo.exists():
        pytest.skip("django clone not present")
    ver = trace.django_version(repo)
    interp = trace.provision(repo, trace.python_for_django(ver))
    res = trace.trace_tests(repo, interp, ["dispatch"])
    assert res.ok, res.error
    assert res.functions > 100
    assert len(res.edges) > 100
```

- [ ] **Step 2: Run it and watch it fail** — `uv run pytest tests/test_trace.py -v -m "not engine"`, expect `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/friction/trace.py`**

The tracer runs *inside* the guest interpreter as a generated script, because the host is 3.12 and django 3.0 cannot import there. Key details proven by the probe: `sys.path` must include the `tests/` directory (else `test_sqlite` settings are not importable), `runtests.py` is executed via `compile`/`exec` with `__name__ == "__main__"`, `SystemExit` is caught, and the trace is scoped to files under `django/` so third-party frames are skipped.

```python
"""Dynamic COVERS edges: what a test actually executes.

The build spec called COVERS "the important one and the hardest to get right"
and offered a static approximation (a test transitively calls a function within
3 hops). That approximation cannot see pytest fixtures, setUp, parametrize, or
framework dispatch -- which is the leading explanation for why static test->fix
connectivity measured only 55%.

This runs the tests. Measured: one django test module traces in ~2s and yields
~3,400 call edges over ~2,300 functions. Every edge is executed, not inferred.

Each django version needs its own interpreter (django 3.0 will not import on
3.12), so the tracer is emitted as a script and run under a uv-provisioned
guest.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_TRACER = '''
import sys, os, json, time
sys.path.insert(0, os.getcwd())
sys.argv = ["runtests.py", "--settings=test_sqlite", "--parallel=1"] + {labels!r}
ROOT = os.path.abspath("..")
SCOPE = os.path.join(ROOT, "django") + os.sep
edges, stack = set(), []

def tracer(frame, event, arg):
    if event != "call":
        return None
    c = frame.f_code
    if not c.co_filename.startswith(SCOPE):
        return None
    callee = os.path.relpath(c.co_filename, ROOT) + "::" + c.co_name
    if stack:
        edges.add((stack[-1], callee))
    stack.append(callee)
    def ret(f, e, a):
        if e == "return" and stack:
            stack.pop()
        return None
    return ret

t0 = time.perf_counter()
sys.settrace(tracer)
try:
    exec(compile(open("runtests.py").read(), "runtests.py", "exec"),
         {{"__name__": "__main__", "__file__": "runtests.py"}})
except SystemExit:
    pass
except Exception as exc:
    sys.stderr.write("TRACE_ERROR " + repr(exc)[:300])
finally:
    sys.settrace(None)

json.dump({{"edges": sorted(edges),
           "functions": len({{e[1] for e in edges}}),
           "seconds": round(time.perf_counter() - t0, 2)}},
          open({out!r}, "w"))
'''


@dataclass(frozen=True)
class TraceResult:
    edges: list[tuple[str, str]]
    functions: int
    seconds: float
    ok: bool
    error: str


_PY_FOR_DJANGO = ((2, 2, "3.8"), (3, 2, "3.9"), (4, 1, "3.10"))


def python_for_django(version: tuple[int, int]) -> str:
    for major, minor, py in _PY_FOR_DJANGO:
        if version <= (major, minor):
            return py
    return "3.12"


def django_version(repo: Path) -> tuple[int, int]:
    text = (Path(repo) / "django" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("VERSION"):
            nums = [int(p) for p in line.split("(")[1].split(")")[0].split(",")[:2]
                    if p.strip().strip("'\"").isdigit()]
            if len(nums) >= 2:
                return (nums[0], nums[1])
    return (4, 2)


def provision(repo: Path, py: str) -> Path:
    repo = Path(repo)
    venv = repo / ".trace-venv"
    interp = venv / "bin" / "python"
    if interp.exists():
        return interp
    subprocess.run(["uv", "venv", "-q", "--python", py, str(venv)],
                   check=True, capture_output=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(interp), "-e", "."],
                   cwd=str(repo), check=True, capture_output=True, timeout=600)
    return interp


def trace_tests(repo: Path, interpreter: Path, test_labels: list[str],
                timeout: int = 300) -> TraceResult:
    repo = Path(repo)
    out = repo / ".trace-out.json"
    script = repo / ".trace-run.py"
    script.write_text(_TRACER.format(labels=test_labels, out=str(out)),
                      encoding="utf-8")
    start = time.perf_counter()
    try:
        proc = subprocess.run([str(interpreter), str(script)],
                              cwd=str(repo / "tests"), capture_output=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return TraceResult([], 0, round(time.perf_counter() - start, 2), False,
                           f"timed out after {timeout}s")
    finally:
        script.unlink(missing_ok=True)

    if not out.exists():
        err = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
        return TraceResult([], 0, round(time.perf_counter() - start, 2), False, err)
    payload = json.loads(out.read_text(encoding="utf-8"))
    out.unlink(missing_ok=True)
    return TraceResult([tuple(e) for e in payload["edges"]],
                       payload["functions"], payload["seconds"], True, "")


def covers_edges(trace: TraceResult,
                 test_prefixes: tuple[str, ...] = ("tests/",)) -> list[tuple[str, str]]:
    """Test -> Function edges only: the source must live under a test path."""
    return [(s, d) for s, d in trace.edges
            if any(s.startswith(p) for p in test_prefixes)]


def cleanup(repo: Path) -> None:
    shutil.rmtree(Path(repo) / ".trace-venv", ignore_errors=True)
```

- [ ] **Step 4: Run tests to green** — `uv run pytest tests/test_trace.py -v`

- [ ] **Step 5: Trace one real instance's own FAIL_TO_PASS tests**

Take an instance from `data/instances/arms/manifest.jsonl`, derive its test labels from `FAIL_TO_PASS` (django labels are `module.Class.method` — pass the module portion to `runtests.py`), trace, and report: edges produced, functions entered, seconds, and **how many of the instance's fix sites appear as a COVERS target**. That last number is the whole point.

- [ ] **Step 6: Commit**

---

### Task 2 — `covers.py`: fold COVERS into the graph and re-measure connectivity

**Files:** create `src/friction/covers3.py`, `tests/test_covers3.py`; modify `src/friction/connectivity.py`

**Interfaces:**
- `merge_covers(static_edges, covers_edges) -> tuple[list, dict]` — union, tagging each edge `source: "static" | "dynamic"`
- `connectivity_with_covers(manifest, arms_root, covers_root) -> ConnectivityReport`

- [ ] **Step 1: Failing test** — a static graph where test and fix are disconnected becomes connected once a COVERS edge is added; edge provenance is preserved; a duplicate edge is not double-counted.

- [ ] **Step 2–4:** implement, green, then **re-run the connectivity measurement with COVERS included**.

- [ ] **Step 5: THE GATE.** Report `test→fix` directed connectivity before and after COVERS.

| Result | Action |
|---|---|
| ≥ 80% | The fixture gap was the cause. The thesis gets its first fair test — proceed to Task 4 with confidence. |
| 60–80% | Real improvement; proceed, and report the residual gap as a stated limitation. |
| < 60% | COVERS is not the blocker. Report that plainly — it is itself a finding about static-vs-dynamic code graphs — and proceed anyway, since the corpus expansion is independent. |

Write `docs/covers.md` with the before/after table whichever way it goes.

- [ ] **Step 6: Commit**

---

### Task 3 — the missing node and edge types

**Files:** modify `src/friction/scip/extract.py`, `src/friction/arms.py`, `src/friction/loader.py`; create `src/friction/config_keys.py`, `tests/test_config_keys.py`

Spec Part 3.1/3.2 lists five node types and seven edge types. The shipped graph has `Function` and `CALLS`.

- [ ] **Step 1:** `Test` nodes — a `Function` whose path is under a test prefix or whose name starts with `test_` is emitted with label `Test`. Cheap, and it makes `COVERS` type-correct.
- [ ] **Step 2:** `File` and `Class` nodes plus `DEFINED_IN`, `HAS_METHOD`, `INHERITS`, `IMPORTS` — these already exist in `scip.extract` output but are dropped by `arms.emit_arm`, which keeps only `CALLS`. Stop dropping them.
- [ ] **Step 3:** `ConfigKey` + `READS_CONFIG` — extract `settings.<NAME>` attribute reads from the SCIP index (django's `django.conf.settings` accesses). Emit one `ConfigKey` per distinct name.
- [ ] **Step 4:** Tests — each node type appears with the right label; each edge type round-trips through the loader; the shipped graph contains all seven edge types.
- [ ] **Step 5:** Re-emit one instance and assert the label/type census matches the spec. **Report the real census** — if `READS_CONFIG` yields near-zero, say so rather than shipping an empty edge type.
- [ ] **Step 6: Commit**

---

### Task 4 — corpus expansion to 150+ instances, 4 repos

**Files:** create `scripts/build_corpus3.py`; modify `src/friction/build3.py`

- [ ] **Step 1:** Clone `sympy`, `scikit-learn`, `matplotlib` beside django (full clones — SWE-bench base commits are historical).
- [ ] **Step 2:** Select instances: all django instances already built, plus enough from the other three to clear **150 total**, preferring instances whose `FAIL_TO_PASS` parses cleanly.
- [ ] **Step 3:** Build arm B (scip-python, ~40 s each, no dependency install) and arm A (tree-sitter) per instance, resumable via a `manifest.jsonl` append, `nohup` + poll.
- [ ] **Step 4:** Trace COVERS per instance where the repo's suite runs. **sympy/scikit-learn/matplotlib use pytest, not django's `runtests.py`** — add a pytest branch to `trace_tests` and report per-repo success rate honestly. If a repo's suite will not run, build it static-only and record that in the manifest.
- [ ] **Step 5:** Report: instances per repo, per-arm node/edge medians, COVERS coverage per repo, total wall clock.
- [ ] **Step 6: Commit**

---

### Task 5 — the fair test: re-run the science with a real split

**Files:** modify `src/friction/evaluate4.py`, `src/friction/features.py`; create `tests/test_split.py`

- [ ] **Step 1:** Add COVERS-aware features — `covers_hops` (directed test→fix over the COVERS-augmented graph) and `covers_fanout` (functions a test actually executes). Label each with its provenance.
- [ ] **Step 2:** **Leave-one-repo-out** evaluation: train on three repos, test on the held-out one, for each repo in turn. This is the split the spec asked for and it is stronger than a random split, because it cannot memorise repo identity.
- [ ] **Step 3:** Re-run the three confound checks at the new n, and add the repo-identity confound (does repo alone predict failure?).
- [ ] **Step 4:** Recompute the bootstrap CI at the new n and state the power honestly — `required_n` says ~610 instances for +0.05 AUC at ρ=0.5, so 150 is still short and must be said.
- [ ] **Step 5:** Regenerate `docs/evaluation.md`. **The retractions stay.** If friction still loses to `patch_lines`, that is the result and the headline stays the substrate finding.
- [ ] **Step 6: Commit**

---

### Task 6 — propagate honestly to the product

**Files:** modify `README.md`, `docs/video-script.md`, `src/friction/cli.py`, `src/friction/viz.py`, `docs/index.html`, `data/shipped/`

- [ ] **Step 1:** `friction check` gains a COVERS line — "the test actually executes this code" is now a claim we can make where a dynamic edge exists, and *only* there.
- [ ] **Step 2:** A new figure, `docs/plots/covers.png` — the same neighbourhood with static edges vs COVERS edges overlaid, showing what execution reveals that static analysis misses.
- [ ] **Step 3:** Update the README's connectivity section with the before/after table, the new n, the leave-one-repo-out result, and the corrected limitations. **Remove** "single repository" from limitations if it no longer applies; add whatever new limitation the COVERS work exposes.
- [ ] **Step 4:** Re-distil `data/shipped` (≤50 MB) and re-verify from a real clean clone: every acceptance command, plus the Pages site.
- [ ] **Step 5:** Update `docs/index.html` and the video script with the new numbers.
- [ ] **Step 6: Commit and push**

---

## Self-Review

**Spec coverage of the gaps.** `COVERS` (Part 3.2) → Tasks 1–2, dynamic rather than the spec's static default, because the static version is what produced the 55%. `Test`/`ConfigKey`/`READS_CONFIG`/remaining edge types (Part 3.1–3.2) → Task 3. 150+ instances and 3–5 repos (Parts 2.2, 11) → Task 4. Train/test split (Parts 5.3, 11) → Task 5, as leave-one-repo-out. Confound checks re-run at the new n → Task 5 Step 3.

**Deliberate departures.** (a) `COVERS` is dynamic-first, not static-first — the spec's ordering was "start static, upgrade if the correlation is weak," and the correlation *was* weak, so the upgrade is the whole point. (b) The split is leave-one-repo-out rather than random, which is strictly harder and rules out repo memorisation. (c) The headline does not change back to prediction even if connectivity improves — that would require beating the 0.787 text baseline, not merely improving on our own null.

**What this plan does not promise.** COVERS may not rescue the thesis. n=150 is still ~4× short of the power requirement. Both are stated in the tasks rather than discovered later.

**Type consistency.** `TraceResult(edges, functions, seconds, ok, error)` is produced by `trace_tests` and consumed by `covers_edges` and Task 2's `merge_covers`. `ConnectivityReport` is the existing v4 dataclass, extended not replaced. `V4Features` gains two fields; `FEATURE_NAMES` must be updated in the same commit or Task 5's tables desync.

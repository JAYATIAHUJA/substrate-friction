"""Dynamic COVERS edges: what a test actually executes.

The build spec called COVERS "the important one and the hardest to get right"
and offered a static approximation (a test transitively calls a function within
3 hops). That approximation cannot see pytest fixtures, setUp, parametrize, or
framework dispatch -- which is the leading explanation for why static test->fix
connectivity measured only 55%.

This runs the tests. Measured: one django test module traces in ~2s and yields
thousands of call edges over thousands of functions. Every edge is executed,
not inferred.

Each django version needs its own interpreter (django 3.0 will not import on
3.12), so the tracer is emitted as a script and run under a uv-provisioned
guest.

DEVIATION FROM THE PLAN (owned for correctness).  The plan's tracer scoped the
trace to files under ``django/`` only.  Django's own test suite lives under a
sibling ``tests/`` tree, so with a ``django/``-only scope NO recorded edge ever
originates in a test function and ``covers_edges`` -- whose entire job is to
keep edges whose *source* is a test -- returns an empty list on every real
trace.  That silently defeats COVERS.  The scope here is therefore the union of
``django/`` and ``tests/`` (configurable via ``scopes``), so that the executed
``Test -> Function`` edges the whole exercise depends on are actually captured.
The third-party frames the plan wanted to skip (installed into ``.trace-venv``)
are still excluded, because the venv is not one of the scoped subtrees.
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
SCOPES = tuple(os.path.join(ROOT, d) + os.sep for d in {scopes!r})
edges, stack = set(), []

def tracer(frame, event, arg):
    if event != "call":
        return None
    c = frame.f_code
    if not c.co_filename.startswith(SCOPES):
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
    # Resolve to an absolute path: the editable install runs with cwd=repo, and
    # a relative --python interpreter path would be re-anchored against that cwd
    # and fail to resolve (plan bug, fixed here).
    repo = Path(repo).resolve()
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
                timeout: int = 300,
                scopes: tuple[str, ...] = ("django", "tests")) -> TraceResult:
    # Absolute: the guest runs with cwd=repo/tests, so a relative script/out
    # path would be re-anchored against that cwd and not be found (plan bug).
    repo = Path(repo).resolve()
    out = repo / ".trace-out.json"
    script = repo / ".trace-run.py"
    script.write_text(
        _TRACER.format(labels=test_labels, out=str(out), scopes=list(scopes)),
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

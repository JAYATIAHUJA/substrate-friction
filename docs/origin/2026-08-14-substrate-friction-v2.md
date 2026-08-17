# Substrate Friction v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure what name-matched code graphs cost the AI-coding-agent tooling ecosystem, by building the first type-resolved call graph for SWE-bench instances and quantifying — as graph structure, on HydraDB — how much of a name-matched graph is fiction.

**Architecture:** For each SWE-bench instance, build **two** call graphs of the same repository at the same commit: (A) a **name-matched** graph reproducing what Aider / RepoGraph / LocAgent actually do, and (B) a **type-resolved** graph from `scip-python` (pyright-backed). Both load into HydraDB in disjoint id bands. Every downstream question — edge falsity, path structure, friction — is then a *graph comparison* answered by bounded path queries against the two arms.

**Tech Stack:** Python 3.12 + `uv`, pytest, `scip-python` (npm, Sourcegraph), protobuf (`scip_pb2` compiled from `scip.proto`), tree-sitter + tree-sitter-python (arm A only), neo4j Bolt driver, HydraDB open-source engine, networkx, scikit-learn, scipy, matplotlib, Docker + MinIO.

---

## Why this plan exists — what v1 got wrong

v1 built a tree-sitter call graph, measured a friction metric on it, and reported a null. Three measured facts invalidated that:

1. **73.9% of resolved CALLS edges were false.** A "bare name is globally unique → resolve it" fallback wired Python's builtin `super()` to `django/template/loader_tags.py::BlockNode.super` **1,321 times**, `.lower()` to `defaultfilters.lower` (259), `.extend()` to a GIS class (222).
2. **Removing the fallback gave average out-degree 0.33** (7,369 CALLS edges / 22,534 functions) — too sparse for bounded paths to exist.
3. Therefore the v1 null **never tested the thesis**. It measured name collisions.

Research then established three more things that reshape the goal:

4. **`scip-python` fixes it, verified by running it on this machine.** Full `django/` indexed in **24.3s**, no dependency install required (pyright bundles typeshed). **22,269 edges, 12,499 project→project, 81.3% of functions appear as a caller.** `super()` → `python-stdlib builtins/super#`; `.lower()` on a `str` → `builtins/str#lower().`; an untyped receiver emits **no occurrence** — a missing edge, never a wrong one.
5. **The prediction problem is already solved.** *Agent Psychometrics* (arXiv 2604.00594) reaches **AUC 0.841** on SWE-bench Verified; **problem-statement text alone reaches 0.787**; a task-agnostic prior reaches ~0.718. Claiming the problem is new would be desk-rejected.
6. **Everyone's repo graph is name-matched.** Aider's repo map draws an edge wherever a referenced identifier *name* matches a defined identifier *name*. RepoGraph does tree-sitter def/ref name matching plus a stdlib denylist. LocAgent's `invoke` edges are AST-derived, not type-resolved. **Nobody has published what that costs.**

**So the headline flips.** We are not predicting agent failure — that is done, better, by other people. We are measuring the substrate that the entire code-graph tooling ecosystem is built on, and we have the instrument to do it.

---

## Global Constraints

Every task's requirements implicitly include this section.

**Engine — hard limits (violations are parse errors):**
- Node matching is **integer `id` only**. Names are properties, never match keys.
- `algo.*` `sourceValues`/`targetValues` are **lists of STRINGS** matched against a **string** property, and must be **inlined as Cypher literals** — parameters are rejected with `composite parameter $name is only supported as an UNWIND input`. Every node carries `sid = str(id)`.
- Integer values in `sourceValues` are a parse error (`sourceValues must be a list of strings`); string values against an integer property parse but **match nothing**.
- `algo.MSpaths` supports `pairwise: true` (verified). `algo.SSpaths` requires an **integer `sourceNode`**, rejects a `sourceValues` set, and **without an explicit `pathCount` returns only the single shortest path**.
- Node upsert: `UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Label, n.prop = row.prop`. Labels may not appear in the MERGE pattern; exactly one SET label is required.
- Edge create: `UNWIND $rows AS row CREATE (a {id: row.src})-[:REL]->(b {id: row.dst})`.
- `count(path)` is rejected (`unknown path projection count`) — count client-side.
- `RETURN *`, `IN`, `CONTAINS`, `min`, `max`, `DISTINCT`-in-aggregate are unsupported. `WITH` is pass-through only. Variable-length paths need a mandatory upper bound. One statement per request.
- `UNWIND` batches cap at `max_parameters`, **1024 by default** (`DEFAULT_MAX_PARAMETERS`, `src/client/service.rs:37`) — chunk to the configured limit.
- HTTP does **not** accept `$params` for `UNWIND`. **Bolt is mandatory for loading.**
- Only the graph named `default` is reachable (403 otherwise). `DETACH DELETE` on a large graph exceeds the 29,999 ms query timeout. **Isolate by disjoint integer id bands.**

**Engine — operational:**
- `export RUST_MIN_STACK=33554432` or the node serves `/readyz` then aborts on the first query.
- `GRAPH_CELLS` must contain `GRAPH_CELL_ID`; `GRAPH_BOLT_NODE_ADDRESSES` must use `node-id=host:port`.
- **`CLOUD_PROVIDER=local` degrades**: manifest GC fails permanently (`put_opts` / `PutMode::Update` unimplemented by `LocalFileSystem`) after ~6 min of sustained writes, garbage is never reclaimed (~1,394 bytes/vertex), and **reads keep serving so the node looks healthy**. Keep the working set small; wipe `hydradb-data` between heavy runs; never trust read health as liveness. Filed as [hydra-db/hydradb#81](https://github.com/hydra-db/hydradb/issues/81).
- Engine pinned at `02a40025d2d57e97ab2754c8256219cdbfeab379` (v0.1.1).
- Healthy-store scaling: 16k nodes / 24k edges answers `maxLen 6` in ~1.5s; 34k/102k in ~7.5s. Binding constraint is `(both-degree)^maxLen`, not node count.

**scip-python:**
- Install: `npm i -g @sourcegraph/scip-python` (v0.6.6).
- **Always pass `--project-version`** or it crashes with `TypeError: Cannot read properties of undefined (reading 'indexOf')`.
- Run with cwd = repo root; write the index **outside** the repo so the checkout stays clean.
- It emits the **deprecated `enclosing_range` (field 7)**, not `typed_enclosing_range`. Read field 7.
- `symbol_roles` bitmask: `Definition = 0x1`.
- No pip package for the schema — compile `scip.proto` from `github.com/sourcegraph/scip` with `grpc_tools.protoc`.

**Project rules:**
- Python only. Say so.
- Never use the hosted product at `api.hydradb.com`.
- **Two arms, always.** Every structural claim is name-matched vs type-resolved on the *same* repo at the *same* commit. A single-arm number is not a finding.
- Do not claim per-instance failure prediction is novel. Cite arXiv 2604.00594 (0.841) and the 0.787 text-only baseline in the README.
- Do not report a friction AUC without also reporting patch-scope and text baselines on the same instances.
- **Label contamination is real and must be disclosed**: SWE-Bench+ (arXiv 2410.06992) found 32.7% solution leakage and 31% weak tests; OpenAI reports 59.4% of o3 failures on Verified were test flaws and no longer recommends the benchmark.
- Do not hide a negative result.

**Submission:**
- Public repo, OSI LICENSE in root, no participant-authored commit before 2026-08-12.
- Form: `forms.gle/GrMYKxLj9zPQcqqc8`. Deadline 2026-08-20, 11:59 PM PT.
- Video ≤ 3:00, order problem → project → demo → HydraDB.
- Track 02A and 02B are judged as **one track**.

---

## What carries over from v1

Reused unchanged: `friction.config`, `friction.client`, `friction.probe`, `friction.loader`, `friction.throughput`, `friction.swebench`, `friction.fidelity`, `friction.evaluate`, `friction.metric`, `friction.subgraph`, and the docker-compose/engine setup. 213 tests pass.

Rewritten: graph construction (`friction.parsing.*` becomes **arm A only**, explicitly labelled as the name-match baseline), `friction.build`, `friction.harness`, `friction.cli`, `friction.viz`, README, video.

Deleted claims: the v1 friction null and `docs/evaluation.md` as written. They are superseded and must be retracted in the README, not silently dropped.

---

## File Structure

```
substrate-friction/
├── README.md                       rewritten — leads with the substrate finding
├── setup.sh · docker-compose.yml   reused
├── scripts/
│   └── engine_scaling_sweep.py     reused
├── vendor/
│   └── scip.proto                  pinned copy of the SCIP schema
├── src/friction/
│   ├── config.py client.py probe.py loader.py throughput.py   REUSED
│   ├── swebench.py fidelity.py evaluate.py metric.py subgraph.py  REUSED
│   ├── scip/
│   │   ├── __init__.py
│   │   ├── schema.py               compile + import scip_pb2
│   │   ├── index.py                drive scip-python over a checkout
│   │   ├── extract.py              SCIP occurrences -> caller/callee edges
│   │   └── symbols.py              SCIP symbol -> stable node identity
│   ├── namematch/
│   │   ├── __init__.py
│   │   └── graph.py                arm A: the name-matched baseline graph
│   ├── arms.py                     build both arms for one instance
│   ├── delta.py                    THE FINDING: arm A vs arm B, quantified
│   ├── harness.py                  end-to-end run -> docs/*.md
│   ├── cli.py                      friction compare / check / eval / delta
│   └── viz.py                      two-arm contrast figures
└── tests/
    ├── test_scip_schema.py test_scip_index.py test_scip_extract.py
    ├── test_scip_symbols.py test_namematch.py test_arms.py
    ├── test_delta.py test_harness.py test_cli.py test_viz.py
    └── fixtures/scip_pkg/          a tiny package with KNOWN correct edges
```

**Decomposition rationale:** `scip/` is split four ways because each stage fails differently and must be independently reviewable — schema compilation is environmental, indexing is subprocess orchestration, extraction is the novel algorithm, and symbol identity is where cross-commit stability is won or lost. `delta.py` is separate from `harness.py` so the headline finding is a pure function over two edge sets, unit-testable without an engine or a checkout.

---

## Task Sequencing

Tasks 1–4 build arm B (type-resolved). Task 5 formalises arm A. Task 6 produces the headline finding. Tasks 7–9 put both arms in the engine and measure. Task 10 is the honest evaluation. Tasks 11–14 are the product.

**Task 6 is the gate.** If the name-match/type-resolved delta is small, the headline finding evaporates and you fall back to Task 10's evaluation as the deliverable. Do not build the CLI before Task 6.

---

### Task 1: SCIP schema and a decoded index

**Files:**
- Create: `substrate-friction/vendor/scip.proto`
- Create: `substrate-friction/src/friction/scip/__init__.py`
- Create: `substrate-friction/src/friction/scip/schema.py`
- Create: `substrate-friction/tests/test_scip_schema.py`
- Modify: `substrate-friction/pyproject.toml` (add `protobuf`, `grpcio-tools`)

**Interfaces:**
- Consumes: nothing internal.
- Produces:
  - `friction.scip.schema.ensure_compiled(proto_path: Path = VENDOR_PROTO, out_dir: Path = GENERATED) -> Path`
  - `friction.scip.schema.load_index(path: Path) -> "scip_pb2.Index"`
  - `friction.scip.schema.DEFINITION_ROLE: int = 0x1`

- [ ] **Step 1: Vendor the schema and add dependencies**

```bash
cd /Users/cruzer/Desktop/Hackathon/substrate-friction
mkdir -p vendor src/friction/scip
curl -sSL https://raw.githubusercontent.com/sourcegraph/scip/main/scip.proto -o vendor/scip.proto
head -5 vendor/scip.proto
```

Add to `pyproject.toml` dependencies: `"protobuf>=5.27"`, `"grpcio-tools>=1.64"`. Then `uv sync --extra dev`.

- [ ] **Step 2: Write the failing test**

`tests/test_scip_schema.py`:
```python
from pathlib import Path

import pytest

from friction.scip import schema


def test_ensure_compiled_produces_importable_module(tmp_path):
    out = schema.ensure_compiled(out_dir=tmp_path)
    assert out.exists()
    assert out.name == "scip_pb2.py"


def test_definition_role_bit_is_one():
    assert schema.DEFINITION_ROLE == 0x1


def test_load_index_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        schema.load_index(tmp_path / "nope.scip")


def test_index_roundtrip(tmp_path):
    schema.ensure_compiled(out_dir=tmp_path)
    pb = schema.scip_pb2()
    idx = pb.Index()
    doc = idx.documents.add()
    doc.relative_path = "a/b.py"
    occ = doc.occurrences.add()
    occ.symbol = "scip-python python . . `a.b`/f()."
    occ.symbol_roles = schema.DEFINITION_ROLE
    blob = tmp_path / "x.scip"
    blob.write_bytes(idx.SerializeToString())
    back = schema.load_index(blob)
    assert back.documents[0].relative_path == "a/b.py"
    assert back.documents[0].occurrences[0].symbol_roles == schema.DEFINITION_ROLE
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_scip_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.scip'`

- [ ] **Step 4: Write `src/friction/scip/__init__.py` and `schema.py`**

`src/friction/scip/__init__.py`:
```python
"""Type-resolved call graphs from SCIP indexes (arm B)."""
```

`src/friction/scip/schema.py`:
```python
"""Compile and load the SCIP protobuf schema.

There is no pip package for the SCIP schema and the npm module ships only
compiled JS, so the canonical `scip.proto` is vendored and compiled on demand
with grpc_tools.protoc.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

VENDOR_PROTO = Path(__file__).resolve().parents[3] / "vendor" / "scip.proto"
GENERATED = Path(__file__).resolve().parent / "_generated"

# scip.proto: SymbolRole.Definition = 1
DEFINITION_ROLE = 0x1

_MODULE: Any = None


def ensure_compiled(proto_path: Path = VENDOR_PROTO, out_dir: Path = GENERATED) -> Path:
    proto_path, out_dir = Path(proto_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").touch()
    target = out_dir / "scip_pb2.py"
    if target.exists() and target.stat().st_mtime >= proto_path.stat().st_mtime:
        return target
    subprocess.run(
        [sys.executable, "-m", "grpc_tools.protoc",
         f"-I{proto_path.parent}", f"--python_out={out_dir}", proto_path.name],
        check=True, capture_output=True,
    )
    if not target.exists():
        raise RuntimeError(f"protoc produced no {target}")
    return target


def scip_pb2() -> Any:
    """Import the compiled module, compiling it first if needed."""
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    target = ensure_compiled()
    spec = importlib.util.spec_from_file_location("scip_pb2", target)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scip_pb2"] = module
    spec.loader.exec_module(module)
    _MODULE = module
    return module


def load_index(path: Path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    index = scip_pb2().Index()
    index.ParseFromString(path.read_bytes())
    return index
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scip_schema.py -v`
Expected: PASS, 4 passed

- [ ] **Step 6: Add `_generated/` to `.gitignore` and commit**

```bash
grep -q '_generated/' .gitignore || echo 'src/friction/scip/_generated/' >> .gitignore
git add -A
git commit -m "feat(scip): vendor SCIP schema and compile-on-demand loader"
```

---

### Task 2: Drive scip-python over a checkout

**Files:**
- Create: `substrate-friction/src/friction/scip/index.py`
- Create: `substrate-friction/tests/test_scip_index.py`

**Interfaces:**
- Consumes: `friction.scip.schema`.
- Produces:
  - `friction.scip.index.IndexResult` dataclass: `path: Path`, `seconds: float`, `documents: int`, `occurrences: int`
  - `friction.scip.index.build_command(repo: Path, out: Path, name: str, version: str, target: str) -> list[str]`
  - `friction.scip.index.index_repo(repo, out, name="project", version="0", target=None, runner=subprocess.run) -> IndexResult`
  - `friction.scip.index.ScipUnavailable(RuntimeError)`

- [ ] **Step 1: Install the indexer and confirm it runs**

```bash
npm i -g @sourcegraph/scip-python
scip-python --version
```

Expected: a version string (v0.6.6 at time of writing). If `npm` is missing, install Node first — the whole of arm B depends on this binary.

- [ ] **Step 2: Write the failing test**

`tests/test_scip_index.py`:
```python
from pathlib import Path

import pytest

from friction.scip import index as I


def test_command_always_passes_project_version(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "django", "4.2", "django")
    assert "--project-version" in cmd
    assert cmd[cmd.index("--project-version") + 1] == "4.2"


def test_command_targets_only_the_named_package(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "django", "4.2", "django")
    assert "--target-only" in cmd
    assert cmd[cmd.index("--target-only") + 1] == "django"


def test_command_omits_target_when_none(tmp_path):
    cmd = I.build_command(tmp_path, tmp_path / "o.scip", "p", "1", None)
    assert "--target-only" not in cmd


def test_command_writes_output_outside_the_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    out = tmp_path / "out" / "o.scip"
    cmd = I.build_command(repo, out, "p", "1", None)
    written = Path(cmd[cmd.index("--output") + 1])
    assert written.is_absolute()
    assert repo not in written.parents


def test_index_repo_raises_when_binary_missing(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("scip-python")
    with pytest.raises(I.ScipUnavailable):
        I.index_repo(tmp_path, tmp_path / "o.scip", runner=boom)


def test_index_repo_raises_on_nonzero_exit(tmp_path):
    class R:
        returncode = 1
        stdout = b""
        stderr = b"normalizeNameOrVersion"
    with pytest.raises(I.ScipUnavailable) as exc:
        I.index_repo(tmp_path, tmp_path / "o.scip", runner=lambda *a, **k: R())
    assert "normalizeNameOrVersion" in str(exc.value)


@pytest.mark.engine
def test_index_real_fixture_package(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "scip_pkg"
    out = tmp_path / "fixture.scip"
    res = I.index_repo(fixture, out, name="scip_pkg", version="0.0.1")
    assert res.path.exists()
    assert res.documents > 0
    assert res.occurrences > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_scip_index.py -v -m "not engine"`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.scip.index'`

- [ ] **Step 4: Write `src/friction/scip/index.py`**

```python
"""Run scip-python over a checkout and report what it produced.

Two operational facts the hard way: scip-python crashes with
"Cannot read properties of undefined (reading 'indexOf')" unless
--project-version is supplied, and the output must land outside the repo or
the checkout is left dirty.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from friction.scip.schema import load_index


class ScipUnavailable(RuntimeError):
    """scip-python is missing or refused to index."""


@dataclass(frozen=True)
class IndexResult:
    path: Path
    seconds: float
    documents: int
    occurrences: int


def build_command(repo: Path, out: Path, name: str, version: str,
                  target: str | None) -> list[str]:
    cmd = ["scip-python", "index",
           "--output", str(Path(out).resolve()),
           "--project-name", name,
           "--project-version", version]
    if target:
        cmd += ["--target-only", target]
    cmd.append(".")
    return cmd


def index_repo(repo: Path, out: Path, name: str = "project", version: str = "0",
               target: str | None = None, runner=subprocess.run) -> IndexResult:
    repo, out = Path(repo), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(repo, out, name, version, target)
    start = time.perf_counter()
    try:
        proc = runner(cmd, cwd=str(repo), capture_output=True)
    except FileNotFoundError as exc:
        raise ScipUnavailable(
            "scip-python not found — install with `npm i -g @sourcegraph/scip-python`"
        ) from exc
    elapsed = time.perf_counter() - start
    if getattr(proc, "returncode", 1) != 0:
        err = getattr(proc, "stderr", b"") or b""
        raise ScipUnavailable(err.decode("utf-8", "replace")[:600])
    idx = load_index(out)
    return IndexResult(
        path=out,
        seconds=round(elapsed, 2),
        documents=len(idx.documents),
        occurrences=sum(len(d.occurrences) for d in idx.documents),
    )
```

- [ ] **Step 5: Create the fixture package with known-correct edges**

`tests/fixtures/scip_pkg/mod_a.py`:
```python
class Base:
    def greet(self):
        return "base"


class Child(Base):
    def greet(self):
        return super().greet() + "!"


def lower(n):
    return n - 1


def shout(s: str) -> str:
    return s.lower()
```

`tests/fixtures/scip_pkg/mod_b.py`:
```python
from mod_a import Child, lower


def run(n):
    return Child().greet() + str(lower(n))
```

This fixture is the false-edge trap in miniature: `super().greet()` must resolve to `Base.greet` (not `Child.greet`), and `s.lower()` must resolve to `builtins/str#lower()` (not the module-level `lower`).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_scip_index.py -v`
Expected: PASS, 7 passed (including the engine-marked real index)

- [ ] **Step 7: Time a real django index and record it**

```bash
cd /Users/cruzer/Desktop/Hackathon/substrate-friction
uv run python -c "
from pathlib import Path
from friction.scip.index import index_repo
r = index_repo(Path('data/repos/django'), Path('/tmp/django.scip'),
               name='django', version='4.2', target='django')
print(r)
"
```

Expected: ~25s, ~828 documents. Record the number — it is the per-instance cost that makes this plan feasible.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(scip): drive scip-python over a checkout with timing"
```

---

### Task 3: Symbol identity — stable node keys across commits

**Files:**
- Create: `substrate-friction/src/friction/scip/symbols.py`
- Create: `substrate-friction/tests/test_scip_symbols.py`

**Interfaces:**
- Consumes: `friction.scip.schema`.
- Produces:
  - `friction.scip.symbols.Sym` dataclass: `symbol: str`, `kind: str` (`"function" | "class" | "other"`), `is_external: bool`, `module: str`, `name: str`
  - `friction.scip.symbols.parse_symbol(symbol: str) -> Sym`
  - `friction.scip.symbols.canonical(sym: Sym, path: str | None) -> str` — the cross-commit-stable key
  - `friction.scip.symbols.PROJECT_SCHEME: str = "scip-python python"`

- [ ] **Step 1: Write the failing test**

`tests/test_scip_symbols.py`:
```python
from friction.scip import symbols as S


FUNC = "scip-python python django 4.2 `django.db.models.query`/QuerySet#filter()."
CLS = "scip-python python django 4.2 `django.db.models.query`/QuerySet#"
STDLIB = "scip-python python python-stdlib 3.11 `builtins`/str#lower()."
BUILTIN_SUPER = "scip-python python python-stdlib 3.11 `builtins`/super#"


def test_function_symbol_parsed():
    s = S.parse_symbol(FUNC)
    assert s.kind == "function"
    assert s.name == "filter"
    assert s.module == "django.db.models.query"
    assert s.is_external is False


def test_class_symbol_parsed():
    s = S.parse_symbol(CLS)
    assert s.kind == "class"
    assert s.name == "QuerySet"


def test_stdlib_symbol_is_external():
    assert S.parse_symbol(STDLIB).is_external is True
    assert S.parse_symbol(BUILTIN_SUPER).is_external is True


def test_local_symbol_is_other():
    assert S.parse_symbol("local 12").kind == "other"


def test_canonical_is_stable_across_versions():
    a = S.parse_symbol(FUNC)
    b = S.parse_symbol(FUNC.replace("4.2", "5.0"))
    assert S.canonical(a, "django/db/models/query.py") == \
           S.canonical(b, "django/db/models/query.py")


def test_canonical_distinguishes_same_name_in_different_modules():
    other = FUNC.replace("django.db.models.query", "django.contrib.admin.views")
    assert S.canonical(S.parse_symbol(FUNC), "a.py") != \
           S.canonical(S.parse_symbol(other), "b.py")


def test_canonical_survives_a_missing_path():
    assert S.canonical(S.parse_symbol(FUNC), None).endswith("QuerySet#filter().")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scip_symbols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.scip.symbols'`

- [ ] **Step 3: Write `src/friction/scip/symbols.py`**

```python
"""SCIP symbol strings -> stable node identity.

A SCIP symbol looks like:
    scip-python python <package> <version> `<module>`/<Class>#<method>().
The package VERSION varies across SWE-bench base commits, so it must be
stripped from any identity used to compare graphs across instances.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PROJECT_SCHEME = "scip-python python"
_EXTERNAL_PACKAGES = {"python-stdlib"}
_DESCRIPTOR = re.compile(r"`(?P<module>[^`]*)`/(?P<rest>.*)$")


@dataclass(frozen=True)
class Sym:
    symbol: str
    kind: str
    is_external: bool
    module: str
    name: str


def parse_symbol(symbol: str) -> Sym:
    if not symbol.startswith(PROJECT_SCHEME):
        # "local 12" and any non-python scheme
        return Sym(symbol, "other", False, "", symbol)

    parts = symbol.split(" ", 4)
    package = parts[2] if len(parts) > 2 else ""
    tail = parts[4] if len(parts) > 4 else ""
    external = package in _EXTERNAL_PACKAGES

    m = _DESCRIPTOR.search(tail)
    if not m:
        return Sym(symbol, "other", external, "", tail)
    module, rest = m.group("module"), m.group("rest")

    if rest.endswith("()."):
        kind, name = "function", rest[:-3].split("#")[-1].split("/")[-1]
    elif rest.endswith("#"):
        kind, name = "class", rest[:-1].split("#")[-1].split("/")[-1]
    else:
        kind, name = "other", rest.rstrip(".#/")
    return Sym(symbol, kind, external, module, name)


def canonical(sym: Sym, path: str | None) -> str:
    """Identity that is stable across package versions and base commits.

    Uses the module descriptor rather than the file path, because a file can
    move between commits while the module path stays put.
    """
    if sym.kind == "other" and not sym.module:
        return f"?::{sym.name}"
    m = _DESCRIPTOR.search(sym.symbol)
    rest = m.group("rest") if m else sym.name
    return f"{sym.module}::{rest}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scip_symbols.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(scip): version-independent symbol identity"
```

---

### Task 4: SCIP occurrences → caller/callee edges

The novel algorithm. Every downstream number depends on it being right.

**Files:**
- Create: `substrate-friction/src/friction/scip/extract.py`
- Create: `substrate-friction/tests/test_scip_extract.py`

**Interfaces:**
- Consumes: `friction.scip.schema`, `friction.scip.symbols`.
- Produces:
  - `friction.scip.extract.Def` dataclass: `symbol: str`, `path: str`, `start: int`, `end: int`, `canonical: str`, `kind: str`
  - `friction.scip.extract.CallEdge` dataclass: `src: str`, `dst: str`, `dst_external: bool`, `weight: int`
  - `friction.scip.extract.collect_definitions(index) -> list[Def]`
  - `friction.scip.extract.innermost(defs_by_path, path, line) -> Def | None`
  - `friction.scip.extract.extract_edges(index) -> tuple[list[CallEdge], dict]`

- [ ] **Step 1: Write the failing test**

`tests/test_scip_extract.py`:
```python
import pytest

from friction.scip import extract as E
from friction.scip import schema


def _index(docs):
    pb = schema.scip_pb2()
    idx = pb.Index()
    for path, occs in docs.items():
        d = idx.documents.add()
        d.relative_path = path
        for sym, roles, rng, enc in occs:
            o = d.occurrences.add()
            o.symbol = sym
            o.symbol_roles = roles
            o.range.extend(rng)
            if enc:
                o.enclosing_range.extend(enc)
    return idx


F_OUTER = "scip-python python p 1 `m`/outer()."
F_INNER = "scip-python python p 1 `m`/outer()/inner()."
F_CALLEE = "scip-python python p 1 `m`/callee()."
STR_LOWER = "scip-python python python-stdlib 3 `builtins`/str#lower()."


def test_collect_definitions_reads_enclosing_range():
    idx = _index({"m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 20, 0])]})
    defs = E.collect_definitions(idx)
    assert len(defs) == 1
    assert defs[0].start == 0 and defs[0].end == 20


def test_definitions_without_enclosing_range_are_skipped():
    idx = _index({"m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], None)]})
    assert E.collect_definitions(idx) == []


def test_innermost_prefers_the_smallest_containing_span():
    outer = E.Def(F_OUTER, "m.py", 0, 20, "m::outer().", "function")
    inner = E.Def(F_INNER, "m.py", 5, 10, "m::outer()/inner().", "function")
    by_path = {"m.py": [outer, inner]}
    assert E.innermost(by_path, "m.py", 7).symbol == F_INNER
    assert E.innermost(by_path, "m.py", 15).symbol == F_OUTER
    assert E.innermost(by_path, "m.py", 25) is None
    assert E.innermost(by_path, "other.py", 7) is None


def test_reference_inside_a_definition_becomes_an_edge():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_CALLEE, schema.DEFINITION_ROLE, [12, 0, 12, 6], [12, 0, 14, 0]),
        (F_CALLEE, 0, [3, 4, 3, 10], None),
    ]})
    edges, stats = E.extract_edges(idx)
    pairs = {(e.src, e.dst) for e in edges}
    assert ("m::outer().", "m::callee().") in pairs
    assert stats["references"] == 1


def test_definition_occurrences_are_not_treated_as_references():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
    ]})
    edges, _ = E.extract_edges(idx)
    assert edges == []


def test_external_targets_are_flagged_not_dropped():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (STR_LOWER, 0, [3, 4, 3, 10], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert len(edges) == 1
    assert edges[0].dst_external is True


def test_self_edges_are_dropped():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_OUTER, 0, [3, 4, 3, 9], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert edges == []


def test_repeated_references_accumulate_weight():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_CALLEE, schema.DEFINITION_ROLE, [12, 0, 12, 6], [12, 0, 14, 0]),
        (F_CALLEE, 0, [3, 4, 3, 10], None),
        (F_CALLEE, 0, [5, 4, 5, 10], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert [e.weight for e in edges if e.dst == "m::callee()."] == [2]


def test_references_outside_any_definition_are_counted_not_silently_lost():
    idx = _index({"m.py": [(F_CALLEE, 0, [3, 4, 3, 10], None)]})
    edges, stats = E.extract_edges(idx)
    assert edges == []
    assert stats["unenclosed_references"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scip_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.scip.extract'`

- [ ] **Step 3: Write `src/friction/scip/extract.py`**

```python
"""Turn SCIP occurrences into caller -> callee edges.

Definition occurrences carry an `enclosing_range` spanning the body. A
reference occurrence lying inside that span was written *by* that definition,
so it is a call from it. Where spans nest (a method inside a class, a closure
inside a function) the INNERMOST containing definition is the caller.

scip-python 0.6.6 emits the deprecated `enclosing_range` (field 7), not
`typed_enclosing_range`, so field 7 is what is read here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from friction.scip.schema import DEFINITION_ROLE
from friction.scip.symbols import canonical, parse_symbol


@dataclass(frozen=True)
class Def:
    symbol: str
    path: str
    start: int
    end: int
    canonical: str
    kind: str


@dataclass(frozen=True)
class CallEdge:
    src: str
    dst: str
    dst_external: bool
    weight: int = 1


def _line(rng) -> int:
    return rng[0] if rng else -1


def _span(enclosing) -> tuple[int, int] | None:
    """enclosing_range is [startLine, startChar, endLine, endChar]."""
    if not enclosing or len(enclosing) < 3:
        return None
    return enclosing[0], enclosing[2]


def collect_definitions(index) -> list[Def]:
    out: list[Def] = []
    for doc in index.documents:
        for occ in doc.occurrences:
            if not occ.symbol_roles & DEFINITION_ROLE:
                continue
            span = _span(list(occ.enclosing_range))
            if span is None:
                continue
            sym = parse_symbol(occ.symbol)
            out.append(Def(
                symbol=occ.symbol,
                path=doc.relative_path,
                start=span[0],
                end=span[1],
                canonical=canonical(sym, doc.relative_path),
                kind=sym.kind,
            ))
    return out


def innermost(defs_by_path: dict[str, list[Def]], path: str, line: int) -> Def | None:
    best: Def | None = None
    for d in defs_by_path.get(path, ()):
        if d.start <= line <= d.end:
            if best is None or (d.end - d.start) < (best.end - best.start):
                best = d
    return best


def extract_edges(index) -> tuple[list[CallEdge], dict]:
    defs = collect_definitions(index)
    by_path: dict[str, list[Def]] = defaultdict(list)
    for d in defs:
        by_path[d.path].append(d)

    weights: dict[tuple[str, str, bool], int] = defaultdict(int)
    refs = unenclosed = 0

    for doc in index.documents:
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue
            refs += 1
            caller = innermost(by_path, doc.relative_path, _line(list(occ.range)))
            if caller is None:
                unenclosed += 1
                continue
            sym = parse_symbol(occ.symbol)
            if sym.kind == "other":
                continue
            dst = canonical(sym, None)
            if dst == caller.canonical:
                continue
            weights[(caller.canonical, dst, sym.is_external)] += 1

    edges = [CallEdge(s, d, ext, n) for (s, d, ext), n in sorted(weights.items())]
    stats = {
        "definitions": len(defs),
        "references": refs,
        "unenclosed_references": unenclosed,
        "edges": len(edges),
        "internal_edges": sum(1 for e in edges if not e.dst_external),
        "external_edges": sum(1 for e in edges if e.dst_external),
    }
    return edges, stats
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scip_extract.py -v`
Expected: PASS, 9 passed

- [ ] **Step 5: Prove the false edges are gone on the fixture**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.scip.index import index_repo
from friction.scip.schema import load_index
from friction.scip.extract import extract_edges

fx = Path("tests/fixtures/scip_pkg")
index_repo(fx, Path("/tmp/fx.scip"), name="scip_pkg", version="0.0.1")
edges, stats = extract_edges(load_index(Path("/tmp/fx.scip")))
print(stats)
for e in edges:
    print(f"  {'EXT ' if e.dst_external else 'int '}{e.src}  ->  {e.dst}")
PY
```

**This is the gate for the whole plan.** Required:
- `shout` → an **external** `builtins/str#lower()`, NOT the module-level `lower`.
- `Child.greet` → `Base#greet()`, NOT `Child#greet()`.

If either is wrong the extraction is broken and nothing downstream can be believed. Fix it here.

- [ ] **Step 6: Run it on real django and record the numbers**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.scip.schema import load_index
from friction.scip.extract import extract_edges
edges, stats = extract_edges(load_index(Path("/tmp/django.scip")))
print(stats)
callers = {e.src for e in edges}
print(f"distinct callers: {len(callers)}")
bad = [e for e in edges if e.dst.endswith("::super#") and not e.dst_external]
print(f"internal edges to a project 'super': {len(bad)}   (must be 0)")
PY
```

Expected: ~22,000 edges, ~12,500 internal, and **zero** internal edges to a project `super`. Record these — they are half the headline.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(scip): occurrence -> caller/callee edge extraction"
```

---

### Task 5: Arm A — the name-matched baseline graph

Not legacy code. This is the **experimental control**, and it must faithfully reproduce what Aider / RepoGraph / LocAgent actually do, or the comparison is a strawman.

**Files:**
- Create: `substrate-friction/src/friction/namematch/__init__.py`
- Create: `substrate-friction/src/friction/namematch/graph.py`
- Create: `substrate-friction/tests/test_namematch.py`

**Interfaces:**
- Consumes: `friction.parsing.symbols` (tree-sitter extraction, reused unchanged).
- Produces:
  - `friction.namematch.graph.NameEdge` dataclass: `src: str`, `dst: str`, `weight: int`, `rule: str`
  - `friction.namematch.graph.build(root: Path, stdlib_denylist: set[str] | None = None) -> tuple[list[NameEdge], dict]`
  - `friction.namematch.graph.DEFAULT_DENYLIST: frozenset[str]`

- [ ] **Step 1: Write the failing test**

`tests/test_namematch.py`:
```python
from pathlib import Path

from friction.namematch import graph as N

FIXTURE = Path(__file__).parent / "fixtures" / "scip_pkg"


def test_name_match_links_a_reference_to_a_same_named_definition():
    edges, _ = N.build(FIXTURE)
    pairs = {(e.src, e.dst) for e in edges}
    assert any(dst.endswith("::lower") for _, dst in pairs)


def test_name_match_reproduces_the_false_edge_it_is_meant_to_model():
    """s.lower() must WRONGLY bind to the module-level lower — that is the point."""
    edges, _ = N.build(FIXTURE)
    wrong = [e for e in edges if e.src.endswith("::shout") and e.dst.endswith("::lower")]
    assert wrong, "arm A must reproduce the name-collision edge, or it is not a fair control"


def test_denylist_suppresses_known_builtins():
    edges, _ = N.build(FIXTURE, stdlib_denylist={"lower"})
    assert not [e for e in edges if e.dst.endswith("::lower")]


def test_stats_report_rule_provenance():
    _, stats = N.build(FIXTURE)
    assert "by_rule" in stats
    assert set(stats["by_rule"]) <= {"module_local", "self_method", "import_alias", "bare_name"}


def test_default_denylist_contains_common_builtins():
    assert {"super", "len", "str", "list"} <= set(N.DEFAULT_DENYLIST)


def test_no_self_edges():
    edges, _ = N.build(FIXTURE)
    assert all(e.src != e.dst for e in edges)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_namematch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.namematch'`

- [ ] **Step 3: Write `src/friction/namematch/graph.py`**

```python
"""Arm A — the name-matched call graph, as the ecosystem actually builds it.

This deliberately reproduces the standard approach so the comparison is fair:
  * Aider's repo map draws an edge wherever a referenced identifier NAME matches
    a defined identifier NAME (tree-sitter tags + PageRank).
  * RepoGraph does tree-sitter def/ref name matching plus an empirical stdlib
    denylist.
  * LocAgent's `invoke` edges are AST-derived, not type-resolved.

It is the control arm, not dead code. Every edge carries the rule that produced
it so the delta analysis can attribute error to a specific resolution strategy.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from friction.parsing.symbols import parse_repo

DEFAULT_DENYLIST = frozenset({
    "super", "len", "str", "list", "dict", "set", "tuple", "int", "float", "bool",
    "print", "open", "range", "type", "isinstance", "getattr", "setattr", "hasattr",
    "append", "extend", "lower", "upper", "strip", "split", "join", "format",
    "get", "keys", "values", "items", "add", "remove", "pop", "update", "copy",
})


@dataclass(frozen=True)
class NameEdge:
    src: str
    dst: str
    weight: int
    rule: str


def build(root: Path, stdlib_denylist: set[str] | None = None
          ) -> tuple[list[NameEdge], dict]:
    from friction.parsing.calls import resolve_with_stats

    deny = set(DEFAULT_DENYLIST if stdlib_denylist is None else stdlib_denylist)
    table = parse_repo(Path(root), repo_code=0)
    raw, _ = resolve_with_stats(Path(root), table)

    qual = {f.id: f.qualname for f in table.functions}
    qual.update({c.id: c.qualname for c in table.classes})
    name_of = {f.id: f.name for f in table.functions}
    name_of.update({c.id: c.name for c in table.classes})

    counts = {}
    for name in name_of.values():
        counts[name] = counts.get(name, 0) + 1
    unique = {n for n, c in counts.items() if c == 1}

    weights: dict[tuple[str, str, str], int] = defaultdict(int)
    for e in raw:
        if e.type != "CALLS":
            continue
        s, d = qual.get(e.src), qual.get(e.dst)
        if s is None or d is None or s == d:
            continue
        target = name_of.get(e.dst, "")
        if target in deny:
            continue
        rule = "bare_name" if target in unique else "module_local"
        weights[(s, d, rule)] += e.weight

    edges = [NameEdge(s, d, n, r) for (s, d, r), n in sorted(weights.items())]
    by_rule: dict[str, int] = defaultdict(int)
    for e in edges:
        by_rule[e.rule] += 1
    return edges, {"edges": len(edges), "by_rule": dict(by_rule),
                   "denylisted": len(deny)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_namematch.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(namematch): arm A control graph reproducing ecosystem practice"
```

---

### Task 6: THE FINDING — quantify the delta ⚠️ GATE

**Do not build the CLI, the visualization, or the README before this task produces numbers.**

**Files:**
- Create: `substrate-friction/src/friction/delta.py`
- Create: `substrate-friction/tests/test_delta.py`
- Create (generated): `substrate-friction/docs/graph-delta.md`

**Interfaces:**
- Consumes: `friction.scip.extract.CallEdge`, `friction.namematch.graph.NameEdge`.
- Produces:
  - `friction.delta.Delta` dataclass: `only_a: int`, `only_b: int`, `both: int`, `precision_a: float`, `recall_a: float`, `jaccard: float`, `worst_offenders: list[tuple[str, int]]`
  - `friction.delta.compare(arm_a, arm_b) -> Delta`
  - `friction.delta.write_report(delta, extra: dict, path: Path) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_delta.py`:
```python
import pytest

from friction import delta as D
from friction.namematch.graph import NameEdge
from friction.scip.extract import CallEdge


def A(*pairs):
    return [NameEdge(s, d, 1, "bare_name") for s, d in pairs]


def B(*pairs):
    return [CallEdge(s, d, False, 1) for s, d in pairs]


def test_identical_arms_give_perfect_agreement():
    r = D.compare(A(("f", "g")), B(("f", "g")))
    assert r.precision_a == 1.0 and r.recall_a == 1.0 and r.jaccard == 1.0


def test_disjoint_arms_give_zero_agreement():
    r = D.compare(A(("f", "g")), B(("x", "y")))
    assert r.precision_a == 0.0 and r.recall_a == 0.0 and r.jaccard == 0.0


def test_precision_is_fraction_of_arm_a_edges_confirmed_by_arm_b():
    r = D.compare(A(("f", "g"), ("f", "h")), B(("f", "g")))
    assert r.precision_a == 0.5
    assert r.recall_a == 1.0
    assert r.only_a == 1


def test_recall_counts_true_edges_arm_a_missed():
    r = D.compare(A(("f", "g")), B(("f", "g"), ("f", "h")))
    assert r.recall_a == 0.5
    assert r.only_b == 1


def test_external_arm_b_edges_are_excluded_from_the_comparison():
    b = [CallEdge("f", "builtins::str#lower().", True, 1)]
    r = D.compare(A(("f", "g")), b)
    assert r.only_b == 0


def test_worst_offenders_ranks_targets_by_unconfirmed_edge_count():
    a = A(("f1", "super"), ("f2", "super"), ("f3", "super"), ("f4", "g"))
    r = D.compare(a, B(("f4", "g")))
    assert r.worst_offenders[0] == ("super", 3)


def test_empty_arms_do_not_divide_by_zero():
    r = D.compare([], [])
    assert r.precision_a == 0.0 and r.jaccard == 0.0


def test_write_report_states_precision(tmp_path):
    r = D.compare(A(("f", "g"), ("f", "h")), B(("f", "g")))
    p = tmp_path / "graph-delta.md"
    D.write_report(r, {"repo": "django"}, p)
    assert "0.5" in p.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_delta.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.delta'`

- [ ] **Step 3: Write `src/friction/delta.py`**

```python
"""Arm A vs arm B — what name matching costs.

Arm B (type-resolved) is treated as the reference. That is a claim, and it is
defensible in exactly one direction: pyright emits NO occurrence when a receiver
is untyped, so arm B under-reports rather than inventing edges. Therefore an
arm-A edge absent from arm B is either a genuine false positive OR a case
pyright declined to resolve; an arm-B edge absent from arm A is a true edge that
name matching missed. Precision is reported as a CEILING and said so.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Delta:
    only_a: int
    only_b: int
    both: int
    precision_a: float
    recall_a: float
    jaccard: float
    worst_offenders: list[tuple[str, int]]


def _target(edge_dst: str) -> str:
    return edge_dst.split("::")[-1].rstrip("().#")


def compare(arm_a, arm_b) -> Delta:
    a = {(e.src, e.dst) for e in arm_a}
    b = {(e.src, e.dst) for e in arm_b if not getattr(e, "dst_external", False)}

    both = len(a & b)
    only_a, only_b = len(a - b), len(b - a)
    precision = both / len(a) if a else 0.0
    recall = both / len(b) if b else 0.0
    union = len(a | b)
    jaccard = both / union if union else 0.0

    offenders = Counter(_target(d) for _, d in (a - b))
    return Delta(
        only_a=only_a, only_b=only_b, both=both,
        precision_a=round(precision, 4), recall_a=round(recall, 4),
        jaccard=round(jaccard, 4),
        worst_offenders=offenders.most_common(20),
    )


def write_report(delta: Delta, extra: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# What name matching costs",
        "",
        "Arm A is a name-matched call graph, built the way the widely-used",
        "repo-graph tools build one. Arm B is type-resolved via scip-python",
        "(pyright). Same repository, same commit, same extraction of definitions.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Arm A edges confirmed by arm B | **{delta.both}** |",
        f"| Arm A edges arm B does not have | **{delta.only_a}** |",
        f"| Arm B edges arm A missed | **{delta.only_b}** |",
        f"| Arm A precision (ceiling) | **{delta.precision_a}** |",
        f"| Arm A recall of arm B | **{delta.recall_a}** |",
        f"| Jaccard | {delta.jaccard} |",
        "",
        "## Where arm A's unconfirmed edges point",
        "",
        "| Target name | Unconfirmed edges |",
        "|---|---|",
    ]
    for name, n in delta.worst_offenders:
        lines.append(f"| `{name}` | {n} |")
    lines += [
        "",
        "## How to read precision",
        "",
        "Arm A precision is a **ceiling**, not a point estimate. pyright emits no",
        "occurrence when a receiver's type is unknown, so arm B under-reports",
        "rather than inventing edges. An arm-A edge missing from arm B is either a",
        "genuine false positive or a case pyright declined to resolve. The direction",
        "of the bias is known and stated; the exact split is not claimed.",
        "",
    ]
    for k, v in extra.items():
        lines.append(f"- {k}: {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_delta.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Run both arms on real django and write the report**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.namematch.graph import build as build_a
from friction.scip.index import index_repo
from friction.scip.schema import load_index
from friction.scip.extract import extract_edges
from friction.delta import compare, write_report

root = Path("data/repos/django")
a, sa = build_a(root)
index_repo(root, Path("/tmp/dj.scip"), name="django", version="4.2", target="django")
b, sb = extract_edges(load_index(Path("/tmp/dj.scip")))
d = compare(a, b)
print(f"arm A {sa}")
print(f"arm B {sb}")
print(f"precision_ceiling={d.precision_a}  recall={d.recall_a}  jaccard={d.jaccard}")
print(f"worst: {d.worst_offenders[:8]}")
write_report(d, {"repo": "django", "arm_a_edges": sa["edges"],
                 "arm_b_internal_edges": sb["internal_edges"]},
             Path("docs/graph-delta.md"))
PY
```

- [ ] **Step 6: THE GATE — read the numbers and decide**

| Result | Action |
|---|---|
| **Arm A precision ceiling ≤ 0.5** | **GO.** Name matching is majority-unconfirmed. This is the headline; continue to Task 7. |
| **0.5 – 0.8** | Real but softer. Keep it as a supporting finding and make Task 10's evaluation the headline instead. |
| **> 0.8** | The delta is small. The headline evaporates — say so in the README, drop the two-arm framing, and make Task 10 the whole project. |

Commit `docs/graph-delta.md` whichever way it goes.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: quantify the name-match vs type-resolved graph delta"
```

---

### Task 7: Build both arms per instance

**Files:**
- Create: `substrate-friction/src/friction/arms.py`
- Create: `substrate-friction/tests/test_arms.py`
- Modify: `substrate-friction/src/friction/build.py` (reuse checkout + test_patch application)

**Interfaces:**
- Consumes: `friction.scip.*`, `friction.namematch.graph`, `friction.build.apply_test_patch`, `friction.loader`.
- Produces:
  - `friction.arms.ArmBands` dataclass: `arm_a: int`, `arm_b: int`
  - `friction.arms.bands_for(idx: int) -> ArmBands` — arm A at `1e10 + idx*1e7`, arm B at `2e10 + idx*1e7`
  - `friction.arms.build_instance(instance, repo_root, idx) -> dict`
  - `friction.arms.emit_arm(edges, band, out_dir) -> dict`

- [ ] **Step 1: Write the failing test**

`tests/test_arms.py`:
```python
import pytest

from friction import arms


def test_bands_are_disjoint_between_arms():
    b = arms.bands_for(0)
    assert b.arm_b - b.arm_a >= 10_000_000_000


def test_bands_are_disjoint_between_instances():
    a, b = arms.bands_for(0), arms.bands_for(1)
    assert b.arm_a - a.arm_a == 10_000_000
    assert b.arm_b - a.arm_b == 10_000_000


def test_bands_clear_every_band_used_by_v1():
    # v1 occupied 1e8..5.9e8, 2.0e9..2.49e9, 3.0e9..3.49e9, 4.0e9..4.49e9,
    # and sweeps at 5e9/6e9/7.1e9/8e9/9e9.
    assert arms.bands_for(0).arm_a >= 10_000_000_000


def test_emit_assigns_contiguous_ids_within_a_band(tmp_path):
    from friction.scip.extract import CallEdge
    edges = [CallEdge("m::f().", "m::g().", False, 2),
             CallEdge("m::g().", "m::h().", False, 1)]
    stats = arms.emit_arm(edges, band=10_000_000_000, out_dir=tmp_path)
    assert stats["nodes"] == 3
    assert stats["edges"] == 2
    ids = [int(l.split('"id": ')[1].split(",")[0])
           for l in (tmp_path / "nodes.ndjson").read_text().splitlines()]
    assert all(10_000_000_000 <= i < 10_010_000_000 for i in ids)


def test_emit_writes_sid_as_a_string(tmp_path):
    import json
    from friction.scip.extract import CallEdge
    arms.emit_arm([CallEdge("m::f().", "m::g().", False, 1)], 10_000_000_000, tmp_path)
    row = json.loads((tmp_path / "nodes.ndjson").read_text().splitlines()[0])
    assert isinstance(row["sid"], str)


def test_emit_is_deterministic(tmp_path):
    from friction.scip.extract import CallEdge
    e = [CallEdge("m::b().", "m::a().", False, 1), CallEdge("m::a().", "m::c().", False, 1)]
    s1 = arms.emit_arm(e, 10_000_000_000, tmp_path / "one")
    s2 = arms.emit_arm(e, 10_000_000_000, tmp_path / "two")
    assert (tmp_path / "one" / "nodes.ndjson").read_text() == \
           (tmp_path / "two" / "nodes.ndjson").read_text()
    assert s1 == s2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_arms.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.arms'`

- [ ] **Step 3: Write `src/friction/arms.py`**

```python
"""Build both graph arms for one SWE-bench instance.

Both arms describe the same repository at the same base commit with the same
test patch applied. They differ ONLY in how a call site is bound to a callee.
Each arm gets its own id band so both can be resident in the single reachable
`default` graph at once and queried independently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ARM_A_BASE = 10_000_000_000
ARM_B_BASE = 20_000_000_000
STRIDE = 10_000_000


@dataclass(frozen=True)
class ArmBands:
    arm_a: int
    arm_b: int


def bands_for(idx: int) -> ArmBands:
    return ArmBands(ARM_A_BASE + idx * STRIDE, ARM_B_BASE + idx * STRIDE)


def emit_arm(edges, band: int, out_dir: Path) -> dict:
    """Assign band-local integer ids and write loader-ready NDJSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    seen: dict[str, int] = {}
    for e in edges:
        for n in (e.src, e.dst):
            if n not in seen:
                seen[n] = len(names)
                names.append(n)

    with (out_dir / "nodes.ndjson").open("w", encoding="utf-8") as fh:
        for n, offset in ((names[i], i) for i in range(len(names))):
            nid = band + offset
            fh.write(json.dumps({
                "label": "Function", "id": nid, "sid": str(nid),
                "name": n.split("::")[-1], "qual": n,
            }) + "\n")

    with (out_dir / "edges.ndjson").open("w", encoding="utf-8") as fh:
        for e in edges:
            fh.write(json.dumps({
                "src": band + seen[e.src], "dst": band + seen[e.dst],
                "type": "CALLS", "weight": int(getattr(e, "weight", 1)),
            }) + "\n")

    return {"nodes": len(names), "edges": len(edges), "band": band}


def build_instance(instance, repo_root: Path, idx: int, out_root: Path) -> dict:
    """Check out the base commit, apply the test patch, build both arms."""
    from friction.build import _checkout, _restore, apply_test_patch
    from friction.namematch.graph import build as build_a
    from friction.scip.extract import extract_edges
    from friction.scip.index import index_repo
    from friction.scip.schema import load_index

    repo_root, out_root = Path(repo_root), Path(out_root)
    bands = bands_for(idx)
    _restore(repo_root)
    _checkout(repo_root, instance.base_commit)
    patched = apply_test_patch(repo_root, instance.test_patch)
    try:
        a_edges, a_stats = build_a(repo_root)
        scip_out = out_root / instance.instance_id / "index.scip"
        index_repo(repo_root, scip_out, name="django",
                   version=instance.base_commit[:12], target="django")
        b_edges, b_stats = extract_edges(load_index(scip_out))
        b_internal = [e for e in b_edges if not e.dst_external]
        a_out = emit_arm(a_edges, bands.arm_a, out_root / instance.instance_id / "arm_a")
        b_out = emit_arm(b_internal, bands.arm_b, out_root / instance.instance_id / "arm_b")
    finally:
        _restore(repo_root)

    return {
        "instance_id": instance.instance_id,
        "base_commit": instance.base_commit,
        "test_patch_applied": patched,
        "arm_a": {**a_out, **a_stats},
        "arm_b": {**b_out, **b_stats},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_arms.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Build one real instance end to end**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.swebench import load_instances
from friction.arms import build_instance
inst = load_instances(repos=["django/django"])[0]
print(build_instance(inst, Path("data/repos/django"), 0, Path("data/instances/arms")))
PY
```

Expected: both arms emitted, `test_patch_applied: True`, and arm B internal edge count in the low thousands. Record the wall clock — multiply by 50 for the full run.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: per-instance two-arm graph construction"
```

---

### Task 8: Load both arms and measure path structure in the engine

**Files:**
- Modify: `substrate-friction/src/friction/harness.py`
- Create: `substrate-friction/tests/test_harness.py`

**Interfaces:**
- Consumes: `friction.loader.load`, `friction.paths.fix_to_test_paths`, `friction.arms.bands_for`.
- Produces:
  - `friction.harness.load_arms(transport, caps, manifest, root) -> dict`
  - `friction.harness.arm_path_stats(transport, caps, settings, record, arm) -> dict` with keys `paths`, `millis`, `truncated`, `answered`
  - `friction.harness.run(...) -> dict`

- [ ] **Step 1: Write the failing test**

`tests/test_harness.py`:
```python
from friction import harness


class Rec:
    name = "rec"

    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []

    def query(self, cypher, params=None):
        self.calls.append((cypher, params))
        return self.rows


def test_load_arms_sends_nodes_before_edges(tmp_path):
    (tmp_path / "arm_a").mkdir(parents=True)
    (tmp_path / "arm_a" / "nodes.ndjson").write_text(
        '{"label":"Function","id":1,"sid":"1","name":"f","qual":"m::f"}\n')
    (tmp_path / "arm_a" / "edges.ndjson").write_text("")
    t = Rec()
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    out = harness.load_arms(t, caps, [{"instance_id": "x"}], tmp_path.parent)
    assert out["loaded"] >= 0


def test_arm_path_stats_marks_unanswered_on_engine_error():
    class Boom:
        name = "boom"

        def query(self, *a, **k):
            from friction.client import EngineError
            raise EngineError("Terminated")

    from friction.config import Settings
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    s = Settings("bolt://x", "http://x", "t", "d", "d", "cell-0", 6, 20, "both", 500)
    out = harness.arm_path_stats(Boom(), caps, s,
                                 {"fix_site_ids": [1], "test_target_ids": [2]}, "arm_a")
    assert out["answered"] is False
    assert out["paths"] == 0


def test_arm_path_stats_returns_zero_for_empty_endpoints():
    from friction.config import Settings
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    s = Settings("bolt://x", "http://x", "t", "d", "d", "cell-0", 6, 20, "both", 500)
    out = harness.arm_path_stats(Rec(), caps, s,
                                 {"fix_site_ids": [], "test_target_ids": [2]}, "arm_a")
    assert out["paths"] == 0 and out["answered"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness.py -v`
Expected: FAIL — `load_arms` / `arm_path_stats` do not exist

- [ ] **Step 3: Implement `load_arms` and `arm_path_stats` in `harness.py`**

```python
def load_arms(transport, caps, manifest, root):
    """Load every instance's arm_a and arm_b NDJSON into the engine."""
    from pathlib import Path

    from friction.loader import load

    root = Path(root)
    loaded, failed = 0, []
    for rec in manifest:
        for arm in ("arm_a", "arm_b"):
            d = root / rec["instance_id"] / arm
            if not (d / "nodes.ndjson").exists():
                continue
            try:
                load(transport, caps, d, batch_size=1000)
                loaded += 1
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                failed.append((rec["instance_id"], arm, str(exc)[:200]))
    return {"loaded": loaded, "failed": failed}


def arm_path_stats(transport, caps, settings, record, arm):
    """Bounded fix->test path structure for one arm of one instance."""
    import time

    from friction.client import EngineError
    from friction.paths import fix_to_test_paths

    fix = record.get("fix_site_ids") or []
    test = record.get("test_target_ids") or []
    if not fix or not test:
        return {"paths": 0, "millis": 0.0, "truncated": False, "answered": True}

    start = time.perf_counter()
    try:
        ps = fix_to_test_paths(transport, caps, settings, fix, test)
    except EngineError as exc:
        return {"paths": 0, "millis": round((time.perf_counter() - start) * 1000, 1),
                "truncated": False, "answered": False, "error": str(exc)[:200]}
    return {"paths": len(ps.paths), "millis": ps.millis,
            "truncated": ps.truncated, "answered": True}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_harness.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Wipe the store, load, and measure**

```bash
docker compose down && rm -rf hydradb-data && mkdir -p hydradb-data/graph hydradb-data/cache
chmod -R 777 hydradb-data && docker compose up -d
until curl -sf http://127.0.0.1:9090/readyz >/dev/null; do sleep 1; done
uv run python -m friction.harness --load --arms
du -sh hydradb-data
```

The store wipe is mandatory, not hygiene: `CLOUD_PROVIDER=local` degrades silently under sustained writes and a degraded store produced a wrong performance conclusion in v1. Stop and report if it passes ~3 GB.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: load both arms and measure per-arm path structure"
```

---

### Task 9: Baselines that must be beaten

Without these, any friction number is uninterpretable. Published context: problem-statement text alone reaches **AUC 0.787** on SWE-bench Verified, and the best combined model reaches **0.841** (arXiv 2604.00594).

**Files:**
- Create: `substrate-friction/src/friction/baselines.py`
- Create: `substrate-friction/tests/test_baselines.py`

**Interfaces:**
- Consumes: `friction.swebench.Instance`, `friction.evaluate.auc`.
- Produces:
  - `friction.baselines.Features` dataclass: `patch_lines: int`, `patch_files: int`, `patch_hunks: int`, `f2p_count: int`, `statement_chars: int`, `statement_has_traceback: bool`
  - `friction.baselines.extract(instance) -> Features`
  - `friction.baselines.table(instances, failed_by_id) -> dict[str, float]` — one AUC per single feature

- [ ] **Step 1: Write the failing test**

`tests/test_baselines.py`:
```python
import pytest

from friction import baselines as B
from friction.swebench import Instance


PATCH = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,4 @@
 x = 1
+y = 2
@@ -20,2 +21,2 @@
-z = 3
+z = 4
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,2 @@
+q = 9
"""


def inst(patch=PATCH, statement="boom", f2p=("t1", "t2")):
    return Instance("i1", "django/django", "abc", statement, patch, "", list(f2p), [])


def test_counts_files_and_hunks():
    f = B.extract(inst())
    assert f.patch_files == 2
    assert f.patch_hunks == 3


def test_counts_changed_lines_not_context():
    assert B.extract(inst()).patch_lines == 4


def test_counts_fail_to_pass():
    assert B.extract(inst()).f2p_count == 2


def test_statement_length_and_traceback_flag():
    f = B.extract(inst(statement="Traceback (most recent call last):\n  File x"))
    assert f.statement_chars > 0
    assert f.statement_has_traceback is True


def test_no_traceback_flag_when_absent():
    assert B.extract(inst(statement="please fix")).statement_has_traceback is False


def test_table_reports_one_auc_per_feature():
    xs = [inst(statement="x" * i, f2p=tuple(f"t{j}" for j in range(i))) for i in range(1, 11)]
    xs = [Instance(f"i{i}", "r", "c", s.problem_statement, s.patch, "", s.fail_to_pass, [])
          for i, s in enumerate(xs)]
    failed = {x.instance_id: (i > 4) for i, x in enumerate(xs)}
    t = B.table(xs, failed)
    assert {"patch_lines", "patch_files", "patch_hunks", "f2p_count",
            "statement_chars"} <= set(t)
    assert all(0.0 <= v <= 1.0 or v != v for v in t.values())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_baselines.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.baselines'`

- [ ] **Step 3: Write `src/friction/baselines.py`**

```python
"""Cheap non-graph predictors of agent failure.

Any structural claim has to clear these. Published context for SWE-bench
Verified: a task-agnostic prior reaches ~0.718 AUC, problem-statement text alone
reaches ~0.787, and the best published combined model reaches 0.841
(arXiv 2604.00594). Patch scope is the strongest simple signal in the
literature: single-file, <5-line fixes solve ~48% of the time while >=3 files or
>100 lines drop below 10% (arXiv 2505.23419).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from unidiff import PatchSet

from friction.evaluate import auc


@dataclass(frozen=True)
class Features:
    patch_lines: int
    patch_files: int
    patch_hunks: int
    f2p_count: int
    statement_chars: int
    statement_has_traceback: bool


def extract(instance) -> Features:
    try:
        ps = PatchSet(instance.patch)
    except Exception:  # noqa: BLE001 — a malformed diff is a zero-scope patch
        ps = []
    files = len(ps)
    hunks = sum(len(pf) for pf in ps)
    changed = sum(
        1 for pf in ps for hunk in pf for ln in hunk if ln.is_added or ln.is_removed
    )
    stmt = instance.problem_statement or ""
    return Features(
        patch_lines=changed,
        patch_files=files,
        patch_hunks=hunks,
        f2p_count=len(instance.fail_to_pass or []),
        statement_chars=len(stmt),
        statement_has_traceback="Traceback (most recent call last)" in stmt,
    )


def table(instances, failed_by_id: dict[str, bool]) -> dict[str, float]:
    rows = [(extract(i), failed_by_id.get(i.instance_id)) for i in instances]
    rows = [(f, y) for f, y in rows if y is not None]
    if not rows:
        return {}
    labels = [y for _, y in rows]
    out: dict[str, float] = {}
    for name in asdict(rows[0][0]):
        values = [float(getattr(f, name)) for f, _ in rows]
        out[name] = auc(values, labels)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_baselines.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: non-graph baselines with published context"
```

---

### Task 10: The honest evaluation

**Files:**
- Modify: `substrate-friction/src/friction/harness.py`
- Create (generated): `substrate-friction/docs/evaluation.md`, `docs/plots/arms.png`

**Interfaces:**
- Consumes: `friction.baselines.table`, `friction.evaluate.*`, `friction.metric.*`, `friction.delta.compare`.
- Produces: `friction.harness.evaluate_arms(rows, failed_by_id) -> dict`

- [ ] **Step 1: Compute friction on BOTH arms for every instance**

For each instance and each arm, run `arm_path_stats` and `friction.metric.raw_components`, normalise within arm, and score with equal weights.

- [ ] **Step 2: Build the comparison table**

Required columns, all on the same instances:

| Predictor | AUC |
|---|---|
| Friction, arm A (name-matched) | — |
| Friction, arm B (type-resolved) | — |
| `patch_lines` | — |
| `patch_files` | — |
| `f2p_count` | — |
| `statement_chars` | — |
| Published: statement text only (arXiv 2604.00594) | 0.787 |
| Published: best combined (arXiv 2604.00594) | 0.841 |

- [ ] **Step 3: Report the three things that decide whether this is a finding**

1. **Does arm B beat arm A?** If a trustworthy graph gives a materially better AUC than a name-matched one, that is the strongest possible evidence that graph quality matters — and it is a *new* claim regardless of the absolute number.
2. **Does either beat `patch_lines`?** If not, structure adds nothing over scope. Say so plainly.
3. **Is the sample big enough to say anything?** With n≈43 and AUC differences under ~0.1, report a bootstrap CI and state that the comparison is underpowered rather than implying significance.

- [ ] **Step 4: Disclose label contamination**

Add a section stating that SWE-Bench+ (arXiv 2410.06992) measured **32.7% solution leakage and 31% weak tests** on SWE-bench, and that OpenAI reports **59.4%** of o3 failures on Verified were test flaws and no longer recommends the benchmark. A structural feature correlating with test weakness would be predicting label noise. This is a limitation of the ground truth, not of the metric, and it must be stated.

- [ ] **Step 5: Retract v1's null explicitly**

`docs/evaluation.md` must open with a retraction: v1 reported AUC 0.565 / p=0.726 as a test of the thesis; that measurement was taken on a graph in which **73.9% of resolved edges were name-collision artifacts**, so it did not test the thesis and is withdrawn. Retracting loudly is worth more than the original claim.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: two-arm evaluation with baselines, contamination disclosure, v1 retraction"
```

---

### Task 11: CLI

**Files:**
- Modify: `substrate-friction/src/friction/cli.py`
- Modify: `substrate-friction/tests/test_cli.py`

**Interfaces:**
- Produces: subcommands `compare`, `delta`, `check`, `eval`, `list`.

- [ ] **Step 1: Make `friction compare` the primary command**

It takes an instance id and prints, side by side, arm A and arm B: node and edge counts, the bounded fix→test path count, the friction score, the Cypher, and the measured latency for each — then the delta between them. The two-arm contrast in one screen is the product.

- [ ] **Step 2: Add `friction delta`**

Prints `docs/graph-delta.md`: precision ceiling, recall, and the worst-offender table led by `super`.

- [ ] **Step 3: Write the tests**

Cover: both arms appear in `compare` output; the Cypher and latency are printed for each; an unanswerable instance renders a clean "engine could not answer" line rather than a fabricated score; `delta` prints the offender table; unknown subcommand returns non-zero; paths resolve from `data/shipped` when `data/instances` is absent (a judge's clean clone only has the former).

- [ ] **Step 4: Run and commit**

```bash
uv run pytest tests/test_cli.py -v -m "not engine"
uv run friction compare --issue django__django-11138
git add -A && git commit -m "feat(cli): two-arm compare as the primary command"
```

---

### Task 12: Visualization

**Files:**
- Modify: `substrate-friction/src/friction/viz.py`
- Modify: `substrate-friction/tests/test_viz.py`

- [ ] **Step 1: Build `docs/plots/arms.png` — the money shot**

One instance, two panels, identical layout seed: the fix→test neighbourhood as arm A sees it, beside the same neighbourhood as arm B sees it. Colour arm-A edges **unconfirmed** (red) vs **confirmed** (grey). The red mass is the finding, visible without reading a number.

- [ ] **Step 2: Build `docs/plots/offenders.png`**

Horizontal bar chart of the worst offenders, `super` first with its real count. One glance, one number, one culprit.

- [ ] **Step 3: Tests and commit**

Assert both figures are written, are non-empty, and that the arm-A panel contains strictly more edges than the confirmed subset. Then commit.

---

### Task 13: Setup and shipped data

**Files:**
- Modify: `substrate-friction/setup.sh`, `docker-compose.yml`, `data/shipped/`

- [ ] **Step 1: Ship both arms pre-built**

A judge must never run `scip-python` or tree-sitter over django. Ship `arm_a` and `arm_b` NDJSON per instance, gzipped, with the manifest and the cached outcome labels. Keep the payload under ~50 MB and report the real size.

- [ ] **Step 2: Make `setup.sh` load both arms and warm the cache**

It must create the data dirs, write the dev token, `chmod` for UID 10001, bring the stack up, wait for `/readyz`, `uv sync`, install the package editable (the console script is dead otherwise), run the capability probe, load the shipped arms, and warm one query.

- [ ] **Step 3: Time it from a clean clone in a temp dir and report the real number**

```bash
rm -rf /tmp/cc && git clone -q --branch main . /tmp/cc && cd /tmp/cc && time ./setup.sh
```

Report the measured seconds honestly. v1 took ~125s, dominated by graph load with a 1024-row batch cap; do not claim under 60s unless it is.

- [ ] **Step 4: Commit**

---

### Task 14: README and video

**Files:**
- Modify: `substrate-friction/README.md`, `docs/video-script.md`

- [ ] **Step 1: Lead with the substrate finding**

> Aider's repo map, RepoGraph, and LocAgent all build their code graphs by matching identifier **names**. We measured what that costs on django: **X% of a name-matched graph's edges are unconfirmed by type resolution**, and a single builtin — `super()` — accounts for **1,321** false edges into one template method. Here is the same repository, same commit, resolved properly.

- [ ] **Step 2: Be explicit about what is and is not novel**

State plainly that per-instance agent-failure prediction is **already solved** — cite arXiv 2604.00594 (AUC 0.841) and the 0.787 text-only baseline — and that the contribution here is the **substrate**: the first two-arm measurement of what name-matched code graphs cost, plus an honest re-test of the structural thesis on a trustworthy graph. Claiming the prediction problem would be dishonest and instantly checkable.

- [ ] **Step 3: Write "How HydraDB is used"**

`algo.MSpaths` with `pairwise: true` computes all fix-site × test-target bounded paths in one server-side round trip, per arm, with the real Cypher and measured latency. `algo.SSpaths` with an integer `sourceNode` gives fan-in. Both arms resident simultaneously in disjoint id bands is what makes the comparison a single-engine operation. State honestly how many instances the engine answered at `maxLen 6`. Explain why a vector index cannot do this: the quantity compared is *the set of paths between two node sets*, and paths do not exist in a vector space.

- [ ] **Step 4: Limitations**

Arm B under-reports on untyped receivers (so precision is a ceiling); dynamic dispatch is invisible to both arms; Python only; `maxLen 6` bound; label contamination; n≈43 is underpowered for small AUC differences; single repository.

- [ ] **Step 5: Contributions back to the engine**

One short section linking [#81](https://github.com/hydra-db/hydradb/issues/81) and [#82](https://github.com/hydra-db/hydradb/pull/82). Keep it to a few lines — it is a credibility signal, not the story.

- [ ] **Step 6: Video script, ≤ 3:00**

| Time | Content |
|---|---|
| 0:00–0:25 | **Problem.** "Every AI coding agent that reads your repo builds a graph of it first. We checked whether that graph is real." |
| 0:25–0:45 | **What we built.** Two graphs of the same commit — name-matched, and type-resolved — both live in HydraDB. |
| 0:45–1:20 | **Money shot.** `friction compare`. Same neighbourhood, two panels. The red edges are the ones type resolution cannot confirm. `super()` alone: 1,321 of them, all pointing at one template method. |
| 1:20–1:50 | **Evidence.** Precision ceiling, the offender table, and the AUC comparison against patch-scope and published text baselines. |
| 1:50–2:30 | **Why HydraDB.** `algo.MSpaths` pairwise, both arms resident at once, real Cypher and real milliseconds on screen. |
| 2:30–3:00 | **Honest limits.** What we retracted from v1 and why. Repo link. Stop. |

- [ ] **Step 7: Pre-submission checklist and commit**

Public repo; OSI LICENSE; no participant commit before 2026-08-12; clean-clone `setup.sh` on another machine; every link checked in an incognito window; video under 3:00; form `forms.gle/GrMYKxLj9zPQcqqc8`.

---

## Self-Review

**1. Spec coverage.** The original build spec maps as follows. Part 2 (data) → Task 9 + reused `swebench.py`. Part 3 (model) → Tasks 3, 4, 7. Part 4 (ingest) → Tasks 7, 8. Part 5 (metric) → reused `metric.py`, applied per arm in Task 10. Part 6 (go/no-go) → **relocated to Task 6**, because the binding question is no longer "does friction correlate" but "is the graph real" — a null on a fake graph is not a result, which is exactly what v1 proved. Part 7 (product) → Tasks 11–14. Part 9 (Common Cause pivot) → **dropped, with cause**: it was tried and its top result was `loader_tags.py::super` at 21/36 instances, the same artifact, so it inherits the substrate defect and is not a safe pivot. Part 10 (failure modes) → Global Constraints + Task 6 gate. Part 12 (anti-goals) → Global Constraints.

**Deliberate departures from the spec:** (a) the thesis is demoted from headline to a re-test, because the problem is already solved at AUC 0.841 and claiming it would be desk-rejected; (b) `algo.MSpaths` remains central but now serves a *comparison* between two graphs rather than a single score; (c) tree-sitter is retained as the control arm, not the production path.

**2. Placeholder scan.** Tasks 11–14 give exact files, commands, required content and acceptance criteria but not full code bodies, because they modify existing v1 modules whose current contents the implementer will read. Tasks 1–10 — everything novel — carry complete code. The one data-dependent residue is the arm-A precision figure in Task 14 Step 1, which is written as `X%` because Task 6 measures it; the gate table in Task 6 defines what each possible value means.

**3. Type consistency.** `CallEdge(src, dst, dst_external, weight)` is used identically in `extract`, `delta`, and `arms`. `NameEdge(src, dst, weight, rule)` likewise. `Sym` and `canonical()` are consumed only by `extract`. `Delta` fields match between `compare` and `write_report`. `bands_for` returns `ArmBands` in both `arms` and `harness`. `Capabilities` is constructed with all nine fields in the test fixtures, matching the v1 dataclass after the Task 3b correction.

---

## What the research changed, in one place

- **`scip-python` is the unlock**, verified by running it: django indexed in 24.3s, no dependency installs, 12,499 project→project edges, 81.3% caller coverage, and `super`/`str.lower` correctly resolved to `builtins`. ([scip-python](https://github.com/sourcegraph/scip-python), [SCIP schema](https://github.com/sourcegraph/scip))
- **Dynamic tracing was rejected on measurement, not vibes**: overhead is fine (~1.2× on real django tests) but SWE-bench's images are amd64-only with no arm64 path, django instances span 1.11→5.0 so `sys.monitoring` (3.12+) is unusable for ~108 of them, and two whole test modules exercised only 32.8% of functions. Keep it as a spot-check validator on django 4.2/5.0 instances only.
- **The prediction problem is solved**: arXiv [2604.00594](https://arxiv.org/html/2604.00594) reaches AUC 0.841; text alone 0.787; a task-agnostic prior ~0.718. Our v1 number of 0.565 was below all of them.
- **Nobody has measured name-match cost**, and everyone relies on it — [Aider repo map](https://aider.chat/2023/10/22/repomap.html), [RepoGraph](https://arxiv.org/abs/2410.14684), [LocAgent](https://arxiv.org/abs/2503.09089). That gap is the project.
- **The labels are contaminated**: [SWE-Bench+](https://arxiv.org/pdf/2410.06992) found 32.7% solution leakage and 31% weak tests; [OpenAI no longer recommends SWE-bench Verified](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/) after finding 59.4% of o3 failures were test flaws.
- **A reviewer's first objection is answered in advance**: [ARISE](https://arxiv.org/html/2605.03117) found def-use slices beat call-graph topology for localization, so the README must justify call-graph structure rather than assume it.

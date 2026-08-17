# Substrate Friction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working triage gate that computes a graph-structural "friction" score for a software issue and predicts whether an AI coding agent will fail on it — with the correlation measured honestly against real SWE-bench outcomes, running on the self-hosted open-source HydraDB engine.

**Architecture:** An offline Python pipeline parses Python repositories with tree-sitter into a symbol graph (Functions, Classes, Files, Tests) and loads it into HydraDB over Bolt using `UNWIND $rows` batches. At query time, `algo.MSpaths` computes all bounded paths between an instance's fix sites and its test targets in one server-side round trip; six friction components are computed client-side from those paths. An evaluation harness scores the metric against published per-instance SWE-bench outcomes (AUC + point-biserial + three confound checks), and a CLI renders the gate decision, the Cypher, and the timing.

**Tech Stack:** Python 3.11+, `uv`, pytest, tree-sitter + tree-sitter-python, neo4j Bolt driver, httpx, unidiff, datasets (HuggingFace), networkx, scikit-learn, scipy, matplotlib, Docker (HydraDB `ghcr.io/hydra-db/hydradb:latest` + MinIO).

---

## Global Constraints

Every task's requirements implicitly include this section.

**Engine — hard limits (violations are parse errors):**
- Node matching is **integer `id` only**. Names are properties, never match keys. Maintain a `symbol name → int id` dictionary in the parser.
- `WHERE` supports only `=`, `<>`, `<`, `>`, `<=`, `>=`, `STARTS WITH`. **No `IN`, `CONTAINS`, `ENDS WITH`, `IS NULL`.**
- **`RETURN *` unsupported.** Aggregates: `count`, `sum`, `avg`, `collect`, `count(*)` only. **No `min`, no `max`, no `DISTINCT` in an aggregate argument.**
- `MERGE` is id-only, no `ON CREATE`/`ON MATCH`. Vertex upsert must be **`MERGE` by id followed by `SET`** — folding extra properties into the MERGE pattern is rejected.
- `WITH` is **pass-through only** — no projection, no aliasing.
- Variable-length paths require a **mandatory upper bound**. `*1..3` valid; `*` and `*1..` rejected. Not allowed in `CREATE`/`MERGE`.
- Relationship patterns are **directed and single-typed**. No `[:CALLS|IMPORTS*..3]`.
- **One statement per request.** No multi-statement transactions.
- Property values: **int, float, bool, string only.** All time is integer epochs.
- `UNWIND` input must be **a parameter holding a list of maps**, not an inline list. One relationship pattern per batch, one hop, directed. `UNWIND MATCH` takes no `OPTIONAL`/hints/`WHERE` and must end in `RETURN` or `DELETE`. `UNWIND … CREATE` cannot be followed by another clause. Accepted via client transport only — the in-process shard API rejects `UNWIND`.
- `algo.*` config keys: `sourceNode`, `targetNode`, `sourceLabel`, `sourceProperty`, `sourceValues`, `targetLabel`, `targetProperty`, `targetValues`, `relTypes`, `relDirection`, `maxLen`, `pathCount`. Setting `targetLabel` or `targetProperty` **requires `targetValues`**. Yieldable columns: `path`, `pathWeight`, `pathCost` — `RETURN` may only reference yielded columns.

**Engine — operational:**
- `export RUST_MIN_STACK=33554432` or the node serves `/readyz` then aborts on the first query.
- Local env vars: `CLOUD_PROVIDER=local`, `LOCAL_PATH` (must already exist), `GRAPH_NAMESPACE`, `GRAPH_ID`, `GRAPH_CELL_ID`, `GRAPH_CELLS`, `GRAPH_NODE_ID`, `GRAPH_BOLT_NODE_ADDRESSES`, `GRAPH_ADVERTISED_BOLT_ADDR`, `GRAPH_DATA_CACHE_DIR`, `GRAPH_AUTH_TOKEN_FILE`, `GRAPH_ALLOW_PLAINTEXT=true`.
- Docker image `ghcr.io/hydra-db/hydradb:latest`, run with `--user "$(id -u):$(id -g)"` (image runs as UID/GID 10001). Ports: Bolt `7687`, HTTP `8443`, admin `9090`.
- HTTP query: `POST /v1/graphs/{graph}/query`, headers `Authorization: Bearer $TOKEN` and `X-Graph-Namespace`, body `{"cell_id": "cell-0", "query": "..."}`.
- Demo against **local MinIO with a warm cache** — the same cold query from a laptop to real S3 measured ~27 seconds.
- `main` is force-pushed frequently. **Pin a commit hash and record it in the README.**
- Beyond ~3 hops traversal tends toward the whole connected component. **Bound `maxLen` at 5 or 6 and justify it.**

**Project rules:**
- **Six friction components. Six, then freeze.** No seventh.
- Python only. Say so in the README.
- Never use the hosted product at `api.hydradb.com`.
- Do not try to beat LocAgent's 92.7% localization. This project predicts failure; it does not do retrieval.
- Do not hand-tune weights and present the fit as a discovery. Fit on a train split, report on a held-out split.
- Do not hide a negative result.

**Submission rules:**
- Public GitHub repo, OSI-approved LICENSE in root, **no participant-authored commits before 2026-08-12**.
- Submission form: **`forms.gle/GrMYKxLj9zPQcqqc8`** (from the official participant guide, pages 8 and 12 — the `WEwqEmmN7Bkp4HyJ6` URL in the earlier context brief is wrong).
- Deadline 2026-08-20, 11:59 PM PT. Demo video **≤ 3:00 hard stop**, order: problem → project → demo → HydraDB.
- **Track 02A and 02B are judged as ONE track** (participant guide p.6: "Choose A or B — pick one direction and finish it. Both are judged on the same track."). This project is ranked against supply-chain blast-radius entries too. Differentiation, not field size, is the edge — the README and video must make the inverted question legible in the first 25 seconds.

---

## Research Findings That Change the Spec

Three corrections established by reading `cypher-compat.md` and the engine README directly. **These are why Task 3 exists and must run before any query code is written.**

1. **`pairwise` is undocumented.** `cypher-compat.md` lists every `algo.*` config key and `pairwise` is not among them. The spec calls `pairwise: true` "the heart of this project." It may not exist. Task 3 probes it; Task 10 ships a fallback that computes friction from set-to-set `MSpaths` output, which is what the metric actually needs.
2. **`relDirection` casing is `'both'`, lowercase**, in the only documented example. The spec writes `'BOTH'` and `'INCOMING'`. Task 3 probes all casings.
3. **The spec's edge loader may not parse.** `cypher-compat.md` says `UNWIND MATCH` "must end in `RETURN` or `DELETE`" and `UNWIND … CREATE` "cannot be followed by another clause," with "one relationship pattern per batch, one hop, directed." The spec's `UNWIND / MATCH / MATCH / CREATE` edge form contradicts this. Task 3 probes four candidate forms and Task 9 uses whichever parses.

---

## File Structure

```
substrate-friction/
├── LICENSE                        MIT (our code); credits AGPL-3.0 engine
├── README.md                      the 10 required sections
├── pyproject.toml                 deps + console script
├── justfile                       our recipes (not the engine's)
├── docker-compose.yml             graph-node + MinIO + loader
├── setup.sh                       one command to a working `friction check`
├── .gitignore
├── docs/
│   ├── engine-capabilities.md     GENERATED by Task 3 — the probe's verdict
│   └── throughput.md              GENERATED by Task 4
├── data/
│   ├── swebench/                  dataset cache (gitignored)
│   ├── graphs/                    NDJSON node/edge batches (gitignored)
│   ├── instances/                 per-instance annotation side-table
│   └── shipped/                   pre-parsed graph committed for judges
├── src/friction/
│   ├── __init__.py
│   ├── config.py                  connection + engine settings from env
│   ├── client.py                  HydraDB transport (Bolt + HTTP)
│   ├── probe.py                   capability probe → engine-capabilities.md
│   ├── throughput.py              ingest measurement
│   ├── swebench.py                dataset + published outcome labels
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── symbols.py             tree-sitter symbol extraction
│   │   ├── calls.py               call resolution → CALLS edges
│   │   ├── covers.py              Test → Function COVERS derivation
│   │   └── patches.py             gold patch diff → fix-site function ids
│   ├── loader.py                  NDJSON → HydraDB
│   ├── paths.py                   MSpaths / SSpaths wrappers
│   ├── fidelity.py                networkx cross-check (truncation guard)
│   ├── metric.py                  F1–F6 + composite score
│   ├── evaluate.py                AUC, point-biserial, confounds, weights
│   ├── viz.py                     high- vs low-friction subgraph render
│   └── cli.py                     `friction check`, `friction eval`
└── tests/
    ├── conftest.py
    ├── test_client.py
    ├── test_probe.py
    ├── test_swebench.py
    ├── test_symbols.py
    ├── test_calls.py
    ├── test_covers.py
    ├── test_patches.py
    ├── test_loader.py
    ├── test_paths.py
    ├── test_fidelity.py
    ├── test_metric.py
    ├── test_evaluate.py
    └── test_cli.py
```

**Decomposition rationale:** `parsing/` is split by responsibility because each stage has a distinct failure mode a reviewer can judge independently (symbol extraction is testable on fixture source; call resolution is where dynamic dispatch bites; patch mapping is line-range arithmetic). `paths.py` is separated from `metric.py` so the metric is a pure function over path data and can be unit-tested without a running engine — this is what keeps the go/no-go honest and fast to iterate.

---

## Task Sequencing and the Decision Gate

Tasks 1–4 are foundation. Tasks 5–9 build data. Tasks 10–12 build the measurement. **Task 13 is the GO/NO-GO gate.** Tasks 14–18 are the product and only run on GO. Task 19 is the pivot and only runs on NO-GO.

Do not reorder. Do not build the CLI before Task 13.

---

### Task 1: Repository skeleton, license, and test harness

**Files:**
- Create: `substrate-friction/pyproject.toml`
- Create: `substrate-friction/LICENSE`
- Create: `substrate-friction/.gitignore`
- Create: `substrate-friction/src/friction/__init__.py`
- Create: `substrate-friction/src/friction/config.py`
- Create: `substrate-friction/tests/conftest.py`
- Create: `substrate-friction/tests/test_config.py`
- Create: `substrate-friction/justfile`

**Interfaces:**
- Consumes: nothing.
- Produces: `friction.config.Settings` dataclass with fields `bolt_uri: str`, `http_url: str`, `token: str`, `namespace: str`, `graph: str`, `cell_id: str`, `max_len: int`, `path_count: int`, `rel_direction: str`, and classmethod `Settings.from_env() -> Settings`. Every later task reads connection settings through this.

- [ ] **Step 1: Create the directory and initialise git**

```bash
mkdir -p /Users/cruzer/Desktop/Hackathon/substrate-friction
cd /Users/cruzer/Desktop/Hackathon/substrate-friction
git init
mkdir -p src/friction/parsing tests docs data/swebench data/graphs data/instances data/shipped
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "substrate-friction"
version = "0.1.0"
description = "Predict AI coding agent failure from code graph structure, on HydraDB"
requires-python = ">=3.11"
dependencies = [
    "neo4j>=5.28",
    "httpx>=0.27",
    "tree-sitter>=0.23",
    "tree-sitter-python>=0.23",
    "unidiff>=0.7.5",
    "datasets>=2.20",
    "networkx>=3.3",
    "scikit-learn>=1.5",
    "scipy>=1.14",
    "matplotlib>=3.9",
    "rich>=13.7",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-timeout>=2.3"]

[project.scripts]
friction = "friction.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/friction"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["engine: requires a running HydraDB node"]
timeout = 300
```

- [ ] **Step 3: Write `LICENSE` (MIT) and `.gitignore`**

`LICENSE` — standard MIT text with `Copyright (c) 2026 Substrate Friction contributors`.

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.pytest_cache/
data/swebench/
data/graphs/
data/instances/
hydradb-data/
*.egg-info/
docs/plots/
```

- [ ] **Step 4: Write the failing test**

`tests/test_config.py`:
```python
import os
from friction.config import Settings


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("HYDRA_BOLT_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("HYDRA_TOKEN", "local-development-token-32-bytes")
    monkeypatch.setenv("HYDRA_MAX_LEN", "6")
    s = Settings.from_env()
    assert s.bolt_uri == "bolt://127.0.0.1:7687"
    assert s.token == "local-development-token-32-bytes"
    assert s.max_len == 6


def test_from_env_has_defaults(monkeypatch):
    for key in ("HYDRA_BOLT_URI", "HYDRA_HTTP_URL", "HYDRA_NAMESPACE",
                "HYDRA_GRAPH", "HYDRA_CELL_ID", "HYDRA_MAX_LEN"):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert s.http_url == "http://127.0.0.1:8443"
    assert s.namespace == "default"
    assert s.graph == "default"
    assert s.cell_id == "cell-0"
    assert s.max_len == 6
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction'`

- [ ] **Step 6: Write `src/friction/__init__.py` and `src/friction/config.py`**

`src/friction/__init__.py`:
```python
"""Substrate Friction — predict coding-agent failure from code graph structure."""

__version__ = "0.1.0"
```

`src/friction/config.py`:
```python
"""Connection and engine settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bolt_uri: str
    http_url: str
    token: str
    namespace: str
    graph: str
    cell_id: str
    max_len: int
    path_count: int
    rel_direction: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bolt_uri=os.environ.get("HYDRA_BOLT_URI", "bolt://127.0.0.1:7687"),
            http_url=os.environ.get("HYDRA_HTTP_URL", "http://127.0.0.1:8443"),
            token=os.environ.get("HYDRA_TOKEN", "local-development-token-32-bytes"),
            namespace=os.environ.get("HYDRA_NAMESPACE", "default"),
            graph=os.environ.get("HYDRA_GRAPH", "default"),
            cell_id=os.environ.get("HYDRA_CELL_ID", "cell-0"),
            max_len=int(os.environ.get("HYDRA_MAX_LEN", "6")),
            path_count=int(os.environ.get("HYDRA_PATH_COUNT", "20")),
            rel_direction=os.environ.get("HYDRA_REL_DIRECTION", "both"),
        )
```

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS, 2 passed

- [ ] **Step 8: Write the `justfile`**

```makefile
default:
    @just --list

install:
    uv sync --extra dev

test:
    uv run pytest -v -m "not engine"

test-engine:
    uv run pytest -v -m engine

probe:
    uv run python -m friction.probe

up:
    docker compose up -d
    @echo "waiting for readiness..."
    @until curl -sf http://127.0.0.1:9090/readyz >/dev/null; do sleep 1; done
    @echo "ready"

down:
    docker compose down -v
```

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: repository skeleton, license, settings, test harness"
```

---

### Task 2: HydraDB node running locally with a verified write round-trip

**Files:**
- Create: `substrate-friction/docker-compose.yml`
- Create: `substrate-friction/src/friction/client.py`
- Create: `substrate-friction/tests/test_client.py`

**Interfaces:**
- Consumes: `friction.config.Settings`.
- Produces:
  - `friction.client.HttpTransport(settings)` with `.query(cypher: str, params: dict | None = None) -> list[dict]`
  - `friction.client.BoltTransport(settings)` with `.query(cypher: str, params: dict | None = None) -> list[dict]` and `.close() -> None`
  - `friction.client.connect(settings, prefer: str = "bolt") -> HttpTransport | BoltTransport`
  - `friction.client.EngineError(Exception)` raised with the engine's own message text.

- [ ] **Step 1: Write `docker-compose.yml`**

Note: `LOCAL_PATH` must point at a directory that already exists, and the image runs as UID/GID 10001, so the bind mount is created and chowned by `setup.sh` in Task 17. For now create it by hand.

```yaml
services:
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: ["./minio-data:/data"]
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 3s
      timeout: 2s
      retries: 30

  graph-node:
    image: ghcr.io/hydra-db/hydradb:latest
    user: "10001:10001"
    depends_on:
      minio: { condition: service_started }
    environment:
      RUST_MIN_STACK: "33554432"
      CLOUD_PROVIDER: "local"
      LOCAL_PATH: "/data/graph"
      GRAPH_NAMESPACE: "default"
      GRAPH_ID: "default"
      GRAPH_CELL_ID: "cell-0"
      GRAPH_CELLS: "1"
      GRAPH_NODE_ID: "node-0"
      GRAPH_BOLT_NODE_ADDRESSES: "0.0.0.0:7687"
      GRAPH_ADVERTISED_BOLT_ADDR: "127.0.0.1:7687"
      GRAPH_DATA_CACHE_DIR: "/data/cache"
      GRAPH_AUTH_TOKEN_FILE: "/run/secrets/token"
      GRAPH_ALLOW_PLAINTEXT: "true"
    ports: ["7687:7687", "8443:8443", "9090:9090"]
    volumes:
      - "./hydradb-data:/data"
      - "./secrets/token:/run/secrets/token:ro"
```

- [ ] **Step 2: Bring the node up by hand and confirm readiness**

```bash
mkdir -p hydradb-data/graph hydradb-data/cache minio-data secrets
printf 'local-development-token-32-bytes' > secrets/token
sudo chown -R 10001:10001 hydradb-data
docker compose up -d
curl -sf http://127.0.0.1:9090/readyz && echo READY
```

Expected: `READY`. If the container exits instead, check `docker compose logs graph-node` for a stack abort — that means `RUST_MIN_STACK` did not take.

- [ ] **Step 3: Confirm a real write round-trip with curl before writing any client code**

```bash
TOKEN='local-development-token-32-bytes'
curl -sS http://127.0.0.1:8443/v1/graphs/default/query \
  -H "Authorization: Bearer $TOKEN" -H 'X-Graph-Namespace: default' \
  -H 'Content-Type: application/json' \
  --data '{"cell_id":"cell-0","query":"CREATE (a {id: 1})-[:FOLLOWS]->(b {id: 2})"}'

curl -sS http://127.0.0.1:8443/v1/graphs/default/query \
  -H "Authorization: Bearer $TOKEN" -H 'X-Graph-Namespace: default' \
  -H 'Content-Type: application/json' \
  --data '{"cell_id":"cell-0","query":"MATCH (a {id: 1})-[:FOLLOWS]->(b) RETURN b.id AS id"}'
```

Expected: the read returns one row containing the value `2`. A listening port is not proof; a completed round-trip is.

- [ ] **Step 4: Write the failing test**

`tests/test_client.py`:
```python
import pytest
from friction.config import Settings
from friction.client import HttpTransport, BoltTransport, connect, EngineError


@pytest.mark.engine
def test_http_round_trip():
    t = HttpTransport(Settings.from_env())
    t.query("CREATE (a {id: 9001})-[:PROBE]->(b {id: 9002})")
    rows = t.query("MATCH (a {id: 9001})-[:PROBE]->(b) RETURN b.id AS id")
    assert any(9002 in row.values() for row in rows)


@pytest.mark.engine
def test_bolt_round_trip():
    t = BoltTransport(Settings.from_env())
    try:
        t.query("CREATE (a {id: 9003})-[:PROBE]->(b {id: 9004})")
        rows = t.query("MATCH (a {id: 9003})-[:PROBE]->(b) RETURN b.id AS id")
        assert any(9004 in row.values() for row in rows)
    finally:
        t.close()


@pytest.mark.engine
def test_engine_error_carries_engine_message():
    t = HttpTransport(Settings.from_env())
    with pytest.raises(EngineError) as exc:
        t.query("MATCH (a) RETURN *")
    assert str(exc.value)


@pytest.mark.engine
def test_connect_prefers_bolt_and_falls_back():
    t = connect(Settings.from_env(), prefer="bolt")
    assert t.query("RETURN 1 AS one")
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py -v -m engine`
Expected: FAIL with `ImportError: cannot import name 'HttpTransport' from 'friction.client'`

- [ ] **Step 6: Write `src/friction/client.py`**

```python
"""Transports for the open-source HydraDB engine.

Two transports exist because they have different capabilities:

* HTTP is the documented, certain path (`POST /v1/graphs/{graph}/query` with a
  Bearer token). Whether it accepts a `params` object is established by the
  capability probe in Task 3.
* Bolt is required for `UNWIND $rows`, whose input "has to be a parameter
  holding a list of maps" and which is "only accepted via client transport".
"""

from __future__ import annotations

from typing import Any

import httpx
from neo4j import GraphDatabase, basic_auth, bearer_auth

from friction.config import Settings


class EngineError(RuntimeError):
    """Raised with the engine's own error text, unmodified."""


class HttpTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=120.0)

    @property
    def name(self) -> str:
        return "http"

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        body: dict[str, Any] = {"cell_id": self.settings.cell_id, "query": cypher}
        if params is not None:
            body["params"] = params
        resp = self._client.post(
            f"{self.settings.http_url}/v1/graphs/{self.settings.graph}/query",
            headers={
                "Authorization": f"Bearer {self.settings.token}",
                "X-Graph-Namespace": self.settings.namespace,
                "Content-Type": "application/json",
            },
            json=body,
        )
        if resp.status_code >= 400:
            raise EngineError(resp.text.strip())
        payload = resp.json()
        if isinstance(payload, dict) and "rows" in payload:
            return list(payload["rows"])
        if isinstance(payload, list):
            return payload
        return [payload]

    def close(self) -> None:
        self._client.close()


class BoltTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._driver = None
        last: Exception | None = None
        for auth in (bearer_auth(settings.token),
                     basic_auth("neo4j", settings.token),
                     None):
            try:
                driver = GraphDatabase.driver(settings.bolt_uri, auth=auth)
                driver.verify_connectivity()
                self._driver = driver
                self._auth_mode = type(auth).__name__ if auth else "none"
                break
            except Exception as exc:  # noqa: BLE001 - probing auth modes
                last = exc
        if self._driver is None:
            raise EngineError(f"could not open Bolt session: {last}")

    @property
    def name(self) -> str:
        return "bolt"

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        try:
            with self._driver.session() as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except Exception as exc:  # noqa: BLE001 - surface engine text verbatim
            raise EngineError(str(exc)) from exc

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()


def connect(settings: Settings, prefer: str = "bolt"):
    """Return a working transport, preferring `prefer`, falling back to the other."""
    order = [BoltTransport, HttpTransport] if prefer == "bolt" else [HttpTransport, BoltTransport]
    last: Exception | None = None
    for cls in order:
        try:
            transport = cls(settings)
            transport.query("RETURN 1 AS one")
            return transport
        except Exception as exc:  # noqa: BLE001 - transport selection
            last = exc
    raise EngineError(f"no usable transport: {last}")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py -v -m engine`
Expected: PASS, 4 passed

- [ ] **Step 8: Pin the engine commit**

```bash
docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
  ghcr.io/hydra-db/hydradb:latest | tee docs/pinned-engine-commit.txt
```

If the label is empty, clone the repo and record `git rev-parse HEAD` instead. Write the value into `docs/pinned-engine-commit.txt` — Task 18 copies it into the README.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: docker compose stack and HydraDB transports with verified round-trip"
```

---

### Task 3: Engine capability probe — the keystone

Everything downstream depends on knowing exactly which Cypher forms parse. This task answers that empirically and writes the answers to a file the later tasks read.

**Files:**
- Create: `substrate-friction/src/friction/probe.py`
- Create: `substrate-friction/tests/test_probe.py`
- Create (generated): `substrate-friction/docs/engine-capabilities.md`

**Interfaces:**
- Consumes: `friction.client.connect`, `friction.client.EngineError`, `friction.config.Settings`.
- Produces:
  - `friction.probe.ProbeResult` dataclass: `name: str`, `ok: bool`, `detail: str`, `statement: str`
  - `friction.probe.run_all(transport) -> list[ProbeResult]`
  - `friction.probe.Capabilities` dataclass: `rel_direction_both: str`, `rel_direction_incoming: str`, `pairwise_supported: bool`, `node_loader_form: str`, `edge_loader_form: str`, `http_params_supported: bool`
  - `friction.probe.derive(results) -> Capabilities`
  - `friction.probe.write_report(results, caps, path) -> None`
  - `friction.probe.load_capabilities(path) -> Capabilities` — read back by Tasks 9 and 10.

- [ ] **Step 1: Write the failing test**

`tests/test_probe.py`:
```python
import pytest
from friction import probe


class FakeTransport:
    """Accepts only the forms we declare legal; raises EngineError otherwise."""

    name = "fake"

    def __init__(self, legal: set[str]):
        self.legal = legal
        self.seen: list[str] = []

    def query(self, cypher, params=None):
        self.seen.append(cypher)
        for fragment in self.legal:
            if fragment in cypher:
                return [{"ok": 1}]
        from friction.client import EngineError
        raise EngineError("parse error near token")


def test_derive_picks_lowercase_both_when_only_it_parses():
    results = [
        probe.ProbeResult("rel_direction:both", True, "", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:incoming", True, "", "..."),
        probe.ProbeResult("rel_direction:INCOMING", False, "parse error", "..."),
        probe.ProbeResult("pairwise", False, "unknown config key", "..."),
        probe.ProbeResult("node_loader:create_inline", True, "", "..."),
        probe.ProbeResult("edge_loader:match_match_create", False, "parse error", "..."),
        probe.ProbeResult("edge_loader:merge_then_create", True, "", "..."),
        probe.ProbeResult("http_params", True, "", "..."),
    ]
    caps = probe.derive(results)
    assert caps.rel_direction_both == "both"
    assert caps.rel_direction_incoming == "incoming"
    assert caps.pairwise_supported is False
    assert caps.node_loader_form == "create_inline"
    assert caps.edge_loader_form == "merge_then_create"


def test_derive_raises_when_no_direction_parses():
    results = [
        probe.ProbeResult("rel_direction:both", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
    ]
    with pytest.raises(probe.ProbeFailure):
        probe.derive(results)


def test_run_all_records_failures_without_raising():
    t = FakeTransport(legal={"relDirection: 'both'"})
    results = probe.run_all(t)
    assert any(r.ok for r in results)
    assert any(not r.ok for r in results)


def test_write_and_load_round_trip(tmp_path):
    caps = probe.Capabilities(
        rel_direction_both="both", rel_direction_incoming="incoming",
        pairwise_supported=False, node_loader_form="create_inline",
        edge_loader_form="merge_then_create", http_params_supported=True,
    )
    path = tmp_path / "engine-capabilities.md"
    probe.write_report([probe.ProbeResult("x", True, "", "y")], caps, path)
    assert probe.load_capabilities(path) == caps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_probe.py -v`
Expected: FAIL with `AttributeError: module 'friction.probe' has no attribute 'ProbeResult'`

- [ ] **Step 3: Write `src/friction/probe.py`**

```python
"""Empirically establish which Cypher forms this engine build actually accepts.

`cypher-compat.md` documents the config keys for the `algo.*` procedures but
does NOT document `pairwise`, and shows `relDirection` only as lowercase
`'both'`. It also states restrictions ("UNWIND MATCH must end in RETURN or
DELETE", "UNWIND ... CREATE cannot be followed by another clause") that
contradict the obvious edge-loading form. Rather than guess, probe.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from friction.client import EngineError
from friction.config import Settings, connect_default  # noqa: F401 - re-export shim


class ProbeFailure(RuntimeError):
    """No candidate form parsed for a capability the build depends on."""


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str
    statement: str


@dataclass(frozen=True)
class Capabilities:
    rel_direction_both: str
    rel_direction_incoming: str
    pairwise_supported: bool
    node_loader_form: str
    edge_loader_form: str
    http_params_supported: bool


# Seed data every probe runs against. Ids are far above any real symbol id.
SEED = [
    "CREATE (a:Probe {id: 990001, name: 'a'})",
    "CREATE (b:Probe {id: 990002, name: 'b'})",
    "CREATE (c:Probe {id: 990003, name: 'c'})",
    "MATCH (a {id: 990001}) MATCH (b {id: 990002}) CREATE (a)-[:PCALLS]->(b)",
    "MATCH (b {id: 990002}) MATCH (c {id: 990003}) CREATE (b)-[:PCALLS]->(c)",
]


def _direction_stmt(value: str) -> str:
    return (
        "CALL algo.SSpaths({sourceNode: 990001, relTypes: ['PCALLS'], "
        f"maxLen: 3, relDirection: '{value}'}}) YIELD path RETURN path"
    )


def _pairwise_stmt() -> str:
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'id', "
        "sourceValues: [990001], targetLabel: 'Probe', targetProperty: 'id', "
        "targetValues: [990003], relTypes: ['PCALLS'], maxLen: 3, "
        "pairwise: true, pathCount: 5}) YIELD path RETURN path"
    )


def _mspaths_baseline_stmt() -> str:
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'id', "
        "sourceValues: [990001], targetLabel: 'Probe', targetProperty: 'id', "
        "targetValues: [990003], relTypes: ['PCALLS'], maxLen: 3, "
        "pathCount: 5}) YIELD path RETURN path"
    )


NODE_LOADER_FORMS = {
    "create_inline": (
        "UNWIND $rows AS row CREATE (n:ProbeLoad {id: row.id, name: row.name})",
        {"rows": [{"id": 990101, "name": "x"}, {"id": 990102, "name": "y"}]},
    ),
    "merge_then_set": (
        "UNWIND $rows AS row MERGE (n:ProbeLoad {id: row.id}) SET n.name = row.name",
        {"rows": [{"id": 990103, "name": "x"}, {"id": 990104, "name": "y"}]},
    ),
}

EDGE_LOADER_FORMS = {
    "match_match_create": (
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD]->(b)",
        {"rows": [{"src": 990101, "dst": 990102}]},
    ),
    "single_pattern_create": (
        "UNWIND $rows AS row CREATE (a {id: row.src})-[:PLOAD2]->(b {id: row.dst})",
        {"rows": [{"src": 990105, "dst": 990106}]},
    ),
    "merge_then_create": (
        "UNWIND $rows AS row MERGE (a {id: row.src}) MERGE (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD3]->(b)",
        {"rows": [{"src": 990107, "dst": 990108}]},
    ),
    "match_create_return": (
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD4]->(b) RETURN a.id AS id",
        {"rows": [{"src": 990101, "dst": 990102}]},
    ),
}


def _attempt(transport, name: str, cypher: str, params: dict | None = None) -> ProbeResult:
    try:
        transport.query(cypher, params)
        return ProbeResult(name, True, "", cypher)
    except EngineError as exc:
        return ProbeResult(name, False, str(exc)[:400], cypher)


def run_all(transport) -> list[ProbeResult]:
    results: list[ProbeResult] = []

    for stmt in SEED:
        _attempt(transport, "seed", stmt)

    for value in ("both", "BOTH", "Both"):
        results.append(_attempt(transport, f"rel_direction:{value}", _direction_stmt(value)))
    for value in ("incoming", "INCOMING", "in", "IN"):
        results.append(_attempt(transport, f"rel_direction:{value}", _direction_stmt(value)))

    results.append(_attempt(transport, "mspaths_baseline", _mspaths_baseline_stmt()))
    results.append(_attempt(transport, "pairwise", _pairwise_stmt()))

    for form, (cypher, params) in NODE_LOADER_FORMS.items():
        results.append(_attempt(transport, f"node_loader:{form}", cypher, params))
    for form, (cypher, params) in EDGE_LOADER_FORMS.items():
        results.append(_attempt(transport, f"edge_loader:{form}", cypher, params))

    results.append(_attempt(transport, "http_params",
                            "UNWIND $rows AS row RETURN row.id AS id",
                            {"rows": [{"id": 1}]}))
    return results


def _first_ok(results: list[ProbeResult], prefix: str) -> str | None:
    for r in results:
        if r.name.startswith(prefix) and r.ok:
            return r.name.split(":", 1)[1]
    return None


def derive(results: list[ProbeResult]) -> Capabilities:
    both = _first_ok(results, "rel_direction:both") or _first_ok(results, "rel_direction:BOTH") \
        or _first_ok(results, "rel_direction:Both")
    if both is None:
        # try any direction probe that succeeded and looks like a "both" spelling
        for r in results:
            if r.name.startswith("rel_direction:") and r.ok and r.name.lower().endswith("both"):
                both = r.name.split(":", 1)[1]
                break
    if both is None:
        raise ProbeFailure(
            "no relDirection spelling for bidirectional traversal parsed; "
            "inspect docs/engine-capabilities.md and cypher-compat.md"
        )

    incoming = None
    for spelling in ("incoming", "INCOMING", "in", "IN"):
        found = _first_ok(results, f"rel_direction:{spelling}")
        if found:
            incoming = found
            break

    node_form = None
    for form in NODE_LOADER_FORMS:
        if _first_ok(results, f"node_loader:{form}"):
            node_form = form
            break
    if node_form is None:
        raise ProbeFailure("no UNWIND node-loading form parsed")

    edge_form = None
    for form in EDGE_LOADER_FORMS:
        if _first_ok(results, f"edge_loader:{form}"):
            edge_form = form
            break
    if edge_form is None:
        raise ProbeFailure("no UNWIND edge-loading form parsed")

    return Capabilities(
        rel_direction_both=both,
        rel_direction_incoming=incoming or both,
        pairwise_supported=any(r.name == "pairwise" and r.ok for r in results),
        node_loader_form=node_form,
        edge_loader_form=edge_form,
        http_params_supported=any(r.name == "http_params" and r.ok for r in results),
    )


def write_report(results: list[ProbeResult], caps: Capabilities, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Engine capabilities — measured, not assumed",
        "",
        "Generated by `friction.probe` against the pinned engine build. "
        "Every downstream query form is chosen from this table.",
        "",
        "```json",
        json.dumps(asdict(caps), indent=2, sort_keys=True),
        "```",
        "",
        "| Probe | Result | Engine message |",
        "|---|---|---|",
    ]
    for r in results:
        status = "PARSES" if r.ok else "REJECTED"
        detail = r.detail.replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| `{r.name}` | {status} | {detail} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_capabilities(path: Path) -> Capabilities:
    text = Path(path).read_text(encoding="utf-8")
    start = text.index("```json") + len("```json")
    end = text.index("```", start)
    return Capabilities(**json.loads(text[start:end]))


def main() -> None:
    from friction.client import connect

    settings = Settings.from_env()
    transport = connect(settings, prefer="bolt")
    results = run_all(transport)
    caps = derive(results)
    write_report(results, caps, Path("docs/engine-capabilities.md"))
    print(json.dumps(asdict(caps), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

Remove the `connect_default` import shim — it does not exist. The import line must read:

```python
from friction.config import Settings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_probe.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Run the probe against the live engine**

Run: `uv run python -m friction.probe`
Expected: JSON printed with concrete values, and `docs/engine-capabilities.md` written.

**Read the output before continuing.** Three answers change later tasks:
- `pairwise_supported: false` → Task 10 uses the set-to-set `MSpaths` call and F1 is normalised by observed source×target pairs rather than by the pairwise pair count. Say so in the README; do not claim a `pairwise` mode you did not use.
- `rel_direction_both` → the literal string every path query uses. Never hardcode `'BOTH'`.
- `edge_loader_form` → the exact loader shape Task 9 emits.

- [ ] **Step 6: Commit the probe and its report**

```bash
git add -A
git commit -m "feat: engine capability probe, with measured capabilities report"
```

---

### Task 4: Ingest throughput measurement

**Files:**
- Create: `substrate-friction/src/friction/throughput.py`
- Create: `substrate-friction/tests/test_throughput.py`
- Create (generated): `substrate-friction/docs/throughput.md`

**Interfaces:**
- Consumes: `friction.client`, `friction.probe.load_capabilities`.
- Produces: `friction.throughput.measure(transport, caps, total=10000, batch_sizes=(500,1000,2000,5000)) -> list[dict]` where each dict has keys `batch_size: int`, `seconds: float`, `edges_per_sec: float`; and `friction.throughput.write_report(rows, path) -> None`.

- [ ] **Step 1: Write the failing test**

`tests/test_throughput.py`:
```python
from friction import throughput
from friction.probe import Capabilities

CAPS = Capabilities("both", "incoming", False, "create_inline", "merge_then_create", True)


class CountingTransport:
    name = "counting"

    def __init__(self):
        self.batches = 0
        self.rows = 0

    def query(self, cypher, params=None):
        self.batches += 1
        if params and "rows" in params:
            self.rows += len(params["rows"])
        return []


def test_measure_sends_every_row_for_each_batch_size():
    t = CountingTransport()
    rows = throughput.measure(t, CAPS, total=1000, batch_sizes=(250, 500))
    assert len(rows) == 2
    assert {r["batch_size"] for r in rows} == {250, 500}
    assert all(r["edges_per_sec"] > 0 for r in rows)
    assert t.rows == 1000 * 2 + 1000 * 2  # nodes then edges, for each batch size


def test_write_report_contains_best_rate(tmp_path):
    rows = [{"batch_size": 500, "seconds": 2.0, "edges_per_sec": 250.0},
            {"batch_size": 1000, "seconds": 1.0, "edges_per_sec": 500.0}]
    path = tmp_path / "throughput.md"
    throughput.write_report(rows, path)
    text = path.read_text()
    assert "500.0" in text and "1000" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_throughput.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.throughput'`

- [ ] **Step 3: Write `src/friction/throughput.py`**

```python
"""Measure effective ingest throughput. Recorded in the README as a finding."""

from __future__ import annotations

import time
from pathlib import Path

from friction.probe import Capabilities

NODE_FORMS = {
    "create_inline": "UNWIND $rows AS row CREATE (n:Bench {id: row.id})",
    "merge_then_set": "UNWIND $rows AS row MERGE (n:Bench {id: row.id}) SET n.k = row.id",
}

EDGE_FORMS = {
    "match_match_create":
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b)",
    "single_pattern_create":
        "UNWIND $rows AS row CREATE (a {id: row.src})-[:BENCH]->(b {id: row.dst})",
    "merge_then_create":
        "UNWIND $rows AS row MERGE (a {id: row.src}) MERGE (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b)",
    "match_create_return":
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:BENCH]->(b) RETURN a.id AS id",
}


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def measure(transport, caps: Capabilities, total: int = 10_000,
            batch_sizes: tuple[int, ...] = (500, 1000, 2000, 5000)) -> list[dict]:
    node_cypher = NODE_FORMS[caps.node_loader_form]
    edge_cypher = EDGE_FORMS[caps.edge_loader_form]
    out: list[dict] = []
    base = 1_000_000

    for size in batch_sizes:
        offset = base + len(out) * total * 4
        nodes = [{"id": offset + i} for i in range(total * 2)]
        edges = [{"src": offset + i, "dst": offset + total + i} for i in range(total)]

        for chunk in _chunks(nodes, size):
            transport.query(node_cypher, {"rows": chunk})

        start = time.perf_counter()
        for chunk in _chunks(edges, size):
            transport.query(edge_cypher, {"rows": chunk})
        elapsed = max(time.perf_counter() - start, 1e-9)

        out.append({
            "batch_size": size,
            "seconds": round(elapsed, 3),
            "edges_per_sec": round(total / elapsed, 1),
        })
    return out


def write_report(rows: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    best = max(rows, key=lambda r: r["edges_per_sec"])
    lines = [
        "# Measured ingest throughput",
        "",
        "`UNWIND $rows` batches over the client transport, against local object storage.",
        "",
        "| Batch size | Seconds | Edges/sec |",
        "|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: r["batch_size"]):
        lines.append(f"| {r['batch_size']} | {r['seconds']} | {r['edges_per_sec']} |")
    lines += [
        "",
        f"**Best: {best['edges_per_sec']} edges/sec at batch size {best['batch_size']}.**",
        "",
        "Roughly 65,000 edges per repository; three repositories is under 200,000 edges. "
        "At the measured rate this loads in minutes, which is the point of choosing a "
        "project whose graph is small: the engine's write path is serialized and adding "
        "writers does not help.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    from friction.client import connect
    from friction.config import Settings
    from friction.probe import load_capabilities

    transport = connect(Settings.from_env(), prefer="bolt")
    caps = load_capabilities(Path("docs/engine-capabilities.md"))
    rows = measure(transport, caps)
    write_report(rows, Path("docs/throughput.md"))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_throughput.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Run against the live engine and record the finding**

Run: `uv run python -m friction.throughput`
Expected: four rows printed, `docs/throughput.md` written. If the best rate is under ~2,000 edges/sec, cut to one repository for the whole project and note it.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: ingest throughput measurement with recorded finding"
```

---

### Task 5: SWE-bench Verified instances and published outcome labels

The dependent variable. An instance is "failed by system S" if it is in the split and **not** in S's resolved list.

**Files:**
- Create: `substrate-friction/src/friction/swebench.py`
- Create: `substrate-friction/tests/test_swebench.py`

**Interfaces:**
- Consumes: nothing internal.
- Produces:
  - `friction.swebench.Instance` dataclass: `instance_id: str`, `repo: str`, `base_commit: str`, `problem_statement: str`, `patch: str`, `test_patch: str`, `fail_to_pass: list[str]`, `pass_to_pass: list[str]`
  - `friction.swebench.load_instances(repos: list[str] | None = None, cache_dir: Path = Path("data/swebench")) -> list[Instance]`
  - `friction.swebench.list_submissions(split: str = "verified") -> list[str]` — folder names in `SWE-bench/experiments`
  - `friction.swebench.load_resolved(submission: str, split: str = "verified") -> set[str]`
  - `friction.swebench.outcome_table(instances, submissions, split="verified") -> dict[str, dict[str, bool]]` — `{instance_id: {submission: resolved_bool}}`

- [ ] **Step 1: Write the failing test**

`tests/test_swebench.py`:
```python
import json
import pytest
from friction import swebench


def test_outcome_table_marks_missing_as_failed():
    instances = [
        swebench.Instance("a-1", "django/django", "abc", "p", "d", "t", ["t1"], []),
        swebench.Instance("a-2", "django/django", "abc", "p", "d", "t", ["t2"], []),
    ]
    resolved = {"sysA": {"a-1"}, "sysB": {"a-1", "a-2"}}
    table = swebench.outcome_table(
        instances, ["sysA", "sysB"], resolver=lambda s, split: resolved[s]
    )
    assert table["a-1"] == {"sysA": True, "sysB": True}
    assert table["a-2"] == {"sysA": False, "sysB": True}


def test_parse_resolved_accepts_common_shapes():
    assert swebench._parse_resolved({"resolved": ["x", "y"]}) == {"x", "y"}
    assert swebench._parse_resolved({"resolved_ids": ["z"]}) == {"z"}
    assert swebench._parse_resolved(["p", "q"]) == {"p", "q"}


def test_parse_resolved_rejects_unknown_shape():
    with pytest.raises(ValueError):
        swebench._parse_resolved({"unexpected": 1})


@pytest.mark.engine
def test_list_submissions_returns_folder_names():
    names = swebench.list_submissions("verified")
    assert names and all(isinstance(n, str) for n in names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_swebench.py -v -m "not engine"`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.swebench'`

- [ ] **Step 3: Write `src/friction/swebench.py`**

```python
"""SWE-bench Verified instances plus published per-instance outcome labels.

Outcome labels come from github.com/SWE-bench/experiments, where each
submission folder under evaluation/<split>/ holds a results JSON listing the
instance ids that submission resolved. Folder names are discovered at runtime
rather than hardcoded, so nothing here depends on a guessed path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import httpx

GITHUB_API = "https://api.github.com/repos/SWE-bench/experiments/contents"
RAW = "https://raw.githubusercontent.com/SWE-bench/experiments/main"


@dataclass(frozen=True)
class Instance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        return list(json.loads(value))
    return list(value or [])


def load_instances(repos: list[str] | None = None,
                   cache_dir: Path = Path("data/swebench")) -> list[Instance]:
    from datasets import load_dataset

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test",
                      cache_dir=str(cache_dir))
    out: list[Instance] = []
    for row in ds:
        if repos is not None and row["repo"] not in repos:
            continue
        out.append(Instance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            patch=row["patch"],
            test_patch=row["test_patch"],
            fail_to_pass=_as_list(row["FAIL_TO_PASS"]),
            pass_to_pass=_as_list(row["PASS_TO_PASS"]),
        ))
    return out


def list_submissions(split: str = "verified") -> list[str]:
    resp = httpx.get(f"{GITHUB_API}/evaluation/{split}", timeout=60.0)
    resp.raise_for_status()
    return sorted(item["name"] for item in resp.json() if item["type"] == "dir")


def _parse_resolved(payload) -> set[str]:
    if isinstance(payload, list):
        return set(payload)
    if isinstance(payload, dict):
        for key in ("resolved", "resolved_ids", "resolved_instances"):
            if key in payload:
                return set(payload[key])
    raise ValueError(f"unrecognised results shape: {type(payload)} {str(payload)[:120]}")


def load_resolved(submission: str, split: str = "verified") -> set[str]:
    """Fetch a submission's resolved-instance set, trying known result paths."""
    candidates = [
        f"{RAW}/evaluation/{split}/{submission}/results/results.json",
        f"{RAW}/evaluation/{split}/{submission}/results.json",
    ]
    last: Exception | None = None
    for url in candidates:
        try:
            resp = httpx.get(url, timeout=60.0)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            return _parse_resolved(resp.json())
        except Exception as exc:  # noqa: BLE001 - try next candidate
            last = exc
    raise FileNotFoundError(f"no results JSON for {submission!r}: {last}")


def outcome_table(instances: Iterable[Instance], submissions: list[str],
                  split: str = "verified",
                  resolver: Callable[[str, str], set[str]] = load_resolved
                  ) -> dict[str, dict[str, bool]]:
    resolved_by = {s: resolver(s, split) for s in submissions}
    table: dict[str, dict[str, bool]] = {}
    for inst in instances:
        table[inst.instance_id] = {
            s: inst.instance_id in resolved_by[s] for s in submissions
        }
    return table
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_swebench.py -v -m "not engine"`
Expected: PASS, 3 passed

- [ ] **Step 5: Choose three submissions and freeze the choice**

```bash
uv run python -c "from friction.swebench import list_submissions; print('\n'.join(list_submissions()))"
```

Pick three submissions from different systems with meaningfully different resolve rates, and write the exact folder names into `data/instances/submissions.json`:

```bash
mkdir -p data/instances
cat > data/instances/submissions.json <<'JSON'
{"split": "verified", "submissions": ["<folder-1>", "<folder-2>", "<folder-3>"]}
JSON
git add data/instances/submissions.json
```

Three systems is what makes the "is it stable across systems?" confound check in Task 13 possible. One system alone measures that agent's quirks.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: SWE-bench Verified loader and published outcome labels"
```

---

### Task 6: tree-sitter symbol extraction

**Files:**
- Create: `substrate-friction/src/friction/parsing/__init__.py`
- Create: `substrate-friction/src/friction/parsing/symbols.py`
- Create: `substrate-friction/tests/test_symbols.py`
- Create: `substrate-friction/tests/fixtures/sample_pkg/mod_a.py`
- Create: `substrate-friction/tests/fixtures/sample_pkg/mod_b.py`
- Create: `substrate-friction/tests/fixtures/sample_pkg/test_mod_a.py`

**Interfaces:**
- Consumes: nothing internal.
- Produces:
  - `friction.parsing.symbols.FunctionSym` dataclass: `id: int`, `name: str`, `qualname: str`, `file_id: int`, `line_start: int`, `line_end: int`, `cyclomatic: int`, `is_test: bool`, `class_id: int | None`
  - `friction.parsing.symbols.ClassSym`: `id: int`, `name: str`, `qualname: str`, `file_id: int`, `bases: list[str]`
  - `friction.parsing.symbols.FileSym`: `id: int`, `path: str`, `repo: int`, `loc: int`
  - `friction.parsing.symbols.SymbolTable` with attributes `files: list[FileSym]`, `classes: list[ClassSym]`, `functions: list[FunctionSym]`, `by_qualname: dict[str, int]`, and method `next_id() -> int`
  - `friction.parsing.symbols.parse_repo(root: Path, repo_code: int) -> SymbolTable`

- [ ] **Step 1: Write the fixture files**

`tests/fixtures/sample_pkg/mod_a.py`:
```python
def helper(x):
    if x > 0:
        return x
    return -x


class Widget:
    def render(self, x):
        return helper(x)

    def draw(self, x):
        for i in range(x):
            if i % 2:
                continue
        return self.render(x)
```

`tests/fixtures/sample_pkg/mod_b.py`:
```python
from mod_a import Widget, helper


class FancyWidget(Widget):
    def render(self, x):
        return helper(x) + 1


def build(x):
    return FancyWidget().render(x)
```

`tests/fixtures/sample_pkg/test_mod_a.py`:
```python
from mod_a import Widget


def test_render_positive():
    assert Widget().render(3) == 3
```

- [ ] **Step 2: Write the failing test**

`tests/test_symbols.py`:
```python
from pathlib import Path
from friction.parsing.symbols import parse_repo

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_extracts_files_classes_and_functions():
    table = parse_repo(FIXTURE, repo_code=1)
    paths = {f.path for f in table.files}
    assert {"mod_a.py", "mod_b.py", "test_mod_a.py"} <= paths
    assert {c.name for c in table.classes} == {"Widget", "FancyWidget"}
    names = {f.name for f in table.functions}
    assert {"helper", "render", "draw", "build", "test_render_positive"} <= names


def test_qualnames_disambiguate_same_named_methods():
    table = parse_repo(FIXTURE, repo_code=1)
    quals = {f.qualname for f in table.functions}
    assert "mod_a.Widget.render" in quals
    assert "mod_b.FancyWidget.render" in quals


def test_ids_are_unique_positive_integers():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = [s.id for s in table.files + table.classes + table.functions]
    assert len(ids) == len(set(ids))
    assert all(isinstance(i, int) and i >= 0 for i in ids)


def test_test_functions_flagged():
    table = parse_repo(FIXTURE, repo_code=1)
    by_name = {f.name: f for f in table.functions}
    assert by_name["test_render_positive"].is_test is True
    assert by_name["helper"].is_test is False


def test_cyclomatic_counts_decision_points():
    table = parse_repo(FIXTURE, repo_code=1)
    by_qual = {f.qualname: f for f in table.functions}
    assert by_qual["mod_a.helper"].cyclomatic == 2       # base 1 + one if
    assert by_qual["mod_a.Widget.draw"].cyclomatic == 3  # base 1 + for + if


def test_line_ranges_are_sane():
    table = parse_repo(FIXTURE, repo_code=1)
    for f in table.functions:
        assert f.line_start >= 1
        assert f.line_end >= f.line_start


def test_class_bases_recorded():
    table = parse_repo(FIXTURE, repo_code=1)
    fancy = next(c for c in table.classes if c.name == "FancyWidget")
    assert "Widget" in fancy.bases
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_symbols.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.parsing'`

- [ ] **Step 4: Write `src/friction/parsing/__init__.py` and `symbols.py`**

`src/friction/parsing/__init__.py`:
```python
"""Offline parsing: source text in, graph rows out."""
```

`src/friction/parsing/symbols.py`:
```python
"""Extract Function / Class / File symbols from Python sources with tree-sitter.

Every symbol gets a non-negative integer id, because the engine matches nodes
on integer `id` only. Names are carried as properties for display and are never
used as match keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

PY_LANGUAGE = Language(tspython.language())

SKIP_DIRS = {".git", "site-packages", "vendor", "node_modules", "__pycache__",
             ".tox", ".venv", "build", "dist"}

DECISION_NODES = {
    "if_statement", "elif_clause", "for_statement", "while_statement",
    "except_clause", "conditional_expression", "boolean_operator",
    "assert_statement", "with_statement",
}


@dataclass(frozen=True)
class FileSym:
    id: int
    path: str
    repo: int
    loc: int


@dataclass(frozen=True)
class ClassSym:
    id: int
    name: str
    qualname: str
    file_id: int
    bases: list[str]


@dataclass(frozen=True)
class FunctionSym:
    id: int
    name: str
    qualname: str
    file_id: int
    line_start: int
    line_end: int
    cyclomatic: int
    is_test: bool
    class_id: int | None


@dataclass
class SymbolTable:
    files: list[FileSym] = field(default_factory=list)
    classes: list[ClassSym] = field(default_factory=list)
    functions: list[FunctionSym] = field(default_factory=list)
    by_qualname: dict[str, int] = field(default_factory=dict)
    _counter: int = 0

    def next_id(self) -> int:
        value = self._counter
        self._counter += 1
        return value


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _child_name(node: Node, src: bytes) -> str:
    ident = node.child_by_field_name("name")
    return _text(ident, src) if ident else "<anonymous>"


def _cyclomatic(node: Node) -> int:
    count = 1
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            # do not descend into nested function bodies; they get their own score
            if child.type == "function_definition" and child is not node:
                continue
            if child.type in DECISION_NODES:
                count += 1
            stack.append(child)
    return count


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _walk_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _collect(node: Node, src: bytes, table: SymbolTable, file_id: int,
             module: str, class_stack: list[tuple[int, str]]) -> None:
    for child in node.children:
        if child.type == "class_definition":
            name = _child_name(child, src)
            qualname = ".".join([module] + [c[1] for c in class_stack] + [name])
            bases: list[str] = []
            arglist = child.child_by_field_name("superclasses")
            if arglist is not None:
                for base in arglist.children:
                    if base.type in ("identifier", "attribute"):
                        bases.append(_text(base, src).split(".")[-1])
            cls_id = table.next_id()
            table.classes.append(ClassSym(cls_id, name, qualname, file_id, bases))
            table.by_qualname[qualname] = cls_id
            body = child.child_by_field_name("body")
            if body is not None:
                _collect(body, src, table, file_id, module,
                         class_stack + [(cls_id, name)])

        elif child.type in ("function_definition", "decorated_definition"):
            target = child
            if child.type == "decorated_definition":
                inner = child.child_by_field_name("definition")
                if inner is None or inner.type != "function_definition":
                    _collect(child, src, table, file_id, module, class_stack)
                    continue
                target = inner
            name = _child_name(target, src)
            qualname = ".".join([module] + [c[1] for c in class_stack] + [name])
            fn_id = table.next_id()
            table.functions.append(FunctionSym(
                id=fn_id,
                name=name,
                qualname=qualname,
                file_id=file_id,
                line_start=target.start_point[0] + 1,
                line_end=target.end_point[0] + 1,
                cyclomatic=_cyclomatic(target),
                is_test=name.startswith("test_"),
                class_id=class_stack[-1][0] if class_stack else None,
            ))
            table.by_qualname[qualname] = fn_id
            body = target.child_by_field_name("body")
            if body is not None:
                _collect(body, src, table, file_id, module, class_stack)

        else:
            _collect(child, src, table, file_id, module, class_stack)


def parse_repo(root: Path, repo_code: int) -> SymbolTable:
    root = Path(root)
    parser = Parser(PY_LANGUAGE)
    table = SymbolTable()

    for path in _walk_python_files(root):
        src = path.read_bytes()
        tree = parser.parse(src)
        rel = str(path.relative_to(root))
        file_id = table.next_id()
        table.files.append(FileSym(
            id=file_id,
            path=rel,
            repo=repo_code,
            loc=src.count(b"\n") + 1,
        ))
        table.by_qualname[f"<file>{rel}"] = file_id
        _collect(tree.root_node, src, table, file_id,
                 _module_name(path, root), [])

    return table
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_symbols.py -v`
Expected: PASS, 7 passed

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: tree-sitter symbol extraction with integer id dictionary"
```

---

### Task 7: Call resolution and inheritance edges

**Files:**
- Create: `substrate-friction/src/friction/parsing/calls.py`
- Create: `substrate-friction/tests/test_calls.py`

**Interfaces:**
- Consumes: `friction.parsing.symbols.SymbolTable`.
- Produces:
  - `friction.parsing.calls.Edge` dataclass: `src: int`, `dst: int`, `type: str`, `weight: int`
  - `friction.parsing.calls.resolve(root: Path, table: SymbolTable) -> list[Edge]` producing edge types `CALLS`, `HAS_METHOD`, `INHERITS`, `DEFINED_IN`, `IMPORTS`
  - `friction.parsing.calls.ResolutionStats` dataclass: `call_sites: int`, `resolved: int`, `unresolved: int`, and property `resolution_rate: float`
  - `friction.parsing.calls.resolve_with_stats(root, table) -> tuple[list[Edge], ResolutionStats]`

- [ ] **Step 1: Write the failing test**

`tests/test_calls.py`:
```python
from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve, resolve_with_stats

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def _table_and_edges():
    table = parse_repo(FIXTURE, repo_code=1)
    return table, resolve(FIXTURE, table)


def test_direct_call_edge_exists():
    table, edges = _table_and_edges()
    q = {f.qualname: f.id for f in table.functions}
    calls = {(e.src, e.dst) for e in edges if e.type == "CALLS"}
    assert (q["mod_a.Widget.render"], q["mod_a.helper"]) in calls


def test_self_method_call_resolves_within_class():
    table, edges = _table_and_edges()
    q = {f.qualname: f.id for f in table.functions}
    calls = {(e.src, e.dst) for e in edges if e.type == "CALLS"}
    assert (q["mod_a.Widget.draw"], q["mod_a.Widget.render"]) in calls


def test_has_method_edges_link_class_to_methods():
    table, edges = _table_and_edges()
    cls = {c.qualname: c.id for c in table.classes}
    fn = {f.qualname: f.id for f in table.functions}
    hm = {(e.src, e.dst) for e in edges if e.type == "HAS_METHOD"}
    assert (cls["mod_a.Widget"], fn["mod_a.Widget.render"]) in hm


def test_inherits_edge_between_classes():
    table, edges = _table_and_edges()
    cls = {c.qualname: c.id for c in table.classes}
    inh = {(e.src, e.dst) for e in edges if e.type == "INHERITS"}
    assert (cls["mod_b.FancyWidget"], cls["mod_a.Widget"]) in inh


def test_defined_in_edges_link_functions_to_files():
    table, edges = _table_and_edges()
    file_ids = {f.id for f in table.files}
    di = [e for e in edges if e.type == "DEFINED_IN"]
    assert di and all(e.dst in file_ids for e in di)


def test_imports_edge_between_files():
    table, edges = _table_and_edges()
    files = {f.path: f.id for f in table.files}
    imp = {(e.src, e.dst) for e in edges if e.type == "IMPORTS"}
    assert (files["mod_b.py"], files["mod_a.py"]) in imp


def test_no_self_loops_and_no_duplicate_edges():
    _, edges = _table_and_edges()
    assert all(e.src != e.dst for e in edges)
    keys = [(e.src, e.dst, e.type) for e in edges]
    assert len(keys) == len(set(keys))


def test_stats_report_resolution_rate():
    table = parse_repo(FIXTURE, repo_code=1)
    _, stats = resolve_with_stats(FIXTURE, table)
    assert stats.call_sites > 0
    assert 0.0 <= stats.resolution_rate <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_calls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.parsing.calls'`

- [ ] **Step 3: Write `src/friction/parsing/calls.py`**

```python
"""Static call resolution.

Python has no IR, so an AST-based generator has to implement resolution itself.
The strategy here is deliberately conservative and its limits are declared in
the README: resolve by (1) same-class method via `self.`, (2) module-local
name, (3) imported name, (4) unique global name across the repo. Anything
ambiguous is dropped rather than guessed, so CALLS under-reports rather than
inventing edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from friction.parsing.symbols import SKIP_DIRS, SymbolTable, _module_name

PY_LANGUAGE = Language(tspython.language())


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    type: str
    weight: int = 1


@dataclass(frozen=True)
class ResolutionStats:
    call_sites: int
    resolved: int
    unresolved: int

    @property
    def resolution_rate(self) -> float:
        return self.resolved / self.call_sites if self.call_sites else 0.0


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _imports(tree_root: Node, src: bytes) -> dict[str, str]:
    """Map local alias -> exporting module name, for `from X import Y` forms."""
    out: dict[str, str] = {}
    stack = [tree_root]
    while stack:
        node = stack.pop()
        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = _text(module_node, src) if module_node else ""
            for child in node.children:
                if child.type == "dotted_name" and child is not module_node:
                    out[_text(child, src)] = module
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is not None:
                        alias = _text(alias_node, src) if alias_node else _text(name_node, src)
                        out[alias] = module
        stack.extend(node.children)
    return out


def _enclosing(table: SymbolTable, file_id: int, line: int) -> int | None:
    best: int | None = None
    best_span = None
    for fn in table.functions:
        if fn.file_id != file_id:
            continue
        if fn.line_start <= line <= fn.line_end:
            span = fn.line_end - fn.line_start
            if best_span is None or span < best_span:
                best, best_span = fn.id, span
    return best


def _unique_suffix_index(table: SymbolTable) -> dict[str, int]:
    """Bare name -> function id, only where the bare name is unambiguous."""
    counts: dict[str, list[int]] = {}
    for fn in table.functions:
        counts.setdefault(fn.name, []).append(fn.id)
    return {name: ids[0] for name, ids in counts.items() if len(ids) == 1}


def resolve_with_stats(root: Path, table: SymbolTable) -> tuple[list[Edge], ResolutionStats]:
    root = Path(root)
    parser = Parser(PY_LANGUAGE)

    edges: set[tuple[int, int, str, int]] = set()
    fn_by_qual = {f.qualname: f.id for f in table.functions}
    cls_by_qual = {c.qualname: c.id for c in table.classes}
    cls_by_name: dict[str, list[int]] = {}
    for c in table.classes:
        cls_by_name.setdefault(c.name, []).append(c.id)
    file_by_path = {f.path: f.id for f in table.files}
    file_by_module = {
        _module_name(Path(f.path), Path(".")): f.id for f in table.files
    }
    unique_names = _unique_suffix_index(table)
    fn_by_id = {f.id: f for f in table.functions}
    cls_by_id = {c.id: c for c in table.classes}

    # Structural edges that need no source walk
    for fn in table.functions:
        edges.add((fn.id, fn.file_id, "DEFINED_IN", 1))
        if fn.class_id is not None:
            edges.add((fn.class_id, fn.id, "HAS_METHOD", 1))
    for cls in table.classes:
        for base in cls.bases:
            targets = cls_by_name.get(base, [])
            if len(targets) == 1 and targets[0] != cls.id:
                edges.add((cls.id, targets[0], "INHERITS", 1))

    call_sites = 0
    resolved = 0
    weights: dict[tuple[int, int], int] = {}

    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root))
        file_id = file_by_path.get(rel)
        if file_id is None:
            continue
        src = path.read_bytes()
        tree = parser.parse(src)
        module = _module_name(path, root)
        aliases = _imports(tree.root_node, src)

        for alias, exporting in aliases.items():
            target_file = file_by_module.get(exporting)
            if target_file is not None and target_file != file_id:
                edges.add((file_id, target_file, "IMPORTS", 1))

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type != "call":
                continue
            fn_node = node.child_by_field_name("function")
            if fn_node is None:
                continue
            call_sites += 1
            line = node.start_point[0] + 1
            caller = _enclosing(table, file_id, line)
            if caller is None:
                continue

            target: int | None = None
            if fn_node.type == "identifier":
                bare = _text(fn_node, src)
                target = fn_by_qual.get(f"{module}.{bare}") or unique_names.get(bare)
                if target is None and bare in aliases:
                    target = fn_by_qual.get(f"{aliases[bare]}.{bare}")
            elif fn_node.type == "attribute":
                obj = fn_node.child_by_field_name("object")
                attr = fn_node.child_by_field_name("attribute")
                if obj is not None and attr is not None:
                    attr_name = _text(attr, src)
                    obj_text = _text(obj, src)
                    caller_sym = fn_by_id.get(caller)
                    if obj_text == "self" and caller_sym and caller_sym.class_id is not None:
                        owner = cls_by_id[caller_sym.class_id]
                        target = fn_by_qual.get(f"{owner.qualname}.{attr_name}")
                    if target is None:
                        owners = cls_by_name.get(obj_text, [])
                        if len(owners) == 1:
                            owner = cls_by_id[owners[0]]
                            target = fn_by_qual.get(f"{owner.qualname}.{attr_name}")
                    if target is None:
                        target = unique_names.get(attr_name)

            if target is not None and target != caller:
                resolved += 1
                weights[(caller, target)] = weights.get((caller, target), 0) + 1

    for (src_id, dst_id), count in weights.items():
        edges.add((src_id, dst_id, "CALLS", count))

    out = [Edge(s, d, t, w) for (s, d, t, w) in sorted(edges)]
    stats = ResolutionStats(call_sites, resolved, call_sites - resolved)
    return out, stats


def resolve(root: Path, table: SymbolTable) -> list[Edge]:
    edges, _ = resolve_with_stats(root, table)
    return edges
```

Note the `_unique_suffix_index` fallback resolves a bare name only when it is globally unambiguous. `mod_a.Widget.render` and `mod_b.FancyWidget.render` share the name `render`, so the bare fallback will not fire for it — the `self.` and class-qualified branches carry those cases, which is exactly why the fixture contains both.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_calls.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Record the resolution rate on a real repository**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve_with_stats
root = Path("data/repos/django")
table = parse_repo(root, repo_code=1)
edges, stats = resolve_with_stats(root, table)
print(f"functions={len(table.functions)} edges={len(edges)}")
print(f"call_sites={stats.call_sites} resolved={stats.resolved} rate={stats.resolution_rate:.3f}")
PY
```

Write the rate into the README limitations section in Task 18. A rate around 0.5–0.7 is normal for static Python resolution; report the real number rather than a flattering one.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: conservative static call resolution with reported resolution rate"
```

---

### Task 8: COVERS derivation and fix-site extraction from gold patches

**Files:**
- Create: `substrate-friction/src/friction/parsing/covers.py`
- Create: `substrate-friction/src/friction/parsing/patches.py`
- Create: `substrate-friction/tests/test_covers.py`
- Create: `substrate-friction/tests/test_patches.py`

**Interfaces:**
- Consumes: `friction.parsing.symbols.SymbolTable`, `friction.parsing.calls.Edge`.
- Produces:
  - `friction.parsing.covers.derive_covers(table, edges, max_hops: int = 3) -> list[Edge]` emitting `COVERS` edges from test functions to reachable functions
  - `friction.parsing.patches.changed_ranges(patch: str) -> dict[str, list[tuple[int, int]]]` mapping file path to post-image line ranges
  - `friction.parsing.patches.fix_site_ids(patch: str, table) -> list[int]`
  - `friction.parsing.patches.test_target_ids(fail_to_pass: list[str], table) -> list[int]`

- [ ] **Step 1: Write the failing tests**

`tests/test_covers.py`:
```python
from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve
from friction.parsing.covers import derive_covers

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_covers_reaches_transitively_within_hop_bound():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    covers = derive_covers(table, edges, max_hops=3)
    q = {f.qualname: f.id for f in table.functions}
    pairs = {(e.src, e.dst) for e in covers}
    # the test calls Widget.render, which calls helper
    assert (q["test_mod_a.test_render_positive"], q["mod_a.Widget.render"]) in pairs
    assert (q["test_mod_a.test_render_positive"], q["mod_a.helper"]) in pairs


def test_covers_respects_hop_bound():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    one_hop = derive_covers(table, edges, max_hops=1)
    three_hop = derive_covers(table, edges, max_hops=3)
    assert len(one_hop) <= len(three_hop)


def test_covers_only_originates_from_tests():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    covers = derive_covers(table, edges, max_hops=3)
    tests = {f.id for f in table.functions if f.is_test}
    assert all(e.src in tests for e in covers)
    assert all(e.type == "COVERS" for e in covers)
```

`tests/test_patches.py`:
```python
from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing import patches

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"

PATCH = """diff --git a/mod_a.py b/mod_a.py
--- a/mod_a.py
+++ b/mod_a.py
@@ -1,4 +1,5 @@
 def helper(x):
     if x > 0:
         return x
+    # changed
     return -x
"""


def test_changed_ranges_extracts_post_image_lines():
    ranges = patches.changed_ranges(PATCH)
    assert "mod_a.py" in ranges
    assert ranges["mod_a.py"]


def test_fix_site_ids_maps_to_enclosing_function():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.fix_site_ids(PATCH, table)
    q = {f.qualname: f.id for f in table.functions}
    assert q["mod_a.helper"] in ids


def test_fix_site_ids_returns_empty_for_unknown_file():
    table = parse_repo(FIXTURE, repo_code=1)
    other = PATCH.replace("mod_a.py", "not_here.py")
    assert patches.fix_site_ids(other, table) == []


def test_test_target_ids_matches_pytest_node_ids():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.test_target_ids(
        ["test_mod_a.py::test_render_positive"], table
    )
    q = {f.qualname: f.id for f in table.functions}
    assert ids == [q["test_mod_a.test_render_positive"]]


def test_test_target_ids_matches_bare_function_names():
    table = parse_repo(FIXTURE, repo_code=1)
    ids = patches.test_target_ids(["test_render_positive"], table)
    assert len(ids) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_covers.py tests/test_patches.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.parsing.covers'`

- [ ] **Step 3: Write `src/friction/parsing/covers.py`**

```python
"""Derive COVERS edges statically: a test covers what it transitively calls.

This over-approximates relative to real execution coverage. That is declared as
a limitation in the README. The dynamic alternative (running each repo's suite
under coverage.py) is only worth the cost if the go/no-go result is weak and
COVERS quality is the suspected reason.
"""

from __future__ import annotations

from collections import defaultdict, deque

from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable


def derive_covers(table: SymbolTable, edges: list[Edge], max_hops: int = 3) -> list[Edge]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for e in edges:
        if e.type == "CALLS":
            adjacency[e.src].append(e.dst)

    out: list[Edge] = []
    for fn in table.functions:
        if not fn.is_test:
            continue
        seen = {fn.id}
        queue = deque([(fn.id, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for nxt in adjacency.get(node, ()):
                if nxt in seen:
                    continue
                seen.add(nxt)
                out.append(Edge(fn.id, nxt, "COVERS", 1))
                queue.append((nxt, depth + 1))
    return out
```

- [ ] **Step 4: Write `src/friction/parsing/patches.py`**

```python
"""Map a gold patch to the Function nodes it changes, and FAIL_TO_PASS test
identifiers to Function nodes.

Fix sites are derived from the post-image line ranges of each diff hunk,
intersected against Function `line_start`/`line_end`.
"""

from __future__ import annotations

from unidiff import PatchSet

from friction.parsing.symbols import SymbolTable


def _normalise(path: str) -> str:
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def changed_ranges(patch: str) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    patch_set = PatchSet(patch)
    for patched_file in patch_set:
        path = _normalise(patched_file.path)
        spans: list[tuple[int, int]] = []
        for hunk in patched_file:
            lines = [ln.target_line_no for ln in hunk
                     if ln.target_line_no is not None and (ln.is_added or ln.is_context)]
            changed = [ln.target_line_no for ln in hunk
                       if ln.is_added and ln.target_line_no is not None]
            if changed:
                spans.append((min(changed), max(changed)))
            elif lines:
                spans.append((min(lines), max(lines)))
        if spans:
            out.setdefault(path, []).extend(spans)
    return out


def fix_site_ids(patch: str, table: SymbolTable) -> list[int]:
    ranges = changed_ranges(patch)
    file_ids = {f.path: f.id for f in table.files}
    hits: set[int] = set()
    for path, spans in ranges.items():
        file_id = file_ids.get(path)
        if file_id is None:
            continue
        for fn in table.functions:
            if fn.file_id != file_id:
                continue
            for start, end in spans:
                if fn.line_start <= end and start <= fn.line_end:
                    hits.add(fn.id)
                    break
    return sorted(hits)


def test_target_ids(fail_to_pass: list[str], table: SymbolTable) -> list[int]:
    by_qual = {f.qualname: f.id for f in table.functions}
    by_name: dict[str, list[int]] = {}
    for f in table.functions:
        by_name.setdefault(f.name, []).append(f.id)

    hits: list[int] = []
    for raw in fail_to_pass:
        node = raw.strip()
        func = node.split("::")[-1].split("[")[0]
        target = by_qual.get(func.replace("/", ".").replace(".py", ""))
        if target is None:
            candidates = by_name.get(func, [])
            if len(candidates) == 1:
                target = candidates[0]
        if target is not None and target not in hits:
            hits.append(target)
    return hits
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_covers.py tests/test_patches.py -v`
Expected: PASS, 8 passed

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: COVERS derivation and gold-patch fix-site extraction"
```

---

### Task 9: NDJSON emit and the HydraDB loader

**Files:**
- Create: `substrate-friction/src/friction/loader.py`
- Create: `substrate-friction/tests/test_loader.py`

**Interfaces:**
- Consumes: `friction.parsing.symbols.SymbolTable`, `friction.parsing.calls.Edge`, `friction.probe.Capabilities`, `friction.client`.
- Produces:
  - `friction.loader.emit_ndjson(table, edges, out_dir: Path) -> dict[str, Path]` writing `nodes.ndjson` and `edges.ndjson`
  - `friction.loader.node_statement(caps, label) -> str`
  - `friction.loader.edge_statement(caps, rel_type) -> str`
  - `friction.loader.load(transport, caps, out_dir: Path, batch_size: int = 1000) -> dict[str, int]` returning counts by label and relationship type

- [ ] **Step 1: Write the failing test**

`tests/test_loader.py`:
```python
import json
from pathlib import Path

import pytest

from friction import loader
from friction.probe import Capabilities
from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable, FileSym, FunctionSym

CAPS = Capabilities("both", "incoming", False, "create_inline",
                    "merge_then_create", True)


class RecordingTransport:
    name = "recording"

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def query(self, cypher, params=None):
        self.calls.append((cypher, params or {}))
        return []


def _table():
    t = SymbolTable()
    t.files.append(FileSym(0, "mod_a.py", 1, 12))
    t.functions.append(FunctionSym(1, "helper", "mod_a.helper", 0, 1, 4, 2, False, None))
    t.functions.append(FunctionSym(2, "render", "mod_a.W.render", 0, 6, 8, 1, False, None))
    return t


def test_emit_writes_one_json_object_per_line(tmp_path):
    paths = loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 3)], tmp_path)
    node_lines = paths["nodes"].read_text().strip().splitlines()
    edge_lines = paths["edges"].read_text().strip().splitlines()
    assert len(node_lines) == 3
    assert len(edge_lines) == 1
    assert json.loads(edge_lines[0])["type"] == "CALLS"
    assert all("label" in json.loads(line) for line in node_lines)


def test_node_statement_matches_probed_form():
    stmt = loader.node_statement(CAPS, "Function")
    assert stmt.startswith("UNWIND $rows AS row CREATE (n:Function")
    merge_caps = Capabilities("both", "incoming", False, "merge_then_set",
                              "merge_then_create", True)
    assert "MERGE" in loader.node_statement(merge_caps, "Function")


def test_edge_statement_matches_probed_form():
    stmt = loader.edge_statement(CAPS, "CALLS")
    assert "MERGE" in stmt and "[:CALLS" in stmt


def test_edge_statement_rejects_unknown_form():
    bad = Capabilities("both", "incoming", False, "create_inline", "nope", True)
    with pytest.raises(KeyError):
        loader.edge_statement(bad, "CALLS")


def test_load_batches_and_sends_nodes_before_edges(tmp_path):
    loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 3)], tmp_path)
    t = RecordingTransport()
    counts = loader.load(t, CAPS, tmp_path, batch_size=2)
    node_calls = [c for c in t.calls if "CREATE (n:" in c[0] or "MERGE (n:" in c[0]]
    edge_calls = [c for c in t.calls if "[:CALLS" in c[0]]
    assert node_calls and edge_calls
    assert t.calls.index(node_calls[-1]) < t.calls.index(edge_calls[0])
    assert counts["Function"] == 2
    assert counts["CALLS"] == 1


def test_load_never_sends_inline_lists(tmp_path):
    loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 1)], tmp_path)
    t = RecordingTransport()
    loader.load(t, CAPS, tmp_path, batch_size=10)
    for cypher, params in t.calls:
        assert "UNWIND [" not in cypher
        assert "rows" in params
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.loader'`

- [ ] **Step 3: Write `src/friction/loader.py`**

```python
"""Stage graph rows as NDJSON, then load them with UNWIND $rows batches.

The exact statement shapes come from the capability probe rather than from
assumption: `cypher-compat.md` restricts UNWIND forms in ways that rule out the
obvious MATCH/MATCH/CREATE edge loader on some builds.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable
from friction.probe import Capabilities

NODE_FORMS = {
    "create_inline":
        "UNWIND $rows AS row CREATE (n:{label} {{{props}}})",
    "merge_then_set":
        "UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET {sets}",
}

EDGE_FORMS = {
    "match_match_create":
        "UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel} {{weight: row.weight}}]->(b)",
    "single_pattern_create":
        "UNWIND $rows AS row "
        "CREATE (a {{id: row.src}})-[:{rel} {{weight: row.weight}}]->(b {{id: row.dst}})",
    "merge_then_create":
        "UNWIND $rows AS row MERGE (a {{id: row.src}}) MERGE (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel} {{weight: row.weight}}]->(b)",
    "match_create_return":
        "UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel} {{weight: row.weight}}]->(b) RETURN a.id AS id",
}

NODE_PROPS = {
    "File": ["id", "path", "repo", "loc"],
    "Class": ["id", "name", "file_id"],
    "Function": ["id", "name", "file_id", "line_start", "line_end",
                 "cyclomatic", "is_test"],
}


def emit_ndjson(table: SymbolTable, edges: list[Edge], out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = out_dir / "nodes.ndjson"
    edges_path = out_dir / "edges.ndjson"

    with nodes_path.open("w", encoding="utf-8") as fh:
        for f in table.files:
            fh.write(json.dumps({"label": "File", "id": f.id, "path": f.path,
                                 "repo": f.repo, "loc": f.loc}) + "\n")
        for c in table.classes:
            fh.write(json.dumps({"label": "Class", "id": c.id, "name": c.name,
                                 "file_id": c.file_id}) + "\n")
        for fn in table.functions:
            fh.write(json.dumps({"label": "Function", "id": fn.id, "name": fn.name,
                                 "file_id": fn.file_id, "line_start": fn.line_start,
                                 "line_end": fn.line_end, "cyclomatic": fn.cyclomatic,
                                 "is_test": fn.is_test}) + "\n")

    with edges_path.open("w", encoding="utf-8") as fh:
        for e in edges:
            fh.write(json.dumps({"src": e.src, "dst": e.dst,
                                 "type": e.type, "weight": e.weight}) + "\n")

    return {"nodes": nodes_path, "edges": edges_path}


def node_statement(caps: Capabilities, label: str) -> str:
    props = NODE_PROPS[label]
    template = NODE_FORMS[caps.node_loader_form]
    if caps.node_loader_form == "create_inline":
        body = ", ".join(f"{p}: row.{p}" for p in props)
        return template.format(label=label, props=body)
    sets = ", ".join(f"n.{p} = row.{p}" for p in props if p != "id")
    return template.format(label=label, sets=sets)


def edge_statement(caps: Capabilities, rel_type: str) -> str:
    return EDGE_FORMS[caps.edge_loader_form].format(rel=rel_type)


def _read_ndjson(path: Path):
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def load(transport, caps: Capabilities, out_dir: Path,
         batch_size: int = 1000) -> dict[str, int]:
    out_dir = Path(out_dir)
    counts: dict[str, int] = defaultdict(int)

    by_label: dict[str, list[dict]] = defaultdict(list)
    for row in _read_ndjson(out_dir / "nodes.ndjson"):
        label = row.pop("label")
        by_label[label].append(row)

    # All nodes before any edges.
    for label in ("File", "Class", "Function"):
        rows = by_label.get(label, [])
        if not rows:
            continue
        statement = node_statement(caps, label)
        for chunk in _chunks(rows, batch_size):
            transport.query(statement, {"rows": chunk})
        counts[label] += len(rows)

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in _read_ndjson(out_dir / "edges.ndjson"):
        by_type[row.pop("type")].append(row)

    for rel_type, rows in sorted(by_type.items()):
        statement = edge_statement(caps, rel_type)
        for chunk in _chunks(rows, batch_size):
            transport.query(statement, {"rows": chunk})
        counts[rel_type] += len(rows)

    return dict(counts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loader.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Load one real repository end to end**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.client import connect
from friction.config import Settings
from friction.probe import load_capabilities
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve
from friction.parsing.covers import derive_covers
from friction.loader import emit_ndjson, load

root = Path("data/repos/django")
table = parse_repo(root, repo_code=1)
edges = resolve(root, table)
edges += derive_covers(table, edges, max_hops=3)
paths = emit_ndjson(table, edges, Path("data/graphs/django"))
print({k: str(v) for k, v in paths.items()})

caps = load_capabilities(Path("docs/engine-capabilities.md"))
transport = connect(Settings.from_env(), prefer="bolt")
print(load(transport, caps, Path("data/graphs/django"), batch_size=1000))
PY
```

Expected: counts printed for `File`, `Class`, `Function`, `CALLS`, `COVERS`, `HAS_METHOD`, `INHERITS`, `DEFINED_IN`, `IMPORTS`. Roughly 65,000 edges for a repository of Django's size.

- [ ] **Step 6: Verify the loaded graph is queryable**

```bash
uv run python -c "
from friction.client import connect
from friction.config import Settings
t = connect(Settings.from_env())
print(t.query('MATCH (f:Function) RETURN count(f) AS n'))
"
```

Expected: a non-zero count matching the `Function` count from Step 5. If it is lower, a row or byte budget silently truncated a batch — reduce `batch_size` and reload.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: NDJSON staging and probe-driven UNWIND loader"
```

---

### Task 10: Path query wrappers

The engine-facing half of the metric. Everything about direction spelling and `pairwise` comes from the probe, never from a literal.

**Files:**
- Create: `substrate-friction/src/friction/paths.py`
- Create: `substrate-friction/tests/test_paths.py`

**Interfaces:**
- Consumes: `friction.probe.Capabilities`, `friction.client`, `friction.config.Settings`.
- Produces:
  - `friction.paths.PathSet` dataclass: `paths: list[list[int]]`, `costs: list[float]`, `cypher: str`, `millis: float`, `truncated: bool`
  - `friction.paths.build_mspaths_cypher(caps, settings, rel_types) -> str`
  - `friction.paths.fix_to_test_paths(transport, caps, settings, fix_ids, test_ids, rel_types=("CALLS","HAS_METHOD","INHERITS")) -> PathSet`
  - `friction.paths.fan_in(transport, caps, settings, fix_ids) -> tuple[int, str, float]`
  - `friction.paths.extract_node_ids(path_value) -> list[int]`

- [ ] **Step 1: Write the failing test**

`tests/test_paths.py`:
```python
import pytest

from friction import paths
from friction.config import Settings
from friction.probe import Capabilities

SETTINGS = Settings("bolt://x", "http://x", "t", "default", "default",
                    "cell-0", 6, 20, "both")
CAPS_NO_PAIRWISE = Capabilities("both", "incoming", False, "create_inline",
                                "merge_then_create", True)
CAPS_PAIRWISE = Capabilities("both", "incoming", True, "create_inline",
                             "merge_then_create", True)


class StubTransport:
    name = "stub"

    def __init__(self, rows):
        self.rows = rows
        self.last_cypher = None
        self.last_params = None

    def query(self, cypher, params=None):
        self.last_cypher = cypher
        self.last_params = params
        return self.rows


def test_cypher_uses_probed_direction_not_a_literal():
    caps = Capabilities("BOTH", "INCOMING", False, "create_inline",
                        "merge_then_create", True)
    cypher = paths.build_mspaths_cypher(caps, SETTINGS, ("CALLS",))
    assert "relDirection: 'BOTH'" in cypher


def test_cypher_omits_pairwise_when_unsupported():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",))
    assert "pairwise" not in cypher


def test_cypher_includes_pairwise_when_supported():
    cypher = paths.build_mspaths_cypher(CAPS_PAIRWISE, SETTINGS, ("CALLS",))
    assert "pairwise: true" in cypher


def test_cypher_always_bounds_maxlen():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",))
    assert "maxLen: 6" in cypher
    assert "*" not in cypher


def test_cypher_passes_rel_types_as_a_list():
    cypher = paths.build_mspaths_cypher(
        CAPS_NO_PAIRWISE, SETTINGS, ("CALLS", "HAS_METHOD", "INHERITS"))
    assert "relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS']" in cypher


def test_extract_node_ids_handles_list_of_ints():
    assert paths.extract_node_ids([1, 2, 3]) == [1, 2, 3]


def test_extract_node_ids_handles_dicts_with_id_keys():
    value = [{"id": 4}, {"id": 5}]
    assert paths.extract_node_ids(value) == [4, 5]


def test_extract_node_ids_handles_nested_nodes_key():
    value = {"nodes": [{"id": 7}, {"id": 8}]}
    assert paths.extract_node_ids(value) == [7, 8]


def test_fix_to_test_paths_returns_paths_and_timing():
    t = StubTransport([{"path": [1, 2, 3], "pathCost": 2.0},
                       {"path": [1, 4, 3], "pathCost": 2.0}])
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1], [3])
    assert result.paths == [[1, 2, 3], [1, 4, 3]]
    assert result.costs == [2.0, 2.0]
    assert result.millis >= 0
    assert "algo.MSpaths" in result.cypher


def test_fix_to_test_paths_flags_truncation_at_path_count():
    rows = [{"path": [1, 2, 3], "pathCost": 2.0}] * SETTINGS.path_count
    t = StubTransport(rows)
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1], [3])
    assert result.truncated is True


def test_fix_to_test_paths_returns_empty_for_empty_inputs():
    t = StubTransport([])
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [], [3])
    assert result.paths == []
    assert t.last_cypher is None


def test_fan_in_uses_incoming_direction_and_maxlen_one():
    t = StubTransport([{"fan_in": 12}])
    count, cypher, millis = paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert count == 12
    assert "relDirection: 'incoming'" in cypher
    assert "maxLen: 1" in cypher
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.paths'`

- [ ] **Step 3: Write `src/friction/paths.py`**

```python
"""Path queries. The engine finds the paths; the arithmetic happens elsewhere.

`pairwise` is not documented in cypher-compat.md, so it is emitted only when
the capability probe proved the build accepts it. Without it the same call
still returns bounded paths between the fix-site set and the test-target set,
which is what the friction metric is defined over; the difference is how F1 is
normalised, and that is stated in the README.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

from friction.config import Settings
from friction.probe import Capabilities


@dataclass(frozen=True)
class PathSet:
    paths: list[list[int]]
    costs: list[float]
    cypher: str
    millis: float
    truncated: bool


def _rel_types_literal(rel_types: Sequence[str]) -> str:
    inner = ", ".join(f"'{r}'" for r in rel_types)
    return f"[{inner}]"


def build_mspaths_cypher(caps: Capabilities, settings: Settings,
                         rel_types: Sequence[str]) -> str:
    parts = [
        "sourceLabel: 'Function'", "sourceProperty: 'id'",
        "sourceValues: $fixIds",
        "targetLabel: 'Function'", "targetProperty: 'id'",
        "targetValues: $testIds",
        f"relTypes: {_rel_types_literal(rel_types)}",
        f"relDirection: '{caps.rel_direction_both}'",
        f"maxLen: {settings.max_len}",
        f"pathCount: {settings.path_count}",
    ]
    if caps.pairwise_supported:
        parts.insert(-1, "pairwise: true")
    config = ", ".join(parts)
    return (
        f"CALL algo.MSpaths({{{config}}}) "
        "YIELD path, pathCost RETURN path, pathCost"
    )


def build_fan_in_cypher(caps: Capabilities) -> str:
    config = ", ".join([
        "sourceLabel: 'Function'", "sourceProperty: 'id'",
        "sourceValues: $fixIds",
        "relTypes: ['CALLS']",
        f"relDirection: '{caps.rel_direction_incoming}'",
        "maxLen: 1", "pathCount: 500",
    ])
    return f"CALL algo.SSpaths({{{config}}}) YIELD path RETURN count(path) AS fan_in"


def extract_node_ids(path_value: Any) -> list[int]:
    """Normalise whatever shape the driver hands back into a list of node ids."""
    if path_value is None:
        return []
    if isinstance(path_value, dict):
        for key in ("nodes", "vertices", "path"):
            if key in path_value:
                return extract_node_ids(path_value[key])
        if "id" in path_value:
            return [int(path_value["id"])]
        return []
    if isinstance(path_value, (list, tuple)):
        out: list[int] = []
        for item in path_value:
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, dict) and "id" in item:
                out.append(int(item["id"]))
            elif hasattr(item, "get") and item.get("id") is not None:
                out.append(int(item["id"]))
            elif hasattr(item, "id"):
                out.append(int(item.id))
        return out
    nodes = getattr(path_value, "nodes", None)
    if nodes is not None:
        return extract_node_ids(list(nodes))
    return []


def fix_to_test_paths(transport, caps: Capabilities, settings: Settings,
                      fix_ids: list[int], test_ids: list[int],
                      rel_types: Sequence[str] = ("CALLS", "HAS_METHOD", "INHERITS")
                      ) -> PathSet:
    if not fix_ids or not test_ids:
        return PathSet([], [], "", 0.0, False)

    cypher = build_mspaths_cypher(caps, settings, rel_types)
    start = time.perf_counter()
    rows = transport.query(cypher, {"fixIds": list(fix_ids), "testIds": list(test_ids)})
    millis = (time.perf_counter() - start) * 1000.0

    parsed: list[list[int]] = []
    costs: list[float] = []
    for row in rows:
        ids = extract_node_ids(row.get("path"))
        if ids:
            parsed.append(ids)
            cost = row.get("pathCost")
            costs.append(float(cost) if cost is not None else float(len(ids) - 1))

    return PathSet(
        paths=parsed,
        costs=costs,
        cypher=cypher,
        millis=round(millis, 2),
        truncated=len(rows) >= settings.path_count,
    )


def fan_in(transport, caps: Capabilities, settings: Settings,
           fix_ids: list[int]) -> tuple[int, str, float]:
    if not fix_ids:
        return 0, "", 0.0
    cypher = build_fan_in_cypher(caps)
    start = time.perf_counter()
    rows = transport.query(cypher, {"fixIds": list(fix_ids)})
    millis = (time.perf_counter() - start) * 1000.0
    count = 0
    if rows:
        first = rows[0]
        value = first.get("fan_in") if isinstance(first, dict) else None
        count = int(value) if value is not None else 0
    return count, cypher, round(millis, 2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_paths.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Run one real query against the loaded graph**

```bash
uv run python - <<'PY'
from pathlib import Path
from friction.client import connect
from friction.config import Settings
from friction.probe import load_capabilities
from friction import paths

s = Settings.from_env()
caps = load_capabilities(Path("docs/engine-capabilities.md"))
t = connect(s, prefer="bolt")
fn = [r["id"] for r in t.query("MATCH (f:Function) RETURN f.id AS id")][:40]
result = paths.fix_to_test_paths(t, caps, s, fn[:3], fn[3:10])
print(f"paths={len(result.paths)} truncated={result.truncated} {result.millis}ms")
print(result.cypher)
PY
```

Expected: a non-zero path count and a latency in low milliseconds warm. If `truncated` is `True`, note it — Task 11 quantifies what that costs.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: MSpaths/SSpaths wrappers driven by probed capabilities"
```

---

### Task 11: Path fidelity validation against networkx

This exists because the engine has a known class of bug where variable-length traversal can drop same-frontier edges, and query budgets can silently truncate result sets. F1 (path multiplicity) and F3 (intermediate spread) are literally counts of returned paths — silent truncation does not add noise, it biases exactly the high-friction instances downward, which is the direction that would destroy the thesis. Measure the gap before trusting any correlation.

**Files:**
- Create: `substrate-friction/src/friction/fidelity.py`
- Create: `substrate-friction/tests/test_fidelity.py`

**Interfaces:**
- Consumes: `friction.paths`, `friction.parsing.calls.Edge`.
- Produces:
  - `friction.fidelity.reference_paths(edges, fix_ids, test_ids, max_len, rel_types) -> list[list[int]]`
  - `friction.fidelity.FidelityReport` dataclass: `instances: int`, `engine_total: int`, `reference_total: int`, `recall: float`, `truncated_instances: int`, `worst_instance: str`
  - `friction.fidelity.compare(engine_by_instance, reference_by_instance) -> FidelityReport`
  - `friction.fidelity.write_report(report, path) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_fidelity.py`:
```python
from friction import fidelity
from friction.parsing.calls import Edge


EDGES = [
    Edge(1, 2, "CALLS", 1),
    Edge(2, 3, "CALLS", 1),
    Edge(1, 4, "CALLS", 1),
    Edge(4, 3, "CALLS", 1),
    Edge(5, 6, "IMPORTS", 1),
]


def test_reference_finds_both_routes():
    found = fidelity.reference_paths(EDGES, [1], [3], max_len=3, rel_types=("CALLS",))
    assert sorted(found) == [[1, 2, 3], [1, 4, 3]]


def test_reference_respects_max_len():
    found = fidelity.reference_paths(EDGES, [1], [3], max_len=1, rel_types=("CALLS",))
    assert found == []


def test_reference_ignores_other_rel_types():
    found = fidelity.reference_paths(EDGES, [5], [6], max_len=3, rel_types=("CALLS",))
    assert found == []


def test_reference_treats_edges_as_undirected():
    found = fidelity.reference_paths(EDGES, [3], [1], max_len=3, rel_types=("CALLS",))
    assert len(found) == 2


def test_compare_computes_recall():
    engine = {"i1": [[1, 2, 3]], "i2": [[1, 4, 3], [1, 2, 3]]}
    reference = {"i1": [[1, 2, 3], [1, 4, 3]], "i2": [[1, 4, 3], [1, 2, 3]]}
    report = fidelity.compare(engine, reference)
    assert report.instances == 2
    assert report.engine_total == 3
    assert report.reference_total == 4
    assert report.recall == 0.75
    assert report.worst_instance == "i1"


def test_compare_handles_empty_reference():
    report = fidelity.compare({"i1": []}, {"i1": []})
    assert report.recall == 1.0


def test_write_report_states_recall(tmp_path):
    report = fidelity.FidelityReport(2, 3, 4, 0.75, 1, "i1")
    path = tmp_path / "fidelity.md"
    fidelity.write_report(report, path)
    assert "0.75" in path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fidelity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.fidelity'`

- [ ] **Step 3: Write `src/friction/fidelity.py`**

```python
"""Cross-check engine path results against an in-memory networkx reference.

The reference is computed on the identical edge set and the identical maxLen
bound, so any shortfall is the engine's traversal or a result budget, not a
different question being asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import networkx as nx

from friction.parsing.calls import Edge


@dataclass(frozen=True)
class FidelityReport:
    instances: int
    engine_total: int
    reference_total: int
    recall: float
    truncated_instances: int
    worst_instance: str


def reference_paths(edges: list[Edge], fix_ids: Sequence[int],
                    test_ids: Sequence[int], max_len: int,
                    rel_types: Sequence[str]) -> list[list[int]]:
    keep = set(rel_types)
    graph = nx.Graph()
    for e in edges:
        if e.type in keep:
            graph.add_edge(e.src, e.dst)

    found: list[list[int]] = []
    for source in fix_ids:
        if source not in graph:
            continue
        for target in test_ids:
            if target not in graph or target == source:
                continue
            for path in nx.all_simple_paths(graph, source, target, cutoff=max_len):
                found.append(list(path))
    return sorted(found)


def compare(engine_by_instance: dict[str, list[list[int]]],
            reference_by_instance: dict[str, list[list[int]]]) -> FidelityReport:
    engine_total = sum(len(v) for v in engine_by_instance.values())
    reference_total = sum(len(v) for v in reference_by_instance.values())

    truncated = 0
    worst_key = ""
    worst_gap = -1
    for key, ref in reference_by_instance.items():
        got = len(engine_by_instance.get(key, []))
        gap = len(ref) - got
        if gap > 0:
            truncated += 1
        if gap > worst_gap:
            worst_gap, worst_key = gap, key

    recall = 1.0 if reference_total == 0 else engine_total / reference_total
    return FidelityReport(
        instances=len(reference_by_instance),
        engine_total=engine_total,
        reference_total=reference_total,
        recall=round(recall, 4),
        truncated_instances=truncated,
        worst_instance=worst_key,
    )


def write_report(report: FidelityReport, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([
        "# Path fidelity vs a networkx reference",
        "",
        "Same edge set, same `maxLen`, same relationship types. Any shortfall is",
        "the engine's traversal or a result budget, not a different question.",
        "",
        f"- Instances compared: **{report.instances}**",
        f"- Paths returned by the engine: **{report.engine_total}**",
        f"- Paths found by the reference: **{report.reference_total}**",
        f"- Recall: **{report.recall}**",
        f"- Instances where the engine returned fewer paths: **{report.truncated_instances}**",
        f"- Largest single shortfall: `{report.worst_instance}`",
        "",
        "Why this matters: F1 (path multiplicity) and F3 (intermediate spread) are",
        "counts of returned paths. Truncation does not add symmetric noise — it",
        "biases high-friction instances downward, which is the direction that would",
        "suppress the very signal this project tests for. If recall is below ~0.9,",
        "raise `pathCount` and re-run before believing any correlation result.",
        "",
    ]), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fidelity.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Run the comparison on 20 real instances and act on the number**

Compare engine output against the reference for 20 instances of the pilot repository, write `docs/fidelity.md`, and read the recall.

If recall < 0.9, raise `HYDRA_PATH_COUNT` (try 50, then 100), re-run, and record both the before and after numbers. Do not proceed to Task 13 with unmeasured truncation.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: networkx path-fidelity guard against silent truncation"
```

---

### Task 12: The friction metric — six components

Pure functions over path data. No engine required, so this is fast to iterate and honest to test.

**Files:**
- Create: `substrate-friction/src/friction/metric.py`
- Create: `substrate-friction/tests/test_metric.py`

**Interfaces:**
- Consumes: `friction.paths.PathSet`.
- Produces:
  - `friction.metric.Components` dataclass: `f1: float`, `f2: float`, `f3: float`, `f4: float`, `f5: float`, `f6: float`, and `as_dict() -> dict[str, float]`
  - `friction.metric.raw_components(path_set, fix_ids, test_ids, fan_in_count) -> Components`
  - `friction.metric.normalise(all_components: list[Components]) -> list[Components]` — min-max to 0–1, computed client-side because the engine has no `min`/`max`
  - `friction.metric.EQUAL_WEIGHTS: dict[str, float]`
  - `friction.metric.score(components, weights) -> float`
  - `friction.metric.band(score) -> str` returning `"LOW"`, `"MEDIUM"`, or `"HIGH"`

- [ ] **Step 1: Write the failing test**

`tests/test_metric.py`:
```python
import pytest

from friction import metric
from friction.paths import PathSet


def ps(paths, costs=None):
    return PathSet(paths, costs or [float(len(p) - 1) for p in paths], "c", 1.0, False)


def test_f1_is_path_count_normalised_by_pairs():
    c = metric.raw_components(ps([[1, 2, 3], [1, 4, 3]]), [1], [3], 0)
    assert c.f1 == 2.0  # 2 paths / 1 pair


def test_f2_is_mean_hop_count():
    c = metric.raw_components(ps([[1, 2, 3], [1, 2, 3, 4]]), [1], [3], 0)
    assert c.f2 == pytest.approx(2.5)  # hops 2 and 3


def test_f3_counts_distinct_intermediates_only():
    c = metric.raw_components(ps([[1, 2, 3], [1, 4, 3]]), [1], [3], 0)
    assert c.f3 == 2.0  # nodes 2 and 4; endpoints excluded


def test_f4_convergence_ratio_is_distinct_over_total():
    c = metric.raw_components(ps([[1, 2, 3], [1, 2, 3]]), [1], [3], 0)
    assert c.f4 == pytest.approx(0.5)  # 1 distinct intermediate / 2 occurrences


def test_f5_detects_repeated_node_within_a_path():
    c = metric.raw_components(ps([[1, 2, 1, 3]]), [1], [3], 0)
    assert c.f5 == 1.0


def test_f5_is_zero_for_simple_paths():
    c = metric.raw_components(ps([[1, 2, 3]]), [1], [3], 0)
    assert c.f5 == 0.0


def test_f6_is_the_fan_in_count():
    c = metric.raw_components(ps([[1, 2, 3]]), [1], [3], 17)
    assert c.f6 == 17.0


def test_empty_path_set_is_all_zero_not_an_error():
    c = metric.raw_components(ps([]), [1], [3], 0)
    assert c.as_dict() == {"f1": 0.0, "f2": 0.0, "f3": 0.0,
                           "f4": 0.0, "f5": 0.0, "f6": 0.0}


def test_normalise_maps_to_unit_interval():
    raw = [metric.Components(0, 0, 0, 0, 0, 0),
           metric.Components(10, 10, 10, 10, 10, 10),
           metric.Components(5, 5, 5, 5, 5, 5)]
    out = metric.normalise(raw)
    assert out[0].f1 == 0.0
    assert out[1].f1 == 1.0
    assert out[2].f1 == pytest.approx(0.5)


def test_normalise_handles_a_constant_component():
    raw = [metric.Components(3, 0, 0, 0, 0, 0), metric.Components(3, 0, 0, 0, 0, 0)]
    out = metric.normalise(raw)
    assert out[0].f1 == 0.0 and out[1].f1 == 0.0


def test_score_inverts_convergence():
    low_convergence = metric.Components(0, 0, 0, 0.0, 0, 0)
    high_convergence = metric.Components(0, 0, 0, 1.0, 0, 0)
    w = {"f1": 0, "f2": 0, "f3": 0, "f4": 1, "f5": 0, "f6": 0}
    assert metric.score(low_convergence, w) == 1.0
    assert metric.score(high_convergence, w) == 0.0


def test_score_with_equal_weights_is_bounded():
    c = metric.Components(1, 1, 1, 1, 1, 1)
    assert 0.0 <= metric.score(c, metric.EQUAL_WEIGHTS) <= 1.0


def test_band_thresholds():
    assert metric.band(0.20) == "LOW"
    assert metric.band(0.50) == "MEDIUM"
    assert metric.band(0.79) == "HIGH"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metric.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.metric'`

- [ ] **Step 3: Write `src/friction/metric.py`**

```python
"""The friction metric: six components, then freeze.

Every component is derived from the path set the engine returned. Normalisation
is min-max across the instance set and happens here because the engine has no
`min` or `max` aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass

from friction.paths import PathSet

EQUAL_WEIGHTS: dict[str, float] = {
    "f1": 1 / 6, "f2": 1 / 6, "f3": 1 / 6,
    "f4": 1 / 6, "f5": 1 / 6, "f6": 1 / 6,
}

COMPONENT_NAMES = ("f1", "f2", "f3", "f4", "f5", "f6")

COMPONENT_LABELS = {
    "f1": "Path multiplicity",
    "f2": "Mean path length",
    "f3": "Intermediate spread",
    "f4": "Convergence",
    "f5": "Cyclic pressure",
    "f6": "Fan-in load",
}


@dataclass(frozen=True)
class Components:
    f1: float
    f2: float
    f3: float
    f4: float
    f5: float
    f6: float

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in COMPONENT_NAMES}


def raw_components(path_set: PathSet, fix_ids: list[int], test_ids: list[int],
                   fan_in_count: int) -> Components:
    paths = path_set.paths
    if not paths:
        return Components(0.0, 0.0, 0.0, 0.0, 0.0, float(fan_in_count) if fan_in_count else 0.0)

    pairs = max(len(fix_ids) * len(test_ids), 1)
    f1 = len(paths) / pairs

    f2 = sum(len(p) - 1 for p in paths) / len(paths)

    intermediates: list[int] = []
    for path in paths:
        intermediates.extend(path[1:-1])
    distinct = len(set(intermediates))
    f3 = float(distinct)

    f4 = distinct / len(intermediates) if intermediates else 0.0

    cyclic = sum(1 for p in paths if len(set(p)) != len(p))
    f5 = cyclic / len(paths)

    f6 = float(fan_in_count)

    return Components(f1, f2, f3, f4, f5, f6)


def normalise(all_components: list[Components]) -> list[Components]:
    if not all_components:
        return []
    bounds: dict[str, tuple[float, float]] = {}
    for name in COMPONENT_NAMES:
        values = [getattr(c, name) for c in all_components]
        bounds[name] = (min(values), max(values))

    out: list[Components] = []
    for c in all_components:
        scaled: dict[str, float] = {}
        for name in COMPONENT_NAMES:
            low, high = bounds[name]
            span = high - low
            scaled[name] = 0.0 if span == 0 else (getattr(c, name) - low) / span
        out.append(Components(**scaled))
    return out


def score(components: Components, weights: dict[str, float]) -> float:
    values = components.as_dict()
    values["f4"] = 1.0 - values["f4"]  # low convergence means harder
    total = sum(weights[name] * values[name] for name in COMPONENT_NAMES)
    denominator = sum(weights.values()) or 1.0
    return max(0.0, min(1.0, total / denominator))


def band(value: float) -> str:
    if value < 0.34:
        return "LOW"
    if value < 0.67:
        return "MEDIUM"
    return "HIGH"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metric.py -v`
Expected: PASS, 13 passed

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: six-component friction metric with client-side normalisation"
```

---

### Task 13: The GO/NO-GO harness — the decision gate

**Do not build the CLI or the visualization before this task returns a number.**

**Files:**
- Create: `substrate-friction/src/friction/evaluate.py`
- Create: `substrate-friction/tests/test_evaluate.py`
- Create (generated): `substrate-friction/docs/evaluation.md`
- Create (generated): `substrate-friction/docs/plots/correlation.png`

**Interfaces:**
- Consumes: `friction.metric`, `friction.paths`, `friction.swebench`, `friction.parsing.patches`.
- Produces:
  - `friction.evaluate.InstanceRow` dataclass: `instance_id: str`, `repo: str`, `components: Components`, `failed: dict[str, bool]`, `repo_loc: int`, `patch_lines: int`
  - `friction.evaluate.auc(scores: list[float], failed: list[bool]) -> float`
  - `friction.evaluate.point_biserial(scores, failed) -> tuple[float, float]`
  - `friction.evaluate.component_aucs(rows, system) -> dict[str, float]`
  - `friction.evaluate.fit_weights(rows, system, seed=0) -> tuple[dict[str, float], float, float]` returning weights, train AUC, test AUC
  - `friction.evaluate.confounds(rows, system) -> dict[str, float]`
  - `friction.evaluate.verdict(auc_value) -> str` returning `"GO"`, `"WEAK"`, or `"NO-GO"`
  - `friction.evaluate.write_report(rows, results, path) -> None`
  - `friction.evaluate.plot(rows, system, path) -> None`

- [ ] **Step 1: Write the failing test**

`tests/test_evaluate.py`:
```python
import pytest

from friction import evaluate
from friction.metric import Components


def row(iid, f1, failed, loc=1000, patch_lines=10):
    return evaluate.InstanceRow(
        instance_id=iid, repo="r",
        components=Components(f1, f1, f1, 0.5, 0.0, f1),
        failed={"sysA": failed}, repo_loc=loc, patch_lines=patch_lines,
    )


def test_auc_is_one_for_perfect_separation():
    assert evaluate.auc([0.1, 0.2, 0.8, 0.9], [False, False, True, True]) == 1.0


def test_auc_is_half_for_no_signal():
    value = evaluate.auc([0.1, 0.2, 0.3, 0.4], [False, True, False, True])
    assert value == pytest.approx(0.5)


def test_auc_returns_nan_when_one_class_missing():
    import math
    assert math.isnan(evaluate.auc([0.1, 0.2], [True, True]))


def test_point_biserial_returns_r_and_p():
    r, p = evaluate.point_biserial([0.1, 0.2, 0.8, 0.9], [False, False, True, True])
    assert r > 0.9
    assert 0.0 <= p <= 1.0


def test_verdict_thresholds():
    assert evaluate.verdict(0.70) == "GO"
    assert evaluate.verdict(0.60) == "WEAK"
    assert evaluate.verdict(0.50) == "NO-GO"


def test_verdict_boundaries_are_inclusive_at_go():
    assert evaluate.verdict(0.65) == "GO"
    assert evaluate.verdict(0.55) == "WEAK"


def test_component_aucs_reports_every_component():
    rows = [row("a", 0.1, False), row("b", 0.9, True),
            row("c", 0.2, False), row("d", 0.8, True)]
    aucs = evaluate.component_aucs(rows, "sysA")
    assert set(aucs) == {"f1", "f2", "f3", "f4", "f5", "f6"}
    assert aucs["f1"] == 1.0


def test_fit_weights_reports_train_and_test_separately():
    rows = [row(f"i{i}", i / 20, i > 10) for i in range(20)]
    weights, train_auc, test_auc = evaluate.fit_weights(rows, "sysA", seed=0)
    assert set(weights) == {"f1", "f2", "f3", "f4", "f5", "f6"}
    assert 0.0 <= train_auc <= 1.0
    assert 0.0 <= test_auc <= 1.0


def test_confounds_reports_size_and_patch_correlations():
    rows = [row(f"i{i}", i / 10, i > 5, loc=1000 * i, patch_lines=i)
            for i in range(1, 11)]
    out = evaluate.confounds(rows, "sysA")
    assert "friction_vs_repo_loc" in out
    assert "friction_vs_patch_lines" in out
    assert -1.0 <= out["friction_vs_repo_loc"] <= 1.0


def test_write_report_states_the_verdict(tmp_path):
    rows = [row("a", 0.1, False), row("b", 0.9, True)]
    results = {"system": "sysA", "auc": 0.75, "verdict": "GO",
               "point_biserial_r": 0.6, "point_biserial_p": 0.04,
               "component_aucs": {"f1": 0.75}, "confounds": {},
               "weights": evaluate.EQUAL, "train_auc": 0.8, "test_auc": 0.7,
               "per_system_auc": {"sysA": 0.75}}
    path = tmp_path / "evaluation.md"
    evaluate.write_report(rows, results, path)
    text = path.read_text()
    assert "GO" in text and "0.75" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.evaluate'`

- [ ] **Step 3: Write `src/friction/evaluate.py`**

```python
"""Does friction predict agent failure? Answer it honestly, then report it
whichever way it went.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from scipy.stats import pointbiserialr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from friction.metric import COMPONENT_NAMES, EQUAL_WEIGHTS, Components, score

EQUAL = dict(EQUAL_WEIGHTS)


@dataclass(frozen=True)
class InstanceRow:
    instance_id: str
    repo: str
    components: Components
    failed: dict[str, bool]
    repo_loc: int
    patch_lines: int


def auc(scores: list[float], failed: list[bool]) -> float:
    labels = [1 if f else 0 for f in failed]
    if len(set(labels)) < 2:
        return float("nan")
    return float(roc_auc_score(labels, scores))


def point_biserial(scores: list[float], failed: list[bool]) -> tuple[float, float]:
    labels = [1 if f else 0 for f in failed]
    if len(set(labels)) < 2:
        return float("nan"), float("nan")
    result = pointbiserialr(labels, scores)
    return float(result.correlation), float(result.pvalue)


def _scores(rows: list[InstanceRow], weights: dict[str, float]) -> list[float]:
    return [score(r.components, weights) for r in rows]


def _labels(rows: list[InstanceRow], system: str) -> list[bool]:
    return [r.failed.get(system, False) for r in rows]


def component_aucs(rows: list[InstanceRow], system: str) -> dict[str, float]:
    labels = _labels(rows, system)
    out: dict[str, float] = {}
    for name in COMPONENT_NAMES:
        values = [getattr(r.components, name) for r in rows]
        if name == "f4":
            values = [1.0 - v for v in values]
        out[name] = auc(values, labels)
    return out


def fit_weights(rows: list[InstanceRow], system: str,
                seed: int = 0) -> tuple[dict[str, float], float, float]:
    """Fit on a train split, report on a held-out split. Never fit and report
    on the same data."""
    indexed = list(range(len(rows)))
    random.Random(seed).shuffle(indexed)
    split = max(1, int(len(indexed) * 0.7))
    train_idx, test_idx = indexed[:split], indexed[split:]
    if not test_idx:
        return dict(EQUAL), float("nan"), float("nan")

    def matrix(idx):
        return [[getattr(rows[i].components, n) for n in COMPONENT_NAMES] for i in idx]

    def target(idx):
        return [1 if rows[i].failed.get(system, False) else 0 for i in idx]

    y_train = target(train_idx)
    if len(set(y_train)) < 2:
        return dict(EQUAL), float("nan"), float("nan")

    model = LogisticRegression(max_iter=2000)
    model.fit(matrix(train_idx), y_train)

    coefs = model.coef_[0]
    magnitude = sum(abs(c) for c in coefs) or 1.0
    weights = {n: abs(c) / magnitude for n, c in zip(COMPONENT_NAMES, coefs)}

    train_scores = [score(rows[i].components, weights) for i in train_idx]
    test_scores = [score(rows[i].components, weights) for i in test_idx]
    return weights, auc(train_scores, [bool(v) for v in y_train]), \
        auc(test_scores, [bool(v) for v in target(test_idx)])


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return float("nan") if dx == 0 or dy == 0 else num / (dx * dy)


def confounds(rows: list[InstanceRow], system: str) -> dict[str, float]:
    scores = _scores(rows, EQUAL)
    return {
        "friction_vs_repo_loc": _pearson(scores, [float(r.repo_loc) for r in rows]),
        "friction_vs_patch_lines": _pearson(scores, [float(r.patch_lines) for r in rows]),
    }


def verdict(auc_value: float) -> str:
    if math.isnan(auc_value):
        return "NO-GO"
    if auc_value >= 0.65:
        return "GO"
    if auc_value >= 0.55:
        return "WEAK"
    return "NO-GO"


def plot(rows: list[InstanceRow], system: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scores = _scores(rows, EQUAL)
    labels = _labels(rows, system)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    resolved = [s for s, f in zip(scores, labels) if not f]
    failed = [s for s, f in zip(scores, labels) if f]
    ax.hist([resolved, failed], bins=12, stacked=False,
            label=[f"resolved by {system}", f"failed by {system}"])
    ax.set_xlabel("Friction score (equal weights)")
    ax.set_ylabel("Instances")
    ax.set_title(f"Friction vs outcome — n={len(rows)}, AUC={auc(scores, labels):.3f}")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_report(rows: list[InstanceRow], results: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Evaluation",
        "",
        f"**Verdict: {results['verdict']}** — AUC {results['auc']:.3f} "
        f"on n={len(rows)} instances, ground truth `{results['system']}`.",
        "",
        f"Point-biserial r = {results['point_biserial_r']:.3f} "
        f"(p = {results['point_biserial_p']:.4f}).",
        "",
        "## Per-component AUC",
        "",
        "| Component | AUC |",
        "|---|---|",
    ]
    for name, value in results["component_aucs"].items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += [
        "",
        "If one component's AUC matches or beats the composite, that is the actual",
        "finding and it is reported as such rather than buried under a blend.",
        "",
        "## Weights",
        "",
        f"Fitted on a 70% train split, evaluated on the held-out 30%. "
        f"Train AUC {results['train_auc']:.3f}, held-out AUC {results['test_auc']:.3f}.",
        "",
        "| Component | Weight |",
        "|---|---|",
    ]
    for name, value in results["weights"].items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += ["", "## Confound checks", "", "| Check | Pearson r |", "|---|---|"]
    for name, value in results["confounds"].items():
        lines.append(f"| {name.replace('_', ' ')} | {value:.3f} |")
    lines += [
        "",
        "A high correlation with repo LOC would mean friction is a size proxy; a high",
        "correlation with patch line count would mean it is a patch-size proxy. Both",
        "are reported whether or not they flatter the result.",
        "",
        "## Stability across systems",
        "",
        "| System | AUC |",
        "|---|---|",
    ]
    for system, value in results["per_system_auc"].items():
        lines.append(f"| `{system}` | {value:.3f} |")
    lines += [
        "",
        "A result that holds for only one published system is measuring that system's",
        "quirks, not the code.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_evaluate.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Run the go/no-go on 50 pilot-repository instances**

Build the `InstanceRow` list for 50 instances of the pilot repository, compute AUC against the first system, and write `docs/evaluation.md` plus `docs/plots/correlation.png`.

Run the three confound checks in the same pass. Report all three regardless of outcome.

- [ ] **Step 6: THE GATE — read the verdict and branch**

| Verdict | Action |
|---|---|
| **GO** (AUC ≥ 0.65) | Continue to Task 14. Expand to 3 repositories and 150+ instances first. |
| **WEAK** (0.55–0.65) | Check `component_aucs`. If a single component beats the composite, drop the composite, build the product around that one component, and say exactly that in the README. If not, treat as NO-GO. |
| **NO-GO** (< 0.55) | Skip Tasks 14–18 as written. Go to **Task 19**. Do not attempt to rescue the thesis. |

Whatever the verdict, `docs/evaluation.md` is committed and its result appears in the README. A clearly-reported null with three confound checks is more credible than a hedged positive.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: evaluation harness with AUC, confound checks, and recorded verdict"
```

---

### Task 14: The CLI gate

Prints the score breakdown, the recommendation, **the Cypher, and the timing** — a judge assessing "use of HydraDB" has to see the engine working.

**Files:**
- Create: `substrate-friction/src/friction/cli.py`
- Create: `substrate-friction/tests/test_cli.py`

**Interfaces:**
- Consumes: `friction.metric`, `friction.paths`, `friction.evaluate`, `friction.client`, `friction.probe`.
- Produces:
  - `friction.cli.GateResult` dataclass: `instance_id: str`, `fix_sites: int`, `test_targets: int`, `components: Components`, `score: float`, `band: str`, `failure_probability: float`, `recommendation: str`, `cypher: str`, `millis: float`
  - `friction.cli.render(result) -> str`
  - `friction.cli.check(instance_id, ...) -> GateResult`
  - `friction.cli.main(argv=None) -> int` with subcommands `check` and `eval`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
from friction import cli
from friction.metric import Components


RESULT = cli.GateResult(
    instance_id="django__django-15738", fix_sites=3, test_targets=7,
    components=Components(0.82, 0.71, 0.90, 0.34, 0.88, 0.65),
    score=0.79, band="HIGH", failure_probability=0.78,
    recommendation="route to human engineer",
    cypher="CALL algo.MSpaths({...}) YIELD path, pathCost RETURN path, pathCost",
    millis=34.0,
)


def test_render_shows_every_component_label():
    text = cli.render(RESULT)
    for label in ("Path multiplicity", "Mean path length", "Intermediate spread",
                  "Convergence", "Cyclic pressure", "Fan-in load"):
        assert label in text


def test_render_shows_score_band_and_recommendation():
    text = cli.render(RESULT)
    assert "0.79" in text
    assert "HIGH" in text
    assert "route to human engineer" in text


def test_render_prints_the_cypher_and_the_timing():
    text = cli.render(RESULT)
    assert "algo.MSpaths" in text
    assert "34.0" in text or "34" in text


def test_render_includes_a_bar_for_each_component():
    text = cli.render(RESULT)
    assert text.count("█") > 0


def test_recommendation_flips_with_band():
    low = cli.recommendation("LOW")
    high = cli.recommendation("HIGH")
    assert "agent" in low.lower()
    assert "human" in high.lower()


def test_main_returns_nonzero_on_unknown_subcommand(capsys):
    assert cli.main(["nonsense"]) != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.cli'`

- [ ] **Step 3: Write `src/friction/cli.py`**

```python
"""The gate. `friction check --repo django --issue 15738`."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from friction.client import connect
from friction.config import Settings
from friction.metric import COMPONENT_LABELS, COMPONENT_NAMES, Components, band, score
from friction.paths import fan_in, fix_to_test_paths
from friction.probe import load_capabilities

BAR_WIDTH = 10


@dataclass(frozen=True)
class GateResult:
    instance_id: str
    fix_sites: int
    test_targets: int
    components: Components
    score: float
    band: str
    failure_probability: float
    recommendation: str
    cypher: str
    millis: float


def recommendation(band_value: str) -> str:
    if band_value == "HIGH":
        return "route to human engineer"
    if band_value == "MEDIUM":
        return "agent with human review of the patch"
    return "safe for agent"


def _bar(value: float) -> str:
    filled = int(round(max(0.0, min(1.0, value)) * BAR_WIDTH))
    return "█" * filled + "·" * (BAR_WIDTH - filled)


def render(result: GateResult) -> str:
    lines = [
        "",
        f"  {result.instance_id}",
        "",
        f"  Fix sites:                 {result.fix_sites} functions",
        f"  Test targets:              {result.test_targets} functions",
        "  " + "─" * 45,
    ]
    values = result.components.as_dict()
    for name in COMPONENT_NAMES:
        label = COMPONENT_LABELS[name].ljust(20)
        value = values[name]
        lines.append(f"  {label} {name.upper()}  {value:5.2f}  {_bar(value)}")
    lines += [
        "  " + "─" * 45,
        f"  FRICTION SCORE                  {result.score:5.2f}  {result.band}",
        "",
        f"  Predicted agent failure probability: {result.failure_probability:.0%}",
        f"  RECOMMENDATION: {result.recommendation}",
        "",
        f"  Query: {result.cypher}",
        f"  1 round trip, {result.millis}ms",
        "",
    ]
    return "\n".join(lines)


def check(instance_id: str, annotations_path: Path = Path("data/instances/annotations.json"),
          weights_path: Path = Path("data/instances/weights.json")) -> GateResult:
    settings = Settings.from_env()
    caps = load_capabilities(Path("docs/engine-capabilities.md"))
    transport = connect(settings, prefer="bolt")

    annotations = json.loads(Path(annotations_path).read_text())
    record = annotations[instance_id]
    fix_ids = record["fix_site_ids"]
    test_ids = record["test_target_ids"]

    path_set = fix_to_test_paths(transport, caps, settings, fix_ids, test_ids)
    fan, _, fan_millis = fan_in(transport, caps, settings, fix_ids)

    from friction.metric import raw_components
    raw = raw_components(path_set, fix_ids, test_ids, fan)

    bounds = json.loads(Path(weights_path).read_text())
    weights = bounds["weights"]
    scaled = Components(**{
        name: 0.0 if bounds["max"][name] == bounds["min"][name]
        else (getattr(raw, name) - bounds["min"][name])
        / (bounds["max"][name] - bounds["min"][name])
        for name in COMPONENT_NAMES
    })
    value = score(scaled, weights)
    band_value = band(value)

    return GateResult(
        instance_id=instance_id,
        fix_sites=len(fix_ids),
        test_targets=len(test_ids),
        components=scaled,
        score=value,
        band=band_value,
        failure_probability=value,
        recommendation=recommendation(band_value),
        cypher=path_set.cypher,
        millis=round(path_set.millis + fan_millis, 2),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="friction")
    sub = parser.add_subparsers(dest="command")

    check_cmd = sub.add_parser("check", help="score one instance")
    check_cmd.add_argument("--issue", required=True)
    check_cmd.add_argument("--annotations", default="data/instances/annotations.json")

    sub.add_parser("eval", help="print the recorded evaluation verdict")

    args = parser.parse_args(argv)
    if args.command == "check":
        print(render(check(args.issue, Path(args.annotations))))
        return 0
    if args.command == "eval":
        report = Path("docs/evaluation.md")
        if not report.exists():
            print("no evaluation report yet — run the go/no-go harness first")
            return 1
        print(report.read_text())
        return 0
    parser.print_help()
    return 2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Run the gate on a real high-friction and a real low-friction instance**

```bash
uv run friction check --issue <high-friction-instance-id>
uv run friction check --issue <low-friction-instance-id>
```

Expected: two visibly different score breakdowns, each ending with the Cypher and a millisecond timing. Pick this exact pair for the video's money shot — one the agent solved, one it failed.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: friction check CLI printing breakdown, Cypher, and timing"
```

---

### Task 15: Visualization — the visual difference is the demo

**Files:**
- Create: `substrate-friction/src/friction/viz.py`
- Create: `substrate-friction/tests/test_viz.py`

**Interfaces:**
- Consumes: `friction.paths.PathSet`.
- Produces:
  - `friction.viz.build_subgraph(path_set, fix_ids, test_ids) -> networkx.Graph` with node attribute `role` in `{"fix", "test", "intermediate"}` and edge attribute `participation: int`
  - `friction.viz.render_pair(low, high, out_path, labels) -> Path` writing a two-panel PNG

- [ ] **Step 1: Write the failing test**

`tests/test_viz.py`:
```python
from friction import viz
from friction.paths import PathSet


LOW = PathSet([[1, 2, 3]], [2.0], "c", 1.0, False)
HIGH = PathSet([[1, 2, 3], [1, 4, 3], [1, 5, 6, 3]], [2.0, 2.0, 3.0], "c", 1.0, False)


def test_roles_assigned_to_endpoints_and_intermediates():
    g = viz.build_subgraph(LOW, [1], [3])
    assert g.nodes[1]["role"] == "fix"
    assert g.nodes[3]["role"] == "test"
    assert g.nodes[2]["role"] == "intermediate"


def test_edge_participation_counts_paths_using_that_edge():
    g = viz.build_subgraph(HIGH, [1], [3])
    assert g[2][3]["participation"] == 1
    assert g.number_of_edges() >= 5


def test_high_friction_subgraph_is_denser_than_low():
    low = viz.build_subgraph(LOW, [1], [3])
    high = viz.build_subgraph(HIGH, [1], [3])
    assert high.number_of_edges() > low.number_of_edges()


def test_empty_path_set_yields_empty_graph():
    g = viz.build_subgraph(PathSet([], [], "", 0.0, False), [1], [3])
    assert g.number_of_nodes() == 0


def test_render_pair_writes_a_png(tmp_path):
    out = viz.render_pair(LOW, HIGH, tmp_path / "pair.png",
                          labels=("friction 0.21 — SAFE", "friction 0.79 — HUMAN"))
    assert out.exists() and out.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_viz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.viz'`

- [ ] **Step 3: Write `src/friction/viz.py`**

```python
"""Render the subgraph between fix sites and tests.

High-friction instances look like a hairball; low-friction ones look like a
clean line. That contrast is the demo.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from friction.paths import PathSet

COLOURS = {"fix": "#2563eb", "test": "#16a34a", "intermediate": "#9ca3af"}


def build_subgraph(path_set: PathSet, fix_ids: list[int], test_ids: list[int]) -> nx.Graph:
    graph = nx.Graph()
    fix, test = set(fix_ids), set(test_ids)

    for path in path_set.paths:
        for node in path:
            if not graph.has_node(node):
                role = "fix" if node in fix else "test" if node in test else "intermediate"
                graph.add_node(node, role=role)
        for a, b in zip(path, path[1:]):
            if graph.has_edge(a, b):
                graph[a][b]["participation"] += 1
            else:
                graph.add_edge(a, b, participation=1)
    return graph


def render_pair(low: PathSet, high: PathSet, out_path: Path,
                labels: tuple[str, str]) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, path_set, label in zip(axes, (low, high), labels):
        graph = build_subgraph(
            path_set,
            [path_set.paths[0][0]] if path_set.paths else [],
            [path_set.paths[0][-1]] if path_set.paths else [],
        )
        if graph.number_of_nodes():
            pos = nx.spring_layout(graph, seed=7, k=0.6)
            colours = [COLOURS[graph.nodes[n]["role"]] for n in graph.nodes]
            widths = [0.5 + graph[a][b]["participation"] * 0.6 for a, b in graph.edges]
            nx.draw_networkx_edges(graph, pos, ax=ax, width=widths, alpha=0.55)
            nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=colours, node_size=110)
        ax.set_title(label, fontsize=13)
        ax.axis("off")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_viz.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Render the demo pair from the two real instances chosen in Task 14**

Expected: `docs/plots/pair.png` where the contrast is obvious at a glance from across a room. If it is not obvious, pick a more extreme pair — the demo depends on this being legible in a compressed video frame.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: high- vs low-friction subgraph visualisation"
```

---

### Task 16: One-command setup with a pre-parsed graph

Judges must not run tree-sitter over Django. Ship the parsed graph as a data file. Research finding: sponsored hackathons run a mechanical first-round screen — if the project does not install and run from the README, it is eliminated before a human weighs the idea.

**Files:**
- Create: `substrate-friction/setup.sh`
- Modify: `substrate-friction/docker-compose.yml` (add the loader service)
- Create: `substrate-friction/data/shipped/README.md`
- Create: `substrate-friction/tests/test_setup.sh`

- [ ] **Step 1: Commit the pre-parsed graph**

```bash
mkdir -p data/shipped
cp data/graphs/django/nodes.ndjson data/shipped/nodes.ndjson
cp data/graphs/django/edges.ndjson data/shipped/edges.ndjson
cp data/instances/annotations.json data/shipped/annotations.json
cp data/instances/weights.json data/shipped/weights.json
gzip -kf data/shipped/nodes.ndjson data/shipped/edges.ndjson
ls -lh data/shipped/
```

If the gzipped files exceed 50 MB, cut to the subgraph reachable within `maxLen` of any annotated instance and state the reduction in `data/shipped/README.md`.

- [ ] **Step 2: Write `setup.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "==> Substrate Friction setup"

mkdir -p hydradb-data/graph hydradb-data/cache minio-data secrets
if [ ! -f secrets/token ]; then
  printf 'local-development-token-32-bytes' > secrets/token
fi

# The image runs as UID/GID 10001 and LOCAL_PATH must already exist.
if command -v sudo >/dev/null 2>&1; then
  sudo chown -R 10001:10001 hydradb-data || true
fi

echo "==> starting graph-node and MinIO"
docker compose up -d graph-node minio

echo -n "==> waiting for readiness"
for _ in $(seq 1 90); do
  if curl -sf http://127.0.0.1:9090/readyz >/dev/null 2>&1; then
    echo " ready"; break
  fi
  echo -n "."; sleep 1
done

echo "==> installing the Python package"
if command -v uv >/dev/null 2>&1; then
  uv sync --extra dev
  RUN="uv run"
else
  python3 -m venv .venv && . .venv/bin/activate && pip install -e .
  RUN=""
fi

echo "==> probing engine capabilities"
$RUN python -m friction.probe

echo "==> loading the pre-parsed graph"
gunzip -kf data/shipped/nodes.ndjson.gz data/shipped/edges.ndjson.gz 2>/dev/null || true
$RUN python -m friction.loader --dir data/shipped

echo "==> warming the cache"
$RUN friction check --issue "$(python3 -c '
import json;print(next(iter(json.load(open("data/shipped/annotations.json")))))
')" >/dev/null

echo
echo "Ready. Try:"
echo "  friction check --issue <instance-id>"
echo "  friction eval"
```

Add a `main()` to `src/friction/loader.py` accepting `--dir` so `python -m friction.loader --dir data/shipped` works:

```python
def main() -> None:
    import argparse
    from friction.client import connect
    from friction.config import Settings

    parser = argparse.ArgumentParser(prog="friction.loader")
    parser.add_argument("--dir", default="data/graphs/django")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    caps = load_capabilities(Path("docs/engine-capabilities.md"))
    transport = connect(Settings.from_env(), prefer="bolt")
    print(load(transport, caps, Path(args.dir), batch_size=args.batch_size))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Time it from a clean clone on a different machine**

```bash
chmod +x setup.sh
git clone <repo-url> /tmp/clean-clone && cd /tmp/clean-clone
time ./setup.sh
```

Expected: a working `friction check` in under 60 seconds after images are pulled. If it is slower, shrink the shipped graph — this number is what "product completeness and usability" is scored on, and a judge who cannot run it scores the idea, not the work.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: one-command setup with pre-parsed graph"
```

---

### Task 17: README — the document that wins criterion #2

**Files:**
- Create: `substrate-friction/README.md`

- [ ] **Step 1: Write all ten required sections**

Structure, in this order, with the real measured numbers substituted in:

1. **What this is** — one sentence, then the CLI output block from Task 14 as the first thing a reader sees.
2. **The thesis** — the inverted question in plain language. State up front that this is a bet and that the go/no-go result is reported below whichever way it went.
3. **Setup** — `./setup.sh`, the `export RUST_MIN_STACK=33554432` line, `just` recipes, and the **pinned HydraDB commit hash** from `docs/pinned-engine-commit.txt`.
4. **How HydraDB is used** — the criterion-#2 section. Answer three things in order:
   - *Which primitives, where*: `algo.MSpaths` computes every bounded path between the fix-site set and the test-target set in one server-side round trip (quote the actual Cypher and the measured milliseconds); `algo.SSpaths` with `relDirection` incoming and `maxLen: 1` computes fan-in.
   - *What breaks without it*: N×M client round trips per ticket. At the measured per-call latency, a 3×7 instance becomes 21 calls and the gate stops being fast enough to sit in a workflow.
   - *Why a vector index structurally cannot do this*: friction is defined over **the set of paths between two node sets**. Paths do not exist in a vector space. Two functions with near-identical text sit adjacent in embedding space while lying on completely disconnected execution paths — the embedding is blind to precisely the property being measured.
   - State honestly whether `pairwise` was available on the pinned build, per `docs/engine-capabilities.md`. Do not claim a mode that was not used.
5. **The metric** — all six components, defined, with the per-component AUC table from `docs/evaluation.md`.
6. **Evaluation** — AUC, sample size, the plot, **all three confound checks**, and any negative results, stated plainly.
7. **Limitations** — dynamic dispatch producing missing `CALLS` edges (with the measured resolution rate from Task 7), static `COVERS` over-approximating real coverage, Python only, the `maxLen` bound and why it was chosen, and the path-fidelity recall from `docs/fidelity.md`.
8. **Measured throughput** — the table from `docs/throughput.md`, framed as the engineering finding it is.
9. **Attribution** — SWE-bench and SWE-bench/experiments, tree-sitter, HydraDB (AGPL-3.0), and the AI coding assistants used.
10. **License** — MIT for this code, with the engine's AGPL-3.0 credited.

- [ ] **Step 2: Add the competitive framing paragraph near the top**

Because Track 02A and 02B are judged as one track, this README is read beside supply-chain blast-radius entries. Add two sentences immediately after the one-liner making the reframe unmissable:

> Every other tool in this space is trying to make coding agents succeed — better retrieval, better context, better prompts. This asks the inverted and much cheaper question: which tickets should we not give them at all?

- [ ] **Step 3: Verify every claim in the README against a generated file**

Every number in the README must trace to `docs/evaluation.md`, `docs/throughput.md`, `docs/fidelity.md`, or `docs/engine-capabilities.md`. Delete any number that does not.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: README with measured results, limitations, and HydraDB usage"
```

---

### Task 18: Demo video and submission

Research finding: the demo is the primary judging artifact and judges form an opinion in the first 30 seconds. Write the script before recording; rehearse the click path; record twice.

**Files:**
- Create: `substrate-friction/docs/video-script.md`

- [ ] **Step 1: Write the shot list**

| Time | Content |
|---|---|
| 0:00–0:25 | **Problem.** "Everyone is trying to make coding agents smarter. Nobody is asking the cheaper question: which tickets should we not give them at all?" |
| 0:25–0:40 | **What we built.** Substrate Friction, on self-hosted open-source HydraDB. One command. |
| 0:40–1:20 | **Money shot.** Two issues side by side. Run the gate on both. First: low friction, clean thin graph, SAFE FOR AGENT. Second: high friction, the graph explodes into a hairball, ROUTE TO HUMAN. Reveal the ground truth: the agent solved the first and failed the second. *"We knew before it tried."* |
| 1:20–1:50 | **Evidence.** The correlation plot. The AUC. The confound checks. *"This isn't repo size and it isn't patch size — we checked."* |
| 1:50–2:30 | **Why HydraDB.** `algo.MSpaths`: all fix sites against all test targets in one server-side call. Show the query and the measured milliseconds. *"Friction is a path computation. Without many-to-many bounded traversal this is 21 separate round trips per ticket."* |
| 2:30–3:00 | **Results and limits.** AUC, sample size, stated limitations. Repo link. Stop. |

Record against **local MinIO with a warm cache**. A cold query from a laptop to real S3 has been measured at ~27 seconds; that pause would end the video.

- [ ] **Step 2: Run the pre-submission checklist**

- [ ] Public repo, no access request needed
- [ ] OSI LICENSE in root
- [ ] `git log --format='%aI %s' | tail -5` — no participant-authored commit before 2026-08-12
- [ ] Clean-clone `./setup.sh` tested on a machine that is not yours
- [ ] Video under 3:00, opens without login, money shot before 1:20
- [ ] README's "How HydraDB is used" names specific primitives and states what breaks without them
- [ ] Pinned engine commit recorded
- [ ] Subset scale stated
- [ ] Go/no-go result reported whichever way it went
- [ ] All three confound checks reported

- [ ] **Step 3: Submit early**

Form: **`forms.gle/GrMYKxLj9zPQcqqc8`**. Verify every link in an incognito window first. Submit well before 2026-08-20 11:59 PM PT and screenshot the confirmation.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs: video script and submission checklist"
```

---

### Task 19: PIVOT — Common Cause (only if Task 13 returned NO-GO)

Thesis-certain. Retrospective instead of prospective. Everything already built — parser, graph, loader, path queries, CLI shell — carries over. Do not try to rescue the friction thesis.

**Files:**
- Create: `substrate-friction/src/friction/common_cause.py`
- Create: `substrate-friction/tests/test_common_cause.py`

**Interfaces:**
- Consumes: `friction.paths`, `friction.probe.Capabilities`.
- Produces:
  - `friction.common_cause.tally(paths_by_instance) -> dict[int, int]` — how many *independent* instances each intermediate node lies on
  - `friction.common_cause.rank(tallies, top_n=10) -> list[tuple[int, int]]`
  - `friction.common_cause.validate(train_paths, held_out_paths, top_n=5) -> dict[str, float]`
  - `friction.common_cause.bootstrap_ci(paths_by_instance, node_id, trials=1000, seed=0) -> tuple[float, float]`

- [ ] **Step 1: Write the failing test**

`tests/test_common_cause.py`:
```python
from friction import common_cause as cc


PATHS = {
    "i1": [[1, 99, 3]],
    "i2": [[4, 99, 6]],
    "i3": [[7, 8, 9]],
    "i4": [[10, 99, 12]],
}


def test_tally_counts_instances_not_paths():
    counts = cc.tally({"i1": [[1, 99, 3], [1, 99, 4]]})
    assert counts[99] == 1


def test_tally_excludes_endpoints():
    counts = cc.tally({"i1": [[1, 99, 3]]})
    assert 1 not in counts and 3 not in counts


def test_rank_puts_the_common_node_first():
    ranked = cc.rank(cc.tally(PATHS))
    assert ranked[0][0] == 99
    assert ranked[0][1] == 3


def test_validate_reports_hit_rate_on_held_out():
    train = {k: PATHS[k] for k in ("i1", "i2")}
    held = {k: PATHS[k] for k in ("i3", "i4")}
    out = cc.validate(train, held, top_n=1)
    assert out["held_out_hit_rate"] == 0.5


def test_bootstrap_ci_returns_ordered_bounds():
    low, high = cc.bootstrap_ci(PATHS, 99, trials=200, seed=1)
    assert 0.0 <= low <= high <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_common_cause.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'friction.common_cause'`

- [ ] **Step 3: Write `src/friction/common_cause.py`**

```python
"""Common Cause: which structural element lies on the most independent bug paths.

Aviation crash investigation, for code. Investigators do not fix individual
crashes; they find the latent condition shared across many. This makes no
predictive claim — it measures something that demonstrably exists.

The query is the same `algo.MSpaths` call as the friction metric, with issue
entry points as sources and fix sites as targets.
"""

from __future__ import annotations

import random
from collections import Counter


def tally(paths_by_instance: dict[str, list[list[int]]]) -> dict[int, int]:
    """Count instances — not paths — whose paths pass through each node."""
    counts: Counter[int] = Counter()
    for paths in paths_by_instance.values():
        seen: set[int] = set()
        for path in paths:
            seen.update(path[1:-1])
        counts.update(seen)
    return dict(counts)


def rank(tallies: dict[int, int], top_n: int = 10) -> list[tuple[int, int]]:
    return sorted(tallies.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]


def validate(train_paths: dict[str, list[list[int]]],
             held_out_paths: dict[str, list[list[int]]],
             top_n: int = 5) -> dict[str, float]:
    """Do the training set's top nodes appear on held-out incident paths?"""
    top = {node for node, _ in rank(tally(train_paths), top_n)}
    if not held_out_paths:
        return {"held_out_hit_rate": 0.0, "instances": 0.0}

    hits = 0
    for paths in held_out_paths.values():
        nodes: set[int] = set()
        for path in paths:
            nodes.update(path[1:-1])
        if nodes & top:
            hits += 1
    return {
        "held_out_hit_rate": hits / len(held_out_paths),
        "instances": float(len(held_out_paths)),
    }


def bootstrap_ci(paths_by_instance: dict[str, list[list[int]]], node_id: int,
                 trials: int = 1000, seed: int = 0) -> tuple[float, float]:
    """With only dozens of instances the top node can be unstable. Report an
    interval, not a single name."""
    keys = list(paths_by_instance)
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    rates: list[float] = []
    for _ in range(trials):
        sample = [rng.choice(keys) for _ in keys]
        counts = tally({f"{k}#{i}": paths_by_instance[k]
                        for i, k in enumerate(sample)})
        rates.append(counts.get(node_id, 0) / len(sample))
    rates.sort()
    return rates[int(0.025 * len(rates))], rates[int(0.975 * len(rates)) - 1]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_common_cause.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Rework Tasks 14–18 for the pivot**

- CLI subcommand becomes `friction common-cause --repo django`, ranking load-bearing nodes with confidence intervals.
- Visualization becomes the money shot: fifty red threads from unrelated bugs fanning across the repo graph, all bending through one node that flares white. *"Fifty incidents. One load-bearing wall."*
- Baselines to beat, all computed on the same graph: PageRank, raw in-degree, global betweenness. Report all three.
- README states plainly that the friction thesis was tested, did not hold, and the reported AUC is what it was — then presents Common Cause as what the same graph does support. A clearly-reported null with three confound checks reads as rigour, not failure.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: Common Cause pivot with held-out validation and bootstrap intervals"
```

---

## Self-Review

**1. Spec coverage.** Every part of `substrate-friction-build-spec.md` maps to a task: Part 1 constraints → Global Constraints + Task 3; Part 2 data → Task 5; Part 3 model → Tasks 6–8; Part 4 ingest → Tasks 4, 9; Part 5 metric → Tasks 10, 12; Part 6 go/no-go → Task 13; Part 7 product → Tasks 14–17; Part 8 schedule → dropped at the user's instruction, replaced by the Task 13 gate as the only ordering constraint that matters; Part 9 pivot → Task 19; Part 10 failure modes → Tasks 3, 11, 13, 16; Part 11 definition of done → Task 18; Part 12 anti-goals → Global Constraints.

**Two additions the spec does not contain**, both forced by research: Task 3 (capability probe) exists because `pairwise` is undocumented and the spec's edge-loader form contradicts documented `UNWIND` restrictions; Task 11 (fidelity guard) exists because silent path truncation biases F1 and F3 in the exact direction that would suppress the signal.

**2. Placeholder scan.** One deliberate residue: Task 5 Step 5 requires reading real folder names out of `SWE-bench/experiments` at runtime rather than hardcoding names that may not exist. Task 14 Step 5 and Task 15 Step 5 take instance ids chosen from real data. These are data-dependent by nature, not undefined work.

**3. Type consistency.** `Components` uses `f1`–`f6` throughout `metric`, `evaluate`, `cli`, and `viz`. `Edge(src, dst, type, weight)` is consistent across `calls`, `covers`, `loader`, and `fidelity`. `PathSet(paths, costs, cypher, millis, truncated)` is consistent across `paths`, `metric`, and `viz`. `Capabilities` field names match between `probe.derive`, `paths.build_mspaths_cypher`, and `loader.node_statement`/`edge_statement`. One correction applied inline: Task 3's module must import `from friction.config import Settings` only — the `connect_default` shim named in the first draft does not exist and is called out in the step text.

---

## What the research changed, in one place

- **`pairwise` is not in `cypher-compat.md`.** The spec calls it the heart of the project. Task 3 probes it; Task 10 emits it only if it parses; the README states which build was used. ([cypher-compat.md](https://raw.githubusercontent.com/hydra-db/hydradb/main/cypher-compat.md))
- **`relDirection` is documented only as lowercase `'both'`.** Never hardcode `'BOTH'`.
- **The spec's `UNWIND / MATCH / MATCH / CREATE` edge loader contradicts the documented restrictions.** Four candidate forms are probed and the loader uses whichever parses.
- **Ground truth lives in `SWE-bench/experiments`**, per-submission, discovered at runtime rather than guessed. ([SWE-bench/experiments](https://github.com/SWE-bench/experiments))
- **Sponsored hackathons screen mechanically first** — if it does not install from the README, no human weighs the idea. That is why Task 16 is a task and not a footnote. ([JetBrains — notes from the judging table](https://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/), [Devpost — advice from 5 judges](https://info.devpost.com/blog/hackathon-judging-tips))
- **Python static call resolution has no IR to lean on**, so the resolver is deliberately conservative and reports its own resolution rate rather than implying completeness. ([ACER, arXiv 2308.15669](https://arxiv.org/pdf/2308.15669))

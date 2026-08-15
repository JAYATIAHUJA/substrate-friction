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

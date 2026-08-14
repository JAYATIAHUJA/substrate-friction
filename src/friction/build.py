"""Build and load per-instance django code graphs for the evaluation gate.

Why per-instance, and why id namespacing instead of separate graphs
-------------------------------------------------------------------
SWE-bench django ``base_commit`` values are effectively unique: 230 distinct
commits across 231 instances (the largest group is two instances). So a
"per-base-commit" graph is, in practice, a per-instance graph -- there is no
consolidation to be had. ``choose_strategy`` measures this and selects
``per_instance``.

Correctness hazard this module exists to defeat: fix sites are derived by
mapping a gold patch's changed line ranges onto Function ``line_start`` /
``line_end``. Those line numbers are only meaningful against the instance's own
``base_commit``. ``build_instance_graph`` therefore checks out the base_commit
in the shared django clone before parsing, so every instance is parsed against
the exact tree its patch was written for.

Isolation on this deployment (measured, not assumed)
----------------------------------------------------
The brief offered two isolation mechanisms; both are blocked on the pinned
single-node deployment, and this is a reported finding:

* Separate graph name per commit -> HTTP ``/v1/graphs/<name>/query`` returns
  ``403 permission_denied`` for any name other than ``default`` (the node is
  configured with ``GRAPH_ID=default`` and the token is scoped to
  ``default/graphs/default``; there is no reachable graph-create endpoint).
* Clear the graph between loads -> ``DELETE`` / ``DETACH DELETE`` scans the
  full relationship set per operation (roughly O(edges) each) and exceeds the
  engine's 29999 ms per-query timeout even for a few hundred nodes. Clearing a
  ~118k-edge django graph is impractical.

The mechanism that does work at django scale is **disjoint id namespacing**
inside the single ``default`` graph: instance ``i`` is loaded with every node
id, ``sid``, edge endpoint, fix-site id and test-target id offset by
``instance_base(i)``. Bands are disjoint and no edge crosses a band, so a path
query seeded in one instance's band can never reach another's nodes. A bonus
over clear-between-loads: all instance graphs stay resident simultaneously, so
the evaluation gate queries the live engine without reloading.

The ``graph`` name returned per instance is a logical label (``g_<commit12>``)
recorded alongside the numeric id band in the manifest; queries are scoped by
the band, not by a physical graph namespace.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

from friction.config import Settings
from friction.loader import emit_ndjson, load
from friction.parsing.calls import resolve
from friction.parsing.covers import derive_covers
from friction.parsing.patches import fix_site_ids, test_target_ids
from friction.parsing.symbols import parse_repo
from friction.probe import Capabilities

# --- id namespacing -------------------------------------------------------
# Bands start well above any residual low-id node left in ``default`` and are
# spaced far wider than any single django graph (~35k nodes), so no two
# instances' ids can collide.
#
# The engine cannot delete the graphs already resident in ``default``
# (DETACH DELETE on a django-scale graph exceeds the 29999 ms query timeout),
# so a rebuild cannot reuse the old id region. This base sits far above the
# first build's occupied span (100_000_000 .. ~590_035_442), giving every
# rebuilt instance a fresh, disjoint band: instance i occupies
# [2_000_000_000 + i*10_000_000, +~35k]. With 50 instances the top band is
# 2_490_000_000 .. ~2_490_035_442 -- ~1.4e9 clear of the old region's top and,
# at ~35k nodes per graph vs a 10_000_000 stride, no band can reach the next.
GRAPH_BASE = 2_000_000_000
GRAPH_STRIDE = 10_000_000


def instance_base(index: int) -> int:
    """Id offset for the ``index``-th instance's graph band."""
    if index < 0:
        raise ValueError("index must be non-negative")
    return GRAPH_BASE + index * GRAPH_STRIDE


def graph_name(base_commit: str) -> str:
    """Logical, deterministic graph label for a base_commit.

    Instances sharing a base_commit share a graph label (same code, same ids).
    """
    return f"g_{base_commit[:12]}"


def batched(seq: list, size: int) -> Iterator[list]:
    """Yield ``seq`` in chunks of at most ``size`` (size >= 1)."""
    if size < 1:
        raise ValueError("size must be >= 1")
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def choose_strategy(instances: Iterable) -> dict:
    """Pick a graph-building strategy from the base_commit distribution.

    Returns a dict describing the choice. ``per_instance`` is selected when
    commits are mostly unique (no group large enough to make per-base-commit
    consolidation worthwhile); ``per_base_commit`` when a handful of commits
    dominate. ``single_commit`` is only ever a caller's explicit fallback and is
    never selected here.
    """
    commits = Counter(getattr(i, "base_commit") for i in instances)
    n_instances = sum(commits.values())
    distinct = len(commits)
    largest = max(commits.values()) if commits else 0
    # Instances covered by the largest 10 commit groups.
    top10 = sum(n for _, n in commits.most_common(10))
    consolidation = 1.0 - (distinct / n_instances) if n_instances else 0.0

    if consolidation < 0.15:
        strategy = "per_instance"
        rationale = (
            f"{distinct} distinct base_commits across {n_instances} instances "
            f"(largest group {largest}); per-base-commit consolidation would "
            f"save almost nothing, so build one graph per instance."
        )
    else:
        strategy = "per_base_commit"
        rationale = (
            f"{distinct} distinct base_commits across {n_instances} instances; "
            f"the largest 10 groups cover {top10} instances, so build one graph "
            f"per base_commit and reuse it across the group."
        )

    return {
        "strategy": strategy,
        "n_instances": n_instances,
        "distinct_commits": distinct,
        "largest_group": largest,
        "top10_coverage": top10,
        "consolidation_ratio": round(consolidation, 4),
        "rationale": rationale,
    }


# --- offset transforms (pure) ---------------------------------------------

def offset_node_row(row: dict, base: int) -> dict:
    """Return a copy of a node ndjson row with id/sid shifted into the band."""
    out = dict(row)
    new_id = row["id"] + base
    out["id"] = new_id
    out["sid"] = str(new_id)
    if "file_id" in out and out["file_id"] is not None:
        out["file_id"] = out["file_id"] + base
    return out


def offset_edge_row(row: dict, base: int) -> dict:
    """Return a copy of an edge ndjson row with endpoints shifted into the band."""
    out = dict(row)
    out["src"] = row["src"] + base
    out["dst"] = row["dst"] + base
    return out


def _rewrite_offset(out_dir: Path, base: int) -> None:
    """Rewrite nodes.ndjson / edges.ndjson in place, offsetting ids by ``base``."""
    out_dir = Path(out_dir)
    for name, fn in (("nodes.ndjson", offset_node_row),
                     ("edges.ndjson", offset_edge_row)):
        path = out_dir / name
        lines = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    lines.append(json.dumps(fn(json.loads(line), base)))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- test-patch application -----------------------------------------------
# SWE-bench evaluates a fix by applying the instance's ``test_patch`` and
# running FAIL_TO_PASS. Those test functions therefore belong in the graph --
# they are exactly "the tests that validate the fix", which the friction metric
# measures paths *to*. But the graph is (correctly) built at bare
# ``base_commit``, the tree where those newly-introduced tests do not yet exist,
# so at base_commit they are unreachable by construction. Applying the
# ``test_patch`` to the working tree before parsing makes them exist.
#
# This does not move fix-site line numbers: in SWE-bench the gold patch touches
# source files and the test_patch touches test files, and across all 231 django
# instances the two file sets are disjoint (0 overlap, verified), so applying
# only the test_patch cannot shift a line in any file the gold patch edits.


def _apply_command_sequence(repo_root: Path) -> list[list[str]]:
    """Ordered commands tried to apply a test patch (patch read from stdin).

    ``git apply`` is atomic (it either applies cleanly or touches nothing), so a
    failed first attempt leaves the tree untouched for the next. ``--3way`` can
    fall back on blob context when a strict apply fails; ``patch -p1`` is the
    last resort for patches git rejects for whitespace/fuzz reasons.
    """
    r = str(repo_root)
    return [
        ["git", "-C", r, "apply", "--whitespace=nowarn", "-"],
        ["git", "-C", r, "apply", "--3way", "--whitespace=nowarn", "-"],
        ["patch", "-p1", "-d", r, "--force"],
    ]


def _run_apply(cmd: list[str], patch_text: str) -> int:
    """Run one apply command, feeding ``patch_text`` on stdin; return exit code."""
    proc = subprocess.run(cmd, input=patch_text, text=True,
                          capture_output=True)
    return proc.returncode


def apply_test_patch(repo_root: Path, test_patch: str, runner=_run_apply) -> bool:
    """Apply an instance's test_patch to the working tree at ``repo_root``.

    Tries ``git apply``, then ``git apply --3way``, then ``patch -p1`` in order,
    stopping at the first command that exits 0. Returns ``True`` if any
    succeeded, ``False`` otherwise (including an empty/blank patch). ``runner``
    is injectable so the command-selection and failure-handling logic can be
    unit-tested without a real clone.
    """
    if not test_patch or not test_patch.strip():
        return False
    for cmd in _apply_command_sequence(Path(repo_root)):
        if runner(cmd, test_patch) == 0:
            return True
    return False


# --- engine build ---------------------------------------------------------

def _checkout(repo_root: Path, base_commit: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), "checkout", "-q", base_commit],
                   check=True)


def _restore(repo_root: Path) -> None:
    """Return the clone to a clean tree: discard tracked edits and untracked
    files (e.g. a partially-applied patch or ``.rej`` / ``.orig`` residue) so
    the next instance starts from a pristine base_commit. Scoped to the clone.
    """
    r = str(repo_root)
    subprocess.run(["git", "-C", r, "checkout", "-q", "--", "."], check=False)
    subprocess.run(["git", "-C", r, "clean", "-fdq"], check=False)


def build_instance_graph(instance, repo_root: Path, transport, caps: Capabilities,
                         settings: Settings, index: int = 0,
                         work_dir: Path | None = None,
                         repo_code: int = 0) -> dict:
    """Check out an instance's base_commit, parse it, and load its graph.

    Every node id, sid, edge endpoint, fix-site id and test-target id is offset
    into the instance's disjoint id band (``instance_base(index)``). Returns a
    dict with at least instance_id, graph, nodes, edges, seconds, plus the id
    band and the offset fix-site / test-target ids for the evaluation gate.
    """
    repo_root = Path(repo_root)
    base = instance_base(index)
    if work_dir is None:
        work_dir = Path("data/instances/graphs") / instance.instance_id
    work_dir = Path(work_dir)

    timings: dict[str, float] = {}

    t = time.perf_counter()
    # Start from a pristine tree, then pin to this instance's base_commit.
    _restore(repo_root)
    _checkout(repo_root, instance.base_commit)
    timings["checkout"] = time.perf_counter() - t

    # Apply the instance's test_patch so its FAIL_TO_PASS tests exist in the
    # tree being parsed. On failure, discard any partial application and parse
    # the unpatched tree rather than aborting the whole build -- but record it.
    t = time.perf_counter()
    test_patch = getattr(instance, "test_patch", "") or ""
    test_patch_applied = apply_test_patch(repo_root, test_patch)
    if not test_patch_applied and test_patch.strip():
        _restore(repo_root)
        _checkout(repo_root, instance.base_commit)
    timings["test_patch"] = time.perf_counter() - t

    try:
        t = time.perf_counter()
        table = parse_repo(repo_root, repo_code)
        timings["parse"] = time.perf_counter() - t

        t = time.perf_counter()
        edges = resolve(repo_root, table)
        timings["resolve"] = time.perf_counter() - t

        t = time.perf_counter()
        covers = derive_covers(table, edges)
        timings["covers"] = time.perf_counter() - t
    finally:
        # Always leave the clone clean for the next instance, even on error.
        _restore(repo_root)

    # Fix sites and test targets are computed against THIS base_commit's tree.
    fix_ids = [i + base for i in fix_site_ids(instance.patch, table)]
    test_ids = [i + base for i in test_target_ids(instance.fail_to_pass, table)]

    t = time.perf_counter()
    emit_ndjson(table, edges + covers, work_dir)
    _rewrite_offset(work_dir, base)
    timings["emit"] = time.perf_counter() - t

    t = time.perf_counter()
    counts = load(transport, caps, work_dir)
    timings["load"] = time.perf_counter() - t

    n_nodes = sum(v for k, v in counts.items()
                  if k in ("File", "Class", "Function"))
    n_edges = sum(v for k, v in counts.items()
                  if k not in ("File", "Class", "Function"))

    return {
        "instance_id": instance.instance_id,
        "base_commit": instance.base_commit,
        "graph": graph_name(instance.base_commit),
        "id_base": base,
        "id_range": [base, base + table._counter],
        "nodes": n_nodes,
        "edges": n_edges,
        "counts": dict(counts),
        "test_patch_applied": test_patch_applied,
        "fix_site_ids": fix_ids,
        "test_target_ids": test_ids,
        "seconds": round(sum(timings.values()), 3),
        "timings": {k: round(v, 3) for k, v in timings.items()},
    }


def build_many(instances: list, repo_root: Path, transport, caps: Capabilities,
               settings: Settings, work_dir: Path | None = None,
               manifest_path: Path = Path("data/instances/graphs.json"),
               limit: int | None = None,
               repo_code: int = 0) -> list[dict]:
    """Build graphs for ``instances`` (up to ``limit``), writing a manifest.

    Each instance is loaded into its own id band so all graphs coexist in the
    single ``default`` graph without collision. The manifest is rewritten after
    every instance so a mid-run failure still leaves a usable record.
    """
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    selected = instances if limit is None else instances[:limit]

    records: list[dict] = []
    for index, instance in enumerate(selected):
        rec = build_instance_graph(
            instance, repo_root, transport, caps, settings,
            index=index,
            work_dir=None if work_dir is None else Path(work_dir) / instance.instance_id,
            repo_code=repo_code,
        )
        records.append(rec)
        _write_manifest(manifest_path, records)
    return records


def _write_manifest(manifest_path: Path, records: list[dict]) -> None:
    manifest = [
        {
            "instance_id": r["instance_id"],
            "base_commit": r["base_commit"],
            "graph": r["graph"],
            "id_base": r["id_base"],
            "id_range": r["id_range"],
            "nodes": r["nodes"],
            "edges": r["edges"],
            "test_patch_applied": r.get("test_patch_applied", None),
            "fix_site_ids": r["fix_site_ids"],
            "test_target_ids": r["test_target_ids"],
            "seconds": r["seconds"],
        }
        for r in records
    ]
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

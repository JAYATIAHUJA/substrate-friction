"""Per-instance annotation side-table for the evaluation gate.

For every instance that has a graph (``data/instances/graphs.json``) this builds
a record carrying the fix-site and test-target Function node ids (offset into the
instance's id band, matching the loaded graph), the parsed repo LOC, the gold
patch size, and each cached system's pass/fail label.

The heavy path (``build_annotations``) checks out each instance's ``base_commit``
in the shared django clone and re-parses it, exactly as ``friction.build`` does,
so fix-site line numbers are interpreted against the tree the patch was written
for. The pure helpers are unit-tested; the git/parse orchestration is not (it
needs a real clone), mirroring ``friction.build``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from friction.parsing.patches import fix_site_ids, test_target_ids
from friction.parsing.symbols import SymbolTable, parse_repo


def patch_line_count(patch: str) -> int:
    """Added + removed lines in a unified diff (hunk/file headers excluded)."""
    n = 0
    for line in patch.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            n += 1
    return n


def repo_loc(table: SymbolTable) -> int:
    """Total lines of code across every parsed file."""
    return sum(f.loc for f in table.files)


def annotate_instance(instance, table: SymbolTable, id_base: int, graph: str,
                      resolved_by: dict[str, set[str]]) -> dict:
    """Build one annotation record.

    ``fix_site_ids`` / ``test_target_ids`` are offset by ``id_base`` so they name
    the actual loaded graph nodes (same convention as ``friction.build``). An
    instance is FAILED by a system when its id is not in that system's resolved
    set.
    """
    fix = [i + id_base for i in fix_site_ids(instance.patch, table)]
    test = [i + id_base for i in test_target_ids(instance.fail_to_pass, table)]
    return {
        "instance_id": instance.instance_id,
        "repo": instance.repo,
        "graph": graph,
        "fix_site_ids": fix,
        "test_target_ids": test,
        "repo_loc": repo_loc(table),
        "patch_lines": patch_line_count(instance.patch),
        "failed": {
            system: instance.instance_id not in resolved
            for system, resolved in resolved_by.items()
        },
    }


def sanity_report(annotations: dict[str, dict]) -> dict:
    """The gate: percent of instances with non-empty fix sites / test targets.

    ``mapping_sane`` is true only if BOTH are >= 70%.
    """
    n = len(annotations)
    if n == 0:
        return {
            "pct_nonempty_fix_sites": 0.0,
            "pct_nonempty_test_targets": 0.0,
            "mapping_sane": False,
            "n_instances": 0,
        }
    fix = sum(1 for a in annotations.values() if a["fix_site_ids"])
    test = sum(1 for a in annotations.values() if a["test_target_ids"])
    pf = round(100.0 * fix / n, 2)
    pt = round(100.0 * test / n, 2)
    return {
        "pct_nonempty_fix_sites": pf,
        "pct_nonempty_test_targets": pt,
        "mapping_sane": pf >= 70.0 and pt >= 70.0,
        "n_instances": n,
    }


def _checkout(repo_root: Path, base_commit: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), "checkout", "-q", base_commit],
                   check=True)


def build_annotations(instances_by_id: dict, manifest: list[dict],
                      repo_root: Path, resolved_by: dict[str, set[str]],
                      repo_code: int = 0) -> dict[str, dict]:
    """Check out and re-parse each manifest instance, returning annotations.

    ``manifest`` is the ``graphs.json`` list (each item carries ``instance_id``,
    ``id_base`` and ``graph``). Parses are cached per ``base_commit`` so shared
    commits are only parsed once.
    """
    repo_root = Path(repo_root)
    annotations: dict[str, dict] = {}
    cache: dict[str, SymbolTable] = {}
    for rec in manifest:
        iid = rec["instance_id"]
        instance = instances_by_id[iid]
        commit = rec["base_commit"]
        table = cache.get(commit)
        if table is None:
            _checkout(repo_root, commit)
            table = parse_repo(repo_root, repo_code)
            cache[commit] = table
        annotations[iid] = annotate_instance(
            instance, table, rec["id_base"], rec["graph"], resolved_by)
    return annotations

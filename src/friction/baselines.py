"""Cheap non-graph predictors of agent failure.

Any structural claim has to clear these. Published context for SWE-bench
Verified: a task-agnostic prior reaches ~0.718 AUC, problem-statement text alone
reaches ~0.787, and the best published combined model reaches 0.841
(arXiv 2604.00594). Patch scope is the strongest simple signal in the
literature: single-file, <5-line fixes solve ~48% of the time while >=3 files or
>100 lines drop below 10% (arXiv 2505.23419).

Label orientation: throughout, ``failed=True`` is the positive class. An AUC
above 0.5 means larger feature values track agent *failure*.
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


def _counts_unidiff(patch: str) -> tuple[int, int, int]:
    ps = PatchSet(patch)
    files = len(ps)
    hunks = sum(len(pf) for pf in ps)
    changed = sum(
        1 for pf in ps for hunk in pf for ln in hunk if ln.is_added or ln.is_removed
    )
    return files, hunks, changed


def _counts_manual(patch: str) -> tuple[int, int, int]:
    """Hunk-aware fallback for diffs strict unidiff rejects.

    Real SWE-bench patches are well-formed and go through unidiff; this path only
    fires when a hunk header's declared line counts do not match its body (as in
    hand-written terse diffs). Counting is scoped to hunk bodies so file-content
    lines that themselves begin with '+'/'-' are attributed correctly, and the
    '--- '/'+++ ' file headers (space-suffixed) are never miscounted as changes.
    """
    files = hunks = changed = 0
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            files += 1
            in_hunk = False
        elif line.startswith("@@"):
            hunks += 1
            in_hunk = True
        elif line.startswith("--- ") or line.startswith("+++ "):
            in_hunk = False
        elif in_hunk and line[:1] in ("+", "-"):
            changed += 1
    return files, hunks, changed


def extract(instance) -> Features:
    patch = instance.patch or ""
    try:
        files, hunks, changed = _counts_unidiff(patch)
    except Exception:  # noqa: BLE001 — strict parse failed; count leniently
        files, hunks, changed = _counts_manual(patch)
    stmt = instance.problem_statement or ""
    return Features(
        patch_lines=int(changed),
        patch_files=int(files),
        patch_hunks=int(hunks),
        f2p_count=len(instance.fail_to_pass or []),
        statement_chars=len(stmt),
        statement_has_traceback="Traceback (most recent call last)" in stmt,
    )


def table(instances, failed_by_id: dict[str, bool]) -> dict[str, float]:
    """One AUC per single feature. ``failed=True`` is the positive class."""
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

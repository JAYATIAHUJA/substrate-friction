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

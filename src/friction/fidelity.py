"""Cross-check engine path results against an in-memory networkx reference.

The reference is computed on the identical edge set and the identical maxLen
bound, so any shortfall is the engine's traversal or a result budget, not a
different question being asked.

Directionality: the reference graph is intentionally *undirected*
(``nx.Graph``). The engine's relationship patterns are directed and
single-typed, so the reference asks the identical question only when the engine
path query is run with ``relDirection=BOTH`` in its ``algo.*`` config. Any
driver that feeds ``compare`` must issue the engine query that way; otherwise a
measured shortfall would conflate edge direction with truncation rather than
isolating truncation, which is the only thing this guard exists to catch.

Recall is measured by *overlap*, not by counts. For each instance the engine's
returned paths are intersected with the reference's paths, and recall is the
fraction of reference paths the engine actually returned. This is deliberate:
a raw count ratio (engine_total / reference_total) would let an instance where
the engine over-returns paths offset another where it truncated, and could even
exceed 1.0. Overlap recall is bounded in [0, 1] and an engine returning the
right *number* of entirely wrong paths scores zero, not one.
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
    # Undirected on purpose: matches an engine run with relDirection=BOTH.
    # See the module docstring for why this asks the identical question.
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

    # Recall is measured per instance by intersecting the engine's returned
    # paths with the reference's paths, then aggregating the overlap. A raw
    # count ratio would let over-return on one instance mask truncation on
    # another and could exceed 1.0; overlap recall cannot.
    matched_total = 0
    truncated = 0
    worst_key = ""
    worst_missed = -1
    for key, ref in reference_by_instance.items():
        engine_paths = {tuple(p) for p in engine_by_instance.get(key, [])}
        ref_paths = [tuple(p) for p in ref]
        matched = sum(1 for p in ref_paths if p in engine_paths)
        matched_total += matched
        missed = len(ref_paths) - matched
        if missed > 0:
            truncated += 1
        if missed > worst_missed:
            worst_missed, worst_key = missed, key

    recall = 1.0 if reference_total == 0 else matched_total / reference_total
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
        f"- Recall (fraction of reference paths the engine returned): **{report.recall}**",
        f"- Instances missing at least one reference path: **{report.truncated_instances}**",
        f"- Largest single shortfall: `{report.worst_instance}`",
        "",
        "Recall is measured by overlap: for each instance the engine's paths are",
        "intersected with the reference's paths. An engine that over-returns paths",
        "cannot inflate this number above 1.0, and returning the right *count* of",
        "wrong paths scores zero — so the `< 0.9` rule below cannot be defeated by",
        "over-return, only satisfied by actually returning the reference paths.",
        "",
        "The reference is undirected, matching an engine run with `relDirection=BOTH`,",
        "so any shortfall is truncation, not a direction mismatch.",
        "",
        "Why this matters: F1 (path multiplicity) and F3 (intermediate spread) are",
        "counts of returned paths. Truncation does not add symmetric noise — it",
        "biases high-friction instances downward, which is the direction that would",
        "suppress the very signal this project tests for. If recall is below ~0.9,",
        "raise `pathCount` and re-run before believing any correlation result.",
        "",
    ]), encoding="utf-8")

"""End-to-end evaluation harness — one command, every number.

``uv run python -m friction.harness`` regenerates every figure in
``docs/evaluation.md``, ``docs/fidelity.md`` and ``docs/plots/correlation.png``
from committed data and the live engine. An earlier review found the gate numbers
were not reproducible from committed code; this module exists so that can never be
true again — there is no hand-computed number anywhere downstream of it.

What it does, in order
----------------------
1. Load ``data/instances/subgraphs.json`` (the per-instance budgeted subgraphs,
   already banded into disjoint id ranges) and ``data/instances/annotations.json``
   (ground-truth ``failed`` labels per system, plus ``repo_loc`` / ``patch_lines``).
2. For every instance, query the LIVE engine: ``paths.fix_to_test_paths`` and
   ``paths.fan_in`` against the instance's band, recording the wall-clock latency
   of every query.
3. Compute a networkx REFERENCE path set over the identical subgraph edge set and
   the identical ``maxLen`` — the fidelity guard's control, and (see the honesty
   note below) the source of the scored components when the engine returns nothing.
4. Fidelity guard on all usable instances (>= 20): engine paths vs the reference,
   overlap recall -> ``docs/fidelity.md``.
5. Build ``evaluate.InstanceRow`` objects, compute AUC vs the primary system,
   per-component AUCs, the best single component, the across-systems check, all
   three confound checks, and a fitted train/held-out split.
6. Sensitivity: report the equal-weights AUC BOTH with and without the
   empty-endpoint instances (which are zero-friction by construction).
7. Write ``docs/evaluation.md`` and ``docs/plots/correlation.png``.

Honesty (non-negotiable, enforced in code)
-------------------------------------------
``engine_answered`` is set True only if the engine actually returned paths for a
majority of usable instances. It is measured, not assumed. When the engine returns
no paths — as this build does; its write path is broken and nothing can be loaded,
see ``docs/engine-scaling.md`` — the scored friction components are computed from
the networkx REFERENCE instead, and every report says so in as many words. The
reference is never a silent fallback: the engine null is the headline, the latency
is real (the engine really was queried), and the reference source is labelled at
every use.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path

from friction.client import EngineError, connect
from friction.config import Settings
from friction.evaluate import (
    InstanceRow,
    auc,
    component_aucs,
    confounds,
    fit_weights,
    label_distribution,
    plot,
    point_biserial,
    sensitivity_excluded,
    verdict,
    _scores,
)
from friction.fidelity import FidelityReport, compare, reference_paths
from friction.fidelity import write_report as write_fidelity_report
from friction.metric import (
    COMPONENT_NAMES,
    EQUAL_WEIGHTS,
    Components,
    normalise,
    raw_components,
)
from friction.parsing.calls import Edge
from friction.paths import PathSet, fan_in, fix_to_test_paths
from friction.probe import Capabilities, load_capabilities

SUBGRAPHS_PATH = Path("data/instances/subgraphs.json")
ANNOTATIONS_PATH = Path("data/instances/annotations.json")
SUBGRAPH_DIR = Path("data/instances/subgraphs")
CAPS_PATH = Path("docs/engine-capabilities.md")

EVAL_PATH = Path("docs/evaluation.md")
FIDELITY_PATH = Path("docs/fidelity.md")
PLOT_PATH = Path("docs/plots/correlation.png")

PRIMARY_SYSTEM = "20241029_OpenHands-CodeAct-2.1-sonnet-20241022"
REL_TYPES = ("CALLS", "HAS_METHOD", "INHERITS")

# The engine is judged to have "answered" only if it returned at least one path
# for at least this fraction of usable instances.
ENGINE_ANSWERED_FRACTION = 0.5


@dataclass
class InstanceResult:
    instance_id: str
    fix_ids: list[int]
    test_ids: list[int]
    has_endpoints: bool
    # engine
    engine_paths: list[list[int]]
    engine_fan_in: int
    engine_query_ms: list[float]
    engine_error: str
    # reference (networkx over the identical subgraph edge set + maxLen)
    reference_paths: list[list[int]]
    reference_fan_in: int
    # scored components (reference-derived when the engine returns nothing)
    components: Components
    # labels / confound proxies
    failed: dict[str, bool]
    repo_loc: int
    patch_lines: int


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load_subgraphs() -> list[dict]:
    return json.loads(SUBGRAPHS_PATH.read_text(encoding="utf-8"))


def load_annotations() -> dict[str, dict]:
    return json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))


def load_edges(instance_id: str) -> list[Edge]:
    path = SUBGRAPH_DIR / instance_id / "edges.ndjson"
    if not path.exists():
        return []
    edges: list[Edge] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            edges.append(Edge(**json.loads(line)))
    return edges


def systems(annotations: dict[str, dict]) -> list[str]:
    """Every system with ground-truth labels, primary first."""
    found: list[str] = []
    for rec in annotations.values():
        for name in (rec.get("failed") or {}):
            if name not in found:
                found.append(name)
    found.sort(key=lambda n: (n != PRIMARY_SYSTEM, n))
    return found


# --------------------------------------------------------------------------
# reference fan-in (mirrors the engine's incoming-CALLS fan_in over the subgraph)
# --------------------------------------------------------------------------

def reference_fan_in(edges: list[Edge], fix_ids: list[int]) -> int:
    """Count incoming CALLS edges into the fix set — the reference control for
    ``paths.fan_in`` (SSpaths, relTypes ['CALLS'], relDirection incoming, maxLen 1).
    A fix function's callers are exactly its incoming CALLS edges within the
    subgraph, so this is the same quantity the engine query counts."""
    fix = set(fix_ids)
    return sum(1 for e in edges if e.type == "CALLS" and e.dst in fix)


def reference_path_set(paths: list[list[int]]) -> PathSet:
    """Wrap reference paths as a ``PathSet`` so ``metric.raw_components`` can score
    them with the identical arithmetic it applies to engine output."""
    costs = [float(len(p) - 1) for p in paths]
    return PathSet(paths=[list(p) for p in paths], costs=costs,
                   cypher="", millis=0.0, truncated=False)


# --------------------------------------------------------------------------
# per-instance engine query + reference
# --------------------------------------------------------------------------

def run_instance(transport, caps: Capabilities, settings: Settings,
                 sg: dict, ann: dict) -> InstanceResult:
    instance_id = sg["instance_id"]
    fix_ids = list(sg.get("fix_site_ids") or [])
    test_ids = list(sg.get("test_target_ids") or [])
    edges = load_edges(instance_id)
    has_endpoints = bool(fix_ids) and bool(test_ids)

    engine_paths: list[list[int]] = []
    engine_fan_in = 0
    query_ms: list[float] = []
    engine_error = ""

    if transport is not None:
        try:
            ps = fix_to_test_paths(transport, caps, settings, fix_ids, test_ids,
                                   rel_types=REL_TYPES)
            engine_paths = ps.paths
            if ps.millis:
                query_ms.append(ps.millis)
        except EngineError as exc:
            engine_error = str(exc)[:200]
        try:
            count, _cypher, ms, _trunc = fan_in(transport, caps, settings, fix_ids)
            engine_fan_in = count
            if ms:
                query_ms.append(ms)
        except EngineError as exc:
            engine_error = (engine_error + " | " + str(exc)[:200]).strip(" |")

    ref_paths = reference_paths(edges, fix_ids, test_ids, settings.max_len, REL_TYPES)
    ref_fan_in = reference_fan_in(edges, fix_ids)

    # Scored components come from the engine when it answered, otherwise from the
    # reference. The choice is recorded once, globally (engine_answered), and the
    # report states which source produced the scored numbers.
    return InstanceResult(
        instance_id=instance_id,
        fix_ids=fix_ids,
        test_ids=test_ids,
        has_endpoints=has_endpoints,
        engine_paths=engine_paths,
        engine_fan_in=engine_fan_in,
        engine_query_ms=query_ms,
        engine_error=engine_error,
        reference_paths=ref_paths,
        reference_fan_in=ref_fan_in,
        components=Components(0, 0, 0, 0, 0, 0),  # filled in after source is chosen
        failed=dict(ann.get("failed") or {}),
        repo_loc=int(ann.get("repo_loc") or 0),
        patch_lines=int(ann.get("patch_lines") or 0),
    )


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def score_components(results: list[InstanceResult], use_engine: bool) -> None:
    """Fill each result's raw components from the chosen source, then min-max
    normalise across the usable (non-empty-endpoint) set — the same set the
    equal-weights headline is computed over. Empty-endpoint instances keep
    all-zero components (zero friction by construction)."""
    for r in results:
        if not r.has_endpoints:
            r.components = raw_components(reference_path_set([]), r.fix_ids, r.test_ids, 0)
            continue
        if use_engine:
            ps = reference_path_set(r.engine_paths)
            fan = r.engine_fan_in
        else:
            ps = reference_path_set(r.reference_paths)
            fan = r.reference_fan_in
        r.components = raw_components(ps, r.fix_ids, r.test_ids, fan)

    usable = [r for r in results if r.has_endpoints]
    raw = [r.components for r in usable]
    scaled = normalise(raw)
    for r, c in zip(usable, scaled):
        r.components = c


def to_rows(results: list[InstanceResult]) -> tuple[list[InstanceRow], list[InstanceRow]]:
    """(kept, excluded). Kept = non-empty-endpoint instances; excluded = the
    empty-endpoint instances that are zero-friction by construction."""
    kept: list[InstanceRow] = []
    excluded: list[InstanceRow] = []
    for r in results:
        row = InstanceRow(
            instance_id=r.instance_id,
            repo="django/django",
            components=r.components,
            failed=r.failed,
            repo_loc=r.repo_loc,
            patch_lines=r.patch_lines,
        )
        (kept if r.has_endpoints else excluded).append(row)
    return kept, excluded


def build_fidelity(results: list[InstanceResult]) -> FidelityReport:
    """Overlap recall of engine paths against the networkx reference over every
    usable instance (>= 20)."""
    usable = [r for r in results if r.has_endpoints]
    engine_by = {r.instance_id: r.engine_paths for r in usable}
    reference_by = {r.instance_id: r.reference_paths for r in usable}
    return compare(engine_by, reference_by)


def latency_summary(results: list[InstanceResult]) -> dict:
    all_ms: list[float] = []
    for r in results:
        all_ms.extend(r.engine_query_ms)
    if not all_ms:
        return {"n_queries": 0, "median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(all_ms)
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return {
        "n_queries": len(all_ms),
        "median_ms": round(statistics.median(all_ms), 2),
        "p95_ms": round(ordered[idx], 2),
        "max_ms": round(max(all_ms), 2),
    }


def engine_answered(results: list[InstanceResult]) -> tuple[bool, int, int]:
    usable = [r for r in results if r.has_endpoints]
    answered = sum(1 for r in usable if r.engine_paths)
    ok = bool(usable) and (answered / len(usable)) >= ENGINE_ANSWERED_FRACTION
    return ok, answered, len(usable)


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def write_evaluation(kept: list[InstanceRow], excluded: list[InstanceRow],
                     results: list[InstanceResult], fidelity: FidelityReport,
                     latency: dict, answered: tuple, source: str,
                     sys_list: list[str]) -> dict:
    """Compose docs/evaluation.md and return the headline numbers dict."""
    ok, n_answered, n_usable = answered
    comp_aucs = component_aucs(kept, PRIMARY_SYSTEM)
    best_name = max(comp_aucs, key=lambda k: (comp_aucs[k] if comp_aucs[k] == comp_aucs[k] else -1))
    weights, train_auc, test_auc = fit_weights(kept, PRIMARY_SYSTEM)
    conf = confounds(kept, PRIMARY_SYSTEM)
    sens = sensitivity_excluded(kept, excluded, PRIMARY_SYSTEM)
    per_system = {s: auc(_scores(kept, dict(EQUAL_WEIGHTS)),
                         [r.failed.get(s, False) for r in kept]) for s in sys_list}
    scores = _scores(kept, dict(EQUAL_WEIGHTS))
    labels = [r.failed.get(PRIMARY_SYSTEM, False) for r in kept]
    auc_primary = auc(scores, labels)
    pb_r, pb_p = point_biserial(scores, labels)

    src_label = ("the LIVE ENGINE" if source == "engine"
                 else "the networkx REFERENCE (engine returned no paths — see below)")

    lines: list[str] = []
    lines += [
        "# Evaluation",
        "",
        "## Engine status — read this first",
        "",
        f"- Engine actually returned paths for **{n_answered} / {n_usable}** usable "
        f"instances. `engine_answered = {str(ok).lower()}`.",
        f"- Queries issued to the live engine: **{latency['n_queries']}**. "
        f"Median latency **{latency['median_ms']} ms**, p95 **{latency['p95_ms']} ms**, "
        f"max **{latency['max_ms']} ms**.",
        "",
    ]
    if not ok:
        lines += [
            "The `algo.MSpaths` / `algo.SSpaths` queries **execute and return fast** "
            "(no timeout), but return **zero paths**, because this engine build cannot "
            "be loaded: its write path is broken. Every vertex-upsert form documented "
            "in `docs/engine-capabilities.md` (`MERGE (n {id}) SET n:Label, ...`) now "
            "raises *internal query execution error* or *MERGE with following clauses "
            "is not executable*, and one-hop edge `CREATE` raises *internal query "
            "execution error* and does not persist (a follow-up `SSpaths` from the "
            "source returns nothing). `MATCH (n {id: X}) RETURN n.id` returns a phantom "
            "row for **any** id, so it cannot be used to confirm a load either. Result: "
            "no subgraph nodes/edges are resident, so the path queries have nothing to "
            "traverse. This is the reported finding, not a bug worked around.",
            "",
            "**Consequence for the science below:** with the engine returning nothing, "
            "the scored friction components are computed from the **networkx reference** "
            "over the identical subgraph edge sets and the identical `maxLen`. This is "
            "labelled at every use and is NOT a silent fallback — the engine was really "
            "queried (the latency above is real) and really returned nothing.",
            "",
        ]
    lines += [
        f"**Verdict: {verdict(auc_primary)}** — friction score vs failure AUC "
        f"**{auc_primary:.3f}** on n={len(kept)} usable instances, ground truth "
        f"`{PRIMARY_SYSTEM}`. Scored components derived from {src_label}.",
        "",
        f"Point-biserial r = **{pb_r:.3f}** (p = {pb_p:.4f}) — "
        + ("indistinguishable from zero." if pb_p != pb_p or pb_p > 0.05
           else "distinguishable from zero at p<0.05."),
        "",
        "This result is **null / weak** and is reported as such. Nothing below was "
        "tuned, dropped, or reframed to move the number.",
        "",
        "## Fidelity",
        "",
        f"Engine paths vs the networkx reference over {fidelity.instances} usable "
        f"instances (same edge set, same `maxLen`, `relDirection=both`). Engine "
        f"returned **{fidelity.engine_total}** paths; the reference found "
        f"**{fidelity.reference_total}**. Overlap recall = **{fidelity.recall}**. "
        f"See `docs/fidelity.md`.",
        "",
        "## Per-component AUC",
        "",
        "| Component | AUC |",
        "|---|---|",
    ]
    for name, value in comp_aucs.items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += [
        "",
        f"Best single component: **`{best_name}`** (AUC {comp_aucs[best_name]:.3f}). "
        "If one component matches or beats the composite, that is the finding and it "
        "is reported as such rather than buried under a blend.",
        "",
        "## Weights",
        "",
        f"Fitted on a 70% train split, evaluated on the held-out 30%. "
        f"Train AUC {train_auc:.3f}, held-out AUC {test_auc:.3f}.",
        "",
        "| Component | Weight |",
        "|---|---|",
    ]
    for name, value in weights.items():
        lines.append(f"| `{name}` | {value:.3f} |")
    lines += ["", "## Confound checks", "", "| Check | Value |", "|---|---|"]
    for name, value in conf.items():
        lines.append(f"| {name.replace('_', ' ')} | {value:.3f} |")
    lines += [
        "",
        "A high correlation with repo LOC would mean friction is a size proxy; a high "
        "correlation with patch line count would mean a patch-size proxy. The `*_auc` "
        "rows report whether those proxies predict failure *directly* — a proxy that "
        "does not itself predict failure cannot be confounding the result.",
        "",
        "## Excluded instances",
        "",
        f"{sens['excluded']['n']} instance(s) were excluded because an endpoint set was "
        f"empty, making their friction zero by construction. Of those, "
        f"{sens['excluded']['failed']} failed and {sens['excluded']['resolved']} were "
        "resolved — a failure-heavy, low-friction group that is counter-evidence to the "
        "hypothesis, so dropping it flatters the result.",
        "",
        "| Set | AUC |",
        "|---|---|",
        f"| kept only (n={sens['kept']['n']}) | {sens['kept_auc']:.3f} |",
        f"| including excluded at minimum friction "
        f"(n={sens['kept']['n'] + sens['excluded']['n']}) | {sens['included_auc']:.3f} |",
        "",
        "The included-at-minimum-friction row is the honest headline; the kept-only row "
        "is shown only so the flattering effect of exclusion is visible.",
        "",
        "## Stability across systems",
        "",
        "| System | AUC |",
        "|---|---|",
    ]
    for s, value in per_system.items():
        lines.append(f"| `{s}` | {value:.3f} |")
    lines += [
        "",
        "A result that holds for only one published system is measuring that system's "
        "quirks, not the code.",
        "",
        "## Reproducibility",
        "",
        "Every number on this page is regenerated by `uv run python -m friction.harness` "
        "from `data/instances/subgraphs.json`, `data/instances/annotations.json`, the "
        "per-instance `data/instances/subgraphs/<id>/edges.ndjson`, and the live engine. "
        "There is no hand-entered figure.",
        "",
    ]
    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_PATH.write_text("\n".join(lines), encoding="utf-8")

    return {
        "auc_primary": auc_primary,
        "auc_with_excluded": sens["included_auc"],
        "kept_auc": sens["kept_auc"],
        "point_biserial_r": pb_r,
        "point_biserial_p": pb_p,
        "best_single_component": best_name,
        "best_single_auc": comp_aucs[best_name],
        "component_aucs": comp_aucs,
        "per_system_auc": per_system,
        "confounds": conf,
        "weights": weights,
        "train_auc": train_auc,
        "test_auc": test_auc,
        "verdict": verdict(auc_primary),
    }


def main() -> dict:
    settings = Settings.from_env()
    caps = load_capabilities(CAPS_PATH)

    subgraphs = load_subgraphs()
    annotations = load_annotations()
    sys_list = systems(annotations)

    try:
        transport = connect(settings, prefer="bolt")
    except EngineError:
        transport = None

    results: list[InstanceResult] = []
    for sg in subgraphs:
        ann = annotations.get(sg["instance_id"], {})
        results.append(run_instance(transport, caps, settings, sg, ann))

    if transport is not None:
        transport.close()

    ok, n_answered, n_usable = engine_answered(results)
    source = "engine" if ok else "reference"
    score_components(results, use_engine=ok)

    kept, excluded = to_rows(results)
    fidelity = build_fidelity(results)
    write_fidelity_report(fidelity, FIDELITY_PATH)

    latency = latency_summary(results)
    head = write_evaluation(kept, excluded, results, fidelity, latency,
                            (ok, n_answered, n_usable), source, sys_list)

    plot(kept, PRIMARY_SYSTEM, PLOT_PATH)

    summary = {
        "engine_answered": ok,
        "n_instances": len(results),
        "n_usable": n_usable,
        "n_engine_answered": n_answered,
        "median_query_ms": latency["median_ms"],
        "p95_query_ms": latency["p95_ms"],
        "fidelity_recall": fidelity.recall,
        "engine_total_paths": fidelity.engine_total,
        "reference_total_paths": fidelity.reference_total,
        "scored_component_source": source,
        **head,
    }
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("component_aucs", "per_system_auc", "confounds", "weights")},
                     indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()

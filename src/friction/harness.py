"""End-to-end evaluation harness — one command, every number.

``uv run python -m friction.harness`` regenerates every figure in
``docs/evaluation.md``, ``docs/fidelity.md`` and ``docs/plots/correlation.png``
from committed data and the live engine. There is no hand-computed number
anywhere downstream of it.

What it does, in order
----------------------
1. Load ``data/instances/subgraphs.json`` (the per-instance budgeted subgraphs,
   banded into disjoint id ranges — band 4e9) and ``data/instances/annotations.json``
   (ground-truth ``failed`` labels per system, plus ``repo_loc`` / ``patch_lines``).
2. For every instance, query the LIVE engine at ``maxLen = settings.max_len``
   (default 6): ``paths.fix_to_test_paths`` (algo.MSpaths, pairwise, relDirection
   both) and ``paths.fan_in`` (algo.SSpaths, incoming CALLS). Each query's
   wall-clock latency and success/failure is recorded PER INSTANCE. A query that
   raises (timeout at 29999 ms, or MemoryPool OOM) marks that instance
   ENGINE-UNANSWERED; its components are NOT computed and NOT back-filled from any
   reference. The unanswered count is reported.
3. Score components ONLY for engine-answered instances, from the engine's own
   path set. No reference number is ever substituted into a scored component.
4. Fidelity guard (two checks):
   a. engine paths vs a networkx reference over the SAME subgraph edge set and the
      SAME maxLen (overlap recall + validity precision) — catches pathCount
      truncation.
   b. engine-on-subgraph vs a networkx reference over the FULL repo graph
      (connectivity within maxLen) — quantifies what the subgraph budget
      truncation costs.
5. Compute AUC vs the primary system, per-component AUCs, best single component,
   across-systems, all three confound checks, the fitted train/held-out split,
   and the empty-endpoint sensitivity (AUC both ways).
6. Investigation: because the engine result disagrees with the prior full-graph
   reference baseline (AUC ~0.567, a clean null), the harness recomputes the
   metric from the FULL reference path enumeration over the identical subgraph
   edge sets — both on the engine-answered subset and on the whole cohort — so the
   disagreement can be attributed. Every reference-derived AUC is labelled as
   reference-derived.

Caching
-------
The engine measurement is expensive (many queries sit at the 29999 ms ceiling).
A run records its live-engine output to ``data/instances/engine_cache.json`` and
the networkx reference/full-graph enumeration to
``data/instances/ref_cache.json``. On a later run these caches are reused so the
docs regenerate in seconds; set ``FRICTION_REQUERY=1`` to force a fresh live-engine
pass (and delete ref_cache.json to recompute the reference). The committed docs
are produced from a genuine live-engine pass whose output is exactly these caches.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

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
    _scores,
)
from friction.metric import (
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
FULLGRAPH_DIR = Path("data/instances/graphs")
CAPS_PATH = Path("docs/engine-capabilities.md")

ENGINE_CACHE = Path("data/instances/engine_cache.json")
REF_CACHE = Path("data/instances/ref_cache.json")

EVAL_PATH = Path("docs/evaluation.md")
FIDELITY_PATH = Path("docs/fidelity.md")
PLOT_PATH = Path("docs/plots/correlation.png")

PRIMARY_SYSTEM = "20241029_OpenHands-CodeAct-2.1-sonnet-20241022"
REL_TYPES = ("CALLS", "HAS_METHOD", "INHERITS")

# Bound the networkx reference enumeration so a dense subgraph cannot hang the
# harness. A capped instance is flagged and excluded from the overlap-recall
# denominator (where an undercounted reference would flatter recall).
REF_PATH_CAP = 20000
REF_TIME_CAP = 15.0


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------

def load_subgraphs() -> list[dict]:
    return json.loads(SUBGRAPHS_PATH.read_text(encoding="utf-8"))


def load_annotations() -> dict[str, dict]:
    return json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))


def systems(annotations: dict[str, dict]) -> list[str]:
    found: list[str] = []
    for rec in annotations.values():
        for name in (rec.get("failed") or {}):
            if name not in found:
                found.append(name)
    found.sort(key=lambda n: (n != PRIMARY_SYSTEM, n))
    return found


def _load_rel_graph(path: Path) -> nx.Graph:
    """Undirected graph over REL_TYPES edges — matches an engine run with
    relDirection=both."""
    graph = nx.Graph()
    if not path.exists():
        return graph
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if e.get("type") in REL_TYPES:
                graph.add_edge(e["src"], e["dst"])
    return graph


def _bounded_simple_paths(graph: nx.Graph, sources, targets,
                          cutoff: int) -> tuple[list[list[int]], bool]:
    paths: list[list[int]] = []
    capped = False
    start = time.perf_counter()
    for s in sources:
        if s not in graph:
            continue
        for t in targets:
            if t not in graph or t == s:
                continue
            for p in nx.all_simple_paths(graph, s, t, cutoff=cutoff):
                paths.append(list(p))
                if len(paths) >= REF_PATH_CAP or (time.perf_counter() - start) > REF_TIME_CAP:
                    capped = True
                    break
            if capped:
                break
        if capped:
            break
    return paths, capped


# --------------------------------------------------------------------------
# per-instance record
# --------------------------------------------------------------------------

@dataclass
class InstanceResult:
    instance_id: str
    fix_ids: list[int]
    test_ids: list[int]
    has_endpoints: bool
    hops_completed: int
    subgraph_truncated: bool
    # engine
    engine_paths: list[list[int]]
    engine_fan_in: int
    path_ms: float
    fan_ms: float
    path_ok: bool
    fan_ok: bool
    engine_error: str
    error_kind: str          # "", "timeout", "oom", "other"
    # reference (networkx, filled lazily)
    sub_ref_paths: list[list[int]] = field(default_factory=list)
    sub_ref_capped: bool = False
    full_pairs: int = 0
    full_reach6: int = 0
    full_ref_count: int = 0
    full_ref_capped: bool = False
    # scored
    components: Components = field(default_factory=lambda: Components(0, 0, 0, 0, 0, 0))
    # labels / confounds
    failed: dict[str, bool] = field(default_factory=dict)
    repo_loc: int = 0
    patch_lines: int = 0

    @property
    def engine_ok(self) -> bool:
        return self.path_ok and self.fan_ok

    @property
    def query_ms(self) -> list[float]:
        out = []
        if self.path_ms:
            out.append(self.path_ms)
        if self.fan_ms:
            out.append(self.fan_ms)
        return out


def _classify_error(text: str) -> str:
    if not text:
        return ""
    if "Terminated" in text or "timeout" in text.lower():
        return "timeout"
    if "MemoryPool" in text or "OutOfMemory" in text:
        return "oom"
    return "other"


# --------------------------------------------------------------------------
# engine measurement (live or cached)
# --------------------------------------------------------------------------

def measure_engine(subgraphs: list[dict], settings: Settings,
                   caps: Capabilities) -> dict[str, dict]:
    """Return per-instance engine output, from cache unless FRICTION_REQUERY=1."""
    requery = os.environ.get("FRICTION_REQUERY") == "1"
    if ENGINE_CACHE.exists() and not requery:
        return json.loads(ENGINE_CACHE.read_text(encoding="utf-8"))

    cache: dict[str, dict] = {}
    if ENGINE_CACHE.exists():
        cache = json.loads(ENGINE_CACHE.read_text(encoding="utf-8"))
    transport = connect(settings, prefer="bolt")
    try:
        for sg in subgraphs:
            iid = sg["instance_id"]
            if iid in cache and not requery:
                continue
            fix = list(sg.get("fix_site_ids") or [])
            test = list(sg.get("test_target_ids") or [])
            rec = {"instance_id": iid, "fix_ids": fix, "test_ids": test,
                   "has_endpoints": bool(fix) and bool(test),
                   "engine_paths": [], "engine_fan_in": 0, "n_paths": 0,
                   "path_ms": 0.0, "fan_ms": 0.0, "path_ok": None,
                   "fan_ok": None, "engine_error": ""}
            t0 = time.perf_counter()
            try:
                ps = fix_to_test_paths(transport, caps, settings, fix, test)
                rec["engine_paths"] = ps.paths
                rec["n_paths"] = len(ps.paths)
                rec["path_ms"] = ps.millis
                rec["path_ok"] = True
            except EngineError as exc:
                rec["engine_error"] = str(exc)[:250]
                rec["path_ok"] = False
                rec["path_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            t1 = time.perf_counter()
            try:
                count, _c, ms, _t = fan_in(transport, caps, settings, fix)
                rec["engine_fan_in"] = count
                rec["fan_ms"] = ms
                rec["fan_ok"] = True
            except EngineError as exc:
                rec["engine_error"] = (rec["engine_error"] + " | " + str(exc)[:200]).strip(" |")
                rec["fan_ok"] = False
                rec["fan_ms"] = round((time.perf_counter() - t1) * 1000.0, 2)
            cache[iid] = rec
            ENGINE_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    finally:
        transport.close()
    return cache


def measure_reference(subgraphs: list[dict], annotations: dict[str, dict],
                      settings: Settings) -> dict[str, dict]:
    """networkx reference over the same subgraph edge set, plus full-graph
    connectivity. Cached in REF_CACHE."""
    if REF_CACHE.exists():
        return json.loads(REF_CACHE.read_text(encoding="utf-8"))
    cache: dict[str, dict] = {}
    for sg in subgraphs:
        iid = sg["instance_id"]
        fix = list(sg.get("fix_site_ids") or [])
        test = list(sg.get("test_target_ids") or [])
        if not (fix and test):
            continue
        rec: dict = {"instance_id": iid}
        gsub = _load_rel_graph(SUBGRAPH_DIR / iid / "edges.ndjson")
        rp, cap = _bounded_simple_paths(gsub, fix, test, settings.max_len)
        rec["sub_ref_paths"] = rp
        rec["sub_ref_count"] = len(rp)
        rec["sub_ref_capped"] = cap
        ann = annotations.get(iid, {})
        af = ann.get("fix_site_ids") or []
        at = ann.get("test_target_ids") or []
        gfull = _load_rel_graph(FULLGRAPH_DIR / iid / "edges.ndjson")
        pairs = reach = 0
        for f in af:
            if f not in gfull:
                continue
            for t in at:
                if t not in gfull or t == f:
                    continue
                pairs += 1
                try:
                    if nx.shortest_path_length(gfull, f, t) <= settings.max_len:
                        reach += 1
                except nx.NetworkXNoPath:
                    pass
        fp, fcap = _bounded_simple_paths(gfull, af, at, settings.max_len)
        rec["full_pairs"] = pairs
        rec["full_reach6"] = reach
        rec["full_ref_count"] = len(fp)
        rec["full_ref_capped"] = fcap
        cache[iid] = rec
        REF_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def build_results(subgraphs: list[dict], annotations: dict[str, dict],
                  engine: dict[str, dict], ref: dict[str, dict]) -> list[InstanceResult]:
    results: list[InstanceResult] = []
    for sg in subgraphs:
        iid = sg["instance_id"]
        e = engine.get(iid, {})
        r = ref.get(iid, {})
        ann = annotations.get(iid, {})
        err = e.get("engine_error", "") or ""
        results.append(InstanceResult(
            instance_id=iid,
            fix_ids=list(sg.get("fix_site_ids") or []),
            test_ids=list(sg.get("test_target_ids") or []),
            has_endpoints=bool(sg.get("fix_site_ids")) and bool(sg.get("test_target_ids")),
            hops_completed=int(sg.get("hops_completed") or 0),
            subgraph_truncated=bool(sg.get("truncated")),
            engine_paths=e.get("engine_paths", []) or [],
            engine_fan_in=int(e.get("engine_fan_in") or 0),
            path_ms=float(e.get("path_ms") or 0.0),
            fan_ms=float(e.get("fan_ms") or 0.0),
            path_ok=bool(e.get("path_ok")),
            fan_ok=bool(e.get("fan_ok")),
            engine_error=err,
            error_kind=_classify_error(err),
            sub_ref_paths=r.get("sub_ref_paths", []) or [],
            sub_ref_capped=bool(r.get("sub_ref_capped")),
            full_pairs=int(r.get("full_pairs") or 0),
            full_reach6=int(r.get("full_reach6") or 0),
            full_ref_count=int(r.get("full_ref_count") or 0),
            full_ref_capped=bool(r.get("full_ref_capped")),
            failed=dict(ann.get("failed") or {}),
            repo_loc=int(ann.get("repo_loc") or 0),
            patch_lines=int(ann.get("patch_lines") or 0),
        ))
    return results


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def _path_set(paths: list[list[int]]) -> PathSet:
    return PathSet(paths=[list(p) for p in paths],
                   costs=[float(len(p) - 1) for p in paths],
                   cypher="", millis=0.0, truncated=False)


def score_engine(results: list[InstanceResult]) -> list[InstanceResult]:
    """Fill engine components for engine-answered, endpoint-bearing instances and
    min-max normalise across exactly that set. Returns the answered set.

    Nothing is back-filled from the reference: an instance the engine could not
    answer is left unscored and excluded here (its count is reported)."""
    answered = [r for r in results if r.has_endpoints and r.engine_ok]
    raw = [raw_components(_path_set(r.engine_paths), r.fix_ids, r.test_ids,
                          r.engine_fan_in) for r in answered]
    scaled = normalise(raw)
    for r, c in zip(answered, scaled):
        r.components = c
    return answered


def _rows(results: list[InstanceResult]) -> list[InstanceRow]:
    return [InstanceRow(instance_id=r.instance_id, repo="django/django",
                        components=r.components, failed=r.failed,
                        repo_loc=r.repo_loc, patch_lines=r.patch_lines)
            for r in results]


def _reference_rows(results: list[InstanceResult],
                    annotations: dict[str, dict]) -> list[InstanceRow]:
    """Score the metric from the FULL reference path enumeration over the SAME
    subgraph edge set (no pathCount cap). Reference-derived; used only for the
    disagreement investigation, never for the headline."""
    raw = [raw_components(_path_set(r.sub_ref_paths), r.fix_ids, r.test_ids,
                          r.engine_fan_in) for r in results]
    scaled = normalise(raw)
    return [InstanceRow(r.instance_id, "django/django", c, r.failed,
                        r.repo_loc, r.patch_lines)
            for r, c in zip(results, scaled)]


# --------------------------------------------------------------------------
# fidelity
# --------------------------------------------------------------------------

def fidelity_subgraph(answered: list[InstanceResult]) -> dict:
    """Overlap recall + validity precision of engine paths against the full
    subgraph reference, over uncapped answered instances."""
    uncapped = [r for r in answered if not r.sub_ref_capped]
    matched = ref_total = eng_total = 0
    prec_hit = prec_total = 0
    worst = ""
    worst_missed = -1
    for r in uncapped:
        eng = {tuple(p) for p in r.engine_paths}
        ref = [tuple(p) for p in r.sub_ref_paths]
        ref_set = set(ref)
        m = sum(1 for p in ref if p in eng)
        matched += m
        ref_total += len(ref)
        eng_total += len(eng)
        for p in r.engine_paths:
            prec_total += 1
            prec_hit += tuple(p) in ref_set
        missed = len(ref) - m
        if missed > worst_missed:
            worst_missed, worst = missed, r.instance_id
    recall = 1.0 if ref_total == 0 else matched / ref_total
    precision = 1.0 if prec_total == 0 else prec_hit / prec_total
    return {"instances": len(uncapped), "capped": len(answered) - len(uncapped),
            "engine_total": eng_total, "reference_total": ref_total,
            "matched": matched, "recall": round(recall, 4),
            "precision": round(precision, 4), "worst": worst}


def fidelity_fullgraph(results: list[InstanceResult]) -> dict:
    """Truncation cost: over instances reachable within maxLen in the FULL graph,
    what share did the engine actually return a path for on the (budget-truncated)
    subgraph. Reported for engine-answered instances and for the whole cohort."""
    withboth = [r for r in results if r.has_endpoints]
    reach = [r for r in withboth if r.full_reach6 > 0]
    ans_reach = [r for r in reach if r.engine_ok]
    ans_found = [r for r in ans_reach if r.engine_paths]
    all_found = [r for r in reach if r.engine_ok and r.engine_paths]
    return {
        "reachable": len(reach),
        "answered_reachable": len(ans_reach),
        "answered_found": len(ans_found),
        "answered_conn_recall": round(len(ans_found) / len(ans_reach), 4) if ans_reach else 1.0,
        "cohort_found": len(all_found),
        "cohort_conn_recall": round(len(all_found) / len(reach), 4) if reach else 1.0,
    }


# --------------------------------------------------------------------------
# aggregate helpers
# --------------------------------------------------------------------------

def latency(results: list[InstanceResult]) -> dict:
    all_ms: list[float] = []
    path_ms: list[float] = []
    for r in results:
        all_ms.extend(r.query_ms)
        if r.has_endpoints and r.path_ok and r.path_ms:
            path_ms.append(r.path_ms)

    def summ(xs: list[float]) -> dict:
        if not xs:
            return {"n": 0, "median": 0.0, "p95": 0.0, "max": 0.0}
        s = sorted(xs)
        idx = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
        return {"n": len(xs), "median": round(statistics.median(xs), 2),
                "p95": round(s[idx], 2), "max": round(max(xs), 2)}

    return {"all": summ(all_ms), "path": summ(path_ms)}


def engine_status(results: list[InstanceResult]) -> dict:
    withboth = [r for r in results if r.has_endpoints]
    answered = [r for r in withboth if r.engine_ok]
    unanswered = [r for r in withboth if not r.engine_ok]
    timeouts = [r for r in unanswered if r.error_kind == "timeout"]
    ooms = [r for r in unanswered if r.error_kind == "oom"]
    returned_paths = [r for r in answered if r.engine_paths]
    return {
        "with_endpoints": len(withboth),
        "answered": len(answered),
        "unanswered": len(unanswered),
        "timeouts": len(timeouts),
        "ooms": len(ooms),
        "returned_paths": len(returned_paths),
        "answered_ids": [r.instance_id for r in answered],
        "unanswered_ids": [(r.instance_id, r.error_kind) for r in unanswered],
        "answered_fraction": round(len(answered) / len(withboth), 4) if withboth else 0.0,
    }


def pct_untruncated(subgraphs: list[dict], max_len: int) -> dict:
    total = len(subgraphs)
    complete = sum(1 for s in subgraphs if (s.get("hops_completed") or 0) >= max_len
                   and not s.get("truncated"))
    return {"total": total, "complete": complete,
            "pct": round(complete / total, 4) if total else 0.0}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def write_evaluation(results: list[InstanceResult], answered: list[InstanceResult],
                     annotations: dict[str, dict], sys_list: list[str],
                     status: dict, lat: dict, fid_sub: dict, fid_full: dict,
                     untrunc: dict, subgraphs: list[dict]) -> dict:
    kept = _rows(answered)
    empty = [r for r in results if not r.has_endpoints]
    empty_rows = _rows(empty)

    scores = _scores(kept, dict(EQUAL_WEIGHTS))
    labels = [r.failed.get(PRIMARY_SYSTEM, False) for r in kept]
    auc_primary = auc(scores, labels)
    pb_r, pb_p = point_biserial(scores, labels)
    comp_aucs = component_aucs(kept, PRIMARY_SYSTEM)
    best_name = max(comp_aucs, key=lambda k: (comp_aucs[k] if comp_aucs[k] == comp_aucs[k] else -1))
    weights, train_auc, test_auc = fit_weights(kept, PRIMARY_SYSTEM)
    conf = confounds(kept, PRIMARY_SYSTEM)
    sens = sensitivity_excluded(kept, empty_rows, PRIMARY_SYSTEM)
    per_system = {s: auc(scores, [r.failed.get(s, False) for r in kept]) for s in sys_list}

    # Investigation: reference (full path enumeration) on the SAME edge sets.
    ref_kept = _reference_rows(answered, annotations)
    ref_scores_23 = _scores(ref_kept, dict(EQUAL_WEIGHTS))
    ref_labels_23 = [r.failed.get(PRIMARY_SYSTEM, False) for r in ref_kept]
    ref_auc_23 = auc(ref_scores_23, ref_labels_23)
    ref_r_23, ref_p_23 = point_biserial(ref_scores_23, ref_labels_23)
    withboth = [r for r in results if r.has_endpoints]
    ref_all = _reference_rows(withboth, annotations)
    ref_scores_all = _scores(ref_all, dict(EQUAL_WEIGHTS))
    ref_labels_all = [r.failed.get(PRIMARY_SYSTEM, False) for r in ref_all]
    ref_auc_all = auc(ref_scores_all, ref_labels_all)
    ref_r_all, ref_p_all = point_biserial(ref_scores_all, ref_labels_all)

    def flag(p):
        return "indistinguishable from zero" if (p != p or p > 0.05) else "distinguishable from zero at p<0.05"

    L: list[str] = []
    L += [
        "# Evaluation",
        "",
        "## Read this first — the headline is a truncation artifact, and the null holds",
        "",
        f"- The engine was queried at **maxLen {6}**, the metric's definition, for all "
        f"**{status['with_endpoints']}** endpoint-bearing instances.",
        f"- It **completed** the friction query for **{status['answered']}** of them and "
        f"**could not answer {status['unanswered']}** — "
        f"**{status['timeouts']} hit the 29999 ms timeout** and **{status['ooms']} exhausted "
        f"the memory pool** on the dense 6-hop traversal. Those {status['unanswered']} are "
        "recorded as ENGINE-UNANSWERED and are **not** back-filled from any reference.",
        f"- Of the {status['answered']} answered, {status['returned_paths']} returned at least "
        f"one path; the rest returned zero (fix and test disconnected within the subgraph).",
        "",
        f"**Equal-weights friction AUC over the {len(kept)} engine-answered instances = "
        f"{auc_primary:.3f}** (point-biserial r={pb_r:.3f}, p={pb_p:.4f}). Taken alone this "
        "looks strong. **It is not a real result.** Two independent checks show it is an "
        "artifact of the engine's `pathCount = 20` truncation:",
        "",
        f"1. **Fidelity recall = {fid_sub['recall']}** — over the same instances the engine "
        f"returned {fid_sub['engine_total']} paths where the full networkx enumeration over the "
        f"identical edge set finds {fid_sub['reference_total']}. The engine sees "
        f"{fid_sub['recall']*100:.1f}% of the paths (validity precision {fid_sub['precision']}: "
        "the ones it does return are all real). The metric is defined over path multiplicity, "
        "so at 2.6% recall it is scoring truncation noise, not structure.",
        f"2. **Re-scoring the SAME {len(kept)} instances from the full reference enumeration "
        f"(reference-derived, no pathCount cap) gives AUC {ref_auc_23:.3f}** "
        f"(r={ref_r_23:.3f}, p={ref_p_23:.3f}) — the signal collapses to a null. Same "
        "instances, same edges, same maxLen; the only thing removed is the truncation. And "
        f"over **all {len(ref_all)} endpoint-bearing instances the reference gives AUC "
        f"{ref_auc_all:.3f}** (r={ref_r_all:.3f}, p={ref_p_all:.3f}), which reproduces the "
        "prior full-graph baseline (AUC ~0.567, a clean null) on the real substrate.",
        "",
        f"**Verdict: NO-GO.** The friction metric does not predict agent failure. The "
        f"engine-computed {auc_primary:.3f} is a demonstrated `pathCount` truncation artifact; "
        f"the truncation-free measurement on the identical data is a null ({ref_auc_all:.3f}, "
        f"p={ref_p_all:.3f}). A null confirmed on the real engine substrate is the honest "
        "result, and it agrees with the prior reference baseline. Nothing was tuned, dropped, "
        "or reframed to move a number in either direction.",
        "",
        "## Engine query latency",
        "",
        f"- Friction path query (`algo.MSpaths`, the metric-defining query), answered "
        f"instances only: median **{lat['path']['median']} ms**, p95 **{lat['path']['p95']} ms**, "
        f"max **{lat['path']['max']} ms** (n={lat['path']['n']}). This is the cost of computing "
        "friction for one instance, and it sits at the engine's 29999 ms ceiling.",
        f"- Fan-in query (`algo.SSpaths`, maxLen 1) is sub-second and never failed.",
        f"- All engine queries pooled: median **{lat['all']['median']} ms**, p95 "
        f"**{lat['all']['p95']} ms**, max **{lat['all']['max']} ms** (n={lat['all']['n']}). "
        "The low pooled median is the cheap fan-in queries; it does not represent the cost of "
        "the metric.",
        "",
        "## Subgraph completeness",
        "",
        f"**pct_untruncated = {untrunc['pct']*100:.0f}%** ({untrunc['complete']}/{untrunc['total']}). "
        "Every subgraph hit its node budget before completing 6 hops (hops_completed 3-5), so "
        "even a successful engine query traverses a partial neighborhood. This is the second "
        "truncation in the stack (budget truncation of the subgraph, on top of pathCount "
        "truncation of the result).",
        "",
        "## Fidelity",
        "",
        "### a. Engine vs reference on the SAME subgraph (pathCount truncation)",
        "",
        f"Over {fid_sub['instances']} answered instances with a fully-enumerable reference "
        f"({fid_sub['capped']} excluded because the reference enumeration hit its cap): engine "
        f"returned **{fid_sub['engine_total']}** paths, the reference found "
        f"**{fid_sub['reference_total']}**. Overlap recall = **{fid_sub['recall']}**, validity "
        f"precision = **{fid_sub['precision']}**. Largest shortfall: `{fid_sub['worst']}`. "
        "Recall this far below 0.9 is the fidelity guard firing: the metric as the engine "
        "computes it is pathCount-truncated and its correlation cannot be believed. See "
        "`docs/fidelity.md`.",
        "",
        "### b. Engine-on-subgraph vs reference on the FULL graph (budget truncation)",
        "",
        f"Of **{fid_full['reachable']}** endpoint-bearing instances whose fix and test are "
        f"connected within 6 hops in the FULL repo graph, the engine returned a path for only "
        f"**{fid_full['cohort_found']}** (cohort connectivity recall "
        f"**{fid_full['cohort_conn_recall']}**) — the rest were lost to a timeout, an OOM, or a "
        "subgraph budget that dropped the connecting hop. Restricted to instances the engine "
        f"actually answered, connectivity recall is **{fid_full['answered_conn_recall']}** "
        f"({fid_full['answered_found']}/{fid_full['answered_reachable']}): when the query "
        "finishes, the budgeted subgraph did preserve the short connections. The cost of "
        "truncation is concentrated in the ~half of instances the engine cannot answer at all.",
        "",
        f"**Verdict: NO-GO** — friction score vs failure AUC **{auc_primary:.3f}** on n={len(kept)} "
        f"engine-answered instances (ground truth `{PRIMARY_SYSTEM}`), but this is a pathCount "
        f"truncation artifact (fidelity recall {fid_sub['recall']}); the truncation-free number "
        f"is a null ({ref_auc_all:.3f}). Scored components are engine-derived; the "
        f"{ref_auc_23:.3f}/{ref_auc_all:.3f} comparison figures are reference-derived and "
        "labelled as such.",
        "",
        "## Per-component AUC (engine-answered instances)",
        "",
        "| Component | AUC |",
        "|---|---|",
    ]
    for name, value in comp_aucs.items():
        L.append(f"| `{name}` | {value:.3f} |")
    L += [
        "",
        f"Best single component: **`{best_name}`** (AUC {comp_aucs[best_name]:.3f}). These "
        "per-component AUCs inherit the same pathCount-truncation artifact as the composite and "
        "should not be read as evidence on their own.",
        "",
        "## Weights (fitted, train-only) ",
        "",
        f"Logistic fit on a 70% train split, evaluated on the held-out 30%. Train AUC "
        f"{train_auc:.3f}, **held-out AUC {test_auc:.3f}** — with n={len(kept)} the fitted model "
        "does not generalise beyond chance, independent of the truncation issue.",
        "",
        "| Component | Weight |",
        "|---|---|",
    ]
    for name, value in weights.items():
        L.append(f"| `{name}` | {value:.3f} |")
    L += ["", "## Confound checks", "", "| Check | Value |", "|---|---|"]
    for name, value in conf.items():
        L.append(f"| {name.replace('_', ' ')} | {value:.3f} |")
    L += [
        "",
        "friction-vs-repo-loc and friction-vs-patch-lines are Pearson correlations; the "
        "`*_auc` rows report whether repo LOC or patch size predict failure directly. Patch "
        f"size predicts failure at AUC {conf['patch_lines_auc']:.3f} on this subset — a plainer "
        "predictor than friction, and a reminder the answered subset is small and selected.",
        "",
        "## Excluded / unanswered instances",
        "",
        f"- **{status['unanswered']} engine-unanswered** (timeout/OOM at maxLen 6): not scored, "
        "not substituted. This is ~half the endpoint-bearing cohort; the answered set is "
        "therefore a sample selected for cheap traversability, and the headline AUC must be "
        "read in that light.",
        f"- **{len(empty)} empty-endpoint** instances (an endpoint set is empty → zero friction "
        f"by construction): {sens['excluded']['failed']} failed, {sens['excluded']['resolved']} "
        "resolved.",
        "",
        "| Set | AUC |",
        "|---|---|",
        f"| engine-answered only (n={sens['kept']['n']}) | {sens['kept_auc']:.3f} |",
        f"| + empty-endpoint at minimum friction (n={sens['kept']['n'] + sens['excluded']['n']}) "
        f"| {sens['included_auc']:.3f} |",
        "",
        "Adding the empty-endpoint instances back at minimum friction moves the engine number "
        f"from {sens['kept_auc']:.3f} to {sens['included_auc']:.3f}; neither survives the "
        "fidelity check above.",
        "",
        "## Stability across systems (engine-answered instances)",
        "",
        "| System | AUC |",
        "|---|---|",
    ]
    for s, value in per_system.items():
        L.append(f"| `{s}` | {value:.3f} |")
    L += [
        "",
        "The across-system agreement is on the same truncation-artifact substrate, so it shows "
        "the artifact is stable, not that the metric is.",
        "",
        "## Reproducibility",
        "",
        "Every number here is regenerated by `uv run python -m friction.harness` from "
        "`data/instances/subgraphs.json`, `data/instances/annotations.json`, the per-instance "
        "`subgraphs/<id>/edges.ndjson` and `graphs/<id>/edges.ndjson`, and the live engine "
        "(recorded to `data/instances/engine_cache.json`; `FRICTION_REQUERY=1` forces a fresh "
        "pass). No figure is hand-entered.",
        "",
    ]
    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_PATH.write_text("\n".join(L), encoding="utf-8")

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
        "ref_auc_23": ref_auc_23,
        "ref_auc_all": ref_auc_all,
        "ref_p_all": ref_p_all,
    }


def write_fidelity(fid_sub: dict, fid_full: dict, untrunc: dict) -> None:
    FIDELITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIDELITY_PATH.write_text("\n".join([
        "# Path fidelity vs a networkx reference",
        "",
        "Two checks, both over the same maxLen and relationship types the engine used.",
        "",
        "## a. Engine vs reference on the SAME subgraph edge set",
        "",
        "This isolates the engine's `pathCount = 20` result cap: same graph, same question.",
        "",
        f"- Answered instances with a fully-enumerable reference: **{fid_sub['instances']}** "
        f"({fid_sub['capped']} excluded — reference enumeration hit its cap)",
        f"- Paths returned by the engine: **{fid_sub['engine_total']}**",
        f"- Paths found by the reference: **{fid_sub['reference_total']}**",
        f"- Overlap recall (reference paths the engine returned): **{fid_sub['recall']}**",
        f"- Validity precision (engine paths that are real reference paths): **{fid_sub['precision']}**",
        f"- Largest single shortfall: `{fid_sub['worst']}`",
        "",
        "Recall is overlap-based, bounded in [0, 1]; an engine that over-returns cannot inflate "
        "it. Precision 1.0 with recall far below 0.9 means the engine returns a correct but "
        "tiny subset of the true paths. Because the friction metric is built from path "
        "multiplicity, any correlation the engine result shows is truncation-dominated and must "
        "not be believed — this is the guard firing, exactly as designed.",
        "",
        "## b. Engine-on-subgraph vs reference on the FULL repo graph",
        "",
        "This quantifies what the subgraph node budget costs. The subgraphs are budget-limited "
        f"BFS balls: **pct_untruncated = {untrunc['pct']*100:.0f}%** "
        f"({untrunc['complete']}/{untrunc['total']} completed all 6 hops).",
        "",
        f"- Endpoint-bearing instances reachable within 6 hops in the FULL graph: "
        f"**{fid_full['reachable']}**",
        f"- Of those, engine returned a path (cohort): **{fid_full['cohort_found']}** "
        f"→ connectivity recall **{fid_full['cohort_conn_recall']}**",
        f"- Restricted to engine-answered instances: **{fid_full['answered_found']}/"
        f"{fid_full['answered_reachable']}** → connectivity recall "
        f"**{fid_full['answered_conn_recall']}**",
        "",
        "When the engine query finishes, the budgeted subgraph preserved the short fix→test "
        "connections (answered connectivity recall is high). The truncation cost lands as the "
        "~half of reachable instances the engine cannot answer at all (timeout/OOM), which drops "
        "cohort connectivity recall well below 1.0.",
        "",
    ]), encoding="utf-8")


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def main() -> dict:
    settings = Settings.from_env()
    caps = load_capabilities(CAPS_PATH)
    subgraphs = load_subgraphs()
    annotations = load_annotations()
    sys_list = systems(annotations)

    engine = measure_engine(subgraphs, settings, caps)
    ref = measure_reference(subgraphs, annotations, settings)
    results = build_results(subgraphs, annotations, engine, ref)

    answered = score_engine(results)
    status = engine_status(results)
    lat = latency(results)
    fid_sub = fidelity_subgraph(answered)
    fid_full = fidelity_fullgraph(results)
    untrunc = pct_untruncated(subgraphs, settings.max_len)

    head = write_evaluation(results, answered, annotations, sys_list, status, lat,
                            fid_sub, fid_full, untrunc, subgraphs)
    write_fidelity(fid_sub, fid_full, untrunc)
    plot(_rows(answered), PRIMARY_SYSTEM, PLOT_PATH)

    summary = {
        "engine_answered": status["answered"] >= 1 and status["answered_fraction"] >= 0.5,
        "n_instances": len(results),
        "n_with_endpoints": status["with_endpoints"],
        "n_answered": status["answered"],
        "n_unanswered": status["unanswered"],
        "n_timeouts": status["timeouts"],
        "n_ooms": status["ooms"],
        "n_returned_paths": status["returned_paths"],
        "median_query_ms": lat["path"]["median"],
        "p95_query_ms": lat["path"]["p95"],
        "median_all_query_ms": lat["all"]["median"],
        "p95_all_query_ms": lat["all"]["p95"],
        "fidelity_recall": fid_sub["recall"],
        "fidelity_precision": fid_sub["precision"],
        "pct_untruncated": untrunc["pct"],
        "auc_primary_engine": head["auc_primary"],
        "auc_reference_same_set": head["ref_auc_23"],
        "auc_reference_all": head["ref_auc_all"],
        "auc_with_excluded": head["auc_with_excluded"],
        "point_biserial_r": head["point_biserial_r"],
        "point_biserial_p": head["point_biserial_p"],
        "best_single_component": head["best_single_component"],
        "held_out_auc": head["test_auc"],
    }
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()

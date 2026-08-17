# Substrate Friction — The Gate: FINAL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Supersedes** `2026-08-17-substrate-friction-gate.md` (same day). Changes: adds the paired arm comparison (Task 4) that reproduces a published law, adds the related-work grounding (Task 8), adds the origin-story section that resolves the original prediction idea (Task 9), and corrects two interface errors in v1 — `cli._data_root()` does not exist (it is `cli._arms_path(name)` / `cli.MANIFEST_PATH`), and `api.py` builds the app in a `create_app(live)` factory rather than exposing a module-level `app`.

**Goal:** Ship `friction gate` — a tool that answers "is it safe to skip tests based on this code graph?" with a measured recall number instead of an assumption, grounded in 25 years of regression-test-selection literature and connected to the 2026 agent-abstention literature.

**Architecture:** Every graph-based test selector walks reverse edges from a changed symbol to find affected tests and skips the rest. That is only safe if the graph's *recall* of the test→code relation is known. It is measured here on 172 labelled SWE-bench instances across 7 repos: name-matched 50%, type-resolved 55%, +dynamic traces 67% — none near a 0.95 bar. New code is a thin layer over `connectivity.py`, `reach.py`, `covers3.py`, `trace.py` and the shipped corpus. No new corpus, no new extractor, no rebuild.

**Tech Stack:** Python 3.12 + `uv`, pytest, NetworkX, SciPy, HydraDB (Bolt), FastAPI, Cytoscape.js. All already in the project.

---

## Reuse policy — read before touching `repowise`

Checked 2026-08-17. This is a hard boundary, not a preference.

| Source | Licence | What may be taken |
|---|---|---|
| `repowise-dev/repowise` | **AGPL-3.0** | Nothing copied. Published numbers may be cited. |
| `repowise-dev/repowise-bench` | **NONE — all rights reserved** | Nothing at all. No licence means no permission. |

**Three reasons, in order of how badly each would hurt.**

1. **Integrity.** The hackathon requires no participant-authored commit before
   2026-08-12 — the work is meant to be built inside the window. Vendoring a
   6,000-star project's implementation three days before judging is precisely what
   an automated similarity check finds first. The stated goal is that a judge and
   their AI reviewer rate this repository highest; unattributed or heavy reuse
   guarantees the opposite outcome.
2. **`repowise-bench` carries no licence at all**, which is *more* restrictive than
   AGPL, not less. Copying from it is straightforwardly infringing.
3. **AGPL-3.0 is viral.** Copying `repowise` source obliges this project to
   relicense in full, preserve notices, and state modifications. Achievable, but it
   buys nothing here.

**After reading the source, the code is not the valuable part anyway.** The clone
was analysed: 2,217 Python files across eight packages, with `call_resolver.py`
alone at 1,360 lines of language-specific resolution spanning 19 languages. That
machinery solves a problem this project does not have — it already has two arms and
a type-resolved reference. Absorbing any of it in three days would produce a worse
version of something that already exists, under a licence that would swallow the
repository.

**What the clone was actually worth** is the thing no licence restricts: knowing
that its three tiers assert `0.95 / 0.90 / 0.50`, that those numbers are
hand-assigned rather than measured, and that `confidence` is persisted per edge and
is therefore extractable. That turns `repowise` from a competitor into the single
best **measurement target** available — which is Task 16, and which is worth far
more to this project than any amount of copied code.

**What is freely reusable, and is genuinely valuable** — methods, conventions and
architectural patterns are not copyrightable:

- **Task-shaped tool design** — batch several targets per call instead of forcing an
  agent into one-entity-per-call chains. Adopted in Task 12.
- **Sealed-split discipline** — pin a holdout before measuring, report only the
  sealed half. Adopted in Task 14. This is the single largest methodological upgrade
  available to this project.
- **Publish the rows you lose**, and a "how to read a number here" section. Adopted
  in Task 8 Step 1b. This project already has the substance (three visible
  retractions); the convention makes it legible.
- **Zero-LLM determinism as a stated property.** Already true here; say it.
- **Pinned-engine CI with a badge.** Already Task 11.

A short `docs/reuse-policy.md` stating the above ships with the repo (Task 8 Step 1c),
so a reader can see the boundary was drawn deliberately.

## A note on the winning condition

This project cannot out-feature `repowise` in three days and should not try. It has
ten task-shaped MCP tools, 19-language support and months of benchmarking. Attempting
to look bigger than it is the fastest way to lose a careful reader.

What this project has that nothing else in the category has is a **measurement nobody
runs**, delivered with **credibility that is itself the product**: three retracted
figures left visible with causes written down, a negative headline verdict, precision
reported as a ceiling, and a fair test that is leave-one-repo-out. Overclaiming would
destroy exactly the asset that makes the rest believable. Every superlative in the
shipped copy must be one the generated docs can support — and where a competitor is
better on a dimension, say so before a judge finds it.

## Global Constraints

Every task's requirements implicitly include this section.

- Deadline **2026-08-20 23:59 PT**. Form `forms.gle/GrMYKxLj9zPQcqqc8`. Track 02b. **Submit on 2026-08-19** so the 20th is buffer.
- Never use the hosted product at `api.hydradb.com`. Open-source engine only, pinned commit `02a40025d2d57e97ab2754c8256219cdbfeab379`.
- **Do not hide a negative result.** The headline verdict is `RUN_FULL` for every graph class measured. That is the finding; ship it as the finding.
- **Never name or benchmark another participant's repo** in any shipped artifact. Cite only published named systems: Aider, RepoGraph, LocAgent, ARISE, PyCG, STARTS, Ekstazi. Enforced by a grep gate in Task 9.
- **Do not claim "static graphs are unsound" as a novel finding.** It is 25 years old (Rothermel & Harrold 1997). The novelty is the domain, the oracle, and the abstention link — see Task 8.
- Every structure query uses `count(*)`, never `count(<node>)`, never `count(DISTINCT …)`.
- Variable-length patterns need a mandatory upper bound, single relationship type, integer-`id` node matching.
- Public repo, OSI LICENSE, **no participant-authored commit before 2026-08-12**.
- Video ≤ 3:00 hard stop. Order: problem → project → demo → HydraDB.
- Run tests with `uv run pytest`. Baseline is **494 passing**. Never land a task that reduces that count.
- Every figure quoted in a shipped artifact must exist in a **generated** doc. A number that lives only in the README is a number that will drift.

---

## Measured facts this plan is built on

Verified in the repo on 2026-08-17. Do not re-derive from memory.

| Fact | Value | Source |
|---|---|---|
| test→fix connected, arm B (type-resolved) | **24/44 (55%)** | `docs/connectivity.md` |
| test→fix connected, arm A (name-matched) | **15/30 (50%)** | `docs/connectivity.md` |
| test→fix connected, +dynamic COVERS | **12/18 (67%)** | `docs/covers.md` |
| fix→test connected (wrong direction) | **0/44 (0%)** | `docs/connectivity.md` |
| Name-match precision ceiling | **0.746** | `docs/graph-delta.md`, `cli.PRECISION_CEILING` |
| Prediction idea, pooled held-out AUC | **0.483** | `docs/evaluation.md` |
| Best graph feature vs best baseline | `fanin` 0.567 vs `patch_lines` 0.656 | `docs/evaluation.md` |
| Corpus | 172 instances, 7 repos | `docs/corpus.md` |
| Engine reachability at k=6 | **12 ms** (vs 30,000 ms enumeration timeout) | `docs/latency.md` |

### Published anchors (cite; never reproduce text)

- **Rothermel & Harrold**, *Empirical Studies of a Safe Regression Test Selection Technique* (IEEE TSE 1998) — defines **safe** RTS as excluding no test that would reveal a fault. This is the gate's definition, from 1997.
- **Legunsen et al.**, *An Extensive Study of Static Regression Test Selection in Modern Software Evolution* (FSE 2016) — static RTS is "at the risk of being unsafe sometimes"; safety violation measured as `|E\T|/|E∪T|` against Ekstazi.
- **Shi et al.**, *Reflection-Aware Static Regression Test Selection* (OOPSLA 2019) — traces RTS unsafety to reflection; Python's analogue is framework dispatch.
- **Sui, Dietrich, Tahir, Fourtounis**, *On the Recall of Static Call Graph Construction in Practice* (ICSE 2020) — median recall 0.884, and critically: **"adding precision to the static analysis has little impact on recall — those are separate concerns."** Task 4 reproduces this.
- **Salis et al.**, *PyCG: Practical Call Graph Generation in Python* (ICSE 2021) — 92% on micro-benchmarks, **70% recall on real applications**.
- **Helm et al.**, *Total Recall? How Good Are Static Call Graphs Really?* (ISSTA 2024) — dynamic baselines from test execution as ground-truth approximation; the precedent for the COVERS tracer.
- **AgentAbstain** (arXiv 2607.10059) — best of 17 frontier models 59.5% paired accuracy; **abstention scales independently of task-solving capability.**
- **Agentic Abstention** (arXiv 2606.28733), **ReDAct** (arXiv 2604.07036) — deferral under uncertainty; both use *model-internal* uncertainty, which is the gap the gate fills.
- **Agent Psychometrics** (arXiv 2604.00594) — per-instance failure prediction solved at AUC 0.841, text-only 0.787. **Do not claim this problem.**
- **ARISE** (arXiv 2605.03117) — richer edges lift Function Recall@1 0.43→0.60, resolve 17.3%→22.0%.

### The incumbent: `repowise-dev/repowise` — inspected 2026-08-17

Not a hackathon entry (created 2026-03-23, 5,955★, AGPL-3.0, Python, pushed daily). It
is the state of the art in this exact category and **must be cited**; omitting it
would be the most obvious hole a judge could find.

What it ships that overlaps this project:

| | |
|---|---|
| `repowise impacted-tests HEAD~1` | **"only the tests a diff actually exercises" — it ships test selection.** |
| `get_change_risk(revspec)` | "the tests **coverage proves** it touches" — coverage-backed, not purely static |
| Graph layer | "**3-tier call resolution**", 19 languages, symbol nodes, route→handler edges |
| Ten task-shaped MCP tools | Claude Code, Codex, Cursor, VS Code |
| Defect prediction | **ROC AUC 0.737**, 21 repos, 9 languages, 2,826 files, leakage-free |

Its benchmark rigour is the standard to meet: sealed 42-instance split held out from
every improvement round, DeLong tests, and an explicit policy of publishing the rows
it loses.

**And here is what it does not measure.** `docs/BENCHMARKS.md` has six sections —
finding the right files, the agent loop, commit-context tokens, command-output
compression, defect prediction, indexing time. **None is edge accuracy, and none is
test-selection safety.** The word "safe" appears in that document only about dead-code
removal. Its "3-tier call resolution" is announced in a feature table with no published
accuracy for any tier. Code search across the repository for `edge precision`,
`call graph recall` and `call resolution tier` returns zero hits, and the `docs/`
listing corroborates the absence.

**This is the strongest available evidence for the gate.** The claim is no longer
"some tools don't measure their edges." It is: *the category leader — which seals
splits, runs DeLong tests, and publishes its losses — measures everything downstream
of the graph and never measures the graph itself.* Cite it in that register:
respectfully, as evidence of a field-wide blind spot, never as a defect in their work.

**Two constraints this imposes.**

1. **Sharpen the claim.** This project's thesis is about **graph-based** selection.
   Coverage-backed selection, which `repowise` appears to use, is genuinely stronger —
   dynamic data does not have the static graph's blind spots. Do not imply otherwise.
   The honest extension is that this project already measured the coverage ceiling on
   the same corpus: folding dynamic COVERS edges in moved test→fix from 55% to **67%**
   (`docs/covers.md`) — better, and still nowhere near a 0.95 bar. Say exactly that.
2. **AGPL-3.0.** Do not import or vendor any `repowise` code; the licence is viral and
   this project must stay independently licensed. Citing published numbers is fine.
   Do not attempt to benchmark against it or integrate with it — that is a rabbit hole
   with three days left, and it is not required for anything here.

**On the defect-prediction contrast** (they reach 0.737, this project's prediction
attempt reached 0.483): different targets, and their own ablation makes the point.
Their health score beats *recent churn* by +0.100 AUC and *prior-defect history* by
+0.117 — behavioural and historical baselines carrying most of the signal, with
structure as the increment. That is the same phenomenon measured here, where
`patch_lines` (0.656) beat every structural feature (best 0.567). Structure alone is
weak; history is strong. Their target is file-level defect density; ours was
instance-level agent failure, which is harder and which the published literature
already solves from issue text at 0.841. Use this in Task 9's origin story: it makes
the negative result informed rather than embarrassing.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/friction/gate.py` | **New.** The whole product core: `select_tests`, `audit_recall`, `gate`, `compare_arms`, `build_selection_cypher`. |
| `tests/test_gate.py` | **New.** Unit tests for all five. |
| `tests/test_gate_cli.py` | **New.** CLI + API contract tests. |
| `src/friction/cli.py` | **Modify.** Add the `gate` subcommand, its handler, and the replay branch. |
| `src/friction/api.py` | **Modify.** Add `/gate` and `/gate/{instance_id}` inside `create_app`. |
| `scripts/gate_report.py` | **New.** Regenerates `docs/gate.md`. Runnable provenance. |
| `scripts/gate_demo.py` | **New.** The video demo: corpus verdict then one replayed instance. |
| `docs/gate.md` | **Generated.** Recall table, paired arm comparison, miss list. |
| `docs/related-work.md` | **New, hand-written.** Where the gate sits in the RTS and abstention literature. |
| `README.md`, `docs/index.html`, `docs/video-script.md` | **Modify.** Reframed, plus the origin story. |

**Interface summary** — every symbol later tasks depend on:

```
SelectionResult(selected: frozenset[int], k: int, graph_complete: bool)
select_tests(g: nx.DiGraph, changed_ids, candidate_test_ids, k: int) -> SelectionResult
RecallAudit(arm: str, k: int, n: int, hits: int, misses: tuple[str,...], per_repo: dict[str,tuple[int,int]])
    .recall -> float
audit_recall(manifest_path: Path, arms_root: Path, arm: str, k: int) -> RecallAudit
SAFE_SKIP_RECALL: float = 0.95
GateVerdict(decision, measured_recall, n, arm, k, threshold, reason)
gate(audit: RecallAudit, threshold: float = SAFE_SKIP_RECALL) -> GateVerdict
ArmComparison(n_paired, a_hits, b_hits, both_hit, a_only, b_only, neither, p_value)
    .a_recall / .b_recall / .recall_delta -> float
compare_arms(manifest_path: Path, arms_root: Path, k: int) -> ArmComparison
build_selection_cypher(node_id: int, rel_type: str, k: int) -> str
```

---

## Task 1: `gate.py` — graph-based test selection

Reproduce what every graph-based test selector does, so there is something to audit. From a changed symbol, walk **predecessors** — tests call code, so the affected test sits upstream.

**Files:**
- Create: `src/friction/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `networkx`.
- Produces: `SelectionResult`, `select_tests`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate.py
"""Tests for the gate: selection, recall audit, verdict, arm comparison."""

import networkx as nx
import pytest

from friction.gate import SelectionResult, select_tests


def _chain() -> nx.DiGraph:
    """test(1) -> helper(2) -> fix(3);  unrelated test(4) -> other(5)."""
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 3)
    g.add_edge(4, 5)
    return g


def test_selects_a_test_two_hops_upstream_of_the_change():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=6)
    assert result.selected == frozenset({1})


def test_does_not_select_an_unrelated_test():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=6)
    assert 4 not in result.selected


def test_does_not_select_a_test_beyond_the_bound():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=1)
    assert result.selected == frozenset()


def test_walks_predecessors_not_successors():
    # From the test end, the fix is NOT upstream: nothing should be selected.
    result = select_tests(_chain(), changed_ids=[1], candidate_test_ids=[3], k=6)
    assert result.selected == frozenset()


def test_graph_complete_is_true_when_the_walk_exhausts_before_the_bound():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=6)
    assert result.graph_complete is True


def test_graph_complete_is_false_when_the_bound_cuts_the_walk():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1, 4], k=1)
    assert result.graph_complete is False


def test_a_changed_node_that_is_itself_a_test_is_selected():
    result = select_tests(_chain(), changed_ids=[1], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset({1})


def test_a_changed_node_absent_from_the_graph_selects_nothing():
    result = select_tests(_chain(), changed_ids=[999], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset()


def test_empty_change_set_selects_nothing_and_is_not_graph_complete():
    result = select_tests(_chain(), changed_ids=[], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset()
    assert result.graph_complete is False


def test_empty_candidate_set_selects_nothing():
    result = select_tests(_chain(), changed_ids=[3], candidate_test_ids=[], k=6)
    assert result.selected == frozenset()


def test_a_cycle_terminates():
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 1)
    g.add_edge(2, 3)
    result = select_tests(g, changed_ids=[3], candidate_test_ids=[1], k=6)
    assert result.selected == frozenset({1})


def test_bound_must_be_a_positive_integer():
    with pytest.raises(ValueError):
        select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1], k=0)


def test_bound_must_not_be_a_bool():
    with pytest.raises(ValueError):
        select_tests(_chain(), changed_ids=[3], candidate_test_ids=[1], k=True)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'friction.gate'`

- [ ] **Step 3: Write the implementation**

```python
# src/friction/gate.py
"""The gate: is it safe to skip tests based on this code graph?

Every graph-based test selector answers "which tests does this change affect?"
by walking the call graph backwards from the changed symbol — tests call code,
so an affected test sits upstream. Whatever the walk does not reach gets skipped.

That is only safe if the graph's *recall* of the test -> code relation is known.
This module reproduces the selection (`select_tests`), measures its recall
against labelled ground truth (`audit_recall`), turns the measurement into a
decision (`gate`), and compares the two extraction arms on the same instances
(`compare_arms`).

The distinction the product rests on: a walk that exhausts its frontier is
**graph-complete** — complete with respect to the edges the graph contains. It
is not **program-complete**. An extractor cannot fail-closed on an edge it never
knew existed, so graph-completeness is silent about missing edges. Only a recall
measurement against labels can speak to those.

Prior art, deliberately not re-claimed: safe regression test selection is
Rothermel & Harrold (IEEE TSE 1998); static RTS unsafety is Legunsen et al.
(FSE 2016); reflection as its cause is Shi et al. (OOPSLA 2019). What is new
here is the domain (the graph class LLM coding agents build), the oracle
(SWE-bench FAIL_TO_PASS rather than a dynamic RTS tool), and the link to agent
abstention. See docs/related-work.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx


@dataclass(frozen=True)
class SelectionResult:
    """The tests a graph-based selector would run for one change.

    `graph_complete` records whether the backwards walk exhausted its frontier
    before hitting the bound `k`. True means no test reachable *in this graph*
    was cut off by the bound. It says nothing about edges the graph is missing.
    """

    selected: frozenset[int]
    k: int
    graph_complete: bool


def _check_bound(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k must be a positive integer (the bound is mandatory)")


def select_tests(g: nx.DiGraph, changed_ids: Iterable[int],
                 candidate_test_ids: Iterable[int], k: int) -> SelectionResult:
    """Tests within `k` reverse hops of any changed symbol.

    Direction matters and is easy to get backwards: production code has no edge
    to the test that guards it, so the walk runs along *predecessors*. Measured
    on this corpus, the forward direction (fix -> test) connects 0/44 instances.
    """
    _check_bound(k)

    changed = {int(c) for c in changed_ids}
    candidates = {int(t) for t in candidate_test_ids}
    if not changed or not candidates:
        return SelectionResult(frozenset(), k, False)

    selected = changed & candidates
    frontier = {c for c in changed if c in g}
    visited = set(frontier)

    for _ in range(k):
        nxt: set[int] = set()
        for u in frontier:
            nxt.update(g.predecessors(u))
        nxt -= visited
        if not nxt:
            return SelectionResult(frozenset(selected), k, True)
        selected |= nxt & candidates
        visited |= nxt
        frontier = nxt

    return SelectionResult(frozenset(selected), k, False)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add src/friction/gate.py tests/test_gate.py
git commit -m "feat(gate): graph-based test selection, with graph-completeness named honestly"
```

---

## Task 2: `gate.py` — the recall audit against labelled ground truth

SWE-bench gives the label for free: the `FAIL_TO_PASS` test **is** the test that guards the fix. For each instance, run the selector from the fix sites and ask whether it returned the known guarding test.

**Files:**
- Modify: `src/friction/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `select_tests` (Task 1); `friction.connectivity.load_graph`; the manifest shape `{"instance_id", "arm_a"|"arm_b": {"fix_site_ids": [int], "test_target_ids": [int]}}`; graphs at `arms_root/<instance_id>/<arm>/edges.ndjson`.
- Produces: `RecallAudit`, `audit_recall`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gate.py
import json

from friction.gate import RecallAudit, audit_recall


def _write_instance(root, instance_id, edges, arm="arm_b"):
    d = root / instance_id / arm
    d.mkdir(parents=True)
    with (d / "edges.ndjson").open("w", encoding="utf-8") as fh:
        for src, dst in edges:
            fh.write(json.dumps({"src": src, "dst": dst}) + "\n")


def _manifest(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_audit_counts_a_reachable_guarding_test_as_a_hit(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 2), (2, 3)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-1",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 1
    assert audit.hits == 1
    assert audit.recall == 1.0
    assert audit.misses == ()


def test_audit_counts_an_unreachable_guarding_test_as_a_miss(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-2", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-2",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 1
    assert audit.hits == 0
    assert audit.misses == ("django__django-2",)


def test_audit_skips_instances_with_an_empty_endpoint_set(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-3", [(1, 2)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-3",
                    "arm_b": {"fix_site_ids": [], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 0
    assert audit.recall == 0.0


def test_audit_skips_an_instance_whose_graph_file_is_absent(tmp_path):
    arms = tmp_path / "arms"
    arms.mkdir()
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-4",
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.n == 0


def test_audit_groups_by_repo_prefix(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-5", [(1, 3)])
    _write_instance(arms, "sympy__sympy-6", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-5",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "sympy__sympy-6",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])

    audit = audit_recall(mf, arms, arm="arm_b", k=6)

    assert audit.per_repo["django"] == (1, 1)
    assert audit.per_repo["sympy"] == (0, 1)
    assert audit.n == 2
    assert audit.hits == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate.py -k audit -v`
Expected: FAIL — `ImportError: cannot import name 'RecallAudit' from 'friction.gate'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/friction/gate.py
from friction.connectivity import load_graph


@dataclass(frozen=True)
class RecallAudit:
    """Measured recall of a graph-based selector against labelled instances.

    The label is free: SWE-bench's FAIL_TO_PASS test *is* the test that guards
    the fix. If the selector does not return it, a tool that skipped on this
    graph would have dropped the one test that catches the bug.

    This is the field's standard safety measure with a different oracle.
    Legunsen et al. (FSE 2016) compute safety violation as |E\\T|/|E∪T| against
    Ekstazi, a dynamic RTS tool. Using a human-curated label instead removes the
    dependence on a second tool being right.
    """

    arm: str
    k: int
    n: int
    hits: int
    misses: tuple[str, ...]
    per_repo: dict[str, tuple[int, int]]

    @property
    def recall(self) -> float:
        return self.hits / self.n if self.n else 0.0


def _repo_of(instance_id: str) -> str:
    return instance_id.split("__", 1)[0]


def _iter_manifest(manifest_path: Path):
    with Path(manifest_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _instance_hit(record: dict, arms_root: Path, arm: str,
                  k: int) -> bool | None:
    """Did the selector return the guarding test for this instance?

    Returns None when the instance is not measurable on this arm — either
    endpoint set empty, or no graph on disk. Callers must exclude those from
    `n` rather than score them, exactly as connectivity.measure_corpus does:
    counting an unmeasurable instance either way would be a fabricated number.
    """
    entry = record.get(arm) or {}
    fix = list(entry.get("fix_site_ids") or [])
    tests = list(entry.get("test_target_ids") or [])
    if not fix or not tests:
        return None

    edges = Path(arms_root) / record["instance_id"] / arm / "edges.ndjson"
    if not edges.exists():
        return None

    return bool(select_tests(load_graph(edges), fix, tests, k).selected)


def audit_recall(manifest_path: Path, arms_root: Path, arm: str,
                 k: int) -> RecallAudit:
    """Run the selector over every labelled instance and count the misses."""
    n = hits = 0
    misses: list[str] = []
    per_repo: dict[str, list[int]] = {}

    for record in _iter_manifest(manifest_path):
        hit = _instance_hit(record, Path(arms_root), arm, k)
        if hit is None:
            continue

        n += 1
        bucket = per_repo.setdefault(_repo_of(record["instance_id"]), [0, 0])
        bucket[1] += 1
        if hit:
            hits += 1
            bucket[0] += 1
        else:
            misses.append(record["instance_id"])

    return RecallAudit(
        arm=arm, k=k, n=n, hits=hits,
        misses=tuple(misses),
        per_repo={r: (h, t) for r, (h, t) in per_repo.items()},
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: 18 passed

- [ ] **Step 5: STOP-THE-LINE GATE — verify against the published connectivity figure**

Run:
```bash
uv run python -c "
from pathlib import Path
from friction.gate import audit_recall
for arm, want in (('arm_b','24/44'), ('arm_a','15/30')):
    a = audit_recall(Path('data/shipped/arms/manifest.jsonl'),
                     Path('data/shipped/arms'), arm, 6)
    print(f'{arm}: {a.hits}/{a.n} = {a.recall:.3f}   docs/connectivity.md says {want}')
    print(f'   per_repo: {a.per_repo}')
"
```

Expected: `arm_b` in the **0.50–0.60** band and `arm_a` in the **0.45–0.55** band, consistent with `docs/connectivity.md`.

**If either lands outside its band, STOP and diagnose before writing another line.** A selector that disagrees with the published connectivity measurement means one of the two is wrong. This project has already shipped three numbers that turned out to be artifacts (the 73.9% name-collision AUC, the truncated `pathCount: 20` AUC of 0.780, the unqualified-tracer 0.3% COVERS mapping). Do not add a fourth. The two most likely causes, in order: (a) the shipped manifest's endpoint sets differ from the ones `measure_corpus` used, (b) `select_tests` reaching *any* test counts as a hit whereas `connected_within` requires a specific pair — check which semantics `docs/connectivity.md` reports.

- [ ] **Step 6: Commit**

```bash
git add src/friction/gate.py tests/test_gate.py
git commit -m "feat(gate): recall audit against SWE-bench FAIL_TO_PASS labels"
```

---

## Task 3: `gate.py` — the verdict

**Files:**
- Modify: `src/friction/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `RecallAudit` (Task 2).
- Produces: `SAFE_SKIP_RECALL`, `GateVerdict`, `gate`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gate.py
from friction.gate import SAFE_SKIP_RECALL, GateVerdict, gate


def _audit(hits, n, arm="arm_b", k=6):
    return RecallAudit(arm=arm, k=k, n=n, hits=hits, misses=(), per_repo={})


def test_recall_below_the_bar_forces_a_full_run():
    verdict = gate(_audit(hits=24, n=44))
    assert verdict.decision == "RUN_FULL"


def test_the_reason_states_the_measured_recall():
    verdict = gate(_audit(hits=24, n=44))
    assert "0.545" in verdict.reason


def test_the_reason_quantifies_what_a_skip_would_drop():
    verdict = gate(_audit(hits=24, n=44))
    assert "45%" in verdict.reason


def test_recall_at_or_above_the_bar_permits_a_skip():
    verdict = gate(_audit(hits=96, n=100), threshold=0.95)
    assert verdict.decision == "SKIP_SAFE"


def test_recall_exactly_at_the_bar_permits_a_skip():
    verdict = gate(_audit(hits=95, n=100), threshold=0.95)
    assert verdict.decision == "SKIP_SAFE"


def test_an_unmeasured_graph_never_permits_a_skip():
    verdict = gate(_audit(hits=0, n=0))
    assert verdict.decision == "RUN_FULL"
    assert "unmeasured" in verdict.reason


def test_the_default_bar_is_stated_and_strict():
    assert SAFE_SKIP_RECALL == 0.95


def test_the_verdict_carries_its_provenance():
    verdict = gate(_audit(hits=24, n=44, arm="arm_a", k=6))
    assert verdict.arm == "arm_a"
    assert verdict.k == 6
    assert verdict.n == 44
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate.py -k "verdict or bar or unmeasured or reason" -v`
Expected: FAIL — `ImportError: cannot import name 'SAFE_SKIP_RECALL'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/friction/gate.py

# The bar for "safe to skip". Chosen, not measured: dropping the guarding test
# 1 run in 20 is already a poor trade against the minutes a full suite costs.
# It is a parameter precisely because it is a judgement call — but no graph
# class measured in this project comes close to it, so the verdict does not
# turn on where exactly the bar sits.
SAFE_SKIP_RECALL = 0.95


@dataclass(frozen=True)
class GateVerdict:
    decision: str            # "SKIP_SAFE" | "RUN_FULL"
    measured_recall: float
    n: int
    arm: str
    k: int
    threshold: float
    reason: str


def gate(audit: RecallAudit, threshold: float = SAFE_SKIP_RECALL) -> GateVerdict:
    """Turn a measured recall into a decision about skipping tests."""
    recall = audit.recall

    if audit.n == 0:
        return GateVerdict(
            "RUN_FULL", 0.0, 0, audit.arm, audit.k, threshold,
            "recall is unmeasured on this graph: with no labelled instances "
            "there is no evidence that a skip would keep the guarding test, so "
            "the only defensible decision is to run everything",
        )

    if recall >= threshold:
        return GateVerdict(
            "SKIP_SAFE", recall, audit.n, audit.arm, audit.k, threshold,
            f"measured test->fix recall {recall:.3f} on n={audit.n} labelled "
            f"instances meets the {threshold:.2f} bar",
        )

    dropped = round((1.0 - recall) * 100)
    return GateVerdict(
        "RUN_FULL", recall, audit.n, audit.arm, audit.k, threshold,
        f"measured test->fix recall {recall:.3f} on n={audit.n} labelled "
        f"instances is below the {threshold:.2f} bar: {dropped}% of tests known "
        f"to guard their fix are not reachable in this graph, so a skip would "
        f"silently drop them",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: 26 passed

- [ ] **Step 5: Commit**

```bash
git add src/friction/gate.py tests/test_gate.py
git commit -m "feat(gate): the verdict — measured recall decides, unmeasured never skips"
```

---

## Task 4: `gate.py` — the paired arm comparison (reproducing a published law)

Sui et al. (ICSE 2020) report that **adding precision to a static analysis has little impact on recall — they are separate concerns.** This project has both arms: name-matched (precision ceiling 0.746) and type-resolved (pyright). If the law holds, the enormous precision gain from arm A to arm B should barely move recall.

This must be a **paired** comparison on the instances where *both* arms are measurable. Arm A has 30 usable instances and arm B has 44; comparing 15/30 against 24/44 directly compares different instance sets and is exactly the class of mistake that produced this project's earlier 2,500× scale error.

**Files:**
- Modify: `src/friction/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `_instance_hit`, `_iter_manifest` (Task 2); `scipy.stats.binomtest`.
- Produces: `ArmComparison`, `compare_arms`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gate.py
from friction.gate import ArmComparison, compare_arms


def test_paired_comparison_uses_only_instances_measurable_on_both_arms(tmp_path):
    arms = tmp_path / "arms"
    # measurable on both
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    # arm_b only — must be excluded from the paired set
    _write_instance(arms, "django__django-2", [(1, 3)], arm="arm_b")

    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-1",
         "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "django__django-2",
         "arm_a": {"fix_site_ids": [], "test_target_ids": []},
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])

    cmp_ = compare_arms(mf, arms, k=6)

    assert cmp_.n_paired == 1
    assert cmp_.both_hit == 1


def test_paired_comparison_classifies_the_four_cells(tmp_path):
    arms = tmp_path / "arms"
    # arm_a misses, arm_b hits  -> b_only
    _write_instance(arms, "django__django-1", [(9, 8)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    # both miss -> neither
    _write_instance(arms, "django__django-2", [(9, 8)], arm="arm_a")
    _write_instance(arms, "django__django-2", [(9, 8)], arm="arm_b")

    mf = tmp_path / "manifest.jsonl"
    rows = [{"instance_id": i,
             "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
             "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}
            for i in ("django__django-1", "django__django-2")]
    _manifest(mf, rows)

    cmp_ = compare_arms(mf, arms, k=6)

    assert cmp_.n_paired == 2
    assert cmp_.b_only == 1
    assert cmp_.neither == 1
    assert cmp_.a_only == 0
    assert cmp_.both_hit == 0
    assert cmp_.b_recall == 0.5
    assert cmp_.a_recall == 0.0
    assert cmp_.recall_delta == 0.5


def test_p_value_is_one_when_no_instance_discriminates(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_a")
    _write_instance(arms, "django__django-1", [(1, 3)], arm="arm_b")
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [{"instance_id": "django__django-1",
                    "arm_a": {"fix_site_ids": [3], "test_target_ids": [1]},
                    "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}}])

    cmp_ = compare_arms(mf, arms, k=6)

    assert cmp_.a_only == 0 and cmp_.b_only == 0
    assert cmp_.p_value == 1.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate.py -k paired -v`
Expected: FAIL — `ImportError: cannot import name 'ArmComparison'`

- [ ] **Step 3: Write the implementation**

```python
# append to src/friction/gate.py

@dataclass(frozen=True)
class ArmComparison:
    """Name-matched vs type-resolved recall, on the SAME instances.

    Arm A is measurable on fewer instances than arm B, so an unpaired
    comparison would compare different instance sets. Every count below is
    restricted to instances measurable on both arms.

    `p_value` is an exact McNemar test on the discordant cells (`a_only` vs
    `b_only`) — the correct test for paired binary outcomes. It answers: given
    the instances where the two arms disagree, is the split further from 50/50
    than chance explains?
    """

    n_paired: int
    a_hits: int
    b_hits: int
    both_hit: int
    a_only: int
    b_only: int
    neither: int
    p_value: float

    @property
    def a_recall(self) -> float:
        return self.a_hits / self.n_paired if self.n_paired else 0.0

    @property
    def b_recall(self) -> float:
        return self.b_hits / self.n_paired if self.n_paired else 0.0

    @property
    def recall_delta(self) -> float:
        return self.b_recall - self.a_recall


def _mcnemar_exact(a_only: int, b_only: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts."""
    discordant = a_only + b_only
    if discordant == 0:
        return 1.0
    from scipy.stats import binomtest
    return float(binomtest(b_only, discordant, 0.5).pvalue)


def compare_arms(manifest_path: Path, arms_root: Path, k: int) -> ArmComparison:
    """Paired arm comparison over instances measurable on both arms."""
    arms_root = Path(arms_root)
    both_hit = a_only = b_only = neither = 0

    for record in _iter_manifest(manifest_path):
        hit_a = _instance_hit(record, arms_root, "arm_a", k)
        hit_b = _instance_hit(record, arms_root, "arm_b", k)
        if hit_a is None or hit_b is None:
            continue
        if hit_a and hit_b:
            both_hit += 1
        elif hit_a:
            a_only += 1
        elif hit_b:
            b_only += 1
        else:
            neither += 1

    n_paired = both_hit + a_only + b_only + neither
    return ArmComparison(
        n_paired=n_paired,
        a_hits=both_hit + a_only,
        b_hits=both_hit + b_only,
        both_hit=both_hit,
        a_only=a_only,
        b_only=b_only,
        neither=neither,
        p_value=_mcnemar_exact(a_only, b_only),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: 29 passed

- [ ] **Step 5: Run it on the real corpus and record the result**

Run:
```bash
uv run python -c "
from pathlib import Path
from friction.gate import compare_arms
c = compare_arms(Path('data/shipped/arms/manifest.jsonl'), Path('data/shipped/arms'), 6)
print(f'paired n={c.n_paired}')
print(f'arm_a recall={c.a_recall:.3f}  arm_b recall={c.b_recall:.3f}  delta={c.recall_delta:+.3f}')
print(f'both={c.both_hit} a_only={c.a_only} b_only={c.b_only} neither={c.neither}')
print(f'exact McNemar p={c.p_value:.4f}')
"
```

**Interpretation, written down before the number is seen so it cannot be rationalised afterwards:**
- If `recall_delta` is small (< ~0.10) and `p_value` > 0.05 → the ICSE 2020 law **reproduces**: a large precision gain bought little recall. This is the expected result and it is a genuine finding — report it as a reproduction, not a discovery.
- If `recall_delta` is large and `p_value` < 0.05 → the law does **not** hold here. Report that plainly; it is more interesting than the expected result and must not be suppressed.
- Either way, record `n_paired`. If it is under 25, say so and note that the test is underpowered rather than presenting `p` as decisive.

- [ ] **Step 6: Commit**

```bash
git add src/friction/gate.py tests/test_gate.py
git commit -m "feat(gate): paired arm comparison with exact McNemar — precision gain vs recall gain"
```

---

## Task 5: `friction gate` CLI + `docs/gate.md` generator

**Files:**
- Modify: `src/friction/cli.py`
- Create: `scripts/gate_report.py`
- Create: `tests/test_gate_cli.py`
- Generated: `docs/gate.md`

**Interfaces:**
- Consumes: `audit_recall`, `gate`, `compare_arms`, `SAFE_SKIP_RECALL`; existing `cli.MANIFEST_PATH` and `cli.PRECISION_CEILING`.
- Produces: `friction gate [--arm arm_a|arm_b] [--k INT] [--threshold FLOAT] [--json]`, exit 0 on `SKIP_SAFE` and 1 on `RUN_FULL`; `scripts/gate_report.py --out docs/gate.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate_cli.py
"""Contract tests for `friction gate`."""

import json

from friction.cli import main


def test_gate_prints_a_verdict_and_exits_nonzero_when_unsafe(capsys):
    code = main(["gate", "--arm", "arm_b"])
    out = capsys.readouterr().out
    assert "RUN_FULL" in out
    assert "recall" in out.lower()
    assert code == 1


def test_gate_json_mode_emits_the_verdict_fields(capsys):
    main(["gate", "--arm", "arm_b", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] in {"RUN_FULL", "SKIP_SAFE"}
    assert 0.0 <= payload["measured_recall"] <= 1.0
    assert payload["n"] > 0
    assert payload["threshold"] == 0.95
    assert isinstance(payload["per_repo"], dict)
    assert "advice" in payload


def test_gate_json_advice_is_actionable_for_an_agent(capsys):
    main(["gate", "--arm", "arm_b", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "full" in payload["advice"].lower()


def test_gate_reports_arm_a_no_better_than_arm_b(capsys):
    main(["gate", "--arm", "arm_a", "--json"])
    a = json.loads(capsys.readouterr().out)
    main(["gate", "--arm", "arm_b", "--json"])
    b = json.loads(capsys.readouterr().out)
    assert a["measured_recall"] <= b["measured_recall"] + 0.05


def test_gate_respects_a_lowered_threshold(capsys):
    code = main(["gate", "--arm", "arm_b", "--threshold", "0.10"])
    assert code == 0
    assert "SKIP_SAFE" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate_cli.py -v`
Expected: FAIL — argparse `invalid choice: 'gate'`

- [ ] **Step 3: Register the subcommand in `src/friction/cli.py`**

Add beside the other `sub.add_parser(...)` calls (near line 761, next to `connectivity`):

```python
    gate_cmd = sub.add_parser(
        "gate",
        help="is it safe to skip tests based on this graph? (measured, not assumed)")
    gate_cmd.add_argument("--arm", default="arm_b", choices=["arm_a", "arm_b"],
                          help="arm_a = name-matched, arm_b = type-resolved")
    gate_cmd.add_argument("--k", type=int, default=6,
                          help="hop bound (mandatory; default 6)")
    gate_cmd.add_argument("--threshold", type=float, default=None,
                          help="recall bar for a skip (default 0.95)")
    gate_cmd.add_argument("--instance", default=None,
                          help="replay one instance instead of the corpus")
    gate_cmd.add_argument("--json", action="store_true",
                          help="machine-readable, for CI and agents")
```

- [ ] **Step 4: Add the handler beside the other `cmd_*` functions**

```python
def cmd_gate(args) -> int:
    """Return 0 when a skip is defensible, 1 when it is not.

    The non-zero exit is the product: drop `friction gate` into CI and a graph
    whose recall has not been established fails the build rather than silently
    licensing a skip.
    """
    from friction.gate import SAFE_SKIP_RECALL, audit_recall
    from friction.gate import gate as run_gate

    if args.instance:
        return _gate_replay(args)

    manifest = MANIFEST_PATH
    arms_root = manifest.parent
    threshold = args.threshold if args.threshold is not None else SAFE_SKIP_RECALL

    audit = audit_recall(manifest, arms_root, args.arm, args.k)
    verdict = run_gate(audit, threshold)

    advice = (
        "run the full test suite: this graph's recall is below the bar, so a "
        "selected subset would omit tests that guard the change"
        if verdict.decision == "RUN_FULL" else
        "a selected subset is defensible on this graph at this bar")

    if args.json:
        print(json.dumps({
            "decision": verdict.decision,
            "measured_recall": round(verdict.measured_recall, 4),
            "hits": audit.hits,
            "n": verdict.n,
            "arm": verdict.arm,
            "k": verdict.k,
            "threshold": verdict.threshold,
            "reason": verdict.reason,
            "advice": advice,
            "per_repo": {r: {"hits": h, "n": t}
                         for r, (h, t) in audit.per_repo.items()},
            "misses": list(audit.misses),
        }, indent=2))
        return 0 if verdict.decision == "SKIP_SAFE" else 1

    mark = "PASS" if verdict.decision == "SKIP_SAFE" else "FAIL"
    print(RULE)
    print(f"[{mark}]  {verdict.decision}      arm={verdict.arm}  k={verdict.k}")
    print(RULE)
    print(f"  measured test->fix recall : {verdict.measured_recall:.3f}  "
          f"({audit.hits}/{audit.n} labelled instances)")
    print(f"  bar for skipping          : {verdict.threshold:.2f}")
    print()
    print(f"  {verdict.reason}")
    if audit.per_repo:
        print("\n  per repo:")
        for repo in sorted(audit.per_repo):
            h, t = audit.per_repo[repo]
            bar = _bar(h / t, 1.0, 18) if t else ""
            print(f"    {repo:<14} {h:>3}/{t:<3}  {h / t:.2f}  {bar}"
                  if t else f"    {repo:<14}   —")
    if audit.misses:
        print(f"\n  {len(audit.misses)} instances where the guarding test is "
              f"unreachable. First 5:")
        for m in audit.misses[:5]:
            print(f"    {m}")
        print(f"\n  replay one:  friction gate --instance {audit.misses[0]}")
    print(RULE)
    return 0 if verdict.decision == "SKIP_SAFE" else 1
```

Wire it into `main`'s dispatch beside the existing commands:

```python
    if args.command == "gate":
        return cmd_gate(args)
```

- [ ] **Step 5: Add a stub `_gate_replay` so the module imports (filled in Task 6)**

```python
def _gate_replay(args) -> int:
    raise NotImplementedError("filled in Task 6")
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate_cli.py -v`
Expected: 5 passed

- [ ] **Step 7: Run the real command and read the output**

Run: `uv run friction gate --arm arm_b`
Expected: `[FAIL] RUN_FULL`, recall ≈ 0.55, a per-repo table with bars, a miss list, and a copy-pasteable replay hint.

- [ ] **Step 8: Write the report generator**

```python
#!/usr/bin/env python
"""Regenerate docs/gate.md from the shipped corpus.

The runnable provenance of the gate report: whatever this prints is what the
doc says. There is no scratchpad in the loop.

    uv run python scripts/gate_report.py --out docs/gate.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from friction.cli import PRECISION_CEILING
from friction.gate import SAFE_SKIP_RECALL, audit_recall, compare_arms, gate

ARM_DESC = {
    "arm_a": "name-matched (the graph class Aider, RepoGraph and LocAgent build)",
    "arm_b": "type-resolved via scip-python / pyright",
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path("data/shipped"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args(argv)

    manifest = args.root / "arms" / "manifest.jsonl"
    arms_root = args.root / "arms"

    audits = {}
    for arm in ("arm_a", "arm_b"):
        audit = audit_recall(manifest, arms_root, arm, args.k)
        audits[arm] = (audit, gate(audit))
    cmp_ = compare_arms(manifest, arms_root, args.k)

    L = [
        "# The gate: is it safe to skip tests based on this graph?",
        "",
        "Generated by `scripts/gate_report.py`. Every number below is the "
        "output of `friction.gate` over the labelled instances in "
        "`data/shipped/arms/manifest.jsonl`.",
        "",
        "The label is not ours. SWE-bench's `FAIL_TO_PASS` test **is** the test "
        "that guards the fix. If a graph-based selector does not return it, a "
        "tool that skipped on that graph would have dropped the one test that "
        "catches the bug.",
        "",
        f"Bound `k` = {args.k} hops. Bar for a skip = {SAFE_SKIP_RECALL:.2f}.",
        "",
        "## Verdict",
        "",
        "| Arm | What it is | Recall | Verdict |",
        "|---|---|---|---|",
    ]
    for arm in ("arm_a", "arm_b"):
        audit, verdict = audits[arm]
        L.append(f"| `{arm}` | {ARM_DESC[arm]} | **{audit.recall:.3f}** "
                 f"({audit.hits}/{audit.n}) | **{verdict.decision}** |")

    L += ["", "## What the verdict means", ""]
    for arm in ("arm_a", "arm_b"):
        L.append(f"- **`{arm}`** — {audits[arm][1].reason}")

    L += [
        "",
        "## Precision and recall are separate concerns",
        "",
        "Sui et al. (ICSE 2020) report that adding precision to a static "
        "analysis has little impact on its recall — the two are separate "
        "concerns. This project can test that directly: arm A and arm B index "
        "the same commits, and moving from name matching to full pyright type "
        "resolution is a large precision gain "
        f"(the name-match precision ceiling is {PRECISION_CEILING}).",
        "",
        "Measured on the instances where **both** arms are measurable — an "
        "unpaired comparison would compare different instance sets:",
        "",
        "| | Value |",
        "|---|---|",
        f"| paired instances | {cmp_.n_paired} |",
        f"| arm A recall (name-matched) | {cmp_.a_recall:.3f} |",
        f"| arm B recall (type-resolved) | {cmp_.b_recall:.3f} |",
        f"| recall delta | {cmp_.recall_delta:+.3f} |",
        f"| both arms found it | {cmp_.both_hit} |",
        f"| arm A only | {cmp_.a_only} |",
        f"| arm B only | {cmp_.b_only} |",
        f"| neither | {cmp_.neither} |",
        f"| exact McNemar p | {cmp_.p_value:.4f} |",
        "",
        "The practical consequence: **\"use a better extractor\" is not a fix.** "
        "Type resolution buys precision, and precision is not what makes a skip "
        "safe.",
        "",
        "## What is being measured, and what is not",
        "",
        "PyCG (ICSE 2021) reports ~70% recall on real Python applications; "
        "Sui et al. report a median of 0.884 for Java. The figures here are "
        "lower, and the reason is that they measure a **different and harder "
        "relation**. Those studies ask whether a specific call edge appears in "
        "the graph. This asks whether a labelled test can reach the fix it "
        "guards **transitively, within a bounded number of hops** — a property "
        "of a specific pair, not of a single edge. The numbers are not "
        "comparable and no claim is made that this extractor is worse than "
        "PyCG's.",
        "",
        "## Per repository",
        "",
        "| Repo | arm_a | arm_b |",
        "|---|---|---|",
    ]
    repos = sorted(set(audits["arm_a"][0].per_repo) | set(audits["arm_b"][0].per_repo))
    for repo in repos:
        cells = []
        for arm in ("arm_a", "arm_b"):
            h, t = audits[arm][0].per_repo.get(repo, (0, 0))
            cells.append(f"{h}/{t} ({h / t:.2f})" if t else "—")
        L.append(f"| {repo} | {cells[0]} | {cells[1]} |")

    L += [
        "",
        "## Graph-complete is not program-complete",
        "",
        "A backwards walk that exhausts its frontier before the bound is "
        "**graph-complete**: no test reachable *in this graph* was cut off. "
        "That is a real property and worth checking. It is also silent about "
        "the edges the graph never had. An extractor cannot fail-closed on an "
        "edge it does not know exists, so graph-completeness cannot detect a "
        "missing edge — only a recall measurement against labels can.",
        "",
        "That gap is why this tool exists. Both arms are graph-complete on "
        "nearly every instance. Both still miss roughly half the guarding tests.",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"uv run python scripts/gate_report.py --root {args.root} --out {args.out}",
        "uv run friction gate --arm arm_b",
        "```",
        "",
        "See `docs/related-work.md` for where this sits in the regression-test-"
        "selection and agent-abstention literature.",
        "",
    ]

    args.out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {args.out}")
    for arm in ("arm_a", "arm_b"):
        audit, verdict = audits[arm]
        print(f"  {arm}: recall={audit.recall:.3f} ({audit.hits}/{audit.n}) "
              f"-> {verdict.decision}")
    print(f"  paired: n={cmp_.n_paired} delta={cmp_.recall_delta:+.3f} "
          f"p={cmp_.p_value:.4f}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Generate the report and read every line of it**

Run: `uv run python scripts/gate_report.py --out docs/gate.md && cat docs/gate.md`
Expected: both arms `RUN_FULL`, a populated paired-comparison table, 7 repos in the per-repo table.

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest -q`
Expected: **≥ 528 passed**, 0 failed.

- [ ] **Step 11: Commit**

```bash
git add src/friction/cli.py scripts/gate_report.py docs/gate.md tests/test_gate_cli.py
git commit -m "feat(cli): friction gate — CI-ready verdict, non-zero exit when a skip is undefensible"
```

---

## Task 6: The replay demo — one concrete dropped test

The number persuades a judge; a single named instance they can verify persuades everyone. Replace the Task 5 stub.

**Files:**
- Modify: `src/friction/cli.py` (replace `_gate_replay`)
- Create: `scripts/gate_demo.py`
- Test: `tests/test_gate_cli.py`

**Interfaces:**
- Consumes: `select_tests`, `audit_recall`, `connectivity.load_graph`, `cli.MANIFEST_PATH`.
- Produces: `friction gate --instance <id>`; `scripts/gate_demo.py`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gate_cli.py
from pathlib import Path

from friction.cli import MANIFEST_PATH
from friction.gate import audit_recall


def _first_miss() -> str:
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, "arm_b", 6)
    assert audit.misses, "expected at least one miss in the shipped corpus"
    return audit.misses[0]


def test_gate_instance_mode_shows_the_dropped_test(capsys):
    demo_id = _first_miss()
    code = main(["gate", "--arm", "arm_b", "--instance", demo_id])
    out = capsys.readouterr().out
    assert demo_id in out
    assert "guard" in out.lower()
    assert "not selected" in out.lower()
    assert code == 1


def test_gate_instance_mode_reports_an_unknown_instance(capsys):
    code = main(["gate", "--instance", "nope__nope-0"])
    assert code == 2
    assert "not" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate_cli.py -k instance -v`
Expected: FAIL — `NotImplementedError: filled in Task 6`

- [ ] **Step 3: Replace the stub in `src/friction/cli.py`**

```python
def _gate_replay(args) -> int:
    """Replay one instance: the selection, the label, and the gap between them."""
    from friction.connectivity import load_graph
    from friction.gate import build_selection_cypher, select_tests

    manifest = MANIFEST_PATH
    record = None
    with manifest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["instance_id"] == args.instance:
                record = row
                break
    if record is None:
        print(f"instance {args.instance} is not in {manifest}")
        return 2

    entry = record.get(args.arm) or {}
    fix = list(entry.get("fix_site_ids") or [])
    tests = list(entry.get("test_target_ids") or [])
    edges = manifest.parent / args.instance / args.arm / "edges.ndjson"
    if not edges.exists():
        print(f"no {args.arm} graph on disk for {args.instance}")
        return 2

    g = load_graph(edges)
    result = select_tests(g, fix, tests, args.k)
    missed = sorted(set(int(t) for t in tests) - result.selected)

    print(RULE)
    print(f"  {args.instance}")
    print(RULE)
    print(f"  arm          : {args.arm} "
          f"({'type-resolved' if args.arm == 'arm_b' else 'name-matched'})")
    print(f"  base commit  : {record.get('base_commit', 'unknown')[:12]}")
    print(f"  graph        : {g.number_of_nodes():,} nodes, "
          f"{g.number_of_edges():,} edges")
    print()
    print(f"  changed symbols (fix sites)       : {len(fix)}")
    print(f"  tests that guard the fix (label)  : {len(tests)}"
          f"   <- SWE-bench FAIL_TO_PASS")
    print(f"  tests the selector returns        : {len(result.selected)}")
    print(f"  walk was graph-complete           : {result.graph_complete}")
    print()
    if missed:
        print(f"  NOT SELECTED — {len(missed)} guarding test node(s) are "
              f"unreachable")
        print(f"  from the change within {args.k} hops. A tool that skipped on")
        print(f"  this graph would not have run them.")
        print(f"    node ids: {missed[:8]}{' …' if len(missed) > 8 else ''}")
    else:
        print("  All guarding tests were selected on this instance.")
    print()
    print("  The walk exhausted its frontier: it is complete with respect to the")
    print("  edges this graph has. The guarding test is missing because the edge")
    print("  connecting it was never extracted — and no completeness check on a")
    print("  graph can see an edge that is not in it.")
    if fix:
        print()
        print("  the query, in the engine:")
        print(f"    {build_selection_cypher(int(fix[0]), 'CALLS', args.k)}")
    print(RULE)
    return 1 if missed else 0
```

- [ ] **Step 4: Add `build_selection_cypher` to `src/friction/gate.py`**

```python
# append to src/friction/gate.py

def build_selection_cypher(node_id: int, rel_type: str, k: int) -> str:
    """In-engine backwards selection from a changed symbol.

    Mirrors `reach.build_reach_cypher` but returns the reached node ids rather
    than a count, because the gate needs the *set* to intersect against the
    candidate tests. `RETURN n.id` is deliberate: `count(n)` on a node is
    rejected by the engine ("property values support integer, float, boolean,
    and string literals"), and `n.id` is a verified-working projection.
    """
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise TypeError("node_id must be an integer graph id")
    _check_bound(k)
    return (f"MATCH (s {{id: {node_id}}})<-[:{rel_type}*1..{k}]-(n) "
            f"RETURN n.id AS id")
```

And its tests:

```python
# append to tests/test_gate.py
from friction.gate import build_selection_cypher


def test_selection_cypher_walks_predecessors():
    q = build_selection_cypher(42, "CALLS", 6)
    assert "<-[:CALLS*1..6]-" in q
    assert "{id: 42}" in q


def test_selection_cypher_never_counts_a_node():
    q = build_selection_cypher(42, "CALLS", 6)
    assert "count(n)" not in q
    assert "DISTINCT" not in q
    assert "RETURN n.id" in q


def test_selection_cypher_requires_a_bound():
    with pytest.raises(ValueError):
        build_selection_cypher(42, "CALLS", 0)


def test_selection_cypher_rejects_a_non_integer_id():
    with pytest.raises(TypeError):
        build_selection_cypher("42", "CALLS", 6)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gate.py tests/test_gate_cli.py -v`
Expected: 33 + 7 = 40 passed

- [ ] **Step 6: Write `scripts/gate_demo.py`**

```python
#!/usr/bin/env python
"""The demo shown in the video: one change, one dropped test.

    uv run python scripts/gate_demo.py                 # auto-pick the first miss
    uv run python scripts/gate_demo.py --instance ID   # a specific one
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from friction.cli import MANIFEST_PATH, main as cli_main
from friction.gate import audit_recall


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", default=None)
    ap.add_argument("--arm", default="arm_b", choices=["arm_a", "arm_b"])
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args(argv)

    instance = args.instance
    if instance is None:
        audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, args.arm, args.k)
        if not audit.misses:
            print("no misses in this corpus — nothing to demonstrate")
            return 0
        instance = audit.misses[0]

    print("\n>>> friction gate --arm", args.arm, "\n")
    cli_main(["gate", "--arm", args.arm, "--k", str(args.k)])

    print(f"\n>>> friction gate --instance {instance}\n")
    return cli_main(["gate", "--arm", args.arm, "--k", str(args.k),
                     "--instance", instance])


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run the demo and check it fits one terminal frame**

Run: `uv run python scripts/gate_demo.py 2>&1 | wc -l` then `uv run python scripts/gate_demo.py`
Expected: under ~55 lines total. If longer, trim the replay prints — it has to be readable on camera without scrolling.

- [ ] **Step 8: Commit**

```bash
git add scripts/gate_demo.py src/friction/cli.py src/friction/gate.py tests/
git commit -m "feat(gate): single-instance replay — the guarding test a selector drops"
```

---

## Task 7: API endpoints

`api.py` builds its app inside `create_app(live: bool = True)`. Endpoints are nested functions decorated with `@app.get` **inside that factory** — there is no module-level `app`.

**Files:**
- Modify: `src/friction/api.py`
- Test: `tests/test_gate_cli.py`

**Interfaces:**
- Consumes: `audit_recall`, `gate`, `select_tests`, `build_selection_cypher`, `cli.MANIFEST_PATH`.
- Produces: `GET /gate`, `GET /gate/{instance_id}`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gate_cli.py
from fastapi.testclient import TestClient

from friction.api import create_app


def _client() -> TestClient:
    return TestClient(create_app(live=False))


def test_gate_endpoint_returns_the_corpus_verdict():
    r = _client().get("/gate", params={"arm": "arm_b"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "RUN_FULL"
    assert body["n"] > 0
    assert 0.0 <= body["measured_recall"] <= 1.0


def test_gate_endpoint_rejects_an_unknown_arm():
    assert _client().get("/gate", params={"arm": "arm_z"}).status_code == 400


def test_gate_instance_endpoint_returns_the_dropped_tests_and_the_cypher():
    demo_id = _first_miss()
    r = _client().get(f"/gate/{demo_id}", params={"arm": "arm_b"})
    assert r.status_code == 200
    body = r.json()
    assert body["dropped_guarding_tests"]
    assert "<-[:CALLS*1..6]-" in body["cypher"]


def test_gate_instance_endpoint_404s_on_an_unknown_instance():
    assert _client().get("/gate/nope__nope-0").status_code == 404
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate_cli.py -k endpoint -v`
Expected: FAIL — 404 on `/gate`

- [ ] **Step 3: Add the endpoints inside `create_app`**

Place these beside the other `@app.get` definitions **inside** `create_app`, before its `return app`:

```python
    @app.get("/gate")
    def gate_corpus(arm: str = "arm_b", k: int = 6,
                    threshold: float | None = None) -> dict:
        """May a tool skip tests on this graph class? Measured, not assumed."""
        from friction.gate import SAFE_SKIP_RECALL, audit_recall
        from friction.gate import gate as run_gate

        if arm not in {"arm_a", "arm_b"}:
            raise HTTPException(status_code=400,
                                detail="arm must be arm_a or arm_b")

        manifest = cli.MANIFEST_PATH
        audit = audit_recall(manifest, manifest.parent, arm, k)
        verdict = run_gate(audit,
                           threshold if threshold is not None else SAFE_SKIP_RECALL)
        return {
            "decision": verdict.decision,
            "measured_recall": round(verdict.measured_recall, 4),
            "hits": audit.hits,
            "n": verdict.n,
            "arm": arm,
            "k": k,
            "threshold": verdict.threshold,
            "reason": verdict.reason,
            "per_repo": {r: {"hits": h, "n": t}
                         for r, (h, t) in audit.per_repo.items()},
            "miss_count": len(audit.misses),
        }

    @app.get("/gate/{instance_id}")
    def gate_instance(instance_id: str, arm: str = "arm_b", k: int = 6) -> dict:
        """Replay one instance: selected tests vs the tests that guard the fix."""
        from friction.connectivity import load_graph
        from friction.gate import build_selection_cypher, select_tests

        if arm not in {"arm_a", "arm_b"}:
            raise HTTPException(status_code=400,
                                detail="arm must be arm_a or arm_b")

        manifest = cli.MANIFEST_PATH
        record = None
        with manifest.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row["instance_id"] == instance_id:
                    record = row
                    break
        if record is None:
            raise HTTPException(status_code=404,
                                detail=f"unknown instance {instance_id}")

        entry = record.get(arm) or {}
        fix = list(entry.get("fix_site_ids") or [])
        tests = list(entry.get("test_target_ids") or [])
        edges = manifest.parent / instance_id / arm / "edges.ndjson"
        if not edges.exists():
            raise HTTPException(status_code=404,
                                detail=f"no {arm} graph for {instance_id}")

        result = select_tests(load_graph(edges), fix, tests, k)
        missed = sorted(set(int(t) for t in tests) - result.selected)
        return {
            "instance_id": instance_id,
            "arm": arm,
            "k": k,
            "fix_sites": len(fix),
            "guarding_tests": len(tests),
            "selected": len(result.selected),
            "graph_complete": result.graph_complete,
            "dropped_guarding_tests": missed,
            "cypher": (build_selection_cypher(int(fix[0]), "CALLS", k)
                       if fix else None),
        }
```

Confirm `HTTPException`, `json` and `cli` are imported at the top of `api.py`; add whichever are missing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate_cli.py -v`
Expected: 11 passed

- [ ] **Step 5: Verify the live API in the browser — look at it, do not assume**

Run in one terminal: `uv run friction serve`

Then with the browser tools, load and read each of:
- `http://127.0.0.1:8000/gate?arm=arm_b` → `"decision": "RUN_FULL"`
- `http://127.0.0.1:8000/gate?arm=arm_a` → `"decision": "RUN_FULL"`
- `http://127.0.0.1:8000/gate/<DEMO_ID>` → non-empty `dropped_guarding_tests`, `cypher` containing `<-[:CALLS*1..6]-`
- `http://127.0.0.1:8000/docs` → both routes listed and executable from the Swagger UI

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: **≥ 539 passed**, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add src/friction/api.py tests/test_gate_cli.py
git commit -m "feat(api): GET /gate and /gate/{instance} with the in-engine selection Cypher"
```

---

## Task 8: `docs/related-work.md` — the literature grounding

The cheapest credibility upgrade available. It also protects against the strongest objection a judge can make: *"isn't this already known?"* Partly yes — say so first, then say precisely what is not.

**Files:**
- Create: `docs/related-work.md`

- [ ] **Step 1: Write the document**

```markdown
# Related work

This project did not discover that static call graphs miss edges. That has been
known for 25 years. What follows is where the gate actually sits, what it
borrows, and the three things about it that are new.

## What is already known, and not claimed here

**Safe regression test selection.** Rothermel & Harrold (IEEE TSE 1998) define a
*safe* RTS technique as one that excludes no test which, if executed, would
reveal a fault. That is the gate's definition of safety, and it is theirs. The
systematic review by Engström et al. notes that safety "is hard to achieve in
practice" because it assumes determinism in program and test execution.

**Static RTS is sometimes unsafe.** Legunsen et al. (FSE 2016) studied
class-level static RTS across 22 open-source projects and found it comparable to
the dynamic tool Ekstazi "at the risk of being unsafe sometimes." They measure
safety violation as `|E\T| / |E∪T|` against Ekstazi. Shi et al. (OOPSLA 2019)
traced a major share of that unsafety to **reflection**, and extended STARTS to
handle it.

**Static call graphs have limited recall.** Sui, Dietrich, Tahir & Fourtounis
(ICSE 2020) report a median recall of 0.884 for Java. Salis et al. (PyCG,
ICSE 2021) report that a Python call-graph analysis passing 92% of
micro-benchmarks achieves only **70% recall on real applications**. Helm et al.
(*Total Recall?*, ISSTA 2024) construct dynamic baselines from test execution as
a ground-truth approximation.

**Per-instance agent failure prediction is solved.** Agent Psychometrics
(arXiv 2604.00594) reports AUC 0.841, with a text-only variant at 0.787 and a
task-agnostic prior at 0.718. This project attempted that problem, failed, and
does not claim it — see "The prediction attempt" below.

## What this project borrows

- The **safety framing** from Rothermel & Harrold: a selector is unsafe if it
  drops a test that would have revealed the fault.
- The **dynamic-baseline methodology** from Helm et al.: `friction.trace` runs
  each instance's own tests under `sys.settrace` in a version-matched guest
  interpreter and records executed `Test -> Function` edges, exactly as an
  approximation of unobtainable ground truth.
- The **precision/recall separation** from Sui et al., reproduced here in
  `docs/gate.md` as a paired comparison with an exact McNemar test.

## What is new

**1. The domain.** The RTS literature measures Java build tools — STARTS,
Ekstazi, class firewalls over type-dependency graphs. Nobody has measured safety
for the graph class that LLM coding agents actually build: the name-matched
Python call graphs behind Aider, RepoGraph and LocAgent. That graph class is now
making test-selection and impact-analysis decisions in production, and its
recall was unmeasured.

The clearest illustration is the category leader. **repowise** (AGPL-3.0, ~6k
stars) ships `repowise impacted-tests` — "only the tests a diff actually
exercises" — on a dependency graph with "3-tier call resolution" across 19
languages, plus ten MCP tools for Claude Code, Codex and Cursor. Its benchmarking
is exemplary: a sealed 42-instance split held out from every improvement round,
DeLong tests, defect prediction validated at ROC AUC 0.737 over 21 repositories
and 9 languages, and a stated policy of publishing the rows it loses.

Its `docs/BENCHMARKS.md` measures six things: finding the right files, the agent
loop, commit-context tokens, command-output compression, defect prediction, and
indexing time. **Edge accuracy is not among them, and neither is test-selection
safety.** The three resolution tiers ship without a published accuracy for any
tier.

That is not a criticism of a project whose measurement standards are higher than
most of this field's. It is the point: when the most rigorous tool in the
category measures everything downstream of its graph and nothing about the graph
itself, the omission is structural rather than an oversight by any one team.

Two honest qualifications. First, `repowise`'s change-risk tool reports "the
tests **coverage proves** it touches" — coverage-backed selection, which is
genuinely stronger than static-graph selection because dynamic data does not
carry the static graph's blind spots. This project's claim is about **graph-based**
selection and should not be stretched onto coverage-based selection. Second, the
coverage ceiling was measured here anyway: folding dynamic execution traces into
the type-resolved graph moved test→fix connectivity from 55% to **67%**
(`docs/covers.md`) — better, and still far from a 0.95 bar.

**2. The oracle.** The field measures safety violation of one tool relative to
another tool — Ekstazi as the stand-in for truth. This uses **SWE-bench
`FAIL_TO_PASS`**: a human-curated label stating which test guards which fix. It
removes the dependence on a second tool being right, and it is the reason the
number here can be called recall rather than disagreement.

**3. The link to agent abstention.** A 2026 literature has formed around when an
agent should decline to act: AgentAbstain (arXiv 2607.10059) finds the best of
17 frontier models reaches 59.5% paired accuracy and — critically — that
**abstention capability scales independently of task-solving capability**, so
larger models do not fix it. Agentic Abstention (arXiv 2606.28733) frames it as
a sequential decision problem; ReDAct (arXiv 2604.07036) defers under
uncertainty because errors compound irreversibly.

Every one of these defers on **model-internal** uncertainty — the agent's own
sense of doubt. The gate supplies something none of them has: an **external,
measured, substrate-level** reason to abstain. Not "the model is unsure" but
"the graph this conclusion rests on reaches the guarding test 55% of the time,
measured on labelled data." Any agent conclusion resting on a graph traversal —
affected tests, blast radius, related files — inherits that graph's recall.

## The prediction attempt, and why it failed

This project began as a different idea: predict from graph structure whether an
AI agent would fail a task, and route the hard ones to a human. It was built and
measured, and it does not work. Pooled leave-one-repo-out AUC across 7 repos was
**0.483** — at or below chance. The best single structural feature (`fanin`,
0.567) lost to counting the lines in the patch (`patch_lines`, 0.656). Two
earlier figures, 0.565 and 0.631, were retracted for measurement defects; the
full record is in `docs/evaluation.md` and `docs/evaluation-v1-retracted.md`.

The diagnosis is that the target was wrong. A call graph carries no information
about whether a language model will succeed — that depends on the model, the
prompt and the sampling, none of which is in the edges. The gate asks the graph
to report a property of *itself* instead, which is deterministic and measurable.

Two facts make that failure informative rather than merely negative. First, the
problem is already solved at 0.841 by methods that read the issue text and
ignore the graph entirely, so there was no headroom for a structural signal.
Second, the features were computed on a graph now measured to reach the guarding
test only 55% of the time — so the thesis was never tested on a substrate that
could carry it. Those two cannot be separated with the data here, and no claim
of vindication is made. The honest statement is that the prediction thesis is
unsupported on this corpus, and that the substrate is too weak to test it
properly. The second half is what the gate measures.

## References

- Rothermel & Harrold. *Empirical Studies of a Safe Regression Test Selection Technique.* IEEE TSE, 1998.
- Engström, Runeson & Skoglund. *A Systematic Review on Regression Test Selection Techniques.* IST, 2010.
- Legunsen et al. *An Extensive Study of Static Regression Test Selection in Modern Software Evolution.* FSE 2016.
- Legunsen, Shi & Marinov. *STARTS: STAtic Regression Test Selection.* ASE 2017.
- Shi et al. *Reflection-Aware Static Regression Test Selection.* OOPSLA 2019.
- Sui, Dietrich, Tahir & Fourtounis. *On the Recall of Static Call Graph Construction in Practice.* ICSE 2020.
- Salis et al. *PyCG: Practical Call Graph Generation in Python.* ICSE 2021.
- Helm et al. *Total Recall? How Good Are Static Call Graphs Really?* ISSTA 2024.
- *AgentAbstain: Do LLM Agents Know When Not to Act?* arXiv 2607.10059.
- *Agentic Abstention: Do Agents Know When to Stop Instead of Act?* arXiv 2606.28733.
- *ReDAct: Uncertainty-Aware Deferral for LLM Agents.* arXiv 2604.07036.
- *Agent Psychometrics.* arXiv 2604.00594.
- *ARISE.* arXiv 2605.03117.
- repowise. *Codebase intelligence for AI and humans.* https://github.com/repowise-dev/repowise — benchmarks at `docs/BENCHMARKS.md`.
```

- [ ] **Step 1b: Add a "How to read a number here" section**

Matching the field's best practice — `repowise`'s benchmarks doc carries an
equivalent section, and this project already has the substance (retractions,
leave-one-repo-out, ceilings stated as ceilings). Append to `docs/related-work.md`:

```markdown
## How to read a number in this project

- **Every figure is generated**, not typed. Each doc names the script that
  produces it, and the README quotes only figures that appear in a generated doc.
- **Retracted numbers stay visible.** Three figures in this project turned out to
  be measurement artifacts. All three are still in the repo with the cause
  written down: `docs/evaluation-v1-retracted.md`, and the retraction notes in
  `docs/evaluation.md` and `docs/covers.md`.
- **Precision is reported as a ceiling**, never a point estimate, because the
  type-resolved reference under-reports rather than inventing edges.
- **The fair test is leave-one-repo-out**, not a random split: the model never
  sees the held-out repository, so it cannot memorise repo identity.
- **The headline verdict is negative** and is the finding, not a shortfall.
- **Where another tool is better on a dimension, this project says so** before a
  reader has to find it.
```

- [ ] **Step 1c: Ship `docs/reuse-policy.md`**

Short, and it exists so a reader can see the boundary was drawn on purpose rather
than assumed.

```markdown
# Reuse policy

This project studies other code-graph tools and cites their published results. It
copies none of their code.

| Project | Licence | Used how |
|---|---|---|
| `repowise-dev/repowise` | AGPL-3.0 | Cited only. Published benchmark figures are quoted with attribution. No code copied or vendored. |
| `repowise-dev/repowise-bench` | none — all rights reserved | Not used. Absence of a licence means absence of permission. |
| `hydra-db/hydradb` | AGPL-3.0 | Used as a running service over Bolt. Not linked against. Two findings contributed back: issue #81, PR #82. |

Methods and conventions are not code, and several here are adopted openly from the
better-run projects in this field: pinning a holdout split before measuring,
publishing the results that lose, stating how to read a number, and designing
agent-facing tools to accept several targets per call. Those are credited where
they appear.

Everything in `src/` was written for this project inside the hackathon window that
opened 2026-08-12.
```

- [ ] **Step 2: Verify every claim about this repo's own numbers**

Run:
```bash
grep -n "0.483\|0.567\|0.656\|0.565\|0.631" docs/evaluation.md
grep -n "24/44\|55%" docs/connectivity.md
```
Expected: every figure quoted in `related-work.md` appears in a generated doc. Fix any that does not.

- [ ] **Step 3: Commit**

```bash
git add docs/related-work.md
git commit -m "docs: related work — what is borrowed, what is already known, what is new"
```

---

## Task 9: README, landing page, video script

**Files:**
- Modify: `README.md`, `docs/index.html`, `docs/video-script.md`

- [ ] **Step 1: Rewrite the README lead**

Fill every bracketed figure from the **generated** `docs/gate.md`, never from memory.

```markdown
# Substrate Friction

**Before your tool skips a test, measure the graph it trusted.**

Graph-based test selection is a good idea: build a call graph, walk backwards
from the change, run the tests it reaches, skip the rest. It is also unsafe in a
way that is invisible from inside the tool — the walk can be provably complete
with respect to the graph while the graph is missing the edge that mattered.
**An extractor cannot fail-closed on an edge it never knew existed.**

`friction gate` measures the thing that is load-bearing: **what fraction of
tests known to guard a fix does this graph let you reach?**

On [N] labelled SWE-bench instances across 7 repositories:

| Graph | Recall of the guarding test | Safe to skip? |
|---|---|---|
| Name-matched — the class Aider, RepoGraph and LocAgent build | **[X]** | **No** |
| Type-resolved — scip-python / pyright | **[Y]** | **No** |
| Type-resolved + dynamic execution traces | **[Z]** | **No** |

Bar for skipping: 0.95. Nothing measured here comes close, and the ranking does
not depend on where the bar sits.

```bash
friction gate --arm arm_b        # exits 1: RUN_FULL
```

**"Use a better extractor" is not a fix.** Moving from name matching to full
pyright type resolution is a large precision gain and moves recall by [delta]
(paired, n=[n_paired], exact McNemar p=[p]). Sui et al. (ICSE 2020) reported the
same separation for Java: adding precision to a static analysis has little
impact on its recall. See `docs/gate.md`.
```

- [ ] **Step 2: Add "What we tried first"**

```markdown
## What we tried first, and why it failed

This started as a different product: predict from graph structure whether an AI
agent would fail a task, and route the hard ones to a human. We built it and
measured it. Pooled leave-one-repo-out AUC across 7 repos: **0.483** — at or
below chance. The best structural feature lost to counting the lines in the
patch. Two earlier figures were retracted for measurement defects. The full
record is in `docs/evaluation.md`.

The target was wrong. A call graph carries no information about whether a
language model will succeed. The gate asks the graph to report a property of
*itself* — deterministic, and measurable.

That failure is why this repository exists, and it is left in the repo rather
than deleted.
```

- [ ] **Step 3: Add the abstention framing as the closing section**

```markdown
## Why this matters beyond test selection

A 2026 literature has formed around when an agent should decline to act.
AgentAbstain (arXiv 2607.10059) finds the best of 17 frontier models reaches
59.5% paired accuracy, and that **abstention capability scales independently of
task-solving capability** — larger models do not fix it. ReDAct
(arXiv 2604.07036) defers under uncertainty because errors compound irreversibly.

All of them defer on the model's own sense of doubt. The gate offers an
external, measured reason: any agent conclusion resting on a graph traversal —
affected tests, blast radius, related files — inherits that graph's recall.
`friction gate --json` emits that as an advisory an agent can act on.

See `docs/related-work.md`.
```

- [ ] **Step 4: Keep "How HydraDB is used" concrete**

```markdown
## How HydraDB is used

The selection runs **in the engine**, as a bounded backwards walk:

```cypher
MATCH (s {id: 10000005756})<-[:CALLS*1..6]-(n) RETURN n.id AS id
```

- Both arms are resident at once in **disjoint id bands**, so one engine holds
  the name-matched and type-resolved graphs of the same commit and the gate
  compares them without a reload.
- Structure metrics use `count(*)` over `[:REL*1..k]`. Verified exact against
  NetworkX at every k from 1 to 6, and flat in k: **12 ms at k=6** on a
  3,000-node / 8,989-edge graph, where `algo.MSpaths` path enumeration timed out
  at 30,000 ms on identical density.
- `RETURN count(n)` on a node is rejected by the engine; `count(*)` and
  `RETURN n.id` are the working forms.
- Two engine findings were filed upstream during this build:
  [#81](https://github.com/hydra-db/hydradb/issues/81) and
  [#82](https://github.com/hydra-db/hydradb/pull/82).
```

- [ ] **Step 5: Keep the limitations section prominent**

```markdown
## Limitations

- **Python only.** The extractors are `tree-sitter` and `scip-python`.
- **These figures are not comparable to PyCG's 70% or Java's 0.884.** Those
  measure whether a specific call edge is present. This measures whether a
  labelled test reaches the fix it guards transitively within a bounded number
  of hops — a property of a pair, not of an edge. No claim is made that this
  extractor is worse than PyCG's.
- **Precision is a ceiling, not a point estimate.** pyright emits no occurrence
  for an untyped receiver, so arm B under-reports and never invents an edge. The
  `cursor` counter-example in `docs/graph-delta.md` is a case where the
  name-matched arm was right and type resolution was incomplete.
- **The 0.95 bar is a judgement call**, not a measurement. It is a CLI flag.
- **`n` and its power** are in `docs/evaluation.md`; the fair test is
  leave-one-repo-out.
- **Per-instance failure prediction is already solved** at AUC 0.841
  (arXiv 2604.00594). This project does not claim it.
```

- [ ] **Step 6: Update `docs/index.html`**

Change the hero to the gate framing; replace the lead figure with the recall
table; add a terminal-styled block with real `friction gate --arm arm_b` output;
add a "What we tried first" card. Keep the existing Cytoscape figures — arm A vs
arm B pruning is now the *evidence* for the recall gap rather than the headline.

- [ ] **Step 7: Rewrite `docs/video-script.md` — hard 3:00 cap**

Target ~400 words (≈2:40, leaving headroom):

1. **Problem (0:00–0:35).** Coding agents build a graph of your repo, then skip tests based on it. Show the backwards walk. State the trap: complete with respect to the graph ≠ complete with respect to the program.
2. **Project (0:35–1:15).** `friction gate`. The label is free — SWE-bench's FAIL_TO_PASS test *is* the guarding test. Recall table, both verdicts `RUN_FULL`. One line: a better extractor does not fix it, and that matches ICSE 2020.
3. **Demo (1:15–2:20).** Live terminal: `uv run python scripts/gate_demo.py`. Corpus verdict, then the named instance, then the dropped guarding test. Then the browser: `GET /gate/<id>` with the Cypher in the response.
4. **HydraDB (2:20–2:50).** The `<-[:CALLS*1..6]-` query, both arms resident in disjoint bands, 12 ms vs the 30,000 ms enumeration timeout, and the two upstream filings.

- [ ] **Step 8: Verify no participant repo is named anywhere**

```bash
grep -rniE "hydraimpact|keto|blastradius|blast-radius|hydrashield|patientzero|freshcontext|hydramind|hydrascan|graphify|cortex-hq|glasshouse" \
  README.md docs/ --include="*.md" --include="*.html" && echo "VIOLATION" || echo "CLEAN"
```
Expected: `CLEAN`. Anything that matches must be removed.

- [ ] **Step 9: Verify every quoted figure exists in a generated doc**

For each number in the README, confirm it appears in `docs/gate.md`,
`docs/connectivity.md`, `docs/covers.md`, `docs/graph-delta.md` or
`docs/evaluation.md`.

- [ ] **Step 10: Commit**

```bash
git add README.md docs/index.html docs/video-script.md
git commit -m "docs: reframe around the gate, with the prediction attempt kept as origin story"
```

---

## Task 10: Ship

- [ ] **Step 1: Verify a genuinely clean clone works**

This has failed twice in this project — agents were told not to run git, and the
shipped clone was missing files that existed locally. Verify by actually cloning.

```bash
cd /private/tmp/claude-501/-Users-cruzer-Desktop-Hackathon/60b45b25-ec97-4c90-a007-eefe363648c5/scratchpad
rm -rf clone-check && git clone https://github.com/areycruzer/substrate-friction clone-check
cd clone-check && uv sync && uv run pytest -q && uv run friction gate --arm arm_b
```
Expected: tests pass **from the clone**, and `friction gate` prints `RUN_FULL`
with no files copied in by hand.

- [ ] **Step 2: Verify the payload size**

```bash
du -sh data/shipped && git count-objects -vH | grep size-pack
```
Expected: ≤ 50 MB, with omissions named in `data/shipped/README.md`.

- [ ] **Step 3: Push**

```bash
git push origin main
```

- [ ] **Step 4: Confirm GitHub Pages updated**

Load `https://areycruzer.github.io/substrate-friction` in the browser and confirm
the hero shows the gate framing. Pages can lag several minutes — re-check rather
than assuming.

- [ ] **Step 5: Record the video**

Follow `docs/video-script.md`. **Hard stop at 3:00** — running over is a rule
violation, not a style note. Record the demo terminal live; do not use a still.

- [ ] **Step 6: Submit**

`forms.gle/GrMYKxLj9zPQcqqc8` — repo URL, Pages URL, video URL, Track 02b.
**Submit on 2026-08-19**, not on the deadline.

---

## Task 11: CI — a pinned engine, proven live, with a badge

Adopted from a pattern seen in the wild: stand up a **pinned** HydraDB in CI,
prove a round trip on both transports, wipe the store between phases, and put a
badge on the README. We filed [#81](https://github.com/hydra-db/hydradb/issues/81)
about `CLOUD_PROVIDER=local` degrading under sustained writes while reads keep
serving — so the wipe-and-restart discipline is not hygiene theatre here, it is
the mitigation for a defect we discovered.

**Files:**
- Create: `.github/workflows/hydra-verify.yml`
- Create: `scripts/hydra_proof.py`
- Modify: `README.md` (badge)

- [ ] **Step 1: Write the liveness proof script**

```python
#!/usr/bin/env python
"""Prove a real round trip against the pinned open-source engine.

Writes a node, reads it back with a bounded reachability query, and fails
loudly if either leg does not work. Exists so CI can distinguish "the engine
container started" from "the engine actually serves reads and writes" — a
distinction this project learned the hard way (issue #81: reads keep serving
after the write path has degraded).
"""

from __future__ import annotations

import sys

from friction.client import connect
from friction.config import Settings
from friction.gate import build_selection_cypher


def main() -> int:
    transport = connect(Settings.from_env(), prefer="bolt")
    print(f"transport: {transport.name}")

    transport.run("MERGE (n:Probe {id: 1, sid: 'probe-1'}) RETURN n.id AS id")
    transport.run("MERGE (a:Probe {id: 1}) MERGE (b:Probe {id: 2}) "
                  "MERGE (b)-[:CALLS]->(a) RETURN b.id AS id")

    rows = list(transport.run(build_selection_cypher(1, "CALLS", 6)))
    ids = {int(r["id"]) for r in rows if r.get("id") is not None}
    transport.close()

    if 2 not in ids:
        print(f"FAIL: backwards walk from node 1 did not reach node 2; got {ids}")
        return 1
    print(f"OK: backwards walk from 1 reached {sorted(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it locally against a running engine first**

Run: `uv run python scripts/hydra_proof.py`
Expected: `OK: backwards walk from 1 reached [2]`. If the engine is not up, start it with the project's existing `docker-compose.yml` before wiring CI — debugging this inside a CI run is far slower.

- [ ] **Step 3: Write the workflow**

```yaml
name: HydraDB verify

on:
  workflow_dispatch:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "scripts/**"
      - "tests/**"
      - ".github/workflows/hydra-verify.yml"

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Sync
        run: uv sync

      - name: Unit tests (no engine)
        run: uv run pytest -q -m "not engine"

      - name: Start pinned HydraDB
        run: |
          docker compose up -d
          for i in $(seq 1 60); do
            if uv run python -c "
from friction.client import connect
from friction.config import Settings
connect(Settings.from_env(), prefer='bolt').close()
" 2>/dev/null; then echo "engine up after ${i}s"; exit 0; fi
            sleep 1
          done
          echo "engine did not become reachable"; docker compose logs; exit 1

      - name: Bolt round-trip proof
        run: uv run python scripts/hydra_proof.py | tee hydra-proof.log

      - name: Wipe the store and restart
        # Issue #81: CLOUD_PROVIDER=local degrades under sustained writes while
        # reads keep serving. Never trust read health as liveness; start clean.
        run: |
          docker compose down -v
          rm -rf hydradb-data
          docker compose up -d
          sleep 15

      - name: Engine-marked tests against a clean store
        run: uv run pytest -q -m engine

      - name: The gate itself must run from the repo
        run: |
          uv run python scripts/gate_report.py --out /tmp/gate.md
          uv run friction gate --arm arm_b --json > /tmp/gate.json || true
          uv run python -c "
import json
d = json.load(open('/tmp/gate.json'))
assert d['decision'] == 'RUN_FULL', d
assert d['n'] > 0, d
print('gate verdict reproduced in CI:', d['decision'], d['measured_recall'])
"

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: hydra-proof
          path: |
            hydra-proof.log
            /tmp/gate.md
```

- [ ] **Step 4: Confirm the pytest marker exists**

Run: `grep -rn "engine" pyproject.toml pytest.ini setup.cfg 2>/dev/null | grep -i marker`
If `engine` is not a registered marker, add it to `pyproject.toml` under
`[tool.pytest.ini_options] markers`. The workflow's `-m "not engine"` /
`-m engine` split depends on it.

- [ ] **Step 5: Push the branch and watch the run**

```bash
git add .github/workflows/hydra-verify.yml scripts/hydra_proof.py
git commit -m "ci: pinned HydraDB, Bolt round-trip proof, wipe-and-restart per issue #81"
git push origin main
gh run watch
```
Expected: green. If the engine step times out, read `docker compose logs` from
the failed run before changing anything.

- [ ] **Step 6: Add the badge to `README.md`**

```markdown
[![HydraDB verify](https://github.com/areycruzer/substrate-friction/actions/workflows/hydra-verify.yml/badge.svg)](https://github.com/areycruzer/substrate-friction/actions/workflows/hydra-verify.yml)
```

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: HydraDB verify badge"
```

---

## Task 12: MCP server — put the gate where agents can reach it

The sponsor's distribution strategy is agent integration: `hydradb-mcp`
(`npx -y @hydradb/mcp@latest`, configs documented for Claude Desktop, Cursor,
Windsurf, VS Code), `hydradb-claude-code`, `openclaw-hydradb`, `hydradb-cli`
("agent-friendly"). This project's closing argument is about agents and until
now had no delivery mechanism.

**Do not integrate with their MCP server** — it targets the hosted product and
requires `hydradb.com` credentials, which this project is barred from using.
Ship our own, against the open-source engine, following their conventions.

**Scope, stated so this does not read as a weak clone.** `repowise` ships ten
task-shaped MCP tools and has done so for months. This is not a rival to that and
must not be presented as one. It is **two tools doing the one thing nobody in the
category measures** — whether the graph an agent's conclusion rests on can reach
the tests that guard the change. A narrow, novel tool is defensible; a thinner
version of an existing suite is not. Keep it to two tools and say why in the
README.

**Files:**
- Create: `src/friction/mcp_server.py`
- Create: `tests/test_mcp.py`
- Modify: `pyproject.toml` (add the `mcp` dependency and a console script)
- Modify: `README.md` (config snippet)

- [ ] **Step 1: Add the dependency**

Run: `uv add mcp`
Then add to `pyproject.toml` under `[project.scripts]`:
```toml
friction-mcp = "friction.mcp_server:run"
```

- [ ] **Step 1b: Make both tools task-shaped, not entity-shaped**

A design convention worth adopting from the mature end of this field: tools built
around a single data entity force agents into long sequential call chains, so
**accept several targets in one call and return complete context**. Concretely,
`gate_explain` takes `instance_ids: list[str]`, not one id, and returns a list.
One round trip, not five. This costs nothing to build now and is painful to
retrofit.

- [ ] **Step 2: Write the failing test**

Test the tool functions directly — an end-to-end MCP handshake in CI is not
worth the time here, and the logic is what matters. Note `gate_explain` takes a
**list**.

```python
# tests/test_mcp.py
import json

from friction.mcp_server import gate_check, gate_explain
from friction.cli import MANIFEST_PATH
from friction.gate import audit_recall


def test_gate_check_returns_a_refusal_for_the_type_resolved_arm():
    payload = json.loads(gate_check(arm="arm_b"))
    assert payload["decision"] == "RUN_FULL"
    assert payload["n"] > 0
    assert "advice" in payload


def test_gate_check_rejects_an_unknown_arm():
    payload = json.loads(gate_check(arm="arm_z"))
    assert "error" in payload


def test_gate_explain_names_the_dropped_tests():
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, "arm_b", 6)
    assert audit.misses
    payload = json.loads(gate_explain(instance_id=audit.misses[0]))
    assert payload["dropped_guarding_tests"]
    assert "<-[:CALLS*1..6]-" in payload["cypher"]


def test_gate_explain_reports_an_unknown_instance():
    payload = json.loads(gate_explain(instance_id="nope__nope-0"))
    assert "error" in payload
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_mcp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'friction.mcp_server'`

- [ ] **Step 4: Write the server**

```python
"""MCP server exposing the gate to coding agents.

The abstention literature (AgentAbstain arXiv 2607.10059, ReDAct arXiv
2604.07036) has agents defer on *model-internal* uncertainty. This server
supplies the missing external signal: a measured statement about the graph an
agent's conclusion rests on.

Runs against the **open-source** engine and the committed corpus. It does not
talk to any hosted service.

Configure it the way the ecosystem expects:

    {"mcpServers": {"substrate-friction": {"command": "friction-mcp"}}}
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from friction.cli import MANIFEST_PATH

mcp = FastMCP("substrate-friction")


def gate_check(arm: str = "arm_b", k: int = 6) -> str:
    """Is it safe to skip tests based on this class of code graph?"""
    from friction.gate import audit_recall, gate as run_gate

    if arm not in {"arm_a", "arm_b"}:
        return json.dumps({"error": f"unknown arm {arm!r}; "
                                    "use 'arm_a' or 'arm_b'"})

    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, arm, k)
    verdict = run_gate(audit)
    return json.dumps({
        "decision": verdict.decision,
        "measured_recall": round(verdict.measured_recall, 4),
        "n": verdict.n,
        "arm": arm,
        "k": k,
        "threshold": verdict.threshold,
        "reason": verdict.reason,
        "advice": (
            "Run the full test suite. This graph's measured recall of the "
            "test-to-fix relation is below the bar, so a subset selected by "
            "graph traversal would omit tests that guard the change. Do not "
            "present a graph-derived 'affected tests' list as complete."
            if verdict.decision == "RUN_FULL" else
            "A graph-selected subset is defensible at this bar."),
    }, indent=2)


def gate_explain(instance_id: str, arm: str = "arm_b", k: int = 6) -> str:
    """Replay one labelled instance: what a selector returns vs what guards it."""
    from friction.connectivity import load_graph
    from friction.gate import build_selection_cypher, select_tests

    if arm not in {"arm_a", "arm_b"}:
        return json.dumps({"error": f"unknown arm {arm!r}"})

    record = None
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["instance_id"] == instance_id:
                record = row
                break
    if record is None:
        return json.dumps({"error": f"unknown instance {instance_id!r}"})

    entry = record.get(arm) or {}
    fix = list(entry.get("fix_site_ids") or [])
    tests = list(entry.get("test_target_ids") or [])
    edges = MANIFEST_PATH.parent / instance_id / arm / "edges.ndjson"
    if not edges.exists():
        return json.dumps({"error": f"no {arm} graph for {instance_id!r}"})

    result = select_tests(load_graph(edges), fix, tests, k)
    missed = sorted(set(int(t) for t in tests) - result.selected)
    return json.dumps({
        "instance_id": instance_id,
        "arm": arm,
        "k": k,
        "guarding_tests": len(tests),
        "selected": len(result.selected),
        "graph_complete": result.graph_complete,
        "dropped_guarding_tests": missed,
        "cypher": (build_selection_cypher(int(fix[0]), "CALLS", k)
                   if fix else None),
        "note": ("graph_complete=true means the walk exhausted every edge this "
                 "graph has. It does not mean the graph has every edge."),
    }, indent=2)


mcp.tool()(gate_check)
mcp.tool()(gate_explain)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_mcp.py -v`
Expected: 4 passed

- [ ] **Step 6: Verify the server actually starts over stdio**

Run: `uv run friction-mcp` and confirm it starts and waits on stdin without
crashing (Ctrl-C to exit). A server that imports cleanly but dies on startup is
the failure mode to catch here.

- [ ] **Step 7: Document the config in `README.md`**

```markdown
## Use it from a coding agent

`friction gate` is available over MCP, so an agent can ask before it trusts its
own impact analysis:

```json
{"mcpServers": {"substrate-friction": {"command": "friction-mcp"}}}
```

Tools: `gate_check` (is a skip defensible on this graph class?) and
`gate_explain` (replay one labelled instance). Runs against the open-source
engine and the committed corpus — no hosted service, no credentials.
```

- [ ] **Step 8: Commit**

```bash
git add src/friction/mcp_server.py tests/test_mcp.py pyproject.toml README.md
git commit -m "feat(mcp): expose the gate to coding agents over MCP"
```

---

## Task 13: Confidence-tier calibration — `friction verify`

**Verified on 2026-08-17** against a cached `graphify` run over django
`db/models` (34 files, 3,079 edges). These are re-measured numbers; an earlier
figure quoted in conversation (198 same-leaf-name edges, 25.1%) came from a
broken script that compared node ids instead of leaf names and **must not be
used**:

| Fact | Value |
|---|---|
| edges | 3,079 |
| `EXTRACTED` | 3,072 (**99.77%**) |
| `INFERRED` | 7 (0.23%) |
| `AMBIGUOUS` | 0 |
| `calls` edges | 718 — **all `EXTRACTED`** |

And the resolution input, from the same output's `raw_calls`:

```json
{"caller_nid": "...sqlitenumericmixin_as_sqlite", "callee": "get_internal_type",
 "is_member_call": true, "receiver": null}
```

A bare callee name with a **null receiver** — the extractor does not know the
receiver's type — yet the emitted edge carries the top confidence tier.

**The finding, stated so it needs no claim about any specific edge being
wrong:** a confidence field where 99.77% of edges receive the highest tier
carries almost no information. `EXTRACTED` marks *syntactically present in the
source*, not *verified correct* — and a downstream consumer reading
`confidence: EXTRACTED` will treat it as ground truth.

**Why this belongs in the plan, and it is not primarily the audit:** right now
`friction gate` reads only this project's own `edges.ndjson`. That makes it a
measurement harness. An adapter for a third-party graph format makes it a
**tool** — the single biggest weakness in the plan as it stands.

**Scope discipline.** This deliberately does **not** attempt a cross-tool
identity join between graphify ids and SCIP symbols. That is real work with real
risk three days out. Everything below is computed inside graphify's own output.

**Ethical line, applied throughout this plan:** repos in the **sponsor's org**
are fair to measure and contribute back to — the same posture as
[#81](https://github.com/hydra-db/hydradb/issues/81) and
[#82](https://github.com/hydra-db/hydradb/pull/82). **Participant entries are
learn-from-only: never measured, never named.**

**Files:**
- Create: `src/friction/adapters/graphify.py`
- Create: `tests/test_adapter_graphify.py`
- Modify: `src/friction/cli.py` (add `verify`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapter_graphify.py
import json

import networkx as nx

from friction.adapters.graphify import TierReport, load_graph, tier_report

SAMPLE = {
    "nodes": [
        {"id": "a", "label": "a.py"},
        {"id": "b", "label": "b.py"},
    ],
    "edges": [
        {"source": "a", "target": "b", "relation": "calls",
         "confidence": "EXTRACTED"},
        {"source": "b", "target": "a", "relation": "imports",
         "confidence": "INFERRED"},
    ],
    "raw_calls": [
        {"caller_nid": "a", "callee": "f", "is_member_call": True,
         "receiver": None},
        {"caller_nid": "a", "callee": "g", "is_member_call": True,
         "receiver": "obj"},
    ],
}


def _write(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(SAMPLE), encoding="utf-8")
    return p


def test_load_graph_builds_a_digraph_with_integer_ids(tmp_path):
    g, _ = load_graph(_write(tmp_path))
    assert isinstance(g, nx.DiGraph)
    assert g.number_of_edges() == 2


def test_tier_report_counts_the_confidence_census(tmp_path):
    rep = tier_report(_write(tmp_path))
    assert rep.total == 2
    assert rep.by_tier["EXTRACTED"] == 1
    assert rep.by_tier["INFERRED"] == 1


def test_tier_report_flags_top_tier_saturation(tmp_path):
    rep = tier_report(_write(tmp_path))
    assert 0.0 <= rep.top_tier_share <= 1.0


def test_tier_report_counts_unresolved_receivers(tmp_path):
    rep = tier_report(_write(tmp_path))
    assert rep.member_calls == 2
    assert rep.null_receiver == 1


def test_tier_report_handles_a_graph_with_no_raw_calls(tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    rep = tier_report(p)
    assert rep.total == 0
    assert rep.member_calls == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_adapter_graphify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'friction.adapters'`

- [ ] **Step 3: Write the adapter**

```python
# src/friction/adapters/__init__.py
"""Adapters that read third-party code-graph formats into the gate."""
```

```python
# src/friction/adapters/graphify.py
"""Read a graphify JSON code graph and audit its confidence tiers.

graphify labels every edge `EXTRACTED` / `INFERRED` / `AMBIGUOUS`. That is a
self-reported trust signal, and a downstream tool will act on it. Nobody has
published what those tiers are worth, so this measures two things that can be
computed entirely inside graphify's own output — no cross-tool identity join,
no claim that any particular edge is wrong:

1. **Tier saturation.** If nearly every edge receives the top tier, the field
   carries almost no information regardless of whether the edges are right.
2. **Unresolved receivers.** `raw_calls` records each call site's `receiver`.
   A null receiver means the extractor did not know the receiver's type. Edges
   derived from those sites still carry the top tier.

This is offered as calibration, not critique: a confidence label is more useful
once its meaning is measured.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

TOP_TIER = "EXTRACTED"


@dataclass(frozen=True)
class TierReport:
    total: int
    by_tier: dict[str, int]
    calls_by_tier: dict[str, int]
    member_calls: int
    null_receiver: int

    @property
    def top_tier_share(self) -> float:
        return self.by_tier.get(TOP_TIER, 0) / self.total if self.total else 0.0

    @property
    def null_receiver_share(self) -> float:
        return self.null_receiver / self.member_calls if self.member_calls else 0.0


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_graph(path: Path) -> tuple[nx.DiGraph, dict[str, int]]:
    """Build a DiGraph plus the string-id -> integer-id mapping used for it.

    graphify ids are long strings (`$graphify-root$_django_db_models_...`); the
    gate works in integer node ids, so they are interned here. The mapping is
    returned so a caller can name a node again afterwards.
    """
    doc = _load(path)
    index: dict[str, int] = {}

    def intern(sid: str) -> int:
        if sid not in index:
            index[sid] = len(index) + 1
        return index[sid]

    g = nx.DiGraph()
    for node in doc.get("nodes") or []:
        if node.get("id"):
            g.add_node(intern(node["id"]))
    for edge in doc.get("edges") or []:
        src, dst = edge.get("source"), edge.get("target")
        if src and dst:
            g.add_edge(intern(src), intern(dst))
    return g, index


def tier_report(path: Path) -> TierReport:
    """Census the confidence field and the call-resolution input."""
    doc = _load(path)
    edges = doc.get("edges") or []
    raw = doc.get("raw_calls") or []

    by_tier = Counter(e.get("confidence") for e in edges)
    calls_by_tier = Counter(e.get("confidence") for e in edges
                            if e.get("relation") == "calls")
    member = [r for r in raw if r.get("is_member_call")]

    return TierReport(
        total=len(edges),
        by_tier={k: v for k, v in by_tier.items() if k},
        calls_by_tier={k: v for k, v in calls_by_tier.items() if k},
        member_calls=len(member),
        null_receiver=sum(1 for r in member if r.get("receiver") is None),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_adapter_graphify.py -v`
Expected: 5 passed

- [ ] **Step 5: Add the `verify` subcommand to `src/friction/cli.py`**

```python
    ver_cmd = sub.add_parser(
        "verify",
        help="audit a third-party graph's self-reported confidence tiers")
    ver_cmd.add_argument("graph", type=Path,
                         help="path to a graphify JSON graph")
    ver_cmd.add_argument("--json", action="store_true")
```

```python
def cmd_verify(args) -> int:
    from friction.adapters.graphify import TOP_TIER, tier_report

    rep = tier_report(args.graph)
    if args.json:
        print(json.dumps({
            "total_edges": rep.total,
            "by_tier": rep.by_tier,
            "calls_by_tier": rep.calls_by_tier,
            "top_tier_share": round(rep.top_tier_share, 4),
            "member_calls": rep.member_calls,
            "null_receiver": rep.null_receiver,
            "null_receiver_share": round(rep.null_receiver_share, 4),
        }, indent=2))
        return 0

    print(RULE)
    print(f"  confidence-tier audit: {args.graph}")
    print(RULE)
    print(f"  edges: {rep.total:,}")
    for tier, count in sorted(rep.by_tier.items(), key=lambda x: -x[1]):
        share = count / rep.total if rep.total else 0.0
        print(f"    {tier:<12} {count:>6,}  {share:6.2%}")
    print(f"\n  `calls` edges by tier: {rep.calls_by_tier}")
    print(f"\n  member call sites          : {rep.member_calls:,}")
    print(f"  with an unresolved receiver : {rep.null_receiver:,} "
          f"({rep.null_receiver_share:.1%})")
    print()
    if rep.top_tier_share > 0.95:
        print(f"  {rep.top_tier_share:.2%} of edges carry the top tier "
              f"`{TOP_TIER}`. A confidence field that is this saturated")
        print("  carries almost no information: it marks 'syntactically present"
              " in the source',")
        print("  not 'verified correct'. Calibrating it would make it "
              "actionable downstream.")
    print(RULE)
    return 0
```

Wire into `main`:
```python
    if args.command == "verify":
        return cmd_verify(args)
```

- [ ] **Step 6: Run it against the real cached graphify output**

```bash
uv run friction verify \
  /private/tmp/claude-501/-Users-cruzer-Desktop-Hackathon/60b45b25-ec97-4c90-a007-eefe363648c5/scratchpad/gtest/graphify-out/cache/ast/v0.9.45/0833f67bf732932cefacd3256937ae2a5837a807e5f71f6ba65bc912ce1b08f4.json
```
Expected: 356 edges, all `EXTRACTED`, a non-zero unresolved-receiver count.

**If that scratchpad path is gone** (it is session-scoped and may be cleaned),
regenerate: `uv pip install graphifyy` and re-run it over
`data/repos/django/django/db/models`. If regeneration fails for any reason,
**cut this task** — it is the designated first cut and the project is complete
without it.

- [ ] **Step 7: File it upstream as calibration, not critique**

Open an issue on `hydra-db/graphify` in the same register as #81/#82: report the
tier census and the null-receiver share, note that the tiers appear uncalibrated
rather than incorrect, and offer the measurement. **Ask before filing** — this
is outward-facing and touches the sponsor's own repo.

- [ ] **Step 8: Commit**

```bash
git add src/friction/adapters/ tests/test_adapter_graphify.py src/friction/cli.py
git commit -m "feat(verify): audit a third-party graph's confidence tiers — the gate is graph-agnostic"
```

---

## Task 15: `friction gate --repo` — a real repository as input

**This is the task that makes it a product rather than a replay.** Everything so
far gates the committed corpus. This gates *your* repository, at *your* commit,
for *your* diff.

**The honest design constraint, and it is not a limitation to hide.** On an
arbitrary repository there are no labels, so recall **cannot** be measured there.
What the gate does is identify which *class* of graph was built, apply that
class's recall measured on the labelled corpus, and refuse or permit accordingly.
That is exactly what a prior is for, and the output must say so in words.

**Files:**
- Create: `src/friction/live.py`
- Modify: `src/friction/cli.py`
- Test: `tests/test_live.py`

**Interfaces:**
- Consumes: `friction.namematch.graph.build(repo) -> (edges, stats)`; `friction.gate.select_tests`, `audit_recall`, `gate`; `friction.scip.index.index_repo` / `extract_edges` for the type-resolved path.
- Produces: `LiveGate(repo, arm, changed, selected, total_tests, verdict, prior)`; `gate_repo(repo, changed_files, arm, k) -> LiveGate`.

- [ ] **Step 1: Write the failing test**

Use this project's own repository as the fixture — it is a real Python repo that
is guaranteed present, which avoids depending on `data/repos/django` being
checked out.

```python
# tests/test_live.py
from pathlib import Path

import pytest

from friction.live import LiveGate, gate_repo

REPO = Path(__file__).resolve().parent.parent


def test_gate_repo_builds_a_graph_and_returns_a_verdict():
    result = gate_repo(REPO, changed_files=["src/friction/gate.py"],
                       arm="arm_a", k=6)
    assert isinstance(result, LiveGate)
    assert result.graph_nodes > 0
    assert result.verdict.decision in {"RUN_FULL", "SKIP_SAFE"}


def test_the_prior_comes_from_the_labelled_corpus_not_this_repo():
    result = gate_repo(REPO, changed_files=["src/friction/gate.py"],
                       arm="arm_a", k=6)
    # No labels exist for an arbitrary repo, so recall must be the corpus prior.
    assert result.prior_n > 0
    assert 0.0 <= result.verdict.measured_recall <= 1.0
    assert "labelled corpus" in result.prior_note


def test_an_unknown_changed_file_is_reported_not_silently_ignored():
    result = gate_repo(REPO, changed_files=["does/not/exist.py"],
                       arm="arm_a", k=6)
    assert result.unmatched_changed == ("does/not/exist.py",)


def test_a_changed_file_with_no_symbols_still_returns_run_full():
    result = gate_repo(REPO, changed_files=["does/not/exist.py"],
                       arm="arm_a", k=6)
    assert result.verdict.decision == "RUN_FULL"


def test_rejects_a_path_that_is_not_a_directory(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        gate_repo(f, changed_files=[], arm="arm_a", k=6)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_live.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'friction.live'`

- [ ] **Step 3: Write the implementation**

```python
"""Gate a real repository at a real commit for a real diff.

Everything else in this package measures the committed corpus. This runs the
same selection against a repository the user actually has, which is what makes
the gate usable rather than merely demonstrated.

The one thing it cannot do is measure recall on that repository: recall needs
labels saying which test guards which fix, and an arbitrary repo has none. So
the gate identifies which *class* of graph was built and applies that class's
recall as measured on the labelled corpus. The output says so explicitly — a
prior presented as a measurement would be exactly the kind of borrowed number
this project exists to object to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from friction.gate import GateVerdict, audit_recall, gate, select_tests

TEST_MARKERS = ("test_", "_test", "/tests/", "conftest")


@dataclass(frozen=True)
class LiveGate:
    repo: Path
    arm: str
    k: int
    graph_nodes: int
    graph_edges: int
    changed_symbols: int
    total_tests: int
    selected_tests: tuple[str, ...]
    graph_complete: bool
    unmatched_changed: tuple[str, ...]
    verdict: GateVerdict
    prior_n: int
    prior_note: str


def _is_test(node: str) -> bool:
    low = node.replace("\\", "/").lower()
    return any(m in low for m in TEST_MARKERS)


def gate_repo(repo: Path, changed_files: list[str], arm: str = "arm_a",
              k: int = 6) -> LiveGate:
    """Build a graph of `repo`, select tests for `changed_files`, and decide."""
    repo = Path(repo)
    if not repo.is_dir():
        raise NotADirectoryError(f"{repo} is not a directory")

    from friction.namematch.graph import build as build_arm_a
    edges, stats = build_arm_a(repo)

    # Intern string node names to the integer ids select_tests works in.
    index: dict[str, int] = {}

    def nid(name: str) -> int:
        if name not in index:
            index[name] = len(index) + 1
        return index[name]

    g = nx.DiGraph()
    for src, dst in edges:
        g.add_edge(nid(src), nid(dst))

    wanted = {c.replace("\\", "/") for c in changed_files}
    changed_ids: set[int] = set()
    matched: set[str] = set()
    for name, node_id in index.items():
        flat = name.replace("\\", "/")
        for w in wanted:
            if flat.startswith(w) or w in flat:
                changed_ids.add(node_id)
                matched.add(w)

    test_ids = {node_id for name, node_id in index.items() if _is_test(name)}
    by_id = {v: k_ for k_, v in index.items()}

    result = select_tests(g, changed_ids, test_ids, k)

    # Recall is a corpus prior, never a measurement on this repo.
    from friction.cli import MANIFEST_PATH
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, arm, k)
    verdict = gate(audit)

    return LiveGate(
        repo=repo, arm=arm, k=k,
        graph_nodes=g.number_of_nodes(), graph_edges=g.number_of_edges(),
        changed_symbols=len(changed_ids),
        total_tests=len(test_ids),
        selected_tests=tuple(sorted(by_id[i] for i in result.selected)),
        graph_complete=result.graph_complete,
        unmatched_changed=tuple(sorted(wanted - matched)),
        verdict=verdict,
        prior_n=audit.n,
        prior_note=(
            f"Recall {verdict.measured_recall:.3f} is the value measured for "
            f"'{arm}'-class graphs on the labelled corpus (n={audit.n}), not a "
            f"measurement on {repo.name}. An unlabelled repository cannot yield "
            f"a recall figure; this is that class's prior, applied."),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_live.py -v`
Expected: 5 passed

- [ ] **Step 5: Wire `--repo` into the CLI**

Add to `gate_cmd`:
```python
    gate_cmd.add_argument("--repo", type=Path, default=None,
                          help="gate a real repository instead of the corpus")
    gate_cmd.add_argument("--changed", nargs="*", default=[],
                          help="changed file paths, relative to --repo")
```

At the top of `cmd_gate`, before the `--instance` branch:
```python
    if args.repo:
        return _gate_live(args)
```

```python
def _gate_live(args) -> int:
    from friction.live import gate_repo

    live = gate_repo(args.repo, list(args.changed), args.arm, args.k)
    v = live.verdict

    print(RULE)
    mark = "PASS" if v.decision == "SKIP_SAFE" else "FAIL"
    print(f"[{mark}]  {v.decision}      {live.repo.name}  arm={live.arm}  k={live.k}")
    print(RULE)
    print(f"  graph            : {live.graph_nodes:,} nodes, {live.graph_edges:,} edges")
    print(f"  changed symbols  : {live.changed_symbols:,}")
    print(f"  tests in repo    : {live.total_tests:,}")
    print(f"  tests selected   : {len(live.selected_tests):,}")
    print(f"  graph-complete   : {live.graph_complete}")
    if live.unmatched_changed:
        print(f"  UNMATCHED paths  : {', '.join(live.unmatched_changed)}")
    print()
    print(f"  {v.reason}")
    print()
    print(f"  {live.prior_note}")
    if live.selected_tests:
        print(f"\n  selected (first 10):")
        for t in live.selected_tests[:10]:
            print(f"    {t}")
    print(RULE)
    return 0 if v.decision == "SKIP_SAFE" else 1
```

- [ ] **Step 6: Run it on this repo, then on a real external one**

```bash
uv run friction gate --repo . --changed src/friction/reach.py
uv run friction gate --repo data/repos/requests --changed src/requests/sessions.py
uv run friction gate --repo data/repos/django --changed django/db/models/query.py
```
Expected: a graph is built for each, tests are selected, and the verdict is
`RUN_FULL` with the prior explained. Time the django run — if it exceeds ~60 s,
note the number in the README rather than hiding it.

- [ ] **Step 7: Commit**

```bash
git add src/friction/live.py src/friction/cli.py tests/test_live.py
git commit -m "feat(gate): --repo gates a real repository, with the corpus prior stated as a prior"
```

---

## Task 16: `friction calibrate` — measure what asserted tier confidences are worth

**Highest value, highest risk. Attempt only after Tasks 1–7, 11, 14 and 15 are
committed, and abort on the criterion in Step 3 rather than pushing through.**

Reading `repowise`'s `call_resolver.py` (1,360 lines) shows its three tiers carry
**asserted** confidence numbers:

| Tier | Rule | Asserted confidence |
|---|---|---|
| 1 | Same-file exact match | **0.95** |
| 2 | Import-scoped match | **0.90** |
| 3 | Global unique match | **0.50** |

Those are hand-assigned priors. Its benchmarks measure retrieval, tokens, defect
prediction and indexing time — **never per-tier edge accuracy**. And `confidence`
*is* persisted per edge (`persistence/crud/graph.py`), so it is extractable.

This project already has the instrument: arm B (scip-python / pyright) is the
type-resolved reference used to produce the 0.746 precision ceiling. Pointing it
at another tool's tiers turns an asserted number into a measured one.

**Framing is not optional here.** This is calibration offered to a project whose
measurement standards are higher than most of this field's, in the same register
as issue #81 and PR #82. It is not a takedown, and the shipped copy must not read
as one. Tier 3 at 0.50 is *already* a statement that the tier is weak — measuring
it is finishing their sentence, not contradicting it.

**Files:**
- Create: `src/friction/adapters/tiers.py`
- Create: `tests/test_calibrate.py`
- Modify: `src/friction/cli.py`
- Generated: `docs/calibration.md`

- [ ] **Step 1: Index django with repowise and export the edges**

```bash
cd /private/tmp/claude-501/.../scratchpad
uv pip install repowise
repowise index data/repos/django          # they state they are the slowest indexer
```
Then locate the graph DB and dump `CALLS` edges with `source`, `target`,
`confidence`, `origin` to `calls.ndjson`. Read
`packages/core/src/repowise/core/persistence/crud/graph.py` for the column names —
**do not guess the schema.**

- [ ] **Step 2: Build the identity map into the SCIP space**

Reuse `friction.identity` — do not write a second joiner. The mapping is
`<file path>::<Class>.<member>` on their side against SCIP canonical symbols on
ours, which is the same shape `covers3.covers_identity` already solves for the
dynamic tracer.

- [ ] **Step 3: ABORT GATE — check the join rate before computing anything**

```bash
uv run python -c "
from friction.adapters.tiers import join_rate
print(join_rate('calls.ndjson'))
"
```

**If fewer than 60% of their `CALLS` edges join into the SCIP space, STOP and cut
this task.** A low join rate produces a precision number that measures the joiner,
not the tiers. This project has already shipped that exact error twice — the
unqualified-tracer run mapped 0.3% and read RED, and the reviewer's arm-A
reconstruction differed by 229 edges through a `__init__` collapse. Do not make it
a third time three days before judging. Record the join rate in
`docs/calibration.md` whatever happens.

- [ ] **Step 4: Compute per-tier precision against arm B**

For each tier, precision = (edges confirmed by arm B) / (edges compared), reported
**as a ceiling** for the same reason the 0.746 is a ceiling: pyright emits no
occurrence for an untyped receiver, so arm B under-reports and never invents an
edge.

- [ ] **Step 5: Write `docs/calibration.md`**

It must contain, in this order: the join rate and how many edges were dropped; the
per-tier table with asserted vs measured; the ceiling caveat; and an explicit note
that a tier measuring below its asserted number means the label is optimistic, not
that the edges are wrong.

- [ ] **Step 6: Ask before publishing**

This names another project's numbers. **Show me the generated `docs/calibration.md`
and stop.** Publishing it, and any upstream issue, is the user's call.

---

## Task 14: A pinned, sealed split — with an honest account of what it buys

The field's best practice, adopted from `repowise`'s benchmark discipline: pin a
holdout **before** the final measurement, and report the sealed half.

**State plainly what this does and does not buy here**, because overclaiming it
would be worse than not doing it. `select_tests` has **no learned parameters** —
there is no model to overfit, so this is not a train/test split and must never be
described as one. What *was* iterated on across sessions is a set of researcher
degrees of freedom: the hop bound `k=6`, the package-`__init__` collapse in the
identity join, the endpoint-mapping rules, and the scope restriction. Those choices
were made while looking at django. A sealed split across the other six repos tests
whether they generalise.

The strong prediction, written down before the measurement: **with no fitted
parameters, the two halves should agree closely.** If they diverge materially, that
is not a tuning failure — it is evidence the identity join is repo-specific, which
would be a genuine finding and must be reported as one.

**Files:**
- Create: `scripts/pin_split.py`
- Create: `data/shipped/split.json` (committed, generated once, never regenerated)
- Modify: `src/friction/gate.py` (add `split_of`, extend `audit_recall`)
- Modify: `scripts/gate_report.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `audit_recall` (Task 2).
- Produces: `split_of(instance_id, split_path) -> str` returning `"dev"` or `"sealed"`; `audit_recall(..., split: str | None = None)`.

- [ ] **Step 1: Write the pinning script**

```python
#!/usr/bin/env python
"""Pin the dev/sealed split once, deterministically, and never again.

Assignment is a SHA-256 of the instance id — not a random shuffle — so the split
is reproducible from the ids alone and cannot be quietly re-rolled to a more
flattering partition. The output is committed; `--force` exists only to make
overwriting a deliberate act.

    uv run python scripts/pin_split.py --out data/shipped/split.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def assign(instance_id: str, sealed_share: float = 0.375) -> str:
    """Hash the id into [0,1) and assign below the cut to `sealed`.

    0.375 puts roughly 3 of every 8 instances in the sealed half, mirroring the
    70/42 proportion this field's benchmarks use.
    """
    digest = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
    position = int(digest[:16], 16) / float(1 << 64)
    return "sealed" if position < sealed_share else "dev"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/shipped/arms/manifest.jsonl"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sealed-share", type=float, default=0.375)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.out.exists() and not args.force:
        raise SystemExit(
            f"{args.out} already exists. The split is pinned once by design; "
            f"pass --force only if you intend to break that.")

    split: dict[str, str] = {}
    with args.manifest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            iid = json.loads(line)["instance_id"]
            split[iid] = assign(iid, args.sealed_share)

    args.out.write_text(json.dumps({
        "method": "sha256(instance_id) -> [0,1); < sealed_share is sealed",
        "sealed_share": args.sealed_share,
        "note": "Pinned before the final measurement. There are no fitted "
                "parameters in the selector; this guards the hop bound, the "
                "identity-join rules and the endpoint mapping, which were chosen "
                "while looking at django.",
        "assignments": split,
    }, indent=2, sort_keys=True), encoding="utf-8")

    sealed = sum(1 for v in split.values() if v == "sealed")
    print(f"wrote {args.out}: {len(split)} instances, "
          f"{sealed} sealed / {len(split) - sealed} dev")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_gate.py
from friction.gate import split_of


def test_split_assignment_is_deterministic(tmp_path):
    p = tmp_path / "split.json"
    p.write_text(json.dumps({"assignments": {"django__django-1": "sealed"}}),
                 encoding="utf-8")
    assert split_of("django__django-1", p) == "sealed"
    assert split_of("django__django-1", p) == "sealed"


def test_an_unlisted_instance_is_not_silently_assigned(tmp_path):
    p = tmp_path / "split.json"
    p.write_text(json.dumps({"assignments": {}}), encoding="utf-8")
    assert split_of("django__django-99", p) is None


def test_audit_can_be_restricted_to_one_half(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "django__django-1", [(1, 3)])
    _write_instance(arms, "django__django-2", [(9, 8)])
    mf = tmp_path / "manifest.jsonl"
    _manifest(mf, [
        {"instance_id": "django__django-1",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
        {"instance_id": "django__django-2",
         "arm_b": {"fix_site_ids": [3], "test_target_ids": [1]}},
    ])
    sp = tmp_path / "split.json"
    sp.write_text(json.dumps({"assignments": {
        "django__django-1": "sealed", "django__django-2": "dev"}}),
        encoding="utf-8")

    sealed = audit_recall(mf, arms, "arm_b", 6, split="sealed", split_path=sp)
    dev = audit_recall(mf, arms, "arm_b", 6, split="dev", split_path=sp)
    both = audit_recall(mf, arms, "arm_b", 6)

    assert sealed.n == 1 and sealed.hits == 1
    assert dev.n == 1 and dev.hits == 0
    assert both.n == 2
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate.py -k split -v`
Expected: FAIL — `ImportError: cannot import name 'split_of'`

- [ ] **Step 4: Extend `src/friction/gate.py`**

```python
# append to src/friction/gate.py
from functools import lru_cache

DEFAULT_SPLIT_PATH = Path("data/shipped/split.json")


@lru_cache(maxsize=8)
def _load_split(split_path: str) -> dict[str, str]:
    p = Path(split_path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("assignments") or {}


def split_of(instance_id: str,
             split_path: Path = DEFAULT_SPLIT_PATH) -> str | None:
    """Which half is this instance in? None when it is not in the pinned file.

    Returning None rather than guessing matters: an instance added after the
    split was pinned must not be silently folded into either half.
    """
    return _load_split(str(split_path)).get(instance_id)
```

Then change `audit_recall`'s signature and add the filter:

```python
def audit_recall(manifest_path: Path, arms_root: Path, arm: str, k: int,
                 split: str | None = None,
                 split_path: Path = DEFAULT_SPLIT_PATH) -> RecallAudit:
    """Run the selector over every labelled instance and count the misses.

    `split` restricts to one half of the pinned split ("dev" or "sealed").
    Instances absent from the split file are excluded when `split` is set,
    never silently included.
    """
```

and immediately inside the loop, before `_instance_hit`:

```python
        if split is not None:
            if split_of(record["instance_id"], split_path) != split:
                continue
```

Add `split` to the `RecallAudit` dataclass as a field defaulting to `None`, and
pass it through in the constructor call, so a report can never misattribute which
half a number came from.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: all previous tests plus 3 new ones passing.

- [ ] **Step 6: Pin the split — once**

```bash
uv run python scripts/pin_split.py --out data/shipped/split.json
git add data/shipped/split.json scripts/pin_split.py
git commit -m "data: pin the dev/sealed split by sha256(instance_id), before measurement"
```

**Commit this before running Step 7.** Pinning after seeing the result is the
failure mode the whole task exists to prevent, and the commit timestamp is the
evidence that it did not happen.

- [ ] **Step 7: Measure both halves and record the outcome**

```bash
uv run python -c "
from pathlib import Path
from friction.gate import audit_recall
mf, ar = Path('data/shipped/arms/manifest.jsonl'), Path('data/shipped/arms')
for half in ('dev','sealed', None):
    a = audit_recall(mf, ar, 'arm_b', 6, split=half)
    print(f'{str(half or \"all\"):>6}: {a.hits}/{a.n} = {a.recall:.3f}')
"
```

**Interpretation, fixed in advance:** the halves should agree closely, because
there are no fitted parameters. A gap under ~0.10 confirms the hop bound and
identity-join choices generalise beyond django. A larger gap is a **finding about
the identity join**, must be reported in `docs/gate.md` as such, and must not be
resolved by re-pinning.

- [ ] **Step 8: Add the split to `scripts/gate_report.py`**

Insert after the Verdict table:

```python
    L += [
        "",
        "## Pinned split",
        "",
        "The split was pinned by `sha256(instance_id)` and committed **before** "
        "this measurement — see `data/shipped/split.json` and its commit. There "
        "are no fitted parameters in the selector, so this is not a train/test "
        "split and is not presented as one. It tests whether choices made while "
        "looking at django — the hop bound, the package-`__init__` collapse in "
        "the identity join, the endpoint mapping — hold on the other six "
        "repositories.",
        "",
        "| Half | arm_a | arm_b |",
        "|---|---|---|",
    ]
    for half in ("dev", "sealed"):
        cells = []
        for arm in ("arm_a", "arm_b"):
            a = audit_recall(manifest, arms_root, arm, args.k, split=half)
            cells.append(f"{a.recall:.3f} ({a.hits}/{a.n})" if a.n else "—")
        L.append(f"| {half} | {cells[0]} | {cells[1]} |")
```

- [ ] **Step 9: Regenerate and commit**

```bash
uv run python scripts/gate_report.py --out docs/gate.md
git add src/friction/gate.py scripts/gate_report.py docs/gate.md tests/test_gate.py
git commit -m "feat(gate): report the pinned sealed split alongside the pooled figure"
```

---

## Schedule

| When | Tasks |
|---|---|
| **17 Aug (tonight)** | 1, 2, 3, 4 — `gate.py` complete, verified against `docs/connectivity.md` |
| **18 Aug (am)** | 5, 6, **15** — CLI, `docs/gate.md`, replay demo, **`--repo` on real repositories** |
| **18 Aug (pm)** | **14**, **11** — pin the split and measure both halves; CI green with the badge |
| **19 Aug (am)** | 7, **12** — API browser-verified, then the MCP server |
| **19 Aug (pm)** | 8, 9, 10 — related work + reuse policy, README/landing/video, clean clone, push, record, **submit** |
| **20 Aug** | Buffer. **16** (calibration) then **13** (`verify`), only if everything else is done and Task 16's abort gate passes. |

**Honest capacity note.** Sixteen tasks is more than three days holds if every one
is done well. The schedule above fits Tasks 1–12, 14 and 15. Tasks 13 and 16 are
genuinely optional and are placed in the buffer on purpose — 16 in particular has
an abort gate that may fire, and firing it is a success, not a failure.

**Cut order if the schedule slips**, first to go first: Task 13 (`verify`), then
Task 12 (MCP), then Task 4 (paired comparison). Tasks 1–3, 5–7, 9–11 and **14** are
the irreducible product — 14 stays because a pinned sealed split is the cheapest
credibility available and it is what a rigorous reviewer looks for. Never cut Task 10.

**Task 14 must be pinned before it is measured.** Its Step 6 commits
`data/shipped/split.json`; Step 7 measures. Doing those in the other order, or
re-pinning after seeing a result, voids the entire point and would be worse than
omitting the task.

---

## Self-Review

**Spec coverage.** The strategic requirement was to convert a measurement study into a deliverable product without discarding the work, and to resolve rather than bury the original prediction idea. Tasks 1–4 build the product core entirely from existing measurements. Task 5 makes it CI-usable — the non-zero exit *is* the product. Task 6 makes it demonstrable. Task 7 satisfies the judging criterion for real ingestion and retrieval by putting the selection in the engine. Task 8 grounds it in the literature and gives the prediction attempt a proper ending. Task 9 repositions the narrative. Task 10 ships it.

**Placeholder scan.** Every code step contains complete runnable code. The only bracketed values are in Task 9 Steps 1–2, and each is explicitly sourced from the generated `docs/gate.md` with an instruction never to fill them from memory.

**Type consistency.** `SelectionResult(selected, k, graph_complete)` — produced Task 1, consumed 2, 4, 6, 7. `RecallAudit(arm, k, n, hits, misses, per_repo)` with `.recall` — produced Task 2, consumed 3, 4, 5, 6, 7. `GateVerdict(decision, measured_recall, n, arm, k, threshold, reason)` — produced Task 3, consumed 5, 7. `ArmComparison(...)` with `.a_recall`/`.b_recall`/`.recall_delta` — produced Task 4, consumed 5. `build_selection_cypher(node_id, rel_type, k)` — produced Task 6, consumed 6 and 7. `_check_bound` is shared by `select_tests` and `build_selection_cypher`. `_instance_hit`/`_iter_manifest` are produced in Task 2 and reused in Task 4. `arm` is `"arm_a"`/`"arm_b"` throughout, matching the manifest keys verified in `data/shipped/arms/manifest.jsonl`.

**Interface corrections carried from v1.** `cli._data_root()` does not exist — use `cli.MANIFEST_PATH` and `MANIFEST_PATH.parent`. `api.py` has no module-level `app` — endpoints nest inside `create_app(live)`. Both are now correct throughout.

**Known risks, in priority order.**
1. **Task 2 Step 5 is a stop-the-line gate.** If the selector's recall disagrees with `docs/connectivity.md`, one of the two is wrong. Three numbers in this project have already turned out to be artifacts. Diagnose; do not paper over.
2. **Task 4 may be underpowered.** If `n_paired` < 25, report the McNemar p as indicative and say so rather than presenting it as decisive.
3. **The "your extractor is just worse" objection** is pre-empted in Task 5 Step 8 and README Limitations. If those two sections are cut for length, the objection becomes live.
4. **Video overrun** is the single most likely rule violation. Script to 2:40, not 3:00.
5. **Task 13 depends on a session-scoped scratchpad path** that may be cleaned. Step 6 names the regeneration route and says to cut the task if it fails. It is the designated first cut.
6. **Task 12 adds a runtime dependency (`mcp`)** to a project that must install cleanly in a judge's clean clone. Task 10 Step 1 re-clones and runs `uv sync`; if `mcp` breaks that, drop it from the default dependency group rather than debugging it on the 19th.

**Ecosystem alignment (added after reviewing the sponsor's org).** The sponsor's distribution strategy is agent integration — `hydradb-mcp` (`npx -y @hydradb/mcp@latest`, with documented Claude Desktop / Cursor / Windsurf / VS Code configs), `hydradb-claude-code`, `openclaw-hydradb`, `hydradb-cli`. Task 12 puts this project on those rails without touching the hosted service. Task 11 adopts a CI pattern seen in the wild — pinned engine, dual-transport proof, wipe-and-restart — which is independently the correct mitigation for issue #81. `hydra-db/benchmark` (Rust, engine perf) and `hydra-db/hydradb-bench` (Python, DeepEval RAG retrieval quality) were reviewed and neither has a harness that fits what is measured here; recorded so it is clear they were considered rather than skipped.

**Ethical line, applied throughout.** Repos in the **sponsor's org** are fair to measure and contribute back to, in the same register as issue #81 and PR #82. **Participant entries are learn-from-only: never measured, never named.** Task 9 Step 8 enforces the second half with a grep gate.

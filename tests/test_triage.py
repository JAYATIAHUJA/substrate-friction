"""The triage layer: a link in, a tier out — fail-closed at every seam.

Offline by construction: the GitHub API and the shallow clone are monkey-
patched; the gate runs for real on a mini repo fixture. The tier logic and
the rendered comment are the contracts under test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from friction import triage as T
from friction.triage import TriageReport, classify, parse_target, render_markdown


# ── URL parsing ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,slug,kind,n", [
    ("https://github.com/fastapi/fastapi/pull/16159", "fastapi/fastapi", "pr", 16159),
    ("https://github.com/fastapi/fastapi/pulls/16159", "fastapi/fastapi", "pr", 16159),
    ("https://github.com/o/r/issues/42", "o/r", "issue", 42),
    ("https://github.com/o/r/issues/42/", "o/r", "issue", 42),
])
def test_parse_target(url, slug, kind, n):
    assert parse_target(url) == (slug, kind, n)


@pytest.mark.parametrize("url", [
    "https://gitlab.com/o/r/pull/1",
    "https://github.com/o/r",
    "https://github.com/o/r/wiki/3",
    "not a url",
])
def test_parse_target_rejects(url):
    with pytest.raises(ValueError):
        parse_target(url)


# ── tier logic — four tiers, three vary today, all fail-closed ──────────────

def _gate(decision="RUN_FULL", symbols=5, tests=10, complete=True,
          unmatched=()):
    from friction.gate import GateVerdict
    from friction.live import LiveGate
    return LiveGate(
        repo=Path("r"), graph_sha="x" * 16, repo_head="abc1234", arm="arm_a",
        k=6, graph_nodes=10, graph_edges=12, changed_symbols=symbols,
        total_tests=tests, selected_tests=("t.a", "t.b"),
        graph_complete=complete, unmatched_changed=tuple(unmatched),
        verdict=GateVerdict(decision, 0.5, 30, "arm_a", 6, 0.95, "reason"),
        prior_n=30, prior_note="prior note on r")


def test_skip_safe_is_the_only_autonomy():
    assert classify(_gate(decision="SKIP_SAFE"), ["a.py"]) == "ai-autonomy"
    assert classify(_gate(decision="RUN_FULL"), ["a.py"]) != "ai-autonomy"


def test_no_python_is_out_of_scope():
    assert classify(_gate(symbols=0), ["README.md", "x.toml"]) == "out-of-scope"


@pytest.mark.parametrize("kwargs", [
    {"symbols": 0},                       # nothing resolved
    {"unmatched": ("gone/mod.py",)},      # files that matched no symbol
    {"complete": False},                  # truncated walk
    {"tests": 0},                         # no recognised tests
])
def test_blind_gates_route_to_needs_human(kwargs):
    assert classify(_gate(**kwargs), ["a.py"]) == "needs-human"


def test_measured_refusal_is_human_verification():
    assert classify(_gate(), ["a.py"]) == "human-verification"


# ── the rendered comment ────────────────────────────────────────────────────

def _report(**kw):
    defaults = dict(kind="pr", slug="o/r", number=7, head="pull/7/head",
                    changed=("a.py",), tier="human-verification",
                    label=T.TIERS["human-verification"],
                    blurb=T.TIER_BLURB["human-verification"],
                    gate=_gate(),
                    localization_note="fix sites are the PR's real changed files")
    defaults.update(kw)
    return TriageReport(**defaults)


def test_comment_carries_gate_numbers_not_hand_written_ones():
    md = render_markdown(_report())
    assert "triage/human-verification" in md or "human-verification" in md
    assert "RUN_FULL" in md
    assert "reason" in md                       # the gate's own reason string
    assert "prior note" in md                   # the gate's own prior note
    assert "Wilson lower bound" in md           # the fail-closed footer


def test_out_of_scope_comment_is_short_and_honest():
    md = render_markdown(_report(tier="out-of-scope",
                                 label=T.TIERS["out-of-scope"],
                                 blurb=T.TIER_BLURB["out-of-scope"],
                                 gate=None))
    assert "gate: not run" in md
    assert "RUN_FULL" not in md


def test_issue_comment_discloses_the_localization_layer():
    md = render_markdown(_report(
        kind="issue",
        localization_note="fix files taken from 1 path(s) mentioned in the "
                          "issue text — DISCLOSED heuristic"))
    assert "DISCLOSED" in md


# ── end-to-end triage() against a monkeypatched GitHub ─────────────────────

def _mini_repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "core.py").write_text(
        "def compute(x):\n    return x + 1\n\n"
        "def helper(x):\n    return compute(x)\n", encoding="utf-8")
    (d / "test_core.py").write_text(
        "from core import helper\n\n"
        "def test_helper():\n    assert helper(1) == 2\n", encoding="utf-8")
    return d


def test_triage_pr_end_to_end(tmp_path, monkeypatch):
    mini = _mini_repo(tmp_path)

    def fake_gh(path, token=None):
        if "/files" in path:
            return [{"filename": "core.py", "status": "modified"}]
        if path.endswith("/pulls/7"):
            return {"head": {"ref": "patch-1"}}
        raise AssertionError(f"unexpected api call {path}")

    def fake_clone(slug, dest, pr_number=None, branch=None):
        # copy the mini repo in place of a clone
        for f in mini.iterdir():
            (dest / f.name).write_text(f.read_text(), encoding="utf-8")

    monkeypatch.setattr(T, "_gh", fake_gh)
    monkeypatch.setattr(T, "_shallow_clone", fake_clone)

    r = T.triage("https://github.com/o/r/pull/7")
    assert r.tier == "human-verification"      # real gate on a real mini repo
    assert r.changed == ("core.py",)
    assert r.gate.graph_nodes > 0
    assert "DISCLOSED" not in r.localization_note  # PRs use the real diff


def test_triage_no_python_pr_skips_the_gate(tmp_path, monkeypatch):
    def fake_gh(path, token=None):
        if "/files" in path:
            return [{"filename": "README.md", "status": "modified"}]
        raise AssertionError(f"unexpected api call {path}")

    def fail_clone(*a, **k):
        raise AssertionError("clone must not happen for a no-python PR")

    monkeypatch.setattr(T, "_gh", fake_gh)
    monkeypatch.setattr(T, "_shallow_clone", fail_clone)

    r = T.triage("https://github.com/o/r/pull/9")
    assert r.tier == "out-of-scope"
    assert r.gate is None

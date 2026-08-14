"""The CLI gate. Unit tests stub the engine; anything needing the live node is
marked @pytest.mark.engine.

The gate's whole reason to exist honestly is that this project's headline result
is a NULL (AUC 0.565, p=0.726) and the engine-computed signal is a demonstrated
pathCount-truncation artifact. So the tests assert not only that the breakdown,
Cypher and timing render, but that the null caveat and the truncation warning
render too — a gate that printed a confident recommendation without them would be
the dishonest thing the fidelity guard exists to prevent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from friction import cli
from friction.client import EngineError
from friction.metric import Components
from friction.probe import Capabilities

CAPS = Capabilities("both", "incoming", True, "string", "merge_set_label",
                    "single_pattern_create", False, False)

ANSWERED = cli.GateResult(
    instance_id="django__django-15738", fix_sites=3, test_targets=7,
    components=Components(0.82, 0.71, 0.90, 0.34, 0.88, 0.65),
    score=0.79, band="HIGH", failure_probability=0.79,
    recommendation="route to a human engineer",
    cypher="CALL algo.MSpaths({sourceLabel: 'Function', ...}) YIELD path, pathCost "
           "RETURN path, pathCost",
    millis=14614.0, n_paths=20, path_truncated=True, fan_truncated=False,
    max_len=6, nodes=8691, edges=14349, answered=True,
)

UNCAPPED = cli.GateResult(
    instance_id="django__django-10880", fix_sites=1, test_targets=1,
    components=Components(0.10, 0.20, 0.05, 0.90, 0.00, 0.10),
    score=0.14, band="LOW", failure_probability=0.14,
    recommendation="safe for an autonomous agent",
    cypher="CALL algo.MSpaths({...}) YIELD path, pathCost RETURN path, pathCost",
    millis=10.6, n_paths=8, path_truncated=False, fan_truncated=False,
    max_len=6, nodes=3902, edges=5857, answered=True,
)

UNANSWERED = cli.GateResult(
    instance_id="django__django-10973", fix_sites=2, test_targets=4,
    components=None, score=float("nan"), band="UNKNOWN",
    failure_probability=float("nan"), recommendation="",
    cypher="CALL algo.MSpaths({...}) YIELD path, pathCost RETURN path, pathCost",
    millis=29999.0, n_paths=0, path_truncated=False, fan_truncated=False,
    max_len=6, nodes=8247, edges=11176, answered=False,
    error_kind="timeout",
    error_text="native_path_neighbors exceeded query timeout after 29999 ms",
)


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def test_render_shows_every_component_label():
    text = cli.render(ANSWERED)
    for label in ("Path multiplicity", "Mean path length", "Intermediate spread",
                  "Convergence", "Cyclic pressure", "Fan-in load"):
        assert label in text


def test_render_shows_score_band_and_recommendation():
    text = cli.render(ANSWERED)
    assert "0.79" in text
    assert "HIGH" in text
    assert "route to a human engineer" in text


def test_render_prints_the_cypher_and_the_timing():
    text = cli.render(ANSWERED)
    assert "algo.MSpaths" in text
    assert "14614" in text or "14614.0" in text


def test_render_includes_a_bar_for_each_component():
    text = cli.render(ANSWERED)
    assert text.count("█") > 0


def test_render_leads_with_the_null():
    """Every rendered gate must carry the measured null so the score is never
    read as a validated failure probability."""
    text = cli.render(ANSWERED)
    assert "0.565" in text          # the headline null AUC
    assert "0.726" in text          # its p-value
    assert "not" in text.lower()    # "does not predict" / "not validated"


def test_render_shows_truncation_caveat_when_capped():
    text = cli.render(ANSWERED)
    assert "pathCount" in text
    # the per-instance path count is surfaced
    assert "20" in text
    # cohort fidelity recall, the number that proves the cap matters
    assert "0.0264" in text or "2.6%" in text


def test_render_omits_the_capped_line_when_not_truncated():
    text = cli.render(UNCAPPED)
    assert "truncated at the pathCount cap" not in text
    # but the null caveat is still there
    assert "0.565" in text


def test_render_unanswerable_instance_shows_the_timeout_result():
    text = cli.render(UNANSWERED)
    assert "could not answer" in text.lower()
    assert "maxLen 6" in text or "maxLen=6" in text or "max-len" in text.lower()
    assert "timeout" in text.lower()
    # it must not fabricate a score/recommendation for an instance it never scored
    assert "route to a human engineer" not in text


# --------------------------------------------------------------------------
# recommendation
# --------------------------------------------------------------------------

def test_recommendation_flips_with_band():
    low = cli.recommendation("LOW")
    high = cli.recommendation("HIGH")
    assert "agent" in low.lower()
    assert "human" in high.lower()


# --------------------------------------------------------------------------
# check() against a stubbed engine
# --------------------------------------------------------------------------

_SOURCE_NODE_RE = re.compile(r"sourceNode:\s*(\d+)")


class EngineStub:
    """Answers MSpaths with a canned path list and SSpaths per-sourceNode, the
    two shapes friction.paths actually issues. Never touches a real node."""

    name = "stub"

    def __init__(self, mspaths_rows, fan_by_source=None, raise_text=None):
        self.mspaths_rows = mspaths_rows
        self.fan_by_source = fan_by_source or {}
        self.raise_text = raise_text
        self.cyphers: list[str] = []

    def query(self, cypher, params=None):
        self.cyphers.append(cypher)
        if self.raise_text is not None and "MSpaths" in cypher:
            raise EngineError(self.raise_text)
        if "MSpaths" in cypher:
            return self.mspaths_rows
        if "SSpaths" in cypher:
            m = _SOURCE_NODE_RE.search(cypher)
            source = int(m.group(1))
            return [{"path": [source, c]} for c in self.fan_by_source.get(source, [])]
        return []


def _subgraphs_file(tmp_path: Path) -> Path:
    data = [{
        "instance_id": "test__inst-1",
        "band": 4010000000,
        "nodes": 3621, "edges": 7739,
        "fix_site_ids": [4010007327, 4010007466],
        "test_target_ids": [4010027887, 4010027886],
    }]
    p = tmp_path / "subgraphs.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# fixed min-max bounds so the unit test does not depend on the engine cache
BOUNDS = {"f1": (0.0, 10.0), "f2": (0.0, 6.0), "f3": (0.0, 20.0),
          "f4": (0.0, 1.0), "f5": (0.0, 1.0), "f6": (0.0, 10.0)}


def test_check_scores_an_answered_instance_with_a_stub(tmp_path):
    fix = [4010007327, 4010007466]
    test = [4010027887, 4010027886]
    # three real fix->test paths
    rows = [{"path": [fix[0], 111, test[0]], "pathCost": 2.0},
            {"path": [fix[0], 222, test[1]], "pathCost": 2.0},
            {"path": [fix[1], test[0]], "pathCost": 1.0}]
    stub = EngineStub(rows, fan_by_source={fix[0]: [900, 901], fix[1]: [902]})
    result = cli.check("test__inst-1", transport=stub, caps=CAPS,
                       subgraphs_path=_subgraphs_file(tmp_path), bounds=BOUNDS)
    assert result.answered is True
    assert result.fix_sites == 2
    assert result.test_targets == 2
    assert result.n_paths == 3
    assert 0.0 <= result.score <= 1.0
    assert result.band in ("LOW", "MEDIUM", "HIGH")
    assert "algo.MSpaths" in result.cypher
    assert result.millis > 0.0
    # it rendered end to end
    text = cli.render(result)
    assert "test__inst-1" in text
    assert "algo.MSpaths" in text


def test_check_flags_pathcount_truncation(tmp_path):
    fix = [4010007327, 4010007466]
    test = [4010027887, 4010027886]
    # 20 rows == the pathCount cap -> truncated
    rows = [{"path": [fix[0], 100 + i, test[0]], "pathCost": 2.0} for i in range(20)]
    stub = EngineStub(rows, fan_by_source={fix[0]: [1], fix[1]: [2]})
    result = cli.check("test__inst-1", transport=stub, caps=CAPS,
                       subgraphs_path=_subgraphs_file(tmp_path), bounds=BOUNDS)
    assert result.path_truncated is True
    assert result.n_paths == 20
    assert "pathCount" in cli.render(result)


def test_check_renders_a_timeout_result_when_the_engine_raises(tmp_path):
    stub = EngineStub([], raise_text="{message: native_path_neighbors exceeded "
                      "query timeout after 29999 ms}")
    result = cli.check("test__inst-1", transport=stub, caps=CAPS,
                       subgraphs_path=_subgraphs_file(tmp_path), bounds=BOUNDS)
    assert result.answered is False
    assert result.error_kind == "timeout"
    text = cli.render(result)
    assert "could not answer" in text.lower()


def test_check_classifies_an_oom_result(tmp_path):
    stub = EngineStub([], raise_text="Neo.TransientError.General.MemoryPoolOutOfMemory")
    result = cli.check("test__inst-1", transport=stub, caps=CAPS,
                       subgraphs_path=_subgraphs_file(tmp_path), bounds=BOUNDS)
    assert result.answered is False
    assert result.error_kind == "oom"


def test_check_honours_max_len_override(tmp_path):
    fix = [4010007327, 4010007466]
    test = [4010027887, 4010027886]
    rows = [{"path": [fix[0], test[0]], "pathCost": 1.0}]
    stub = EngineStub(rows, fan_by_source={fix[0]: [1], fix[1]: [2]})
    result = cli.check("test__inst-1", transport=stub, caps=CAPS,
                       subgraphs_path=_subgraphs_file(tmp_path), bounds=BOUNDS,
                       max_len=4)
    assert result.max_len == 4
    assert "maxLen: 4" in result.cypher


# --------------------------------------------------------------------------
# main / subcommands
# --------------------------------------------------------------------------

def test_main_returns_nonzero_on_unknown_subcommand(capsys):
    assert cli.main(["nonsense"]) != 0


def test_main_no_subcommand_returns_nonzero(capsys):
    assert cli.main([]) != 0


def test_main_eval_prints_the_verdict(capsys):
    rc = cli.main(["eval"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NO-GO" in out


def test_main_fidelity_prints_the_truncation_evidence(capsys):
    rc = cli.main(["fidelity"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.0264" in out or "recall" in out.lower()


def test_main_list_shows_instances_and_answerability(capsys):
    rc = cli.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "django__django-" in out
    # a header/legend making answerability legible
    assert "engine" in out.lower() or "answered" in out.lower()

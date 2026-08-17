"""Contract tests for `friction gate` (CLI, replay, live) and the API."""

import json
from pathlib import Path

import pytest

from friction.cli import MANIFEST_PATH, main
from friction.gate import audit_recall

REPO = Path(__file__).resolve().parent.parent


def _first_miss() -> str:
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, "arm_b", 6)
    assert audit.misses, "expected at least one miss in the shipped corpus"
    return audit.misses[0]


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
    assert "full" in payload["advice"].lower()
    assert isinstance(payload["per_repo"], dict)


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


def test_gate_instance_mode_shows_the_dropped_test(capsys):
    demo_id = _first_miss()
    code = main(["gate", "--arm", "arm_b", "--instance", demo_id])
    out = capsys.readouterr().out
    assert demo_id in out
    assert "NOT SELECTED" in out
    assert "-[:CALLED_BY*1..6]->" in out
    assert code == 1


def test_gate_instance_mode_reports_an_unknown_instance(capsys):
    code = main(["gate", "--instance", "nope__nope-0"])
    assert code == 2
    assert "not" in capsys.readouterr().out.lower()


# ── live repo mode ───────────────────────────────────────────────────────


@pytest.fixture()
def mini_repo(tmp_path):
    """A tiny but real Python repo: one module, one test that calls into it."""
    (tmp_path / "core.py").write_text(
        "def compute(x):\n    return x + 1\n\n"
        "def helper(x):\n    return compute(x)\n", encoding="utf-8")
    (tmp_path / "test_core.py").write_text(
        "from core import helper\n\n"
        "def test_helper():\n    assert helper(1) == 2\n", encoding="utf-8")
    return tmp_path


def test_gate_repo_builds_a_graph_and_returns_a_verdict(capsys, mini_repo):
    code = main(["gate", "--repo", str(mini_repo),
                 "--changed", "core.py", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["graph_nodes"] > 0
    assert payload["decision"] == "RUN_FULL"
    assert "labelled corpus" in payload["prior_note"]
    assert code == 1


def test_gate_repo_selects_the_calling_test(capsys, mini_repo):
    main(["gate", "--repo", str(mini_repo), "--changed", "core.py", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["changed_symbols"] > 0
    assert any("test_" in t for t in payload["selected_tests"])


def test_gate_repo_reports_an_unmatched_changed_path(capsys, mini_repo):
    main(["gate", "--repo", str(mini_repo), "--changed", "does/not/exist.py",
          "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["unmatched_changed"] == ["does/not/exist.py"]
    assert payload["decision"] == "RUN_FULL"


def test_gate_repo_rejects_a_non_directory(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("", encoding="utf-8")
    from friction.live import gate_repo
    with pytest.raises(NotADirectoryError):
        gate_repo(f, changed_files=[], arm="arm_a", k=6)


# ── API ──────────────────────────────────────────────────────────────────


def _client():
    from fastapi.testclient import TestClient
    from friction.api import create_app
    return TestClient(create_app(live=False))


def test_gate_endpoint_returns_the_corpus_verdict():
    r = _client().get("/gate", params={"arm": "arm_b"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "RUN_FULL"
    assert body["n"] > 0


def test_gate_endpoint_rejects_an_unknown_arm():
    assert _client().get("/gate", params={"arm": "arm_z"}).status_code == 400


def test_gate_instance_endpoint_returns_the_dropped_tests_and_the_cypher():
    demo_id = _first_miss()
    r = _client().get(f"/gate/{demo_id}", params={"arm": "arm_b"})
    assert r.status_code == 200
    body = r.json()
    assert body["dropped_guarding_tests"]
    assert "-[:CALLED_BY*1..6]->" in body["cypher"]


def test_gate_instance_endpoint_404s_on_an_unknown_instance():
    assert _client().get("/gate/nope__nope-0").status_code == 404

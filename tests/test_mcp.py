"""The MCP tool functions, tested directly — the logic is what matters."""

import json

from friction.cli import MANIFEST_PATH
from friction.gate import audit_recall
from friction.mcp_server import gate_check, gate_explain


def test_gate_check_returns_a_refusal_for_the_type_resolved_arm():
    payload = json.loads(gate_check(arm="arm_b"))
    assert payload["decision"] == "RUN_FULL"
    assert payload["n"] > 0
    assert "advice" in payload


def test_gate_check_rejects_an_unknown_arm():
    assert "error" in json.loads(gate_check(arm="arm_z"))


def test_gate_explain_is_task_shaped_and_names_the_dropped_tests():
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, "arm_b", 6)
    assert audit.misses
    payload = json.loads(gate_explain(
        instance_ids=[audit.misses[0], "nope__nope-0"]))
    assert len(payload) == 2
    assert payload[0]["dropped_guarding_tests"]
    assert "-[:CALLED_BY*1..6]->" in payload[0]["cypher"]
    assert payload[1]["error"] == "unknown instance"

import pytest
from friction import probe


class FakeTransport:
    """Accepts only the forms we declare legal; raises EngineError otherwise."""

    name = "fake"

    def __init__(self, legal: set[str]):
        self.legal = legal
        self.seen: list[str] = []

    def query(self, cypher, params=None):
        self.seen.append(cypher)
        for fragment in self.legal:
            if fragment in cypher:
                return [{"ok": 1}]
        from friction.client import EngineError
        raise EngineError("parse error near token")


def test_derive_picks_lowercase_both_when_only_it_parses():
    results = [
        probe.ProbeResult("rel_direction:both", True, "", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:incoming", True, "", "..."),
        probe.ProbeResult("rel_direction:INCOMING", False, "parse error", "..."),
        probe.ProbeResult("pairwise", False, "unknown config key", "..."),
        probe.ProbeResult("node_loader:create_inline", True, "", "..."),
        probe.ProbeResult("edge_loader:match_match_create", False, "parse error", "..."),
        probe.ProbeResult("edge_loader:merge_then_create", True, "", "..."),
        probe.ProbeResult("http_params", True, "", "..."),
    ]
    caps = probe.derive(results)
    assert caps.rel_direction_both == "both"
    assert caps.rel_direction_incoming == "incoming"
    assert caps.pairwise_supported is False
    assert caps.node_loader_form == "create_inline"
    assert caps.edge_loader_form == "merge_then_create"


def test_derive_raises_when_no_direction_parses():
    results = [
        probe.ProbeResult("rel_direction:both", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
    ]
    with pytest.raises(probe.ProbeFailure):
        probe.derive(results)


def test_run_all_records_failures_without_raising():
    t = FakeTransport(legal={"relDirection: 'both'"})
    results = probe.run_all(t)
    assert any(r.ok for r in results)
    assert any(not r.ok for r in results)


def test_write_and_load_round_trip(tmp_path):
    caps = probe.Capabilities(
        rel_direction_both="both", rel_direction_incoming="incoming",
        pairwise_supported=False, node_loader_form="create_inline",
        edge_loader_form="merge_then_create", http_params_supported=True,
    )
    path = tmp_path / "engine-capabilities.md"
    probe.write_report([probe.ProbeResult("x", True, "", "y")], caps, path)
    assert probe.load_capabilities(path) == caps

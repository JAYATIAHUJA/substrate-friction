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


def _measured_results(**overrides):
    """A results list mirroring the LIVE engine's measured truth, so derive()
    can be exercised without a running engine. Individual probes can be flipped
    with overrides keyed by probe name."""
    base = {
        "rel_direction:both": True,
        "rel_direction:BOTH": True,
        "rel_direction:Both": True,
        "rel_direction:incoming": True,
        "rel_direction:INCOMING": True,
        "rel_direction:in": False,
        "rel_direction:IN": False,
        "sourceValues_type:int": False,
        "sourceValues_type:string": True,
        "pairwise": True,
        "count_path": False,
        "node_loader:create_inline": False,
        "node_loader:merge_then_set": False,
        "node_loader:merge_set_label": True,
        "edge_loader:match_match_create": False,
        "edge_loader:single_pattern_create": True,
        "edge_loader:merge_then_create": False,
        "edge_loader:match_create_return": False,
        "http_params": False,
    }
    base.update(overrides)
    return [
        probe.ProbeResult(name, ok, "" if ok else "parse error", "...")
        for name, ok in base.items()
    ]


def test_derive_picks_lowercase_both_when_only_it_parses():
    results = [
        probe.ProbeResult("rel_direction:both", True, "", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:incoming", True, "", "..."),
        probe.ProbeResult("rel_direction:INCOMING", False, "parse error", "..."),
        probe.ProbeResult("sourceValues_type:int", False, "must be a list of strings", "..."),
        probe.ProbeResult("sourceValues_type:string", True, "", "..."),
        probe.ProbeResult("pairwise", False, "unknown config key", "..."),
        probe.ProbeResult("count_path", False, "unknown path projection count", "..."),
        probe.ProbeResult("node_loader:create_inline", True, "", "..."),
        probe.ProbeResult("edge_loader:match_match_create", False, "parse error", "..."),
        probe.ProbeResult("edge_loader:merge_then_create", True, "", "..."),
        probe.ProbeResult("http_params", True, "", "..."),
    ]
    caps = probe.derive(results)
    assert caps.rel_direction_both == "both"
    assert caps.rel_direction_incoming == "incoming"
    assert caps.pairwise_supported is False
    assert caps.sourceValues_type == "string"
    assert caps.count_path_supported is False
    assert caps.node_loader_form == "create_inline"
    assert caps.edge_loader_form == "merge_then_create"


def test_derive_reports_pairwise_and_count_path_when_they_parse():
    caps = probe.derive(_measured_results())
    assert caps.pairwise_supported is True
    assert caps.sourceValues_type == "string"
    assert caps.count_path_supported is False
    assert caps.rel_direction_both == "both"
    assert caps.rel_direction_incoming == "incoming"


def test_derive_prefers_node_loader_that_parses():
    # create_inline and merge_then_set are rejected; only merge_set_label parses,
    # so derive() must report merge_set_label regardless of dict ordering.
    caps = probe.derive(_measured_results())
    assert caps.node_loader_form == "merge_set_label"


def test_derive_raises_when_no_direction_parses():
    results = [
        probe.ProbeResult("rel_direction:both", False, "parse error", "..."),
        probe.ProbeResult("rel_direction:BOTH", False, "parse error", "..."),
    ]
    with pytest.raises(probe.ProbeFailure):
        probe.derive(results)


def test_derive_raises_when_no_source_values_type_parses():
    results = _measured_results(**{
        "sourceValues_type:int": False,
        "sourceValues_type:string": False,
    })
    with pytest.raises(probe.ProbeFailure):
        probe.derive(results)


def test_run_all_records_failures_without_raising():
    t = FakeTransport(legal={"relDirection: 'both'"})
    results = probe.run_all(t)
    assert any(r.ok for r in results)
    assert any(not r.ok for r in results)


def test_run_all_isolates_source_values_type_from_pairwise():
    names = {r.name for r in probe.run_all(FakeTransport(legal=set()))}
    assert "sourceValues_type:int" in names
    assert "sourceValues_type:string" in names
    assert "pairwise" in names
    assert "count_path" in names


def test_write_and_load_round_trip(tmp_path):
    caps = probe.Capabilities(
        rel_direction_both="both", rel_direction_incoming="incoming",
        pairwise_supported=True, sourceValues_type="string",
        node_loader_form="merge_set_label",
        edge_loader_form="single_pattern_create", http_params_supported=False,
        count_path_supported=False,
    )
    path = tmp_path / "engine-capabilities.md"
    probe.write_report([probe.ProbeResult("x", True, "", "y")], caps, path)
    assert probe.load_capabilities(path) == caps

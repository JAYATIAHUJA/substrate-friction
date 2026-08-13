import os

import pytest

from friction import paths
from friction.config import Settings
from friction.probe import Capabilities

SETTINGS = Settings("bolt://x", "http://x", "t", "default", "default",
                    "cell-0", 6, 20, "both")
# Capabilities carries 8 fields (see friction.probe.Capabilities): the
# sourceValues_type and count_path_supported flags were added after the brief
# was written. On this build sourceValues are matched as strings and
# count(path) is rejected, so those two flags are "string" and False here.
CAPS_NO_PAIRWISE = Capabilities("both", "incoming", False, "string",
                                "merge_set_label", "single_pattern_create",
                                False, False)
CAPS_PAIRWISE = Capabilities("both", "incoming", True, "string",
                             "merge_set_label", "single_pattern_create",
                             False, False)


class StubTransport:
    name = "stub"

    def __init__(self, rows):
        self.rows = rows
        self.last_cypher = None
        self.last_params = None
        self.query_calls = 0

    def query(self, cypher, params=None):
        self.last_cypher = cypher
        self.last_params = params
        self.query_calls += 1
        return self.rows


def test_cypher_uses_probed_direction_not_a_literal():
    caps = Capabilities("BOTH", "INCOMING", False, "string", "merge_set_label",
                        "single_pattern_create", False, False)
    cypher = paths.build_mspaths_cypher(caps, SETTINGS, ("CALLS",), [1], [3])
    assert "relDirection: 'BOTH'" in cypher


def test_cypher_omits_pairwise_when_unsupported():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                        [1], [3])
    assert "pairwise" not in cypher


def test_cypher_includes_pairwise_when_supported():
    cypher = paths.build_mspaths_cypher(CAPS_PAIRWISE, SETTINGS, ("CALLS",),
                                        [1], [3])
    assert "pairwise: true" in cypher


def test_cypher_matches_the_string_sid_property_not_the_int_id():
    # MEASURED ENGINE TRUTH: sourceValues/targetValues are matched against the
    # STRING `sid` property; matching against the int `id` prop returns nothing.
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                        [1], [3])
    assert "sourceProperty: 'sid'" in cypher
    assert "targetProperty: 'sid'" in cypher


def test_cypher_always_bounds_maxlen():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                        [1], [3])
    assert "maxLen: 6" in cypher
    assert "*" not in cypher


def test_cypher_passes_rel_types_as_a_list():
    cypher = paths.build_mspaths_cypher(
        CAPS_NO_PAIRWISE, SETTINGS, ("CALLS", "HAS_METHOD", "INHERITS"), [1], [3])
    assert "relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS']" in cypher


def test_cypher_inlines_id_lists_as_string_literals_not_parameters():
    # MEASURED ENGINE TRUTH: the engine rejects a Bolt parameter for
    # sourceValues/targetValues ("composite parameter $fixIds is only supported
    # as an UNWIND input"). The id list must be inlined as a Cypher list of
    # STRING literals (the ids address the STRING `sid` property).
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                        [2000000123, 2000000456], [2000000789])
    assert "sourceValues: ['2000000123', '2000000456']" in cypher
    assert "targetValues: ['2000000789']" in cypher
    # No leftover Bolt-parameter placeholders anywhere in the statement.
    assert "$fixIds" not in cypher
    assert "$testIds" not in cypher
    assert "$" not in cypher


def test_build_mspaths_rejects_non_integer_ids_rather_than_interpolating():
    # Ids are integers by construction. Anything else (e.g. an injection
    # attempt) must raise, never be string-formatted into the query text.
    with pytest.raises((TypeError, ValueError)):
        paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                   ["1') RETURN 1 //"], [3])
    with pytest.raises((TypeError, ValueError)):
        paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",),
                                   [1.5], [3])


def test_build_fan_in_inlines_ids_and_rejects_non_integers():
    cypher = paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS,
                                       [990001, 990002])
    assert "sourceValues: ['990001', '990002']" in cypher
    assert "$fixIds" not in cypher
    assert "$" not in cypher
    with pytest.raises((TypeError, ValueError)):
        paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS, ["nope"])


def test_extract_node_ids_handles_list_of_ints():
    assert paths.extract_node_ids([1, 2, 3]) == [1, 2, 3]


def test_extract_node_ids_handles_dicts_with_id_keys():
    value = [{"id": 4}, {"id": 5}]
    assert paths.extract_node_ids(value) == [4, 5]


def test_extract_node_ids_handles_nested_nodes_key():
    value = {"nodes": [{"id": 7}, {"id": 8}]}
    assert paths.extract_node_ids(value) == [7, 8]


def test_fix_to_test_paths_returns_paths_and_timing():
    t = StubTransport([{"path": [1, 2, 3], "pathCost": 2.0},
                       {"path": [1, 4, 3], "pathCost": 2.0}])
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1], [3])
    assert result.paths == [[1, 2, 3], [1, 4, 3]]
    assert result.costs == [2.0, 2.0]
    assert result.millis >= 0
    assert "algo.MSpaths" in result.cypher


def test_fix_to_test_paths_inlines_ids_and_passes_no_params():
    # MEASURED ENGINE TRUTH: the id list is inlined as STRING literals in the
    # query text and NO Bolt params dict is sent (the engine rejects a param for
    # sourceValues/targetValues).
    t = StubTransport([{"path": [1, 2, 3], "pathCost": 2.0}])
    paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2], [3])
    assert "sourceValues: ['1', '2']" in t.last_cypher
    assert "targetValues: ['3']" in t.last_cypher
    assert t.last_params is None


def test_fix_to_test_paths_flags_truncation_at_path_count():
    rows = [{"path": [1, 2, 3], "pathCost": 2.0}] * SETTINGS.path_count
    t = StubTransport(rows)
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1], [3])
    assert result.truncated is True


def test_fix_to_test_paths_returns_empty_for_empty_inputs():
    t = StubTransport([])
    result = paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [], [3])
    assert result.paths == []
    assert t.last_cypher is None


def test_fan_in_counts_rows_client_side_uses_incoming_and_maxlen_one():
    # MEASURED ENGINE TRUTH: count(path) does not parse, so the query yields the
    # paths and fan_in() counts the returned rows itself.
    rows = [{"path": [990001, i]} for i in range(12)]
    t = StubTransport(rows)
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert count == 12
    assert "relDirection: 'incoming'" in cypher
    assert "maxLen: 1" in cypher
    assert "count(path)" not in cypher
    assert "RETURN path" in cypher


def test_fan_in_inlines_ids_and_passes_no_params():
    t = StubTransport([{"path": [990001, 1]}])
    paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert "sourceValues: ['1', '2']" in t.last_cypher
    assert t.last_params is None


def test_fan_in_cap_comes_from_settings_not_a_hardcoded_literal():
    # F6 (fan-in load) must be capped by the configurable Settings field, not a
    # literal buried in the query string, so the cap can be tuned per run.
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 7)
    t = StubTransport([{"path": [990001, 1]}])
    paths.fan_in(t, CAPS_NO_PAIRWISE, small, [1, 2])
    assert "pathCount: 7" in t.last_cypher
    assert "pathCount: 500" not in t.last_cypher


def test_fan_in_flags_truncation_when_row_count_reaches_cap():
    # A hub with more incoming CALLS than the cap is clipped; that clipping
    # compresses exactly the high-friction tail, so it must be reported.
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 3)
    rows = [{"path": [990001, i]} for i in range(3)]
    t = StubTransport(rows)
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, small, [1, 2])
    assert count == 3
    assert truncated is True


def test_fan_in_not_truncated_when_below_cap():
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 3)
    rows = [{"path": [990001, i]} for i in range(2)]
    t = StubTransport(rows)
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, small, [1, 2])
    assert count == 2
    assert truncated is False


def test_fan_in_empty_inputs_are_not_truncated():
    t = StubTransport([])
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, SETTINGS, [])
    assert count == 0
    assert truncated is False
    assert t.last_cypher is None


# --- live-engine regression guard ----------------------------------------
# The absence of exactly this test is what let the $-parameter bug through:
# paths.py was only ever exercised against StubTransport, which happily records
# whatever params it is handed and never validates the Cypher against a real
# engine. This test seeds a tiny graph in a fresh id band and asserts real paths
# come back from fix_to_test_paths against the live engine.

# A fresh id band above 9_000_000_000, clear of every other band in the live
# `default` graph (instance bands sit at 2e9..~2.49e9; probe nodes at ~990_000;
# client round-trip nodes at 9001..9008).
ENGINE_TEST_BASE = 9_000_000_017


@pytest.mark.engine
def test_fix_to_test_paths_returns_real_paths_from_live_engine(tmp_path):
    from friction import loader, probe
    from friction.client import connect

    settings = Settings.from_env()
    try:
        transport = connect(settings, prefer="bolt")
    except Exception as exc:  # noqa: BLE001 - engine may not be running
        pytest.skip(f"engine not reachable: {exc}")

    try:
        caps = probe.derive(probe.run_all(transport))

        base = ENGINE_TEST_BASE
        fix_id = base + 1
        mid_a = base + 2
        mid_b = base + 3
        test_id = base + 4

        def fn_row(node_id: int, name: str, is_test: bool) -> dict:
            return {
                "label": "Function", "id": node_id, "sid": str(node_id),
                "name": name, "file_id": base, "line_start": 1, "line_end": 2,
                "cyclomatic": 1, "is_test": is_test,
            }

        nodes_path = tmp_path / "nodes.ndjson"
        edges_path = tmp_path / "edges.ndjson"
        node_rows = [
            fn_row(fix_id, "fix_site", False),
            fn_row(mid_a, "mid_a", False),
            fn_row(mid_b, "mid_b", False),
            fn_row(test_id, "test_target", True),
        ]
        # A single directed chain fix_site -> mid_a -> mid_b -> test_target, so
        # exactly one CALLS path (length 3) connects the fix site to the test.
        edge_rows = [
            {"src": fix_id, "dst": mid_a, "type": "CALLS", "weight": 1.0},
            {"src": mid_a, "dst": mid_b, "type": "CALLS", "weight": 1.0},
            {"src": mid_b, "dst": test_id, "type": "CALLS", "weight": 1.0},
        ]
        nodes_path.write_text(
            "\n".join(__import__("json").dumps(r) for r in node_rows) + "\n",
            encoding="utf-8")
        edges_path.write_text(
            "\n".join(__import__("json").dumps(r) for r in edge_rows) + "\n",
            encoding="utf-8")

        loader.load(transport, caps, tmp_path)

        result = paths.fix_to_test_paths(
            transport, caps, settings, [fix_id], [test_id])

        # The whole point: a real, non-empty path came back from the engine, and
        # it connects the seeded fix site to the seeded test target. Under the
        # old $-parameter form the engine rejected the query and nothing did.
        assert result.paths, (
            f"engine returned no paths; cypher was:\n{result.cypher}")
        endpoints = {p[0] for p in result.paths} | {p[-1] for p in result.paths}
        assert fix_id in endpoints
        assert test_id in endpoints
    finally:
        transport.close()

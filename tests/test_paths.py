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

    def query(self, cypher, params=None):
        self.last_cypher = cypher
        self.last_params = params
        return self.rows


def test_cypher_uses_probed_direction_not_a_literal():
    caps = Capabilities("BOTH", "INCOMING", False, "string", "merge_set_label",
                        "single_pattern_create", False, False)
    cypher = paths.build_mspaths_cypher(caps, SETTINGS, ("CALLS",))
    assert "relDirection: 'BOTH'" in cypher


def test_cypher_omits_pairwise_when_unsupported():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",))
    assert "pairwise" not in cypher


def test_cypher_includes_pairwise_when_supported():
    cypher = paths.build_mspaths_cypher(CAPS_PAIRWISE, SETTINGS, ("CALLS",))
    assert "pairwise: true" in cypher


def test_cypher_matches_the_string_sid_property_not_the_int_id():
    # MEASURED ENGINE TRUTH: sourceValues/targetValues are matched against the
    # STRING `sid` property; matching against the int `id` prop returns nothing.
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",))
    assert "sourceProperty: 'sid'" in cypher
    assert "targetProperty: 'sid'" in cypher


def test_cypher_always_bounds_maxlen():
    cypher = paths.build_mspaths_cypher(CAPS_NO_PAIRWISE, SETTINGS, ("CALLS",))
    assert "maxLen: 6" in cypher
    assert "*" not in cypher


def test_cypher_passes_rel_types_as_a_list():
    cypher = paths.build_mspaths_cypher(
        CAPS_NO_PAIRWISE, SETTINGS, ("CALLS", "HAS_METHOD", "INHERITS"))
    assert "relTypes: ['CALLS', 'HAS_METHOD', 'INHERITS']" in cypher


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


def test_fix_to_test_paths_passes_string_ids_not_ints():
    # MEASURED ENGINE TRUTH: an integer sourceValues list is a parse error;
    # the wrapper must convert every id to str before it reaches the engine.
    t = StubTransport([{"path": [1, 2, 3], "pathCost": 2.0}])
    paths.fix_to_test_paths(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2], [3])
    assert t.last_params["fixIds"] == ["1", "2"]
    assert t.last_params["testIds"] == ["3"]
    assert all(isinstance(x, str) for x in t.last_params["fixIds"])
    assert all(isinstance(x, str) for x in t.last_params["testIds"])


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
    count, cypher, millis = paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert count == 12
    assert "relDirection: 'incoming'" in cypher
    assert "maxLen: 1" in cypher
    assert "count(path)" not in cypher
    assert "RETURN path" in cypher


def test_fan_in_passes_string_ids_not_ints():
    t = StubTransport([{"path": [990001, 1]}])
    paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert t.last_params["fixIds"] == ["1", "2"]
    assert all(isinstance(x, str) for x in t.last_params["fixIds"])

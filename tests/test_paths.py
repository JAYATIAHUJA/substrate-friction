import os
import re

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


_SOURCE_NODE_RE = re.compile(r"sourceNode:\s*(\d+)")


class FanInStub:
    """A transport that answers each SSpaths call according to the `sourceNode`
    the query actually names, instead of returning one canned row list for every
    query. This is what makes the fan-in unit tests exercise real behaviour —
    per-source dispatch and the client-side DISTINCT union — rather than assert
    on a fixed string, which is the mock-instead-of-behaviour gap that hid the
    original $sourceNode bug.

    `callers_by_source` maps a fix-site id to the list of caller ids the engine
    would return for it; each is turned into a `[sourceNode, caller]` path row,
    exactly the shape the live engine yields for incoming/maxLen-1.
    """

    name = "fanstub"

    def __init__(self, callers_by_source):
        self.callers_by_source = callers_by_source
        self.cyphers: list[str] = []
        self.all_params: list = []

    def query(self, cypher, params=None):
        self.cyphers.append(cypher)
        self.all_params.append(params)
        m = _SOURCE_NODE_RE.search(cypher)
        if not m:
            raise AssertionError(f"fan-in query names no sourceNode:\n{cypher}")
        source = int(m.group(1))
        callers = self.callers_by_source.get(source, [])
        return [{"path": [source, c]} for c in callers]


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


def test_build_fan_in_uses_integer_sourcenode_not_a_values_set():
    # MEASURED ENGINE TRUTH: algo.SSpaths rejects the MSpaths-style sourceValues
    # SET ("missing OpenCypher query parameter $sourceNode") and demands ONE
    # integer sourceNode. The fan-in query must emit that scalar form.
    cypher = paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS, 990001)
    assert "sourceNode: 990001" in cypher
    # The old, rejected form must be gone entirely.
    assert "sourceValues" not in cypher
    assert "sourceLabel" not in cypher
    assert "$" not in cypher
    assert "relDirection: 'incoming'" in cypher
    assert "maxLen: 1" in cypher
    assert "count(path)" not in cypher
    assert "RETURN path" in cypher


def test_build_fan_in_rejects_non_integer_sourcenode():
    # sourceNode is a genuine int by construction; anything else (a string node
    # id the engine would reject, or an injection attempt) must raise rather than
    # be formatted into the query text.
    with pytest.raises((TypeError, ValueError)):
        paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS, "990001")
    with pytest.raises((TypeError, ValueError)):
        paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS, "1) RETURN 1 //")
    with pytest.raises((TypeError, ValueError)):
        paths.build_fan_in_cypher(CAPS_NO_PAIRWISE, SETTINGS, 1.5)


def test_build_fan_in_rejects_unknown_sspaths_source_form():
    # If the engine were re-probed to a form other than the measured integer
    # sourceNode, the builder must fail loudly rather than emit a rejected query.
    caps = Capabilities("both", "incoming", False, "string", "merge_set_label",
                        "single_pattern_create", False, False, "sourceValues")
    with pytest.raises(ValueError):
        paths.build_fan_in_cypher(caps, SETTINGS, 990001)


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


def test_fan_in_counts_distinct_incoming_callers_using_incoming_maxlen_one():
    # MEASURED ENGINE TRUTH: SSpaths is single-source, so fan_in issues one query
    # per fix site and counts the distinct callers the engine returns. count(path)
    # does not parse, so the rows are counted client-side.
    t = FanInStub({1: [990001, 990002, 990003], 2: [990004]})
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert count == 4
    assert len(t.cyphers) == 2  # one SSpaths per fix site
    assert "relDirection: 'incoming'" in cypher
    assert "maxLen: 1" in cypher
    assert "count(path)" not in cypher
    assert "RETURN path" in cypher


def test_fan_in_dedups_a_caller_shared_by_two_fix_sites():
    # A function that calls two different fix sites is ONE distinct caller. The
    # naive per-site sum here is 4 (3 + 1 where 990003 is shared); the correct
    # deduped count is 3. This is the behaviour a fixed-row stub could never test.
    t = FanInStub({1: [990001, 990002, 990003], 2: [990003]})
    count, _, _, _ = paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [1, 2])
    assert count == 3


def test_fan_in_queries_each_fix_site_by_its_own_sourcenode():
    t = FanInStub({10: [1], 20: [2], 30: [3]})
    paths.fan_in(t, CAPS_NO_PAIRWISE, SETTINGS, [10, 20, 30])
    joined = "\n".join(t.cyphers)
    assert "sourceNode: 10" in joined
    assert "sourceNode: 20" in joined
    assert "sourceNode: 30" in joined
    # No Bolt parameters: the id is inlined in each statement.
    assert all(p is None for p in t.all_params)


def test_fan_in_cap_comes_from_settings_not_a_hardcoded_literal():
    # F6 (fan-in load) must be capped by the configurable Settings field, not a
    # literal buried in the query string, so the cap can be tuned per run.
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 7)
    t = FanInStub({1: [990001]})
    paths.fan_in(t, CAPS_NO_PAIRWISE, small, [1])
    assert "pathCount: 7" in t.cyphers[0]
    assert "pathCount: 500" not in t.cyphers[0]


def test_fan_in_flags_truncation_when_a_fix_site_reaches_cap():
    # A hub called by more functions than the cap is clipped; that clipping
    # compresses exactly the high-friction tail, so it must be reported even when
    # only ONE fix site in the set is affected.
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 3)
    # Fix site 1 returns exactly the cap (3) -> clipped; site 2 is below it.
    t = FanInStub({1: [990001, 990002, 990003], 2: [990004]})
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, small, [1, 2])
    assert truncated is True


def test_fan_in_not_truncated_when_every_fix_site_is_below_cap():
    small = Settings("bolt://x", "http://x", "t", "default", "default",
                     "cell-0", 6, 20, "both", 3)
    t = FanInStub({1: [990001, 990002], 2: [990003]})
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, small, [1, 2])
    assert count == 3
    assert truncated is False


def test_fan_in_empty_inputs_are_not_truncated():
    t = FanInStub({})
    count, cypher, millis, truncated = paths.fan_in(
        t, CAPS_NO_PAIRWISE, SETTINGS, [])
    assert count == 0
    assert cypher == ""
    assert truncated is False
    assert t.cyphers == []


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


# A second fresh band for the fan-in engine test, disjoint from every other.
FAN_IN_TEST_BASE = 9_000_000_050


@pytest.mark.engine
def test_fan_in_returns_known_in_degree_from_live_engine(tmp_path):
    # The regression that mattered: fan_in emitted an SSpaths sourceValues SET the
    # engine rejects on every real instance ("missing OpenCypher query parameter
    # $sourceNode"), and no test caught it because the stub returned canned rows
    # regardless of the query. This seeds a graph whose incoming CALLS in-degree
    # is KNOWN and asserts fan_in returns exactly it, against the real engine.
    from friction import loader, probe
    from friction.client import connect

    settings = Settings.from_env()
    try:
        transport = connect(settings, prefer="bolt")
    except Exception as exc:  # noqa: BLE001 - engine may not be running
        pytest.skip(f"engine not reachable: {exc}")

    try:
        caps = probe.derive(probe.run_all(transport))

        base = FAN_IN_TEST_BASE
        # Two fix sites. Callers c1,c2,c3 -> f1; shared -> f1 AND f2; c4 -> f2.
        # Distinct incoming callers of {f1, f2} = {c1, c2, c3, shared, c4} = 5.
        # f1 also has an OUTGOING edge to a sink, which must NOT be counted.
        f1, f2 = base + 1, base + 2
        c1, c2, c3, c4, shared, sink = (base + 3, base + 4, base + 5,
                                        base + 6, base + 7, base + 8)

        def fn_row(node_id: int, name: str) -> dict:
            return {
                "label": "Function", "id": node_id, "sid": str(node_id),
                "name": name, "file_id": base, "line_start": 1, "line_end": 2,
                "cyclomatic": 1, "is_test": False,
            }

        node_rows = [
            fn_row(f1, "fix1"), fn_row(f2, "fix2"), fn_row(c1, "c1"),
            fn_row(c2, "c2"), fn_row(c3, "c3"), fn_row(c4, "c4"),
            fn_row(shared, "shared"), fn_row(sink, "sink"),
        ]
        edge_rows = [
            {"src": c1, "dst": f1, "type": "CALLS", "weight": 1.0},
            {"src": c2, "dst": f1, "type": "CALLS", "weight": 1.0},
            {"src": c3, "dst": f1, "type": "CALLS", "weight": 1.0},
            {"src": shared, "dst": f1, "type": "CALLS", "weight": 1.0},
            {"src": shared, "dst": f2, "type": "CALLS", "weight": 1.0},
            {"src": c4, "dst": f2, "type": "CALLS", "weight": 1.0},
            # Outgoing from a fix site: fan-in must ignore it.
            {"src": f1, "dst": sink, "type": "CALLS", "weight": 1.0},
        ]

        (tmp_path / "nodes.ndjson").write_text(
            "\n".join(__import__("json").dumps(r) for r in node_rows) + "\n",
            encoding="utf-8")
        (tmp_path / "edges.ndjson").write_text(
            "\n".join(__import__("json").dumps(r) for r in edge_rows) + "\n",
            encoding="utf-8")

        loader.load(transport, caps, tmp_path)

        count, cypher, millis, truncated = paths.fan_in(
            transport, caps, settings, [f1, f2])

        # The whole point: the real engine ran the query and returned the exact
        # known distinct in-degree. Under the old sourceValues form it rejected
        # every call and this would have raised, not counted.
        assert count == 5, f"expected 5 distinct callers; cypher was:\n{cypher}"
        assert truncated is False

        # A single fix site in isolation returns exactly its own callers (f1 has
        # 4 incoming; the outgoing edge to sink is not among them).
        count_f1, _, _, _ = paths.fan_in(transport, caps, settings, [f1])
        assert count_f1 == 4
    finally:
        transport.close()

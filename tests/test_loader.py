import json
from pathlib import Path

import pytest

from friction import loader
from friction.probe import Capabilities
from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable, FileSym, FunctionSym

# The live engine (docs/engine-capabilities.md) only accepts the merge_set_label
# node form and the single_pattern_create edge form. Capabilities is an 8-field
# record; construct it with the values the probe actually measured.
CAPS = Capabilities(
    rel_direction_both="both",
    rel_direction_incoming="incoming",
    pairwise_supported=True,
    sourceValues_type="string",
    node_loader_form="merge_set_label",
    edge_loader_form="single_pattern_create",
    http_params_supported=False,
    count_path_supported=False,
)


class RecordingTransport:
    name = "recording"

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def query(self, cypher, params=None):
        self.calls.append((cypher, params or {}))
        return []


def _table():
    t = SymbolTable()
    t.files.append(FileSym(0, "mod_a.py", 1, 12))
    t.functions.append(FunctionSym(1, "helper", "mod_a.helper", 0, 1, 4, 2, False, None))
    t.functions.append(FunctionSym(2, "render", "mod_a.W.render", 0, 6, 8, 1, False, None))
    return t


def test_emit_writes_one_json_object_per_line(tmp_path):
    paths = loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 3)], tmp_path)
    node_lines = paths["nodes"].read_text().strip().splitlines()
    edge_lines = paths["edges"].read_text().strip().splitlines()
    assert len(node_lines) == 3
    assert len(edge_lines) == 1
    assert json.loads(edge_lines[0])["type"] == "CALLS"
    assert all("label" in json.loads(line) for line in node_lines)


def test_emit_carries_string_sid_mirror(tmp_path):
    # algo.MSpaths matches sourceValues/targetValues against a STRING property;
    # every node row must carry sid = str(id) or path queries match nothing.
    paths = loader.emit_ndjson(_table(), [], tmp_path)
    for line in paths["nodes"].read_text().strip().splitlines():
        row = json.loads(line)
        assert row["sid"] == str(row["id"])
        assert isinstance(row["sid"], str)


def test_node_statement_matches_probed_form():
    stmt = loader.node_statement(CAPS, "Function")
    # The only form the live engine accepts: MERGE by id, apply the label and
    # properties via SET.
    assert stmt.startswith("UNWIND $rows AS row MERGE (n {id: row.id}) SET n:Function")
    assert "n.sid = row.sid" in stmt
    # The rejected create_inline form is still buildable for documentation.
    inline_caps = Capabilities("both", "incoming", True, "string", "create_inline",
                               "single_pattern_create", False, False)
    assert loader.node_statement(inline_caps, "Function").startswith(
        "UNWIND $rows AS row CREATE (n:Function")


def test_edge_statement_matches_probed_form():
    stmt = loader.edge_statement(CAPS, "CALLS")
    assert "[:CALLS" in stmt and "CREATE" in stmt
    merge_caps = Capabilities("both", "incoming", True, "string", "merge_set_label",
                              "merge_then_create", False, False)
    assert "MERGE" in loader.edge_statement(merge_caps, "CALLS")


def test_edge_statement_rejects_unknown_form():
    bad = Capabilities("both", "incoming", True, "string", "merge_set_label", "nope",
                       False, False)
    with pytest.raises(KeyError):
        loader.edge_statement(bad, "CALLS")


def test_load_batches_and_sends_nodes_before_edges(tmp_path):
    loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 3)], tmp_path)
    t = RecordingTransport()
    counts = loader.load(t, CAPS, tmp_path, batch_size=2)
    node_calls = [c for c in t.calls if "MERGE (n {id: row.id})" in c[0]]
    edge_calls = [c for c in t.calls if "[:CALLS" in c[0]]
    assert node_calls and edge_calls
    assert t.calls.index(node_calls[-1]) < t.calls.index(edge_calls[0])
    assert counts["Function"] == 2
    assert counts["CALLS"] == 1


def test_load_never_sends_inline_lists(tmp_path):
    loader.emit_ndjson(_table(), [Edge(2, 1, "CALLS", 1)], tmp_path)
    t = RecordingTransport()
    loader.load(t, CAPS, tmp_path, batch_size=10)
    for cypher, params in t.calls:
        assert "UNWIND [" not in cypher
        assert "rows" in params


# --- typed graph (five labels, seven edge types) round-trips --------------

def test_node_props_cover_the_two_new_labels():
    assert "Test" in loader.NODE_PROPS
    assert "ConfigKey" in loader.NODE_PROPS
    assert loader.NODE_PROPS["ConfigKey"] == ["id", "sid", "name"]


def test_node_statement_builds_for_test_and_config_key():
    for label in ("Test", "ConfigKey"):
        stmt = loader.node_statement(CAPS, label)
        assert stmt.startswith(f"UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{label}")
        assert "n.sid = row.sid" in stmt


def _emit_typed_graph(tmp_path):
    from friction import arms
    from friction.config_keys import ConfigRead
    from friction.scip.extract import CallEdge, Def, TypedEdge

    def sym(t):
        return f"scip-python python p 1 `{t}"

    defs = [
        Def(sym("m`/C#"), "m.py", 0, 20, "m::C#", "class"),
        Def(sym("m`/Base#"), "m.py", 30, 40, "m::Base#", "class"),
        Def(sym("m`/C#save()."), "m.py", 2, 8, "m::C#save().", "function"),
        Def(sym("m`/run()."), "m.py", 22, 28, "m::run().", "function"),
        Def(sym("tests.t`/test_it()."), "tests/t.py", 0, 6,
            "tests.t::test_it().", "function"),
    ]
    arms.emit_typed_arm(
        [CallEdge("m::run().", "m::C#save().", False, 2),
         CallEdge("tests.t::test_it().", "m::C#save().", False, 1)],
        defs, ["m.py", "tests/t.py"],
        [TypedEdge("m::C#save().", "m.py", "DEFINED_IN"),
         TypedEdge("m::C#", "m::C#save().", "HAS_METHOD"),
         TypedEdge("m::C#", "m::Base#", "INHERITS"),
         TypedEdge("tests/t.py", "m.py", "IMPORTS")],
        [ConfigRead("m::run().", "DEBUG")],
        band=20_000_000_000, out_dir=tmp_path,
        covers=[("tests.t::test_it().", "m::C#save().")])


def test_typed_graph_round_trips_every_node_label_and_edge_type(tmp_path):
    _emit_typed_graph(tmp_path)
    t = RecordingTransport()
    counts = loader.load(t, CAPS, tmp_path, batch_size=1000)
    # every new label loaded
    for label in ("File", "Class", "Function", "Test", "ConfigKey"):
        assert counts.get(label, 0) >= 1, label
    # all seven edge types loaded
    for rel in ("CALLS", "DEFINED_IN", "HAS_METHOD", "INHERITS", "IMPORTS",
                "READS_CONFIG", "COVERS"):
        assert counts.get(rel, 0) >= 1, rel
    # nodes before edges, and no batch exceeds the engine's 1024 cap
    last_node = max(i for i, c in enumerate(t.calls) if "MERGE (n {id: row.id})" in c[0])
    first_edge = min(i for i, c in enumerate(t.calls) if "]->" in c[0])
    assert last_node < first_edge
    for _cypher, params in t.calls:
        assert len(params["rows"]) <= 1024

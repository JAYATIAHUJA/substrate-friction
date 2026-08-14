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

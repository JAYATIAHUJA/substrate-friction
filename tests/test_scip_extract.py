import pytest

from friction.scip import extract as E
from friction.scip import schema


def _index(docs):
    pb = schema.scip_pb2()
    idx = pb.Index()
    for path, occs in docs.items():
        d = idx.documents.add()
        d.relative_path = path
        for sym, roles, rng, enc in occs:
            o = d.occurrences.add()
            o.symbol = sym
            o.symbol_roles = roles
            o.range.extend(rng)
            if enc:
                o.enclosing_range.extend(enc)
    return idx


F_OUTER = "scip-python python p 1 `m`/outer()."
F_INNER = "scip-python python p 1 `m`/outer()/inner()."
F_CALLEE = "scip-python python p 1 `m`/callee()."
STR_LOWER = "scip-python python python-stdlib 3 `builtins`/str#lower()."


def test_collect_definitions_reads_enclosing_range():
    idx = _index({"m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 20, 0])]})
    defs = E.collect_definitions(idx)
    assert len(defs) == 1
    assert defs[0].start == 0 and defs[0].end == 20


def test_definitions_without_enclosing_range_are_skipped():
    idx = _index({"m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], None)]})
    assert E.collect_definitions(idx) == []


def test_innermost_prefers_the_smallest_containing_span():
    outer = E.Def(F_OUTER, "m.py", 0, 20, "m::outer().", "function")
    inner = E.Def(F_INNER, "m.py", 5, 10, "m::outer()/inner().", "function")
    by_path = {"m.py": [outer, inner]}
    assert E.innermost(by_path, "m.py", 7).symbol == F_INNER
    assert E.innermost(by_path, "m.py", 15).symbol == F_OUTER
    assert E.innermost(by_path, "m.py", 25) is None
    assert E.innermost(by_path, "other.py", 7) is None


def test_reference_inside_a_definition_becomes_an_edge():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_CALLEE, schema.DEFINITION_ROLE, [12, 0, 12, 6], [12, 0, 14, 0]),
        (F_CALLEE, 0, [3, 4, 3, 10], None),
    ]})
    edges, stats = E.extract_edges(idx)
    pairs = {(e.src, e.dst) for e in edges}
    assert ("m::outer().", "m::callee().") in pairs
    assert stats["references"] == 1


def test_definition_occurrences_are_not_treated_as_references():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
    ]})
    edges, _ = E.extract_edges(idx)
    assert edges == []


def test_external_targets_are_flagged_not_dropped():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (STR_LOWER, 0, [3, 4, 3, 10], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert len(edges) == 1
    assert edges[0].dst_external is True


def test_self_edges_are_dropped():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_OUTER, 0, [3, 4, 3, 9], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert edges == []


def test_repeated_references_accumulate_weight():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0]),
        (F_CALLEE, schema.DEFINITION_ROLE, [12, 0, 12, 6], [12, 0, 14, 0]),
        (F_CALLEE, 0, [3, 4, 3, 10], None),
        (F_CALLEE, 0, [5, 4, 5, 10], None),
    ]})
    edges, _ = E.extract_edges(idx)
    assert [e.weight for e in edges if e.dst == "m::callee()."] == [2]


def test_references_outside_any_definition_are_counted_not_silently_lost():
    idx = _index({"m.py": [(F_CALLEE, 0, [3, 4, 3, 10], None)]})
    edges, stats = E.extract_edges(idx)
    assert edges == []
    assert stats["unenclosed_references"] == 1

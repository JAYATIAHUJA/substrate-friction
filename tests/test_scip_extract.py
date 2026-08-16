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


# --- typed nodes and structural edges -------------------------------------

CLASS_C = "scip-python python p 1 `m`/C#"
CLASS_BASE = "scip-python python p 1 `m`/Base#"
M_SAVE = "scip-python python p 1 `m`/C#save()."


def test_enclosing_class_of_a_method():
    assert E.enclosing_class("m::C#save().") == "m::C#"
    assert E.enclosing_class("m::Outer#Inner#f().") == "m::Outer#Inner#"


def test_enclosing_class_of_a_module_level_function_is_none():
    assert E.enclosing_class("m::run().") is None


def test_collect_files_are_distinct_and_sorted():
    idx = _index({
        "b.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 2, 0])],
        "a.py": [(F_CALLEE, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 2, 0])],
    })
    assert E.collect_files(E.collect_definitions(idx)) == ["a.py", "b.py"]


def test_defined_in_links_each_function_to_its_file():
    idx = _index({"m.py": [
        (F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0])]})
    edges = E.defined_in_edges(E.collect_definitions(idx))
    assert edges == [E.TypedEdge("m::outer().", "m.py", "DEFINED_IN")]


def test_has_method_links_class_to_its_method():
    idx = _index({"m.py": [
        (CLASS_C, schema.DEFINITION_ROLE, [0, 0, 0, 7], [0, 0, 20, 0]),
        (M_SAVE, schema.DEFINITION_ROLE, [2, 4, 2, 8], [2, 4, 6, 0]),
    ]})
    edges = E.has_method_edges(E.collect_definitions(idx))
    assert E.TypedEdge("m::C#", "m::C#save().", "HAS_METHOD") in edges


def test_has_method_omitted_when_class_not_defined_here():
    # a method whose enclosing class has no definition in this index yields no
    # HAS_METHOD edge (nothing to hang it off).
    idx = _index({"m.py": [
        (M_SAVE, schema.DEFINITION_ROLE, [2, 4, 2, 8], [2, 4, 6, 0])]})
    assert E.has_method_edges(E.collect_definitions(idx)) == []


def test_inherits_reads_base_class_from_the_class_header_line():
    # class C(Base): on line 5 -> a reference to Base on line 5.
    idx = _index({"m.py": [
        (CLASS_C, schema.DEFINITION_ROLE, [5, 0, 5, 7], [5, 0, 20, 0]),
        (CLASS_BASE, schema.DEFINITION_ROLE, [0, 0, 0, 10], [0, 0, 3, 0]),
        (CLASS_BASE, 0, [5, 8, 5, 12], None),
    ]})
    defs = E.collect_definitions(idx)
    assert E.inherits_edges(idx, defs) == [
        E.TypedEdge("m::C#", "m::Base#", "INHERITS")]


def test_inherits_ignores_a_class_reference_off_the_header_line():
    # a reference to Base inside C's body (line 10) is not a base class.
    idx = _index({"m.py": [
        (CLASS_C, schema.DEFINITION_ROLE, [5, 0, 5, 7], [5, 0, 20, 0]),
        (CLASS_BASE, schema.DEFINITION_ROLE, [0, 0, 0, 10], [0, 0, 3, 0]),
        (CLASS_BASE, 0, [10, 8, 10, 12], None),
    ]})
    defs = E.collect_definitions(idx)
    assert E.inherits_edges(idx, defs) == []


def test_imports_links_files_from_a_module_level_reference():
    # a.py references outer() (defined in m.py) at module scope (no enclosing def).
    idx = _index({
        "m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0])],
        "a.py": [(F_OUTER, 0, [0, 0, 0, 5], None)],
    })
    defs = E.collect_definitions(idx)
    assert E.imports_edges(idx, defs) == [
        E.TypedEdge("a.py", "m.py", "IMPORTS")]


def test_imports_ignores_references_inside_a_function_body():
    # the same reference, but now enclosed by a.py's own function -> not an import.
    idx = _index({
        "m.py": [(F_OUTER, schema.DEFINITION_ROLE, [0, 0, 0, 5], [0, 0, 10, 0])],
        "a.py": [
            (F_CALLEE, schema.DEFINITION_ROLE, [0, 0, 0, 6], [0, 0, 9, 0]),
            (F_OUTER, 0, [3, 4, 3, 9], None),
        ],
    })
    defs = E.collect_definitions(idx)
    assert E.imports_edges(idx, defs) == []


def test_structural_edges_reports_a_per_type_census():
    idx = _index({"m.py": [
        (CLASS_C, schema.DEFINITION_ROLE, [5, 0, 5, 7], [5, 0, 20, 0]),
        (M_SAVE, schema.DEFINITION_ROLE, [6, 4, 6, 8], [6, 4, 10, 0]),
    ]})
    edges, stats = E.structural_edges(idx)
    assert stats["DEFINED_IN"] == 1
    assert stats["HAS_METHOD"] == 1
    assert stats["INHERITS"] == 0
    assert stats["IMPORTS"] == 0

from friction import fidelity
from friction.parsing.calls import Edge


EDGES = [
    Edge(1, 2, "CALLS", 1),
    Edge(2, 3, "CALLS", 1),
    Edge(1, 4, "CALLS", 1),
    Edge(4, 3, "CALLS", 1),
    Edge(5, 6, "IMPORTS", 1),
]


def test_reference_finds_both_routes():
    found = fidelity.reference_paths(EDGES, [1], [3], max_len=3, rel_types=("CALLS",))
    assert sorted(found) == [[1, 2, 3], [1, 4, 3]]


def test_reference_respects_max_len():
    found = fidelity.reference_paths(EDGES, [1], [3], max_len=1, rel_types=("CALLS",))
    assert found == []


def test_reference_ignores_other_rel_types():
    found = fidelity.reference_paths(EDGES, [5], [6], max_len=3, rel_types=("CALLS",))
    assert found == []


def test_reference_treats_edges_as_undirected():
    found = fidelity.reference_paths(EDGES, [3], [1], max_len=3, rel_types=("CALLS",))
    assert len(found) == 2


def test_compare_computes_recall():
    engine = {"i1": [[1, 2, 3]], "i2": [[1, 4, 3], [1, 2, 3]]}
    reference = {"i1": [[1, 2, 3], [1, 4, 3]], "i2": [[1, 4, 3], [1, 2, 3]]}
    report = fidelity.compare(engine, reference)
    assert report.instances == 2
    assert report.engine_total == 3
    assert report.reference_total == 4
    assert report.recall == 0.75
    assert report.worst_instance == "i1"


def test_compare_handles_empty_reference():
    report = fidelity.compare({"i1": []}, {"i1": []})
    assert report.recall == 1.0


def test_write_report_states_recall(tmp_path):
    report = fidelity.FidelityReport(2, 3, 4, 0.75, 1, "i1")
    path = tmp_path / "fidelity.md"
    fidelity.write_report(report, path)
    assert "0.75" in path.read_text()

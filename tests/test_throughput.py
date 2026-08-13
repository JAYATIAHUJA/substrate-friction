from friction import throughput
from friction.probe import Capabilities

CAPS = Capabilities("both", "incoming", False, "create_inline", "merge_then_create", True)


class CountingTransport:
    name = "counting"

    def __init__(self):
        self.batches = 0
        self.rows = 0

    def query(self, cypher, params=None):
        self.batches += 1
        if params and "rows" in params:
            self.rows += len(params["rows"])
        return []


def test_measure_sends_every_row_for_each_batch_size():
    t = CountingTransport()
    rows = throughput.measure(t, CAPS, total=1000, batch_sizes=(250, 500))
    assert len(rows) == 2
    assert {r["batch_size"] for r in rows} == {250, 500}
    assert all(r["edges_per_sec"] > 0 for r in rows)
    assert t.rows == 1000 * 2 + 1000 * 2  # nodes then edges, for each batch size


def test_write_report_contains_best_rate(tmp_path):
    rows = [{"batch_size": 500, "seconds": 2.0, "edges_per_sec": 250.0},
            {"batch_size": 1000, "seconds": 1.0, "edges_per_sec": 500.0}]
    path = tmp_path / "throughput.md"
    throughput.write_report(rows, path)
    text = path.read_text()
    assert "500.0" in text and "1000" in text

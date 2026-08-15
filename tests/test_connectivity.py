import json

import networkx as nx
import pytest

from friction import connectivity


def _chain(*ids):
    g = nx.DiGraph()
    for a, b in zip(ids, ids[1:]):
        g.add_edge(a, b)
    return g


def test_directed_chain_connects_one_way_only():
    # 1 -> 2 -> 3 -> 4
    g = _chain(1, 2, 3, 4)
    assert connectivity.connected_within(g, [1], [4], 6, undirected=False) is True
    # backward direction is NOT connected in a directed graph
    assert connectivity.connected_within(g, [4], [1], 6, undirected=False) is False


def test_undirected_connects_both_directions():
    g = _chain(1, 2, 3, 4)
    assert connectivity.connected_within(g, [1], [4], 6, undirected=True) is True
    assert connectivity.connected_within(g, [4], [1], 6, undirected=True) is True


def test_k_bound_is_respected():
    # 1 -> 2 -> 3 -> 4 : distance 3
    g = _chain(1, 2, 3, 4)
    assert connectivity.connected_within(g, [1], [4], 3, undirected=False) is True
    assert connectivity.connected_within(g, [1], [4], 2, undirected=False) is False


def test_empty_endpoint_set_returns_none():
    g = _chain(1, 2, 3)
    assert connectivity.connected_within(g, [], [3], 6, undirected=True) is None
    assert connectivity.connected_within(g, [1], [], 6, undirected=True) is None
    assert connectivity.connected_within(g, [], [], 6, undirected=True) is None


def test_any_to_any_across_endpoint_sets():
    # 10 -> 11 ; 20 isolated. src {20, 10} should reach dst {11} via 10.
    g = nx.DiGraph()
    g.add_edge(10, 11)
    g.add_node(20)
    assert connectivity.connected_within(g, [20, 10], [11], 6, undirected=False) is True


def test_overlapping_endpoints_are_connected_at_zero_hops():
    g = _chain(1, 2, 3)
    assert connectivity.connected_within(g, [2], [2, 99], 6, undirected=False) is True


def test_missing_source_node_is_unreachable_not_an_error():
    g = _chain(1, 2, 3)
    # 777 is not in the graph and does not overlap the dst set
    assert connectivity.connected_within(g, [777], [3], 6, undirected=True) is False


def _write_instance(root, instance_id, arm, edges):
    d = root / instance_id / arm
    d.mkdir(parents=True)
    with (d / "edges.ndjson").open("w", encoding="utf-8") as fh:
        for src, dst in edges:
            fh.write(json.dumps({"src": src, "dst": dst, "type": "CALLS",
                                 "weight": 1}) + "\n")


def test_report_over_two_fake_instances_aggregates(tmp_path):
    arms = tmp_path / "arms"
    # inst_a: test -> fix directed (2->1), so fix->test is False, test->fix True.
    _write_instance(arms, "inst_a", "arm_b", [(2, 3), (3, 1)])
    # inst_b: fix -> test directed (1 -> ... -> 2), both directions connected undirected.
    _write_instance(arms, "inst_b", "arm_b", [(10, 11), (11, 12)])

    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {"instance_id": "inst_a",
         "arm_b": {"fix_site_ids": [1], "test_target_ids": [2]}},
        {"instance_id": "inst_b",
         "arm_b": {"fix_site_ids": [10], "test_target_ids": [12]}},
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                        encoding="utf-8")

    report = connectivity.measure_corpus(manifest, arms, "arm_b")
    assert report.n == 2
    # inst_a: 2->3->1 so test(2)->fix(1) connected; fix(1)->test(2) not.
    # inst_b: 10->11->12 so fix(10)->test(12) connected; test(12)->fix(10) not.
    assert report.fix_to_test == 1
    assert report.test_to_fix == 1
    # both are connected undirected
    assert report.undirected_6 == 2
    assert report.undirected_10 == 2
    assert set(report.per_instance) == {"inst_a", "inst_b"}
    assert report.per_instance["inst_a"]["test_to_fix"] is True
    assert report.per_instance["inst_a"]["fix_to_test"] is False


def test_report_skips_instances_missing_an_endpoint_set(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "inst_a", "arm_b", [(1, 2)])
    _write_instance(arms, "inst_b", "arm_b", [(10, 11)])
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {"instance_id": "inst_a",
         "arm_b": {"fix_site_ids": [1], "test_target_ids": [2]}},
        # inst_b has no fix sites -> excluded from the corpus measurement
        {"instance_id": "inst_b",
         "arm_b": {"fix_site_ids": [], "test_target_ids": [11]}},
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                        encoding="utf-8")
    report = connectivity.measure_corpus(manifest, arms, "arm_b")
    assert report.n == 1
    assert set(report.per_instance) == {"inst_a"}


def test_write_report_emits_the_direction_table_and_caveats(tmp_path):
    arms = tmp_path / "arms"
    _write_instance(arms, "inst_a", "arm_b", [(2, 1)])
    _write_instance(arms, "inst_a", "arm_a", [(2, 1)])
    manifest = tmp_path / "manifest.jsonl"
    row = {"instance_id": "inst_a",
           "arm_b": {"fix_site_ids": [1], "test_target_ids": [2]},
           "arm_a": {"fix_site_ids": [1], "test_target_ids": [2]}}
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")
    rb = connectivity.measure_corpus(manifest, arms, "arm_b")
    ra = connectivity.measure_corpus(manifest, arms, "arm_a")

    out = tmp_path / "connectivity.md"
    connectivity.write_report(rb, ra, out)
    text = out.read_text(encoding="utf-8")
    assert "fix" in text.lower() and "test" in text.lower()
    # the three directions must all be named
    for phrase in ("fix", "test", "undirected"):
        assert phrase in text.lower()
    # the load-bearing caveats
    assert "does not call tests" in text.lower()
    assert "shares a neighbourhood" in text.lower() or "neighbourhood" in text.lower()
    assert "both" in text.lower()

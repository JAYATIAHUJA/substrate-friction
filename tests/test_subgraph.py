"""Unit tests for the pure subgraph logic (no engine required).

Covers the four properties the brief names: BFS respects the hop count; a budget
cap sets the truncation flag; the neighbourhood contains every node on a known
short path between two seeds; and an unreachable seed pair still yields a
subgraph holding both seeds with no connecting path.
"""

from __future__ import annotations

from friction.parsing.calls import Edge
from friction.subgraph import (
    EDGE_BUDGET,
    NODE_BUDGET,
    TRAVERSED_TYPES,
    build_subgraph_rows,
    induced_neighbourhood,
)


def _chain(n: int, rel: str = "CALLS") -> list[Edge]:
    """A simple directed chain 0->1->2->...->(n-1)."""
    return [Edge(i, i + 1, rel) for i in range(n - 1)]


# --- BFS respects hop count -----------------------------------------------

def test_bfs_stops_at_hop_count():
    # Chain of 11 nodes (0..10). From node 0, 2 undirected hops reach {0,1,2}.
    edges = _chain(11)
    kept_edges, stats = induced_neighbourhood(
        edges, seed_ids=[0], hops=2, node_budget=999, edge_budget=999)
    assert set(stats["kept_node_ids"]) == {0, 1, 2}
    assert stats["hops_completed"] == 2
    assert stats["truncated"] is False


def test_bfs_hop_count_is_undirected():
    # Direction is ignored: from the middle node of a chain, 1 hop reaches both
    # neighbours even though one edge points "backwards".
    edges = _chain(5)  # 0->1->2->3->4
    _, stats = induced_neighbourhood(
        edges, seed_ids=[2], hops=1, node_budget=999, edge_budget=999)
    assert set(stats["kept_node_ids"]) == {1, 2, 3}


def test_zero_hops_keeps_only_seeds():
    edges = _chain(5)
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0, 4], hops=0, node_budget=999, edge_budget=999)
    assert set(stats["kept_node_ids"]) == {0, 4}
    assert stats["hops_completed"] == 0


def test_natural_saturation_is_not_truncation():
    # Whole graph is within reach before hops run out.
    edges = _chain(4)  # 0..3
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0], hops=10, node_budget=999, edge_budget=999)
    assert set(stats["kept_node_ids"]) == {0, 1, 2, 3}
    assert stats["truncated"] is False
    assert stats["hops_completed"] == 3  # saturated after 3 hops, then stopped


# --- budget truncation sets the flag --------------------------------------

def test_node_budget_truncates_and_flags():
    edges = _chain(50)
    kept_edges, stats = induced_neighbourhood(
        edges, seed_ids=[0], hops=49, node_budget=5, edge_budget=999)
    assert stats["truncated"] is True
    assert stats["node_budget_hit"] is True
    assert stats["nodes"] <= 5
    # The hop that would have pushed it over budget was not added.
    assert len(stats["kept_node_ids"]) <= 5


def test_edge_budget_truncates_and_flags():
    edges = _chain(50)
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0], hops=49, node_budget=999, edge_budget=3)
    assert stats["truncated"] is True
    assert stats["edge_budget_hit"] is True
    assert stats["edges"] <= 3


def test_within_budget_is_not_truncated():
    edges = _chain(5)
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0], hops=10, node_budget=NODE_BUDGET, edge_budget=EDGE_BUDGET)
    assert stats["truncated"] is False
    assert stats["node_budget_hit"] is False
    assert stats["edge_budget_hit"] is False


def test_dense_seed_set_over_edge_budget_flags_immediately():
    # A clique of 5 seeds has 10 undirected edges; an edge budget of 3 is blown
    # before any expansion, but the seeds are still kept.
    nodes = [0, 1, 2, 3, 4]
    edges = [Edge(a, b, "CALLS") for i, a in enumerate(nodes) for b in nodes[i + 1:]]
    _, stats = induced_neighbourhood(
        edges, seed_ids=nodes, hops=3, node_budget=999, edge_budget=3)
    assert stats["truncated"] is True
    assert stats["edge_budget_hit"] is True
    assert set(stats["kept_node_ids"]) == set(nodes)


# --- neighbourhood contains every node on a known short path --------------

def test_neighbourhood_contains_full_short_path_between_two_seeds():
    # 0->1->2->3->4; seeds at both ends. With hops >= path length, every
    # intermediate node (1,2,3) must be present.
    edges = _chain(5)
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0, 4], hops=4, node_budget=999, edge_budget=999)
    assert set(stats["kept_node_ids"]) >= {0, 1, 2, 3, 4}
    # The two seeds land in one component -> reachable from each other.
    assert stats["seed_pairs_connected"] == 1
    assert stats["seed_components"] == 1


def test_meeting_in_the_middle_covers_the_connecting_node():
    # Two seeds three hops apart via a single middle node m:
    #   f -> a -> m <- b <- t   (undirected distance f..t = 4)
    # With hops=2 from each seed, BFS from both ends still meets at m.
    edges = [Edge(0, 1, "CALLS"), Edge(1, 2, "CALLS"),
             Edge(3, 2, "CALLS"), Edge(4, 3, "CALLS")]
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0, 4], hops=2, node_budget=999, edge_budget=999)
    assert 2 in stats["kept_node_ids"]  # the connecting node is present


# --- unreachable seed pair -------------------------------------------------

def test_unreachable_seed_pair_keeps_both_seeds_no_path():
    # Two disconnected components; a seed in each.
    edges = [Edge(0, 1, "CALLS"), Edge(10, 11, "CALLS")]
    _, stats = induced_neighbourhood(
        edges, seed_ids=[0, 10], hops=6, node_budget=999, edge_budget=999)
    assert {0, 10} <= set(stats["kept_node_ids"])
    assert stats["seed_components"] == 2
    assert stats["seed_pairs_connected"] == 0
    assert stats["seed_pairs_total"] == 1


def test_isolated_seed_with_no_edges_is_still_kept():
    edges = [Edge(0, 1, "CALLS")]
    kept_edges, stats = induced_neighbourhood(
        edges, seed_ids=[99], hops=6, node_budget=999, edge_budget=999)
    assert stats["kept_node_ids"] == [99]
    assert kept_edges == []
    assert stats["seed_pairs_total"] == 0


# --- row building ----------------------------------------------------------

def test_build_subgraph_rows_offsets_into_band_and_includes_isolated_seed():
    table = {
        0: {"label": "Function", "id": 0, "sid": "0", "name": "f", "file_id": 100},
        1: {"label": "Function", "id": 1, "sid": "1", "name": "g", "file_id": 100},
        99: {"label": "Function", "id": 99, "sid": "99", "name": "iso", "file_id": 100},
    }
    kept_edges = [Edge(0, 1, "CALLS")]
    band = 3_000_000_000
    rows = build_subgraph_rows(table, seed_ids=[0, 99], kept_edges=kept_edges,
                               band_base=band)
    ids = {r["id"] for r in rows["nodes"]}
    assert ids == {band + 0, band + 1, band + 99}  # isolated seed 99 included
    for r in rows["nodes"]:
        assert r["sid"] == str(r["id"])
        assert r["file_id"] == 100 + band  # file_id shifted too
    assert rows["edges"] == [
        {"src": band + 0, "dst": band + 1, "type": "CALLS", "weight": 1}
    ]


def test_build_subgraph_rows_skips_seed_absent_from_table():
    table = {0: {"label": "Function", "id": 0, "sid": "0", "name": "f", "file_id": None}}
    rows = build_subgraph_rows(table, seed_ids=[0, 777], kept_edges=[],
                               band_base=5)
    ids = {r["id"] for r in rows["nodes"]}
    assert ids == {5}  # 777 has no table row -> not emitted


def test_traversed_types_are_the_metric_relations():
    assert TRAVERSED_TYPES == ("CALLS", "HAS_METHOD", "INHERITS")

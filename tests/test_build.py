"""Unit tests for the pure parts of friction.build.

Network/engine paths (build_instance_graph, build_many) are not exercised here;
they require a running node and are covered by @pytest.mark.engine tests
elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from friction.build import (
    GRAPH_BASE,
    GRAPH_STRIDE,
    batched,
    choose_strategy,
    graph_name,
    instance_base,
    offset_edge_row,
    offset_node_row,
)


@dataclass
class FakeInstance:
    base_commit: str


# --- id banding -----------------------------------------------------------

def test_instance_base_starts_at_graph_base():
    assert instance_base(0) == GRAPH_BASE


def test_instance_base_strides_and_is_disjoint():
    assert instance_base(1) == GRAPH_BASE + GRAPH_STRIDE
    # A django graph is ~33k nodes; the stride must dwarf that so bands never
    # overlap.
    assert GRAPH_STRIDE > 1_000_000
    assert instance_base(5) - instance_base(4) == GRAPH_STRIDE


def test_instance_base_rejects_negative():
    with pytest.raises(ValueError):
        instance_base(-1)


def test_bands_do_not_overlap_across_many_instances():
    max_graph_size = GRAPH_STRIDE  # generous upper bound on node count
    for i in range(50):
        lo, hi = instance_base(i), instance_base(i) + max_graph_size
        assert hi <= instance_base(i + 1)  # strictly below next band start + 0


# --- graph naming ---------------------------------------------------------

def test_graph_name_is_deterministic_and_commit_scoped():
    c = "b9cf764be62e5d05b2c6b9f5cf1a2a1f3e4d5c6a"
    assert graph_name(c) == "g_b9cf764be62e"
    assert graph_name(c) == graph_name(c)


def test_graph_name_shared_by_same_commit_differs_across_commits():
    a = "aaaaaaaaaaaa1111"
    b = "bbbbbbbbbbbb2222"
    assert graph_name(a) == graph_name(a)
    assert graph_name(a) != graph_name(b)


# --- batching -------------------------------------------------------------

def test_batched_even_split():
    assert list(batched([1, 2, 3, 4], 2)) == [[1, 2], [3, 4]]


def test_batched_remainder():
    assert list(batched([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_batched_size_larger_than_seq():
    assert list(batched([1, 2], 10)) == [[1, 2]]


def test_batched_empty():
    assert list(batched([], 3)) == []


def test_batched_rejects_zero_size():
    with pytest.raises(ValueError):
        list(batched([1], 0))


# --- strategy selection ---------------------------------------------------

def test_choose_strategy_unique_commits_picks_per_instance():
    insts = [FakeInstance(f"commit{i:040x}") for i in range(231)]
    result = choose_strategy(insts)
    assert result["strategy"] == "per_instance"
    assert result["distinct_commits"] == 231
    assert result["largest_group"] == 1


def test_choose_strategy_matches_real_django_shape():
    # 230 distinct commits over 231 instances: one commit has two instances.
    insts = [FakeInstance(f"c{i:040x}") for i in range(230)]
    insts.append(FakeInstance(insts[0].base_commit))  # duplicate of insts[0]
    result = choose_strategy(insts)
    assert result["n_instances"] == 231
    assert result["distinct_commits"] == 230
    assert result["largest_group"] == 2
    assert result["strategy"] == "per_instance"


def test_choose_strategy_clustered_commits_picks_per_base_commit():
    # Ten commits, each shared by 20 instances -> heavy consolidation.
    insts = [FakeInstance(f"c{i % 10:040x}") for i in range(200)]
    result = choose_strategy(insts)
    assert result["strategy"] == "per_base_commit"
    assert result["distinct_commits"] == 10
    assert result["consolidation_ratio"] > 0.15


# --- offset transforms ----------------------------------------------------

def test_offset_node_row_shifts_id_sid_and_file_id():
    row = {"label": "Function", "id": 5, "sid": "5", "name": "f", "file_id": 2}
    out = offset_node_row(row, 100_000_000)
    assert out["id"] == 100_000_005
    assert out["sid"] == "100000005"
    assert out["file_id"] == 100_000_002
    # original untouched (pure)
    assert row["id"] == 5


def test_offset_node_row_file_without_file_id():
    row = {"label": "File", "id": 3, "sid": "3", "path": "a.py"}
    out = offset_node_row(row, 100_000_000)
    assert out["id"] == 100_000_003
    assert out["sid"] == "100000003"
    assert "file_id" not in out


def test_offset_node_row_handles_none_file_id():
    row = {"label": "Function", "id": 1, "sid": "1", "file_id": None}
    out = offset_node_row(row, 50)
    assert out["file_id"] is None
    assert out["id"] == 51


def test_offset_edge_row_shifts_both_endpoints():
    row = {"src": 4, "dst": 9, "type": "CALLS", "weight": 1}
    out = offset_edge_row(row, 100_000_000)
    assert out["src"] == 100_000_004
    assert out["dst"] == 100_000_009
    assert out["type"] == "CALLS"
    assert row["src"] == 4  # pure


def test_offset_disjoint_bands_never_collide():
    # Two instances, id 5 in each, must map to different global ids.
    a = offset_node_row({"id": 5, "sid": "5"}, instance_base(0))
    b = offset_node_row({"id": 5, "sid": "5"}, instance_base(1))
    assert a["id"] != b["id"]

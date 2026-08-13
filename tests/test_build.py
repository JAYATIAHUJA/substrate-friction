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
    _apply_command_sequence,
    apply_test_patch,
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


# --- test_patch application (pure: command selection + failure handling) ---

_PATCH = "diff --git a/tests/t.py b/tests/t.py\n--- a/tests/t.py\n+++ b/tests/t.py\n"


def test_apply_command_sequence_is_git_first_then_3way_then_patch():
    cmds = _apply_command_sequence("/repo")
    assert len(cmds) == 3
    # Every command targets the given repo root.
    assert all("/repo" in c for c in cmds)
    # git apply (strict) is tried first.
    assert cmds[0][:5] == ["git", "-C", "/repo", "apply", "--whitespace=nowarn"]
    # git apply --3way is the second fallback.
    assert "--3way" in cmds[1] and cmds[1][3] == "apply"
    # patch -p1 is the last resort.
    assert cmds[2][0] == "patch" and "-p1" in cmds[2]


def test_apply_command_sequence_reads_patch_from_stdin():
    cmds = _apply_command_sequence("/repo")
    # The two git commands read the patch from stdin (trailing '-').
    assert cmds[0][-1] == "-"
    assert cmds[1][-1] == "-"


def test_apply_test_patch_empty_returns_false_without_running():
    calls = []

    def runner(cmd, text):
        calls.append(cmd)
        return 0

    assert apply_test_patch("/repo", "", runner=runner) is False
    assert apply_test_patch("/repo", "   \n  ", runner=runner) is False
    assert calls == []  # never invoked a command for a blank patch


def test_apply_test_patch_first_command_succeeds_stops_early():
    calls = []

    def runner(cmd, text):
        calls.append(cmd)
        return 0  # first attempt succeeds

    assert apply_test_patch("/repo", _PATCH, runner=runner) is True
    assert len(calls) == 1  # did not try the fallbacks


def test_apply_test_patch_falls_back_through_the_sequence():
    calls = []

    def runner(cmd, text):
        calls.append(cmd)
        # git apply fails, git apply --3way fails, patch -p1 succeeds.
        return 0 if cmd[0] == "patch" else 1

    assert apply_test_patch("/repo", _PATCH, runner=runner) is True
    assert len(calls) == 3


def test_apply_test_patch_all_commands_fail_returns_false():
    calls = []

    def runner(cmd, text):
        calls.append(cmd)
        return 1  # everything fails

    assert apply_test_patch("/repo", _PATCH, runner=runner) is False
    assert len(calls) == 3  # exhausted the whole sequence


def test_apply_test_patch_feeds_patch_text_to_runner():
    seen = []

    def runner(cmd, text):
        seen.append(text)
        return 0

    apply_test_patch("/repo", _PATCH, runner=runner)
    assert seen == [_PATCH]


# --- real-clone roundtrip (needs the django clone) ------------------------

@pytest.mark.engine
def test_apply_test_patch_roundtrip_on_real_clone(tmp_path):
    """A real django test_patch applies cleanly and _restore fully reverts it.

    Marked engine because it needs the on-disk django clone; it does not touch
    the graph engine, but shares the "needs real repo state" precondition.
    """
    import subprocess
    from pathlib import Path

    from friction.build import _checkout, _restore, apply_test_patch
    from friction.swebench import load_instances

    repo_root = Path("data/repos/django")
    if not (repo_root / ".git").exists():
        pytest.skip("django clone not present")

    inst = next(i for i in load_instances(repos=["django/django"]))
    try:
        _restore(repo_root)
        _checkout(repo_root, inst.base_commit)
        assert apply_test_patch(repo_root, inst.test_patch) is True
        # The tree is now dirty (the test_patch touched tracked/new files).
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True, text=True).stdout
        assert dirty.strip() != ""
    finally:
        _restore(repo_root)

    clean = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True).stdout
    assert clean.strip() == ""  # fully restored

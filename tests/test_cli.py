"""The two-arm CLI. `compare` is the primary command and the demo; every test
here runs against the committed cache (arms/manifest.jsonl + arms/path_stats.json)
via a stub fixture, so no engine is needed. Anything that would touch a live node
is marked @pytest.mark.engine.

The project's headline is the SUBSTRATE finding (what name matching costs), and
the honest secondary result is a scoped NO-GO. So the tests assert that both arms
render side by side with their Cypher and latency, that an arm the engine could
not answer renders a clean "could not answer" line and NEVER a fabricated score,
and that every friction number carries the f1/path-multiplicity-only qualifier.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from friction import cli

# --------------------------------------------------------------------------
# fixtures: a two-instance cache, one with both arms answered, one with arm B
# engine-unanswerable (timeout) — the two shapes the demo must handle.
# --------------------------------------------------------------------------

BOTH = "test__both-1"
BTIMEOUT = "test__btimeout-1"

_MANIFEST = [
    {"instance_id": BOTH, "comparable": True,
     "arm_a": {"nodes": 13429, "edges": 19506, "band": 10050000000,
               "fix_site_ids": [10050001, 10050002],
               "test_target_ids": [10050100, 10050101, 10050102, 10050103]},
     "arm_b": {"nodes": 27866, "edges": 78382, "band": 20050000000,
               "fix_site_ids": [20050001, 20050002],
               "test_target_ids": [20050100, 20050101, 20050102, 20050103]}},
    {"instance_id": BTIMEOUT, "comparable": True,
     "arm_a": {"nodes": 13614, "edges": 19815, "band": 10060000000,
               "fix_site_ids": [10060001, 10060002],
               "test_target_ids": [10060100, 10060101]},
     "arm_b": {"nodes": 28225, "edges": 79447, "band": 20060000000,
               "fix_site_ids": [20060001, 20060002, 20060003],
               "test_target_ids": [20060100, 20060101]}},
]

_PATH_STATS = {
    "summary": {"n_comparable": 2, "max_len": 6},
    "per_instance": {
        BOTH: {"comparable": True,
               "arm_a": {"paths": 8, "millis": 5.24, "truncated": False,
                         "answered": True},
               "arm_b": {"paths": 36, "millis": 10.29, "truncated": True,
                         "answered": True}},
        BTIMEOUT: {"comparable": True,
                   "arm_a": {"paths": 80, "millis": 22.78, "truncated": True,
                             "answered": True},
                   "arm_b": {"paths": 0, "millis": 30015.5, "truncated": False,
                             "answered": False,
                             "error": "{neo4j_code: Neo.ClientError.Transaction."
                                      "Terminated} {message: native_path_neighbors "
                                      "exceeded query timeout after 29999 ms}"}},
    },
}

_OOM = ("{neo4j_code: Neo.TransientError.General.MemoryPoolOutOfMemoryError} "
        "{message: native_path_frontier_paths rejected by admission control: "
        "actual 250001 exceeds limit 250000}")


def _cache(tmp_path: Path) -> tuple[Path, Path]:
    man = tmp_path / "manifest.jsonl"
    man.write_text("\n".join(json.dumps(r) for r in _MANIFEST), encoding="utf-8")
    stats = tmp_path / "path_stats.json"
    stats.write_text(json.dumps(_PATH_STATS), encoding="utf-8")
    return man, stats


def _compare(tmp_path: Path, iid: str):
    man, stats = _cache(tmp_path)
    return cli.compare(iid, manifest_path=man, path_stats_path=stats,
                       caps=cli._DEFAULT_CAPS)


# --------------------------------------------------------------------------
# compare — both arms answered
# --------------------------------------------------------------------------

def test_compare_returns_both_arms(tmp_path):
    a, b, comparable = _compare(tmp_path, BOTH)
    assert a.arm == "A" and b.arm == "B"
    assert comparable is True
    assert a.answered and b.answered


def test_compare_output_shows_both_arms(tmp_path):
    a, b, cmp = _compare(tmp_path, BOTH)
    text = cli.render_compare(a, b, BOTH, cmp)
    assert "ARM A" in text and "ARM B" in text
    assert "name-matched" in text and "type-resolved" in text


def test_compare_prints_cypher_and_latency_for_each_arm(tmp_path):
    a, b, cmp = _compare(tmp_path, BOTH)
    text = cli.render_compare(a, b, BOTH, cmp)
    # the exact algo.MSpaths query, once per arm
    assert text.count("algo.MSpaths") >= 2
    # each arm's measured latency is surfaced
    assert "5.24" in text     # arm A ms
    assert "10.29" in text    # arm B ms


def test_compare_cypher_carries_each_arms_own_endpoint_ids(tmp_path):
    a, b, _ = _compare(tmp_path, BOTH)
    # arm A band ids appear in arm A's cypher, arm B band ids in arm B's
    assert "'10050001'" in a.cypher and "'10050100'" in a.cypher
    assert "'20050001'" in b.cypher and "'20050100'" in b.cypher


def test_compare_computes_f1_path_multiplicity(tmp_path):
    a, b, _ = _compare(tmp_path, BOTH)
    # arm A: 8 paths / (2 fix * 4 test) = 1.0 ; arm B: 36 / 8 = 4.5
    assert a.f1 == pytest.approx(1.0)
    assert b.f1 == pytest.approx(4.5)


def test_compare_labels_every_friction_number_as_f1_only(tmp_path):
    a, b, cmp = _compare(tmp_path, BOTH)
    text = cli.render_compare(a, b, BOTH, cmp)
    assert "f1 / path-multiplicity only" in text


def test_compare_flags_pathcount_truncation(tmp_path):
    a, b, cmp = _compare(tmp_path, BOTH)
    text = cli.render_compare(a, b, BOTH, cmp)
    assert b.truncated is True
    assert "truncated" in text.lower()


def test_compare_surfaces_the_precision_ceiling(tmp_path):
    a, b, cmp = _compare(tmp_path, BOTH)
    text = cli.render_compare(a, b, BOTH, cmp)
    assert "0.746" in text


# --------------------------------------------------------------------------
# compare — arm B engine-unanswerable
# --------------------------------------------------------------------------

def test_compare_unanswered_arm_has_no_score(tmp_path):
    a, b, _ = _compare(tmp_path, BTIMEOUT)
    assert a.answered is True
    assert b.answered is False
    assert b.f1 is None
    assert b.error_kind == "timeout"


def test_compare_unanswered_arm_renders_clean_line_not_a_score(tmp_path):
    a, b, cmp = _compare(tmp_path, BTIMEOUT)
    text = cli.render_compare(a, b, BTIMEOUT, cmp)
    assert "could not answer" in text.lower()
    assert "timeout" in text.lower()
    assert "maxLen 6" in text
    # it must not fabricate an f1 for the arm it never scored: only arm A's f1
    # value (20.000) should appear, never a made-up arm B number
    assert "not scored" in text.lower()


def test_compare_unanswered_arm_still_shows_the_attempted_cypher(tmp_path):
    a, b, cmp = _compare(tmp_path, BTIMEOUT)
    text = cli.render_compare(a, b, BTIMEOUT, cmp)
    # even the arm that timed out shows the query that was issued and gave up
    assert b.cypher != ""
    assert "algo.MSpaths" in b.cypher
    assert "30,015" in text           # the latency at which it gave up


def test_compare_delta_notes_density_paradox_when_arm_b_unanswerable(tmp_path):
    a, b, cmp = _compare(tmp_path, BTIMEOUT)
    text = cli.render_compare(a, b, BTIMEOUT, cmp)
    assert "density paradox" in text.lower()
    assert "not computed" in text.lower()


def test_classify_error_distinguishes_timeout_from_memory_pool():
    assert cli._classify_error(_OOM) == "memory pool"
    assert cli._classify_error("exceeded query timeout after 29999 ms") == "timeout"
    assert cli._classify_error("") == ""


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------

def test_list_rows_carry_per_arm_counts_and_answerability(tmp_path):
    man, stats = _cache(tmp_path)
    rows = cli._list_rows(manifest_path=man, path_stats_path=stats)
    by_id = {r["instance_id"]: r for r in rows}
    assert by_id[BOTH]["arm_a"]["nodes"] == 13429
    assert by_id[BOTH]["arm_b"]["edges"] == 78382
    assert by_id[BTIMEOUT]["arm_b"]["answered"] is False
    assert by_id[BTIMEOUT]["arm_b"]["status"] == "timeout"


def test_render_list_shows_both_arms_and_answerability(tmp_path):
    man, stats = _cache(tmp_path)
    rows = cli._list_rows(manifest_path=man, path_stats_path=stats)
    text = cli.render_list(rows)
    assert "A nodes" in text and "B nodes" in text
    assert "timeout" in text
    assert BOTH in text and BTIMEOUT in text


# --------------------------------------------------------------------------
# data-path fallback (v1 shipped a bug exactly here)
# --------------------------------------------------------------------------

def test_arms_path_prefers_working_build(monkeypatch, tmp_path):
    working = tmp_path / "data" / "instances" / "arms"
    working.mkdir(parents=True)
    (working / "manifest.jsonl").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli._arms_path("manifest.jsonl") == Path("data/instances/arms/manifest.jsonl")


def test_arms_path_falls_back_to_shipped_when_instances_absent(monkeypatch, tmp_path):
    shipped = tmp_path / "data" / "shipped" / "arms"
    shipped.mkdir(parents=True)
    (shipped / "manifest.jsonl").write_text("", encoding="utf-8")
    # no data/instances/arms present
    monkeypatch.chdir(tmp_path)
    assert cli._arms_path("manifest.jsonl") == Path("data/shipped/arms/manifest.jsonl")


def test_shipped_cache_exists_so_a_clean_clone_can_run_compare():
    # the committed fallback payload a judge's clone relies on
    assert Path("data/shipped/arms/manifest.jsonl").exists()
    assert Path("data/shipped/arms/path_stats.json").exists()


# --------------------------------------------------------------------------
# main / subcommands
# --------------------------------------------------------------------------

def test_main_returns_nonzero_on_unknown_subcommand():
    assert cli.main(["nonsense"]) != 0


def test_main_no_subcommand_returns_nonzero():
    assert cli.main([]) != 0


def test_main_unknown_issue_returns_nonzero(tmp_path, capsys):
    man, stats = _cache(tmp_path)
    rc = cli.main(["compare", "--issue", "does__not-exist",
                   "--manifest", str(man), "--path-stats", str(stats)])
    assert rc == 1


def test_main_compare_prints_both_arms(tmp_path, capsys):
    man, stats = _cache(tmp_path)
    rc = cli.main(["compare", "--issue", BOTH,
                   "--manifest", str(man), "--path-stats", str(stats)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ARM A" in out and "ARM B" in out
    assert "f1 / path-multiplicity only" in out


def test_main_delta_prints_the_offender_table(capsys):
    rc = cli.main(["delta"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "0.746" in out            # the precision ceiling
    assert "extend" in out           # the worst offender family


def test_main_eval_prints_the_scoped_no_go(capsys):
    rc = cli.main(["eval"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NO-GO" in out
    assert "0.631" in out            # arm A f1 AUC, the honest null


def test_main_list_shows_instances_and_answerability(capsys):
    rc = cli.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "django__django-" in out
    assert "A nodes" in out and "B nodes" in out

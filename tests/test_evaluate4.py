import json
from pathlib import Path

import pytest

from friction import evaluate4
from friction.evaluate4 import (
    Row,
    baseline_aucs,
    bootstrap_ci,
    build_rows,
    feature_aucs,
    write_report,
)

SYSTEM = "sys_primary"


def _write_instance(arms_root: Path, iid: str, arm: str, edges):
    d = arms_root / iid / arm
    d.mkdir(parents=True, exist_ok=True)
    with (d / "edges.ndjson").open("w") as fh:
        for src, dst in edges:
            fh.write(json.dumps({"src": src, "dst": dst, "type": "CALLS"}) + "\n")


def _fake_corpus(tmp_path: Path):
    """Two instances: one where test -> fix is directed-connected, one where the
    edge points the wrong way. Both carry both endpoints."""
    arms_root = tmp_path / "arms"
    manifest = tmp_path / "manifest.jsonl"
    annotations = tmp_path / "annotations.json"

    # inst A: test(30) -> fix(20), a directed chain; failed
    _write_instance(arms_root, "proj__proj-1", "arm_b",
                    [(30, 31), (31, 20), (20, 21)])
    # inst B: fix(20) -> test(30), wrong way; resolved
    _write_instance(arms_root, "proj__proj-2", "arm_b",
                    [(20, 30), (30, 31)])

    records = [
        {"instance_id": "proj__proj-1",
         "arm_b": {"fix_site_ids": [20], "test_target_ids": [30]}},
        {"instance_id": "proj__proj-2",
         "arm_b": {"fix_site_ids": [20], "test_target_ids": [30]}},
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    ann = {
        "proj__proj-1": {"instance_id": "proj__proj-1", "patch_lines": 40,
                         "failed": {SYSTEM: True}},
        "proj__proj-2": {"instance_id": "proj__proj-2", "patch_lines": 3,
                         "failed": {SYSTEM: False}},
    }
    annotations.write_text(json.dumps(ann))
    return manifest, annotations, arms_root


def test_rows_build_from_fake_manifest_and_annotations(tmp_path):
    manifest, annotations, arms_root = _fake_corpus(tmp_path)
    rows = build_rows(manifest, annotations, arms_root, arm="arm_b", instances=[])
    assert len(rows) == 2
    by_id = {r.instance_id: r for r in rows}
    assert set(by_id) == {"proj__proj-1", "proj__proj-2"}

    a = by_id["proj__proj-1"]
    assert isinstance(a, Row)
    # features are the directional feature dict
    assert "fwd_growth" in a.features
    assert "test_to_fix_hops" in a.features
    # inst A has a directed test->fix path, inst B does not
    assert a.features["test_to_fix_hops"] >= 1
    assert by_id["proj__proj-2"].features["test_to_fix_hops"] == -1
    # labels carried through
    assert a.failed[SYSTEM] is True
    assert by_id["proj__proj-2"].failed[SYSTEM] is False
    # baselines fell back to annotations patch_lines (no swebench instances given)
    assert a.baselines.get("patch_lines") == 40.0


def test_auc_orientation_is_failed_positive():
    # A feature that increases with failure must score AUC > 0.5.
    rows = [
        Row("i1", {"x": 0.0}, {SYSTEM: False}, {"b": 0.0}),
        Row("i2", {"x": 1.0}, {SYSTEM: False}, {"b": 1.0}),
        Row("i3", {"x": 2.0}, {SYSTEM: True}, {"b": 2.0}),
        Row("i4", {"x": 3.0}, {SYSTEM: True}, {"b": 3.0}),
    ]
    f = feature_aucs(rows, SYSTEM)
    assert f["x"] == pytest.approx(1.0)
    b = baseline_aucs(rows, SYSTEM)
    assert b["b"] == pytest.approx(1.0)


def test_bootstrap_ci_brackets_the_point_estimate():
    rows = [
        Row("i1", {"x": 0.0}, {SYSTEM: False}, {"b": 3.0}),
        Row("i2", {"x": 1.0}, {SYSTEM: False}, {"b": 2.0}),
        Row("i3", {"x": 2.0}, {SYSTEM: True}, {"b": 1.0}),
        Row("i4", {"x": 3.0}, {SYSTEM: True}, {"b": 0.0}),
        Row("i5", {"x": 1.5}, {SYSTEM: True}, {"b": 1.5}),
        Row("i6", {"x": 0.5}, {SYSTEM: False}, {"b": 2.5}),
    ]
    point, lo, hi = bootstrap_ci(rows, SYSTEM, "x", "b", n=500, seed=0)
    assert lo <= point <= hi
    # x tracks failure, b is anti-correlated, so the difference is positive
    assert point > 0


def test_report_carries_retractions_caveat_and_published_marker(tmp_path):
    rows = [
        Row("i1", {"fwd_growth": 1.0}, {SYSTEM: False}, {"patch_lines": 1.0}),
        Row("i2", {"fwd_growth": 2.0}, {SYSTEM: True}, {"patch_lines": 2.0}),
    ]
    results = {
        "system": SYSTEM,
        "arm": "arm_b",
        "feature_aucs": feature_aucs(rows, SYSTEM),
        "baseline_aucs": baseline_aucs(rows, SYSTEM),
        "class_balance": {"n": 2, "failed": 1, "resolved": 1},
        "bootstrap": {"fwd_growth": (0.0, -0.5, 0.5)},
        "bootstrap_baseline": "patch_lines",
        "best_feature": ("fwd_growth", 1.0),
        "best_baseline": ("patch_lines", 1.0),
    }
    path = tmp_path / "evaluation.md"
    write_report(rows, results, path)
    text = path.read_text()

    # Both retractions, by their numbers
    assert "0.565" in text
    assert "0.726" in text
    assert "0.631" in text
    assert "0.637" in text
    assert "WITHDRAWN" in text
    # Directional caveat
    assert "shares a neighbourhood" in text
    assert "relDirection" in text
    # Published rows, clearly marked
    assert "published, NOT reproduced" in text
    assert "0.718" in text
    assert "0.787" in text
    assert "0.841" in text
    # Contamination disclosure
    assert "32.7%" in text
    assert "59.4%" in text


def test_report_states_scoped_no_go_when_no_feature_beats_baseline(tmp_path):
    rows = [Row("i1", {"fwd_growth": 1.0}, {SYSTEM: False}, {"patch_lines": 1.0}),
            Row("i2", {"fwd_growth": 2.0}, {SYSTEM: True}, {"patch_lines": 2.0})]
    results = {
        "system": SYSTEM, "arm": "arm_b",
        "feature_aucs": {"fwd_growth": 0.44},
        "baseline_aucs": {"patch_lines": 0.65},
        "class_balance": {"n": 2, "failed": 1, "resolved": 1},
        "bootstrap": {"fwd_growth": (-0.2, -0.5, 0.1)},
        "bootstrap_baseline": "patch_lines",
        "best_feature": ("fwd_growth", 0.44),
        "best_baseline": ("patch_lines", 0.65),
    }
    path = tmp_path / "evaluation.md"
    write_report(rows, results, path)
    text = path.read_text()
    assert "NO-GO" in text
    assert "No feature beats the best baseline" in text


def test_report_states_the_sample_cannot_resolve_small_effects(tmp_path):
    rows = [Row("i1", {"fwd_growth": 1.0}, {SYSTEM: False}, {"patch_lines": 1.0}),
            Row("i2", {"fwd_growth": 2.0}, {SYSTEM: True}, {"patch_lines": 2.0})]
    results = {
        "system": SYSTEM, "arm": "arm_b",
        "feature_aucs": feature_aucs(rows, SYSTEM),
        "baseline_aucs": baseline_aucs(rows, SYSTEM),
        "class_balance": {"n": 2, "failed": 1, "resolved": 1},
        "bootstrap": {"fwd_growth": (0.0, -0.5, 0.5)},
        "bootstrap_baseline": "patch_lines",
        "best_feature": ("fwd_growth", 1.0),
        "best_baseline": ("patch_lines", 1.0),
    }
    path = tmp_path / "evaluation.md"
    write_report(rows, results, path)
    text = path.read_text().lower()
    assert "cannot resolve" in text


# --------------------------------------------------------------------------
# Corpus frame: labels derived from resolved sets, repo carried, arm files
# resolved by the record's `source` (carried vs built).
# --------------------------------------------------------------------------

def _fake_multirepo_corpus(tmp_path: Path):
    carried = tmp_path / "carried"
    built = tmp_path / "built"
    resolved = tmp_path / "resolved"
    resolved.mkdir()
    manifest = tmp_path / "manifest.jsonl"

    # django (carried) reachable test->fix; sphinx (built) not reachable.
    _write_instance(carried, "django__django-1", "arm_b",
                    [(30, 31), (31, 20), (20, 21)])
    _write_instance(built, "sphinx-doc__sphinx-1", "arm_b",
                    [(20, 30), (30, 31)])
    # a usable-but-empty-endpoint record must be dropped.
    _write_instance(built, "sphinx-doc__sphinx-2", "arm_b", [(1, 2)])

    records = [
        {"instance_id": "django__django-1", "repo": "django", "source": "carried",
         "arm_b": {"fix_site_ids": [20], "test_target_ids": [30]}},
        {"instance_id": "sphinx-doc__sphinx-1", "repo": "sphinx", "source": "built",
         "arm_b": {"fix_site_ids": [20], "test_target_ids": [30]}},
        {"instance_id": "sphinx-doc__sphinx-2", "repo": "sphinx", "source": "built",
         "arm_b": {"fix_site_ids": [], "test_target_ids": [30]}},
    ]
    manifest.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    # resolved set: django-1 resolved (=> failed False); sphinx-1 absent
    # (=> failed True).
    (resolved / f"{SYSTEM}.json").write_text(
        json.dumps({"resolved": ["django__django-1"]}))
    return manifest, carried, built, resolved


def test_derive_failed_labels_from_resolved_sets(tmp_path):
    resolved = tmp_path / "resolved"
    resolved.mkdir()
    (resolved / "sysA.json").write_text(json.dumps({"resolved": ["a", "c"]}))
    labels = evaluate4.derive_failed_labels(["a", "b", "c"], ["sysA"], resolved)
    assert labels["a"]["sysA"] is False   # resolved -> not failed
    assert labels["b"]["sysA"] is True    # absent -> failed
    assert labels["c"]["sysA"] is False


def test_build_corpus_rows_labels_all_usable_and_carries_repo(tmp_path):
    manifest, carried, built, resolved = _fake_multirepo_corpus(tmp_path)
    rows = evaluate4.build_corpus_rows(
        manifest, [SYSTEM], carried_root=carried, built_root=built,
        resolved_dir=resolved, instances=[])
    by_id = {r.instance_id: r for r in rows}
    # the empty-endpoint sphinx-2 is dropped; the other two are kept.
    assert set(by_id) == {"django__django-1", "sphinx-doc__sphinx-1"}
    # repo carried through
    assert by_id["django__django-1"].repo == "django"
    assert by_id["sphinx-doc__sphinx-1"].repo == "sphinx"
    # labels derived from the resolved set (django resolved, sphinx failed)
    assert by_id["django__django-1"].failed[SYSTEM] is False
    assert by_id["sphinx-doc__sphinx-1"].failed[SYSTEM] is True
    # arm files resolved from the right base dir per source -> real features
    assert by_id["django__django-1"].features["test_to_fix_hops"] >= 1
    assert by_id["sphinx-doc__sphinx-1"].features["test_to_fix_hops"] == -1


def test_rows_to_frame_has_features_repo_and_label(tmp_path):
    manifest, carried, built, resolved = _fake_multirepo_corpus(tmp_path)
    rows = evaluate4.build_corpus_rows(
        manifest, [SYSTEM], carried_root=carried, built_root=built,
        resolved_dir=resolved, instances=[])
    frame = evaluate4.rows_to_frame(rows, SYSTEM)
    assert len(frame) == 2
    assert "repo" in frame.columns
    assert "failed" in frame.columns
    assert "test_to_fix_hops" in frame.columns
    assert set(frame["repo"]) == {"django", "sphinx"}

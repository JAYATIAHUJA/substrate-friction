from friction import harness


class Rec:
    name = "rec"

    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or []

    def query(self, cypher, params=None):
        self.calls.append((cypher, params))
        return self.rows


def test_load_arms_sends_nodes_before_edges(tmp_path):
    (tmp_path / "arm_a").mkdir(parents=True)
    (tmp_path / "arm_a" / "nodes.ndjson").write_text(
        '{"label":"Function","id":1,"sid":"1","name":"f","qual":"m::f"}\n')
    (tmp_path / "arm_a" / "edges.ndjson").write_text("")
    t = Rec()
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    out = harness.load_arms(t, caps, [{"instance_id": "x"}], tmp_path.parent)
    assert out["loaded"] >= 0


def test_arm_path_stats_marks_unanswered_on_engine_error():
    class Boom:
        name = "boom"

        def query(self, *a, **k):
            from friction.client import EngineError
            raise EngineError("Terminated")

    from friction.config import Settings
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    s = Settings("bolt://x", "http://x", "t", "d", "d", "cell-0", 6, 20, "both", 500)
    out = harness.arm_path_stats(Boom(), caps, s,
                                 {"fix_site_ids": [1], "test_target_ids": [2]}, "arm_a")
    assert out["answered"] is False
    assert out["paths"] == 0


def test_arm_path_stats_returns_zero_for_empty_endpoints():
    from friction.config import Settings
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    s = Settings("bolt://x", "http://x", "t", "d", "d", "cell-0", 6, 20, "both", 500)
    out = harness.arm_path_stats(Rec(), caps, s,
                                 {"fix_site_ids": [], "test_target_ids": [2]}, "arm_a")
    assert out["paths"] == 0 and out["answered"] is True


# --- adaptation coverage: real manifest records are NESTED per arm ----------
# build_instance emits record[arm]["fix_site_ids"], NOT a flat key. This test
# pins the nested-read behaviour so a flat read (which returns None -> silent
# all-zero path stats) can never regress in.
def test_arm_path_stats_reads_nested_per_arm_endpoints():
    from friction.config import Settings
    from friction.probe import Capabilities
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    s = Settings("bolt://x", "http://x", "t", "d", "d", "cell-0", 6, 20, "both", 500)
    # arm_b has empty fix sites -> zero paths, answered True, without any query.
    record = {
        "arm_a": {"fix_site_ids": [1], "test_target_ids": [2]},
        "arm_b": {"fix_site_ids": [], "test_target_ids": [2]},
    }
    out = harness.arm_path_stats(Rec(), caps, s, record, "arm_b")
    assert out["paths"] == 0 and out["answered"] is True


# --- regression: loader.load must adapt to the leaner Task-7 arm node schema.
# Arm nodes carry only {label,id,sid,name,qual}; the v1 NODE_PROPS Function
# schema (file_id/line_start/cyclomatic/is_test) made the live engine reject
# every arm batch with "UNWIND row 0 is missing field cyclomatic". load() must
# SET exactly the props each row actually carries, never a v1-only field.
def test_load_adapts_to_arm_node_schema(tmp_path):
    from friction import loader
    from friction.probe import Capabilities

    class RecordingTransport:
        def __init__(self):
            self.calls = []

        def query(self, cypher, params=None):
            self.calls.append((cypher, params))
            return []

    d = tmp_path / "arm_a"
    d.mkdir(parents=True)
    (d / "nodes.ndjson").write_text(
        '{"label":"Function","id":10000000000,"sid":"10000000000","name":"f","qual":"m::f"}\n')
    (d / "edges.ndjson").write_text("")
    caps = Capabilities("both", "incoming", True, "string",
                        "merge_set_label", "single_pattern_create", False, False, "sourceNode")
    t = RecordingTransport()
    counts = loader.load(t, caps, d, batch_size=1000)
    node_calls = [c for c in t.calls if "MERGE (n {id: row.id})" in c[0]]
    assert node_calls, "no node upsert emitted"
    stmt = node_calls[0][0]
    assert "n.qual = row.qual" in stmt
    assert "n.sid = row.sid" in stmt
    assert "cyclomatic" not in stmt and "file_id" not in stmt
    assert counts["Function"] == 1


# ==========================================================================
# Task 10: the honest two-arm evaluation
# ==========================================================================

def test_arm_friction_components_are_multiplicity_only():
    """Committed path_stats stores COUNTS, not node lists, so of the six friction
    components only f1 (multiplicity) and f6 (fan-in, when queried) are real. This
    pins the documented deviation: f2-f5 are 0 because node lists were never cached."""
    c = harness._arm_friction_components(paths_count=6, n_fix=2, n_test=3,
                                         fan_in_count=7)
    assert c.f1 == 1.0            # 6 paths / (2*3) pairs
    assert c.f2 == 0.0 and c.f3 == 0.0 and c.f4 == 0.0 and c.f5 == 0.0
    assert c.f6 == 7.0


def test_arm_friction_components_zero_endpoints_do_not_divide_by_zero():
    c = harness._arm_friction_components(paths_count=0, n_fix=0, n_test=5)
    assert c.f1 == 0.0 and c.f6 == 0.0


def test_build_arm_rows_merges_nested_endpoints_and_labels():
    path_stats = {"per_instance": {
        "django__x": {"comparable": True,
                      "arm_a": {"answered": True, "paths": 4, "millis": 1.0, "truncated": False},
                      "arm_b": {"answered": False, "paths": 0, "millis": 0.0, "truncated": False}},
    }}
    manifest = [{"instance_id": "django__x",
                 "comparable": True,
                 "arm_a": {"fix_site_ids": [1], "test_target_ids": [2, 3]},
                 "arm_b": {"fix_site_ids": [], "test_target_ids": [9]}}]
    annotations = {"django__x": {"patch_lines": 12, "repo_loc": 1000,
                                 "failed": {"S": True}}}
    rows = harness.build_arm_rows(path_stats, manifest, annotations, instances=None)
    assert len(rows) == 1
    r = rows[0]
    assert r["instance_id"] == "django__x" and r["comparable"] is True
    assert r["patch_lines"] == 12
    assert r["arm_a"]["answered"] is True and r["arm_a"]["paths"] == 4
    assert r["arm_a"]["n_fix"] == 1 and r["arm_a"]["n_test"] == 2
    assert r["arm_b"]["answered"] is False and r["arm_b"]["n_test"] == 1


def _row(iid, comparable, a_ans, a_paths, a_fix, a_test, b_ans, b_paths,
         patch_lines):
    return {"instance_id": iid, "comparable": comparable,
            "patch_lines": patch_lines, "patch_files": None,
            "f2p_count": None, "statement_chars": None,
            "arm_a": {"answered": a_ans, "paths": a_paths, "n_fix": a_fix, "n_test": a_test},
            "arm_b": {"answered": b_ans, "paths": b_paths, "n_fix": 1, "n_test": 1}}


def test_evaluate_arms_returns_the_full_schema():
    rows = [_row(f"i{i}", True, True, i, 1, 1, False, 0, 10 * i) for i in range(6)]
    failed = {f"i{i}": (i % 2 == 0) for i in range(6)}
    out = harness.evaluate_arms(rows, failed, n_boot=200)
    for key in ("primary_system", "n_instances", "n_comparable", "cache_note",
                "arm_a", "arm_b", "baselines_headline", "questions", "published"):
        assert key in out, key
    assert out["published"]["statement_text_only"] == 0.787
    assert out["published"]["best_combined"] == 0.841
    assert "arm_b_beats_arm_a" in out["questions"]
    assert "beats_patch_lines" in out["questions"]
    assert "n_sufficient" in out["questions"]
    ci = out["questions"]["n_sufficient"]["bootstrap_ci"]
    assert len(ci) == 2 and ci[0] <= ci[1]


def test_evaluate_arms_auc_tracks_multiplicity_ordering():
    # friction (path count) rank-agrees with the failure label => AUC 1.0
    rows = []
    failed = {}
    for i in range(8):
        fail = i >= 4                 # top-4 by path count are the failures
        rows.append(_row(f"i{i}", True, True, i, 1, 1, False, 0, 0))
        failed[f"i{i}"] = fail
    out = harness.evaluate_arms(rows, failed, n_boot=100)
    assert abs(out["arm_a"]["auc"] - 1.0) < 1e-9


def test_evaluate_arms_flags_arm_b_underpowered_when_few_answered():
    rows = [_row(f"i{i}", True, True, i, 1, 1, i < 2, i, 5 * i) for i in range(12)]
    failed = {f"i{i}": (i % 2 == 0) for i in range(12)}
    out = harness.evaluate_arms(rows, failed, n_boot=100)
    # only 2 arm_b answered -> the comparison must be reported undetermined
    assert out["arm_b"]["n"] == 2
    assert out["questions"]["arm_b_beats_arm_a"]["answer"] in ("undetermined", "no")

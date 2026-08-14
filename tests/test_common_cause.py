from friction import common_cause as cc


PATHS = {
    "i1": [[1, 99, 3]],
    "i2": [[4, 99, 6]],
    "i3": [[7, 8, 9]],
    "i4": [[10, 99, 12]],
}


def test_tally_counts_instances_not_paths():
    counts = cc.tally({"i1": [[1, 99, 3], [1, 99, 4]]})
    assert counts[99] == 1


def test_tally_excludes_endpoints():
    counts = cc.tally({"i1": [[1, 99, 3]]})
    assert 1 not in counts and 3 not in counts


def test_rank_puts_the_common_node_first():
    ranked = cc.rank(cc.tally(PATHS))
    assert ranked[0][0] == 99
    assert ranked[0][1] == 3


def test_validate_reports_hit_rate_on_held_out():
    train = {k: PATHS[k] for k in ("i1", "i2")}
    held = {k: PATHS[k] for k in ("i3", "i4")}
    out = cc.validate(train, held, top_n=1)
    assert out["held_out_hit_rate"] == 0.5


def test_bootstrap_ci_returns_ordered_bounds():
    low, high = cc.bootstrap_ci(PATHS, 99, trials=200, seed=1)
    assert 0.0 <= low <= high <= 1.0

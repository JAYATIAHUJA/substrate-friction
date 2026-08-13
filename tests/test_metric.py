import pytest

from friction import metric
from friction.paths import PathSet


def ps(paths, costs=None):
    return PathSet(paths, costs or [float(len(p) - 1) for p in paths], "c", 1.0, False)


def test_f1_is_path_count_normalised_by_pairs():
    c = metric.raw_components(ps([[1, 2, 3], [1, 4, 3]]), [1], [3], 0)
    assert c.f1 == 2.0  # 2 paths / 1 pair


def test_f2_is_mean_hop_count():
    c = metric.raw_components(ps([[1, 2, 3], [1, 2, 3, 4]]), [1], [3], 0)
    assert c.f2 == pytest.approx(2.5)  # hops 2 and 3


def test_f3_counts_distinct_intermediates_only():
    c = metric.raw_components(ps([[1, 2, 3], [1, 4, 3]]), [1], [3], 0)
    assert c.f3 == 2.0  # nodes 2 and 4; endpoints excluded


def test_f4_convergence_ratio_is_distinct_over_total():
    c = metric.raw_components(ps([[1, 2, 3], [1, 2, 3]]), [1], [3], 0)
    assert c.f4 == pytest.approx(0.5)  # 1 distinct intermediate / 2 occurrences


def test_f5_detects_repeated_node_within_a_path():
    c = metric.raw_components(ps([[1, 2, 1, 3]]), [1], [3], 0)
    assert c.f5 == 1.0


def test_f5_is_zero_for_simple_paths():
    c = metric.raw_components(ps([[1, 2, 3]]), [1], [3], 0)
    assert c.f5 == 0.0


def test_f6_is_the_fan_in_count():
    c = metric.raw_components(ps([[1, 2, 3]]), [1], [3], 17)
    assert c.f6 == 17.0


def test_empty_path_set_is_all_zero_not_an_error():
    c = metric.raw_components(ps([]), [1], [3], 0)
    assert c.as_dict() == {"f1": 0.0, "f2": 0.0, "f3": 0.0,
                           "f4": 0.0, "f5": 0.0, "f6": 0.0}


def test_normalise_maps_to_unit_interval():
    raw = [metric.Components(0, 0, 0, 0, 0, 0),
           metric.Components(10, 10, 10, 10, 10, 10),
           metric.Components(5, 5, 5, 5, 5, 5)]
    out = metric.normalise(raw)
    assert out[0].f1 == 0.0
    assert out[1].f1 == 1.0
    assert out[2].f1 == pytest.approx(0.5)


def test_normalise_handles_a_constant_component():
    raw = [metric.Components(3, 0, 0, 0, 0, 0), metric.Components(3, 0, 0, 0, 0, 0)]
    out = metric.normalise(raw)
    assert out[0].f1 == 0.0 and out[1].f1 == 0.0


def test_score_inverts_convergence():
    low_convergence = metric.Components(0, 0, 0, 0.0, 0, 0)
    high_convergence = metric.Components(0, 0, 0, 1.0, 0, 0)
    w = {"f1": 0, "f2": 0, "f3": 0, "f4": 1, "f5": 0, "f6": 0}
    assert metric.score(low_convergence, w) == 1.0
    assert metric.score(high_convergence, w) == 0.0


def test_score_with_equal_weights_is_bounded():
    c = metric.Components(1, 1, 1, 1, 1, 1)
    assert 0.0 <= metric.score(c, metric.EQUAL_WEIGHTS) <= 1.0


def test_band_thresholds():
    assert metric.band(0.20) == "LOW"
    assert metric.band(0.50) == "MEDIUM"
    assert metric.band(0.79) == "HIGH"

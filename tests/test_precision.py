"""What name matching costs, joined to consequence — tests.

The parsing tests are pinned against the COMMITTED ``docs/graph-delta.md`` so
the numbers in ``friction.precision`` can never drift from the report. The
projection tests fence in the ARISE analogy: it must be an interval, it must
name ARISE, a perfect graph must cost ~nothing, and a degenerate graph must
never fall out of [0, 1].
"""

from pathlib import Path

import pytest

from friction import precision as P

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_DELTA = REPO_ROOT / "docs" / "graph-delta.md"


# --------------------------------------------------------------------------
# Parsing the committed report yields the exact committed numbers.
# --------------------------------------------------------------------------

def test_load_report_parses_the_committed_scalar_numbers():
    r = P.load_report(GRAPH_DELTA)
    assert r.precision_ceiling == 0.746
    assert r.recall == 0.352
    assert r.jaccard == 0.3143
    assert r.confirmed == 4381
    assert r.only_a == 1492
    assert r.only_b == 8064
    assert r.compared == 5873


def test_compared_equals_confirmed_plus_only_a():
    r = P.load_report(GRAPH_DELTA)
    # the compared-in-scope count is the two arm-A partitions summed
    assert r.compared == r.confirmed + r.only_a


def test_load_report_parses_the_offender_table():
    r = P.load_report(GRAPH_DELTA)
    offenders = dict(r.offenders)
    assert offenders["extend"] == 139
    assert offenders["lower"] == 125
    assert offenders["cursor"] == 54
    assert offenders["import_module"] == 33
    # the report ranks by unconfirmed-edge count, most first
    assert r.offenders[0] == ("extend", 139)


def test_counter_example_is_cursor_54():
    r = P.load_report(GRAPH_DELTA)
    assert r.counter_example == ("cursor", 54)


def test_load_report_default_path_reads_docs_graph_delta():
    # exercised from the repo root; the default path must resolve the real file
    r = P.load_report()
    assert r.precision_ceiling == 0.746


# --------------------------------------------------------------------------
# The cost projection: an ARISE-anchored interval, never a point estimate.
# --------------------------------------------------------------------------

def test_projection_is_an_interval_low_below_high():
    proj = P.project_localization_cost(0.746, 0.352)
    assert proj.low < proj.high


def test_projection_basis_names_arise_and_flags_it_as_analogy():
    proj = P.project_localization_cost(0.746, 0.352)
    assert "ARISE" in proj.basis
    assert "analogy" in proj.basis.lower()
    # never claim it is something we measured
    assert "not a measurement" in proj.basis.lower()


def test_projection_states_its_assumption():
    proj = P.project_localization_cost(0.746, 0.352)
    assert proj.assumption.strip() != ""
    assert "assum" in proj.assumption.lower()


def test_perfect_precision_graph_projects_about_zero_cost():
    # a graph whose edges are all confirmed costs nothing, whatever its recall
    for recall in (1.0, 0.5, 0.0):
        proj = P.project_localization_cost(1.0, recall)
        assert proj.low == pytest.approx(0.0, abs=1e-9)
        assert proj.high == pytest.approx(0.0, abs=1e-9)


def test_degenerate_graph_stays_within_zero_and_one():
    proj = P.project_localization_cost(0.0, 0.0)
    assert 0.0 <= proj.low <= proj.high <= 1.0


def test_no_input_yields_a_negative_or_above_one_cost():
    # sweep the whole unit square; the projection must never leave [0, 1]
    for p in (0.0, 0.25, 0.5, 0.746, 1.0):
        for rec in (0.0, 0.352, 0.5, 1.0):
            proj = P.project_localization_cost(p, rec)
            assert 0.0 <= proj.low <= 1.0
            assert 0.0 <= proj.high <= 1.0
            assert proj.low <= proj.high


def test_worse_precision_costs_at_least_as_much():
    better = P.project_localization_cost(0.9, 0.352)
    worse = P.project_localization_cost(0.5, 0.352)
    assert worse.high >= better.high
    assert worse.low >= better.low


# --------------------------------------------------------------------------
# The generated report.
# --------------------------------------------------------------------------

def test_write_report_emits_counter_example_and_published_caveat(tmp_path):
    r = P.load_report(GRAPH_DELTA)
    proj = P.project_localization_cost(r.precision_ceiling, r.recall)
    out = tmp_path / "precision.md"
    P.write_report(r, proj, out)
    text = out.read_text(encoding="utf-8")

    # the counter-example, named
    assert "cursor" in text
    # the published anchors are clearly marked as not reproduced here
    assert "published, not reproduced" in text.lower()
    # all three published anchors are cited
    assert "ARISE" in text and "SHERLOC" in text and "RGFL" in text
    # we must NOT claim we measured a resolve-rate delta
    assert "resolve" in text.lower()  # it is discussed...
    lowered = text.lower()
    assert "we did not" in lowered or "not a measurement" in lowered \
        or "not reproduced" in lowered


def test_write_report_states_the_ceiling_in_both_directions(tmp_path):
    r = P.load_report(GRAPH_DELTA)
    proj = P.project_localization_cost(r.precision_ceiling, r.recall)
    out = tmp_path / "precision.md"
    P.write_report(r, proj, out)
    text = out.read_text(encoding="utf-8")
    lowered = text.lower()
    # ceiling framing: arm A can be a false positive OR pyright under-reported
    assert "ceiling" in lowered
    assert "under-report" in lowered or "under report" in lowered
    # the honest counter-direction: arm A was right here
    assert "right" in lowered


def test_write_report_carries_the_measured_and_offender_tables(tmp_path):
    r = P.load_report(GRAPH_DELTA)
    proj = P.project_localization_cost(r.precision_ceiling, r.recall)
    out = tmp_path / "precision.md"
    P.write_report(r, proj, out)
    text = out.read_text(encoding="utf-8")
    # measured numbers present
    assert "0.746" in text
    assert "4381" in text and "1492" in text and "8064" in text
    # offender table present
    assert "extend" in text and "139" in text
    # the projection interval is rendered, with its assumption
    assert "assum" in text.lower()

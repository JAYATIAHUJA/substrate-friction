from pathlib import Path
from friction.parsing.symbols import parse_repo
from friction.parsing.calls import resolve
from friction.parsing.covers import derive_covers

FIXTURE = Path(__file__).parent / "fixtures" / "sample_pkg"


def test_covers_reaches_transitively_within_hop_bound():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    covers = derive_covers(table, edges, max_hops=3)
    q = {f.qualname: f.id for f in table.functions}
    pairs = {(e.src, e.dst) for e in covers}
    # the test calls Widget.render, which calls helper
    assert (q["test_mod_a.test_render_positive"], q["mod_a.Widget.render"]) in pairs
    assert (q["test_mod_a.test_render_positive"], q["mod_a.helper"]) in pairs


def test_covers_respects_hop_bound():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    one_hop = derive_covers(table, edges, max_hops=1)
    three_hop = derive_covers(table, edges, max_hops=3)
    assert len(one_hop) <= len(three_hop)


def test_covers_only_originates_from_tests():
    table = parse_repo(FIXTURE, repo_code=1)
    edges = resolve(FIXTURE, table)
    covers = derive_covers(table, edges, max_hops=3)
    tests = {f.id for f in table.functions if f.is_test}
    assert all(e.src in tests for e in covers)
    assert all(e.type == "COVERS" for e in covers)

"""S1 acceptance: the committed corpus artifact is internally consistent and
is what the shipped docs quote.

The full regeneration needs ~4.5 GB of git-ignored inputs, so a clean clone
cannot re-run the audit — instead this recomputes every summary figure from
the committed per-instance outcomes and fails if a single number drifted.
"""

import json
from pathlib import Path

RESULTS = Path("data/shipped/gate-results.json")


def _load():
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def test_summary_is_exactly_derivable_from_per_instance_rows():
    d = _load()
    rows = d["per_instance"]
    for arm in ("arm_a", "arm_b"):
        for repo, arms in d["summary"]["per_repo"].items():
            hits = sum(1 for r in rows
                       if r["repo"] == repo and r[arm] and r[arm]["hit"])
            n = sum(1 for r in rows
                    if r["repo"] == repo and r[arm] is not None)
            assert arms[arm] == {"hits": hits, "n": n}, (arm, repo)
        pooled = d["summary"]["pooled"][arm]
        hits = sum(1 for r in rows if r[arm] and r[arm]["hit"])
        n = sum(1 for r in rows if r[arm] is not None)
        assert pooled["hits"] == hits and pooled["n"] == n
        assert pooled["recall"] == round(hits / n, 4)


def test_the_corpus_covers_seven_repos_and_the_registered_scale():
    d = _load()
    assert set(d["summary"]["per_repo"]) == {
        "django", "sphinx", "matplotlib", "xarray", "pytest", "requests",
        "sympy"}
    assert d["summary"]["pooled"]["arm_b"]["n"] == 172


def test_gate_md_quotes_the_committed_pooled_numbers():
    d = _load()
    text = Path("docs/gate.md").read_text(encoding="utf-8")
    for arm in ("arm_a", "arm_b"):
        p = d["summary"]["pooled"][arm]
        assert f"{p['hits']}/{p['n']} ({p['recall']:.3f})" in text, arm


def test_no_repo_with_meaningful_n_clears_the_bar():
    d = _load()
    for repo, arms in d["summary"]["per_repo"].items():
        a = arms["arm_b"]
        if a["n"] >= 19:
            assert a["hits"] / a["n"] < 0.95, repo

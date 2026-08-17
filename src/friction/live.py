"""Gate a real repository at a real commit for a real diff.

Everything else in this package measures the committed corpus. This runs the
same selection against a repository the user actually has, which is what makes
the gate usable rather than merely demonstrated.

The one thing it cannot do is measure recall on that repository: recall needs
labels saying which test guards which fix, and an arbitrary repo has none. So
the gate identifies which *class* of graph was built and applies that class's
recall as measured on the labelled corpus. The output says so explicitly — a
prior presented as a measurement would be exactly the kind of borrowed number
this project exists to object to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from friction.gate import GateVerdict, audit_recall, gate, select_tests

TEST_MARKERS = ("test_", "_test", "tests.", ".tests", "conftest")


@dataclass(frozen=True)
class LiveGate:
    repo: Path
    graph_sha: str
    repo_head: str
    arm: str
    k: int
    graph_nodes: int
    graph_edges: int
    changed_symbols: int
    total_tests: int
    selected_tests: tuple[str, ...]
    graph_complete: bool
    unmatched_changed: tuple[str, ...]
    verdict: GateVerdict
    prior_n: int
    prior_note: str


def _is_test(node: str) -> bool:
    low = node.replace("\\", "/").lower()
    return any(m in low for m in TEST_MARKERS)


def _module_prefixes(path: str) -> tuple[str, ...]:
    """`src/requests/sessions.py` -> dotted qualname prefixes a node may carry.

    tree-sitter qualnames are dotted from the repo root and KEEP layout dirs
    (`src.requests.sessions.Session::__init__`), so the full dotted path is the
    primary candidate; the src/lib-stripped variant covers repos whose parse
    root sat below the layout dir.
    """
    p = path.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    full = p.replace("/", ".")
    out = [full]
    for strip in ("src/", "lib/"):
        if p.startswith(strip):
            out.append(p[len(strip):].replace("/", "."))
    return tuple(out)


def gate_repo(repo: Path, changed_files: list[str], arm: str = "arm_a",
              k: int = 6) -> LiveGate:
    """Build a graph of `repo`, select tests for `changed_files`, and decide."""
    repo = Path(repo)
    if not repo.is_dir():
        raise NotADirectoryError(f"{repo} is not a directory")

    from friction.namematch.graph import build as build_arm_a
    edges, _stats = build_arm_a(repo)

    # Intern qualname nodes to the integer ids select_tests works in.
    index: dict[str, int] = {}

    def nid(name: str) -> int:
        if name not in index:
            index[name] = len(index) + 1
        return index[name]

    g = nx.DiGraph()
    for e in edges:
        g.add_edge(nid(e.src), nid(e.dst))

    wanted = {c.replace("\\", "/") for c in changed_files}
    prefixes = {w: _module_prefixes(w) for w in wanted}
    changed_ids: set[int] = set()
    matched: set[str] = set()
    for name, node_id in index.items():
        for w, prefs in prefixes.items():
            if any(name.startswith(pref) for pref in prefs if pref):
                changed_ids.add(node_id)
                matched.add(w)

    test_ids = {node_id for name, node_id in index.items() if _is_test(name)}
    by_id = {v: k_ for k_, v in index.items()}

    result = select_tests(g, changed_ids, test_ids, k)

    # Staleness fingerprint: a verdict is about THIS graph of THIS commit.
    # Consumers can detect a stale answer by re-hashing.
    import hashlib
    import subprocess
    h = hashlib.sha256()
    for u, v in sorted(g.edges):
        h.update(f"{u},{v};".encode())
    graph_sha = h.hexdigest()[:16]
    try:
        repo_head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5).stdout.strip() or "n/a"
    except Exception:
        repo_head = "n/a"

    # Recall is a corpus prior, never a measurement on this repo.
    from friction.cli import MANIFEST_PATH
    audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent, arm, k)
    verdict = gate(audit)

    return LiveGate(
        repo=repo, graph_sha=graph_sha, repo_head=repo_head, arm=arm, k=k,
        graph_nodes=g.number_of_nodes(), graph_edges=g.number_of_edges(),
        changed_symbols=len(changed_ids),
        total_tests=len(test_ids),
        selected_tests=tuple(sorted(by_id[i] for i in result.selected)),
        graph_complete=result.graph_complete,
        unmatched_changed=tuple(sorted(wanted - matched)),
        verdict=verdict,
        prior_n=audit.n,
        prior_note=(
            f"Recall {verdict.measured_recall:.3f} is the value measured for "
            f"'{arm}'-class graphs on the labelled corpus (n={audit.n}), not a "
            f"measurement on {repo.name}. An unlabelled repository cannot yield "
            f"a recall figure; this is that class's prior, applied."),
    )

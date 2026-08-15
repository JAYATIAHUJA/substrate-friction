"""Arm A — the name-matched call graph, as the ecosystem actually builds it.

This deliberately reproduces the standard approach so the comparison is fair:
  * Aider's repo map draws an edge wherever a referenced identifier NAME matches
    a defined identifier NAME (tree-sitter tags + PageRank).
  * RepoGraph does tree-sitter def/ref name matching plus an empirical stdlib
    denylist.
  * LocAgent's `invoke` edges are AST-derived, not type-resolved.

It is the control arm, not dead code. Every edge carries the rule that produced
it so the delta analysis can attribute error to a specific resolution strategy.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from friction.parsing.symbols import parse_repo

# Only genuine builtin FUNCTIONS / types are denylisted — the same class of
# names Aider / RepoGraph strip (super, len, print, isinstance, ...). Container
# METHOD names (lower, append, split, get, ...) are deliberately NOT denylisted:
# they are precisely where name matching invents its false edges (`s.lower()`
# binding to a module-level `lower`), and reproducing that collision is the whole
# purpose of this control arm. See test_name_match_reproduces_the_false_edge_*.
DEFAULT_DENYLIST = frozenset({
    "super", "len", "str", "list", "dict", "set", "tuple", "int", "float", "bool",
    "print", "open", "range", "type", "isinstance", "getattr", "setattr", "hasattr",
})


@dataclass(frozen=True)
class NameEdge:
    src: str
    dst: str
    weight: int
    rule: str


def _identity(qualname: str) -> str:
    """Dotted tree-sitter qualname -> a `module::name` node identity.

    Arm B's SCIP `canonical` keys are `module::rest`, so arm A uses the same
    `::` separator between the containing scope and the leaf name to keep the
    two arms structurally comparable in the delta analysis.
    """
    head, sep, tail = qualname.rpartition(".")
    return f"{head}::{tail}" if sep else qualname


def build(root: Path, stdlib_denylist: set[str] | None = None
          ) -> tuple[list[NameEdge], dict]:
    from friction.parsing.calls import resolve_with_stats

    deny = set(DEFAULT_DENYLIST if stdlib_denylist is None else stdlib_denylist)
    table = parse_repo(Path(root), repo_code=0)
    raw, _ = resolve_with_stats(Path(root), table)

    qual = {f.id: f.qualname for f in table.functions}
    qual.update({c.id: c.qualname for c in table.classes})
    name_of = {f.id: f.name for f in table.functions}
    name_of.update({c.id: c.name for c in table.classes})

    counts = {}
    for name in name_of.values():
        counts[name] = counts.get(name, 0) + 1
    unique = {n for n, c in counts.items() if c == 1}

    weights: dict[tuple[str, str, str], int] = defaultdict(int)
    for e in raw:
        if e.type != "CALLS":
            continue
        s, d = qual.get(e.src), qual.get(e.dst)
        if s is None or d is None or s == d:
            continue
        target = name_of.get(e.dst, "")
        if target in deny:
            continue
        rule = "bare_name" if target in unique else "module_local"
        weights[(_identity(s), _identity(d), rule)] += e.weight

    edges = [NameEdge(s, d, n, r) for (s, d, r), n in sorted(weights.items())]
    by_rule: dict[str, int] = defaultdict(int)
    for e in edges:
        by_rule[e.rule] += 1
    return edges, {"edges": len(edges), "by_rule": dict(by_rule),
                   "denylisted": len(deny)}

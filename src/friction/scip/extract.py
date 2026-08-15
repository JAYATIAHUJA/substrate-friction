"""Turn SCIP occurrences into caller -> callee edges.

Definition occurrences carry an `enclosing_range` spanning the body. A
reference occurrence lying inside that span was written *by* that definition,
so it is a call from it. Where spans nest (a method inside a class, a closure
inside a function) the INNERMOST containing definition is the caller.

scip-python 0.6.6 emits the deprecated `enclosing_range` (field 7), not
`typed_enclosing_range`, so field 7 is what is read here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from friction.scip.schema import DEFINITION_ROLE
from friction.scip.symbols import canonical, parse_symbol


@dataclass(frozen=True)
class Def:
    symbol: str
    path: str
    start: int
    end: int
    canonical: str
    kind: str


@dataclass(frozen=True)
class CallEdge:
    src: str
    dst: str
    dst_external: bool
    weight: int = 1


def _line(rng) -> int:
    return rng[0] if rng else -1


def _span(enclosing) -> tuple[int, int] | None:
    """enclosing_range is [startLine, startChar, endLine, endChar]."""
    if not enclosing or len(enclosing) < 3:
        return None
    return enclosing[0], enclosing[2]


def collect_definitions(index) -> list[Def]:
    out: list[Def] = []
    for doc in index.documents:
        for occ in doc.occurrences:
            if not occ.symbol_roles & DEFINITION_ROLE:
                continue
            span = _span(list(occ.enclosing_range))
            if span is None:
                continue
            sym = parse_symbol(occ.symbol)
            out.append(Def(
                symbol=occ.symbol,
                path=doc.relative_path,
                start=span[0],
                end=span[1],
                canonical=canonical(sym, doc.relative_path),
                kind=sym.kind,
            ))
    return out


def innermost(defs_by_path: dict[str, list[Def]], path: str, line: int) -> Def | None:
    best: Def | None = None
    for d in defs_by_path.get(path, ()):
        if d.start <= line <= d.end:
            if best is None or (d.end - d.start) < (best.end - best.start):
                best = d
    return best


def extract_edges(index) -> tuple[list[CallEdge], dict]:
    defs = collect_definitions(index)
    by_path: dict[str, list[Def]] = defaultdict(list)
    for d in defs:
        by_path[d.path].append(d)

    weights: dict[tuple[str, str, bool], int] = defaultdict(int)
    refs = unenclosed = 0

    for doc in index.documents:
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue
            refs += 1
            caller = innermost(by_path, doc.relative_path, _line(list(occ.range)))
            if caller is None:
                unenclosed += 1
                continue
            sym = parse_symbol(occ.symbol)
            if sym.kind == "other":
                continue
            dst = canonical(sym, None)
            if dst == caller.canonical:
                continue
            weights[(caller.canonical, dst, sym.is_external)] += 1

    edges = [CallEdge(s, d, ext, n) for (s, d, ext), n in sorted(weights.items())]
    stats = {
        "definitions": len(defs),
        "references": refs,
        "unenclosed_references": unenclosed,
        "edges": len(edges),
        "internal_edges": sum(1 for e in edges if not e.dst_external),
        "external_edges": sum(1 for e in edges if e.dst_external),
    }
    return edges, stats

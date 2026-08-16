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


# --- typed nodes and structural edges -------------------------------------
#
# ``extract_edges`` above keeps only CALLS. Everything the build spec's other
# edge types (DEFINED_IN, HAS_METHOD, INHERITS, IMPORTS) need is already sitting
# in the same SCIP index -- in the definition spans and the reference
# occurrences -- and was simply discarded. These functions recover it.


@dataclass(frozen=True)
class TypedEdge:
    src: str
    dst: str
    type: str


def collect_files(defs: list[Def]) -> list[str]:
    """Distinct file paths that hold at least one definition, sorted."""
    return sorted({d.path for d in defs})


def enclosing_class(func_canonical: str) -> str | None:
    """The class canonical that encloses a method canonical, or None.

    ``m::C#save().`` -> ``m::C#``; ``m::Outer#Inner#f().`` -> ``m::Outer#Inner#``;
    ``m::run().`` (module-level function) -> None.
    """
    module, sep, rest = func_canonical.partition("::")
    if not sep or "#" not in rest:
        return None
    return f"{module}::{rest[:rest.rfind('#') + 1]}"


def defined_in_edges(defs: list[Def]) -> list[TypedEdge]:
    """Function -> File, for every function definition (DEFINED_IN)."""
    return [TypedEdge(d.canonical, d.path, "DEFINED_IN")
            for d in defs if d.kind == "function"]


def has_method_edges(defs: list[Def]) -> list[TypedEdge]:
    """Class -> Function, for every method whose enclosing class is defined here."""
    class_canons = {d.canonical for d in defs if d.kind == "class"}
    out: list[TypedEdge] = []
    for d in defs:
        if d.kind != "function":
            continue
        cls = enclosing_class(d.canonical)
        if cls is not None and cls in class_canons:
            out.append(TypedEdge(cls, d.canonical, "HAS_METHOD"))
    return out


def inherits_edges(index, defs: list[Def]) -> list[TypedEdge]:
    """Class -> Class (INHERITS), from base classes named on the class header.

    A reference to an internal class symbol whose occurrence line is the START
    line of a class definition is a base class in that class's ``class Foo(Bar):``
    header. Deduplicated; self-references dropped.
    """
    class_canons = {d.canonical for d in defs if d.kind == "class"}
    headers: dict[tuple[str, int], list[str]] = defaultdict(list)
    for d in defs:
        if d.kind == "class":
            headers[(d.path, d.start)].append(d.canonical)

    seen: set[tuple[str, str]] = set()
    out: list[TypedEdge] = []
    for doc in index.documents:
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue
            sym = parse_symbol(occ.symbol)
            if sym.kind != "class" or sym.is_external:
                continue
            rng = list(occ.range)
            if not rng:
                continue
            subclasses = headers.get((doc.relative_path, rng[0]))
            if not subclasses:
                continue
            base = canonical(sym, None)
            if base not in class_canons:
                continue
            for sub in subclasses:
                if sub == base or (sub, base) in seen:
                    continue
                seen.add((sub, base))
                out.append(TypedEdge(sub, base, "INHERITS"))
    return out


def imports_edges(index, defs: list[Def]) -> list[TypedEdge]:
    """File -> File (IMPORTS), from module-level references to internal defs.

    An import statement sits at module scope, so its reference to an imported
    symbol is enclosed by NO definition. Resolving that symbol's canonical back to
    the file that defines it yields a file-to-file import edge. Deduplicated;
    same-file references dropped.
    """
    by_path: dict[str, list[Def]] = defaultdict(list)
    path_by_canonical: dict[str, str] = {}
    for d in defs:
        by_path[d.path].append(d)
        path_by_canonical.setdefault(d.canonical, d.path)

    seen: set[tuple[str, str]] = set()
    out: list[TypedEdge] = []
    for doc in index.documents:
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue
            sym = parse_symbol(occ.symbol)
            if sym.is_external or sym.kind == "other":
                continue
            rng = list(occ.range)
            if not rng:
                continue
            if innermost(by_path, doc.relative_path, rng[0]) is not None:
                continue  # inside a function/class body: not a top-level import
            target = path_by_canonical.get(canonical(sym, None))
            if target is None or target == doc.relative_path:
                continue
            key = (doc.relative_path, target)
            if key in seen:
                continue
            seen.add(key)
            out.append(TypedEdge(doc.relative_path, target, "IMPORTS"))
    return out


def structural_edges(index, defs: list[Def] | None = None
                     ) -> tuple[list[TypedEdge], dict]:
    """All four non-CALLS structural edge types plus a per-type census."""
    if defs is None:
        defs = collect_definitions(index)
    di = defined_in_edges(defs)
    hm = has_method_edges(defs)
    inh = inherits_edges(index, defs)
    imp = imports_edges(index, defs)
    edges = di + hm + inh + imp
    stats = {
        "DEFINED_IN": len(di),
        "HAS_METHOD": len(hm),
        "INHERITS": len(inh),
        "IMPORTS": len(imp),
    }
    return edges, stats

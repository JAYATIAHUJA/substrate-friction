"""Static call resolution.

Python has no IR, so an AST-based generator has to implement resolution itself.
The strategy here is deliberately conservative and its limits are declared in
the README: resolve by (1) same-class method via `self.`, (2) module-local
name, (3) imported name, (4) unique global name across the repo. Anything
ambiguous is dropped rather than guessed, so CALLS under-reports rather than
inventing edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from friction.parsing.symbols import SKIP_DIRS, SymbolTable, _module_name

PY_LANGUAGE = Language(tspython.language())


@dataclass(frozen=True)
class Edge:
    src: int
    dst: int
    type: str
    weight: int = 1


@dataclass(frozen=True)
class ResolutionStats:
    call_sites: int
    resolved: int
    unresolved: int

    @property
    def resolution_rate(self) -> float:
        return self.resolved / self.call_sites if self.call_sites else 0.0


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _imports(tree_root: Node, src: bytes) -> dict[str, str]:
    """Map local alias -> exporting module name, for `from X import Y` forms."""
    out: dict[str, str] = {}
    stack = [tree_root]
    while stack:
        node = stack.pop()
        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = _text(module_node, src) if module_node else ""
            for child in node.children:
                if child.type == "dotted_name" and child is not module_node:
                    out[_text(child, src)] = module
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is not None:
                        alias = _text(alias_node, src) if alias_node else _text(name_node, src)
                        out[alias] = module
        stack.extend(node.children)
    return out


def _enclosing(table: SymbolTable, file_id: int, line: int) -> int | None:
    best: int | None = None
    best_span = None
    for fn in table.functions:
        if fn.file_id != file_id:
            continue
        if fn.line_start <= line <= fn.line_end:
            span = fn.line_end - fn.line_start
            if best_span is None or span < best_span:
                best, best_span = fn.id, span
    return best


def _unique_suffix_index(table: SymbolTable) -> dict[str, int]:
    """Bare name -> function id, only where the bare name is unambiguous."""
    counts: dict[str, list[int]] = {}
    for fn in table.functions:
        counts.setdefault(fn.name, []).append(fn.id)
    return {name: ids[0] for name, ids in counts.items() if len(ids) == 1}


def resolve_with_stats(root: Path, table: SymbolTable) -> tuple[list[Edge], ResolutionStats]:
    root = Path(root)
    parser = Parser(PY_LANGUAGE)

    edges: set[tuple[int, int, str, int]] = set()
    fn_by_qual = {f.qualname: f.id for f in table.functions}
    cls_by_qual = {c.qualname: c.id for c in table.classes}
    cls_by_name: dict[str, list[int]] = {}
    for c in table.classes:
        cls_by_name.setdefault(c.name, []).append(c.id)
    file_by_path = {f.path: f.id for f in table.files}
    file_by_module = {
        _module_name(Path(f.path), Path(".")): f.id for f in table.files
    }
    unique_names = _unique_suffix_index(table)
    fn_by_id = {f.id: f for f in table.functions}
    cls_by_id = {c.id: c for c in table.classes}

    # Structural edges that need no source walk
    for fn in table.functions:
        edges.add((fn.id, fn.file_id, "DEFINED_IN", 1))
        if fn.class_id is not None:
            edges.add((fn.class_id, fn.id, "HAS_METHOD", 1))
    for cls in table.classes:
        for base in cls.bases:
            targets = cls_by_name.get(base, [])
            if len(targets) == 1 and targets[0] != cls.id:
                edges.add((cls.id, targets[0], "INHERITS", 1))

    call_sites = 0
    resolved = 0
    weights: dict[tuple[int, int], int] = {}

    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root))
        file_id = file_by_path.get(rel)
        if file_id is None:
            continue
        src = path.read_bytes()
        tree = parser.parse(src)
        module = _module_name(path, root)
        aliases = _imports(tree.root_node, src)

        for alias, exporting in aliases.items():
            target_file = file_by_module.get(exporting)
            if target_file is not None and target_file != file_id:
                edges.add((file_id, target_file, "IMPORTS", 1))

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type != "call":
                continue
            fn_node = node.child_by_field_name("function")
            if fn_node is None:
                continue
            call_sites += 1
            line = node.start_point[0] + 1
            caller = _enclosing(table, file_id, line)
            if caller is None:
                continue

            target: int | None = None
            if fn_node.type == "identifier":
                bare = _text(fn_node, src)
                target = fn_by_qual.get(f"{module}.{bare}") or unique_names.get(bare)
                if target is None and bare in aliases:
                    target = fn_by_qual.get(f"{aliases[bare]}.{bare}")
            elif fn_node.type == "attribute":
                obj = fn_node.child_by_field_name("object")
                attr = fn_node.child_by_field_name("attribute")
                if obj is not None and attr is not None:
                    attr_name = _text(attr, src)
                    obj_text = _text(obj, src)
                    caller_sym = fn_by_id.get(caller)
                    if obj_text == "self" and caller_sym and caller_sym.class_id is not None:
                        owner = cls_by_id[caller_sym.class_id]
                        target = fn_by_qual.get(f"{owner.qualname}.{attr_name}")
                    if target is None:
                        owners = cls_by_name.get(obj_text, [])
                        if len(owners) == 1:
                            owner = cls_by_id[owners[0]]
                            target = fn_by_qual.get(f"{owner.qualname}.{attr_name}")
                    if target is None and obj.type == "call":
                        # `ClassName().method()` — treat the constructed value as an
                        # instance of the called class and resolve the method on it.
                        ctor = obj.child_by_field_name("function")
                        if ctor is not None and ctor.type == "identifier":
                            ctor_name = _text(ctor, src)
                            owners = cls_by_name.get(ctor_name, [])
                            if len(owners) == 1:
                                owner = cls_by_id[owners[0]]
                                target = fn_by_qual.get(f"{owner.qualname}.{attr_name}")
                    if target is None:
                        target = unique_names.get(attr_name)

            if target is not None and target != caller:
                resolved += 1
                weights[(caller, target)] = weights.get((caller, target), 0) + 1

    for (src_id, dst_id), count in weights.items():
        edges.add((src_id, dst_id, "CALLS", count))

    out = [Edge(s, d, t, w) for (s, d, t, w) in sorted(edges)]
    stats = ResolutionStats(call_sites, resolved, call_sites - resolved)
    return out, stats


def resolve(root: Path, table: SymbolTable) -> list[Edge]:
    edges, _ = resolve_with_stats(root, table)
    return edges

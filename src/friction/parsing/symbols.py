"""Extract Function / Class / File symbols from Python sources with tree-sitter.

Every symbol gets a non-negative integer id, because the engine matches nodes
on integer `id` only. Names are carried as properties for display and are never
used as match keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

PY_LANGUAGE = Language(tspython.language())

SKIP_DIRS = {".git", "site-packages", "vendor", "node_modules", "__pycache__",
             ".tox", ".venv", "build", "dist"}

DECISION_NODES = {
    "if_statement", "elif_clause", "for_statement", "while_statement",
    "except_clause", "conditional_expression", "boolean_operator",
    "assert_statement", "with_statement",
}


@dataclass(frozen=True)
class FileSym:
    id: int
    path: str
    repo: int
    loc: int


@dataclass(frozen=True)
class ClassSym:
    id: int
    name: str
    qualname: str
    file_id: int
    bases: list[str]


@dataclass(frozen=True)
class FunctionSym:
    id: int
    name: str
    qualname: str
    file_id: int
    line_start: int
    line_end: int
    cyclomatic: int
    is_test: bool
    class_id: int | None


@dataclass
class SymbolTable:
    files: list[FileSym] = field(default_factory=list)
    classes: list[ClassSym] = field(default_factory=list)
    functions: list[FunctionSym] = field(default_factory=list)
    by_qualname: dict[str, int] = field(default_factory=dict)
    _counter: int = 0

    def next_id(self) -> int:
        value = self._counter
        self._counter += 1
        return value


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _child_name(node: Node, src: bytes) -> str:
    ident = node.child_by_field_name("name")
    return _text(ident, src) if ident else "<anonymous>"


def _cyclomatic(node: Node) -> int:
    count = 1
    stack = [node]
    while stack:
        current = stack.pop()
        for child in current.children:
            # do not descend into nested function bodies; they get their own score
            if child.type == "function_definition" and child is not node:
                continue
            if child.type in DECISION_NODES:
                count += 1
            stack.append(child)
    return count


def _module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _walk_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _collect(node: Node, src: bytes, table: SymbolTable, file_id: int,
             module: str, class_stack: list[tuple[int, str]]) -> None:
    for child in node.children:
        if child.type == "class_definition":
            name = _child_name(child, src)
            qualname = ".".join([module] + [c[1] for c in class_stack] + [name])
            bases: list[str] = []
            arglist = child.child_by_field_name("superclasses")
            if arglist is not None:
                for base in arglist.children:
                    if base.type in ("identifier", "attribute"):
                        bases.append(_text(base, src).split(".")[-1])
            cls_id = table.next_id()
            table.classes.append(ClassSym(cls_id, name, qualname, file_id, bases))
            table.by_qualname[qualname] = cls_id
            body = child.child_by_field_name("body")
            if body is not None:
                _collect(body, src, table, file_id, module,
                         class_stack + [(cls_id, name)])

        elif child.type in ("function_definition", "decorated_definition"):
            target = child
            if child.type == "decorated_definition":
                inner = child.child_by_field_name("definition")
                if inner is None or inner.type != "function_definition":
                    _collect(child, src, table, file_id, module, class_stack)
                    continue
                target = inner
            name = _child_name(target, src)
            qualname = ".".join([module] + [c[1] for c in class_stack] + [name])
            fn_id = table.next_id()
            table.functions.append(FunctionSym(
                id=fn_id,
                name=name,
                qualname=qualname,
                file_id=file_id,
                line_start=target.start_point[0] + 1,
                line_end=target.end_point[0] + 1,
                cyclomatic=_cyclomatic(target),
                is_test=name.startswith("test_"),
                class_id=class_stack[-1][0] if class_stack else None,
            ))
            table.by_qualname[qualname] = fn_id
            body = target.child_by_field_name("body")
            if body is not None:
                _collect(body, src, table, file_id, module, class_stack)

        else:
            _collect(child, src, table, file_id, module, class_stack)


def parse_repo(root: Path, repo_code: int) -> SymbolTable:
    root = Path(root)
    parser = Parser(PY_LANGUAGE)
    table = SymbolTable()

    for path in _walk_python_files(root):
        src = path.read_bytes()
        tree = parser.parse(src)
        rel = str(path.relative_to(root))
        file_id = table.next_id()
        table.files.append(FileSym(
            id=file_id,
            path=rel,
            repo=repo_code,
            loc=src.count(b"\n") + 1,
        ))
        table.by_qualname[f"<file>{rel}"] = file_id
        _collect(tree.root_node, src, table, file_id,
                 _module_name(path, root), [])

    return table

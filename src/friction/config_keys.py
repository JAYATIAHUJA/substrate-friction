"""ConfigKey nodes and READS_CONFIG edges from ``settings.<NAME>`` reads.

django's ``django.conf.settings`` is a ``LazySettings`` proxy: every attribute is
resolved dynamically at run time, so pyright (and therefore SCIP) cannot bind
``settings.DEBUG`` to a symbol for ``DEBUG``. The index DOES carry a reference to
the ``settings`` object itself at each read site, so the object references are
recoverable from the index alone -- but the attribute NAME after the dot is only
in the source text. This module joins the two: it walks the index for references
to the ``django.conf.settings`` object, then reads the source line at each to
capture the ``.<NAME>`` that follows.

The enclosing function of each read is the READS_CONFIG source; a read at module
scope (no enclosing function) contributes its ConfigKey but no edge, and is
counted so the shortfall is never invisible.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from friction.scip.extract import Def, collect_definitions, innermost
from friction.scip.schema import DEFINITION_ROLE
from friction.scip.symbols import canonical, parse_symbol

_ATTR = re.compile(r"\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class ConfigRead:
    reader: str | None  # canonical of the enclosing function, or None at module scope
    key: str            # the setting name, e.g. "DEBUG"


def is_settings_symbol(symbol: str) -> bool:
    """True iff ``symbol`` is the ``django.conf.settings`` object reference.

    Fast-path the common case (almost every occurrence is not settings) before
    the full symbol parse.
    """
    if not symbol.endswith("/settings.") or "conf" not in symbol:
        return False
    sym = parse_symbol(symbol)
    return sym.name == "settings" and canonical(sym, None).endswith("conf::settings.")


def _range_end_char(rng: list[int]) -> int:
    """SCIP ranges are [line, sc, ec] on one line or [sl, sc, el, ec]."""
    return rng[2] if len(rng) == 3 else rng[3]


def _attr_after(line: str, end_char: int) -> str | None:
    m = _ATTR.match(line[end_char:])
    return m.group(1) if m else None


def source_reader(repo_root: Path):
    """A cached ``path -> list[str] | None`` line reader rooted at ``repo_root``."""
    repo_root = Path(repo_root)
    cache: dict[str, list[str] | None] = {}

    def read(path: str) -> list[str] | None:
        if path not in cache:
            fp = repo_root / path
            try:
                cache[path] = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            except (FileNotFoundError, OSError, IsADirectoryError):
                cache[path] = None
        return cache[path]

    return read


def git_source_reader(repo_root: Path, commit: str):
    """A cached ``path -> list[str] | None`` reader for a file AT ``commit``.

    Reads via ``git show <commit>:<path>`` so source lines match the base commit
    the SCIP index was built at, WITHOUT touching the working tree (a hard
    requirement: the django clone must never be mutated destructively).
    """
    import subprocess

    repo_root = Path(repo_root)
    cache: dict[str, list[str] | None] = {}

    def read(path: str) -> list[str] | None:
        if path not in cache:
            try:
                proc = subprocess.run(
                    ["git", "-C", str(repo_root), "show", f"{commit}:{path}"],
                    capture_output=True, timeout=30)
                cache[path] = (
                    proc.stdout.decode("utf-8", "replace").splitlines()
                    if proc.returncode == 0 else None)
            except (OSError, subprocess.SubprocessError):
                cache[path] = None
        return cache[path]

    return read


def extract_config_reads(index, read_lines, defs: list[Def] | None = None
                         ) -> tuple[list[ConfigRead], dict]:
    """Every ``settings.<NAME>`` read in the index, with its reading function.

    ``read_lines(relative_path) -> list[str] | None`` supplies source text; pass
    :func:`source_reader` for a real checkout. Returns ``(reads, stats)``. The
    stats disclose reads whose source line was unavailable and reads whose
    ``.<NAME>`` could not be parsed, so a low ConfigKey count is never silent.
    """
    if defs is None:
        defs = collect_definitions(index)
    by_path: dict[str, list[Def]] = defaultdict(list)
    for d in defs:
        by_path[d.path].append(d)

    reads: list[ConfigRead] = []
    refs = missing_source = no_attr = module_scope = 0
    for doc in index.documents:
        lines: list[str] | None = None
        loaded = False
        for occ in doc.occurrences:
            if occ.symbol_roles & DEFINITION_ROLE:
                continue
            if not is_settings_symbol(occ.symbol):
                continue
            refs += 1
            rng = list(occ.range)
            if not rng:
                continue
            if not loaded:
                lines = read_lines(doc.relative_path)
                loaded = True
            if lines is None:
                missing_source += 1
                continue
            line_no = rng[0]
            if line_no >= len(lines):
                missing_source += 1
                continue
            key = _attr_after(lines[line_no], _range_end_char(rng))
            if key is None:
                no_attr += 1
                continue
            caller = innermost(by_path, doc.relative_path, line_no)
            if caller is not None and caller.kind == "function":
                reader = caller.canonical
            else:
                reader = None
                module_scope += 1
            reads.append(ConfigRead(reader, key))

    stats = {
        "settings_references": refs,
        "reads_resolved": len(reads),
        "missing_source": missing_source,
        "unparsed_attribute": no_attr,
        "module_scope_reads": module_scope,
        "distinct_keys": len({r.key for r in reads}),
    }
    return reads, stats


def config_keys(reads: list[ConfigRead]) -> list[str]:
    """Distinct setting names, sorted -- one ConfigKey node each."""
    return sorted({r.key for r in reads})


def reads_config_pairs(reads: list[ConfigRead]) -> list[tuple[str, str]]:
    """Distinct ``(function_canonical, key)`` READS_CONFIG pairs, sorted.

    Reads at module scope (``reader is None``) carry no function and so emit no
    edge, though their key still becomes a ConfigKey node.
    """
    pairs = {(r.reader, r.key) for r in reads if r.reader is not None}
    return sorted(pairs)

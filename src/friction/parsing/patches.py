"""Map a gold patch to the Function nodes it changes, and FAIL_TO_PASS test
identifiers to Function nodes.

Fix sites are derived from the post-image line ranges of each diff hunk,
intersected against Function `line_start`/`line_end`.
"""

from __future__ import annotations

import re

from unidiff import PatchSet

from friction.parsing.symbols import SymbolTable

# Django test-runner identifier: 'method (dotted.module.Class[.method])'.
_DJANGO_RE = re.compile(r"^(?P<method>[^()\s]+)\s*\((?P<inside>[^)]*)\)\s*$")


def _normalise(path: str) -> str:
    for prefix in ("a/", "b/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def changed_ranges(patch: str) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    patch_set = PatchSet(patch)
    for patched_file in patch_set:
        path = _normalise(patched_file.path)
        spans: list[tuple[int, int]] = []
        for hunk in patched_file:
            lines = [ln.target_line_no for ln in hunk
                     if ln.target_line_no is not None and (ln.is_added or ln.is_context)]
            changed = [ln.target_line_no for ln in hunk
                       if ln.is_added and ln.target_line_no is not None]
            if changed:
                spans.append((min(changed), max(changed)))
            elif lines:
                spans.append((min(lines), max(lines)))
        if spans:
            out.setdefault(path, []).extend(spans)
    return out


def fix_site_ids(patch: str, table: SymbolTable) -> list[int]:
    ranges = changed_ranges(patch)
    file_ids = {f.path: f.id for f in table.files}
    hits: set[int] = set()
    for path, spans in ranges.items():
        file_id = file_ids.get(path)
        if file_id is None:
            continue
        for fn in table.functions:
            if fn.file_id != file_id:
                continue
            for start, end in spans:
                if fn.line_start <= end and start <= fn.line_end:
                    hits.add(fn.id)
                    break
    return sorted(hits)


def parse_test_identifier(raw: str) -> tuple[str | None, str]:
    """Split a FAIL_TO_PASS test identifier into (dotted_class_or_None, method).

    Handles two shapes:
      - pytest:  'path/to/test_x.py::Class::method'  and 'path::method'
                 (with optional '[param]' suffix on the method)
      - django:  'method (dotted.module.Class)'  and
                 'method (dotted.module.Class.method)'  (method repeated)

    The dotted class is returned WITHOUT the method appended and WITHOUT any
    file-path component. The method is returned with any '[param]' stripped.
    """
    text = raw.strip()

    # Django test-runner format takes precedence: it is the only one with parens.
    m = _DJANGO_RE.match(text)
    if m:
        method = m.group("method").split("[")[0]
        parts = [p for p in m.group("inside").strip().split(".") if p]
        # Newer Django/unittest repeats the method name inside the parens.
        if parts and parts[-1] == method:
            parts = parts[:-1]
        dotted = ".".join(parts) if parts else None
        return dotted, method

    # pytest node id.
    if "::" in text:
        comps = text.split("::")
        method = comps[-1].split("[")[0]
        # Drop the leading file-path component(s); keep only class parts.
        middle = [c for c in comps[:-1] if not c.endswith(".py")]
        dotted = ".".join(middle) if middle else None
        return dotted, method

    # Bare method name.
    return None, text.split("[")[0]


def _suffix_matches(full: str, table: SymbolTable) -> list[int]:
    """Function ids whose qualname equals `full` or ends with `.full`.

    parse_repo roots qualnames at the clone directory, so a Function.qualname
    carries path-derived module prefixes that the django dotted name omits.
    Matching on dot boundaries prevents 'Widget.render' from also matching
    'FancyWidget.render'.
    """
    suffix = "." + full
    return [f.id for f in table.functions
            if f.qualname == full or f.qualname.endswith(suffix)]


def test_target_ids(fail_to_pass: list[str], table: SymbolTable) -> list[int]:
    by_qual = {f.qualname: f.id for f in table.functions}
    by_name: dict[str, list[int]] = {}
    for f in table.functions:
        by_name.setdefault(f.name, []).append(f.id)

    hits: list[int] = []
    for raw in fail_to_pass:
        dotted, method = parse_test_identifier(raw)
        target: int | None = None

        if dotted:
            full = f"{dotted}.{method}"
            # 1. exact qualname match, else unique dot-boundary suffix match.
            target = by_qual.get(full)
            if target is None:
                matches = _suffix_matches(full, table)
                if len(matches) == 1:
                    target = matches[0]

        if target is None:
            # 2. unique bare method-name match; give up when ambiguous.
            candidates = by_name.get(method, [])
            if len(candidates) == 1:
                target = candidates[0]

        if target is not None and target not in hits:
            hits.append(target)
    return hits

"""Map a gold patch to the Function nodes it changes, and FAIL_TO_PASS test
identifiers to Function nodes.

Fix sites are derived from the post-image line ranges of each diff hunk,
intersected against Function `line_start`/`line_end`.
"""

from __future__ import annotations

from unidiff import PatchSet

from friction.parsing.symbols import SymbolTable


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


def test_target_ids(fail_to_pass: list[str], table: SymbolTable) -> list[int]:
    by_qual = {f.qualname: f.id for f in table.functions}
    by_name: dict[str, list[int]] = {}
    for f in table.functions:
        by_name.setdefault(f.name, []).append(f.id)

    hits: list[int] = []
    for raw in fail_to_pass:
        node = raw.strip()
        func = node.split("::")[-1].split("[")[0]
        target = by_qual.get(func.replace("/", ".").replace(".py", ""))
        if target is None:
            candidates = by_name.get(func, [])
            if len(candidates) == 1:
                target = candidates[0]
        if target is not None and target not in hits:
            hits.append(target)
    return hits

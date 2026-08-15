"""Build both graph arms for one SWE-bench instance.

Both arms describe the same repository at the same base commit with the same
test patch applied. They differ ONLY in how a call site is bound to a callee:

  * arm A (name-matched) reproduces what Aider / RepoGraph / LocAgent build --
    an edge wherever a referenced identifier NAME matches a defined name.
  * arm B (type-resolved) comes from scip-python (pyright): an untyped receiver
    emits no occurrence, so arm B under-reports rather than inventing edges.

Each arm gets its own disjoint id band so both can be resident in the single
reachable ``default`` graph at once and queried independently.

Endpoint mapping (the Task-8 contract)
--------------------------------------
Task 8's bounded fix->test path queries need, per arm, the band-local integer
node ids of (a) the functions the gold patch changes and (b) the FAIL_TO_PASS
test functions. The two arms key their nodes differently, so the endpoints must
be resolved SEPARATELY in each arm's own identity space:

  * arm A: reuse v1's tree-sitter ``fix_site_ids`` / ``test_target_ids`` (which
    return tree-sitter Function ids), turn each function's qualname into the
    same ``module::name`` identity arm A emits, then look that up in the in-memory
    qual->id assignment produced by ``emit_arm`` (never by re-reading NDJSON).
  * arm B: intersect the gold patch's changed line ranges with SCIP definition
    enclosing_ranges (innermost containment wins) to get fix-site canonicals,
    and match FAIL_TO_PASS class+method names against SCIP test-file defs to get
    test-target canonicals, then look each canonical up in arm B's qual->id map.

``unmapped_fix_sites`` / ``unmapped_test_targets`` COUNT two disjoint miss modes
(Finding 1, Task-6 review), never dropping either silently:

  1. a resolved endpoint whose def participates in NO edge, so it is not a node
     in that arm; and
  2. a requested endpoint -- a diff hunk or a FAIL_TO_PASS entry -- that resolves
     to ZERO defs/canonicals at all (a module-level change, or an inherited test
     method with no physical def in the named subclass).

Mode 2 was the invisible one: it contributes nothing to the flat canonical list,
so counting only mode 1 reported ``unmapped=0`` for the commonest real miss.
Both ``map_arm_a_endpoints`` and ``map_arm_b_endpoints`` now add the mode-2
shortfall, counted per request (before de-duplication).

SCOPE discipline (binding, from the Task-6 gate)
------------------------------------------------
For fix->test paths to exist, the FAIL_TO_PASS tests must be present in BOTH
arms. Arm A's tree-sitter parse already walks the whole checkout (tests
included). Arm B must therefore index the FULL repository -- ``--target-only``
is deliberately NOT passed here, unlike the ``docs/graph-delta.md`` gate run
which scoped to ``django/`` only. This costs ~40-60s/instance and is accepted.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ARM_A_BASE = 10_000_000_000
ARM_B_BASE = 20_000_000_000
STRIDE = 10_000_000


@dataclass(frozen=True)
class ArmBands:
    arm_a: int
    arm_b: int


def bands_for(idx: int) -> ArmBands:
    """Id band for instance ``idx``.

    Arm A at ``1e10 + idx*1e7``, arm B at ``2e10 + idx*1e7``. Both sit an order
    of magnitude above every band v1 occupied (top v1 sweep ~9.5e9), so a v2 run
    never collides with residual v1 nodes in ``default``.
    """
    return ArmBands(ARM_A_BASE + idx * STRIDE, ARM_B_BASE + idx * STRIDE)


def emit_arm(edges, band: int, out_dir: Path) -> dict:
    """Assign band-local integer ids and write loader-ready NDJSON.

    Nodes are numbered in first-appearance order over ``edges`` (src before dst),
    which makes the assignment a pure, deterministic function of the edge list.
    The returned dict carries ``id_by_qual`` -- the SAME in-memory node-qual ->
    id assignment -- so callers resolve endpoints without re-reading the file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = []
    seen: dict[str, int] = {}
    for e in edges:
        for n in (e.src, e.dst):
            if n not in seen:
                seen[n] = len(names)
                names.append(n)

    id_by_qual: dict[str, int] = {n: band + seen[n] for n in names}

    with (out_dir / "nodes.ndjson").open("w", encoding="utf-8") as fh:
        for offset, n in enumerate(names):
            nid = band + offset
            fh.write(json.dumps({
                "label": "Function", "id": nid, "sid": str(nid),
                "name": n.split("::")[-1], "qual": n,
            }) + "\n")

    with (out_dir / "edges.ndjson").open("w", encoding="utf-8") as fh:
        for e in edges:
            fh.write(json.dumps({
                "src": band + seen[e.src], "dst": band + seen[e.dst],
                "type": "CALLS", "weight": int(getattr(e, "weight", 1)),
            }) + "\n")

    return {"nodes": len(names), "edges": len(edges), "band": band,
            "id_by_qual": id_by_qual}


# --- endpoint mapping -----------------------------------------------------

def _map_canonicals(canonicals: list[str], id_by_qual: dict[str, int]
                    ) -> tuple[list[int], int]:
    """Resolve node-identity strings to band-local ids; count the misses.

    A canonical absent from ``id_by_qual`` is a definition that exists in the
    checkout but participates in no edge of this arm, so it is not a node. That
    is a real, disclosed miss -- not an error.

    NOTE (Finding 1, Task-6 review): this counts only the *canonical-without-node*
    miss mode. The *no-canonical-at-all* miss mode -- a requested endpoint (a
    FAIL_TO_PASS entry or a diff hunk) that resolves to ZERO canonicals -- is
    invisible here because such a request contributes nothing to ``canonicals``.
    That shortfall is the commonest miss (inherited test methods with no physical
    def, module-level hunks) and is counted separately by the ``map_*`` functions
    below, then ADDED to the total. Do not treat this function's count as the
    whole ``unmapped_*`` figure.
    """
    ids: list[int] = []
    unmapped = 0
    for c in canonicals:
        nid = id_by_qual.get(c)
        if nid is None:
            unmapped += 1
        elif nid not in ids:
            ids.append(nid)
    return sorted(ids), unmapped


def _dedup(groups: list[list[str]]) -> list[str]:
    """Flatten per-request canonical groups into one order-preserving deduped list."""
    out: list[str] = []
    for group in groups:
        for c in group:
            if c not in out:
                out.append(c)
    return out


def _arm_a_unresolved_fix_hunks(patch: str, table) -> int:
    """Diff hunks that land inside NO tree-sitter Function (Finding 1).

    Mirrors ``fix_site_ids``' overlap test per (path, span) hunk, but counts the
    hunks that hit no def instead of the funcs that were hit. A hunk in a
    module-level location (e.g. django__django-16082) or in a file absent from
    the table produces no fix-site node and would otherwise vanish into
    ``unmapped_fix_sites=0``.
    """
    from friction.parsing.patches import changed_ranges

    file_ids = {f.path: f.id for f in table.files}
    fns_by_file: dict[int, list] = defaultdict(list)
    for fn in table.functions:
        fns_by_file[fn.file_id].append(fn)

    unresolved = 0
    for path, spans in changed_ranges(patch).items():
        fns = fns_by_file.get(file_ids.get(path), [])
        for start, end in spans:
            if not any(fn.line_start <= end and start <= fn.line_end for fn in fns):
                unresolved += 1
    return unresolved


def _arm_a_unresolved_test_entries(fail_to_pass: list[str], table) -> int:
    """FAIL_TO_PASS entries that resolve to NO Function id (Finding 1).

    Resolved per entry (not on the deduped flat list) so a request that names a
    test which has no physical def in the checkout is counted rather than
    silently absorbed by de-duplication.
    """
    from friction.parsing.patches import test_target_ids

    return sum(1 for raw in fail_to_pass if not test_target_ids([raw], table))


def map_arm_a_endpoints(table, patch: str, fail_to_pass: list[str],
                        id_by_qual: dict[str, int]) -> dict:
    """Fix-site and test-target arm-A node ids from the tree-sitter table.

    ``fix_site_ids`` / ``test_target_ids`` return tree-sitter Function ids; each
    is turned into arm A's ``module::name`` node identity (the same ``_identity``
    arm A emits) before lookup, so this resolves in arm A's own key space.

    ``unmapped_*`` is the sum of two disjoint miss modes (Finding 1): a resolved
    endpoint whose node is absent from this arm's edge graph
    (``_map_canonicals``), PLUS a requested endpoint (hunk / FAIL_TO_PASS entry)
    that resolved to no def at all (the ``_arm_a_unresolved_*`` shortfalls).
    """
    from friction.namematch.graph import _identity
    from friction.parsing.patches import fix_site_ids, test_target_ids

    qual_of = {f.id: f.qualname for f in table.functions}
    fix_quals = [_identity(qual_of[i]) for i in fix_site_ids(patch, table)
                 if i in qual_of]
    test_quals = [_identity(qual_of[i]) for i in test_target_ids(fail_to_pass, table)
                  if i in qual_of]

    fix_ids, fix_absent = _map_canonicals(fix_quals, id_by_qual)
    test_ids, test_absent = _map_canonicals(test_quals, id_by_qual)
    return {
        "fix_site_ids": fix_ids,
        "test_target_ids": test_ids,
        "unmapped_fix_sites": fix_absent + _arm_a_unresolved_fix_hunks(patch, table),
        "unmapped_test_targets": test_absent
        + _arm_a_unresolved_test_entries(fail_to_pass, table),
    }


def _canonical_class_leaf(canonical: str) -> str | None:
    """Innermost class name from a SCIP canonical, or None for a bare function.

    ``django.db.models.query::QuerySet#filter().`` -> ``QuerySet``;
    ``mod::run().`` -> None (module-level function, no enclosing class).
    """
    rest = canonical.split("::", 1)[-1]
    if "#" not in rest:
        return None
    return rest.split("#")[-2].split("/")[-1] or None


def _fix_canonicals_by_hunk(defs, patch: str) -> list[list[str]]:
    """Innermost SCIP canonicals grouped per diff hunk (a ``(path, span)`` pair).

    Returns one sub-list per hunk, in ``changed_ranges`` order. A hunk that lands
    inside no def yields an EMPTY sub-list -- preserving that emptiness is what
    lets ``map_arm_b_endpoints`` count the no-canonical miss mode (Finding 1)
    instead of silently dropping it once the flat list is deduped.

    ``changed_ranges`` yields 1-based post-image line spans; SCIP enclosing
    ranges (and therefore ``Def.start`` / ``Def.end``) are 0-based, so each
    changed line is shifted by -1 before the containment test.
    """
    from friction.parsing.patches import changed_ranges
    from friction.scip.extract import innermost

    by_path: dict[str, list] = defaultdict(list)
    for d in defs:
        by_path[d.path].append(d)

    groups: list[list[str]] = []
    for path, spans in changed_ranges(patch).items():
        for start, end in spans:
            found: list[str] = []
            for line in range(start - 1, end):  # 1-based inclusive -> 0-based
                d = innermost(by_path, path, line)
                if d is not None and d.canonical not in found:
                    found.append(d.canonical)
            groups.append(found)
    return groups


def _test_canonicals_by_entry(defs, fail_to_pass: list[str]) -> list[list[str]]:
    """SCIP test-def canonicals grouped per FAIL_TO_PASS entry.

    Returns one sub-list per entry, in ``fail_to_pass`` order; an entry that
    matches no def yields an EMPTY sub-list. Inherited test methods are the
    canonical case: the subclass named by FAIL_TO_PASS has no physical def, so
    the exact class-leaf match finds nothing and the entry maps to zero
    canonicals -- a miss that MUST be counted (Finding 1), not vanish when the
    flat list is deduped.

    A dotted-class identifier (``test_x (mod.Class)``) is matched on both the
    innermost class name and the method name against every function def; a bare
    method identifier is matched on the method name but only within test files,
    where an unqualified collision is far less likely.
    """
    from friction.parsing.patches import parse_test_identifier
    from friction.scip.symbols import parse_symbol

    funcs = [d for d in defs if d.kind == "function"]
    groups: list[list[str]] = []
    for raw in fail_to_pass:
        dotted, method = parse_test_identifier(raw)
        class_leaf = dotted.split(".")[-1] if dotted else None
        found: list[str] = []
        for d in funcs:
            if parse_symbol(d.symbol).name != method:
                continue
            if class_leaf is not None:
                if _canonical_class_leaf(d.canonical) != class_leaf:
                    continue
            elif "test" not in d.path.lower():
                continue
            if d.canonical not in found:
                found.append(d.canonical)
        groups.append(found)
    return groups


def fix_site_canonicals(defs, patch: str) -> list[str]:
    """Flat, deduped canonicals of the innermost defs the gold patch changes."""
    return _dedup(_fix_canonicals_by_hunk(defs, patch))


def test_target_canonicals(defs, fail_to_pass: list[str]) -> list[str]:
    """Flat, deduped canonicals of the SCIP test defs named by FAIL_TO_PASS."""
    return _dedup(_test_canonicals_by_entry(defs, fail_to_pass))


def map_arm_b_endpoints(defs, patch: str, fail_to_pass: list[str],
                        id_by_qual: dict[str, int]) -> dict:
    """Fix-site and test-target arm-B node ids from SCIP defs, band-local.

    ``unmapped_*`` sums two disjoint miss modes (Finding 1): a produced canonical
    absent from this arm's edge graph (``_map_canonicals``), PLUS a requested
    endpoint (hunk / FAIL_TO_PASS entry) that produced no canonical at all (an
    empty group). The second term is the common inherited-test / module-level
    case that previously reported 0.
    """
    fix_groups = _fix_canonicals_by_hunk(defs, patch)
    test_groups = _test_canonicals_by_entry(defs, fail_to_pass)

    fix_ids, fix_absent = _map_canonicals(_dedup(fix_groups), id_by_qual)
    test_ids, test_absent = _map_canonicals(_dedup(test_groups), id_by_qual)

    fix_unresolved = sum(1 for g in fix_groups if not g)
    test_unresolved = sum(1 for g in test_groups if not g)
    return {
        "fix_site_ids": fix_ids,
        "test_target_ids": test_ids,
        "unmapped_fix_sites": fix_absent + fix_unresolved,
        "unmapped_test_targets": test_absent + test_unresolved,
    }


def endpoints_comparable(arm_a_endpoints: dict, arm_b_endpoints: dict) -> bool:
    """True iff BOTH arms mapped >=1 fix site AND >=1 test target (Finding 2).

    The two arms resolve endpoints in different identity spaces and, for
    inherited test methods, in incomparable ways: arm A's bare-name fallback
    (``test_target_ids`` step 2) maps ``TZAwareTimesinceTests.test_depth`` to the
    physical ``TimesinceTests.test_depth`` node -- the WRONG class -- while arm B
    requires an exact class-leaf match and correctly resolves nothing. Comparing
    3 arm-A endpoints against 0 arm-B endpoints would poison the headline
    arm-A-vs-arm-B path-structure delta.

    Rather than teach arm B to invent arm A's wrong mapping, an instance is only
    ``comparable`` when both fix sites AND test targets map in BOTH arms; Task 8
    MUST gate its per-instance path-structure comparison on this flag and report
    the excluded count. The per-arm endpoint lists remain in the record so the
    asymmetry itself is inspectable, never averaged over silently.
    """
    return bool(
        arm_a_endpoints.get("fix_site_ids")
        and arm_a_endpoints.get("test_target_ids")
        and arm_b_endpoints.get("fix_site_ids")
        and arm_b_endpoints.get("test_target_ids")
    )


# --- per-instance build ---------------------------------------------------

def build_instance(instance, repo_root: Path, idx: int, out_root: Path) -> dict:
    """Check out the base commit, apply the test patch, build both arms.

    Returns per-arm node/edge counts, the mapped fix-site / test-target ids in
    each arm's own band, the counts that failed to map, and the wall clock.
    """
    from friction.build import _checkout, _restore, apply_test_patch
    from friction.namematch.graph import build as build_a
    from friction.parsing.symbols import parse_repo
    from friction.scip.extract import collect_definitions, extract_edges
    from friction.scip.index import index_repo
    from friction.scip.schema import load_index

    repo_root, out_root = Path(repo_root), Path(out_root)
    bands = bands_for(idx)
    inst_dir = out_root / instance.instance_id

    t0 = time.perf_counter()
    _restore(repo_root)
    _checkout(repo_root, instance.base_commit)
    test_patch = getattr(instance, "test_patch", "") or ""
    patched = apply_test_patch(repo_root, test_patch)
    if not patched and test_patch.strip():
        # Parse the unpatched tree rather than a half-applied one; disclose it.
        _restore(repo_root)
        _checkout(repo_root, instance.base_commit)
    try:
        # arm A: name-matched, whole-checkout tree-sitter parse.
        a_edges, a_stats = build_a(repo_root)
        # Endpoints are computed against THIS base_commit's tree, so parse once
        # more for the table (parse_repo is deterministic -> same qualnames).
        table = parse_repo(repo_root, repo_code=0)

        # arm B: type-resolved, FULL repo (no --target-only; see module docstring)
        # so the FAIL_TO_PASS tests are present in arm B as they are in arm A.
        scip_out = inst_dir / "index.scip"
        index_repo(repo_root, scip_out, name=instance.repo.split("/")[-1],
                   version=instance.base_commit[:12], target=None)
        index = load_index(scip_out)
        b_edges, b_stats = extract_edges(index)
        b_defs = collect_definitions(index)
        b_internal = [e for e in b_edges if not e.dst_external]
    finally:
        _restore(repo_root)

    a_out = emit_arm(a_edges, bands.arm_a, inst_dir / "arm_a")
    b_out = emit_arm(b_internal, bands.arm_b, inst_dir / "arm_b")
    a_id_by_qual = a_out.pop("id_by_qual")
    b_id_by_qual = b_out.pop("id_by_qual")

    a_endpoints = map_arm_a_endpoints(table, instance.patch,
                                      instance.fail_to_pass, a_id_by_qual)
    b_endpoints = map_arm_b_endpoints(b_defs, instance.patch,
                                      instance.fail_to_pass, b_id_by_qual)

    seconds = round(time.perf_counter() - t0, 2)
    return {
        "instance_id": instance.instance_id,
        "base_commit": instance.base_commit,
        "test_patch_applied": patched,
        "seconds": seconds,
        # Endpoints are NESTED per arm because the arms live in disjoint id bands
        # with different node identities (Finding 3, binding Task-8 contract):
        # Task 8's arm_path_stats MUST read record[arm]["fix_site_ids"] /
        # record[arm]["test_target_ids"], NOT a flat record["fix_site_ids"] --
        # a flat read returns None for every instance and yields silent all-zero
        # path stats. ``comparable`` gates the cross-arm path-structure delta
        # (Finding 2); Task 8 excludes non-comparable instances and reports the
        # excluded count.
        "comparable": endpoints_comparable(a_endpoints, b_endpoints),
        "arm_a": {**a_out, **a_stats, **a_endpoints},
        "arm_b": {**b_out, **b_stats, **b_endpoints},
    }

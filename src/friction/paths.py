"""Path queries. The engine finds the paths; the arithmetic happens elsewhere.

`pairwise` is not documented in cypher-compat.md, so it is emitted only when the
capability probe proved the build accepts it. Without it the same call still
returns bounded paths between the fix-site set and the test-target set, which is
what the friction metric is defined over; the difference is how F1 is
normalised, and that is stated in the README.

Three engine facts, established by `friction.probe`, shape every query here:

* `algo.*` set queries match `sourceValues` / `targetValues` (lists of STRINGS)
  against a STRING property. Nodes carry a `sid` string mirror of their integer
  id for exactly this purpose, so these wrappers key on `sid` and emit every id
  as a STRING. An integer list is a parse error; matching against the int `id`
  property parses but returns nothing.
* `sourceValues` / `targetValues` must be INLINED as a Cypher list literal, not
  passed as a Bolt parameter. The engine rejects a parameter there with
  "composite parameter $fixIds is only supported as an UNWIND input", so the id
  list is written straight into the query text (exactly as `friction.probe`
  builds its MSpaths statements) and `transport.query` is called with no params.
  Ids are integers by construction; a non-integer is rejected rather than
  formatted into the query, so nothing but a validated integer ever reaches the
  statement text.
* `count(path)` is rejected ("unknown path projection count"), so the fan-in
  query yields the paths and counts the returned rows client-side.
* `algo.SSpaths` (single-source, used by fan-in) does NOT share MSpaths' origin
  spelling. It rejects the sourceLabel/sourceProperty/sourceValues SET with
  "missing OpenCypher query parameter $sourceNode" and demands one INTEGER
  `sourceNode`; a string is rejected with "sourceNode must be an integer node
  id". Fan-in over a set of fix sites therefore issues one query per fix site
  (sourceNode = that site's integer id) and unions the callers client-side.
  Without a high `pathCount` SSpaths returns only the single shortest path, so
  every fan-in would read as 1; the cap is set from Settings so all direct
  callers come back.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Sequence

from friction.config import Settings
from friction.probe import Capabilities


@dataclass(frozen=True)
class PathSet:
    paths: list[list[int]]
    costs: list[float]
    cypher: str
    millis: float
    truncated: bool


def _rel_types_literal(rel_types: Sequence[str]) -> str:
    inner = ", ".join(f"'{r}'" for r in rel_types)
    return f"[{inner}]"


def _ids_literal(ids: Sequence[int]) -> str:
    """Inline an integer id list as a Cypher list-of-STRING literals, e.g.
    ``[12, 34]`` -> ``"['12', '34']"``.

    algo.* set queries reject a Bolt parameter for sourceValues/targetValues
    ("composite parameter $fixIds is only supported as an UNWIND input"), so the
    list is written straight into the query text. It is matched against the
    STRING `sid` property, hence each id is emitted quoted; an integer literal
    list is a parse error.

    Every id MUST be a genuine (non-bool) integer. A non-integer is rejected
    with TypeError rather than being string-formatted into the statement, so
    only validated integers can ever reach the query text — there is no
    injection surface even though the values are interpolated.
    """
    out: list[str] = []
    for i in ids:
        if isinstance(i, bool) or not isinstance(i, int):
            raise TypeError(
                f"path id must be a non-bool int, got {type(i).__name__}: {i!r}")
        out.append(f"'{i}'")
    return "[" + ", ".join(out) + "]"


def build_mspaths_cypher(caps: Capabilities, settings: Settings,
                         rel_types: Sequence[str],
                         fix_ids: Sequence[int], test_ids: Sequence[int]) -> str:
    parts = [
        "sourceLabel: 'Function'", "sourceProperty: 'sid'",
        f"sourceValues: {_ids_literal(fix_ids)}",
        "targetLabel: 'Function'", "targetProperty: 'sid'",
        f"targetValues: {_ids_literal(test_ids)}",
        f"relTypes: {_rel_types_literal(rel_types)}",
        f"relDirection: '{caps.rel_direction_both}'",
        f"maxLen: {settings.max_len}",
        f"pathCount: {settings.path_count}",
    ]
    if caps.pairwise_supported:
        parts.insert(-1, "pairwise: true")
    config = ", ".join(parts)
    return (
        f"CALL algo.MSpaths({{{config}}}) "
        "YIELD path, pathCost RETURN path, pathCost"
    )


def _int_literal(value: int) -> str:
    """Render one id as an integer Cypher literal, e.g. ``990001``.

    algo.SSpaths' `sourceNode` must be a genuine INTEGER node id: a string
    (`'990001'`) is rejected with "sourceNode must be an integer node id", and
    the MSpaths-style sourceValues SET is rejected with "missing OpenCypher query
    parameter $sourceNode". As with `_ids_literal`, only a validated non-bool int
    is ever formatted into the query text, so there is no injection surface.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"sourceNode must be a non-bool int, got {type(value).__name__}: {value!r}")
    return str(value)


def build_fan_in_cypher(caps: Capabilities, settings: Settings,
                        source_id: int) -> str:
    """One algo.SSpaths query for the direct incoming CALLS callers of ONE fix
    site.

    SSpaths takes a single integer `sourceNode`, NOT the sourceValues SET that
    MSpaths accepts (see `friction.probe`'s `sspaths_source` probe), so fan-in
    over a set of fix sites issues one query per site and unions the callers
    client-side — `fan_in` does that. `maxLen: 1` restricts the result to direct
    callers; `pathCount` is set high (from Settings) because SSpaths otherwise
    returns a SINGLE shortest path, which would report every fan-in as 1.
    """
    if caps.sspaths_source_form != "sourceNode":
        # Only the integer sourceNode form has ever parsed on this engine; a
        # different probed value means the build changed underneath us, so fail
        # loudly rather than emit a form measured to reject on every call.
        raise ValueError(
            f"unsupported SSpaths source form {caps.sspaths_source_form!r}; "
            "only 'sourceNode' (integer) is implemented — re-probe the engine")
    config = ", ".join([
        f"sourceNode: {_int_literal(source_id)}",
        "relTypes: ['CALLS']",
        f"relDirection: '{caps.rel_direction_incoming}'",
        "maxLen: 1", f"pathCount: {settings.fan_in_path_count}",
    ])
    return f"CALL algo.SSpaths({{{config}}}) YIELD path RETURN path"


def extract_node_ids(path_value: Any) -> list[int]:
    """Normalise whatever shape the driver hands back into a list of node ids."""
    if path_value is None:
        return []
    if isinstance(path_value, dict):
        for key in ("nodes", "vertices", "path"):
            if key in path_value:
                return extract_node_ids(path_value[key])
        if "id" in path_value:
            return [int(path_value["id"])]
        return []
    if isinstance(path_value, (list, tuple)):
        out: list[int] = []
        for item in path_value:
            if isinstance(item, int):
                out.append(item)
            elif isinstance(item, dict) and "id" in item:
                out.append(int(item["id"]))
            elif hasattr(item, "get") and item.get("id") is not None:
                out.append(int(item["id"]))
            elif hasattr(item, "id"):
                out.append(int(item.id))
        return out
    nodes = getattr(path_value, "nodes", None)
    if nodes is not None:
        return extract_node_ids(list(nodes))
    return []


def fix_to_test_paths(transport, caps: Capabilities, settings: Settings,
                      fix_ids: list[int], test_ids: list[int],
                      rel_types: Sequence[str] = ("CALLS", "HAS_METHOD", "INHERITS")
                      ) -> PathSet:
    if not fix_ids or not test_ids:
        return PathSet([], [], "", 0.0, False)

    cypher = build_mspaths_cypher(caps, settings, rel_types, fix_ids, test_ids)
    start = time.perf_counter()
    # The id lists are inlined in `cypher`; the engine rejects a params dict for
    # sourceValues/targetValues, so none is passed.
    rows = transport.query(cypher)
    millis = (time.perf_counter() - start) * 1000.0

    parsed: list[list[int]] = []
    costs: list[float] = []
    for row in rows:
        ids = extract_node_ids(row.get("path"))
        if ids:
            parsed.append(ids)
            cost = row.get("pathCost")
            costs.append(float(cost) if cost is not None else float(len(ids) - 1))

    return PathSet(
        paths=parsed,
        costs=costs,
        cypher=cypher,
        millis=round(millis, 2),
        truncated=len(rows) >= settings.path_count,
    )


def fan_in(transport, caps: Capabilities, settings: Settings,
           fix_ids: list[int]) -> tuple[int, str, float, bool]:
    """Number of DISTINCT functions that call into the fix-site set via CALLS.

    algo.SSpaths is single-source (one integer `sourceNode` per call — see
    `build_fan_in_cypher`), so one query is issued per fix site and the incoming
    callers are unioned into a set here. The union is what makes the count
    correct: a function that calls two different fix sites is ONE distinct
    caller, so summing per-site row counts would over-report it — the set dedups
    it to one. Fix-site sets are small (median 1-3), so the extra round trips are
    cheap.

    Each length-1 path SSpaths returns is `[sourceNode, caller]`; the caller is
    the path node that is not the source. count(path) is rejected by this build,
    so the rows are counted (here, after deduplication) rather than by the engine.
    """
    if not fix_ids:
        return 0, "", 0.0, False

    callers: set[int] = set()
    statements: list[str] = []
    truncated = False
    start = time.perf_counter()
    for source_id in fix_ids:
        cypher = build_fan_in_cypher(caps, settings, source_id)
        statements.append(cypher)
        # The id is inlined in `cypher`; no params dict is passed (see build_*).
        rows = transport.query(cypher)
        # The query caps this fix site's returned rows at settings.fan_in_path_count.
        # A hub called by more functions than that is silently clipped, compressing
        # exactly the high-friction tail this metric exists to detect, so any site
        # hitting its cap is surfaced rather than swallowed (same bias direction as
        # the pathCount truncation the fidelity guard catches).
        if len(rows) >= settings.fan_in_path_count:
            truncated = True
        for row in rows:
            for node_id in extract_node_ids(row.get("path")):
                if node_id != source_id:
                    callers.add(node_id)
    millis = (time.perf_counter() - start) * 1000.0
    # One representative statement per fix site, joined so the run record shows
    # exactly what executed; the returned count is the size of the deduped union.
    cypher_repr = "\n".join(statements)
    return len(callers), cypher_repr, round(millis, 2), truncated

"""Path queries. The engine finds the paths; the arithmetic happens elsewhere.

`pairwise` is not documented in cypher-compat.md, so it is emitted only when the
capability probe proved the build accepts it. Without it the same call still
returns bounded paths between the fix-site set and the test-target set, which is
what the friction metric is defined over; the difference is how F1 is
normalised, and that is stated in the README.

Two engine facts, established by `friction.probe`, shape every query here:

* `algo.*` set queries match `sourceValues` / `targetValues` (lists of STRINGS)
  against a STRING property. Nodes carry a `sid` string mirror of their integer
  id for exactly this purpose, so these wrappers key on `sid` and convert every
  id to `str` before it reaches the engine. An integer list is a parse error;
  matching against the int `id` property parses but returns nothing.
* `count(path)` is rejected ("unknown path projection count"), so the fan-in
  query yields the paths and counts the returned rows client-side.
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


def _str_ids(ids: Sequence[int]) -> list[str]:
    """algo.* set queries reject an integer sourceValues/targetValues list and
    match the values against the STRING `sid` property, so every id crosses the
    wire as a string."""
    return [str(i) for i in ids]


def build_mspaths_cypher(caps: Capabilities, settings: Settings,
                         rel_types: Sequence[str]) -> str:
    parts = [
        "sourceLabel: 'Function'", "sourceProperty: 'sid'",
        "sourceValues: $fixIds",
        "targetLabel: 'Function'", "targetProperty: 'sid'",
        "targetValues: $testIds",
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


def build_fan_in_cypher(caps: Capabilities, settings: Settings) -> str:
    config = ", ".join([
        "sourceLabel: 'Function'", "sourceProperty: 'sid'",
        "sourceValues: $fixIds",
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

    cypher = build_mspaths_cypher(caps, settings, rel_types)
    start = time.perf_counter()
    rows = transport.query(
        cypher, {"fixIds": _str_ids(fix_ids), "testIds": _str_ids(test_ids)})
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
    if not fix_ids:
        return 0, "", 0.0, False
    cypher = build_fan_in_cypher(caps, settings)
    start = time.perf_counter()
    rows = transport.query(cypher, {"fixIds": _str_ids(fix_ids)})
    millis = (time.perf_counter() - start) * 1000.0
    # count(path) is rejected by this build, so the returned paths are counted
    # here rather than by the engine.
    count = len(rows)
    # The query caps returned rows at settings.fan_in_path_count. A hub function
    # with more than that many incoming CALLS is silently clipped, compressing
    # exactly the high-friction tail this metric exists to detect, so hitting the
    # cap is surfaced rather than swallowed (same bias direction as the pathCount
    # truncation the fidelity guard catches).
    truncated = count >= settings.fan_in_path_count
    return count, cypher, round(millis, 2), truncated

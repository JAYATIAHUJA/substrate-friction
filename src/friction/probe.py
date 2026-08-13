"""Empirically establish which Cypher forms this engine build actually accepts.

`cypher-compat.md` documents the config keys for the `algo.*` procedures but
does NOT document `pairwise`, and shows `relDirection` only as lowercase
`'both'`. It also states restrictions ("UNWIND MATCH must end in RETURN or
DELETE", "UNWIND ... CREATE cannot be followed by another clause") that
contradict the obvious edge-loading form. Rather than guess, probe.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from friction.client import EngineError
from friction.config import Settings


class ProbeFailure(RuntimeError):
    """No candidate form parsed for a capability the build depends on."""


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str
    statement: str


@dataclass(frozen=True)
class Capabilities:
    rel_direction_both: str
    rel_direction_incoming: str
    pairwise_supported: bool
    sourceValues_type: str
    node_loader_form: str
    edge_loader_form: str
    http_params_supported: bool
    count_path_supported: bool


# Seed data every probe runs against. Ids are far above any real symbol id.
# Every node carries a STRING `sid` mirror of its integer id: algo.* set queries
# (MSpaths) match sourceValues/targetValues against a STRING property only —
# `sourceValues: [990001]` against the int `id` prop parses but matches nothing,
# and a bare integer list is rejected outright with "sourceValues must be a list
# of strings". `sid` is the property those queries actually match against.
SEED = [
    "CREATE (a:Probe {id: 990001, sid: '990001', name: 'a'})",
    "CREATE (b:Probe {id: 990002, sid: '990002', name: 'b'})",
    "CREATE (c:Probe {id: 990003, sid: '990003', name: 'c'})",
    "MATCH (a {id: 990001}) MATCH (b {id: 990002}) CREATE (a)-[:PCALLS]->(b)",
    "MATCH (b {id: 990002}) MATCH (c {id: 990003}) CREATE (b)-[:PCALLS]->(c)",
]


def _direction_stmt(value: str) -> str:
    return (
        "CALL algo.SSpaths({sourceNode: 990001, relTypes: ['PCALLS'], "
        f"maxLen: 3, relDirection: '{value}'}}) YIELD path RETURN path"
    )


def _mspaths_string_stmt(pairwise: bool) -> str:
    """MSpaths keyed on the STRING `sid` property with STRING sourceValues — the
    only form that both parses and matches nodes. `pairwise` toggles ONLY the
    pairwise key, so the pairwise probe differs from the sourceValues_type:string
    probe by exactly that one key and can never be confounded with a type error."""
    pw = "pairwise: true, " if pairwise else ""
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'sid', "
        "sourceValues: ['990001'], targetLabel: 'Probe', targetProperty: 'sid', "
        "targetValues: ['990003'], relTypes: ['PCALLS'], maxLen: 3, "
        f"{pw}pathCount: 5}}) YIELD path RETURN path"
    )


def _mspaths_int_stmt() -> str:
    """MSpaths with an INTEGER sourceValues list — rejected outright with
    "sourceValues must be a list of strings". Kept as a probe so the type
    failure mode is documented and can never again be mistaken for a missing
    `pairwise` key."""
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'id', "
        "sourceValues: [990001], targetLabel: 'Probe', targetProperty: 'id', "
        "targetValues: [990003], relTypes: ['PCALLS'], maxLen: 3, "
        "pathCount: 5}) YIELD path RETURN path"
    )


def _count_path_stmt() -> str:
    """The fan-in query shape the brief assumed: aggregate the yielded paths with
    `count(path)`. Rejected with "unknown path projection count" — callers must
    yield the paths and count them client-side instead."""
    return (
        "CALL algo.SSpaths({sourceNode: 990001, relTypes: ['PCALLS'], "
        "maxLen: 3, relDirection: 'both'}) YIELD path RETURN count(path) AS fan_in"
    )


NODE_LOADER_FORMS = {
    # Kept as a probe: documents that inline CREATE with an embedded label +
    # multiple properties is rejected ("UNWIND batch supports one-hop
    # relationships only" / not a legal vertex upsert).
    "create_inline": (
        "UNWIND $rows AS row CREATE (n:ProbeLoad {id: row.id, name: row.name})",
        {"rows": [{"id": 990101, "name": "x"}, {"id": 990102, "name": "y"}]},
    ),
    # Kept as a probe: documents that folding the label into the MERGE pattern is
    # rejected ("MERGE pattern matches only id; apply labels with SET").
    "merge_then_set": (
        "UNWIND $rows AS row MERGE (n:ProbeLoad {id: row.id}) SET n.name = row.name",
        {"rows": [{"id": 990103, "name": "x"}, {"id": 990104, "name": "y"}]},
    ),
    # The form that actually parses: MERGE by id, then apply exactly one label
    # and the properties via SET.
    "merge_set_label": (
        "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:ProbeLoad, n.prop = row.prop",
        {"rows": [{"id": 990110, "prop": "x"}, {"id": 990111, "prop": "y"}]},
    ),
}

EDGE_LOADER_FORMS = {
    "match_match_create": (
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD]->(b)",
        {"rows": [{"src": 990101, "dst": 990102}]},
    ),
    "single_pattern_create": (
        "UNWIND $rows AS row CREATE (a {id: row.src})-[:PLOAD2]->(b {id: row.dst})",
        {"rows": [{"src": 990105, "dst": 990106}]},
    ),
    "merge_then_create": (
        "UNWIND $rows AS row MERGE (a {id: row.src}) MERGE (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD3]->(b)",
        {"rows": [{"src": 990107, "dst": 990108}]},
    ),
    "match_create_return": (
        "UNWIND $rows AS row MATCH (a {id: row.src}) MATCH (b {id: row.dst}) "
        "CREATE (a)-[:PLOAD4]->(b) RETURN a.id AS id",
        {"rows": [{"src": 990101, "dst": 990102}]},
    ),
}


def _attempt(transport, name: str, cypher: str, params: dict | None = None) -> ProbeResult:
    try:
        transport.query(cypher, params)
        return ProbeResult(name, True, "", cypher)
    except EngineError as exc:
        return ProbeResult(name, False, str(exc)[:400], cypher)


def run_all(transport, http_transport=None) -> list[ProbeResult]:
    """Probe `transport` for every capability. The `http_params` capability
    characterises the HTTP transport specifically (see `friction.client`), so it
    is measured against `http_transport` when one is supplied; otherwise it falls
    back to `transport`. `main()` passes an explicit `HttpTransport` so the
    reported `http_params_supported` answers the question about HTTP, not Bolt."""
    results: list[ProbeResult] = []

    for stmt in SEED:
        _attempt(transport, "seed", stmt)

    for value in ("both", "BOTH", "Both"):
        results.append(_attempt(transport, f"rel_direction:{value}", _direction_stmt(value)))
    for value in ("incoming", "INCOMING", "in", "IN"):
        results.append(_attempt(transport, f"rel_direction:{value}", _direction_stmt(value)))

    # sourceValues TYPE, isolated from the pairwise key. The int form is
    # rejected for its value type; the string form parses and matches nodes.
    results.append(_attempt(transport, "sourceValues_type:int", _mspaths_int_stmt()))
    results.append(_attempt(transport, "sourceValues_type:string", _mspaths_string_stmt(pairwise=False)))
    # pairwise KEY. Identical to sourceValues_type:string except `pairwise: true`,
    # so a failure here can only mean the pairwise key, never the value type.
    results.append(_attempt(transport, "pairwise", _mspaths_string_stmt(pairwise=True)))
    # count(path) path projection — the fan-in aggregate shape.
    results.append(_attempt(transport, "count_path", _count_path_stmt()))

    for form, (cypher, params) in NODE_LOADER_FORMS.items():
        results.append(_attempt(transport, f"node_loader:{form}", cypher, params))
    for form, (cypher, params) in EDGE_LOADER_FORMS.items():
        results.append(_attempt(transport, f"edge_loader:{form}", cypher, params))

    http_target = http_transport if http_transport is not None else transport
    results.append(_attempt(http_target, "http_params",
                            "UNWIND $rows AS row RETURN row.id AS id",
                            {"rows": [{"id": 1}]}))
    return results


def _first_ok(results: list[ProbeResult], prefix: str) -> str | None:
    for r in results:
        if r.name.startswith(prefix) and r.ok:
            return r.name.split(":", 1)[1]
    return None


def derive(results: list[ProbeResult]) -> Capabilities:
    both = _first_ok(results, "rel_direction:both") or _first_ok(results, "rel_direction:BOTH") \
        or _first_ok(results, "rel_direction:Both")
    if both is None:
        # try any direction probe that succeeded and looks like a "both" spelling
        for r in results:
            if r.name.startswith("rel_direction:") and r.ok and r.name.lower().endswith("both"):
                both = r.name.split(":", 1)[1]
                break
    if both is None:
        raise ProbeFailure(
            "no relDirection spelling for bidirectional traversal parsed; "
            "inspect docs/engine-capabilities.md and cypher-compat.md"
        )

    incoming = None
    for spelling in ("incoming", "INCOMING", "in", "IN"):
        found = _first_ok(results, f"rel_direction:{spelling}")
        if found:
            incoming = found
            break
    if incoming is None:
        # Reverse-edge / blast-radius traversals depend on a legal incoming
        # literal. Aliasing it to the bidirectional 'both' literal would
        # silently traverse BOTH directions and produce over-broad reverse
        # reachability. Surface the negative result instead of hiding it.
        raise ProbeFailure(
            "no relDirection spelling for incoming/reverse traversal parsed; "
            "reverse-edge and blast-radius queries have no legal direction "
            "literal — inspect docs/engine-capabilities.md and cypher-compat.md"
        )

    # sourceValues TYPE for algo.* set queries. Prefer the string form, since
    # it is the one that both parses and matches nodes; fall back to int only if
    # somehow that is the accepted type. If neither parses, MSpaths is unusable
    # and every set-to-set query is dead — surface it rather than emit a value
    # that would silently match nothing downstream.
    if _first_ok(results, "sourceValues_type:string"):
        source_values_type = "string"
    elif _first_ok(results, "sourceValues_type:int"):
        source_values_type = "int"
    else:
        raise ProbeFailure(
            "no sourceValues type parsed for algo.* set queries; MSpaths / F1 "
            "normalisation is unusable — inspect docs/engine-capabilities.md"
        )

    node_form = None
    for form in NODE_LOADER_FORMS:
        if _first_ok(results, f"node_loader:{form}"):
            node_form = form
            break
    if node_form is None:
        raise ProbeFailure("no UNWIND node-loading form parsed")

    edge_form = None
    for form in EDGE_LOADER_FORMS:
        if _first_ok(results, f"edge_loader:{form}"):
            edge_form = form
            break
    if edge_form is None:
        raise ProbeFailure("no UNWIND edge-loading form parsed")

    return Capabilities(
        rel_direction_both=both,
        rel_direction_incoming=incoming,
        pairwise_supported=any(r.name == "pairwise" and r.ok for r in results),
        sourceValues_type=source_values_type,
        node_loader_form=node_form,
        edge_loader_form=edge_form,
        http_params_supported=any(r.name == "http_params" and r.ok for r in results),
        count_path_supported=any(r.name == "count_path" and r.ok for r in results),
    )


def write_report(results: list[ProbeResult], caps: Capabilities, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Engine capabilities — measured, not assumed",
        "",
        "Generated by `friction.probe` against the pinned engine build. "
        "Every downstream query form is chosen from this table.",
        "",
        "```json",
        json.dumps(asdict(caps), indent=2, sort_keys=True),
        "```",
        "",
        "| Probe | Result | Engine message |",
        "|---|---|---|",
    ]
    for r in results:
        status = "PARSES" if r.ok else "REJECTED"
        detail = r.detail.replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| `{r.name}` | {status} | {detail} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_capabilities(path: Path) -> Capabilities:
    text = Path(path).read_text(encoding="utf-8")
    start = text.index("```json") + len("```json")
    end = text.index("```", start)
    return Capabilities(**json.loads(text[start:end]))


def main() -> None:
    from friction.client import connect

    settings = Settings.from_env()
    # Bolt drives every probe except http_params. The http_params probe must
    # characterise the HTTP transport (client.py's contract), so it is measured
    # against an HTTP transport explicitly rather than against whatever single
    # transport ran the rest.
    transport = connect(settings, prefer="bolt")
    http_transport = connect(settings, prefer="http")
    results = run_all(transport, http_transport)
    caps = derive(results)
    write_report(results, caps, Path("docs/engine-capabilities.md"))
    print(json.dumps(asdict(caps), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

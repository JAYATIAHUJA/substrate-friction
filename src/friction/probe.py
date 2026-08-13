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
    node_loader_form: str
    edge_loader_form: str
    http_params_supported: bool


# Seed data every probe runs against. Ids are far above any real symbol id.
SEED = [
    "CREATE (a:Probe {id: 990001, name: 'a'})",
    "CREATE (b:Probe {id: 990002, name: 'b'})",
    "CREATE (c:Probe {id: 990003, name: 'c'})",
    "MATCH (a {id: 990001}) MATCH (b {id: 990002}) CREATE (a)-[:PCALLS]->(b)",
    "MATCH (b {id: 990002}) MATCH (c {id: 990003}) CREATE (b)-[:PCALLS]->(c)",
]


def _direction_stmt(value: str) -> str:
    return (
        "CALL algo.SSpaths({sourceNode: 990001, relTypes: ['PCALLS'], "
        f"maxLen: 3, relDirection: '{value}'}}) YIELD path RETURN path"
    )


def _pairwise_stmt() -> str:
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'id', "
        "sourceValues: [990001], targetLabel: 'Probe', targetProperty: 'id', "
        "targetValues: [990003], relTypes: ['PCALLS'], maxLen: 3, "
        "pairwise: true, pathCount: 5}) YIELD path RETURN path"
    )


def _mspaths_baseline_stmt() -> str:
    return (
        "CALL algo.MSpaths({sourceLabel: 'Probe', sourceProperty: 'id', "
        "sourceValues: [990001], targetLabel: 'Probe', targetProperty: 'id', "
        "targetValues: [990003], relTypes: ['PCALLS'], maxLen: 3, "
        "pathCount: 5}) YIELD path RETURN path"
    )


NODE_LOADER_FORMS = {
    "create_inline": (
        "UNWIND $rows AS row CREATE (n:ProbeLoad {id: row.id, name: row.name})",
        {"rows": [{"id": 990101, "name": "x"}, {"id": 990102, "name": "y"}]},
    ),
    # Global constraints: "Vertex upsert must be MERGE by id followed by SET —
    # folding extra properties into the MERGE pattern is rejected." The label
    # therefore cannot live in the MERGE pattern; it is applied with SET.
    "merge_then_set": (
        "UNWIND $rows AS row MERGE (n {id: row.id}) SET n:ProbeLoad, n.name = row.name",
        {"rows": [{"id": 990103, "name": "x"}, {"id": 990104, "name": "y"}]},
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

    results.append(_attempt(transport, "mspaths_baseline", _mspaths_baseline_stmt()))
    results.append(_attempt(transport, "pairwise", _pairwise_stmt()))

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
        node_loader_form=node_form,
        edge_loader_form=edge_form,
        http_params_supported=any(r.name == "http_params" and r.ok for r in results),
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

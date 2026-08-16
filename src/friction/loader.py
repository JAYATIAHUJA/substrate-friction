"""Stage graph rows as NDJSON, then load them with UNWIND $rows batches.

The exact statement shapes come from the capability probe rather than from
assumption: `cypher-compat.md` restricts UNWIND forms in ways that rule out the
obvious MATCH/MATCH/CREATE edge loader on this build.

Measured against the live engine (docs/engine-capabilities.md):

* The ONLY vertex upsert that parses is MERGE by id, then apply exactly one
  label and every property via SET — keyed `merge_set_label`. The brief's
  `create_inline` and `merge_then_set` are both rejected; they are kept in
  NODE_FORMS only so the loader can still emit them for documentation, but the
  form is selected from the probed Capabilities, not hardcoded.
* Every node row carries `sid = str(id)` as a STRING property in addition to the
  integer `id`. `algo.MSpaths` matches sourceValues/targetValues against a
  string property only; without `sid` the path queries match nothing.
* Loading requires the Bolt transport: HTTP does not accept `$params` for
  UNWIND (`http_params_supported` is false).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable
from friction.probe import Capabilities

NODE_FORMS = {
    # Rejected by the live engine ("UNWIND batch supports one-hop relationships
    # only") — kept for documentation of what does NOT parse.
    "create_inline":
        "UNWIND $rows AS row CREATE (n:{label} {{{props}}})",
    # Rejected ("MERGE pattern matches only id; apply labels with SET") — kept
    # for documentation.
    "merge_then_set":
        "UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET {sets}",
    # The only form that parses: MERGE by id, then apply one label plus every
    # property via SET.
    "merge_set_label":
        "UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{label}, {sets}",
}

# The live engine rejects relationship properties in an UNWIND batch:
# "UNWIND batch requires one fixed relationship type without properties". The
# edge weight is preserved in edges.ndjson but cannot ride on the relationship,
# so no form carries `{weight: ...}`.
EDGE_FORMS = {
    "match_match_create":
        "UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel}]->(b)",
    # The form the live engine accepts: a single one-hop directed CREATE.
    "single_pattern_create":
        "UNWIND $rows AS row "
        "CREATE (a {{id: row.src}})-[:{rel}]->(b {{id: row.dst}})",
    "merge_then_create":
        "UNWIND $rows AS row MERGE (a {{id: row.src}}) MERGE (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel}]->(b)",
    "match_create_return":
        "UNWIND $rows AS row MATCH (a {{id: row.src}}) MATCH (b {{id: row.dst}}) "
        "CREATE (a)-[:{rel}]->(b) RETURN a.id AS id",
}

# `sid` (a STRING mirror of the integer id) is mandatory on every label so that
# algo.* set queries can address the nodes; see module docstring.
NODE_PROPS = {
    "File": ["id", "sid", "path", "repo", "loc"],
    "Class": ["id", "sid", "name", "file_id"],
    "Function": ["id", "sid", "name", "file_id", "line_start", "line_end",
                 "cyclomatic", "is_test"],
    # The typed arm (friction.arms.emit_typed_arm) keys Function/Test/Class nodes
    # by their SCIP canonical (`qual`) rather than a tree-sitter file_id, and adds
    # two labels the v1 SymbolTable never produced. `load` derives the SET props
    # from the rows themselves, so these entries document the typed-arm shape and
    # back `node_statement` for the two new labels.
    "Test": ["id", "sid", "name", "qual", "is_test"],
    "ConfigKey": ["id", "sid", "name"],
}


def emit_ndjson(table: SymbolTable, edges: list[Edge], out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = out_dir / "nodes.ndjson"
    edges_path = out_dir / "edges.ndjson"

    with nodes_path.open("w", encoding="utf-8") as fh:
        for f in table.files:
            fh.write(json.dumps({"label": "File", "id": f.id, "sid": str(f.id),
                                 "path": f.path, "repo": f.repo, "loc": f.loc}) + "\n")
        for c in table.classes:
            fh.write(json.dumps({"label": "Class", "id": c.id, "sid": str(c.id),
                                 "name": c.name, "file_id": c.file_id}) + "\n")
        for fn in table.functions:
            fh.write(json.dumps({"label": "Function", "id": fn.id, "sid": str(fn.id),
                                 "name": fn.name, "file_id": fn.file_id,
                                 "line_start": fn.line_start, "line_end": fn.line_end,
                                 "cyclomatic": fn.cyclomatic,
                                 "is_test": fn.is_test}) + "\n")

    with edges_path.open("w", encoding="utf-8") as fh:
        for e in edges:
            fh.write(json.dumps({"src": e.src, "dst": e.dst,
                                 "type": e.type, "weight": e.weight}) + "\n")

    return {"nodes": nodes_path, "edges": edges_path}


def node_statement_for(caps: Capabilities, label: str, props: list[str]) -> str:
    """Build the upsert statement for ``label`` over an EXPLICIT prop list.

    The live engine's UNWIND checks every referenced field against every row, so
    the SET clause must name exactly the props the rows carry — no more. This
    variant takes the prop list explicitly so ``load`` can derive it from the
    rows themselves (schema-adaptive), while ``node_statement`` keeps the fixed
    v1 ``NODE_PROPS`` contract its tests pin.
    """
    template = NODE_FORMS[caps.node_loader_form]
    if caps.node_loader_form == "create_inline":
        body = ", ".join(f"{p}: row.{p}" for p in props)
        return template.format(label=label, props=body)
    sets = ", ".join(f"n.{p} = row.{p}" for p in props if p != "id")
    return template.format(label=label, sets=sets)


def node_statement(caps: Capabilities, label: str) -> str:
    return node_statement_for(caps, label, NODE_PROPS[label])


def edge_statement(caps: Capabilities, rel_type: str) -> str:
    return EDGE_FORMS[caps.edge_loader_form].format(rel=rel_type)


def _read_ndjson(path: Path):
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def load(transport, caps: Capabilities, out_dir: Path,
         batch_size: int = 1000) -> dict[str, int]:
    out_dir = Path(out_dir)
    counts: dict[str, int] = defaultdict(int)

    by_label: dict[str, list[dict]] = defaultdict(list)
    for row in _read_ndjson(out_dir / "nodes.ndjson"):
        label = row.pop("label")
        by_label[label].append(row)

    # All nodes before any edges. Load File/Class before Function (edge
    # endpoints), then any other label the file carries. Deriving the SET props
    # from the rows themselves keeps this loader schema-agnostic: v1 graph nodes
    # carry NODE_PROPS[label]; the Task-7 arm nodes carry a leaner {sid,name,qual}.
    # A fixed v1-shaped statement rejected every arm batch on the live engine
    # ("UNWIND row 0 is missing field cyclomatic").
    ordered = ["File", "Class", "Function", "Test", "ConfigKey"]
    labels = ordered + [lbl for lbl in by_label if lbl not in ordered]
    for label in labels:
        rows = by_label.get(label, [])
        if not rows:
            continue
        props = list(rows[0].keys())  # rows are uniform per label in every emit
        statement = node_statement_for(caps, label, props)
        for chunk in _chunks(rows, batch_size):
            transport.query(statement, {"rows": chunk})
        counts[label] += len(rows)

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in _read_ndjson(out_dir / "edges.ndjson"):
        by_type[row.pop("type")].append(row)

    for rel_type, rows in sorted(by_type.items()):
        statement = edge_statement(caps, rel_type)
        for chunk in _chunks(rows, batch_size):
            transport.query(statement, {"rows": chunk})
        counts[rel_type] += len(rows)

    return dict(counts)


def main() -> None:
    """`python -m friction.loader --dir <dir>` — load nodes.ndjson/edges.ndjson
    from `--dir` into the live engine over Bolt. Used by setup.sh to load the
    shipped pre-built subgraphs; the console script is otherwise unreachable."""
    import argparse

    from friction.client import connect
    from friction.config import Settings
    from friction.probe import load_capabilities

    parser = argparse.ArgumentParser(prog="friction.loader")
    parser.add_argument("--dir", default="data/shipped",
                        help="directory holding nodes.ndjson and edges.ndjson")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--caps", default="docs/engine-capabilities.md",
                        help="capability report emitted by `python -m friction.probe`")
    args = parser.parse_args()

    # The engine's admission control rejects any UNWIND batch over 1024 items
    # ("client_query_batch_items rejected by admission control: actual N exceeds
    # limit 1024"), so clamp regardless of what was requested.
    batch_size = min(args.batch_size, 1024)

    caps = load_capabilities(Path(args.caps))
    transport = connect(Settings.from_env(), prefer="bolt")
    try:
        counts = load(transport, caps, Path(args.dir), batch_size=batch_size)
    finally:
        transport.close()
    total = sum(counts.values())
    print(json.dumps(counts, sort_keys=True))
    print(f"loaded {total} rows from {args.dir}")


if __name__ == "__main__":
    main()

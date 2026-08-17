#!/usr/bin/env python
"""P7: the certified edge list — every compared edge with its trust label.

Emits data/shipped/consensus.json: the 5,873 compared arm-A edges, each
labelled `confirmed` (arm B agrees) or `name_only` (unconfirmed), with
provenance. Refuses to emit unless the join reproduces docs/graph-delta.md
exactly (same gate as edge_taxonomy).

    uv run python scripts/build_consensus.py --out data/shipped/consensus.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from friction.identity import discover_scip_prefix, joined_edge_sets
from friction.namematch.graph import build as build_arm_a
from friction.scip.extract import extract_edges
from friction.scip.schema import load_index


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    arm_a, _ = build_arm_a(Path("data/repos/django"))
    index = load_index(Path("data/instances/arms/django__django-10097/index.scip"))
    arm_b, _ = extract_edges(index)
    prefix = discover_scip_prefix(index) + "django."
    a_set, b_set, _ = joined_edge_sets(arm_a, arm_b, prefix, "django")

    both, only_a = a_set & b_set, a_set - b_set
    if (len(a_set), len(both), len(only_a)) != (5873, 4381, 1492):
        raise SystemExit("join does not reproduce graph-delta — refusing")

    edges = ([{"src": s, "dst": d, "trust": "confirmed",
               "arms": ["name_matched", "type_resolved"]}
              for s, d in sorted(both)]
             + [{"src": s, "dst": d, "trust": "name_only",
                 "arms": ["name_matched"]} for s, d in sorted(only_a)])
    args.out.write_text(json.dumps({
        "commit": "b9cf764be62e77b4777b3a75ec256f6209a57671",
        "engine_digest": "sha256:db78309a233be54662db29744047e985a39b51c45a270d1a1f47c31a62cdb709",
        "note": ("compared space only; arm B additionally holds "
                 f"{len(b_set - a_set)} type-resolved edges arm A misses "
                 "(the recall gap) — counted here, not enumerated, to keep "
                 "the artifact small"),
        "counts": {"confirmed": len(both), "name_only": len(only_a),
                   "b_only": len(b_set - a_set)},
        "edges": edges}, indent=1), encoding="utf-8")
    print(f"wrote {args.out}: confirmed={len(both)} name_only={len(only_a)}")


if __name__ == "__main__":
    main()

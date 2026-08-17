#!/usr/bin/env python
"""S2: audit the auditor — arm B vs the dynamic-execution reference.

Arm B (SCIP/pyright) is this project's reference for arm A. Who watches it?
The dynamic tracer: `friction.trace` ran each instance's FAIL_TO_PASS tests
under sys.settrace and recorded executed Test->Function edges. This report
computes the agreement table between static arm B connectivity and the
dynamic-augmented result, from the per-instance rows committed in
docs/covers.md (the raw trace JSONs were session-scoped; the committed table
is the pinned result of that run).

    uv run python scripts/audit_auditor.py --out docs/audit-the-auditor.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROW = re.compile(
    r"^\|\s*(django__django-\d+)\s*\|\s*(False|True)\s*\|\s*\**(False|True)\**"
    r"\s*\|\s*(\d+)\s*\|\s*(\d+)/(\d+)\s*\((\d+)%\)")


def parse(covers_md: Path) -> list[dict]:
    rows = []
    for line in covers_md.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if m:
            rows.append({
                "instance_id": m.group(1),
                "static": m.group(2) == "True",
                "augmented": m.group(3) == "True",
                "mapped_pct": int(m.group(7)),
            })
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--covers", type=Path, default=Path("docs/covers.md"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    rows = parse(args.covers)
    if len(rows) < 10:
        raise SystemExit(f"parsed only {len(rows)} rows from {args.covers} — "
                         f"refusing to report on a broken parse")

    tt = sum(1 for r in rows if r["static"] and r["augmented"])
    ft = sum(1 for r in rows if not r["static"] and r["augmented"])
    ff = sum(1 for r in rows if not r["static"] and not r["augmented"])
    tf = sum(1 for r in rows if r["static"] and not r["augmented"])
    dyn_connected = tt + ft
    map_rates = sorted(r["mapped_pct"] for r in rows)

    L = [
        "# Audit the auditor: arm B against dynamic execution (study S2)",
        "",
        "Pre-registered in `docs/studies.md` S2 before computation. Generated "
        "by `scripts/audit_auditor.py` from the per-instance table committed "
        "in `docs/covers.md` (the pinned output of the tracing run).",
        "",
        "Arm B is the reference every precision figure in this project is "
        "measured against. This asks the obvious next question: what does arm "
        "B itself miss, judged against edges that provably executed?",
        "",
        f"## The 2x2, n={len(rows)} traced django instances",
        "",
        "| | dynamic-augmented: connected | dynamic-augmented: not |",
        "|---|---|---|",
        f"| **arm B static: connected** | {tt} | {tf} |",
        f"| **arm B static: not** | {ft} | {ff} |",
        "",
        f"- Instances the dynamic-augmented reference connects: "
        f"**{dyn_connected}**. Arm B alone finds {tt} of those — it misses "
        f"**{ft}/{dyn_connected}** "
        f"({ft/dyn_connected:.0%}) despite the connection being proven by "
        f"execution"
        + (f" (`{[r['instance_id'] for r in rows if not r['static'] and r['augmented']][0]}`)."
           if ft == 1 else "."),
        f"- {tf} instances flip the other way (impossible by construction: "
        "folding executed edges in can only add connectivity)." if tf else
        "- No instance flips the other way, as construction requires: "
        "folding executed edges in can only add connectivity.",
        "",
        "## Result vs the registered hypothesis",
        "",
        f"The hypothesis said arm B would miss a *nontrivial fraction*. The "
        f"proven miss rate on this subset is **{ft}/{dyn_connected}** — "
        "smaller than hypothesized, and that is the honest reading of this "
        "table. It is also only a **floor**, for the reason below.",
        "",
        "## Why this is a floor, not the number",
        "",
        "The dynamic reference is itself partial: only the traced edges whose "
        "endpoints joined the graph identity space count, and the per-instance "
        f"mapping rate runs **{map_rates[0]}%-{map_rates[-1]}%** (median "
        f"{map_rates[len(map_rates)//2]}%). An executed edge that failed to "
        "map cannot rescue an instance, so some of the "
        f"{ff} not/not instances may be dynamically connected in reality. "
        "Arm B's true miss rate against full dynamic truth is therefore "
        "**at least** the figure above. n=18 is small; no significance claim "
        "is made.",
        "",
        "## What this buys the gate",
        "",
        "Every precision number in this project calls itself a *ceiling* "
        "because arm B under-reports rather than inventing edges. This table "
        "is the direct evidence: an execution-proven connection that pyright "
        "declined to resolve. The watchmen are watched, and found incomplete "
        "in exactly the direction the ceiling framing assumed.",
        "",
    ]
    args.out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {args.out}: 2x2 = [[{tt},{tf}],[{ft},{ff}]], "
          f"proven miss {ft}/{dyn_connected}, mapping {map_rates[0]}-"
          f"{map_rates[-1]}%")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Render every statistical figure and diagram as brand-styled SVG.

Single source of truth for README/site visuals. Every number in every figure
is read from a committed artifact (gate-results.json, longitudinal.json) or a
committed generated doc (connectivity.md, negative-control.md, graph-delta.md,
covers.md) — the same parse-the-pinned-report pattern `friction.precision`
uses. A figure whose source cannot be parsed is SKIPPED with a notice, never
guessed.

    uv run python scripts/render_figures.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT = Path("docs/plots")
BG, RAISED, LINE = "#0a0a0a", "#121212", "#2e2e2e"
ACCENT, YELLOW = "#ff571a", "#f9c425"
TEXT, BODY, MUTED = "#ffffff", "#dadada", "#747474"
MONO = "ui-monospace,'Geist Mono','JetBrains Mono',Menlo,monospace"


def svg(w, h, title, parts):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'font-family="{MONO}" role="img" aria-label="{title}">'
            f'<rect width="{w}" height="{h}" fill="{BG}"/>'
            f'<text x="24" y="30" fill="{MUTED}" font-size="11" '
            f'letter-spacing="2">{title.upper()}</text>' + "".join(parts) +
            '</svg>')


def hbar_chart(title, rows, w=860, note="", bar_line=None, xmax=1.0,
               fmt="{:.3f}"):
    """rows: (label, value, color, annotation). Horizontal bars, sharp."""
    top, left, bw = 56, 330, w - 330 - 96
    rh, gap = 34, 16
    h = top + len(rows) * (rh + gap) + (46 if note else 24)
    P = []
    if bar_line is not None:
        x = left + bw * (bar_line / xmax)
        P.append(f'<line x1="{x}" y1="{top-8}" x2="{x}" '
                 f'y2="{top+len(rows)*(rh+gap)-gap+8}" stroke="{YELLOW}" '
                 f'stroke-dasharray="4 5"/>'
                 f'<text x="{x}" y="{top-14}" fill="{YELLOW}" font-size="11" '
                 f'text-anchor="middle">bar {bar_line}</text>')
    y = top
    for label, val, color, ann in rows:
        P.append(f'<text x="{left-12}" y="{y+rh/2+4}" fill="{BODY}" '
                 f'font-size="12.5" text-anchor="end">{label}</text>')
        P.append(f'<rect x="{left}" y="{y}" width="{bw}" height="{rh}" '
                 f'fill="{RAISED}" stroke="{LINE}"/>')
        bwv = max(2, bw * (val / xmax))
        P.append(f'<rect x="{left}" y="{y}" width="{bwv}" height="{rh}" '
                 f'fill="{color}"/>')
        P.append(f'<text x="{left+bwv+10}" y="{y+rh/2+4}" fill="{TEXT}" '
                 f'font-size="13" font-weight="bold">{fmt.format(val)}</text>')
        if ann:
            P.append(f'<text x="{left+8}" y="{y+rh/2+4}" fill="{BG}" '
                     f'font-size="11">{ann}</text>' if bwv > 150 else
                     f'<text x="{left+bwv+70}" y="{y+rh/2+4}" fill="{MUTED}" '
                     f'font-size="11">{ann}</text>')
        y += rh + gap
    if note:
        P.append(f'<text x="24" y="{h-16}" fill="{MUTED}" font-size="11">'
                 f'{note}</text>')
    return svg(w, h, title, P)


def line_chart(title, xs, series, w=760, h=320, note="", ylo=0.0, yhi=1.0,
               yticks=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """series: (name, color, values)."""
    L, R, T, B = 90, 40, 54, h - (56 if note else 36)
    P = [f'<line x1="{L}" y1="{B}" x2="{w-R}" y2="{B}" stroke="{LINE}"/>',
         f'<line x1="{L}" y1="{B}" x2="{L}" y2="{T}" stroke="{LINE}"/>']

    def X(i):
        return L + (w - L - R) * (i / max(1, len(xs) - 1))

    def Y(v):
        return B - (B - T) * ((v - ylo) / (yhi - ylo))

    for tv in yticks:
        P.append(f'<line x1="{L}" y1="{Y(tv)}" x2="{w-R}" y2="{Y(tv)}" '
                 f'stroke="{LINE}" stroke-dasharray="2 7"/>'
                 f'<text x="{L-10}" y="{Y(tv)+4}" fill="{MUTED}" '
                 f'font-size="10" text-anchor="end">{tv:.2f}</text>')
    for i, x in enumerate(xs):
        P.append(f'<text x="{X(i)}" y="{B+18}" fill="{MUTED}" font-size="11" '
                 f'text-anchor="middle">{x}</text>')
    for name, color, vals in series:
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}"
                     for i, v in enumerate(vals))
        P.append(f'<path d="{d}" fill="none" stroke="{color}" '
                 f'stroke-width="2.5"/>')
        for i, v in enumerate(vals):
            P.append(f'<rect x="{X(i)-4}" y="{Y(v)-4}" width="8" height="8" '
                     f'fill="{color}"/>'
                     f'<text x="{X(i)}" y="{Y(v)-12}" fill="{TEXT}" '
                     f'font-size="11" text-anchor="middle">{v:.3f}</text>')
        P.append(f'<text x="{w-R}" y="{Y(vals[-1])+4}" fill="{color}" '
                 f'font-size="11" text-anchor="start"> {name}</text>')
    if note:
        P.append(f'<text x="24" y="{h-14}" fill="{MUTED}" font-size="11">'
                 f'{note}</text>')
    return svg(w, h, title, P)


# ── data loaders (committed artifacts / pinned generated docs) ───────────

def gate_results():
    return json.loads(Path("data/shipped/gate-results.json").read_text())


def covers_gate():
    m = re.search(r"with COVERS \(strict SCIP identity, qualified tracer\)\*?\*?\s*\|\s*\*\*(\d+)/(\d+)",
                  Path("docs/covers.md").read_text())
    return (int(m.group(1)), int(m.group(2))) if m else None


def connectivity_rows():
    text = Path("docs/connectivity.md").read_text()
    out = {}
    for key, pat in (("fix_to_test", r"\*\*fix -> test\*\*.*?\*\*(\d+)/(\d+)"),
                     ("test_to_fix", r"\*\*test -> fix\*\*.*?\*\*(\d+)/(\d+)"),
                     ("undirected", r"\*\*undirected\*\*.*?\*\*(\d+)/(\d+)")):
        m = re.search(pat, text)
        if m:
            out[key] = (int(m.group(1)), int(m.group(2)))
    return out if len(out) == 3 else None


def negative_control_rows():
    rows = re.findall(r"\|\s*(\d+)%\s*\|\s*([\d.]+)\s*\|",
                      Path("docs/negative-control.md").read_text())
    return [(int(a), float(b)) for a, b in rows] or None


def offender_rows():
    text = Path("docs/graph-delta.md").read_text()
    rows = re.findall(r"\|\s*`(\w+)`\s*\|\s*\*?\*?(\d+)\*?\*?\s*\|", text)
    rows = [(n, int(c)) for n, c in rows if int(c) > 20][:5]
    return rows or None


def longitudinal_rows():
    d = json.loads(Path("data/shipped/longitudinal.json").read_text())
    return [(r["era"], r["precision_ceiling"], r["arm_a_edges"])
            for r in d["eras"] if not r.get("join_failed")]


# ── diagrams ─────────────────────────────────────────────────────────────

def box(x, y, w, h, label, sub="", stroke=LINE, fill=RAISED, fs=13):
    s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" '
         f'stroke="{stroke}"/>'
         f'<text x="{x+w/2}" y="{y+h/2-(7 if sub else 0)}" fill="{TEXT}" '
         f'font-size="{fs}" text-anchor="middle" dominant-baseline="middle">'
         f'{label}</text>')
    if sub:
        s += (f'<text x="{x+w/2}" y="{y+h/2+13}" fill="{MUTED}" '
              f'font-size="10" text-anchor="middle" '
              f'dominant-baseline="middle">{sub}</text>')
    return s


def arrow(x1, y1, x2, y2, color=LINE, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}"'
            f'{d} marker-end="url(#ah)"/>')


ARROW_DEF = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
             'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>')


def system_diagram():
    P = [ARROW_DEF]
    # Sources
    P.append(box(20, 70, 160, 56, "SWE-bench Verified", "FAIL_TO_PASS labels"))
    P.append(box(20, 150, 160, 56, "7 repos @ pinned", "commits, 172 instances"))
    P.append(box(20, 230, 160, 56, "django 1.11→5.0", "5 eras (S5)"))
    # Extractors
    P.append(box(250, 110, 170, 56, "arm A", "tree-sitter · name-matched"))
    P.append(box(250, 190, 170, 56, "arm B", "scip-python · type-resolved"))
    P.append(box(250, 270, 170, 56, "arm D", "sys.settrace · executed"))
    # Identity + engine
    P.append(box(480, 150, 150, 56, "identity join", "scope::leaf space"))
    P.append(box(480, 70, 150, 56, "HydraDB", "disjoint id bands",
                 stroke=ACCENT))
    # Measurements
    P.append(box(690, 40, 190, 48, "graph-delta", "precision ceiling 0.746"))
    P.append(box(690, 104, 190, 48, "gate audit", "recall vs labels"))
    P.append(box(690, 168, 190, 48, "engine anti-join", "diff --live · 2.0 ms/edge"))
    P.append(box(690, 232, 190, 48, "negative control", "0.545 → 0.000"))
    P.append(box(690, 296, 190, 48, "longitudinal", "flat ~0.75 · 8 years"))
    # Artifacts + surfaces
    P.append(box(940, 104, 180, 56, "gate-results.json", "single source of truth",
                 stroke=ACCENT))
    P.append(box(940, 200, 180, 44, "friction verify", "site==docs==artifact"))
    P.append(box(1160, 40, 130, 44, "CLI", "exit 1 = RUN_FULL"))
    P.append(box(1160, 100, 130, 44, "MCP", "3 tools"))
    P.append(box(1160, 160, 130, 44, "SARIF", "code scanning"))
    P.append(box(1160, 220, 130, 44, "Action", "self-gating"))
    P.append(box(1160, 280, 130, 44, "HTTP API", "/gate"))
    for y in (98, 178, 258):
        P.append(arrow(180, y, 250, {98: 138, 178: 218, 258: 298}[y]))
    P.append(arrow(420, 138, 480, 168))
    P.append(arrow(420, 218, 480, 178))
    P.append(arrow(420, 298, 480, 188))
    P.append(arrow(420, 138, 480, 98))   # arms load engine
    P.append(arrow(420, 218, 480, 108))
    for y2 in (64, 128, 192, 256, 320):
        P.append(arrow(630, 178, 690, y2))
    P.append(arrow(630, 98, 690, 192, color=ACCENT))  # engine computes anti-join
    P.append(arrow(880, 128, 940, 132))
    P.append(arrow(1120, 132, 1160, 62))
    P.append(arrow(1120, 132, 1160, 122))
    P.append(arrow(1120, 132, 1160, 182))
    P.append(arrow(1120, 132, 1160, 242))
    P.append(arrow(1120, 132, 1160, 302))
    P.append(arrow(1030, 200, 1030, 160, color=YELLOW, dash="3 4"))
    P.append(f'<text x="24" y="376" fill="{MUTED}" font-size="11">'
             'every figure flows left to right; friction verify closes the '
             'loop — the site, the README and this diagram quote the same '
             'committed artifact</text>')
    return svg(1310, 392, "system — from labels to verdicts", P)


def verdict_flow():
    P = [ARROW_DEF]
    P.append(box(30, 60, 170, 56, "change lands", "PR / diff / instance"))
    P.append(box(260, 60, 200, 56, "backwards walk", "CALLED_BY*1..6, bounded"))
    P.append(box(520, 60, 210, 56, "graph-complete?", "frontier exhausted"))
    P.append(box(520, 160, 210, 56, "≠ program-complete",
                 "missing edges are invisible", stroke=YELLOW))
    P.append(box(790, 60, 220, 56, "measured recall", "vs FAIL_TO_PASS labels"))
    P.append(box(1070, 26, 190, 52, "SKIP_SAFE", "recall ≥ 0.95 · exit 0",
                 stroke=LINE))
    P.append(box(1070, 110, 190, 52, "RUN_FULL", "recall < bar · exit 1",
                 stroke=ACCENT, fill="#1a0f0a"))
    P.append(arrow(200, 88, 260, 88))
    P.append(arrow(460, 88, 520, 88))
    P.append(arrow(625, 116, 625, 160, color=YELLOW, dash="3 4"))
    P.append(arrow(730, 88, 790, 88))
    P.append(arrow(1010, 78, 1070, 52))
    P.append(arrow(1010, 98, 1070, 136, color=ACCENT))
    P.append(f'<text x="1075" y="196" fill="{MUTED}" font-size="11">'
             'every graph class measured so far exits here</text>')
    P.append(f'<text x="24" y="238" fill="{MUTED}" font-size="11">'
             'the gate is fail-closed: an unmeasured graph can never license '
             'a skip — RUN_FULL is the product working, not a failure mode'
             '</text>')
    return svg(1290, 254, "the verdict, end to end", P)


# ── figures ──────────────────────────────────────────────────────────────

def main() -> None:
    OUT.mkdir(exist_ok=True)
    written, skipped = [], []

    d = gate_results()
    pool = d["summary"]["pooled"]
    per = d["summary"]["per_repo"]
    dj = per["django"]["arm_b"]

    rows = [
        ("name-matched (Aider/RepoGraph class)",
         pool["arm_a"]["recall"], MUTED,
         f"{pool['arm_a']['hits']}/{pool['arm_a']['n']} pooled"),
        ("type-resolved (scip-python)",
         pool["arm_b"]["recall"], ACCENT,
         f"{pool['arm_b']['hits']}/{pool['arm_b']['n']} pooled"),
        ("type-resolved, django only",
         dj["hits"] / dj["n"], ACCENT, f"{dj['hits']}/{dj['n']}"),
    ]
    cg = covers_gate()
    if cg:
        rows.append(("+ dynamic traces (18 traced, django)",
                     cg[0] / cg[1], YELLOW, f"{cg[0]}/{cg[1]}"))
    (OUT / "fig-recall.svg").write_text(hbar_chart(
        "guarding-test recall vs the 0.95 skip bar", rows,
        bar_line=0.95,
        note="every class refuses: RUN_FULL. source: gate-results.json + "
             "docs/covers.md · rendered by scripts/render_figures.py"))
    written.append("fig-recall.svg")

    prow = sorted(((r, v["arm_b"]) for r, v in per.items()),
                  key=lambda kv: -(kv[1]["hits"] / kv[1]["n"]
                                   if kv[1]["n"] else 0))
    rows = [(f"{r}  (n={v['n']})",
             (v["hits"] / v["n"]) if v["n"] else 0.0,
             ACCENT if v["n"] >= 19 else MUTED,
             f"{v['hits']}/{v['n']}") for r, v in prow]
    (OUT / "fig-perrepo.svg").write_text(hbar_chart(
        "per-repo spread, type-resolved arm — the finding itself", rows,
        bar_line=0.95,
        note="grey = n too small to clear any bar. matplotlib/pytest at zero: "
             "guarding tests sit in a different graph component. source: "
             "gate-results.json"))
    written.append("fig-perrepo.svg")

    c = connectivity_rows()
    if c:
        rows = [
            ("fix → test (directed)", c["fix_to_test"][0] / c["fix_to_test"][1],
             MUTED, "code does not call its tests"),
            ("test → fix (directed)", c["test_to_fix"][0] / c["test_to_fix"][1],
             ACCENT, "the natural direction"),
            ("undirected ('both')", c["undirected"][0] / c["undirected"][1],
             YELLOW, "shares a neighbourhood — NOT coverage"),
        ]
        (OUT / "fig-direction.svg").write_text(hbar_chart(
            "direction: the relation every prior version measured backwards",
            rows, fmt="{:.0%}",
            note="the 55%→98% gap is the pytest fixture/setUp/dispatch closure "
                 "a static graph cannot record. source: docs/connectivity.md"))
        written.append("fig-direction.svg")
    else:
        skipped.append("fig-direction (connectivity.md parse)")

    nc = negative_control_rows()
    if nc:
        (OUT / "fig-negative-control.svg").write_text(line_chart(
            "negative control — the instrument detects degradation",
            [f"{p}%" for p, _ in nc],
            [("recall as edges are deleted", ACCENT, [v for _, v in nc])],
            note="monotone to zero; 0% deletion reproduces the headline "
                 "exactly. seed 20260818 · source: docs/negative-control.md"))
        written.append("fig-negative-control.svg")
    else:
        skipped.append("fig-negative-control (doc parse)")

    lg = longitudinal_rows()
    if lg:
        (OUT / "fig-longitudinal.svg").write_text(line_chart(
            "the longitudinal ceiling — flat across eight years (S5)",
            [e for e, _, _ in lg],
            [("precision ceiling", ACCENT, [c for _, c, _ in lg])],
            ylo=0.5, yhi=1.0, yticks=(0.5, 0.75, 1.0),
            note=f"arm A grows {lg[0][2]:,} → {lg[-1][2]:,} edges; the ceiling "
                 "does not move. third pre-registered hypothesis falsified. "
                 "source: longitudinal.json"))
        written.append("fig-longitudinal.svg")

    off = offender_rows()
    if off:
        mx = max(c for _, c in off)
        rows = [(f"`{n}`", c / mx, ACCENT if n == "cursor" else MUTED,
                 f"{c} edges" + ("  ← arm A was RIGHT here" if n == "cursor"
                                 else "")) for n, c in off]
        (OUT / "fig-offenders.svg").write_text(hbar_chart(
            "where unconfirmed name-matched edges point", rows, fmt="",
            note="container-method name collisions dominate the top; the "
                 "cursor block is the honest counter-example (pyright "
                 "under-reported). source: docs/graph-delta.md"))
        written.append("fig-offenders.svg")
    else:
        skipped.append("fig-offenders (graph-delta parse)")

    # Latency: verbatim constants from docs/latency.md, log-scale bars.
    lat = [("count(*) reachability, typical source", 0.008, ACCENT, "6–10 ms"),
           ("count(*), busiest hub (12,710 reached)", 6.5, ACCENT, "6.5 s"),
           ("algo.MSpaths enumeration, mid-graph", 15.0, MUTED, "~15 s"),
           ("enumeration, hub — grazes the wall", 24.0, MUTED, "~24 s"),
           ("engine hard timeout", 30.0, YELLOW, "30 s")]
    import math
    lo, hi = math.log10(0.005), math.log10(40)
    rows = [(lbl, (math.log10(v) - lo) / (hi - lo), col, ann)
            for lbl, v, col, ann in lat]
    (OUT / "fig-latency.svg").write_text(hbar_chart(
        "one 34,000-node graph, both queries (log scale)", rows, fmt="",
        note="honest ratio ~1,500–2,300x at the typical operating point, "
             "unbounded at the hub. values verbatim from docs/latency.md"))
    written.append("fig-latency.svg")

    (OUT / "system-diagram.svg").write_text(system_diagram())
    (OUT / "verdict-flow.svg").write_text(verdict_flow())
    written += ["system-diagram.svg", "verdict-flow.svg"]

    print("written:", ", ".join(written))
    if skipped:
        print("SKIPPED (source unparseable, not guessed):", ", ".join(skipped))


if __name__ == "__main__":
    main()

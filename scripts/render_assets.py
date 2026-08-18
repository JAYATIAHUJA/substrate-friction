#!/usr/bin/env python
"""Generate the site/README visual assets. Presentation only, reproducible.

    uv run python scripts/render_assets.py

Emits:
  docs/plots/architecture.svg   — the pipeline diagram (hand-authored here)
  docs/plots/hero-terminal.svg  — capture 03 rendered as a styled terminal
  docs/plots/budget-curves.svg  — S4 curves drawn from budget-curves.json
  docs/og.png, docs/favicon.png — via Pillow when available (skipped, with a
                                  notice, when it is not)
"""

from __future__ import annotations

import json
from pathlib import Path

PLOTS = Path("docs/plots")

BG = "#0a0a0a"
RAISED = "#121212"
LINE = "#2e2e2e"
ACCENT = "#ff571a"
TEXT = "#ffffff"
BODY = "#dadada"
MUTED = "#747474"
MONO = "ui-monospace,'Geist Mono','JetBrains Mono',Menlo,monospace"


def architecture() -> str:
    def box(x, y, w, h, label, sub="", stroke=LINE):
        s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{RAISED}" '
             f'stroke="{stroke}" stroke-width="1"/>'
             f'<text x="{x+w/2}" y="{y+h/2-(6 if sub else 0)}" fill="{TEXT}" '
             f'font-family="{MONO}" font-size="13" text-anchor="middle" '
             f'dominant-baseline="middle">{label}</text>')
        if sub:
            s += (f'<text x="{x+w/2}" y="{y+h/2+12}" fill="{MUTED}" '
                  f'font-family="{MONO}" font-size="10" text-anchor="middle" '
                  f'dominant-baseline="middle">{sub}</text>')
        return s

    def arrow(x1, y1, x2, y2):
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{LINE}" stroke-width="1" marker-end="url(#a)"/>')

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 300" '
        f'font-family="{MONO}" role="img" '
        f'aria-label="Pipeline: sources to arms to HydraDB to surfaces">',
        f'<rect width="900" height="300" fill="{BG}"/>',
        '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>',
        f'<text x="20" y="30" fill="{MUTED}" font-size="11" '
        f'letter-spacing="2">SUBSTRATE-FRICTION / PIPELINE</text>',
        box(20, 60, 150, 70, "git checkout", "SWE-bench labels"),
        box(20, 170, 150, 70, "FAIL_TO_PASS", "the free oracle"),
        box(240, 60, 170, 70, "arm A", "tree-sitter, name-matched"),
        box(240, 170, 170, 70, "arm B", "scip-python, type-resolved"),
        box(480, 105, 180, 90, "HydraDB", "digest-pinned · disjoint id bands",
            stroke=ACCENT),
        box(730, 40, 150, 50, "friction gate", "RUN_FULL / exit 1"),
        box(730, 105, 150, 50, "diff --live", "anti-join, 2.0 ms/edge"),
        box(730, 170, 150, 50, "MCP", "gate_check · graph_query"),
        box(730, 235, 150, 50, "--sarif", "code-scanning"),
        arrow(170, 95, 240, 95), arrow(170, 205, 240, 205),
        arrow(410, 95, 480, 130), arrow(410, 205, 480, 170),
        arrow(660, 130, 730, 65), arrow(660, 150, 730, 130),
        arrow(660, 170, 730, 195), arrow(660, 190, 730, 258),
        '</svg>',
    ]
    return "".join(parts)


def hero_terminal(capture: Path) -> str:
    lines = capture.read_text(encoding="utf-8").splitlines()
    keep = [ln for ln in lines if ln.strip()][:14]
    h = 46 + 20 * len(keep) + 18
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {h}" '
        f'font-family="{MONO}" role="img" '
        f'aria-label="friction gate --live terminal output">',
        f'<rect width="760" height="{h}" fill="{RAISED}" stroke="{LINE}"/>',
        f'<rect width="760" height="30" fill="{BG}"/>',
        f'<text x="14" y="20" fill="{MUTED}" font-size="11">'
        f'friction gate --instance django__django-11551 --live</text>',
    ]
    y = 52
    for ln in keep:
        esc = (ln.replace("&", "&amp;").replace("<", "&lt;")
                 .replace(">", "&gt;"))
        color = BODY
        if ln.startswith("$"):
            color = ACCENT
        elif "parity=True" in ln or "DROPPED" in ln:
            color = ACCENT
        elif ln.startswith("──"):
            color = LINE
            esc = "─" * 84
        out.append(f'<text x="14" y="{y}" fill="{color}" font-size="12" '
                   f'xml:space="preserve">{esc}</text>')
        y += 20
    out.append(f'<rect x="14" y="{y-12}" width="8" height="14" fill="{ACCENT}">'
               '<animate attributeName="opacity" values="1;0;1" dur="1.2s" '
               'repeatCount="indefinite"/></rect>')
    out.append('</svg>')
    return "".join(out)


def budget_svg(data: dict) -> str:
    ks = data["ks"]
    W, H, L, B = 720, 300, 70, 250
    xs = {K: L + i * 140 for i, K in enumerate(ks)}

    def y_of(r):
        return B - r * 180

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'font-family="{MONO}" role="img" aria-label="Recall vs identifier '
        f'budget: both arms collapse under truncation">',
        f'<rect width="{W}" height="{H}" fill="{BG}"/>',
        f'<text x="20" y="26" fill="{MUTED}" font-size="11" letter-spacing="2">'
        'S4 / GUARDING-TEST RECALL vs TOP-K IDENTIFIERS KEPT</text>',
        f'<line x1="{L}" y1="{B}" x2="{W-30}" y2="{B}" stroke="{LINE}"/>',
        f'<line x1="{L}" y1="{B}" x2="{L}" y2="50" stroke="{LINE}"/>',
    ]
    for r in (0.0, 0.25, 0.5):
        parts.append(f'<text x="{L-10}" y="{y_of(r)+4}" fill="{MUTED}" '
                     f'font-size="10" text-anchor="end">{r:.2f}</text>')
        parts.append(f'<line x1="{L}" y1="{y_of(r)}" x2="{W-30}" '
                     f'y2="{y_of(r)}" stroke="{LINE}" stroke-dasharray="2 6"/>')
    for K in ks:
        parts.append(f'<text x="{xs[K]}" y="{B+18}" fill="{MUTED}" '
                     f'font-size="10" text-anchor="middle">K={K}</text>')
    colors = {"arm_a": MUTED, "arm_b": ACCENT}
    full = data["full"]
    for arm in ("arm_a", "arm_b"):
        pts = []
        for K in ks:
            c = data["curves"][arm][str(K)]
            r = c["hits"] / c["n"] if c["n"] else 0.0
            pts.append((xs[K], y_of(r)))
        d = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}"
                     for i, (x, y) in enumerate(pts))
        parts.append(f'<path d="{d}" fill="none" stroke="{colors[arm]}" '
                     f'stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<rect x="{x-3}" y="{y-3}" width="6" height="6" '
                         f'fill="{colors[arm]}"/>')
        fr = full[arm]["hits"] / full[arm]["n"]
        parts.append(f'<line x1="{L}" y1="{y_of(fr)}" x2="{W-30}" '
                     f'y2="{y_of(fr)}" stroke="{colors[arm]}" '
                     f'stroke-dasharray="6 4" opacity="0.6"/>')
        parts.append(f'<text x="{W-28}" y="{y_of(fr)+4}" '
                     f'fill="{colors[arm]}" font-size="10">'
                     f'{arm} full {fr:.2f}</text>')
    parts.append('</svg>')
    return "".join(parts)


def png_assets() -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return "Pillow absent — og.png/favicon.png skipped (disclosed)"

    def font(size):
        for cand in ("/System/Library/Fonts/Helvetica.ttc",
                     "/System/Library/Fonts/Supplemental/Arial.ttf"):
            try:
                return ImageFont.truetype(cand, size)
            except OSError:
                continue
        return ImageFont.load_default()

    og = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(og)
    d.rectangle([60, 60, 1140, 570], outline=LINE, width=2)
    d.text((100, 140), "substrate", font=font(72), fill=TEXT)
    d.text((470, 140), "—", font=font(72), fill=ACCENT)
    d.text((530, 140), "friction", font=font(72), fill=TEXT)
    d.text((100, 280), "0.419", font=font(120), fill=ACCENT)
    d.text((100, 430), "guarding-test recall, 172 instances / 7 repos.",
           font=font(34), fill=BODY)
    d.text((100, 480), "Before your tool skips a test, measure the graph "
           "it trusted.", font=font(34), fill=MUTED)
    og.save("docs/og.png", optimize=True)

    fav = Image.new("RGB", (64, 64), BG)
    d = ImageDraw.Draw(fav)
    d.rectangle([12, 12, 52, 52], fill=ACCENT)
    d.rectangle([24, 24, 40, 40], fill=BG)
    fav.save("docs/favicon.png")
    return "og.png + favicon.png written"


def substrate_tree() -> str:
    """Procedural pixel-tree in the engine's visual dialect — original art,
    seeded and reproducible, with OUR measured numbers in the sampled-node
    overlay (0.746 ceiling, 0.545 django, 0.419 pooled, 2.0 ms anti-join).
    """
    import math
    import random

    rng = random.Random(20260819)
    W, H, CELL = 1600, 760, 11
    cells: dict[tuple[int, int], float] = {}

    def put(x, y, heat):
        gx, gy = int(x // CELL), int(y // CELL)
        if 0 <= gx * CELL < W and 0 <= gy * CELL < H:
            cells[(gx, gy)] = max(cells.get((gx, gy), 0.0), heat)

    def branch(x, y, ang, length, width, depth):
        for step in range(length):
            x += math.cos(ang) * CELL
            y += math.sin(ang) * CELL
            heat = max(0.12, 1.0 - depth * 0.16 + rng.uniform(-0.14, 0.22))
            for _ in range(max(1, int(width))):
                jx = rng.gauss(0, width * CELL * 0.5)
                jy = rng.gauss(0, width * CELL * 0.35)
                put(x + jx, y + jy, heat * rng.uniform(0.55, 1.0))
            put(x, y, heat)
            ang += rng.uniform(-0.055, 0.055)
            if depth < 4 and rng.random() < (0.028 + depth * 0.008):
                spread = rng.uniform(0.35, 0.95) * rng.choice((1, -1))
                branch(x, y, ang + spread,
                       int(length * rng.uniform(0.45, 0.75)),
                       width * 0.6, depth + 1)

    # trunk splits low, canopy leans right — the hydra silhouette
    branch(430, H - 10, -math.pi / 2, 16, 3.4, 0)
    branch(430, H - 170, -math.pi / 2 + 0.55, 46, 2.6, 1)
    branch(430, H - 170, -math.pi / 2 - 0.45, 30, 2.4, 1)
    branch(430, H - 300, -0.10, 96, 2.0, 1)          # long right limb
    branch(430, H - 260, -math.pi / 2 - 1.05, 26, 1.8, 2)

    palette = ["#5c130a", "#8a1f0d", "#b62c0f", "#d84012", "#ff571a",
               "#ff8a4d", "#ffc38a", "#fff3e0"]
    P = []
    for (gx, gy), heat in cells.items():
        c = palette[min(len(palette) - 1, int(heat * len(palette)))]
        s = CELL - 3
        P.append(f'<rect x="{gx*CELL}" y="{gy*CELL}" width="{s}" height="{s}" '
                 f'fill="{c}"/>')

    # sampled-node overlay: real numbers, dashed interconnects
    nodes = [(1150, 430, "0.7460"), (1330, 330, "0.5455"),
             (1470, 480, "0.4186"), (1250, 560, "2.0ms")]
    for i, (x, y, _) in enumerate(nodes):
        for x2, y2, _ in nodes[i + 1:]:
            P.append(f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" '
                     f'stroke="#dadada" stroke-width="1" '
                     f'stroke-dasharray="3 6" opacity="0.7"/>')
    for x, y, val in nodes:
        r = 34
        P.append(f'<rect x="{x-r}" y="{y-r}" width="{2*r}" height="{2*r}" '
                 f'fill="none" stroke="#ffffff" stroke-width="1.2"/>'
                 f'<line x1="{x-r}" y1="{y-r}" x2="{x+r}" y2="{y+r}" '
                 f'stroke="#ffffff" stroke-width="0.8" opacity="0.8"/>'
                 f'<line x1="{x-r}" y1="{y+r}" x2="{x+r}" y2="{y-r}" '
                 f'stroke="#ffffff" stroke-width="0.8" opacity="0.8"/>'
                 f'<text x="{x}" y="{y+r+16}" fill="#ffffff" '
                 f'font-family="{MONO}" font-size="12" '
                 f'text-anchor="middle">{val}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {W} {H}" role="img" aria-label="Decorative pixel '
            f'tree in the engine\'s visual language; sampled nodes carry this '
            f'project\'s measured numbers.">'
            f'<rect width="{W}" height="{H}" fill="{BG}"/>'
            + "".join(P) +
            f'<line x1="0" y1="{H-2}" x2="{W}" y2="{H-2}" stroke="{ACCENT}" '
            f'stroke-width="2"/></svg>')


def main() -> None:
    PLOTS.mkdir(exist_ok=True)
    (PLOTS / "architecture.svg").write_text(architecture(), encoding="utf-8")
    (PLOTS / "hero-terminal.svg").write_text(
        hero_terminal(Path("docs/captures/03-live-parity.txt")),
        encoding="utf-8")
    (PLOTS / "budget-curves.svg").write_text(
        budget_svg(json.loads(
            Path("data/shipped/budget-curves.json").read_text())),
        encoding="utf-8")
    (PLOTS / "substrate-tree.svg").write_text(substrate_tree(),
                                              encoding="utf-8")
    print("architecture.svg, hero-terminal.svg, budget-curves.svg, "
          "substrate-tree.svg written")
    print(png_assets())


if __name__ == "__main__":
    main()

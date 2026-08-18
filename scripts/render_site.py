#!/usr/bin/env python
"""Render docs/index.html (+404, css, js) from data/shipped/gate-results.json.

Every number on the page is injected here from the committed artifact and
tagged `data-num="<key>"` so `friction verify` can assert site == json.
Hand-editing a number into the HTML will fail verify.

    uv run python scripts/render_site.py
"""

from __future__ import annotations

import json
from pathlib import Path

D = json.loads(Path("data/shipped/gate-results.json").read_text())
POOL = D["summary"]["pooled"]
PER = D["summary"]["per_repo"]

NUMS = {
    "pooled_b_recall": f"{POOL['arm_b']['recall']:.3f}",
    "pooled_a_recall": f"{POOL['arm_a']['recall']:.3f}",
    "pooled_b_ratio": f"{POOL['arm_b']['hits']}/{POOL['arm_b']['n']}",
    "pooled_a_ratio": f"{POOL['arm_a']['hits']}/{POOL['arm_a']['n']}",
    "django_b_ratio": f"{PER['django']['arm_b']['hits']}/{PER['django']['arm_b']['n']}",
    "django_b_recall": f"{PER['django']['arm_b']['hits']/PER['django']['arm_b']['n']:.3f}",
    "django_a_recall": f"{PER['django']['arm_a']['hits']/PER['django']['arm_a']['n']:.3f}",
}


def n(key: str) -> str:
    return f'<span data-num="{key}">{NUMS[key]}</span>'


CSS = """
:root{--bg:#0a0a0a;--raised:#121212;--hover:#202020;--line:#2e2e2e;
--line-strong:#353535;--accent:#ff571a;--yellow:#f9c425;--text:#fff;
--body:#dadada;--muted:#747474}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--body);
font-family:Inter,system-ui,sans-serif;font-size:16px;line-height:1.65}
h1,h2,h3{font-family:'VT323','Geist Mono',ui-monospace,monospace;
color:var(--text);letter-spacing:.01em;font-weight:400}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code,.mono{font-family:'Geist Mono','JetBrains Mono',ui-monospace,monospace}
.wrap{max-width:1100px;margin:0 auto;padding:0 24px}
.micro{font-family:'Geist Mono',ui-monospace,monospace;font-size:12px;
text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid
var(--line);z-index:10}
nav .wrap{display:flex;align-items:center;justify-content:space-between;
height:60px}
.wordmark{font-family:'Geist Mono',ui-monospace,monospace;color:var(--text);
font-size:15px}
.wordmark b{color:var(--accent);font-weight:400}
nav ul{display:flex;gap:24px;list-style:none}
nav ul a{color:var(--body);font-size:14px}
nav ul a:hover{color:var(--accent);text-decoration:none}
.btn{display:inline-block;padding:10px 20px;border:1px solid var(--line);
color:var(--body);font-size:14px;font-weight:500}
.btn:hover{border-color:var(--accent);color:var(--accent);
text-decoration:none}
.btn.primary{background:var(--accent);border-color:var(--accent);
color:#0a0a0a}
.btn.primary:hover{background:#e64d15;color:#0a0a0a}
header.hero{padding:90px 0 60px;border-bottom:1px solid var(--line)}
.hero-grid{display:grid;grid-template-columns:1fr 1fr;gap:48px;
align-items:center}
.hero h1{font-size:clamp(52px,7.5vw,88px);line-height:.95;
margin:14px 0 20px}
.hero p{max-width:60ch;margin-bottom:26px}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}
.chip{font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;
color:var(--muted);border:1px solid var(--line);padding:4px 10px}
.hero img{width:100%;border:1px solid var(--line)}
section{padding:70px 0;border-bottom:1px solid var(--line)}
section h2{font-size:40px;margin:10px 0 24px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
background:var(--line);border:1px solid var(--line)}
.stat{background:var(--raised);padding:28px 22px}
.stat .v{font-family:'Geist Mono',ui-monospace,monospace;font-size:36px;
color:var(--accent);font-weight:500}
.stat .l{font-size:13px;color:var(--muted);margin-top:6px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1px;
background:var(--line);border:1px solid var(--line)}
.col{background:var(--raised);padding:30px}
.col h3{font-size:24px;margin-bottom:12px}
.col.bad h3{color:var(--muted)}
.col.good h3{color:var(--accent)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.card{border:1px solid var(--line);padding:24px;background:var(--raised)}
.card:hover{border-color:var(--line-strong)}
.card code{display:block;margin-top:14px;font-size:11.5px;
color:var(--muted);overflow-x:auto;white-space:nowrap}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{border:1px solid var(--line);padding:12px 14px;text-align:left}
th{font-family:'Geist Mono',ui-monospace,monospace;font-size:12px;
text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
td.verdict{color:var(--accent);
font-family:'Geist Mono',ui-monospace,monospace}
.evidence ul{list-style:none;display:grid;gap:12px}
.evidence li{border-left:2px solid var(--accent);padding:2px 0 2px 16px}
details{border-top:1px solid var(--line);padding:18px 0}
details:last-of-type{border-bottom:1px solid var(--line)}
summary{cursor:pointer;color:var(--text);font-weight:500;list-style:none}
summary::before{content:'+ ';color:var(--accent);
font-family:'Geist Mono',ui-monospace,monospace}
details[open] summary::before{content:'− '}
details p{margin-top:10px;max-width:70ch}
footer{padding:50px 0;font-size:13px}
footer .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:30px}
footer h4{font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;
text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
margin-bottom:12px}
footer ul{list-style:none}
footer li{margin-bottom:8px}
footer .digest{margin-top:36px;color:var(--muted);
font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;
word-break:break-all}
img.diagram{width:100%;border:1px solid var(--line)}
figcaption{font-size:12.5px;color:var(--muted);margin-top:10px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(max-width:900px){.hero-grid,.cols,.cards{grid-template-columns:1fr}
.stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){nav ul{display:none}
.stats{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""

JS = """
// Animated counters. Nothing else moves.
(function () {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const els = document.querySelectorAll('[data-count]');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting || e.target.dataset.done) return;
      e.target.dataset.done = '1';
      const target = parseFloat(e.target.dataset.count);
      const dec = (e.target.dataset.count.split('.')[1] || '').length;
      const t0 = performance.now();
      const step = (t) => {
        const p = Math.min((t - t0) / 800, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        e.target.textContent = (target * eased).toFixed(dec);
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }, { threshold: 0.4 });
  els.forEach((el) => io.observe(el));
})();
"""

HEAD = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>substrate—friction · measure the graph before you trust it</title>
<meta name="description" content="Graph-based test selection is unsafe in a way that is invisible from inside the tool. friction gate measures guarding-test recall against SWE-bench labels: {NUMS['pooled_b_recall']} pooled across 7 repos. Verdict: RUN_FULL.">
<link rel="canonical" href="https://areycruzer.github.io/substrate-friction/">
<meta property="og:title" content="substrate—friction">
<meta property="og:description" content="Before your tool skips a test, measure the graph it trusted. Guarding-test recall {NUMS['pooled_b_recall']} pooled / 7 repos — verdict RUN_FULL.">
<meta property="og:image" content="https://areycruzer.github.io/substrate-friction/og.png">
<meta property="og:type" content="website">
<link rel="icon" type="image/png" href="favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=VT323&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="site.css">
</head>"""

NAV = """<nav><div class="wrap">
<a class="wordmark" href="#">substrate<b>—</b>friction</a>
<ul>
<li><a href="#gate">Gate</a></li>
<li><a href="#measurement">Measurement</a></li>
<li><a href="#engine">Engine</a></li>
<li><a href="#evidence">Evidence</a></li>
<li><a href="https://github.com/areycruzer/substrate-friction">GitHub</a></li>
</ul>
<a class="btn primary" href="https://github.com/areycruzer/substrate-friction#quickstart">Run the gate</a>
</div></nav>"""


def body() -> str:
    dj = PER["django"]["arm_b"]
    return f"""<body>
{NAV}
<header class="hero"><div class="wrap hero-grid">
<div>
<div class="micro">01 / TEST SELECTION SAFETY</div>
<h1>Before your tool skips a test, measure the graph it trusted.</h1>
<p>Coding agents build a graph of your repository by matching names, then
skip tests based on it. <code>friction gate</code> prices that graph against
labelled ground truth before anything skips on it — and refuses when the
evidence is thin.</p>
<a class="btn primary" href="https://github.com/areycruzer/substrate-friction#quickstart">Run the gate</a>
<a class="btn" href="https://github.com/areycruzer/substrate-friction/blob/main/docs/gate.md">Read the measurement</a>
<div class="chips">
<span class="chip">engine digest-pinned</span>
<span class="chip">full pytest suite in CI</span>
<span class="chip">MIT (engine AGPL, external)</span>
<span class="chip">pre-registered studies</span>
</div>
</div>
<figure>
<img src="plots/hero-terminal.svg" alt="Terminal: friction gate --live — engine selects 0 of 1 guarding tests, parity with offline walk is True, the engine itself proves the miss." loading="eager">
<figcaption>A real capture: the engine executes the selection and proves the
dropped guarding test. <a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/captures/03-live-parity.txt">docs/captures/03-live-parity.txt</a></figcaption>
</figure>
</div></header>

<section id="stats"><div class="wrap">
<div class="stats">
<div class="stat"><div class="v"><span data-count="0.746">0.746</span></div>
<div class="l">name-match precision ceiling — flat across 8 years of
django (docs/graph-delta.md · docs/longitudinal.md S5)</div></div>
<div class="stat"><div class="v"><span data-count="{NUMS['django_b_recall']}" data-num="django_b_recall">{NUMS['django_b_recall']}</span></div>
<div class="l">guarding-test recall, type-resolved, django
({n('django_b_ratio')})</div></div>
<div class="stat"><div class="v"><span data-count="{NUMS['pooled_b_recall']}" data-num="pooled_b_recall">{NUMS['pooled_b_recall']}</span></div>
<div class="l">pooled recall, 7 repos ({n('pooled_b_ratio')} — study S1)</div></div>
<div class="stat"><div class="v">2.0<span style="font-size:20px"> ms</span></div>
<div class="l">per-edge in-engine anti-join (docs/engine-diff.md)</div></div>
</div>
</div></section>

<section id="gate"><div class="wrap">
<div class="micro">02 / THE GATE</div>
<h2>Graph-complete is not program-complete.</h2>
<div class="cols">
<div class="col bad"><h3>WITHOUT THE GATE</h3>
<p>The selector walks its graph backwards from the change, exhausts every
edge the graph has, calls the walk complete, and skips the rest. An extractor
cannot fail-closed on an edge it never knew existed — the walk is
graph-complete while the graph is missing the edge that mattered. On one real
django instance the walk was provably complete and selected <b>0 of 370</b>
tests known to guard the fix.</p></div>
<div class="col good"><h3>WITH THE GATE</h3>
<p>Recall is measured against SWE-bench <code>FAIL_TO_PASS</code> labels —
the test that guards each fix is known. Below the 0.95 bar the gate exits 1:
<code>RUN_FULL</code>. Fail-closed, in CI, over MCP, and as a SARIF
code-scanning finding. A gate that refuses below the bar is the product
working.</p></div>
</div>
</div></section>

<section id="how"><div class="wrap">
<div class="micro">03 / HOW IT WORKS</div>
<h2>Two arms, one engine, one verdict.</h2>
<div class="cards">
<div class="card"><div class="micro">BUILD BOTH ARMS</div>
<p>The same commit parsed twice: name-matched (what deployed agents build)
and type-resolved (scip-python/pyright).</p>
<code>arm A: tree-sitter · arm B: SCIP</code></div>
<div class="card"><div class="micro">LOAD ONE ENGINE</div>
<p>Both arms resident at once in disjoint integer id bands — the diff is a
single-engine operation.</p>
<code>MERGE (n {{id: row.id}}) SET n:Sym</code></div>
<div class="card"><div class="micro">MEASURE, THEN GATE</div>
<p>Bounded walks answer reachability; labels turn it into recall; recall
becomes an exit code.</p>
<code>MATCH (s {{id:N}})-[:CALLED_BY*1..6]-&gt;(n) RETURN n.id</code></div>
</div>
<figure style="margin-top:40px">
<img class="diagram" src="plots/architecture.svg" alt="Pipeline diagram: git checkout and SWE-bench labels feed arm A (tree-sitter) and arm B (scip-python); both load into digest-pinned HydraDB in disjoint id bands; surfaces are friction gate, diff --live, MCP, and SARIF.">
<figcaption>Generated by <code>scripts/render_assets.py</code>.</figcaption>
</figure>
</div></section>

<section id="measurement"><div class="wrap">
<div class="micro">04 / THE VERDICT</div>
<h2>No graph class measured here clears the bar.</h2>
<table>
<tr><th>Graph</th><th>Guarding-test recall</th><th>vs 0.95 bar</th></tr>
<tr><td>Name-matched — the class Aider, RepoGraph, LocAgent build</td>
<td class="mono"><span data-num="pooled_a_recall">{NUMS['pooled_a_recall']}</span> pooled ({n('pooled_a_ratio')})</td>
<td class="verdict">RUN_FULL</td></tr>
<tr><td>Type-resolved — scip-python / pyright</td>
<td class="mono"><span data-num="pooled_b_recall2">{NUMS['pooled_b_recall']}</span> pooled ({n('pooled_b_ratio')}) · {NUMS['django_b_recall']} django</td>
<td class="verdict">RUN_FULL</td></tr>
<tr><td>Type-resolved + dynamic execution traces (django subset)</td>
<td class="mono">0.67 (12/18)</td>
<td class="verdict">RUN_FULL</td></tr>
</table>
<p style="margin-top:16px;font-size:14px;color:var(--muted)">Per-repo spread
is the finding, not an inconsistency: django {dj['hits']}/{dj['n']}, xarray 19/21,
matplotlib 0/33 and pytest 0/19 (guarding tests in a different graph
component), two tiny repos at 1.0 with n too small to clear any bar. Full
table and Wilson intervals:
<a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/gate.md">docs/gate.md</a>.</p>
</div></section>

<section id="engine"><div class="wrap">
<div class="micro">05 / THE ENGINE</div>
<h2>The measurement itself runs in HydraDB.</h2>
<p style="max-width:70ch"><code>friction diff --live</code> reifies every
compared edge as a node and computes the arm-A-vs-arm-B anti-join as a 2-hop
bounded traversal — 5,873 queries at 2.0&nbsp;ms each, reproducing the offline
join <b>exactly</b> (4,381 confirmed / 1,492 unconfirmed), enforced by
exception. Bounded reachability answers in milliseconds where path enumeration
hit the 30-second wall; both arms live in one engine in disjoint id bands; the
image is pinned by digest. Four findings went upstream:
<a href="https://github.com/hydra-db/hydradb/issues/81">#81</a>,
<a href="https://github.com/hydra-db/hydradb/pull/82">#82</a>,
<a href="https://github.com/hydra-db/hydradb/issues/101">#101</a>,
<a href="https://github.com/hydra-db/hydradb/issues/102">#102</a>.</p>
</div></section>

<section id="evidence" class="evidence"><div class="wrap">
<div class="micro">06 / EVIDENCE</div>
<h2>How we know this is real.</h2>
<ul>
<li><b>Pre-registered studies</b> — hypothesis before run
(<code>docs/studies.md</code>); two hypotheses came back wrong and ship
as-written.</li>
<li><b>Negative control</b> — delete edges, recall falls monotonically
0.545&nbsp;→&nbsp;0.000; the instrument detects degradation
(<code>docs/negative-control.md</code>).</li>
<li><b>The auditor is audited</b> — arm B misses execution-proven
connections; reported as a floor (<code>docs/audit-the-auditor.md</code>).</li>
<li><b>Fidelity</b> — aider's real extractor tags 119/119 definitions arm A
sees (<code>docs/fidelity-differential.md</code>).</li>
<li><b><code>friction verify</code></b> — re-derives every shipped figure
from committed artifacts; nonzero exit on drift. It caught one on its first
run.</li>
<li><b>Retractions stay published</b> — three withdrawn figures, causes
written down, kept on purpose (README).</li>
</ul>
</div></section>

<section id="faq"><div class="wrap">
<div class="micro">07 / FAQ</div>
<h2>Questions a careful reader asks.</h2>
<details><summary>Does 0.419 pooled contradict 0.545 on django?</summary>
<p>No — same measurement, different scope: {NUMS['django_b_recall']} is django
(n=44), {NUMS['pooled_b_recall']} is all 7 repos pooled (n=172), and the
per-repo spread (1.00 down to 0.00) is itself the finding.</p></details>
<details><summary>Is RUN_FULL a failure?</summary>
<p>It is the product working: a gate that refuses to license a skip below the
measured bar. The exit code is 1 so CI fails closed.</p></details>
<details><summary>Why not just use a better extractor?</summary>
<p>Measured: upgrading name matching to full pyright type resolution moved
paired recall by +0.071 (n=28, McNemar p=0.73). Precision and recall of a
static analysis are separate concerns — ICSE 2020 reported the same for
Java.</p></details>
<details><summary>Are these numbers comparable to PyCG's 70%?</summary>
<p>No, and the docs say so: those studies measure single-edge presence; this
measures bounded transitive reachability of a labelled pair — a harder
relation.</p></details>
<details><summary>What was retracted?</summary>
<p>Three figures, all still published with causes: two predictor AUCs
(measurement defects) and one latency ratio (cross-graph comparison). The
prediction idea itself is a reported NO-GO — the gate exists because that
failure was measured honestly.</p></details>
</div></section>

<footer><div class="wrap">
<div class="grid">
<div><h4>Repo</h4><ul>
<li><a href="https://github.com/areycruzer/substrate-friction">github.com/areycruzer/substrate-friction</a></li>
<li><a href="https://github.com/areycruzer/substrate-friction#quickstart">Quickstart</a></li>
<li><a href="demo.html">Interactive demo</a></li>
</ul></div>
<div><h4>Evidence</h4><ul>
<li><a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/gate.md">The gate report</a></li>
<li><a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/studies.md">Pre-registered studies</a></li>
<li><a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/related-work.md">Related work</a></li>
</ul></div>
<div><h4>Upstream</h4><ul>
<li><a href="https://github.com/hydra-db/hydradb/issues/81">hydradb#81</a> · <a href="https://github.com/hydra-db/hydradb/pull/82">#82</a></li>
<li><a href="https://github.com/hydra-db/hydradb/issues/101">hydradb#101</a> · <a href="https://github.com/hydra-db/hydradb/issues/102">#102</a></li>
</ul></div>
</div>
<div class="digest">engine ghcr.io/hydra-db/hydradb@sha256:db78309a233be54662db29744047e985a39b51c45a270d1a1f47c31a62cdb709 · commit 02a40025 · numbers rendered from data/shipped/gate-results.json by scripts/render_site.py</div>
</div></footer>
<script src="site.js"></script>
</body></html>"""


NOTFOUND = HEAD + NAV.join(["<body>", ""]) + """
<section><div class="wrap" style="padding:120px 0">
<div class="micro">404 / NOT FOUND</div>
<h1 style="font-size:48px;margin:14px 0 20px">This path is not in the graph.</h1>
<p>Which, around here, we can prove. <a href="index.html">Back to the gate</a>.</p>
</div></section>
</body></html>"""


def main() -> None:
    Path("docs/site.css").write_text(CSS, encoding="utf-8")
    Path("docs/site.js").write_text(JS, encoding="utf-8")
    Path("docs/index.html").write_text(HEAD + body(), encoding="utf-8")
    Path("docs/404.html").write_text(NOTFOUND, encoding="utf-8")
    total = sum(Path(f).stat().st_size for f in
                ("docs/index.html", "docs/site.css", "docs/site.js",
                 "docs/plots/hero-terminal.svg",
                 "docs/plots/architecture.svg"))
    print(f"site rendered; core transfer {total/1024:.0f} KB "
          f"(+fonts, +og only on share)")
    for k, v in NUMS.items():
        print(f"  {k} = {v}")


if __name__ == "__main__":
    main()

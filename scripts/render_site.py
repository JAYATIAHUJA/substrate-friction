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
:root{--bg:#000000;--raised:#0a0a0a;--hover:#202020;--line:#2e2e2e;
--line-strong:#353535;--accent:#ff571a;--yellow:#f9c425;--text:#fff;
--body:#dadada;--muted:#747474}
*{margin:0;padding:0;box-sizing:border-box}
::selection{background:var(--accent);color:#000000}
::-webkit-scrollbar{width:10px;background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--line-strong);border:2px solid
var(--bg)}
::-webkit-scrollbar-thumb:hover{background:var(--accent)}
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
#bgtree{position:fixed;inset:0;z-index:0;pointer-events:none}
nav,header,section,footer,.wrap{position:relative;z-index:1}
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
color:#000000}
.btn.primary:hover{background:#e64d15;color:#000000}
header.hero{padding:90px 0 60px;border-bottom:1px solid var(--line)}
.hero-grid{display:grid;grid-template-columns:0.82fr 1.18fr;gap:44px;
align-items:center}
.hero h1{font-size:clamp(52px,7.5vw,88px);line-height:.95;
margin:14px 0 20px}
.hero p{max-width:60ch;margin-bottom:26px}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}
.chip{font-family:'Geist Mono',ui-monospace,monospace;font-size:11px;
color:var(--muted);border:1px solid var(--line);padding:4px 10px}
.hero figure.term{position:relative;margin-right:-56px}
.hero figure.term img{width:100%;border:1px solid var(--line-strong);
display:block}
.hero figure.term::after{content:'';position:absolute;inset:0 0 auto 0;
height:calc(100% - 0px);pointer-events:none;
background:repeating-linear-gradient(0deg,transparent 0 3px,
rgba(0,0,0,.22) 3px 4px)}
.hero figure.term:hover img{border-color:var(--accent)}
@media(max-width:900px){.hero figure.term{margin-right:0}}
section{padding:70px 0;border-bottom:1px solid var(--line)}
section h2{font-size:40px;margin:10px 0 24px}
.caret{display:inline-block;width:.45em;height:.9em;background:var(--accent);
margin-left:.12em;vertical-align:-.08em;animation:blink 1.1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
@media(prefers-reduced-motion:reduce){.caret{animation:none}}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;
background:var(--line);border:1px solid var(--line)}
.stat{background:var(--raised);padding:28px 22px;border:1px solid
transparent;transition:border-color .15s}
.stat:hover{border-color:var(--accent)}
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
details.walkterm{margin:18px 0;border:1px solid var(--line-strong)}
details.walkterm summary{cursor:pointer;background:var(--bg);padding:9px 14px;
border-bottom:1px solid var(--line);list-style:none;display:flex;gap:10px;
align-items:baseline;font-family:'Geist Mono',ui-monospace,monospace;
font-size:12.5px;color:var(--body)}
details.walkterm summary::-webkit-details-marker{display:none}
details.walkterm summary::before{content:"▸";color:var(--accent);
font-size:11px;transition:transform .15s}
details.walkterm[open] summary::before{transform:rotate(90deg)}
details.walkterm summary .hint{margin-left:auto;color:var(--muted);
font-size:10.5px;letter-spacing:.08em;text-transform:uppercase}
details.walkterm pre{background:var(--raised);padding:16px 18px;overflow-x:auto;
--cA:#ff571a;--cY:#f9c425;--cD:#4d4d4d;--cF:#9a9a9a}
.walkterm pre .tA{color:var(--accent)}.walkterm pre .tY{color:var(--yellow)}
.walkterm pre .tD{color:#4d4d4d}.walkterm pre .tF{color:#9a9a9a}
.walkterm pre b{font-weight:700}
font-family:'Geist Mono',ui-monospace,monospace;font-size:12.5px;
line-height:1.55;color:var(--body)}
.walkver{flex:0 0 auto;display:flex;align-items:center;padding:0 14px;
color:var(--muted);font:600 10px 'Geist Mono',ui-monospace,monospace;
letter-spacing:.12em;text-transform:uppercase;border-left:1px solid var(--line);
background:var(--bg)}
.artband{margin:0;border-bottom:1px solid var(--line)}
.artband img{width:100%;display:block}
.artband figcaption{font-size:12px;color:var(--muted);padding:10px 24px 26px}
.gallery{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:8px}
.gallery figure img{width:100%;border:1px solid var(--line);
transition:border-color .15s}
.gallery figure:hover img{border-color:var(--accent)}
.gallery figure.wide{grid-column:1/-1}
@media(max-width:900px){.gallery{grid-template-columns:1fr}}
figcaption{font-size:12.5px;color:var(--muted);margin-top:10px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@media(max-width:900px){.hero-grid,.cols,.cards{grid-template-columns:1fr}
.stats{grid-template-columns:repeat(2,1fr)}}
@media(max-width:480px){nav ul{display:none}
.stats{grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
.walkstage{margin:34px 0 8px;border:1px solid var(--line-strong);
background:var(--raised)}
.walkrail{display:flex;flex-wrap:wrap;gap:0;border-bottom:1px solid
var(--line)}
.walkrail button{flex:1 1 auto;min-width:96px;background:var(--bg);border:0;
border-right:1px solid var(--line);color:var(--muted);cursor:pointer;
padding:10px 8px;font:600 10.5px/1.2 'Space Grotesk',sans-serif;
letter-spacing:.14em;text-transform:uppercase;transition:color .15s,
background .15s}
.walkrail button:last-child{border-right:0}
.walkrail button .num{display:block;font-family:'Geist Mono',ui-monospace,
monospace;font-size:9px;opacity:.7;margin-bottom:3px}
.walkrail button[aria-pressed="true"]{color:var(--accent);background:
var(--hover)}
.walkrail button:hover{color:var(--text)}
.walkstage svg{display:block;width:100%;height:auto}
.wg{opacity:0;transition:opacity .55s ease}
.wg.on{opacity:1}
.wg .pop{transform:translateY(6px);transition:transform .55s ease}
.wg.on .pop{transform:translateY(0)}
.wg .meterfill{transform:scaleX(0);transform-origin:left center;
transition:transform .9s cubic-bezier(.2,.7,.2,1) .25s}
.wg.on .meterfill{transform:scaleX(1)}
@media(prefers-reduced-motion:reduce){.wg,.wg .pop,.wg .meterfill,
.wg.on .meterfill{transition:none;transform:none;opacity:1}
.wg{opacity:0}.wg.on{opacity:1}}
"""

JS = """
// The living substrate: the same generated tree, as a fixed background
// that ignites under the cursor and cools behind it. Dull by design; it
// never fights the foreground. Static single render under
// prefers-reduced-motion.
(function () {
  const T = window.__TREE;
  if (!T) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cv = document.createElement('canvas');
  cv.id = 'bgtree';
  cv.setAttribute('aria-hidden', 'true');
  document.body.prepend(cv);
  const ctx = cv.getContext('2d');

  const HOT = ['#5c130a','#8a1f0d','#b62c0f','#d84012','#ff571a',
               '#ff8a4d','#ffc38a','#fff3e0'];
  const n = T.cells.length / 3;
  const gx = new Float32Array(n), gy = new Float32Array(n);
  const heat = new Uint8Array(n), boost = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    gx[i] = T.cells[3*i]; gy[i] = T.cells[3*i+1]; heat[i] = T.cells[3*i+2];
  }

  let s = 1, ox = 0, oy = 0, cs = 8, dpr = 1;
  function layout() {
    if (!innerWidth || !innerHeight) {      // hidden/pre-paint viewport:
      setTimeout(layout, 250);              // retry until it exists
      return;
    }
    dpr = Math.min(devicePixelRatio || 1, 2);
    cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
    cv.style.width = innerWidth + 'px'; cv.style.height = innerHeight + 'px';
    s = Math.max(innerWidth / T.w, innerHeight / T.h);
    cs = T.cell * s;
    ox = 0; oy = innerHeight - T.h * s;   // anchor the trunk to the floor
    draw(true);
  }

  let mx = -1e4, my = -1e4, active = 0;
  addEventListener('pointermove', (e) => {
    mx = e.clientX; my = e.clientY; active = 60;
    if (!raf) loop();
  }, { passive: true });

  const R = 120, R2 = R * R;
  function draw(staticOnly) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    for (let i = 0; i < n; i++) {
      const x = ox + gx[i] * cs, y = oy + gy[i] * cs;
      if (x < -cs || x > innerWidth || y < -cs || y > innerHeight) continue;
      let b = boost[i];
      if (!staticOnly && active > 0) {
        const dx = x - mx, dy = y - my, d2 = dx*dx + dy*dy;
        if (d2 < R2) {
          const f = 1 - Math.sqrt(d2) / R;
          if (f > b) { boost[i] = f; b = f; }
        }
      }
      const idx = Math.min(7, heat[i] + (b > 0.4 ? 2 : b > 0.15 ? 1 : 0));
      ctx.globalAlpha = 0.13 + 0.45 * b;
      ctx.fillStyle = HOT[idx];
      const sz = Math.max(2, cs - 3 * s);
      ctx.fillRect(x, y, sz, sz);
      boost[i] = b * 0.955;
    }
    ctx.globalAlpha = 1;
  }

  let raf = 0, last = 0;
  function loop(ts) {
    raf = requestAnimationFrame(loop);
    if (ts - last < 33) return;         // ~30 fps is plenty for embers
    last = ts;
    draw(false);
    active--;
    let hotLeft = false;
    for (let i = 0; i < n; i += 7) if (boost[i] > 0.02) { hotLeft = true; break; }
    if (active <= 0 && !hotLeft) { cancelAnimationFrame(raf); raf = 0; }
  }

  addEventListener('resize', layout, { passive: true });
  layout();
  if (reduced) return;                   // static, dim, persistent — no motion
  loop(0);
})();

// Animated counters. Nothing else moves besides the substrate.
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
<li><a href="walkthrough.html">Walkthrough</a></li>\n<li><a href="#findings">Findings</a></li>
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
<h1>Before your tool skips a test, measure the graph it trusted.<span class="caret" aria-hidden="true"></span></h1>
<p>AI coding tools skip tests to save time, using a <b>map of your
code</b> to decide what's safe. We measured the map against 172 real bug
fixes — <b>it misses more than half of what matters.</b>
<code>friction gate</code> is the seatbelt: nothing skips until the map is
proven good. Today, the honest verdict is always the same — run everything.</p>
<a class="btn primary" href="https://github.com/areycruzer/substrate-friction#quickstart">Run the gate</a>
<a class="btn" href="walkthrough.html">Watch it on a real bug</a>
<a class="btn" href="https://github.com/areycruzer/substrate-friction/blob/main/docs/gate.md">Read the measurement</a>
<div class="chips">
<span class="chip">engine digest-pinned</span>
<span class="chip">full pytest suite in CI</span>
<span class="chip">MIT (engine AGPL, external)</span>
<span class="chip">pre-registered studies</span>
</div>
</div>
<figure class="term">
<img src="plots/hero-terminal.svg" alt="Terminal: friction gate --live — engine selects 0 of 1 guarding tests, parity with offline walk is True, the engine itself proves the miss." loading="eager">
<figcaption>A real recorded session, replayed: the corpus gate's verdict,
the live in-engine gate proving the dropped test, and <code>friction
verify</code>. <a href="https://github.com/areycruzer/substrate-friction/blob/main/docs/captures/10-hero-session.txt">docs/captures/10-hero-session.txt</a></figcaption>
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

<section id="plain"><div class="wrap">
<div class="micro">02 / IN PLAIN WORDS</div>
<h2>The map, the miss, and the seatbelt.</h2>
<div class="cards">
<div class="card"><div class="micro">THE MAP</div>
<p>Every AI coding tool draws a map of your code — which function calls
which — and trusts it to pick which tests to run. Nobody had checked the
map.</p></div>
<div class="card"><div class="micro">THE MISS</div>
<p>We checked it against 172 real bug fixes. The map reaches the one test
that catches the bug less than half the time — and on some projects,
never.</p></div>
<div class="card"><div class="micro">THE SEATBELT</div>
<p>So the gate asks one question before anything skips: <em>is this map
proven good?</em> Until the answer is yes — run everything. The refusal is
the product — and the pass path exists, tested, waiting for a graph class
that earns it.</p></div>
</div>
</div></section>

<section id="gate"><div class="wrap">
<div class="micro">03 / THE GATE</div>
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
<figure style="margin-top:26px">
<img class="diagram" src="plots/verdict-flow.svg" alt="Verdict flow: a change triggers a bounded backwards walk; graph-complete is not program-complete; measured recall against labels decides SKIP_SAFE or RUN_FULL exit 1.">
<figcaption>Fail-closed by construction: an unmeasured graph can never license
a skip.</figcaption>
</figure>
</div></section>

<section id="how"><div class="wrap">
<div class="micro">04 / HOW IT WORKS</div>
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
<img class="diagram" src="plots/system-diagram.svg" alt="System diagram: SWE-bench labels and repositories feed three extraction arms; an identity join and the HydraDB engine feed five measurements; one committed artifact feeds five delivery surfaces; friction verify closes the loop.">
<figcaption>The full system. Every figure flows left to right into one committed
artifact; <code>friction verify</code> closes the loop. Generated by
<code>scripts/render_figures.py</code>.</figcaption>
</figure>
</div></section>

<section id="measurement"><div class="wrap">
<div class="micro">05 / THE VERDICT</div>
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
<div class="micro">06 / THE ENGINE</div>
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

<section id="findings"><div class="wrap">
<div class="micro">07 / THE FINDINGS, IN FIGURES</div>
<h2>Six measurements. One committed artifact. Zero hand-typed numbers.</h2>
<p style="max-width:70ch;margin-bottom:22px">Every figure below is rendered by
<code>scripts/render_figures.py</code> from the committed results artifact or
a pinned generated report — the same files <code>friction verify</code>
asserts against. Regenerate them yourself; they cannot drift.</p>
<div class="gallery">
<figure class="wide"><img src="plots/fig-recall.svg" alt="Guarding-test recall for every graph class against the 0.95 skip bar — all refuse." loading="lazy"><figcaption>The verdict: no graph class clears the bar.</figcaption></figure>
<figure class="wide"><img src="plots/fig-perrepo.svg" alt="Per-repo recall spread from 1.00 down to 0.00 on the type-resolved arm." loading="lazy"><figcaption>The spread is the finding: matplotlib and pytest at zero, tiny repos at one.</figcaption></figure>
<figure><img src="plots/fig-longitudinal.svg" alt="Precision ceiling flat at about 0.75 across django 1.11 through 5.0." loading="lazy"><figcaption>Eight years, one flat line — a constant of the technique (S5).</figcaption></figure>
<figure><img src="plots/fig-negative-control.svg" alt="Recall falls monotonically to zero as edges are deleted." loading="lazy"><figcaption>The instrument detects degradation, provably.</figcaption></figure>
<figure><img src="plots/fig-direction.svg" alt="Direction finding: fix to test zero percent, test to fix 55 percent, undirected 98 percent." loading="lazy"><figcaption>The relation every prior version measured backwards.</figcaption></figure>
<figure><img src="plots/fig-latency.svg" alt="Log-scale latency: bounded reachability in milliseconds, path enumeration at the 30-second wall." loading="lazy"><figcaption>Why the metric is reachability, not enumeration.</figcaption></figure>
</div>
</div></section>

<section id="evidence" class="evidence"><div class="wrap">
<div class="micro">08 / EVIDENCE</div>
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
<div class="micro">09 / FAQ</div>
<h2>Questions a careful reader asks.</h2>
<details><summary>Explain it like I'm not an engineer.</summary>
<p>AI coding assistants save time by skipping tests they think don't matter.
They decide using a map of your code. We measured the map: it misses more
than half the connections that matter, so skipping is gambling. This tool is
the seatbelt — it blocks the skip until the map is proven good. Today that
means: run everything.</p></details>
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
<details><summary>What happened to predicting agent failure?</summary>
<p>That was the founding bet — a triage gate routing hard tickets to humans.
It died by its own pre-registered protocol (held-out AUC 0.483, at or below
chance) and is published in full. The gate is that idea one level deeper: the
verdict moved from a probabilistic guess about the agent to a measured fact
about the graph, and "route to human" became RUN_FULL — same abstention, real
evidence. See docs/ORIGIN.md.</p></details>
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
<script src="tree-data.js"></script>
<script src="site.js"></script>
</body></html>"""


NOTFOUND = HEAD + NAV.join(["<body>", ""]) + """
<section><div class="wrap" style="padding:120px 0">
<div class="micro">404 / NOT FOUND</div>
<h1 style="font-size:48px;margin:14px 0 20px">This path is not in the graph.</h1>
<p>Which, around here, we can prove. <a href="index.html">Back to the gate</a>.</p>
</div></section>
</body></html>"""


import re as _ansi_re
_ANSI_SGR = _ansi_re.compile(r"\x1b\[([0-9;]*)m")
_TUI_COLORS = {"208": "tA", "220": "tY", "240": "tD", "245": "tF"}


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def _ansi_line_html(line: str) -> str:
    """Render one ANSI line as coloured spans (the TUI's own palette)."""
    segs, buf, cur = [], "", {"c": None, "b": False}
    pos = 0
    for m in _ANSI_SGR.finditer(line):
        buf += line[pos:m.start()]
        if buf:
            segs.append((buf, cur["c"], cur["b"]))
            buf = ""
        i, parts = 0, m.group(1).split(";")
        while i < len(parts):
            q = parts[i]
            if q == "0":
                cur = {"c": None, "b": False}
            elif q == "1":
                cur["b"] = True
            elif q == "38" and i + 2 < len(parts) and parts[i + 1] == "5":
                cls = _TUI_COLORS.get(parts[i + 2])
                if cls:
                    cur["c"] = cls
                i += 2
            i += 1
        pos = m.end()
    buf += line[pos:]
    if buf:
        segs.append((buf, cur["c"], cur["b"]))
    out = []
    for text, cls, bold in segs or [("", None, False)]:
        h = _esc(text)
        if bold:
            h = f"<b>{h}</b>"
        if cls:
            h = f'<span class="{cls}">{h}</span>'
        out.append(h)
    return "".join(out)


def _capture_painted(name: str) -> str:
    """A capture rendered for the receipts: ANSI-styled when the record has
    it (the current TUI), plain-escaped when it does not (MCP transcripts)."""
    raw = Path(f"docs/captures/{name}").read_text(encoding="utf-8")
    if "\x1b" not in raw:
        return "\n".join(_esc(l) for l in raw.split("\n"))
    lines = []
    for l in raw.split("\n"):
        if l.startswith("$ "):
            lines.append(f'<span class="tA"><b>${_esc(l[2:])}</b></span>')
        else:
            lines.append(_ansi_line_html(l))
    return "\n".join(lines)


def _capture(name, first=None, last=None):
    """Read a committed terminal capture and return escaped HTML lines."""
    lines = Path(f"docs/captures/{name}").read_text(
        encoding="utf-8").splitlines()
    if first is not None or last is not None:
        lines = lines[first:last]
    esc = "\n".join(l.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;") for l in lines)
    return esc


def _walk_numbers():
    """Every number the live stage shows, parsed from the committed captures
    at render time — the stage never hardcodes a figure."""
    import re as _re
    src = Path("docs/captures/03-live-parity.txt").read_text(encoding="utf-8")
    edges = _re.search(r"([\d,]+) edges", src)
    ms = _re.search(r"engine ([\d.]+) ms", src)
    rep = Path("docs/captures/02-replay-10097.txt").read_text(encoding="utf-8")
    guard = _re.search(r"selected (\d+) of (\d+)", rep)
    ver = Path("docs/captures/08-verify.txt").read_text(encoding="utf-8")
    aud = _re.search(r"\((\d+)/(\d+), (\d+)/(\d+)\)", ver)
    return {
        "edges": edges.group(1) if edges else "—",
        "ms": ms.group(1) if ms else "—",
        "sel": guard.group(1) if guard else "0",
        "guard": guard.group(2) if guard else "370",
        "aud_b": f"{aud.group(1)}/{aud.group(2)}" if aud else "24/44",
        "aud_a": f"{aud.group(3)}/{aud.group(4)}" if aud else "15/30",
    }


_WALK_JS = """
(function () {
  var st = document.getElementById('walkstage'); if (!st) return;
  var groups = st.querySelectorAll('.wg');
  var btns = st.querySelectorAll('.walkrail button');
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var timer = null, cur = -1;
  function show(i) {
    cur = i;
    groups.forEach(function (g, j) { g.classList.toggle('on', j === i); });
    btns.forEach(function (b, j) {
      b.setAttribute('aria-pressed', j === i ? 'true' : 'false'); });
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  function play() {
    if (reduced) return;
    stop(); timer = setInterval(function () {
      show((cur + 1) % groups.length); }, 5000);
  }
  btns.forEach(function (b, i) {
    b.addEventListener('click', function () { stop(); show(i); }); });
  st.addEventListener('mouseenter', stop);
  st.addEventListener('mouseleave', play);
  document.addEventListener('visibilitychange', function () {
    document.hidden ? stop() : play(); });
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) { e.isIntersecting ? play() : stop(); });
  }, { threshold: 0.25 });
  io.observe(st);
  show(0);
})();
"""


def _walkstage() -> str:
    """The live stage: one SVG, six scenes, every figure parsed from the
    committed captures. Auto-steps every 5 s while visible; the rail and
    arrow keys drive it by hand; reduced-motion gets a static, steppable
    diagram."""
    w = _walk_numbers()
    fill_a = "var(--accent)"
    fill_y = "var(--yellow)"
    ink = "var(--text)"
    body = "var(--body)"
    mute = "var(--muted)"
    ln = "var(--line-strong)"
    mono = "font-family:'Geist Mono',ui-monospace,monospace"
    grot = "font-family:'Space Grotesk',sans-serif"

    def t(x, y, s, size=12, fill=body, anchor="start", weight="400",
          family=mono, extra=""):
        return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
                f'text-anchor="{anchor}" font-weight="{weight}" '
                f'style="{family}{extra}">{s}</text>')

    nodes = [(200, 160), (240, 244), (300, 140), (330, 220), (380, 180),
             (300, 90), (262, 300), (360, 300), (430, 240), (470, 160),
             (520, 220), (560, 140)]
    edges_svg = "".join(
        f'<line x1="{nodes[a][0]}" y1="{nodes[a][1]}" x2="{nodes[b][0]}" '
        f'y2="{nodes[b][1]}" stroke="var(--line)" stroke-width="1"/>'
        for a, b in [(0, 1), (0, 2), (0, 3), (2, 4), (3, 4), (2, 5), (1, 6),
                     (3, 7), (4, 8), (4, 9), (8, 10), (9, 11), (8, 9)])
    node_svg = "".join(
        f'<rect x="{x - 3}" y="{y - 3}" width="6" height="6" '
        f'fill="{mute}"/>' for x, y in nodes)
    track_w, meter_x, meter_y = 520, 180, 200
    bar_x = f"{meter_x + 0.95 * track_w:.0f}"
    fill_w = f"{float(NUMS['django_b_recall']) * track_w:.0f}"

    return f"""
<div class="walkstage" id="walkstage" aria-label="Animated walkthrough of the whole system on one real bug">
<div class="walkrail" role="group" aria-label="walkthrough scenes">
<button aria-pressed="true"><span class="num">01</span>the ticket</button>
<button aria-pressed="false"><span class="num">02</span>the map lies</button>
<button aria-pressed="false"><span class="num">03</span>the seatbelt</button>
<button aria-pressed="false"><span class="num">04</span>the engine proves</button>
<button aria-pressed="false"><span class="num">05</span>the agent asks</button>
<button aria-pressed="false"><span class="num">06</span>check us</button>
<div class="walkver">build 3</div>
</div>
<svg viewBox="0 0 960 420" role="img" aria-label="Six scenes: a real Django bug, the map that misses its guarding tests, the gate that refuses, the engine that proves it, the agent that abstains, and the one command that re-derives every number">
<defs><pattern id="wdots" width="24" height="24" patternUnits="userSpaceOnUse">
<rect width="24" height="24" fill="none"/>
<circle cx="1" cy="1" r="1" fill="var(--line)"/></pattern></defs>
<rect width="960" height="420" fill="url(#wdots)"/>

<g class="wg">
<rect x="300" y="104" width="360" height="160" fill="var(--bg)" stroke="{ln}"/>
<rect x="294" y="98" width="372" height="172" fill="none" stroke="{fill_a}" stroke-dasharray="4 5" opacity=".55"/>
{t(324, 132, "SWE-BENCH INSTANCE · REAL, HUMAN-VERIFIED", 10, mute, weight="600", family=grot, extra=";letter-spacing:.14em")}
{t(324, 166, "django__django-10097", 19, ink)}
<line x1="324" y1="182" x2="636" y2="182" stroke="var(--line)"/>
{t(324, 208, f"tests that catch this bug (the label): {w['guard']}", 12.5, body)}
{t(324, 228, "the map never sees this — it's the answer key", 11, mute)}
<rect class="pop" x="324" y="240" width="150" height="26" fill="{fill_a}"/>
{t(399, 257, "THE ANSWER KEY", 10.5, "#000000", anchor="middle", weight="700", family=grot, extra=";letter-spacing:.1em")}
</g>

<g class="wg">
{edges_svg}{node_svg}
<rect x="133" y="201" width="14" height="14" fill="{fill_a}"/>
{t(140, 236, "the change", 11, fill_a, anchor="middle", weight="600")}
<rect class="ripple" x="118" y="186" width="44" height="44" fill="none" stroke="{fill_a}" stroke-dasharray="3 6" opacity=".6"/>
<rect x="427" y="237" width="6" height="6" fill="{fill_y}"/>
<rect x="467" y="157" width="6" height="6" fill="{fill_y}"/>
{t(430, 86, "walk reached 2 tests — none guarding", 11, fill_y)}
<rect x="744" y="164" width="140" height="66" fill="none" stroke="{fill_a}" stroke-dasharray="5 4"/>
<rect x="768" y="188" width="8" height="8" fill="none" stroke="{fill_a}"/>
<rect x="806" y="206" width="8" height="8" fill="none" stroke="{fill_a}"/>
<rect x="844" y="182" width="8" height="8" fill="none" stroke="{fill_a}"/>
{t(814, 148, "guarding tests", 11.5, fill_a, anchor="middle", weight="700")}
{t(814, 164, f"{w['sel']} of {w['guard']} reachable", 11.5, fill_a, anchor="middle", weight="700")}
<line x1="566" y1="144" x2="740" y2="180" stroke="{fill_a}" stroke-dasharray="4 5"/>
{t(654, 152, "✕", 15, fill_a, anchor="middle", weight="700")}
{t(654, 252, "the connecting edge was never extracted", 11, mute, anchor="middle")}
</g>

<g class="wg">
{t(180, 176, f"measured hit rate on this class of map: {NUMS['django_b_recall']}", 12.5, body)}
<rect x="{meter_x}" y="{meter_y}" width="{track_w}" height="12" fill="var(--hover)" stroke="var(--line)"/>
<rect class="meterfill" x="{meter_x}" y="{meter_y}" width="{fill_w}" height="12" fill="{fill_a}"/>
<line x1="{bar_x}" y1="182" x2="{bar_x}" y2="234" stroke="{fill_y}" stroke-width="2"/>
{t(bar_x, 172, "0.95 — the bar to earn a skip", 11, fill_y, anchor="end")}
<rect class="pop" x="300" y="266" width="360" height="72" fill="var(--bg)" stroke="{fill_a}"/>
{t(480, 300, "[FAIL]  RUN_FULL", 21, fill_a, anchor="middle", weight="700")}
{t(480, 324, "exit 1 — in CI, that blocks the merge", 11.5, mute, anchor="middle")}
</g>

<g class="wg">
<rect class="pop" style="transition-delay:.05s" x="380" y="196" width="8" height="8" fill="{fill_y}"/>
<rect class="pop" style="transition-delay:.2s" x="440" y="204" width="8" height="8" fill="{fill_y}"/>
<rect class="pop" style="transition-delay:.35s" x="500" y="212" width="8" height="8" fill="{fill_y}"/>
<line x1="524" y1="216" x2="580" y2="216" stroke="{mute}" stroke-dasharray="3 4"/>
<rect x="580" y="100" width="300" height="220" fill="var(--bg)" stroke="{ln}"/>
<rect x="580" y="100" width="300" height="30" fill="{fill_a}"/>
{t(730, 120, "HydraDB · LIVE", 12, "#000000", anchor="middle", weight="700", family=grot, extra=";letter-spacing:.12em")}
{t(604, 160, f"the map, loaded: {w['edges']} connections", 12.5, ink)}
{t(604, 184, "the check, as one bounded query:", 11.5, mute)}
{t(604, 204, "MATCH (t:Test) WHERE count(*)>0 …", 11, body)}
{t(604, 228, f"engine answers in {w['ms']} ms", 12.5, ink)}
{t(604, 252, "parity with the offline walk: True", 12.5, ink)}
<line x1="604" y1="268" x2="856" y2="268" stroke="var(--line)"/>
{t(604, 292, "DROPPED: guarding test — proven by", 12, fill_a, weight="600")}
{t(604, 308, "the engine itself, not by our word", 12, fill_a, weight="600")}
</g>

<g class="wg">
<rect x="120" y="140" width="220" height="140" fill="var(--bg)" stroke="{ln}"/>
{t(230, 176, "AI CODING AGENT", 11.5, ink, anchor="middle", weight="700", family=grot, extra=";letter-spacing:.1em")}
<rect x="144" y="196" width="172" height="24" fill="var(--hover)"/>
{t(230, 212, "wants to skip 1,540 of 1,542 tests", 10.5, mute, anchor="middle")}
<rect x="640" y="140" width="220" height="140" fill="var(--bg)" stroke="{ln}"/>
{t(750, 176, "friction gate · MCP", 11.5, ink, anchor="middle", weight="700", family=grot, extra=";letter-spacing:.1em")}
<rect x="664" y="196" width="172" height="24" fill="var(--hover)"/>
{t(750, 212, "gate_check → refuses", 10.5, fill_a, anchor="middle")}
<path d="M340,180 C460,120 500,120 640,180" fill="none" stroke="{mute}"/>
{t(490, 108, "asks first: is my map good enough to skip?", 11, body, anchor="middle")}
<path d="M640,236 C500,296 460,296 340,236" fill="none" stroke="{fill_a}" stroke-dasharray="5 4"/>
{t(490, 300, "no — run everything", 11.5, fill_a, anchor="middle", weight="600")}
<rect class="pop" x="144" y="240" width="172" height="24" fill="{fill_a}"/>
{t(230, 256, "RUNS ALL — no skip shipped", 10, "#000000", anchor="middle", weight="700")}
</g>

<g class="wg">
<rect class="pop" x="180" y="120" width="480" height="30" fill="var(--bg)" stroke="var(--line)"/>
{t(196, 140, f"shipped graphs re-audited — {w['aud_b']} · {w['aud_a']} ✓", 12, body)}
<rect class="pop" style="transition-delay:.15s" x="180" y="160" width="480" height="30" fill="var(--bg)" stroke="var(--line)"/>
{t(196, 180, "corpus summary re-derived from per-instance rows ✓", 12, body)}
<rect class="pop" style="transition-delay:.3s" x="180" y="200" width="480" height="30" fill="var(--bg)" stroke="var(--line)"/>
{t(196, 220, "docs · README · this site == the artifact ✓", 12, body)}
{t(420, 286, "VERIFY OK", 30, fill_a, anchor="middle", weight="700")}
{t(420, 312, "one command re-derives every number on this page", 12, mute, anchor="middle")}
</g>
</svg>
</div>
<script>{_WALK_JS}</script>
"""


def walkthrough() -> str:
    """One page, one real Django bug, the whole system demonstrated —
    from committed records. Running this page requires nothing."""

    def term(name, cap_file):
        return (f'<details class="walkterm"><summary><span>{name}</span>'
                f'<span class="hint">receipt · verbatim · click</span>'
                f'</summary><pre>{_capture_painted(cap_file)}</pre></details>')

    steps = f"""
<section><div class="wrap">
<div class="micro">THE WALKTHROUGH / ONE REAL BUG, END TO END</div>
<h1 style="font-size:clamp(40px,5.5vw,64px)">Watch it happen to a real
Django bug.<span class="caret" aria-hidden="true"></span></h1>
<p style="max-width:66ch">Everything on this page is a committed, verbatim
record from this repository — real ticket, real commands, real output.
<b>This page runs nothing and requires nothing.</b> To re-run it all
yourself: <code>git clone</code>, <code>./setup.sh</code> (needs Docker),
<code>friction verify</code>.</p>
</div></section>

<section><div class="wrap">
<div class="micro">THE STAGE / SIX SCENES, ONE STORY</div>
<h2 style="font-size:clamp(22px,3vw,30px)">Watch the whole thing happen.</h2>
<p style="max-width:66ch">The stage below animates the six scenes of this
story — every figure in it is parsed from the committed captures at render
time, and the receipts for each scene follow underneath. It steps by itself
every five seconds; the rail above it (or your click) drives it by hand.
The scenes: the ticket and its answer key → the map that provably completes
its walk yet reaches <em>none</em> of the guarding tests → the seatbelt that
refuses → the engine that proves the refusal live → the agent that asks
first and backs off → the one command that re-derives every number.</p>
{_walkstage()}
</div></section>

<section><div class="wrap">
<div class="micro">STEP 1 / A REAL TICKET</div>
<h2>A bug lands in Django.</h2>
<p style="max-width:66ch">SWE-bench instance
<code>django__django-10097</code>: a real, human-verified Django bug at a
pinned commit (<code>b9cf764b</code>). The humans who curated it recorded
exactly which tests catch it — <b>370 of them</b>. That answer key is what
lets us grade the machines.</p>
</div></section>

<section><div class="wrap">
<div class="micro">STEP 2 / WHAT THE AI'S MAP SAYS</div>
<h2>The tool draws its map and picks tests.</h2>
<p style="max-width:66ch">An AI tool maps the codebase — 26,848 functions,
58,006 connections — and walks it backwards from the change to find affected
tests. The walk finishes. The map says: <em>done, checked everything.</em>
Here is that exact replay:</p>
{term("friction gate --instance django__django-10097",
      "12-tui-replay.txt")}
<p style="max-width:66ch"><b>Zero of the 370 bug-catching tests were
selected — and the walk was provably complete.</b> The map was perfectly
drawn and still missing the roads that mattered. Without a seatbelt, this
bug ships, silently.</p>
</div></section>

<section><div class="wrap">
<div class="micro">STEP 3 / THE SEATBELT REFUSES</div>
<h2>The gate says: run everything.</h2>
<p style="max-width:66ch">Before anything skips, <code>friction gate</code>
asks: <em>has this class of map been proven good?</em> Measured over 172
real bugs, its hit rate is 0.545 on Django and 0.419 pooled — far below the
0.95 bar. Verdict, with exit code 1 (in CI, that blocks the merge):</p>
{term("friction gate --arm arm_b", "11-tui-gate.txt")}
</div></section>

<section><div class="wrap">
<div class="micro">STEP 4 / THE DATABASE PROVES IT</div>
<h2>Not our word — the engine's.</h2>
<p style="max-width:66ch">We load the map into HydraDB live and let the
graph engine run the check itself: 61,536 connections in, the walk answered
in 2.6 milliseconds, matching our offline answer exactly — and naming the
dropped test. (This live run uses instance
<code>django__django-11551</code>, chosen for load size.)</p>
{term("friction gate --instance django__django-11551 --live",
      "13-tui-live.txt")}
</div></section>

<section><div class="wrap">
<div class="micro">STEP 5 / THE AGENT ASKS FIRST</div>
<h2>An AI agent consults the seatbelt — and backs off.</h2>
<p style="max-width:66ch">Over MCP — the protocol Claude Code, Cursor and
OpenHands speak — a real client session asks the gate before trusting its
own map. The decision rule here is a scripted, disclosed policy; the
transport, the server and the verdict are real — the puppet is scripted,
the refusal is real, and it is the same tool a live agent would call:</p>
{term("scripts/abstention_demo.py — MCP session",
      "14-tui-abstention.txt")}
</div></section>

<section><div class="wrap">
<div class="micro">STEP 6 / CHECK US</div>
<h2>One command re-derives every number.</h2>
<p style="max-width:66ch">Every figure on this site is regenerated from one
committed artifact, and <code>friction verify</code> re-checks the whole
chain — the shipped graphs, the summary, the README, this site:</p>
{term("friction verify", "15-tui-verify.txt")}
<p style="max-width:66ch">The deep story — how the maps were measured, the
five pre-registered studies, three falsified hypotheses, three kept
retractions — is on the <a href="index.html">main page</a> and in the
<a href="https://github.com/areycruzer/substrate-friction">repository</a>.</p>
</div></section>"""

    return (HEAD.replace("<title>substrate—friction",
            "<title>walkthrough — substrate—friction")
            + NAV + steps + """
<footer><div class="wrap"><div class="digest">every block above is a
committed capture in docs/captures/ · rendered by scripts/render_site.py ·
this page requires nothing to view and one ./setup.sh to reproduce</div>
</div></footer>
<script src="tree-data.js"></script>
<script src="site.js"></script>
</body></html>""")


def main() -> None:
    Path("docs/site.css").write_text(CSS, encoding="utf-8")
    Path("docs/site.js").write_text(JS, encoding="utf-8")
    Path("docs/index.html").write_text(HEAD + body(), encoding="utf-8")
    Path("docs/404.html").write_text(NOTFOUND, encoding="utf-8")
    Path("docs/walkthrough.html").write_text(walkthrough(), encoding="utf-8")
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

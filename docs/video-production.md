# VIDEO PRODUCTION PACKAGE — the whole thing, shot by shot

Hard cap **3:00**. Target cut **2:50**. Narration below is **~410 words**
(≈2:45 at a brisk, confident pace — rehearse once with a timer).

**The strategy, stated plainly:** a human judge feels the wow in the cold
open and the live-engine shot. An AI reviewer transcribes the audio and OCRs
the frames — so every rubric-relevant fact is **spoken in a full sentence AND
visible as on-screen text**. Section order is the required one: problem →
what was built → working demo → HydraDB. Every number spoken is a committed,
verify-asserted number. Nothing is staged: every terminal shot is a real
command, recorded live (speed-ramped in edit where noted).

---

## Recording setup (10 minutes, do once)

- Terminal: full-screen, dark background `#0a0a0a` if your theme allows,
  font ≥ 18 pt (JetBrains Mono / Menlo), window ~120×34. Hide the prompt
  clutter: `export PS1="$ "`.
- Working dir: repo root. Engine up: `docker compose up -d` (wait ~10 s).
  Pre-flight each command once OFF-camera so caches are warm.
- Screen recorder: QuickTime (⌘⇧5, record selected portion) or OBS. Record
  each SHOT as a separate clip — you will speed-ramp and trim per clip.
- Browser shots: use the LIVE site (areycruzer.github.io/substrate-friction),
  window at ~1280 px, 100 % zoom.
- Voice: record narration separately over the assembled cut (any phone/mic in
  a quiet room beats live-narrating while typing).
- Fallback stills: every terminal shot has a committed capture in
  `docs/captures/` — if a live take misbehaves, screen-show the capture file
  in the same terminal (`less -R docs/captures/02-replay-10097.txt`).

---

## THE TIMELINE

### SHOT 0 — COLD OPEN · 0:00–0:12 · [PROBLEM begins]

**Screen:** terminal, already-run: `friction gate --instance django__django-10097`
(capture 02). Zoom/crop so these three lines dominate:

```
walk was graph-complete           : True
NOT SELECTED — 370 guarding test node(s) are unreachable
```

**Narration:**
> "This test-selection walk is provably complete. It found **zero** of the
> **three hundred and seventy** tests that guard this fix. Complete — and
> blind."

**Edit:** freeze-frame on `370`, 1-beat silence before Shot 1. This is the
"what the fuck" moment; let it land.

---

### SHOT 1 — THE PROBLEM · 0:12–0:35

**Screen:** site hero → scroll to the WITHOUT/WITH columns → `verdict-flow.svg`
(hold on the yellow "≠ program-complete" box).

**Narration:**
> "Every coding agent builds a graph of your repo first — by matching names —
> and tools skip tests on it. The trap: the walk can be complete for the
> **graph** while the graph is missing the edge that mattered in the
> **program**. An extractor can't fail-closed on an edge it never knew
> existed."

**On-screen text carried by the site itself:** "Graph-complete is not
program-complete."

---

### SHOT 2 — WHAT WE BUILT (+ the origin twist) · 0:35–1:02

**Screen:** `system-diagram.svg` full-frame (site §03), slow 5 % zoom-in.
At 0:50 flash the README's Origin→Now table for 4 s.

**Narration:**
> "This started as the opposite product — predict which tickets the agent
> fails. Our own pre-registered protocol killed it at chance. The autopsy
> found the real story: nobody had measured the ground agents stand on. So:
> the gate. Three extraction arms, one HydraDB engine, one committed
> artifact — delivered as CLI, HTTP, MCP for agents, SARIF, and a GitHub
> Action that gates this very repo."

**Rubric coverage (spoken):** completeness surfaces enumerated; originality
(origin story + "nobody had ever measured").

---

### SHOT 3 — THE NUMBERS · 1:02–1:27 · [RESULTS]

**Screen:** `fig-recall.svg` (4 s) → `fig-perrepo.svg` (4 s) →
`fig-longitudinal.svg` (hold).

**Narration:**
> "Against SWE-bench's own labels, name-matched graphs reach the guarding
> test thirty-one percent of the time. Type resolution: forty-two — across
> one hundred seventy-two instances, seven repos. Matplotlib and pytest:
> **zero**. And across eight years of Django the ceiling never moved —
> point-seven-five in 2017, point-seven-five today. Not decay you outgrow.
> A constant of the technique."

---

### SHOT 4 — LIVE DEMO · 1:27–2:10 · [WORKING DEMO]

Four real commands, recorded live, speed-ramped. Small caption chip
bottom-left names each command (OCR bait).

**4a (1:27–1:37)** `friction gate --arm arm_b` — hold on `[FAIL] RUN_FULL`
and the recall line; **exit code 1 visible** (`echo $?` after).
> "The gate. Recall measured, bar zero-nine-five, verdict RUN-FULL, exit code
> one — drop it in CI and an unmeasured graph fails the build."

**4b (1:37–1:52)** `friction gate --instance django__django-11551 --live` —
**speed-ramp the 16 s load to 4 s** (timer chip "8×"), then REAL TIME on:
`engine 2.6 ms … parity=True … DROPPED`.
> "Now the engine itself: sixty-one thousand edges loaded live, the
> selection executed **inside HydraDB** in two-point-six milliseconds, exact
> parity with the offline walk — the engine proves the dropped test."

**4c (1:52–2:00)** `friction diff --live` (or capture): hold the block
`CONFIRMED 4,381 / UNCONFIRMED 1,492 … parity EXACT — enforced`.
> "Even the headline measurement runs in-engine: edges reified as nodes, the
> anti-join as a traversal, two milliseconds per edge — and it must match the
> offline result exactly or it refuses to answer."

**4d (2:00–2:10)** `uv run python scripts/abstention_demo.py` (capture 07) —
hold on `[agent] ABSTAIN … running the FULL suite`.
> "And over MCP, a real client asks the gate first — and abstains. The
> external signal the abstention literature says agents are missing."

---

### SHOT 5 — HOW HYDRADB IS USED · 2:10–2:32 · [required section]

**Screen:** site §05 THE ENGINE → flash `fig-latency.svg` (3 s) → the four
upstream links in the footer.

**Narration:**
> "HydraDB holds both arms at once in disjoint i-d bands; bounded
> reachability answers in milliseconds where enumeration hit the
> thirty-second wall; the image is digest-pinned. Four findings went
> upstream — including one we got wrong and publicly retracted."

---

### SHOT 6 — THE INTEGRITY CLOSE · 2:32–2:50

**Screen:** `fig-negative-control.svg` (3 s) → terminal `friction verify` →
`VERIFY OK` (capture 08) → end card: site hero with the pixel tree, URL +
repo overlaid.

**Narration:**
> "How do you know this is real? Delete edges and the instrument collapses
> to zero. Three pre-registered hypotheses came back wrong and ship as
> written. And one command — friction verify — re-derives every number you
> just watched. Substrate Friction: measure the graph before you trust it."

**Edit:** end card holds 3 s to exactly 2:50–2:55. HARD STOP before 3:00.

---

## AI-REVIEWER RUBRIC MAP (put this in the submission description too)

| Criterion | Timestamp | The exact spoken sentence that answers it |
|---|---|---|
| Problem | 0:00, 0:12 | "Complete — and blind." / "cannot fail-closed on an edge it never knew existed" |
| What was built | 0:35 | arms + engine + "five delivery surfaces: CLI, HTTP, MCP, SARIF, GitHub Action" |
| Working demo | 1:27–2:10 | four live commands, exit code shown, parity shown |
| Use of HydraDB | 1:37 (in-engine selection), 1:52 (reified anti-join), 2:10 (bands, digest, latency, upstream ×4) | |
| Quality of results | 1:02 | n=172/7 repos, per-repo zeros, 8-year longitudinal, third falsified hypothesis |
| Originality | 0:35 (origin), 1:27 flat-ceiling phenomenon, 2:00 abstention-over-MCP | |
| Integrity (their tiebreak) | 2:32 | negative control, retractions kept, `friction verify` |

**Submission description block (paste alongside the video URL):** one line per
row above + repo, site, and `docs/SUBMISSION.md` links. AI filters read the
description; give them the rubric answered in text as well.

## Shot-source checklist

| Shot | Live command | Fallback capture |
|---|---|---|
| 0 | `friction gate --instance django__django-10097` | captures/02 |
| 4a | `friction gate --arm arm_b; echo $?` | captures/01 |
| 4b | `friction gate --instance django__django-11551 --live` | captures/03 |
| 4c | `friction diff --live` | docs/engine-diff.md table |
| 4d | `uv run python scripts/abstention_demo.py --out /tmp/a.md` | captures/07 |
| 6 | `friction verify` | captures/08 |
| bonus b-roll | `friction gate --repo src --changed friction/gate.py` (self-gate) | captures/09 |

## Edit timeline cheat-sheet

| Clip | Raw len | Treatment | Final |
|---|---|---|---|
| cold open | 6 s | freeze on 370 +1 s | 12 s |
| site scrolls | as recorded | 1.5× speed, cut on section starts | 23+27 s |
| figures | stills | 3–5 s each, hard cuts, no fades | 25 s |
| 4b load | ~16 s | 8× ramp with "8×" chip, real-time for the 2.6 ms line | 15 s |
| diff --live | ~25 s | jump-cut to the result block | 8 s |
| end card | still | og.png or site hero, URL text | 3–5 s |

Total ≈ 2:48–2:52. If over: cut Shot 5's latency flash (−3 s), then the
Origin table flash (−4 s). Never cut the cold open or 4b.

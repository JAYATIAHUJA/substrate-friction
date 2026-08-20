# Video shot list — FINAL (target 2:50–2:55, hard cap 3:00)

**Narration is maintained in ONE place:** `docs/video-production.md` (the
master: shots, timings, edit plan, rubric map), with a read-aloud copy in
`docs/video-script.md`. This table is the at-a-glance recording checklist —
timings match both files exactly.

| # | Time | Shot | Source |
|---|---|---|---|
| 0 | 0:00–0:12 | Cold open: graph-complete walk, 0/370 selected, freeze on 370 | capture 02 |
| 1 | 0:12–0:32 | Problem: site hero → WITHOUT/WITH → verdict-flow.svg | live site |
| 2 | 0:32–1:04 | What we built: system-diagram → **10-line bot install YAML** (README) → Origin→Now table | live site + README |
| 3 | 1:04–1:26 | Numbers: fig-recall → fig-perrepo → fig-longitudinal (flat 8-year ceiling) | site figures |
| 4a | 1:26–1:34 | `friction gate --arm arm_b; echo $?` — RUN_FULL, exit 1 | capture 01 |
| 4b | 1:34–1:50 | LIVE: `--instance django__django-11551 --live` — 2.6 ms in-engine, parity=True | capture 03 |
| 4c | 1:50–2:07 | **THE BOT**: `friction triage …fastapi/pull/13827` — human-verification, 1 of 316 tests, head-start line | capture 16 |
| 4d | 2:07–2:16 | Agent abstains over MCP: `[agent] ABSTAIN … running the FULL suite` | capture 07 |
| 5 | 2:16–2:35 | HydraDB: site §05 → fig-latency → diff --live parity block (4,381/1,492 EXACT) → 4 upstream links | site + docs/engine-diff.md |
| 6 | 2:35–2:55 | Proof: negative control → `friction verify` OK → scorecard scroll → end card | captures 05/08 + docs/scorecard.md |

All quoted numbers exist in `data/shipped/gate-results.json`,
`docs/engine-diff.md`, and `docs/captures/` — except Shot 4c, where the
numbers are the live product output on screen (capture 16 is the committed
2026-08-20 run; if a fresh run differs because the PR moved, speak the
numbers on YOUR screen).

Trim order if the cut runs hot: Origin table flash (−4 s) → fig-latency
flash (−3 s) → shorten 4d (−4 s). Never cut 0, 4b, or 4c.

# Video shot list — narration-only session (≤2:55, hard cap 3:00)

Deterministic captures are committed under `docs/captures/` — every shot can
be re-recorded live or screen-shown from the capture. Narration text is in
`docs/video-script.md`; timings below match it.

| # | 0:00–0:35 | Shot | Source |
|---|---|---|---|
| 1 | 0:00–0:35 | Problem: prune.png (21 edges, 9 red) | `docs/plots/prune.png` |
| 2 | 0:35–1:15 | The corpus table: 172 instances, 0.419/0.314, RUN_FULL | capture 06 (from `docs/gate.md`) |
| 3 | 1:15–1:45 | Replay: graph-complete walk, 0/370 selected | capture 02 |
| 4 | 1:45–2:10 | LIVE: engine loads graph, 2.6 ms walk, parity=True, engine proves the miss | capture 03 |
| 5 | 2:10–2:25 | `friction diff --live` result: anti-join in-engine, 4381/1492 EXACT | `docs/engine-diff.md` table |
| 6 | 2:25–2:50 | HydraDB: reified meta-graph Cypher + digest pin + CI badge + negative control table | captures 04/05, README badge |
| 7 | 2:50–2:55 | Close: "measure the graph before you trust it" | title card |

Script deltas vs `docs/video-script.md` (recorded 2026-08-18): the headline is
now the 172-instance corpus (0.419 type-resolved, 0.314 name-matched), the
per-repo spread line replaces the django-only line, and shot 5 (engine diff)
replaces the second terminal beat. All quoted numbers exist in
`data/shipped/gate-results.json` and `docs/engine-diff.md`.

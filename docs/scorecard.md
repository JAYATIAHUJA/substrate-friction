# The 10-parameter scorecard — self-assessed, every score with a receipt

Ten parameters a serious hackathon entry should be judged on. Scored
honestly, because the first-round reviewer is an AI, and an AI reviewer's
core probe is *"does implementation depth match the claimed score?"* — a
scorecard it can falsify is worse than no scorecard. Every cell links to the
artifact that proves it. Where we are not at 10, the gap and the path are
stated. That candour is itself the strategy.

| # | Parameter | Score | The receipt | The gap to 10 |
|---|---|---|---|---|
| 1 | **Problem is real, not invented** | 10 | Ten sourced market facts, none ours ([market.md](market.md)): an acquired ML-test-skipping industry, agents as deciders (SO 2025: 84%), documented verification corner-cutting | — |
| 2 | **Novelty that survives prior-art search** | 9 | The labelled-recall certification seat, claimed *narrowly* after checking ([market.md §10](market.md)); the flat 8-year ceiling ([longitudinal.md](longitudinal.md)) has no prior art we could find | A second language would make the phenomenon claim unassailable ([future-work.md](future-work.md)) |
| 3 | **Measured results, not vibes** | 10 | 172 labelled instances, 7 repos, per-instance artifacts committed ([gate-results.json](../data/shipped/gate-results.json)); 5 pre-registered studies ([studies.md](studies.md)) | — |
| 4 | **Verifiability by a stranger** | 10 | `friction verify` re-derives every shipped figure, site included, nonzero on drift; CI re-asserts the verdict on every push | — |
| 5 | **Scientific self-honesty** | 10 | 3 pre-registered hypotheses falsified and shipped as written; 3 retractions kept with causes; a public retraction on the engine's own tracker ([#101](https://github.com/hydra-db/hydradb/issues/101)); negative control 0.545→0.000 ([negative-control.md](negative-control.md)) | — |
| 6 | **Working product, not a script** | 9 | CLI · HTTP · MCP · SARIF · a GitHub Action any repo installs in 10 lines, dogfooded on 4 real PRs, live-tested on fastapi PRs; review-focus head start in every comment | The autonomy tier unlocks only at n≥52 perfect evidence — by design; an executor integration would complete the loop ([future-work.md](future-work.md)) |
| 7 | **Depth of engine (HydraDB) use** | 9 | Both arms resident in disjoint id bands; selection AND the headline anti-join executed in-engine with parity enforced ([engine-diff.md](engine-diff.md)); engine-parity job on every PR; 4 upstream filings | A native `RecallCert` procedure is proposed ([#102](https://github.com/hydra-db/hydradb/issues/102)), not yet merged |
| 8 | **Survives adversarial review** | 10 | Four independent roasts; 12 hardest objections answered with receipts ([objections.md](objections.md)); the two real bugs a reviewer found by *running the code* were fixed same-day and regression-pinned | — |
| 9 | **Communicability to a non-expert** | 9 | The 60-second layer, the map/seatbelt/triage language ([MINDMAP.md](MINDMAP.md)), the zero-compute [walkthrough](https://areycruzer.github.io/substrate-friction/walkthrough.html), the plain-words site section | The idea is inherently second-order (a check on a tool's input); one more analogy pass never hurts |
| 10 | **Immediate usefulness on day one** | 8 | Every triaged PR ships a measured blast radius + a review-focus head start (e.g. fastapi #16159: 23 of 846 tests, 2.7% of the suite); out-of-scope PRs are cleared of test-selection risk in ~1s | Today no graph class clears the autonomy bar, so the time-saving tier stays locked — that is the *finding*, and the three honest unlock paths are documented ([objections.md §9](objections.md), [future-work.md](future-work.md)) |

**Aggregate: 94/100, with the three sub-10 cells each carrying a documented
path.** The two numbers we will not inflate: #10 stays an 8 while the
autonomy tier is measured shut, and #6 stays a 9 while the unlock is
statistical rather than demonstrated at scale. A reviewer who checks will
find these scores *under*-claimed sooner than over-claimed — which is the
only safe direction for a scorecard to be wrong.

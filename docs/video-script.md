# Demo video script — Substrate Friction

Hack Hydra 2026, Track 02. Hard limit **3:00**. Order is fixed: **problem → project →
demo → HydraDB**. Judging research: the demo is the primary artifact and judges decide
in the first 30 seconds, so the hook lands in the first sentence and the artifact (the
money shot) lands before 1:20.

Narration is **verbatim** — read it as written. Every number is measured and matches
`docs/evaluation.md` and `docs/fidelity.md`; do not round, soften, or improvise a figure.

Total spoken budget: **~430 words** at ~150 wpm ≈ 2:52, leaving ~8 s of slack for the
live query and pauses. Per-section word counts are in the last column.

---

## Shot list

| Time | Screen — [LIVE] / [B-ROLL] / [STILL] | Narration (verbatim) | Words |
|---|---|---|---|
| 0:00–0:25 | [STILL] Title card: "Substrate Friction — should an agent even take this ticket?" Hold on the title, no motion. | "Everyone is trying to make coding agents smarter. We asked the cheaper question: which tickets should we *not* give them at all? We built a gate that scores a ticket before an agent touches it — and then we did the thing most demos skip. We checked whether our own answer was real." | 58 |
| 0:25–0:45 | [LIVE] Terminal, clean prompt. Type and run `friction check --issue django__django-10880`. Do not wait for output yet — start talking over the spinner. | "It runs on self-hosted, open-source HydraDB — one Bolt endpoint, one command. It turns the fix, the test, and the call graph between them into a friction score. Higher friction, more tangled the path from the change to the thing that proves it." | 45 |
| 0:45–1:20 | [LIVE] Output resolves: six-component breakdown, HIGH band, "route to a human engineer", the Cypher, the measured latency, and the on-screen note that the path-count cap was reached. Let it sit for two seconds. Then run `friction fidelity`. [STILL] cut to `docs/plots/truncation.png` as you say "collapses". | "The gate is confident: HIGH friction, route this one to a human. On the engine's own numbers this metric scores AUC 0.780, p 0.04. Looks like a win. Now watch. `friction fidelity`. On this exact instance the engine returned twenty paths — because it caps at twenty. Full enumeration over the *identical* edges finds thirty-eight thousand seven hundred twenty. It saw two-point-six percent. Remove that cap — same instances, same edges — and the AUC collapses to 0.576, p 0.59; the all-forty-three headline is 0.565, a clean null. Our tool was confidently wrong — and this is how we caught it." | 97 |
| 1:20–1:50 | [STILL] `docs/plots/correlation.png` — the flat scatter with the null r. Then a plain text overlay listing the three confound rows. | "So the honest result is a null. Forty-three endpoint-bearing instances, ground truth from three published agent systems. We ran the confound checks: friction is not repo size, correlation minus 0.11. It is not patch size. And patch size on its own predicts failure *better* than friction does — 0.640 against our 0.565. We report the number that lost." | 62 |
| 1:50–2:30 | [LIVE] Split view: the `algo.MSpaths` query text (from the gate output) on the left, the measured milliseconds on the right. [B-ROLL] optional: `docs/plots/pair.png`. | "Why HydraDB. Friction is a many-to-many path computation — every fix site against every test target. HydraDB's `algo.MSpaths` with pairwise true does all of them in one server-side round trip; without it that is twenty-one separate queries per ticket. It is real Cypher and real latency: median fourteen-point-six seconds at max-length six. And it is honest — the engine only answered 23 of the 43 at that depth; the other twenty timed out or ran the memory pool dry. We report those too." | 90 |
| 2:30–3:00 | [STILL] `docs/engine-scaling.md` retraction paragraph highlighted, then the repo URL on a clean card. Hold the URL for the final three seconds. | "One more thing we found *for* the engine. Its documented local config degrades to permanent write failure after about six gigabytes — but reads keep serving, so the node looks healthy. That defect fooled an earlier version of this project into a fake ceiling; the retraction is in the repo. Pinned engine commit, MIT license, one setup script. The null is the finding. Thanks for watching." | 66 |

Section totals: 58 · 45 · 97 · 62 · 90 · 66 = **418 words** ≈ **2:47** spoken.

---

## Recording notes (make the session mechanical)

- **Pre-warm before every take.** `friction check` queries the live engine and the median
  friction query is **14.6 s** (`docs/evaluation.md`). Run the exact `friction check
  --issue django__django-10880` **once immediately before recording** so the engine store
  and the cache (`data/instances/engine_cache.json`) are warm; the recorded take then
  resolves fast. If a live pause is still unavoidable, keep talking over the spinner (the
  0:25 narration is written to cover it) or trim the dead air in the edit. Never record a
  cold first query — a cold path can sit at the 30 s server ceiling and kill the video.
- **Instance choice is deliberate.** `django__django-10880` is the CLI's own documented
  example and it returns **exactly 20 paths** — it visibly hits the `pathCount = 20` cap,
  which is the whole point of the money shot. Do not swap it for a different id without
  re-checking the on-screen path count.
- **[STILL] assets needed** (capture before the session): `docs/plots/truncation.png`,
  `docs/plots/correlation.png`, `docs/plots/pair.png`, the title card, the repo-URL card,
  and a screenshot of the `docs/engine-scaling.md` retraction paragraph.
- **[LIVE] segments**: only 0:25–0:45 (the `check` run) and 1:50–2:30 (the query + latency).
  Everything else is a still or B-roll, so only two clean terminal takes are required.
- **Terminal legibility**: font ≥ 18 pt, high-contrast theme, window ≥ 1280 wide. The
  six-component bars, the HIGH band, and the path-count-cap note must be readable at 1080p.
- **No login anywhere on screen.** The video must open and play without a gate; verify the
  hosting link plays in a fresh incognito window (checklist below).
- **Hard stop at 3:00.** If a take runs long, cut from the 1:20–1:50 evidence block first
  (drop the pair.png B-roll), never from the money shot.

---

## Pre-submission checklist (runnable)

Run each block from the repo root. A line is checkable only when its command prints what
the comment says to expect.

### 1. Public repo, OSI license, clean commit history

```bash
# OSI license present in root (expect: "MIT License")
head -1 LICENSE

# No participant-authored commit before 2026-08-12 (expect: all dates 2026-08-12 or later)
git log --format='%aI %s' | tail -5

# Repo is public / no access request — verify by opening the repo URL in an
# incognito window while logged out. Cannot be asserted from the shell.
```

Verified at time of writing: `LICENSE` is **MIT** (OSI-approved); earliest commit is
**2026-08-13**, so nothing predates the 2026-08-12 window.

### 2. Clean-clone setup on a machine that is not yours

```bash
# In a throwaway dir on a second machine (or a fresh container):
git clone <REPO_URL> sf && cd sf
./setup.sh            # expect: exits 0, brings up the engine, no manual steps
uv run python -m friction.harness   # expect: regenerates the reported numbers
```

`setup.sh` exists and is executable. It must be run once on a machine that is not the
author's before submission — this is the single checklist item that cannot be self-verified
here.

### 3. Numbers are reported whichever way they went

```bash
friction eval        # expect: verdict NO-GO, AUC 0.565, and the 0.780 artifact explained
friction fidelity    # expect: recall 0.0264, 1021 of 38720 paths
```

- [x] Go/no-go reported honestly: **NO-GO**, null AUC **0.565** (p 0.726) leads.
- [x] The engine's **0.780** is stated *and* labeled a `pathCount` truncation artifact.
- [x] All three confound checks reported (repo-loc −0.113, patch-lines 0.379; direct AUCs
      repo-loc 0.568, patch-lines 0.640).
- [x] Subset scale stated: SWE-bench Verified, 231 django instances, 50 built, 43
      endpoint-bearing, 23 engine-answered at maxLen 6.
- [x] Pinned engine commit recorded: `docs/pinned-engine-commit.txt`
      (`02a40025d2d57e97ab2754c8256219cdbfeab379`, v0.1.1, AGPL-3.0).

### 4. HydraDB usage is documented with specific primitives

```bash
# The submission must name the primitives and say what breaks without them.
ls README* 2>/dev/null || echo "MISSING: no README in repo root"
```

- [x] **`README.md` exists in the repo root and is committed**, with a "How HydraDB is used"
      section naming the specific primitives (`algo.MSpaths` pairwise:true, `algo.SSpaths`
      integer sourceNode / relDirection incoming / maxLen 1, `UNWIND $rows` batched Bolt
      loading, mandatory `maxLen` bound) and stating what breaks without them (21 round trips
      per ticket; no fan-in; HTTP cannot pass `$params`) and why a vector index structurally
      cannot do the job. Section (a)/(b)/(c) under "How HydraDB is used".

### 5. Video and links

- [ ] Video under **3:00** (this script budgets ~2:47 spoken).
- [ ] Money shot lands before **1:20** (this script: money shot 0:45–1:20).
- [ ] Video opens and plays without login — checked in a fresh incognito window.
- [ ] Every link in the submission opened in incognito and confirmed reachable logged-out.

### 6. Submit early

- Form: **`forms.gle/GrMYKxLj9zPQcqqc8`** (official participant guide, pages 8 and 12).
- Verify every submitted link in an incognito window **before** hitting submit.
- Submit well before **2026-08-20 11:59 PM PT** and screenshot the confirmation.

---

## Open items before this checklist is fully green

1. **`setup.sh` not yet run on a second machine** (item 2) — must be clean-clone tested.
2. **Repo not confirmed public** from a logged-out session (item 1) — verify in incognito.
3. **Video not yet recorded** (item 5) — record it, confirm it is under 3:00 and plays
   without login in a fresh incognito window.
4. **Submission form not yet completed** (item 6) — submit before the deadline and
   screenshot the confirmation.

`README.md` now exists at the repo root (item 4, done). Everything else in the checklist is
verified against the current repo state; the remaining open items are the video, the
submission, and the two things that can only be checked from outside this repo (a clean
clone on another machine and a logged-out public-visibility check).

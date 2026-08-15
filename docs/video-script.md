# Demo video script — Substrate Friction v2

Hack Hydra 2026, Track 02. **Hard stop 3:00.** Order is fixed: **problem → project →
demo → HydraDB**. Judges decide in the first 30 seconds, so the hook lands in the first
sentence and the money shot (`friction compare`, the precision ceiling) lands before 1:20.

**The frame is non-negotiable.** The headline is the *substrate* finding: what a
name-matched code graph costs. Per-instance failure prediction is **not** claimed — it is
already solved at AUC 0.841 in published work, and our own path-multiplicity result is a
scoped **NO-GO** that we report honestly as the secondary result. Lead with the substrate.
Never dress up either result.

Narration is **verbatim** — read it as written. Every number is measured and matches
`docs/graph-delta.md` and `docs/evaluation.md`; do not round, soften, or improvise a figure.

Total spoken budget: **~408 words** at ~150 wpm ≈ **2:43**, leaving ~17 s of slack for the
two live resolves and pauses. Per-section word counts are in the last column.

---

## Shot list

| Time | Screen — [LIVE] / [B-ROLL] / [STILL] | Narration (verbatim) | Words |
|---|---|---|---|
| 0:00–0:25 | [STILL] Title card: "Substrate Friction — is your agent's code graph real?" Hold, no motion. Optional [B-ROLL] under the last sentence: `docs/plots/day3-namematch.png` (one `lower` call fanning out to every `lower` in the repo). | "Every AI coding agent that reads your repo builds a graph of it first. Aider, RepoGraph, LocAgent — they all build that graph the same way: by matching names. A call to `lower` becomes an edge to every `lower` in the repo. We asked what nobody publishes: how much of that graph is real?" | 53 |
| 0:25–0:45 | [LIVE] Terminal, clean prompt. Type and run `friction compare --issue django__django-10973`. Start talking as it renders (it is cache-backed and resolves instantly). | "So we built both. Two call graphs of the same django commit — one name-matched, one type-resolved through pyright. Both live in HydraDB at once, in disjoint id bands, so we can diff them in one command. `friction compare`." | 38 |
| 0:45–1:20 | [LIVE] The `compare` output is up: two per-arm panels (edge counts, confirmed/only-A/only-B, the precision ceiling). Let it sit two seconds. [STILL] cut to `docs/plots/arms.png` on "survive"; [STILL] cut to `docs/plots/offenders.png` on "list.extend". On-screen caption on the ceiling: "0.746 is a ceiling — cursor(54) is a case arm A got right and pyright missed; true precision is somewhat higher." | "Same neighbourhood, two panels. Green edges, both graphs agree. Red edges — the name-matched graph has them; type resolution cannot confirm them. Of five thousand eight hundred seventy-three edges we could check on this commit, forty-three eighty-one survive and fourteen ninety-two are red. The precision ceiling of name matching is zero point seven four six. Why: `list.extend` bound to a GIS class a hundred thirty-nine times; `str.lower` bound to a template filter a hundred twenty-five times. Container-method name collisions." | 78 |
| 1:20–1:50 | [STILL] `docs/plots/density.png` — per-instance edge counts, arm B towering over arm A, the timeout/OOM markers. | "Now the twist. The type-resolved graph — the real one — is about four times denser: a median of seventy-nine thousand four hundred forty-seven edges against nineteen thousand eight hundred fifteen. And it's the graph the engine cannot traverse. Twenty-eight comparable instances, bounded paths at length six: the name-matched graph answers; the type-resolved graph answered three. Twenty-four hit the thirty-second timeout; one ran the memory pool dry. The graph worth having is the hardest to query." | 74 |
| 1:50–2:30 | [LIVE] Split view: the `algo.MSpaths` query text from the `compare` output on the left, the per-arm measured latency on the right. [B-ROLL] optional: a live re-run of the same query against `bolt://127.0.0.1:7687` showing the millisecond timer (pre-warm first — see notes). | "Why HydraDB. Friction is a many-to-many path problem: every fix site against every test target. `algo.MSpaths` with pairwise true computes every pair in one server-side round trip, per arm. And both arms sit in one engine at once, in disjoint id bands — arm A at ten billion, arm B at twenty billion. That simultaneity is the trick: the whole comparison is a single-engine operation. Real Cypher, real milliseconds, on screen. And when the engine can't answer, it says so — we report that too." | 83 |
| 2:30–3:00 | [STILL] The README retraction paragraph highlighted, then the repo-URL card. Hold the URL for the final three seconds. | "The honest limits. Version one claimed a prediction result on a graph where nearly three-quarters of its call edges were name collisions — `super` alone matched wrong over thirteen hundred times. It tested nothing; we withdrew it. Per-instance failure prediction is already solved — published work hits AUC point eight four one. Our path-multiplicity signal scores point six three one on eighteen instances, and doesn't beat patch size. A scoped no-go, and we say so. The substrate finding is the result. Repo's linked. Thanks." | 82 |

Section totals: 53 · 38 · 78 · 74 · 83 · 82 = **408 words** ≈ **2:43** spoken (~17 s slack).

**Number-fidelity crib** (say these exactly; sources in parentheses):
- Precision ceiling **0.746**; compared in-scope **5,873**; confirmed-both **4,381**;
  only-A (red) **1,492**; only-B **8,064**; recall of arm B **0.352**; Jaccard **0.3143**
  (`docs/graph-delta.md`). The ceiling is honest in *both* directions — `cursor(54)` is a
  case arm A was right and pyright under-reported, so true precision is somewhat above 0.746.
- Offenders: `extend` **139**, `lower` **125**, `cursor` **54** (`docs/graph-delta.md`).
- Density: median **79,447** (arm B) vs **19,815** (arm A) edges; **3** of **28** answered
  at maxLen 6; **24** timed out at 29,999 ms; **1** OOM (`django__django-11292`).
- Prediction NO-GO: friction arm A (f1 / path-multiplicity only) AUC **0.631**, n=**18**;
  patch_lines **0.637**; arm B **undetermined** (n=3); published prior art AUC **0.841**
  (Agent Psychometrics, arXiv 2604.00594) — *cite as published, never as reproduced by us*
  (`docs/evaluation.md`). Always qualify our metric as **f1 / path-multiplicity**; never say
  "structure does not predict failure."
- Retraction: v1 AUC 0.565 / p 0.726 measured on a graph where **73.9%** of resolved CALLS
  edges were name-collision artifacts — `super()` → `BlockNode.super` **1,321** times.
  Withdrawn (`docs/evaluation-v1-retracted.md`, and the README retraction paragraph).

---

## Recording notes (make the session mechanical)

- **The headline commands are cache-backed — record them cold, they are instant.**
  `friction compare`, `friction list`, `friction delta`, and `friction eval` read the
  committed caches (`data/instances/arms/manifest.jsonl` and `arms/path_stats.json`), which
  **are** the pinned live-engine measurement — arm B is the arm the engine mostly cannot
  answer, so it must be served from cache to show both arms at all. No engine round trip, no
  cold-query risk, deterministic output every take. This is a feature: the money shot cannot
  stall.
- **Pre-warm ONLY the live-engine B-roll.** The single segment that hits `bolt://127.0.0.1:7687`
  live is the optional 1:50–2:30 re-run of `algo.MSpaths`. A cold path can sit at the ~30 s
  server ceiling. Run that exact query **once immediately before the take** so the store is
  warm; the recorded run then returns in real milliseconds. If you skip the live re-run, use
  the latency already printed by `compare` (it is the pinned measurement) and no pre-warm is
  needed at all.
- **Instance choice is deliberate.** `django__django-10973` is the CLI's own documented
  example where **both arms answered**, so the two panels are both populated — required for
  the money shot. If you also want to show the density penalty live, `django__django-10554`
  is the documented case where **arm B timed out** and `compare` prints a clean "engine could
  not answer" line (never a fabricated path). Do not swap ids without re-checking the panels.
- **[LIVE] segments** are only two: 0:25–0:45 (`friction compare`) and 1:50–2:30 (the
  `algo.MSpaths` text + latency). Everything else is a [STILL] or [B-ROLL], so only two clean
  terminal takes are required.
- **Terminal legibility**: font ≥ 18 pt, high-contrast theme, window ≥ 1280 wide. The per-arm
  edge counts, the confirmed / only-A / only-B split, and the **0.746** ceiling line must be
  readable at 1080p.
- **No login anywhere on screen.** The video must open and play without a gate; verify the
  hosting link in a fresh incognito window (checklist below).
- **Hard stop at 3:00.** If a take runs long, trim from the 1:20–1:50 density block first
  (it is a still), never from the money shot.

## Asset capture commands (run from repo root before the session)

```bash
# arms.png (money-shot cut), offenders.png (collision table), density.png (the paradox)
uv run python -m friction.viz            # writes docs/plots/{arms,offenders,density}.png

# The primary command, captured live for the 0:25 and 0:45 segments:
friction compare --issue django__django-10973   # both arms answered — two full panels
friction compare --issue django__django-10554   # (optional) arm B timed out — clean no-answer line

# The precision ceiling / offender table as text, if you prefer a text still over the plot:
friction delta            # precision ceiling 0.746 + worst-offender table
friction list             # per-arm node/edge counts + per-arm answerability

# The scoped NO-GO + retraction, as a text still for 2:30:
friction eval             # NO-GO verdict, f1/path-multiplicity AUC 0.631, retraction

# day3-namematch.png is already committed under docs/plots/ (problem-section B-roll).
```

Capture as [STILL]s before the session: the title card, `docs/plots/arms.png`,
`docs/plots/offenders.png`, `docs/plots/density.png`, the README retraction paragraph, and
the repo-URL card. Optional [B-ROLL]: `docs/plots/day3-namematch.png`.

---

## Pre-submission checklist (runnable)

Run each block from the repo root. A line is checkable only when its command prints what the
comment says to expect. Deadline: **2026-08-20 11:59 PM PT**. Submit early.

### 1. Public repo, OSI license, clean commit history

```bash
# OSI license present in root (expect: "MIT License")
head -1 LICENSE

# No participant-authored commit before 2026-08-12 (expect: all dates 2026-08-12 or later)
git log --format='%aI %s' | tail -5

# Repo is public / no access request — CANNOT be asserted from the shell.
# Open the repo URL in a logged-out incognito window and confirm it loads.
```

Verified at time of writing: `LICENSE` is **MIT** (OSI-approved); the earliest commit is
**2026-08-13**, so nothing predates the 2026-08-12 window.

### 2. Clean-clone setup on a machine that is not yours

```bash
# In a throwaway dir on a second machine (or a fresh container):
git clone <REPO_URL> sf && cd sf
./setup.sh                                 # expect: exits 0, engine up, no manual steps
friction compare --issue django__django-10973   # expect: two populated arm panels
```

`setup.sh` exists and is executable (`-rwxr-xr-x`). It **must** be run once on a machine that
is not the author's before submission — the single checklist item that cannot be self-verified
here.

### 3. The two results are reported honestly, headline first

```bash
friction delta      # expect: precision ceiling 0.746, offender table led by extend/lower/cursor
friction eval       # expect: scoped NO-GO, f1/path-multiplicity AUC 0.631, retraction printed
friction list       # expect: per-arm answerability — arm B answers few instances at maxLen 6
```

- [x] **Headline is the substrate finding**: precision ceiling **0.746**; only-A red edges
      **1,492**; the density paradox (**3**/**28** arm-B answers at maxLen 6, **24** timeouts,
      **1** OOM).
- [x] **Prediction reported as a scoped NO-GO**: friction arm A f1/path-multiplicity AUC
      **0.631** (n=18), does not beat patch_lines **0.637**; arm B **undetermined** (n=3).
      Never phrased as "structure does not predict failure."
- [x] **Prior art cited as published, not reproduced**: Agent Psychometrics AUC **0.841**
      (arXiv 2604.00594) — per-instance prediction is already solved; we do not claim it.
- [x] **Retraction in the README**: v1's AUC 0.565 was measured on a graph where **73.9%** of
      resolved CALLS edges were name-collision artifacts (`super` → `BlockNode.super` **1,321**
      times). Withdrawn.
- [x] Pinned engine commit recorded: `docs/pinned-engine-commit.txt`
      (`02a40025d2d57e97ab2754c8256219cdbfeab379`, v0.1.1).

### 4. HydraDB usage is documented with specific primitives

```bash
ls README* 2>/dev/null || echo "MISSING: no README in repo root"   # expect: README.md
```

- [x] `README.md` in repo root has a "How HydraDB is used" section naming the primitives:
      **`algo.MSpaths` with `pairwise:true`** (all fix-site × test-target paths in one
      server-side round trip, per arm, both arms resident in disjoint id bands — arm A at
      `1e10+idx*1e7`, arm B at `2e10+idx*1e7`), **`algo.SSpaths`** with an integer sourceNode
      for fan-in, and **`UNWIND $rows`** batched Bolt loading — and states what breaks without
      them (21 round trips per ticket; no fan-in; HTTP cannot pass `$params`).

### 5. Video and links

- [ ] Video under **3:00** (this script budgets **~2:43** spoken).
- [ ] Money shot (`friction compare` + the 0.746 ceiling) lands before **1:20** (this script:
      0:45–1:20).
- [ ] Substrate is the headline and the prediction NO-GO is scoped as f1/path-multiplicity —
      confirm on final playback.
- [ ] Video opens and plays without login — checked in a fresh incognito window.
- [ ] Every link in the submission opened in incognito and confirmed reachable logged-out.

### 6. Submit early

- Form: **`forms.gle/GrMYKxLj9zPQcqqc8`**.
- Verify every submitted link in an incognito window **before** hitting submit.
- Submit well before **2026-08-20 11:59 PM PT** and screenshot the confirmation.

---

## Open items before this checklist is fully green

1. **`setup.sh` not yet run on a second machine** (item 2) — must be clean-clone tested.
2. **Repo not confirmed public** from a logged-out session (item 1) — verify in incognito.
3. **Video not yet recorded** (item 5) — record it, confirm under 3:00 and that it plays
   without login in a fresh incognito window.
4. **Submission form not yet completed** (item 6) — submit before the deadline and screenshot
   the confirmation.

Everything else in the checklist is verified against the current repo state; the remaining
open items are the video, the submission, and the two things that can only be checked from
outside this repo (a clean clone on another machine and a logged-out public-visibility check).

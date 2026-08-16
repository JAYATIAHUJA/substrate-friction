# Demo video script — Substrate Friction (v4)

Hack Hydra 2026. **Hard stop 3:00.** Order is fixed: **problem → project → demo → HydraDB → honest limits**. Judges decide in the first 30 seconds, so the hook lands in the first sentence and the money shot (`friction compare` + `docs/demo.html`, the `0.746` ceiling) lands before 1:25.

**The frame is non-negotiable.** The headline is the _substrate_ finding: what a name-matched code graph costs. Per-instance failure prediction is **not** claimed — it is already solved at AUC `0.841` in published work, and our own predictor is a scoped **NO-GO** — now a *significant* one (n=172, 7 repos, DeLong p=0.046) — we report honestly. Lead with the substrate. Never dress up either result.

Narration is **verbatim** — read it as written. Every number matches `docs/precision.md`, `docs/connectivity.md`, `docs/covers.md`, `docs/evaluation.md`, `src/friction/reach.py`, and `docs/demo.html`. Do not round, soften, or improvise a figure.

**Spoken budget: 405 words at ~150 wpm ≈ 2:42**, leaving ~18 s for the two live resolves and pauses. Per-section counts are in the last column and total below.

---

## Shot list

| Time | Screen — [STILL] / [B-ROLL] / [LIVE TERMINAL] | Narration (verbatim) | Words |
|---|---|---|---|
| 0:00–0:25 | [STILL] Title card: "Substrate Friction — is your agent's code graph real?" Hold. [B-ROLL] under the last sentence: `docs/plots/offenders.png` sliding up. | "Every AI coding agent that reads your repo builds a graph of it first. Aider's repo map, RepoGraph, LocAgent — they all build that graph the same way: by matching names. A call to `lower` becomes an edge to every function named `lower` in the repo. Nobody publishes how much of that graph is real. So we measured it." | 59 |
| 0:25–0:45 | [LIVE TERMINAL] Clean prompt. Type and run `friction compare --issue django__django-10973`. Start talking as it renders — it is cache-backed and resolves instantly. | "We built both. Two call graphs of the same django commit — one name-matched, one type-resolved through pyright. Both live inside HydraDB at once, in disjoint id bands, so we diff them in a single command. `friction compare`." | 38 |
| 0:45–1:25 | [LIVE TERMINAL] `compare` output up (edge counts, confirmed / only-A / only-B, the ceiling). Let it sit 2 s. Then [B-ROLL] `docs/demo.html`: hit **"Prune wrong edges"** — 9 of 21 edges vanish, live counter ticks down. On-screen caption: "0.746 is a CEILING — cursor(54) is a case arm A got right; true precision is >= 0.746." | "Same neighbourhood, two graphs. Of five thousand eight hundred seventy-three edges we could check on this commit, four thousand three hundred eighty-one survive type resolution — and fourteen ninety-two do not. The precision ceiling of name matching is zero point seven four six. Watch it: here's the fix site's neighbourhood, twenty-one edges. Prune the ones type resolution can't confirm — nine vanish. Four of those nine are one collision: `list.extend`, bound to a GIS class — graph-wide, a hundred thirty-nine times. In version one, builtin `super` bound to a template method thirteen hundred and twenty-one times." | 95 |
| 1:25–1:50 | [STILL] `docs/plots/direction.png` — the 0 / 55 / 98 bars. Caption: "test → fix, not fix → test — and COVERS, traced live, moves 11/18 → 12/18." | "Does the graph connect a fix to the test that exercises it? Fix to test, directed: zero of forty-four — code doesn't call tests. Test to fix: twenty-four. Undirected: forty-three — fixture machinery a static graph can't see. We also traced it live, the executed edge: test-to-fix goes eleven of eighteen to twelve — modest, and it doesn't rescue the predictor." | 58 |
| 1:50–2:30 | [LIVE TERMINAL] Left: the `count(*)` reachability Cypher from `friction check`. Right: the measured latency it prints. [STILL] cut to `docs/plots/latency.png` on "thirty seconds". | "Why HydraDB. The old metric counted bounded paths between two node sets — that's sharp-P-complete, and enumeration hit the engine's thirty-thousand-millisecond timeout. So we ask reachable-set size instead, in-engine, as a masked count-star. `MATCH`, `CALLS`, star one to k, `count` star. Exact against networkx at every k, and it always returns — on one django graph, milliseconds to seconds, where that same graph's enumeration hits thirty seconds. A vector index can't do this — reachable sets and cuts don't exist in an embedding space." | 83 |
| 2:30–3:00 | [STILL] The README retraction paragraph, then the repo-URL card. Hold the URL for the final 3 s. | "The honest limits. We also tried predicting which tickets an agent fails. Across seven repos, a hundred seventy-two instances, leave-one-repo-out, it doesn't beat patch size — and DeLong p of point oh four six says so significantly, not a shrug. Version one's result ran on a graph three-quarters name collisions; withdrawn. Per-instance prediction is already solved at point eight four one — we don't claim it. The substrate finding is ours. Repo's linked. Thanks." | 72 |

**Section totals:** 59 · 38 · 95 · 58 · 83 · 72 = **405 words** ≈ **2:42** spoken (~18 s slack). Fits the 3:00 hard stop.

**Number-fidelity crib** (say these exactly; sources in parentheses):
- Substrate: compared **5,873**; confirmed-both **4,381**; only-A (red) **1,492**; true edges missed **8,064**; precision ceiling **0.746**; recall **0.352**; Jaccard **0.3143** (`docs/precision.md`, `docs/graph-delta.md`). The ceiling is honest in _both_ directions — `cursor(54)` is a case arm A was right and pyright under-reported, so true precision is **>= 0.746, never <=**.
- Offenders: `extend` **139**, `lower` **125**, `cursor` **54** (`docs/precision.md`). v1 `super()` → `BlockNode.super` **1,321** — a **v1 build-log figure**, recorded in the retraction string in `src/friction/harness.py` (the v1 name-matched caches are gitignored, so it is not recomputable from committed data; `docs/call-resolution-audit.md` documents the collision *mechanism*, not this count).
- Prune demo: **21** edges, **12** confirmed, **9** unconfirmed; 4 of the 9 are the `list.extend` collision; instance `django__django-11490`, fix site `get_combinator_sql()` (`docs/demo.html`).
- Direction: fix→test **0/44 (0%)**, test→fix **24/44 (55%)**, undirected **43/44 (98%)** at 6 hops (`docs/connectivity.md`).
- COVERS (dynamic tracer, folded into the 1:25–1:50 beat): **18** instances traced live, all succeeded; strict edge mapping **0.3% (69/23,043) → 27.6% (3,492/12,635)** after qualifying names (~**90×**); directed test→fix **11/18 (61%) → 12/18 (67%)**, **+1** (`django__django-11265` flips), **AMBER**; residual is the runtime-class-vs-definition-site mismatch. Real but modest — **does NOT rescue the predictor** (`docs/covers.md`). Representative trace `django__django-11163` = **5,921** call edges / **3,215** functions / **6.9 s** (from the measured facts; the folded-edge count in `docs/covers.md` is a different metric).
- Engine: `count(*)` over `[:CALLS*1..k]` is exact vs networkx at k=1..6. **Two graphs, kept distinct** (`docs/latency.md`): on a **1,000-node out-degree-3** graph reachability is **3–12 ms** and enumeration finishes in ~200 ms (no timeout there); the **30,000 ms** enumeration timeout is the **~34,000-node django** graph. Measured on **one** 34k django-density graph, reachability answers **6–10 ms** (typical source) to **6.5 s** (busiest hub) and always returns, while enumeration costs **~15 s** from mid-graph seeds and **~24 s** from a hub (grazing the 30 s ceiling; it times out on it in other cold runs) — honest ratio **~1,500–2,300×** at the typical operating point, unbounded (times out) at the hub. Path counting is **#P-complete** (Valiant 1979); `RETURN count(n)` is rejected, `count(*)` is the working form (`docs/latency.md`, `src/friction/reach.py`, `docs/engine-scaling.md`, `docs/demo.html`).
- Predictor NO-GO — now **SIGNIFICANT**: **n=172** across **7 repos**, class balance **86 failed / 86 resolved**, scored **leave-one-repo-out**. Pooled held-out AUC features **0.483** (≤ chance) vs `patch_lines` **0.628**; in-sample best feature `fanin` **0.567** vs best baseline `patch_lines` **0.656**; **DeLong z = −1.996, p = 0.046**; bootstrap ΔAUC (fanin − patch_lines) **−0.089, 95% CI [−0.178, −0.003]** (excludes zero, below it). Repo-identity confound: **0.596 / 0.613** under the two weaker cached systems, **0.382** under the strong primary — what leave-one-repo-out neutralises. Power: the 0.089 gap needs ~310 instances, a general +0.05 needs ~584, we have 172 — the gap is resolved, no small effect claimed (`docs/evaluation.md`). Published prior art AUC **0.841** (Agent Psychometrics, arXiv 2604.00594) — _cite as published, never reproduced by us._ Never say "structure does not predict failure."

---

## Recording notes (make the session mechanical)

- **The headline commands are cache-backed — record them cold, they are instant.** `friction compare`, `friction list`, `friction precision`, `friction connectivity`, `friction eval` read the committed `docs/` reports and `data/…/arms/` caches. No engine round trip, no cold-query risk, deterministic every take. The money shot cannot stall.
- **`docs/demo.html` is self-contained and works OFFLINE** (Cytoscape.js vendored, no CDN). Open it in a browser, click **"Prune wrong edges"**, and the live counter animates 21 → 12. No server needed. This is the money shot — rehearse the click so the 9 red edges vanish on the word "nine".
- **Only two [LIVE TERMINAL] takes are required:** 0:25–0:45 (`friction compare`) and 1:50–2:30 (`friction check` — its Cypher and printed latency). Everything else is a [STILL] or [B-ROLL], so the session is mechanical.
- **Pre-warm ONLY the `friction check` take.** It hits the running engine; a cold store can be slow. Run `friction check --issue django__django-10554` once immediately before the take so the store is warm; the recorded run then returns in the tens of milliseconds it prints. If you skip the live check, the `count(*)` Cypher and the committed reachability band on `docs/plots/latency.png` (6–10 ms typical, up to 6.5 s from a hub; `docs/latency.md`) carry the point with no engine at all.
- **Instance choice is deliberate.** `django__django-10973` is the documented example where **both arms answered**, so `compare` shows two populated panels. The prune demo is `django__django-11490` (fix site `get_combinator_sql()`). Do not swap ids without re-checking the panels.
- **Terminal legibility:** font ≥ 18 pt, high-contrast theme, window ≥ 1280 wide. The edge counts, the confirmed / only-A / only-B split, and the **0.746** ceiling line must be readable at 1080p.
- **No login anywhere on screen.** The video must open and play without a gate; verify the hosting link in a fresh incognito window.
- **Hard stop at 3:00.** If a take runs long, trim from the 1:25–1:50 direction still first (it is a still), never from the money shot.

## Asset capture commands (run from repo root before the session)

```bash
# Regenerate all figures + docs/demo.html (prune, offenders, direction, latency, arms, density):
uv run python -m friction.viz

# The two live takes:
friction compare --issue django__django-10973   # both arms answered — two full panels
friction check   --issue django__django-10554   # THE GATE: real count(*) Cypher + measured latency

# Text stills, if you prefer text over a plot:
friction precision       # ceiling 0.746 + offender table
friction connectivity    # the 0 / 55 / 98 direction table
friction eval            # scoped NO-GO + both retractions
```

Capture as [STILL]s before the session: the title card, `docs/plots/direction.png`, `docs/plots/latency.png`, the README retraction paragraph, the repo-URL card. [B-ROLL]: `docs/plots/offenders.png`, and `docs/demo.html` with the prune button.

---

## Pre-submission checklist (runnable)

Run each block from the repo root. A line is checkable only when its command prints what the comment says to expect. Deadline: **2026-08-20 11:59 PM PT**. Submit early.

### 1. Public repo, OSI license, clean commit history

```bash
# OSI license present in root (expect: "MIT License")
head -1 LICENSE

# No participant-authored commit before 2026-08-12 (expect: all dates 2026-08-12 or later)
git log --format='%aI %s' | tail -5

# Repo is public / no access request — CANNOT be asserted from the shell.
# Open the repo URL in a logged-out incognito window and confirm it loads.
```

### 2. Clean-clone setup on a machine that is not yours

```bash
# In a throwaway dir on a second machine (or a fresh container):
git clone <REPO_URL> sf && cd sf
./setup.sh                                        # expect: exits 0, engine up, no manual steps
friction check   --issue django__django-10554     # expect: real count(*) Cypher + measured latency
friction compare --issue django__django-10973      # expect: two populated arm panels
```

`setup.sh` was verified from a real clean clone: all acceptance commands pass, cold ~77 s to a working gate. It **must** be re-run once on a machine that is not the author's before submission — the single checklist item that cannot be self-verified here.

### 3. The three findings are reported honestly, headline first

```bash
friction precision       # expect: precision ceiling 0.746, offender table led by extend/lower/cursor
friction connectivity    # expect: fix→test 0/44, test→fix 24/44 (55%), undirected 43/44 (98%)
friction eval            # expect: SIGNIFICANT scoped NO-GO (n=172, 7 repos, leave-one-repo-out); pooled held-out features 0.483 vs patch_lines 0.628; DeLong p=0.046; both retractions
```

- [x] **Headline is the substrate finding**: precision ceiling **0.746** (a ceiling: true precision >= 0.746); only-A red edges **1,492**; true edges missed **8,064**.
- [x] **Direction reported both ways**: fix→test **0/44**, test→fix **24/44 (55%)**, undirected **43/44 (98%)** — never present undirected as "the test exercises this code."
- [x] **Engine**: `count(*)` reachability exact vs networkx at k=1..6; on one 34k-node django-density graph (`docs/latency.md`) it answers in **6–10 ms** (typical source) to **6.5 s** (busiest hub) and always returns, while path enumeration on that same graph costs **~15 s** (mid seeds) to **~24 s** (hub), grazing the 30 s ceiling and timing out on it in other cold runs — honest ratio **~1,500–2,300×** at the typical operating point (the retracted "~2,500×" compared two different graphs); standing `@pytest.mark.engine` regression test.
- [x] **Predictor reported as a SIGNIFICANT scoped NO-GO**: n=**172** across 7 repos, leave-one-repo-out; pooled held-out features **0.483** (≤ chance) vs `patch_lines` **0.628**; in-sample `fanin` **0.567** loses to `patch_lines` **0.656** at **DeLong p=0.046**; bootstrap ΔAUC **−0.089 [−0.178, −0.003]** excludes zero. Never phrased as "structure does not predict failure."
- [x] **Prior art cited as published, not reproduced**: Agent Psychometrics AUC **0.841** (arXiv 2604.00594).
- [x] **Both retractions in the README**: v1 AUC **0.565** (73.9% name-collision edges; `super` → `BlockNode.super` **1,321**×) WITHDRAWN; v2 **0.631** (f1/path-multiplicity only, lost to `patch_lines` **0.637**) WITHDRAWN as a test of the thesis.
- [x] Pinned engine commit recorded: `docs/pinned-engine-commit.txt` (`02a40025d2d57e97ab2754c8256219cdbfeab379`, v0.1.1).

### 4. HydraDB usage is documented with specific primitives

```bash
ls README* 2>/dev/null || echo "MISSING: no README in repo root"   # expect: README.md
```

- [x] `README.md` "How HydraDB is used" section: **`count(*)` bounded reachability** over `[:CALLS*1..k]` (masked GraphBLAS BFS, cost O(m) per hop, bounded by the visited set — flat in k for a typical source, a few seconds from the busiest hub), **both arms resident in disjoint id bands** (single-engine diff), the **`count(n)`-rejected / `count(*)`-works** syntax finding, and why a vector index structurally cannot compute a relation defined over reachable sets and cuts.

### 5. Video and links

- [ ] Video under **3:00** (this script budgets **~2:42** spoken).
- [ ] Money shot (`friction compare` + the prune demo + the **0.746** ceiling) lands before **1:25** (this script: 0:45–1:25).
- [ ] Substrate is the headline; direction is reported both ways; predictor NO-GO is scoped — confirm on final playback.
- [ ] Video opens and plays without login — checked in a fresh incognito window.
- [ ] Every link in the submission opened in incognito and confirmed reachable logged-out.

### 6. Submit early

- Form: **`forms.gle/GrMYKxLj9zPQcqqc8`**.
- Verify every submitted link in an incognito window **before** hitting submit.
- Submit well before **2026-08-20 11:59 PM PT** and screenshot the confirmation.

---

## Open items before this checklist is fully green

1. **`setup.sh` not yet re-run on a second machine** (item 2) — must be clean-clone tested.
2. **Repo not confirmed public** from a logged-out session (item 1) — verify in incognito.
3. **Video not yet recorded** (item 5) — record it, confirm under 3:00 and that it plays without login.
4. **Submission form not yet completed** (item 6) — submit before the deadline and screenshot the confirmation.

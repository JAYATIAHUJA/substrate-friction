# Submission package — Hack Hydra 2026, Track 02

Form: `forms.gle/GrMYKxLj9zPQcqqc8` · Deadline 2026-08-20 23:59 PT · **submit on the 19th.**

## (a) Form answers

**Project name**
Substrate Friction

**One-paragraph description**
Every AI coding agent builds a graph of your repository before it acts — and
tools skip tests based on that graph. Substrate Friction is the safety gate
nobody in the category runs: `friction gate` measures, against SWE-bench's
human-curated FAIL_TO_PASS labels, what fraction of tests known to guard a fix
a graph actually reaches. On 172 labelled instances across 7 repositories the
answer is 0.419 for full pyright type resolution and 0.314 for the
name-matched graphs Aider/RepoGraph/LocAgent build — nowhere near a 0.95
skip-safety bar — and the underlying precision ceiling is flat across eight
years of django, so this is a constant of the technique, not decay you
outgrow. The verdict ships as a CLI exit code, an MCP tool for agents, a SARIF
code-scanning finding, and a certified per-edge trust graph; the headline
anti-join is reproduced *inside* HydraDB via edge reification at 2.0 ms/edge
with exact offline parity enforced by exception. Five pre-registered studies
(three hypotheses falsified and shipped as-written), a negative control, three
published retractions, and `friction verify` re-deriving every figure from
committed artifacts — the repo gates its own PRs with its own gate.

**Problem statement**
Graph-based test selection is unsafe in a way that is invisible from inside
the tool: a backwards walk can be provably complete with respect to the graph
while the graph is missing the edge that mattered, because an extractor cannot
fail-closed on an edge it never knew existed. On one real django instance a
graph-complete walk selected 0 of 370 guarding tests. Nobody measuring-side
in the agent-tooling category publishes graph recall; this project measures
it, and refuses the skip when the evidence is thin.

**Tech stack**
HydraDB (open-source engine, digest-pinned `db78309a…`, commit `02a40025`,
Bolt) · Python 3.11+/uv · tree-sitter (arm A) · scip-python/pyright (arm B) ·
sys.settrace dynamic tracing · NetworkX/SciPy · FastAPI · MCP (stdio server +
demonstrated client loop) · SARIF/GitHub Actions · static site rendered from
the results artifact.

**How HydraDB is used (short form)**
Both extraction arms of the same commit resident in one engine in disjoint id
bands; bounded reachability via `count(*)` masked-BFS (ms where enumeration
hits the 30 s wall); the arm-A-vs-arm-B anti-join computed in-engine by edge
reification (`friction diff --live`, 4,381/1,492 with exact parity enforced);
four upstream filings (#81 bug, #82 docs PR, #101 cold-start bug with repro
matrix, #102 `RecallCert` procedure proposal).

**Team / contribution note**
Solo participant (areycruzer). Built during the hackathon window (first
commit 2026-08-13); Claude (Anthropic) assisted in building and measuring, as
attributed in the README. All measurements executed on the participant's
machine against the pinned open-source engine; no hosted service used.

## (b) Links block

- Repo: https://github.com/areycruzer/substrate-friction
- Site: https://areycruzer.github.io/substrate-friction
- Video: **[PLACEHOLDER — paste the ≤3:00 upload URL]**
- Upstream: [#81](https://github.com/hydra-db/hydradb/issues/81) ·
  [#82](https://github.com/hydra-db/hydradb/pull/82) ·
  [#101](https://github.com/hydra-db/hydradb/issues/101) ·
  [#102](https://github.com/hydra-db/hydradb/issues/102)
- Key docs: [gate.md](gate.md) · [longitudinal.md](longitudinal.md) ·
  [engine-diff.md](engine-diff.md) · [studies.md](studies.md) ·
  [ORIGIN.md](ORIGIN.md)

## (c) Pre-submit checklist

Run on a machine that has never seen the repo (expected exit codes noted —
the gate's nonzero exits are the product working, not failures):

- [ ] `git clone … && cd substrate-friction && ./setup.sh` — completes with no
      manual step (engine may fail to boot on non-macOS filesystems per
      upstream #101; setup says so and cache-backed commands still work)
- [ ] `friction gate --arm arm_b` → prints RUN_FULL, **exit 1 (by design)**
- [ ] `friction gate --instance django__django-11551 --live` → `parity=True`,
      **exit 1 (by design)** — needs the running engine (macOS)
- [ ] `friction diff --live` → in-engine 4,381/1,492 with the local index, or
      the pinned-result fallback on a clean clone — **exit 0**
- [ ] `friction verify` → VERIFY OK — **exit 0**
- [ ] Every link in README and on the site opened in an incognito window
      (repo is public, Pages live, all four upstream links resolve)
- [ ] Video: **≤ 3:00 hard**, order = problem → what was built → working
      demo → how HydraDB is used; numbers spoken match `docs/gate.md` and
      `docs/longitudinal.md`
- [ ] Both CI workflows green on HEAD (HydraDB verify, Self-gate)
- [ ] Form fields pasted from section (a); video URL replaces the placeholder
      here before submitting

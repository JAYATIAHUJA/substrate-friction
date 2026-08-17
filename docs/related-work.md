# Related work

This project did not discover that static call graphs miss edges. That has been
known for 25 years. What follows is where the gate actually sits, what it
borrows, and the three things about it that are new.

## What is already known, and not claimed here

**Safe regression test selection.** Rothermel & Harrold (IEEE TSE 1998) define a
*safe* RTS technique as one that excludes no test which, if executed, would
reveal a fault. That is the gate's definition of safety, and it is theirs. The
systematic review by Engström et al. notes that safety "is hard to achieve in
practice" because it assumes determinism in program and test execution.

**Static RTS is sometimes unsafe.** Legunsen et al. (FSE 2016) studied
class-level static RTS across 22 open-source projects and found it comparable to
the dynamic tool Ekstazi "at the risk of being unsafe sometimes." They measure
safety violation as `|E\T| / |E∪T|` against Ekstazi. Shi et al. (OOPSLA 2019)
traced a major share of that unsafety to **reflection**, and extended STARTS to
handle it. Python's analogue is framework dispatch: pytest fixtures, `setUp`,
parametrize — the machinery behind this project's measured 55% → 98% gap between
directed and undirected connectivity (`docs/connectivity.md`).

**Static call graphs have limited recall.** Sui, Dietrich, Tahir & Fourtounis
(ICSE 2020) report a median recall of 0.884 for Java — and, critically, that
**adding precision to the static analysis has little impact on recall: they are
separate concerns**. Salis et al. (PyCG, ICSE 2021) report that a Python
call-graph analysis passing 92% of micro-benchmarks achieves only **70% recall
on real applications**. Helm et al. (*Total Recall?*, ISSTA 2024) construct
dynamic baselines from test execution as a ground-truth approximation.

**Per-instance agent failure prediction is solved.** Agent Psychometrics
(arXiv 2604.00594) reports AUC 0.841, with a text-only variant at 0.787 and a
task-agnostic prior at 0.718. This project attempted that problem, failed, and
does not claim it — see "The prediction attempt" below.

## What this project borrows

- The **safety framing** from Rothermel & Harrold: a selector is unsafe if it
  drops a test that would have revealed the fault.
- The **dynamic-baseline methodology** from Helm et al.: `friction.trace` runs
  each instance's own tests under `sys.settrace` in a version-matched guest
  interpreter and records executed `Test -> Function` edges, exactly as an
  approximation of unobtainable ground truth.
- The **precision/recall separation** from Sui et al., reproduced in
  `docs/gate.md` as a paired comparison with an exact McNemar test: the full
  name-match → pyright type-resolution upgrade moves paired recall by +0.071
  (n=28, p=0.73).
- From the better-run end of the code-intelligence field: **pinning a holdout
  split before measuring** (`data/shipped/split.json`), **publishing the rows
  that lose**, a stated **how to read a number here**, and **task-shaped
  agent tools** that batch targets per call.

## The incumbent, and the field-wide blind spot

**repowise** (AGPL-3.0, ~6k stars) is the state of the art in codebase
intelligence for AI agents. It ships `repowise impacted-tests` — "only the tests
a diff actually exercises" — on a dependency graph with three-tier call
resolution across 19 languages, plus ten MCP tools. Its benchmarking is
exemplary: a sealed 42-instance split held out from every improvement round,
DeLong tests, defect prediction validated at ROC AUC 0.737 over 21 repositories,
and a stated policy of publishing the rows it loses.

Its benchmarks measure six things: finding the right files, the agent loop,
commit-context tokens, command-output compression, defect prediction, and
indexing time. **Edge accuracy is not among them, and neither is test-selection
safety.** Reading its source, the three resolution tiers carry asserted
confidences — 0.95 (same-file), 0.90 (import-scoped), 0.50 (global unique) —
hand-assigned, with no published accuracy for any tier.

That is not a criticism of a project whose measurement standards are higher than
most of this field's. It is the point: when the most rigorous tool in the
category measures everything downstream of its graph and nothing about the graph
itself, the omission is structural rather than an oversight by any one team.

Two honest qualifications. First, repowise's change-risk tool reports "the tests
**coverage proves** it touches" — coverage-backed selection, which is genuinely
stronger than static-graph selection because dynamic data does not carry the
static graph's blind spots. This project's claim is about **graph-based**
selection and is not stretched onto coverage-based selection. Second, the
coverage ceiling was measured here anyway: folding dynamic execution traces into
the type-resolved graph moved test→fix connectivity from 55% to **67%**
(`docs/covers.md`) — better, and still far from a 0.95 bar.

## What is new

**1. The domain.** The RTS literature measures Java build tools — STARTS,
Ekstazi, class firewalls over type-dependency graphs. Nobody has measured safety
for the graph class that LLM coding agents actually build: the name-matched
Python call graphs behind Aider, RepoGraph and LocAgent. That graph class is now
making test-selection and impact-analysis decisions in production, and its
recall was unmeasured.

**2. The oracle.** The field measures safety violation of one tool relative to
another tool — Ekstazi as the stand-in for truth. This uses **SWE-bench
`FAIL_TO_PASS`**: a human-curated label stating which test guards which fix. It
removes the dependence on a second tool being right, and it is the reason the
number here can be called recall rather than disagreement.

**3. The link to agent abstention.** A 2026 literature has formed around when an
agent should decline to act: AgentAbstain (arXiv 2607.10059) finds the best of
17 frontier models reaches 59.5% paired accuracy and — critically — that
**abstention capability scales independently of task-solving capability**, so
larger models do not fix it. Agentic Abstention (arXiv 2606.28733) frames it as
a sequential decision problem; ReDAct (arXiv 2604.07036) defers under
uncertainty because errors compound irreversibly.

Every one of these defers on **model-internal** uncertainty — the agent's own
sense of doubt. The gate supplies something none of them has: an **external,
measured, substrate-level** reason to abstain. Not "the model is unsure" but
"the graph this conclusion rests on reaches the guarding test 55% of the time,
measured on labelled data." Any agent conclusion resting on a graph traversal —
affected tests, blast radius, related files — inherits that graph's recall.

## The prediction attempt, and why it failed

This project began as a different idea: predict from graph structure whether an
AI agent would fail a task, and route the hard ones to a human. It was built and
measured, and it does not work. Pooled leave-one-repo-out AUC across 7 repos was
**0.483** — at or below chance. The best single structural feature (`fanin`,
0.567) lost to counting the lines in the patch (`patch_lines`, 0.656). Two
earlier figures, 0.565 and 0.631, were retracted for measurement defects; the
full record is in `docs/evaluation.md` and `docs/evaluation-v1-retracted.md`.

The diagnosis is that the target was wrong. A call graph carries no information
about whether a language model will succeed — that depends on the model, the
prompt and the sampling, none of which is in the edges. The gate asks the graph
to report a property of *itself* instead, which is deterministic and measurable.

Two facts make that failure informative rather than merely negative. First, the
problem is already solved at 0.841 by methods that read the issue text and
ignore the graph entirely, so there was no headroom for a structural signal.
Second, the features were computed on a graph now measured to reach the guarding
test only 55% of the time — so the thesis was never tested on a substrate that
could carry it. Those two cannot be separated with the data here, and no claim
of vindication is made. The honest statement is that the prediction thesis is
unsupported on this corpus, and that the substrate is too weak to test it
properly. The second half is what the gate measures.

## How to read a number in this project

- **Every figure is generated**, not typed. Each doc names the script that
  produces it, and the README quotes only figures that appear in a generated
  doc.
- **Retracted numbers stay visible.** Three figures in this project turned out
  to be measurement artifacts. All three are still in the repo with the cause
  written down: `docs/evaluation-v1-retracted.md`, and the retraction notes in
  `docs/evaluation.md` and `docs/covers.md`.
- **Precision is reported as a ceiling**, never a point estimate, because the
  type-resolved reference under-reports rather than inventing edges.
- **The fair test is leave-one-repo-out**, not a random split: the model never
  sees the held-out repository, so it cannot memorise repo identity.
- **The headline verdict is negative** and is the finding, not a shortfall.
- **Where another tool is better on a dimension, this project says so** before
  a reader has to find it.

## References

- Rothermel & Harrold. *Empirical Studies of a Safe Regression Test Selection Technique.* IEEE TSE, 1998.
- Engström, Runeson & Skoglund. *A Systematic Review on Regression Test Selection Techniques.* IST, 2010.
- Legunsen et al. *An Extensive Study of Static Regression Test Selection in Modern Software Evolution.* FSE 2016.
- Legunsen, Shi & Marinov. *STARTS: STAtic Regression Test Selection.* ASE 2017.
- Shi et al. *Reflection-Aware Static Regression Test Selection.* OOPSLA 2019.
- Sui, Dietrich, Tahir & Fourtounis. *On the Recall of Static Call Graph Construction in Practice.* ICSE 2020.
- Salis et al. *PyCG: Practical Call Graph Generation in Python.* ICSE 2021.
- Helm et al. *Total Recall? How Good Are Static Call Graphs Really?* ISSTA 2024.
- *AgentAbstain: Do LLM Agents Know When Not to Act?* arXiv 2607.10059.
- *Agentic Abstention: Do Agents Know When to Stop Instead of Act?* arXiv 2606.28733.
- *ReDAct: Uncertainty-Aware Deferral for LLM Agents.* arXiv 2604.07036.
- *Agent Psychometrics.* arXiv 2604.00594.
- *ARISE.* arXiv 2605.03117.
- repowise. *Codebase intelligence for AI and humans.* github.com/repowise-dev/repowise — benchmarks at `docs/BENCHMARKS.md`.

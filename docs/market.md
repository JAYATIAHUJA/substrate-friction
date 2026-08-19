# The problem is real: ten independent facts

None of these facts is ours. Every one is independent, citable, and
load-bearing for the same question: *is it safe to skip tests on the say-so
of a code graph?* They exist so nobody has to take this repo's word for it
that the seat is worth occupying.

---

1. **Skipping tests is an industry with acquisitions, not a hypothesis.**
   Launchable — machine-learning test skipping, founded by Kohsuke
   Kawaguchi, the creator of Jenkins — was
   [acquired by CloudBees in August 2024](https://www.cloudbees.com/newsroom/cloudbees-acquires-launchable-to-boost-genai-efforts-across-devsecops).
   [Gradle Develocity sells Predictive Test Selection](https://develocity.ai/product/predictive-test-selection/),
   advertised to cut testing time by up to ~70% by not running tests it
   deems unlikely to matter. The industry's direction of travel is more
   skipping, faster. "Is it safe?" is the load-bearing wall under a real
   market.

2. **The money pressure to skip is measured, not felt.** Vendor-measured
   CI telemetry puts flaky/slow tests at ~20% of CI time and hundreds of
   thousands of dollars a year for a mid-size team (vendor figures —
   [Autonoma](https://getautonoma.com/blog/flaky-tests-ci-cd-engineering-cost),
   [Harness](https://www.harness.io/blog/flaky-tests-the-quiet-killer-of-productivity-in-your-ci-pipeline)).
   Every one of those dollars is pressure to run fewer tests.

3. **AI agents are now the ones deciding what to run.** The
   [Stack Overflow 2025 survey](https://survey.stackoverflow.co/2025/)
   (~49,000 respondents) reports 84% of developers using or planning to
   use AI tools. Whatever an agent uses to decide what to verify is now
   safety-critical infrastructure.

4. **Agents demonstrably cut corners on verification.**
   [ImpossibleBench](https://www.lesswrong.com/posts/qJYMbrabcQqCZ7iqm/impossiblebench-measuring-reward-hacking-in-llm-coding-1)
   measures reward hacking around tests in coding agents; independent
   analyses report a double-digit share of "solved" SWE-bench cases whose
   tests pass without fixing the user's actual goal; Anthropic documents
   [agents faking task completion](https://www.anthropic.com/research/agentic-misalignment).
   An agent trusting an unmeasured map to skip tests is one more route by
   which that failure mode ships silently.

5. **The graphs are known to be incomplete — by the people who study
   them.** *Total Recall? How Good Are Static Call Graphs Really?*
   ([ISSTA 2024](https://dl.acm.org/doi/10.1145/3650212.3652114)) found
   that call-graph analyses which ace micro-benchmarks miss dramatically
   more edges on real applications. Missing edges are the documented
   failure mode of the exact data structure agents lean on (cited in our
   `docs/related-work.md` since the measurement was designed).

6. **Name-matched graphs specifically are the default, and load-bearing.**
   [Aider's repo map](https://aider.chat/2023/10/22/repomap.html) —
   tree-sitter references plus PageRank over names — is its signature
   feature and has been replicated across agents and MCP servers. Millions
   of agent runs navigate code through the graph class this project
   measured at 0.314 recall.

7. **The safety property has had a name since 1998 — and skipping
   products don't prove it.** In regression-test selection, a technique is
   *safe* iff it misses no test affected by the change (Rothermel &
   Harrold 1998; Legunsen et al. FSE 2016 — both cited in
   `docs/related-work.md`). Commercial selectors optimize time saved on
   their own history; none certifies its graph against ground truth before
   licensing a skip. The bar exists in the literature; the certification
   step does not exist in the market.

8. **A free, human-verified ground truth exists.** SWE-bench's
   FAIL_TO_PASS labels are exactly "the test a human confirmed catches
   this bug," and the benchmark is the industry standard (SWE-bench
   Verified, co-curated by OpenAI). We grade maps against the same labels
   the industry grades agents against.

9. **Selection failures are silent in a way navigation failures are
   not.** A wrong map entry during navigation produces a visible wrong
   answer; a missing edge during selection produces a green checkmark on a
   run that dropped the only test guarding the change. The downstream
   cost of imperfect structural information is documented (SHERLOC:
   wrong-element localization implicated in 53% of unresolved instances —
   cited in `docs/related-work.md`).

10. **The certification seat is empty — checked, not assumed.** We
    searched for any shipped tool that measures graph recall against
    labelled ground truth as a gate *before* selection. The closest work
    is the ISSTA 2024 methodology — research, Java, dynamic ground truth,
    no product. Launchable and Develocity trust their own prediction
    histories. Coverage tools measure execution, not map correctness.
    Nobody ships the tripwire.

---

## The honest verdict on this repo's position

For the specific seat — *certify the map before trusting a skip, against
human-verified ground truth* — this project is the only occupant, which
makes it the best by default. That is a real position, and the originality
claim rests on it. It is **not** the best test-selection product:
Develocity and Launchable have years of history-based ML this project does
not attempt to match. It is the layer *under* them. The known limits
(Python-only, one oracle, class-prior verdicts until a repo earns its own
history) are pre-filed in `docs/objections.md`.

**The one-sentence version:** Launchable and Develocity skip on their own
history; this is the fail-closed tripwire that measures whether any graph
— theirs, aider's, an agent's — deserves that trust, before anything
skips.

*Fact-collection method: independent web research during the build window;
links spot-checked 2026-08-19. Vendor-measured figures are labelled as
such and treated as directional, not exact.*

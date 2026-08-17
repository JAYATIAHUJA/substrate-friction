# Video script — hard cap 3:00, target 2:40

~400 words. One live terminal, one browser tab. Record the demo live; no stills.

---

## 1. Problem — 0:00–0:35

> Every AI coding agent that touches your repository builds a graph of it
> first. Aider, RepoGraph, LocAgent — they match identifier names into a call
> graph, and then tools make decisions on top of it. The sharpest decision is
> test selection: walk backwards from a change, run the tests you reach, skip
> the rest.
>
> Here's the trap. That walk can be provably complete — it exhausted every edge
> the graph has — while the graph is missing the edge that mattered. An
> extractor cannot fail-closed on an edge it never knew existed. Graph-complete
> is not program-complete.

*Screen: the prune.png figure — 21 name-matched edges, 9 unconfirmed in red.*

## 2. Project — 0:35–1:15

> So we measured the thing everyone assumes: can these graphs actually reach
> the tests that guard a change? The label is free — SWE-bench's FAIL_TO_PASS
> test IS the test that guards the fix. If your selector doesn't return it, you
> just skipped the one test that catches the bug.
>
> Across one hundred seventy-two labelled instances in seven repositories:
> name-matched graphs reach the guarding test thirty-one percent of the time.
> Full pyright type resolution: forty-two percent. On django alone, fifty-five.
> On matplotlib and pytest: zero — the guarding tests sit in a different
> component of the graph. The bar for safely skipping is ninety-five percent.
> Nothing is close, and upgrading the extractor moved paired recall by seven
> points — the same precision-recall separation ICSE 2020 reported for Java.

*Screen: the recall table from docs/gate.md.*

## 3. Demo — 1:15–2:20

*Terminal, live:*

```bash
uv run python scripts/gate_demo.py
```

> The corpus verdict: RUN_FULL, exit code one — drop it in CI and an unmeasured
> graph fails the build. Then one real instance: django-10097. The walk is
> graph-complete — and it selected zero of the three hundred and seventy tests
> that guard this fix. Zero.

*Browser: `localhost:8000/gate/django__django-10097` — point at
`dropped_guarding_tests` and the Cypher. Then one beat:*

```bash
friction gate --repo . --changed src/friction/gate.py
```

> And it runs on your repository, today — with the corpus recall applied as a
> stated prior, because an unlabelled repo can't yield a recall figure and we
> won't pretend otherwise. Agents get the same answer over MCP.

## 4. HydraDB — 2:20–2:50

> Both graphs live in one HydraDB engine in disjoint id bands. The walk runs
> in-engine — and we learned the engine's rules by measurement: count(*) works
> where count(n) is rejected; incoming variable-length patterns are rejected,
> so the backwards walk is an outward walk over a materialised reverse edge;
> bounded reachability answers in twelve milliseconds where path enumeration
> timed out at thirty seconds. Three findings went upstream: issue 81, PR 82,
> and the CI in this repo wipes the store between phases because of what we
> found.
>
> Substrate Friction: measure the graph before you trust it.

*Screen: the hydra-verify badge, green.*

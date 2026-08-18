# Video narration — FINAL (plain-language cut)

**The master production doc is `docs/video-production.md`** — shots,
timings, edit plan, rubric map. This file is the narration alone, for
reading aloud at the mic. 453 words ≈ 2:50 at a brisk pace.

Speak from `docs/MINDMAP.md`'s glossary: map, seatbelt, hit rate,
run everything. Screens stay technical; your voice stays human.

## SHOT 0 — cold open

> "An AI tool just used its map of this code to pick which tests to run.
> The map says: done. It found **zero** of the **three hundred and seventy**
> tests that would catch this bug. Substrate Friction is the seatbelt that
> stops this."

## SHOT 1 — the problem

> "Every AI coding tool draws a map of your code and trusts it to skip
> tests. Here's the trap: the map can be perfectly drawn — and still missing
> roads. And a tool can never warn you about a road its map doesn't have."

## SHOT 2 — what we built

> "We started out predicting which tickets AI fails at. Our own rules
> killed that idea — so we asked a simpler question: is the map any good?
> Nobody had checked the maps these tools actually use. We built the checker: the code mapped two ways,
> one HydraDB engine measuring, one seatbelt — as a command line, an API, a
> tool the AI itself can ask, a security finding, and an Action guarding
> this very repo."

## SHOT 3 — the numbers

> "Tested against one hundred seventy-two real bug fixes: the map most
> tools use finds the bug-catching test thirty-one percent of the time. The
> careful map: forty-two. On two major projects: **never**. And across
> eight years of Django it never improved. Not a bug that ages out — it's
> how the map is made."

## SHOT 4a — the gate

> "The seatbelt in action. Hit rate measured, bar set at ninety-five
> percent, verdict: run everything. Exit code one — in your CI, that blocks
> the merge."

## SHOT 4b — live in the engine

> "Now the graph database does it itself: sixty-one thousand connections
> loaded live, the check runs **inside HydraDB** in two-point-six
> milliseconds, matching our answer exactly — the database proves which
> test would have been skipped."

## SHOT 4c — the anti-join

> "Even our headline number is computed by the database — two milliseconds
> per connection checked — and if it can't reproduce our result exactly, it
> refuses to answer at all."

## SHOT 4d — the agent abstains

> "And here, an AI agent asks the seatbelt before trusting its own map —
> and backs off. That's the safety signal researchers say agents can't
> generate for themselves."

## SHOT 5 — HydraDB

> "HydraDB holds both maps at once and answers in milliseconds where the
> naive approach hit a thirty-second wall. We pinned the exact engine build,
> and sent four findings back to its makers — including one we got wrong
> and publicly retracted."

## SHOT 6 — proof + potential

> "Is this real? We broke our own meter on purpose — the score falls to
> zero, as it should. We published the three predictions that came back
> wrong. One command re-derives every number you just watched. And every
> map an AI trusts needs this seatbelt. Substrate Friction: measure the map
> before you trust it."

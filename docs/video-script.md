# Video narration — FINAL (plain-language cut, with the bot beat)

**The master production doc is `docs/video-production.md`** — shots,
timings, edit plan, rubric map. This file is the narration alone, for
reading aloud at the mic. ~436 words ≈ 2:49 at a brisk pace.

Speak from `docs/MINDMAP.md`'s glossary: map, seatbelt, hit rate,
run everything, triage. Screens stay technical; your voice stays human.

## SHOT 0 — cold open (0:00)

> "An AI tool just used its map of this code to pick which tests to run.
> The map says: done. It found **zero** of the **three hundred and seventy**
> tests that would catch this bug. Substrate Friction is the seatbelt that
> stops this."

## SHOT 1 — the problem (0:12)

> "Every AI coding tool draws a map of your code and trusts it to skip
> tests. The trap: a map can be perfectly drawn — and still missing roads a
> tool can never warn you about."

## SHOT 2 — what we built + the bot (0:32)

> "We started out predicting which tickets AI fails at. Our own rules
> killed that idea — so we asked a simpler question: is the map any good?
> Nobody had checked. We built the checker — the code mapped two ways, a
> HydraDB engine measuring, a seatbelt deciding — shipped five ways:
> command line, API, a tool the AI itself can ask, a security finding, and
> a bot that installs on any repo in ten lines and triages every pull
> request: safe for AI, or needs a human."

## SHOT 3 — the numbers (1:04)

> "Tested against one hundred seventy-two real bug fixes: the map most
> tools use finds the bug-catching test thirty-one percent of the time. The
> careful map: forty-two. On two major projects: **never**. And across
> eight years of Django it never improved. Not a bug that ages out — it's
> how the map is made."

## SHOT 4a — the gate (1:26)

> "The seatbelt: hit rate measured, bar at ninety-five percent, verdict —
> run everything. Exit code one blocks the merge."

## SHOT 4b — live in the engine (1:34)

> "Now the graph database does it itself: sixty-one thousand connections
> loaded live, the check runs **inside HydraDB** in two-point-six
> milliseconds, matching our answer exactly — or refusing to answer at all."

## SHOT 4c — the bot on a stranger's PR (1:50)

> "Here's the bot on a real FastAPI pull request it has never seen.
> Verdict in seconds: needs a human — start with this one test of three
> hundred sixteen. Even saying no, it hands the reviewer a head start."

*(If your live run prints different numbers — the PR moved — speak the
numbers on YOUR screen. Never dub a number the frame doesn't show.)*

## SHOT 4d — the agent abstains (2:07)

> "And an AI agent asks the seatbelt before trusting its own map — and
> backs off. That's the safety signal agents can't generate for
> themselves."

## SHOT 5 — HydraDB (2:16)

> "HydraDB holds both maps at once and answers in milliseconds where the
> naive approach hit a thirty-second wall. Even our headline number is computed in-engine,
> reproduced exactly or not at all. We pinned the build and sent four
> findings upstream — including one we got wrong and
> publicly retracted."

## SHOT 6 — proof + potential (2:35)

> "Is this real? We broke our own meter on purpose — the score falls to
> zero, as it should. We published the predictions that came back wrong,
> scored ourselves out of a hundred, and showed every receipt. One command
> re-derives every number you just watched. Substrate Friction: measure the
> map before you trust it."

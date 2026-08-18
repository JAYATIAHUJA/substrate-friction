# The Mind Map — what you are actually presenting

One page. If you can say this page, you can present to anyone.

## The whole thing in one sentence

**AI coding tools skip tests using a map of your code — we measured the map,
it's missing half the roads, and we built the seatbelt that stops anything
from skipping until the map is proven good.**

## The story tree

```
WHO IS THIS FOR
└─ Any team letting AI touch their code (Copilot, Cursor, Claude, agents)

THE PAIN (they already feel it)
└─ AI tools save time by running only the tests they think matter.
   They decide using a MAP of your code (a "call graph").
   If the map is wrong, the one test that would have caught the bug
   never runs — and the bug ships. Silently.

THE DISCOVERY (what nobody checked)
└─ We checked the map against 172 real, human-verified bug fixes.
   The map found the right test 42% of the time. Not 95.42.
   On some projects: 0%. And it's been like this for 8 years — it's
   not getting better on its own.

THE PRODUCT (the seatbelt)
└─ `friction gate` — a check that runs BEFORE anything skips:
   "Is this map good enough to trust?"  Measured answer: NO →
   run everything. It refuses to gamble. That refusal IS the product.

WHERE IT PLUGS IN (three doors, all built)
├─ CI: blocks the merge if a tool tried to skip on a bad map
├─ The AI itself (MCP): the agent asks the gate before trusting its map
└─ Security tab (SARIF): "unsafe test skip" shows up like a vulnerability

WHY BELIEVE US (the trust story)
└─ Every number is recomputed by one command (friction verify).
   We published our own failures — three wrong hypotheses, three
   retractions, all still in the repo. We even filed our own bug
   report wrong, found the truth, and retracted it publicly.
```

## The glossary — same words, everywhere

Use these swaps in every spoken sentence. Screens can stay technical;
your mouth stays human.

| Technical | Say instead |
|---|---|
| call graph / code graph | **the map of your code** |
| guarding test (FAIL_TO_PASS) | **the one test that catches that exact bug** |
| recall | **hit rate** — how often the map finds that test |
| RUN_FULL / exit 1 | **"run everything — don't gamble"** |
| the gate | **the seatbelt** (a check before anything skips) |
| arm A / arm B | **the quick map** (what tools actually use) vs **the careful map** (type-checked) |
| graph-complete ≠ program-complete | **the map can be perfectly drawn and still missing roads** |
| in-engine / HydraDB | **the graph database does the checking itself** |
| negative control | **we broke it on purpose to prove the meter works** |

## Three versions of the pitch

**To anyone (10 seconds):**
"AI coding tools skip tests to save time, using a map of your code. We
measured the map — it misses more than half of what matters. Our tool is the
seatbelt: nothing skips until the map is proven good."

**To an engineer (30 seconds):**
"Every agent builds a call graph by name-matching, and test selection walks
it. We measured that graph's recall of the exact test guarding each fix,
against 172 SWE-bench-verified instances: 0.31 name-matched, 0.42
type-resolved, zero on matplotlib and pytest — and flat across eight years of
Django. `friction gate` turns that measurement into a fail-closed exit code,
in CI, over MCP, and as SARIF."

**To a judge (the arc):**
"We set out to predict which tickets AI fails at. Our own protocol killed the
idea — so we performed the autopsy, and found something bigger: the map every
AI tool trusts was never measured. We measured it, it fails, and we shipped
the seatbelt. Then we made the database itself do the measuring, published
every mistake we made along the way, and built one command that re-proves
every number."

## If pressed

Every hard question already has its strongest form filed in
`docs/objections.md` — including the two bugs an adversarial review found
(and we fixed same-day). If someone raises: narrow oracle → §4; hindsight
→ §5; economics → §9; "it's just exit 1" → §1; the pivot → §2. The answer
is one sentence: *"Filed, answered, with receipts."*

## The one rule

**Lead with the map and the seatbelt. Earn the right to say "recall" and
"graph" later.** A person who understands the seatbelt will sit through the
statistics; a person drowning in "bounded reachability" at second ten never
recovers.

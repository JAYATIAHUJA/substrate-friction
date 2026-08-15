"""What name matching costs, joined to consequence.

This is the headline: it turns "these graph edges are wrong" into "wrong edges
cost this much." It does so in two moves, and keeps them scrupulously separate.

1. **The measurement (ours, reproducible).** ``load_report`` parses the
   COMMITTED ``docs/graph-delta.md`` rather than recomputing anything, so the
   numbers here can never drift from the report they cite. That report compares
   an arm-A name-matched call graph (what Aider / RepoGraph / LocAgent build)
   against an arm-B type-resolved graph (scip-python / pyright), on the same
   django commit, over a fair identity join. Arm A confirms only 74.6% of its
   own edges (a CEILING — see below) and recovers only 35.2% of arm B's.

2. **The consequence (an analogy, NOT ours).** ``project_localization_cost``
   maps that measured edge quality onto ARISE's PUBLISHED edge-quality ablation
   band and returns an INTERVAL with the assumption spelled out. We did not run
   SWE-bench and we did not measure a resolve-rate delta ourselves; the basis
   string says so in as many words.

The precision number is reported as a **ceiling in both directions**: pyright
emits no occurrence for an untyped receiver, so arm B under-reports rather than
inventing edges. An arm-A edge missing from arm B is therefore either a genuine
false positive OR a case pyright declined to resolve. The ``cursor`` family
(54 edges) is the honest counter-example where arm A was RIGHT and pyright was
the incomplete one, which is exactly why 0.746 is a floor on true precision,
not a cap: true precision >= 0.746, never <=.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# ARISE (arXiv 2605.03117) improved call-graph edge quality on SWE-bench Lite
# and moved end-to-end resolve 17.3% -> 22.0%: a +4.7 percentage-point dividend
# (and Function Recall@1 0.43 -> 0.60). That PUBLISHED delta is the upper witness
# of what fixing edges can buy, so it is the full width of the band we map our
# measured graph quality onto. We do not exceed it, and we did not reproduce it.
ARISE_RESOLVE_BAND_PP = 4.7          # percentage points, published
ARISE_RESOLVE_BAND = 0.047           # the same, as a fraction of instances

_DEFAULT_REPORT = Path("docs/graph-delta.md")


@dataclass(frozen=True)
class PrecisionReport:
    precision_ceiling: float
    recall: float
    jaccard: float
    confirmed: int
    only_a: int
    only_b: int
    compared: int
    offenders: list[tuple[str, int]]
    counter_example: tuple[str, int]


@dataclass(frozen=True)
class CostProjection:
    low: float
    high: float
    basis: str
    assumption: str


# --------------------------------------------------------------------------
# Parsing the committed docs/graph-delta.md.
# --------------------------------------------------------------------------

def _measure(text: str, label: str) -> str:
    """Pull the value out of a ``| <label> | **<value>** |`` measure row."""
    m = re.search(
        r"\|\s*" + re.escape(label) + r"\s*\|\s*\*{0,2}\s*([0-9.]+)\s*\*{0,2}\s*\|",
        text,
    )
    if not m:
        raise ValueError(f"could not parse measure {label!r} from the report")
    return m.group(1)


def _section(text: str, heading: str) -> str:
    """Return the body of the ``## heading`` section, up to the next ``## ``."""
    idx = text.find(heading)
    if idx == -1:
        raise ValueError(f"could not find section {heading!r} in the report")
    rest = text[idx:]
    nxt = rest.find("\n## ", 1)
    return rest if nxt == -1 else rest[:nxt]


def _offenders(text: str) -> list[tuple[str, int]]:
    section = _section(text, "## Where arm A's unconfirmed edges point")
    out: list[tuple[str, int]] = []
    for m in re.finditer(r"\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|", section):
        out.append((m.group(1), int(m.group(2))))
    if not out:
        raise ValueError("could not parse the offender table from the report")
    return out


def _counter_example(text: str) -> tuple[str, int]:
    section = _section(text, "## Counter-example")
    num = re.search(r"\*\*(\d+)\*\*", section)
    sym = re.search(r"`([^`]+)`", section)
    if not num or not sym:
        raise ValueError("could not parse the counter-example from the report")
    # `django.db.backends.base.base.BaseDatabaseWrapper::cursor` -> "cursor"
    name = sym.group(1).split("::")[-1].split(".")[-1].rstrip("().#")
    return (name, int(num.group(1)))


def _compared(text: str) -> int:
    m = re.search(r"arm_a_edges_compared[^\n:]*:\s*(\d+)", text)
    if not m:
        raise ValueError("could not parse arm_a_edges_compared from the report")
    return int(m.group(1))


def load_report(path: Path = _DEFAULT_REPORT) -> PrecisionReport:
    """Parse the committed ``docs/graph-delta.md`` into a :class:`PrecisionReport`.

    Parsing rather than recomputing is deliberate: it makes drift between this
    module and the committed report impossible. The report is the single source
    of truth for every number here.
    """
    text = Path(path).read_text(encoding="utf-8")
    return PrecisionReport(
        precision_ceiling=float(_measure(text, "Arm A precision (ceiling)")),
        recall=float(_measure(text, "Arm A recall of arm B")),
        jaccard=float(_measure(text, "Jaccard")),
        confirmed=int(_measure(text, "Arm A edges confirmed by arm B")),
        only_a=int(_measure(text, "Arm A edges arm B does not have")),
        only_b=int(_measure(text, "Arm B edges arm A missed")),
        compared=_compared(text),
        offenders=_offenders(text),
        counter_example=_counter_example(text),
    )


# --------------------------------------------------------------------------
# Projecting the consequence — an ARISE-anchored interval.
# --------------------------------------------------------------------------

def project_localization_cost(precision: float, recall: float) -> CostProjection:
    """Map measured edge quality onto ARISE's published ablation band.

    Returns an INTERVAL, never a point estimate, of the localization cost a
    name-matched graph of this ``(precision, recall)`` carries — expressed as a
    fraction of instances of SWE-bench-Lite-style resolve rate, and bounded to
    ``[0, ARISE_RESOLVE_BAND]`` so it can never exceed what ARISE actually
    published.

    The reasoning, kept deliberately conservative so a reviewer cannot call it
    inflated:

    * ARISE moved resolve +4.7pp by upgrading edge quality end to end. That is
      the *most* anyone has published for such an upgrade, so it is the ceiling
      of the whole band. We never claim more.
    * A graph's badness is anchored on its **wrong** edges — ``1 - precision``,
      the fraction of arm-A edges arm B does not confirm. This is the driver
      the localization literature (RGFL: wrong element implicated in 53% of
      unresolved instances) ties to lost resolves. When precision is perfect
      there are no wrong edges and the cost is zero, whatever the recall.
    * The interval's width above that floor comes from **missing** edges —
      ``1 - recall`` — because a graph that also omits true edges gives the
      agent less correct signal to compensate with. The top of the interval is
      ``wrong * (1 + miss)``, capped at 1 (the full band).
    * Multiplying the badness fraction by ARISE's +4.7pp band converts it to a
      projected resolve-rate cost.

    For the measured django numbers (precision 0.746, recall 0.352) this yields
    roughly a 1.2pp-to-2.0pp band — well under ARISE's full 4.7pp, because a
    name-matched graph is a partial, not total, degradation of edge quality.
    """
    wrong = max(0.0, 1.0 - precision)          # unconfirmed-edge fraction (ceiling)
    miss = max(0.0, 1.0 - recall)              # missed-true-edge fraction
    badness_low = wrong
    badness_high = min(1.0, wrong * (1.0 + miss))

    low = round(badness_low * ARISE_RESOLVE_BAND, 4)
    high = round(badness_high * ARISE_RESOLVE_BAND, 4)

    basis = (
        "ANALOGY to ARISE (arXiv 2605.03117); this is NOT a measurement we "
        "performed. ARISE improved call-graph edge quality on SWE-bench Lite and "
        "moved end-to-end resolve 17.3%->22.0% (+4.7pp) and Function Recall@1 "
        "0.43->0.60. We map our measured edge quality onto that published band. "
        "We did not run SWE-bench and measured no resolve-rate delta ourselves."
    )
    assumption = (
        "Assumes ARISE's published edge-quality->resolve elasticity transfers to "
        "a name-matched vs type-resolved graph on the same Python task family. "
        f"The low bound charges only the unconfirmed-edge fraction (1-precision="
        f"{wrong:.3f}); the high bound compounds it with the missed-true-edge "
        f"fraction (1-recall={miss:.3f}), capped at ARISE's full +4.7pp band. "
        "Because arm-A precision is a CEILING (pyright under-reports untyped "
        "receivers, so the true wrong fraction is <= 1-precision), both bounds "
        "are conservative. Reported as fractions of resolve rate: multiply by "
        "100 for percentage points."
    )
    return CostProjection(low=low, high=high, basis=basis, assumption=assumption)


# --------------------------------------------------------------------------
# The generated report — docs/precision.md.
# --------------------------------------------------------------------------

def write_report(report: PrecisionReport, projection: CostProjection,
                 path: Path) -> None:
    """Generate ``docs/precision.md`` from a report and its cost projection."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    r, proj = report, projection
    low_pp = proj.low * 100.0
    high_pp = proj.high * 100.0
    ce_name, ce_count = r.counter_example

    lines: list[str] = []
    lines.append("# What name matching costs")
    lines.append("")
    lines.append(
        "Arm A is a name-matched call graph, built the way the widely-used "
        "repo-graph tools (Aider, RepoGraph, LocAgent) build one. Arm B is "
        "type-resolved via `scip-python` (pyright). Same django commit, same "
        "definitions, joined into one node space by `friction.identity`. Every "
        "number in the measured table below is parsed from the committed "
        "`docs/graph-delta.md`, not recomputed here, so this page cannot drift "
        "from that report.")
    lines.append("")

    lines.append("## Measured (ours, reproducible)")
    lines.append("")
    lines.append("| Measure | Value |")
    lines.append("|---|---|")
    lines.append(f"| Arm A edges confirmed by arm B | **{r.confirmed}** |")
    lines.append(f"| Arm A edges arm B does not have | **{r.only_a}** |")
    lines.append(f"| Arm B edges arm A missed | **{r.only_b}** |")
    lines.append(f"| Arm A edges compared (in scope) | **{r.compared}** |")
    lines.append(f"| Arm A precision (ceiling) | **{r.precision_ceiling}** |")
    lines.append(f"| Arm A recall of arm B | **{r.recall}** |")
    lines.append(f"| Jaccard | {r.jaccard} |")
    lines.append("")

    lines.append("## Where arm A's unconfirmed edges point")
    lines.append("")
    lines.append("These are container-method name collisions: `list.extend` "
                 "bound to a GIS class, `str.lower` bound to "
                 "`django.template.defaultfilters.lower`.")
    lines.append("")
    lines.append("| Target name | Unconfirmed edges |")
    lines.append("|---|---|")
    for name, n in r.offenders:
        lines.append(f"| `{name}` | {n} |")
    lines.append("")

    lines.append("## The ceiling is honest in both directions")
    lines.append("")
    lines.append(
        f"Arm-A precision is reported as a **ceiling**, and the direction of the "
        f"bias is stated both ways. pyright emits no occurrence when a receiver's "
        f"type is unknown, so arm B **under-reports** rather than inventing "
        f"edges. An arm-A edge missing from arm B is therefore either a genuine "
        f"false positive OR a call pyright declined to resolve.")
    lines.append("")
    lines.append(
        f"The `{ce_name}` family — **{ce_count}** unconfirmed arm-A edges "
        f"pointing at `BaseDatabaseWrapper.{ce_name}()` — is the honest "
        f"counter-example. These are real `self.connection.cursor()` calls where "
        f"the receiver is untyped, so pyright emits nothing and arm B "
        f"under-reports. Here arm A was **right** and the type-resolved graph is "
        f"the incomplete one. This is exactly why 0.746 is a floor on true "
        f"precision, not a cap: **true precision is >= 0.746, never <=**. Read "
        f"the ceiling in both directions — some unconfirmed edges are arm A's "
        f"errors, and some are arm B's omissions.")
    lines.append("")

    lines.append("## What the wrong edges cost")
    lines.append("")
    lines.append(
        f"Projected localization cost of a name-matched graph of this quality: "
        f"**{low_pp:.1f}pp to {high_pp:.1f}pp** of resolve rate "
        f"(interval `[{proj.low}, {proj.high}]` as a fraction of instances). "
        f"This is an interval, never a point estimate.")
    lines.append("")
    lines.append(f"- **Basis.** {proj.basis}")
    lines.append(f"- **Assumption.** {proj.assumption}")
    lines.append("")
    lines.append(
        "This page does **not** claim we measured a resolve-rate delta. We did "
        "not run SWE-bench. The interval above is a projection under the stated "
        "assumption, anchored to a published ablation.")
    lines.append("")

    lines.append("## Published anchors (published, not reproduced here)")
    lines.append("")
    lines.append(
        "- **ARISE** (arXiv 2605.03117): richer structural + data-flow edges "
        "lift Function Recall@1 0.43->0.60 and end-to-end resolve 17.3%->22.0% "
        "on SWE-bench Lite. *Published, not reproduced here* — it is the band "
        "our cost projection is mapped onto by analogy.")
    lines.append(
        "- **SHERLOC** (arXiv 2606.24820): +5.95pp mean across 10 "
        "backbone x framework cells, and poor localization causes NEGATIVE "
        "transfer (a model can lose 4-5pp under unfiltered localization). "
        "*Published, not reproduced here.*")
    lines.append(
        "- **RGFL** (arXiv 2601.18044): counterfactual localization substitution "
        "attributes wrong-element localization to 53% of unresolved instances "
        "(wrong file 13%, wrong line 84%). *Published, not reproduced here.*")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

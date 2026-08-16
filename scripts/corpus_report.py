"""Summarise the multi-repo corpus: per-repo table + docs/corpus.md.

Reads data/instances/corpus/manifest.jsonl (built + carried records) and
attempts.jsonl (build attempts, for attempted-vs-built), and writes the honest
per-repo rollup the plan asks for: attempted, built, endpoint-mapping success
rate (both arm_b fix AND test non-empty = "usable"), median nodes/edges, and
wall clock. Usable n is the number the evaluation can actually use.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_corpus3 as bc  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "data" / "instances" / "corpus" / "manifest.jsonl"
ATTEMPTS = REPO / "data" / "instances" / "corpus" / "attempts.jsonl"
DOC = REPO / "docs" / "corpus.md"


def load_records() -> list[dict]:
    return [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]


def load_attempts() -> list[dict]:
    if not ATTEMPTS.exists():
        return []
    return [json.loads(l) for l in ATTEMPTS.read_text().splitlines() if l.strip()]


def attempted_by_repo(attempts: list[dict]) -> dict[str, int]:
    seen: dict[str, set] = defaultdict(set)
    for a in attempts:
        seen[a.get("repo", "?")].add(a.get("instance_id"))
    return {r: len(s) for r, s in seen.items()}


def main() -> int:
    records = load_records()
    attempts = load_attempts()
    agg = bc.aggregate_by_repo(records)
    attempted = attempted_by_repo(attempts)

    repos = sorted(agg)
    total_built = sum(agg[r]["built"] for r in repos)
    total_usable = sum(agg[r]["usable_arm_b"] for r in repos)

    # Console table.
    hdr = (f"{'repo':<14}{'attempted':>10}{'built':>7}{'usable':>8}"
           f"{'map%':>7}{'med_nodes':>11}{'med_edges':>11}{'wall_min':>10}")
    print(hdr)
    print("-" * len(hdr))
    for r in repos:
        a = agg[r]
        att = attempted.get(r, a["built"])  # carried repos have no attempts log
        rate = (100.0 * a["usable_arm_b"] / a["built"]) if a["built"] else 0.0
        print(f"{r:<14}{att:>10}{a['built']:>7}{a['usable_arm_b']:>8}"
              f"{rate:>6.0f}%{a['median_nodes_arm_b']:>11}"
              f"{a['median_edges_arm_b']:>11}{a['wall_seconds']/60:>10.1f}")
    print("-" * len(hdr))
    rate_all = (100.0 * total_usable / total_built) if total_built else 0.0
    print(f"{'TOTAL':<14}{'':>10}{total_built:>7}{total_usable:>8}{rate_all:>6.0f}%")
    print(f"\nTotal instances built: {total_built}")
    print(f"Total USABLE n (arm_b both endpoints): {total_usable}")

    # docs/corpus.md
    lines = [
        "# Corpus (Task 4): multi-repo instance corpus",
        "",
        "The evaluation corpus expanded from 50 django instances in a single "
        "repository to a multi-repo corpus, so a **leave-one-repo-out** split "
        "(Task 5) becomes possible and repo identity stops being a total "
        "confound.",
        "",
        "Each instance is a SWE-bench Verified task built at its own "
        "`base_commit` with the test patch applied, indexed with scip-python, "
        "and emitted as two graph arms (name-matched A, type-resolved B) with "
        "fix-site and test-target endpoints resolved in each arm's id space. "
        "All builds ran against per-repo throwaway `git clone --shared` working "
        "trees; the reference clones under `data/repos/` were never checked out "
        "destructively.",
        "",
        "**Usable n** = instances whose type-resolved arm B mapped **both** a "
        "fix site and a test target (an instance with no test endpoint cannot "
        "test a fix->test path). This is the number the evaluation can use; it "
        "is reported per repo, not just overall.",
        "",
        "## Per-repo",
        "",
        "| repo | attempted | built | usable n | mapping % | median nodes (B) | "
        "median edges (B) | wall (min) |",
        "|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in repos:
        a = agg[r]
        att = attempted.get(r, a["built"])
        rate = (100.0 * a["usable_arm_b"] / a["built"]) if a["built"] else 0.0
        lines.append(
            f"| {r} | {att} | {a['built']} | {a['usable_arm_b']} | {rate:.0f}% | "
            f"{a['median_nodes_arm_b']} | {a['median_edges_arm_b']} | "
            f"{a['wall_seconds']/60:.1f} |"
        )
    lines.append(
        f"| **total** | | **{total_built}** | **{total_usable}** | "
        f"**{rate_all:.0f}%** | | | |"
    )
    lines += [
        "",
        f"**Total instances built: {total_built}. Total usable n: "
        f"{total_usable}.**",
        "",
        "## Notes and honesty caveats",
        "",
        "- **Repo selection deviated from the plan, on measured evidence.** The "
        "plan named the 3 largest non-django repos (real counts: sympy 75, "
        "sphinx 44, matplotlib 34 -- *not* scikit-learn as the plan guessed). "
        "sphinx and matplotlib built cleanly. **sympy, and the two next-largest "
        "candidates scikit-learn and astropy, index pathologically slowly** "
        "(~12-18+ min/instance for a full scip index of a large scientific "
        "codebase) -- scip index time scales with codebase size. Per the plan's "
        "own rule ('if a repo burns hours, stop and move to the next'), the "
        "corpus was filled out with the *smaller* SWE-bench repos, which index "
        "fast (requests ~7 s, pytest ~15 s, xarray ~2 min) and map endpoints at "
        "100%. The result is a **7-repo** corpus -- broader than the planned 4, "
        "which is strictly better for leave-one-repo-out.",
        "- **sympy was capped at 3** (throughput, not a mapping failure -- "
        "sympy's endpoints map at 100%). A concurrency finding: running two "
        "heavy scip indexers at once (sympy + matplotlib) OOM-crashes scip-python "
        "on sympy; run alone it succeeds. The builder now serialises heavy "
        "indexers. scikit-learn and astropy were cloned and piloted but dropped "
        "for the same throughput reason.",
        "- **django (50) was carried, not rebuilt.** The existing "
        "`data/instances/arms/manifest.jsonl` records already carry the "
        "load-bearing endpoint fields (arm_b fix/test ids); rebuilding them "
        "would cost ~2.3 h and not change the usable-n figure. They are tagged "
        "`source: \"carried\"`. The newly built repos additionally carry the "
        "fuller typed node/edge census (`node_labels`/`edge_types`); the carried "
        "django records predate that field but are otherwise format-compatible "
        "on every field the evaluation reads.",
        "- **Arm NDJSON location resolves by `source`.** Built records "
        "(`source: \"built\"`) store their arm files under "
        "`data/instances/corpus/arms/<id>/{arm_a,arm_b}/`; carried django "
        "records (`source: \"carried\"`) reuse the originals under "
        "`data/instances/arms/<id>/`. A consumer (Task 5) picks the base dir "
        "from the record's `source` field. Per-instance `index.scip` files are "
        "deleted after each build; the loader reads the NDJSON, not the SCIP.",
        "- **django is the only repo below 100% mapping (88%, 44/50).** Its "
        "misses are inherited test methods with no physical def in the named "
        "subclass and module-level diff hunks (see `friction.arms` Finding 1). "
        "Every pytest-native repo maps at 95-100%, so the usable-n loss is "
        "concentrated in django, not spread across the corpus.",
        "- **COVERS is static-only in this corpus.** Per-instance dynamic COVERS "
        "tracing (Task 1) is not folded into these arm files; each record is "
        "tagged `covers: \"static-only\"`. COVERS is unioned at analysis time by "
        "`friction.covers3` where a trace exists.",
        "- **Power.** The project's power analysis needs ~610 instances to "
        "detect +0.05 AUC at rho=0.5; this corpus is still well short of that. "
        "What it buys is the ability to resolve *anything at all* (n=44 could "
        "not) and a repo-held-out split (Task 5).",
    ]
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {DOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""S1: the corpus-scale gate audit — 7 repos, every usable instance.

Emits ONE json artifact (`data/shipped/gate-results.json`) that is the single
source of truth for every corpus figure quoted anywhere. `docs/gate.md`'s
corpus section, the README table and the acceptance test all read this file.

    uv run python scripts/gate_corpus.py --out data/shipped/gate-results.json

Roots: django's arms live under data/instances/arms/, the other six repos
under data/instances/corpus/arms/. A judge's clean clone has neither (they are
regeneration inputs, ~4.5 GB); the committed artifact is the run's output.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from friction.gate import _edges_path, _load_edges, select_tests

REPO_NAMES = {
    "django": "django", "sphinx-doc": "sphinx", "matplotlib": "matplotlib",
    "pydata": "xarray", "pytest-dev": "pytest", "psf": "requests",
    "sympy": "sympy",
}


def _wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def run(manifests: list[Path], roots: list[Path], k: int) -> dict:
    per_instance = []
    seen = set()
    for mf in manifests:
        with mf.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                iid = rec["instance_id"]
                if iid in seen:
                    continue
                seen.add(iid)
                repo = REPO_NAMES.get(iid.split("__", 1)[0],
                                      iid.split("__", 1)[0])
                row = {"instance_id": iid, "repo": repo}
                for arm in ("arm_a", "arm_b"):
                    entry = rec.get(arm) or {}
                    fix = list(entry.get("fix_site_ids") or [])
                    tests = list(entry.get("test_target_ids") or [])
                    if not fix or not tests:
                        row[arm] = None            # not measurable: no endpoints
                        continue
                    path = None
                    for root in roots:
                        path = _edges_path(root, iid, arm)
                        if path is not None:
                            break
                    if path is None:
                        row[arm] = None            # not measurable: no graph
                        continue
                    hit = bool(select_tests(_load_edges(path), fix, tests,
                                            k).selected)
                    row[arm] = {"hit": hit}
                per_instance.append(row)

    summary: dict = {"k": k, "per_repo": {}, "pooled": {}}
    repos = sorted({r["repo"] for r in per_instance})
    for arm in ("arm_a", "arm_b"):
        pooled_h = pooled_n = 0
        for repo in repos:
            h = sum(1 for r in per_instance
                    if r["repo"] == repo and r[arm] and r[arm]["hit"])
            n = sum(1 for r in per_instance
                    if r["repo"] == repo and r[arm] is not None)
            summary["per_repo"].setdefault(repo, {})[arm] = {"hits": h, "n": n}
            pooled_h += h
            pooled_n += n
        lo, hi = _wilson(pooled_h, pooled_n)
        summary["pooled"][arm] = {
            "hits": pooled_h, "n": pooled_n,
            "recall": round(pooled_h / pooled_n, 4) if pooled_n else 0.0,
            "wilson95": [round(lo, 4), round(hi, 4)],
        }
    return {"study": "S1 (docs/studies.md)", "summary": summary,
            "per_instance": per_instance}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args(argv)

    manifests = [Path("data/instances/corpus/manifest.jsonl"),
                 Path("data/instances/arms/manifest.jsonl")]
    roots = [Path("data/instances/corpus/arms"), Path("data/instances/arms")]
    missing = [str(m) for m in manifests if not m.exists()]
    if missing:
        raise SystemExit(f"corpus inputs absent (regeneration machine only): "
                         f"{missing}")

    result = run(manifests, roots, args.k)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")

    s = result["summary"]
    print(f"wrote {args.out}")
    for arm in ("arm_a", "arm_b"):
        p = s["pooled"][arm]
        print(f"  {arm}: pooled {p['hits']}/{p['n']} = {p['recall']:.3f} "
              f"(95% CI {p['wilson95'][0]:.3f}-{p['wilson95'][1]:.3f})")
    for repo, arms in sorted(s["per_repo"].items()):
        cells = [f"{arm}={a['hits']}/{a['n']}" for arm, a in arms.items()]
        print(f"    {repo:<12} {'  '.join(cells)}")


if __name__ == "__main__":
    main()

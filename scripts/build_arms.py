"""Build both graph arms (name-matched A, type-resolved B) for the 50 django
SWE-bench instances named in ``data/instances/graphs.json`` (the v1 manifest).

For each instance this calls ``friction.arms.build_instance``, which checks out
the base commit, applies the test patch, builds arm A (tree-sitter name match)
and arm B (scip-python / pyright), writes loader-ready NDJSON per arm into
``data/instances/arms/<instance_id>/{arm_a,arm_b}/``, and returns a record with
per-arm node/edge counts and the band-local fix-site / test-target endpoint ids.

The record for each finished instance is appended to
``data/instances/arms/manifest.jsonl`` immediately, so the run is
crash-resumable: instances already present in the manifest are skipped.

The ``idx`` passed to ``build_instance`` (which fixes each arm's disjoint id
band) is the instance's position in ``graphs.json`` order, so a resumed run
re-derives the identical band for every instance regardless of --limit.

Usage:
    uv run python scripts/build_arms.py [--limit N] [--resume]

The HydraDB engine is NOT needed; this only builds and writes NDJSON on disk.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GRAPHS = REPO / "data" / "instances" / "graphs.json"
ARMS_ROOT = REPO / "data" / "instances" / "arms"
MANIFEST = ARMS_ROOT / "manifest.jsonl"
DJANGO = REPO / "data" / "repos" / "django"


def _completed_ids() -> set[str]:
    """Instance ids already fully written to the manifest (skip on resume)."""
    if not MANIFEST.exists():
        return set()
    done: set[str] = set()
    with MANIFEST.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["instance_id"])
            except (json.JSONDecodeError, KeyError):
                # A torn trailing line from a crash mid-write; ignore it.
                continue
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="Build at most N (not-yet-done) instances then stop.")
    ap.add_argument("--resume", action="store_true",
                    help="No-op flag for clarity; already-manifested instances "
                         "are always skipped.")
    args = ap.parse_args()

    ARMS_ROOT.mkdir(parents=True, exist_ok=True)

    order = json.loads(GRAPHS.read_text())
    idx_of = {row["instance_id"]: i for i, row in enumerate(order)}

    print(f"[{time.strftime('%H:%M:%S')}] loading SWE-bench Verified (django) ...",
          flush=True)
    from friction.swebench import load_instances
    by_id = {i.instance_id: i for i in load_instances(repos=["django/django"])}
    print(f"[{time.strftime('%H:%M:%S')}] hydrated {len(by_id)} django instances",
          flush=True)

    from friction import arms

    done = _completed_ids()
    todo = [row["instance_id"] for row in order if row["instance_id"] not in done]
    if args.limit is not None:
        todo = todo[: args.limit]

    print(f"[{time.strftime('%H:%M:%S')}] {len(done)} already done, "
          f"{len(todo)} to build this run (of {len(order)} total)", flush=True)

    run_t0 = time.perf_counter()
    ok = 0
    for n, iid in enumerate(todo, 1):
        inst = by_id.get(iid)
        if inst is None:
            print(f"[{time.strftime('%H:%M:%S')}] ({n}/{len(todo)}) {iid} "
                  f"FAILED: not in SWE-bench dataset", flush=True)
            continue
        idx = idx_of[iid]
        print(f"[{time.strftime('%H:%M:%S')}] ({n}/{len(todo)}) building {iid} "
              f"(idx={idx}) ...", flush=True)
        try:
            rec = arms.build_instance(inst, DJANGO, idx, ARMS_ROOT)
        except Exception:  # noqa: BLE001 - record the failure, keep going
            print(f"[{time.strftime('%H:%M:%S')}] ({n}/{len(todo)}) {iid} "
                  f"FAILED:\n{traceback.format_exc()}", flush=True)
            continue
        with MANIFEST.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
        a, b = rec["arm_a"], rec["arm_b"]
        print(f"[{time.strftime('%H:%M:%S')}] ({n}/{len(todo)}) DONE {iid} "
              f"{rec['seconds']}s  A[n={a['nodes']} e={a['edges']} "
              f"fix={len(a['fix_site_ids'])} test={len(a['test_target_ids'])}]  "
              f"B[n={b['nodes']} e={b['edges']} fix={len(b['fix_site_ids'])} "
              f"test={len(b['test_target_ids'])}]  comparable={rec['comparable']}",
              flush=True)
        ok += 1

    wall = time.perf_counter() - run_t0
    print(f"[{time.strftime('%H:%M:%S')}] run complete: {ok}/{len(todo)} built "
          f"in {wall / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

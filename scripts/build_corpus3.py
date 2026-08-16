"""Build the multi-repo typed-arm corpus (Task 4).

Expands the evaluation corpus from 50 django instances / 1 repo to 150+ across
four repos, so a leave-one-repo-out split (Task 5) becomes possible. Each
instance is built with :func:`friction.arms.build_instance`, which checks out
the base commit, applies the test patch, indexes with scip-python, extracts the
typed graph, resolves fix/test endpoints in both arms, and emits loader-ready
NDJSON. One JSON line per finished instance is appended to
``data/instances/corpus/manifest.jsonl``.

Safety / determinism
--------------------
* The reference clones under ``data/repos/<name>`` are NEVER checked out
  destructively. Every build runs against a per-repo THROWAWAY ``git clone
  --shared`` under a scratch dir; ``build_instance`` restores that throwaway on
  every exit path, and the whole throwaway is deleted when the repo finishes.
* Resumable: instances already present in the manifest are skipped.
* Per 66 MB ``index.scip`` is deleted after each build (the loader reads the
  NDJSON arms, not the SCIP file), so the corpus stays lean.
* If a repo fails systematically (the first ``--probe`` instances all fail to
  build), that repo is abandoned with a recorded reason and the run moves on --
  rather than burning hours re-hitting the same wall.

The existing 50 django records (``data/instances/arms/manifest.jsonl``) are
carried into the corpus with ``--import-existing`` rather than rebuilt: they
already carry the load-bearing endpoint fields (arm_b fix/test ids), and
rebuilding them would cost ~2.3 h for no change to the usable-n figure. They are
tagged ``source: "carried"`` so the provenance is explicit.

Usage:
    uv run python scripts/build_corpus3.py --import-existing
    uv run python scripts/build_corpus3.py --repos sympy sphinx matplotlib \\
        --limit 60 --probe 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPOS_DIR = REPO / "data" / "repos"
CORPUS_DIR = REPO / "data" / "instances" / "corpus"
CORPUS_ARMS = CORPUS_DIR / "arms"
MANIFEST = CORPUS_DIR / "manifest.jsonl"
ATTEMPTS = CORPUS_DIR / "attempts.jsonl"
EXISTING_DJANGO_MANIFEST = REPO / "data" / "instances" / "arms" / "manifest.jsonl"
SCRATCH_CLONES = Path(
    "/private/tmp/claude-501/-Users-cruzer-Desktop-Hackathon/"
    "60b45b25-ec97-4c90-a007-eefe363648c5/scratchpad/corpus-clones"
)


# --- pure helpers (unit-tested in tests/test_corpus3.py) -------------------

def repo_short(repo: str) -> str:
    """``sphinx-doc/sphinx`` -> ``sphinx``; ``django/django`` -> ``django``."""
    return repo.split("/")[-1]


def select_target_repos(counts: dict[str, int], exclude: set[str],
                        k: int) -> list[str]:
    """The ``k`` largest repos (by instance count) whose short name is not in
    ``exclude``. Ties broken by short name for determinism. Returns short names.
    """
    ranked = sorted(
        ((repo_short(r), n) for r, n in counts.items()
         if repo_short(r) not in exclude),
        key=lambda t: (-t[1], t[0]),
    )
    return [name for name, _ in ranked[:k]]


def completed_ids(manifest_path: Path) -> set[str]:
    """Instance ids already fully written to ``manifest_path`` (skip on resume)."""
    path = Path(manifest_path)
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["instance_id"])
            except (json.JSONDecodeError, KeyError):
                continue  # torn trailing line from a crash mid-write
    return done


def _parseable_fail_to_pass(instance) -> bool:
    """True iff at least one FAIL_TO_PASS entry yields a usable method name."""
    from friction.parsing.patches import parse_test_identifier

    for raw in getattr(instance, "fail_to_pass", []) or []:
        _dotted, method = parse_test_identifier(raw)
        if method:
            return True
    return False


def plan_repo_instances(instances: list, limit: int | None,
                        prefer_parseable: bool = True) -> list:
    """Deterministic build order for one repo's instances.

    Instances with a cleanly-parseable FAIL_TO_PASS come first (they are the
    only ones that can ever map a test endpoint), then instance_id order. At
    most ``limit`` are returned.
    """
    def key(inst):
        parse_rank = 0 if (prefer_parseable and _parseable_fail_to_pass(inst)) else 1
        return (parse_rank, inst.instance_id)

    ordered = sorted(instances, key=key)
    return ordered if limit is None else ordered[:limit]


def _usable(record: dict, arm: str = "arm_b") -> bool:
    """Endpoint mapping succeeded: BOTH a fix site AND a test target mapped."""
    a = record.get(arm, {}) or {}
    return bool(a.get("fix_site_ids")) and bool(a.get("test_target_ids"))


def aggregate_by_repo(records: list[dict]) -> dict[str, dict]:
    """Per-repo rollup: built, usable (arm_b + arm_a), node/edge medians.

    ``usable`` is the number whose type-resolved arm mapped both a fix site and
    a test target -- the figure that decides how many instances the evaluation
    can actually use. Pure over ``records`` so it is unit-testable.
    """
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_repo[r.get("repo", "?")].append(r)

    out: dict[str, dict] = {}
    for repo, recs in sorted(by_repo.items()):
        b_nodes = [r["arm_b"]["nodes"] for r in recs if "arm_b" in r]
        b_edges = [r["arm_b"]["edges"] for r in recs if "arm_b" in r]
        secs = [r.get("seconds", 0.0) for r in recs]
        out[repo] = {
            "built": len(recs),
            "usable_arm_b": sum(_usable(r, "arm_b") for r in recs),
            "usable_arm_a": sum(_usable(r, "arm_a") for r in recs),
            "comparable": sum(bool(r.get("comparable")) for r in recs),
            "median_nodes_arm_b": int(statistics.median(b_nodes)) if b_nodes else 0,
            "median_edges_arm_b": int(statistics.median(b_edges)) if b_edges else 0,
            "wall_seconds": round(sum(secs), 1),
        }
    return out


# --- clone management ------------------------------------------------------

def _throwaway_clone(repo_name: str) -> Path:
    """Create (or reuse) a ``--shared`` throwaway clone of ``data/repos/<name>``.

    ``--shared`` means the working tree is fresh but the object database is the
    reference clone's, so every historical base_commit is reachable without a
    second full download. The reference clone's checkout state is never touched.
    """
    src = REPOS_DIR / repo_name
    if not (src / ".git").exists():
        raise FileNotFoundError(f"reference clone missing: {src}")
    SCRATCH_CLONES.mkdir(parents=True, exist_ok=True)
    dst = SCRATCH_CLONES / repo_name
    if (dst / ".git").exists():
        return dst
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", str(src), str(dst)],
        check=True, capture_output=True,
    )
    return dst


def _drop_throwaway(repo_name: str) -> None:
    shutil.rmtree(SCRATCH_CLONES / repo_name, ignore_errors=True)


# --- import existing django ------------------------------------------------

def import_existing(source_manifest: Path, repo_label: str = "django") -> int:
    """Carry already-built records into the corpus manifest, tagged by repo.

    Skips ids already in the corpus manifest (idempotent). Returns count added.
    """
    if not source_manifest.exists():
        print(f"no source manifest at {source_manifest}", flush=True)
        return 0
    have = completed_ids(MANIFEST)
    added = 0
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    with source_manifest.open(encoding="utf-8") as fh, \
            MANIFEST.open("a", encoding="utf-8") as out:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec["instance_id"] in have:
                continue
            rec.setdefault("repo", repo_label)
            rec["source"] = "carried"
            rec.setdefault("covers", "static-only")
            out.write(json.dumps(rec) + "\n")
            out.flush()
            added += 1
    print(f"imported {added} carried {repo_label} records into corpus", flush=True)
    return added


# --- build loop ------------------------------------------------------------

def _log_attempt(rec: dict) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    with ATTEMPTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


def build_repo(repo_full: str, instances: list, limit: int | None, probe: int,
               idx_start: int) -> int:
    """Build one repo's instances against a throwaway shared clone.

    Returns the number of instances successfully built this run. Aborts the
    repo early if the first ``probe`` attempted builds all fail (systematic
    failure: bad scip index, endpoints never resolving, etc.).
    """
    from friction import arms

    short = repo_short(repo_full)
    done = completed_ids(MANIFEST)
    todo = [i for i in plan_repo_instances(instances, limit) if i.instance_id not in done]
    print(f"[{time.strftime('%H:%M:%S')}] {short}: {len(done & {i.instance_id for i in instances})} "
          f"done, {len(todo)} to build (probe={probe})", flush=True)
    if not todo:
        return 0

    clone = _throwaway_clone(short)
    built = 0
    attempted = 0
    consecutive_fail = 0
    try:
        for n, inst in enumerate(todo, 1):
            idx = idx_start + n  # unique-ish band per instance in the corpus
            print(f"[{time.strftime('%H:%M:%S')}] {short} ({n}/{len(todo)}) "
                  f"building {inst.instance_id} ...", flush=True)
            t0 = time.perf_counter()
            try:
                rec = arms.build_instance(inst, clone, idx, CORPUS_ARMS)
            except Exception:  # noqa: BLE001 - record and keep going
                secs = round(time.perf_counter() - t0, 1)
                err = traceback.format_exc().splitlines()[-1][:300]
                _log_attempt({"instance_id": inst.instance_id, "repo": short,
                              "status": "error", "error": err, "seconds": secs})
                print(f"[{time.strftime('%H:%M:%S')}] {short} {inst.instance_id} "
                      f"FAILED ({secs}s): {err}", flush=True)
                attempted += 1
                consecutive_fail += 1
                if attempted <= probe and consecutive_fail >= probe:
                    print(f"[{time.strftime('%H:%M:%S')}] {short}: first {probe} "
                          f"builds all failed -- abandoning repo (systematic).",
                          flush=True)
                    break
                continue

            attempted += 1
            consecutive_fail = 0
            rec["repo"] = short
            rec["source"] = "built"
            rec["covers"] = "static-only"
            # Drop the 66 MB SCIP index; the loader reads the NDJSON arms.
            scip = CORPUS_ARMS / inst.instance_id / "index.scip"
            scip.unlink(missing_ok=True)
            with MANIFEST.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
            _log_attempt({"instance_id": inst.instance_id, "repo": short,
                          "status": "built", "seconds": rec.get("seconds"),
                          "usable_arm_b": _usable(rec, "arm_b")})
            b = rec["arm_b"]
            print(f"[{time.strftime('%H:%M:%S')}] {short} DONE {inst.instance_id} "
                  f"{rec['seconds']}s B[n={b['nodes']} e={b['edges']} "
                  f"fix={len(b['fix_site_ids'])} test={len(b['test_target_ids'])}] "
                  f"usable={_usable(rec)}", flush=True)
            built += 1
    finally:
        _drop_throwaway(short)
    return built


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repos", nargs="*", default=None,
                    help="Repo short names to build (default: auto-pick 3 "
                         "largest non-django).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max instances PER REPO to build this run.")
    ap.add_argument("--probe", type=int, default=5,
                    help="Abandon a repo if its first PROBE builds all fail.")
    ap.add_argument("--import-existing", action="store_true",
                    help="Carry the existing 50 django records into the corpus "
                         "manifest, then continue.")
    ap.add_argument("--k", type=int, default=3,
                    help="How many non-django repos to auto-pick.")
    args = ap.parse_args()

    CORPUS_ARMS.mkdir(parents=True, exist_ok=True)

    if args.import_existing:
        import_existing(EXISTING_DJANGO_MANIFEST, "django")

    print(f"[{time.strftime('%H:%M:%S')}] loading SWE-bench Verified ...", flush=True)
    from friction.swebench import load_instances
    all_insts = load_instances()
    counts = Counter(i.repo for i in all_insts)

    if args.repos:
        targets = args.repos
    else:
        targets = select_target_repos(dict(counts), exclude={"django"}, k=args.k)
    print(f"[{time.strftime('%H:%M:%S')}] target repos: {targets}", flush=True)

    by_repo: dict[str, list] = defaultdict(list)
    for i in all_insts:
        by_repo[repo_short(i.repo)].append(i)

    run_t0 = time.perf_counter()
    total_built = 0
    # Global idx offset per repo keeps corpus id bands from overlapping.
    idx_base = 1000
    for r_i, short in enumerate(targets):
        insts = by_repo.get(short, [])
        if not insts:
            print(f"[{time.strftime('%H:%M:%S')}] {short}: no instances, skipping",
                  flush=True)
            continue
        full = insts[0].repo
        built = build_repo(full, insts, args.limit, args.probe,
                           idx_start=idx_base + r_i * 1000)
        total_built += built

    total = len(completed_ids(MANIFEST))
    wall = time.perf_counter() - run_t0
    print(f"[{time.strftime('%H:%M:%S')}] run complete: +{total_built} built this "
          f"run, {total} in corpus total, {wall / 60:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

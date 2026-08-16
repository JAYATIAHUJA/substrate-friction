#!/usr/bin/env bash
# Sequential corpus build: fast repos first so the corpus grows quickly, then
# a capped slice of slow sympy. Each phase is resumable (manifest-skip), so a
# restart continues where it left off. Ordering matters: if the run is stopped
# early, the cheap repos are already done and only sympy is truncated.
set -u
cd /Users/cruzer/Desktop/Hackathon/substrate-friction

echo "=== PHASE 1: sphinx (all, ~37s each) $(date +%H:%M:%S) ==="
uv run python scripts/build_corpus3.py --repos sphinx --limit 44 --probe 4

echo "=== PHASE 2: matplotlib (all, ~4min each) $(date +%H:%M:%S) ==="
uv run python scripts/build_corpus3.py --repos matplotlib --limit 34 --probe 4

echo "=== PHASE 3: sympy (capped, ~12min each) $(date +%H:%M:%S) ==="
uv run python scripts/build_corpus3.py --repos sympy --limit 35 --probe 3

echo "=== BUILD DRIVER DONE $(date +%H:%M:%S) ==="

"""Common Cause: which structural element lies on the most independent bug paths.

Aviation crash investigation, for code. Investigators do not fix individual
crashes; they find the latent condition shared across many. This makes no
predictive claim — it measures something that demonstrably exists.

The query is the same `algo.MSpaths` call as the friction metric, with issue
entry points as sources and fix sites as targets.
"""

from __future__ import annotations

import random
from collections import Counter


def tally(paths_by_instance: dict[str, list[list[int]]]) -> dict[int, int]:
    """Count instances — not paths — whose paths pass through each node."""
    counts: Counter[int] = Counter()
    for paths in paths_by_instance.values():
        seen: set[int] = set()
        for path in paths:
            seen.update(path[1:-1])
        counts.update(seen)
    return dict(counts)


def rank(tallies: dict[int, int], top_n: int = 10) -> list[tuple[int, int]]:
    return sorted(tallies.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]


def validate(train_paths: dict[str, list[list[int]]],
             held_out_paths: dict[str, list[list[int]]],
             top_n: int = 5) -> dict[str, float]:
    """Do the training set's top nodes appear on held-out incident paths?"""
    top = {node for node, _ in rank(tally(train_paths), top_n)}
    if not held_out_paths:
        return {"held_out_hit_rate": 0.0, "instances": 0.0}

    hits = 0
    for paths in held_out_paths.values():
        nodes: set[int] = set()
        for path in paths:
            nodes.update(path[1:-1])
        if nodes & top:
            hits += 1
    return {
        "held_out_hit_rate": hits / len(held_out_paths),
        "instances": float(len(held_out_paths)),
    }


def bootstrap_ci(paths_by_instance: dict[str, list[list[int]]], node_id: int,
                 trials: int = 1000, seed: int = 0) -> tuple[float, float]:
    """With only dozens of instances the top node can be unstable. Report an
    interval, not a single name."""
    keys = list(paths_by_instance)
    if not keys:
        return 0.0, 0.0
    rng = random.Random(seed)
    rates: list[float] = []
    for _ in range(trials):
        sample = [rng.choice(keys) for _ in keys]
        counts = tally({f"{k}#{i}": paths_by_instance[k]
                        for i, k in enumerate(sample)})
        rates.append(counts.get(node_id, 0) / len(sample))
    rates.sort()
    return rates[int(0.025 * len(rates))], rates[int(0.975 * len(rates)) - 1]

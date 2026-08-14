"""The friction metric: six components, then freeze.

Every component is derived from the path set the engine returned. Normalisation
is min-max across the instance set and happens here because the engine has no
`min` or `max` aggregate.
"""

from __future__ import annotations

from dataclasses import dataclass

from friction.paths import PathSet

EQUAL_WEIGHTS: dict[str, float] = {
    "f1": 1 / 6, "f2": 1 / 6, "f3": 1 / 6,
    "f4": 1 / 6, "f5": 1 / 6, "f6": 1 / 6,
}

COMPONENT_NAMES = ("f1", "f2", "f3", "f4", "f5", "f6")


@dataclass(frozen=True)
class Components:
    f1: float
    f2: float
    f3: float
    f4: float
    f5: float
    f6: float

    def as_dict(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in COMPONENT_NAMES}


def raw_components(path_set: PathSet, fix_ids: list[int], test_ids: list[int],
                   fan_in_count: int) -> Components:
    paths = path_set.paths
    if not paths:
        return Components(0.0, 0.0, 0.0, 0.0, 0.0, float(fan_in_count) if fan_in_count else 0.0)

    pairs = max(len(fix_ids) * len(test_ids), 1)
    f1 = len(paths) / pairs

    f2 = sum(len(p) - 1 for p in paths) / len(paths)

    intermediates: list[int] = []
    for path in paths:
        intermediates.extend(path[1:-1])
    distinct = len(set(intermediates))
    f3 = float(distinct)

    f4 = distinct / len(intermediates) if intermediates else 0.0

    cyclic = sum(1 for p in paths if len(set(p)) != len(p))
    f5 = cyclic / len(paths)

    f6 = float(fan_in_count)

    return Components(f1, f2, f3, f4, f5, f6)


def fit_bounds(all_components: list[Components]) -> dict[str, tuple[float, float]]:
    """Min-max bounds per component, fit on exactly the instances passed in.

    Pass only the training split here when evaluating a fitted model, so the
    held-out split's scaling never depends on its own extremes.
    """
    bounds: dict[str, tuple[float, float]] = {}
    for name in COMPONENT_NAMES:
        values = [getattr(c, name) for c in all_components]
        bounds[name] = (min(values), max(values)) if values else (0.0, 0.0)
    return bounds


def normalise_with_bounds(components: list[Components],
                          bounds: dict[str, tuple[float, float]]) -> list[Components]:
    """Scale `components` using externally-supplied bounds. Held-out values that
    fall outside the training range map outside [0, 1] on purpose — clamping
    would hide train/test distribution shift."""
    out: list[Components] = []
    for c in components:
        scaled: dict[str, float] = {}
        for name in COMPONENT_NAMES:
            low, high = bounds[name]
            span = high - low
            scaled[name] = 0.0 if span == 0 else (getattr(c, name) - low) / span
        out.append(Components(**scaled))
    return out


def normalise(all_components: list[Components]) -> list[Components]:
    """Full-set min-max scaling for the equal-weights headline. Unaffected by
    the train/test split; the fitted path uses fit_bounds/normalise_with_bounds."""
    if not all_components:
        return []
    return normalise_with_bounds(all_components, fit_bounds(all_components))


def score(components: Components, weights: dict[str, float]) -> float:
    values = components.as_dict()
    # f4 is the intermediate-diversity (divergence) ratio: high means paths
    # spread through distinct nodes, low means they converge on shared ones.
    # Invert it so convergence -- paths funnelling through common nodes --
    # drives friction upward.
    values["f4"] = 1.0 - values["f4"]
    total = sum(weights[name] * values[name] for name in COMPONENT_NAMES)
    denominator = sum(weights.values()) or 1.0
    return max(0.0, min(1.0, total / denominator))


def band(value: float) -> str:
    if value < 0.34:
        return "LOW"
    if value < 0.67:
        return "MEDIUM"
    return "HIGH"

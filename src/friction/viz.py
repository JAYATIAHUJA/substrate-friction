"""Render the subgraph between fix sites and tests.

Two pictures, two stories.

`render_pair` is the classic contrast: a low-friction instance's fix->test
subgraph beside a high-friction one. High-friction instances look like a
hairball; low-friction ones look like a clean line. That contrast is the demo.

`render_truncation` is the more important one. For a single instance it draws,
side by side over the IDENTICAL edge set, the paths the engine returned under its
``pathCount`` cap and the paths a full enumeration finds. The engine sees a sliver
(cohort fidelity recall 0.0264: 1021 returned of ~38720 real). That picture is why
the engine-computed AUC 0.780 was an artifact of truncation, not a real signal.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from friction.paths import PathSet

COLOURS = {"fix": "#2563eb", "test": "#16a34a", "intermediate": "#9ca3af"}


def build_subgraph(path_set: PathSet, fix_ids: list[int], test_ids: list[int]) -> nx.Graph:
    """Collapse a PathSet into an undirected graph.

    Every node carries ``role`` in {"fix", "test", "intermediate"} and every edge
    carries ``participation``: the number of paths in the set that traverse it.
    An empty path set yields an empty graph.
    """
    graph = nx.Graph()
    fix, test = set(fix_ids), set(test_ids)

    for path in path_set.paths:
        for node in path:
            if not graph.has_node(node):
                role = "fix" if node in fix else "test" if node in test else "intermediate"
                graph.add_node(node, role=role)
        for a, b in zip(path, path[1:]):
            if graph.has_edge(a, b):
                graph[a][b]["participation"] += 1
            else:
                graph.add_edge(a, b, participation=1)
    return graph


def _endpoints(path_set: PathSet) -> tuple[list[int], list[int]]:
    """Fix/test seed ids read straight off the path set's own endpoints.

    Every path runs fix-site -> ... -> test-target, so the first node of each path
    is a fix site and the last is a test target. Reading them off the paths keeps
    the picture self-consistent even when explicit seed lists are not to hand.
    """
    fix = {p[0] for p in path_set.paths if p}
    test = {p[-1] for p in path_set.paths if p}
    return sorted(fix), sorted(test)


def _draw(graph: nx.Graph, pos, ax, *, node_size: int = 110,
          edge_alpha: float = 0.55, min_width: float = 0.6,
          max_width: float = 4.0) -> None:
    """Draw ``graph`` at ``pos``. Edge width encodes ``participation`` scaled
    RELATIVE to this graph's own maximum, so a set with thousands of paths
    through one edge stays legible instead of collapsing into an ink blot; the
    within-panel ordering (which edges carry more paths) is preserved."""
    if not graph.number_of_nodes():
        return
    colours = [COLOURS[graph.nodes[n]["role"]] for n in graph.nodes]
    parts = [graph[a][b]["participation"] for a, b in graph.edges]
    top = max(parts) if parts else 1
    span = max_width - min_width
    widths = [min_width + (p / top) * span for p in parts]
    nx.draw_networkx_edges(graph, pos, ax=ax, width=widths, alpha=edge_alpha)
    nx.draw_networkx_nodes(graph, pos, ax=ax, node_color=colours,
                           node_size=node_size, linewidths=0.0)


def _legend(ax) -> None:
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="o", color="none", label="fix site",
               markerfacecolor=COLOURS["fix"], markersize=9),
        Line2D([0], [0], marker="o", color="none", label="test target",
               markerfacecolor=COLOURS["test"], markersize=9),
        Line2D([0], [0], marker="o", color="none", label="intermediate",
               markerfacecolor=COLOURS["intermediate"], markersize=9),
    ]
    ax.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
              fontsize=10, bbox_to_anchor=(0.5, -0.06))


def render_pair(low: PathSet, high: PathSet, out_path: Path,
                labels: tuple[str, str]) -> Path:
    """Two panels: a low-friction fix->test subgraph beside a high-friction one.

    Fix sites blue, tests green, intermediates grey; edge width scales with the
    number of paths that traverse the edge. Node count / edge count are appended
    to each panel title so the density difference is quantified, not just felt.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.4))
    for i, (ax, path_set, label) in enumerate(zip(axes, (low, high), labels)):
        fix_ids, test_ids = _endpoints(path_set)
        graph = build_subgraph(path_set, fix_ids, test_ids)
        if graph.number_of_nodes():
            pos = nx.spring_layout(graph, seed=7, k=0.6)
            _draw(graph, pos, ax)
        ax.set_title(
            f"{label}\n{graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges, {len(path_set.paths)} paths",
            fontsize=13)
        ax.axis("off")
        if i == 0:
            _legend(ax)

    fig.suptitle("fix-site → test-target subgraph: low friction vs high friction",
                 fontsize=15, y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_truncation(engine: PathSet, full: PathSet, out_path: Path,
                      labels: tuple[str, str],
                      fix_ids: list[int] | None = None,
                      test_ids: list[int] | None = None) -> Path:
    """Side-by-side over ONE instance and the IDENTICAL edge set: the paths the
    engine returned under its pathCount cap, and the paths full enumeration finds.

    Both panels share a single layout computed on the full graph, so the engine
    panel is literally the same drawing with most of it removed. The full graph is
    drawn as a faint ghost behind the engine panel, so the returned paths read as
    the sliver of the whole that they are. Real path counts label both panels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fix_ids is None or test_ids is None:
        f, t = _endpoints(full)
        fix_ids = fix_ids if fix_ids is not None else f
        test_ids = test_ids if test_ids is not None else t

    engine_g = build_subgraph(engine, fix_ids, test_ids)
    full_g = build_subgraph(full, fix_ids, test_ids)

    # One layout for both panels, computed on the full graph (the engine's nodes
    # are a subset of it, so the engine panel lands in the same coordinate frame).
    pos = nx.spring_layout(full_g, seed=7, k=0.5) if full_g.number_of_nodes() else {}

    def _share_limits(ax):
        if not pos:
            return
        xs = [p[0] for p in pos.values()]
        ys = [p[1] for p in pos.values()]
        pad = 0.08
        ax.set_xlim(min(xs) - pad, max(xs) + pad)
        ax.set_ylim(min(ys) - pad, max(ys) + pad)

    frac = (len(engine.paths) / len(full.paths) * 100.0) if full.paths else 0.0

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.4))

    # Left: full graph as a faint ghost, engine's returned paths solid on top.
    ax = axes[0]
    if full_g.number_of_nodes():
        nx.draw_networkx_edges(full_g, pos, ax=ax, width=0.4, alpha=0.12,
                               edge_color="#9ca3af")
        nx.draw_networkx_nodes(full_g, pos, ax=ax, node_color="#e5e7eb",
                               node_size=18, linewidths=0.0)
    _draw(engine_g, pos, ax, node_size=130, edge_alpha=0.9,
          min_width=1.0, max_width=4.0)
    ax.set_title(
        f"{labels[0]}\nengine returned {len(engine.paths)} paths "
        f"({engine_g.number_of_nodes()} nodes, {engine_g.number_of_edges()} edges)",
        fontsize=13)
    ax.axis("off")
    _share_limits(ax)
    _legend(ax)

    # Right: the full enumeration over the identical edge set.
    ax = axes[1]
    _draw(full_g, pos, ax, node_size=26, edge_alpha=0.4,
          min_width=0.3, max_width=1.6)
    ax.set_title(
        f"{labels[1]}\nfull enumeration {len(full.paths)} paths "
        f"({full_g.number_of_nodes()} nodes, {full_g.number_of_edges()} edges)",
        fontsize=13)
    ax.axis("off")
    _share_limits(ax)

    fig.suptitle(
        f"Truncated path sampling sees {frac:.1f}% of the paths — "
        "same instance, same edge set",
        fontsize=15, y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------
# Regenerate the two committed demo figures from the run caches. Reproducible
# via ``python -m friction.viz``. Instance choices and their friction values are
# the real, measured ones (reference-derived, no pathCount cap) — see the module
# tests and docs/plots/README.md for the reasoning.
# --------------------------------------------------------------------------

_ENGINE_CACHE = Path("data/instances/engine_cache.json")
_REF_CACHE = Path("data/instances/ref_cache.json")
_PLOTS = Path("docs/plots")

# Figure A: clearest low-vs-high contrast among uncapped instances.
_PAIR_LOW = "django__django-11133"
_PAIR_HIGH = "django__django-11292"
# Figure B: the truncation artifact, on an uncapped instance where the gap is
# unmistakable (engine 20 of 7573 full-enumeration paths over the same edges).
_TRUNC = "django__django-11740"


def _reference_friction() -> dict[str, float]:
    """Real reference-derived friction score per endpoint-bearing instance, using
    the identical scoring the harness reports (raw_components -> full-set min-max
    normalise -> equal-weights score). Reads only the committed caches."""
    import json

    from friction.metric import EQUAL_WEIGHTS, normalise, raw_components, score

    engine = json.loads(_ENGINE_CACHE.read_text())
    ref = json.loads(_REF_CACHE.read_text())
    ids = list(ref)
    raws, fans = [], []
    for iid in ids:
        e = engine.get(iid, {})
        fix = list(e.get("fix_ids") or [])
        test = list(e.get("test_ids") or [])
        fan = int(e.get("engine_fan_in") or 0)
        ps = PathSet([list(p) for p in ref[iid]["sub_ref_paths"]], [], "", 0.0, False)
        raws.append(raw_components(ps, fix, test, fan))
        fans.append(fan)
    scaled = normalise(raws)
    return {iid: score(c, EQUAL_WEIGHTS) for iid, c in zip(ids, scaled)}


def _cache_path_set(record: dict, key: str) -> PathSet:
    paths = [list(p) for p in record.get(key, [])]
    return PathSet(paths, [float(len(p) - 1) for p in paths], "", 0.0, False)


def generate_demo_figures() -> tuple[Path, Path]:
    """Write docs/plots/pair.png and docs/plots/truncation.png from the caches."""
    import json

    engine = json.loads(_ENGINE_CACHE.read_text())
    ref = json.loads(_REF_CACHE.read_text())
    friction = _reference_friction()

    low = _cache_path_set(ref[_PAIR_LOW], "sub_ref_paths")
    high = _cache_path_set(ref[_PAIR_HIGH], "sub_ref_paths")
    pair_out = render_pair(
        low, high, _PLOTS / "pair.png",
        labels=(f"{_PAIR_LOW[8:]}  ·  friction {friction[_PAIR_LOW]:.3f}",
                f"{_PAIR_HIGH[8:]}  ·  friction {friction[_PAIR_HIGH]:.3f}"))

    e = engine[_TRUNC]
    engine_ps = _cache_path_set(e, "engine_paths")
    full_ps = _cache_path_set(ref[_TRUNC], "sub_ref_paths")
    trunc_out = render_truncation(
        engine_ps, full_ps, _PLOTS / "truncation.png",
        labels=("engine, pathCount=20 cap", "full enumeration, same edge set"),
        fix_ids=list(e.get("fix_ids") or []),
        test_ids=list(e.get("test_ids") or []))
    return pair_out, trunc_out


if __name__ == "__main__":
    p, t = generate_demo_figures()
    print(f"wrote {p}")
    print(f"wrote {t}")

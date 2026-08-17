"""The figures. What name matching costs, drawn three ways.

The three v2 figures — the deliverables of this module — are the two-arm ones,
regenerable from the committed caches via ``python -m friction.viz``:

* :func:`render_arms` (docs/plots/arms.png) — THE MONEY SHOT. One instance, two
  panels over one shared layout: the fix-site call neighbourhood as arm A
  (name-matched) sees it, beside the same neighbourhood as arm B (type-resolved)
  sees it. Arm A's edges are coloured UNCONFIRMED (red) vs CONFIRMED-by-arm-B
  (grey), the confirmed/unconfirmed split decided by ``friction.identity``'s join.
  The red mass is the finding.
* :func:`render_offenders` (docs/plots/offenders.png) — the worst unconfirmed
  targets (``extend`` 139, ``lower`` 125, ``cursor`` 54, …) as a bar chart, with
  ``cursor`` annotated as the honest counter-example: there arm A was right and
  pyright under-reported, so precision is a ceiling in both directions.
* :func:`render_density` (docs/plots/density.png) — the density paradox: per
  instance, arm A vs arm B edge counts with engine-answerability overlaid. Arm B
  is ~4x denser and is the arm the engine cannot traverse (answered 3/28 vs
  arm A's 18/28). The graph worth having is the one hardest to query.

The two v1 figures remain for the historical record. `render_pair` is the classic
contrast (a low-friction fix->test subgraph beside a high-friction one).
`render_truncation` draws, over the IDENTICAL edge set, the paths the engine
returned under its ``pathCount`` cap beside a full enumeration.
"""

from __future__ import annotations

import gzip
import json
import re
import statistics
from pathlib import Path

import networkx as nx

from friction.arms import ARM_A_BASE, ARM_B_BASE
from friction.paths import PathSet

COLOURS = {"fix": "#2563eb", "test": "#16a34a", "intermediate": "#9ca3af"}

# Two-arm figure palette. Grey = arm B confirms the arm-A edge; red = arm B does
# not (a name-match artifact OR a pyright under-report — a ceiling, see offenders).
EDGE_CONFIRMED = "#9ca3af"
EDGE_UNCONFIRMED = "#dc2626"
ARM_A_COLOUR = "#2563eb"
ARM_B_COLOUR = "#ea580c"


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
_LATENCY_JSON = Path("docs/latency.json")

# Fallback per-k reachability latency, used ONLY if docs/latency.json is missing
# (it is committed, so this is a clean-clone safety net, not the source of truth).
# These are the mid-source cold numbers from the committed docs/latency.json.
_LATENCY_FALLBACK_REACH = [(1, 8.22), (2, 6.33), (3, 6.38),
                           (4, 7.84), (5, 6.87), (6, 9.88)]
_LATENCY_FALLBACK_ENUM_MS = 14539.21


def load_latency(path: Path = _LATENCY_JSON) -> dict:
    """Read the committed latency measurement (scripts/latency_measure.py).

    viz never touches the engine; it reads the committed docs/latency.json so the
    figure is reproducible from a clean clone with the engine down. Returns the
    mid-source reachability rows, the measured enumeration cost, and the
    busiest-hub context for the caption.
    """
    if path.exists():
        data = json.loads(path.read_text())
        mid = data["reach_count_star"]["mid"]
        hub = data["reach_count_star"]["hub"]
        enum = data["mspaths_enumeration"]["mid_connected_seeds"]
        reach_rows = [(r["k"], r["millis"]) for r in mid["rows"]]
        enum_ms = enum["millis"] if enum.get("answered") \
            else data["timeout_ceiling_millis"]
        return {
            "reach_rows": reach_rows,
            "enum_ms": enum_ms,
            "reach_min": mid["min_millis"], "reach_max": mid["max_millis"],
            "hub_max_ms": hub["max_millis"], "hub_reach_nodes": hub["reach6_nodes"],
            "nodes": data["graph"]["nodes"], "both_degree": data["graph"]["both_degree"],
        }
    return {
        "reach_rows": list(_LATENCY_FALLBACK_REACH),
        "enum_ms": _LATENCY_FALLBACK_ENUM_MS,
        "reach_min": 6.33, "reach_max": 9.88,
        "hub_max_ms": 6505.73, "hub_reach_nodes": 12710,
        "nodes": 34000, "both_degree": 2.9,
    }


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


# ==========================================================================
# TWO-ARM FIGURES — the v2 deliverables. All three regenerate from the caches
# committed under data/instances/arms/ and the docs/graph-delta.md report.
# ==========================================================================

_ARMS_ROOT = Path("data/instances/arms")
_SHIPPED_ROOT = Path("data/shipped/arms")
_MANIFEST = _ARMS_ROOT / "manifest.jsonl"
_PATH_STATS = _ARMS_ROOT / "path_stats.json"
_GRAPH_DELTA = Path("docs/graph-delta.md")
_EVALUATION = Path("docs/evaluation.md")
_VENDOR_CYTOSCAPE = Path("docs/vendor/cytoscape.min.js")

# Half-open id band per arm, from the friction.arms constants. Used to split the
# shipped merged (both-arms) NDJSON back into a single arm's nodes and edges.
_ARM_BANDS = {"arm_a": (ARM_A_BASE, ARM_B_BASE), "arm_b": (ARM_B_BASE, 10**18)}


def _arms_root() -> Path:
    """The arms data root, resolved at call time.

    Prefers the full working corpus under ``data/instances/arms`` (gitignored,
    per-arm plain NDJSON). On a clean clone that directory is absent, so we fall
    back to the committed ``data/shipped/arms`` (merged, gzipped, band-split).
    Resolving here — never at import time against a hardcoded gitignored path —
    is what lets ``python -m friction.viz`` regenerate everything from a fresh
    checkout.
    """
    return _ARMS_ROOT if _MANIFEST.exists() else _SHIPPED_ROOT


def _manifest_path() -> Path:
    return _arms_root() / "manifest.jsonl"


def _path_stats_path() -> Path:
    return _arms_root() / "path_stats.json"

# Figure 1's instance, chosen from real data (see the module tests and findings):
# django__django-11490's fix site is get_combinator_sql, and four of its nine
# unconfirmed edges point at `extend` — the SAME list.extend collision that tops
# the offenders table. The local money shot and the repo-wide bar chart show the
# one finding at two scales.
_ARMS_INSTANCE = "django__django-11490"
_ARMS_DEPTH = 2


# --- arm NDJSON + identity join (index-free, from the committed caches) -----

def _load_arm(instance: str, arm: str) -> tuple[dict[int, str], list[tuple[int, int]]]:
    """Read one arm's committed NDJSON: ``{node_id: qual}`` and ``[(src, dst)]``.

    Handles both on-disk layouts transparently:

    * working corpus — ``<root>/<instance>/<arm>/{nodes,edges}.ndjson`` (plain,
      already one arm per file); and
    * shipped copy — ``<root>/<instance>/{nodes,edges}.ndjson.gz`` (both arms
      merged in one gzipped file), which is split back to a single arm by the
      half-open id band in :data:`_ARM_BANDS`. Edges are intra-band, so filtering
      on the source id selects exactly this arm's edges.
    """
    root = _arms_root()
    per_arm_nodes = root / instance / arm / "nodes.ndjson"

    if per_arm_nodes.exists():
        node_lines = per_arm_nodes.read_text(encoding="utf-8").splitlines()
        edge_lines = (root / instance / arm / "edges.ndjson").read_text(
            encoding="utf-8").splitlines()
        lo, hi = 0, 10**18
    else:
        node_lines = gzip.decompress(
            (root / instance / "nodes.ndjson.gz").read_bytes()).decode(
            "utf-8").splitlines()
        edge_lines = gzip.decompress(
            (root / instance / "edges.ndjson.gz").read_bytes()).decode(
            "utf-8").splitlines()
        lo, hi = _ARM_BANDS[arm]

    nodes: dict[int, str] = {}
    for line in node_lines:
        if line.strip():
            r = json.loads(line)
            if lo <= r["id"] < hi:
                nodes[r["id"]] = r["qual"]
    edges: list[tuple[int, int]] = []
    for line in edge_lines:
        if line.strip():
            r = json.loads(line)
            if lo <= r["src"] < hi:
                edges.append((r["src"], r["dst"]))
    return nodes, edges


def _discover_prefix(b_quals, a_quals) -> str:
    """The constant module prefix scip-python prepends (e.g. ``data.repos.django.``).

    Recovered index-free from the committed arm quals, reproducing what
    ``friction.identity.discover_scip_prefix`` derives from an index. scip-python
    roots project modules at ``<repo-path-as-dots>.<package>``; arm A keeps the
    package as its top segment. So for each arm-B module we strip up to the LAST
    occurrence of the dominant arm-A top package (``django`` sits in the path
    *and* is the package, so the last occurrence is the real boundary) and take
    the most common candidate — stdlib/typeshed nodes that leaked in carry no
    such segment and are ignored, exactly as they are unjoinable and unscored.
    """
    from collections import Counter

    a_tops = Counter(q.split("::")[0].split(".")[0] for q in a_quals)
    if not a_tops:
        return ""
    a_top = a_tops.most_common(1)[0][0]
    cands: Counter = Counter()
    for q in b_quals:
        segs = q.split("::")[0].split(".")
        idxs = [i for i, s in enumerate(segs) if s == a_top]
        if idxs:
            j = idxs[-1]
            cands[".".join(segs[:j]) + "." if j > 0 else ""] += 1
    return cands.most_common(1)[0][0] if cands else ""


def _out_neighbourhood(edges: list[tuple[int, int]], seeds, depth: int) -> set[int]:
    """Node ids within ``depth`` outgoing hops of ``seeds`` (inclusive)."""
    out: dict[int, list[int]] = {}
    for s, d in edges:
        out.setdefault(s, []).append(d)
    reached = set(seeds)
    frontier = set(seeds)
    for _ in range(depth):
        nxt: set[int] = set()
        for u in frontier:
            for v in out.get(u, []):
                if v not in reached:
                    nxt.add(v)
        reached |= nxt
        frontier = nxt
    return reached


def joined_arm_neighbourhood(instance: str, depth: int = _ARMS_DEPTH) -> dict:
    """Build Figure 1's data: the fix-site neighbourhood in both arms, joined.

    Reads only committed caches (the per-arm NDJSON and the manifest). Maps every
    node into ``friction.identity``'s shared ``scope::leaf`` space, restricts to
    the arm-A out-neighbourhood of the mapped fix sites, classifies each arm-A
    edge confirmed/unconfirmed by membership in arm B's joined edge set, and
    returns the same-neighbourhood arm-B edges for the second panel.

    Returns a dict with ``a_edges`` (list of ``(src, dst, confirmed)``),
    ``b_edges`` (list of ``(src, dst)``), ``roles`` (``leaf -> role``),
    ``fix_names`` and count fields. Purely a data function — no plotting.
    """
    from friction.identity import normalize_qualname, normalize_scip

    manifest = {r["instance_id"]: r for r in _read_manifest()}
    rec = manifest[instance]
    a_nodes, a_raw = _load_arm(instance, "arm_a")
    b_nodes, b_raw = _load_arm(instance, "arm_b")
    prefix = _discover_prefix(b_nodes.values(), a_nodes.values())

    a_leaf = {i: normalize_qualname(q) for i, q in a_nodes.items()}
    b_leaf = {i: normalize_scip(q, prefix) for i, q in b_nodes.items()}

    b_set: set[tuple[str, str]] = set()
    for s, d in b_raw:
        ss, dd = b_leaf.get(s), b_leaf.get(d)
        if ss and dd:
            b_set.add((ss, dd))

    fix_ids = [i for i in (rec["arm_a"].get("fix_site_ids") or []) if i in a_nodes]
    test_ids = set(rec["arm_a"].get("test_target_ids") or [])
    nbr = _out_neighbourhood(a_raw, fix_ids, depth)
    nbr_leaves = {a_leaf[i] for i in nbr}

    a_edges: list[tuple[str, str, bool]] = []
    for s, d in a_raw:
        if s in nbr and d in nbr:
            key = (a_leaf[s], a_leaf[d])
            a_edges.append((key[0], key[1], key in b_set))

    b_edges = sorted({(s, d) for (s, d) in b_set
                      if s in nbr_leaves and d in nbr_leaves})

    fix_leaves = {a_leaf[i] for i in fix_ids}
    test_leaves = {a_leaf[i] for i in nbr if i in test_ids}
    roles: dict[str, str] = {}
    for leaf in nbr_leaves | {s for s, _ in b_edges} | {d for _, d in b_edges}:
        roles[leaf] = ("fix" if leaf in fix_leaves
                       else "test" if leaf in test_leaves else "intermediate")

    unconfirmed = sum(1 for _, _, ok in a_edges if not ok)
    return {
        "instance": instance,
        "depth": depth,
        "a_edges": a_edges,
        "b_edges": b_edges,
        "roles": roles,
        "fix_names": sorted(leaf.split("::")[-1] for leaf in fix_leaves),
        "n_a_edges": len(a_edges),
        "n_confirmed": len(a_edges) - unconfirmed,
        "n_unconfirmed": unconfirmed,
        "n_b_edges": len(b_edges),
    }


# --- graph builders (pure, unit-tested) ------------------------------------

def arm_a_graph(a_edges) -> nx.DiGraph:
    """Directed graph of arm-A edges, each carrying ``confirmed: bool``.

    ``a_edges`` is an iterable of ``(src, dst, confirmed)``. Empty input yields an
    empty graph, never an exception.
    """
    g = nx.DiGraph()
    for src, dst, confirmed in a_edges:
        g.add_edge(src, dst, confirmed=bool(confirmed))
    return g


def confirmed_subgraph(g: nx.DiGraph) -> nx.DiGraph:
    """The arm-A edges arm B confirms — always a subset of ``g``'s edges."""
    sub = nx.DiGraph()
    for u, v, data in g.edges(data=True):
        if data.get("confirmed"):
            sub.add_edge(u, v, **data)
    return sub


def _apply_roles(graph, roles: dict) -> list[str]:
    return [COLOURS.get(roles.get(n, "intermediate"), COLOURS["intermediate"])
            for n in graph.nodes]


# --- FIGURE 1: arms.png -----------------------------------------------------

def render_arms(a_edges, b_edges, roles: dict, out_path: Path,
                instance_label: str, counts: dict) -> Path:
    """Two panels over ONE shared layout: arm A (name-matched) beside arm B
    (type-resolved), same fix-site neighbourhood.

    Panel A colours each arm-A edge red where arm B does not confirm it and grey
    where it does — the red mass IS the finding. Panel B draws arm B's edges over
    the identical node positions so the eye compares like with like. Real counts
    label both panels. Empty inputs render empty panels rather than raising.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    a_g = arm_a_graph(a_edges)
    b_g = nx.DiGraph()
    b_g.add_edges_from(b_edges)

    # One layout over the union of both arms' nodes, fixed seed, reused verbatim
    # in both panels so a node sits in the same place on the left and the right.
    union = nx.Graph()
    union.add_nodes_from(a_g.nodes)
    union.add_nodes_from(b_g.nodes)
    union.add_edges_from(a_g.edges())
    union.add_edges_from(b_g.edges())
    pos = nx.spring_layout(union, seed=7, k=0.7) if union.number_of_nodes() else {}

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.6))

    # Left — arm A, edges classified.
    ax = axes[0]
    if a_g.number_of_edges():
        conf = [(u, v) for u, v, d in a_g.edges(data=True) if d["confirmed"]]
        unconf = [(u, v) for u, v, d in a_g.edges(data=True) if not d["confirmed"]]
        nx.draw_networkx_edges(a_g, pos, ax=ax, edgelist=conf, width=1.4,
                               edge_color=EDGE_CONFIRMED, alpha=0.8,
                               arrows=True, arrowsize=8, node_size=150)
        nx.draw_networkx_edges(a_g, pos, ax=ax, edgelist=unconf, width=2.6,
                               edge_color=EDGE_UNCONFIRMED, alpha=0.95,
                               arrows=True, arrowsize=9, node_size=150)
    if a_g.number_of_nodes():
        nx.draw_networkx_nodes(a_g, pos, ax=ax, node_color=_apply_roles(a_g, roles),
                               node_size=150, linewidths=0.0)
    ax.set_title(
        f"arm A · name-matched\n{counts['n_a_edges']} edges — "
        f"{counts['n_unconfirmed']} unconfirmed by arm B (red), "
        f"{counts['n_confirmed']} confirmed (grey)", fontsize=12)
    ax.axis("off")
    _arms_legend(ax)

    # Right — arm B, same positions.
    ax = axes[1]
    if b_g.number_of_edges():
        nx.draw_networkx_edges(b_g, pos, ax=ax, width=1.4,
                               edge_color=EDGE_CONFIRMED, alpha=0.85,
                               arrows=True, arrowsize=8, node_size=150)
    if b_g.number_of_nodes():
        nx.draw_networkx_nodes(b_g, pos, ax=ax, node_color=_apply_roles(b_g, roles),
                               node_size=150, linewidths=0.0)
    ax.set_title(
        f"arm B · type-resolved\n{counts['n_b_edges']} edges over the same "
        "neighbourhood", fontsize=12)
    ax.axis("off")

    fig.suptitle(instance_label, fontsize=15, y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _arms_legend(ax) -> None:
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color=EDGE_UNCONFIRMED, lw=2.6,
               label="arm A edge arm B does NOT confirm"),
        Line2D([0], [0], color=EDGE_CONFIRMED, lw=1.4,
               label="arm A edge arm B confirms"),
        Line2D([0], [0], marker="o", color="none", label="fix site",
               markerfacecolor=COLOURS["fix"], markersize=9),
    ]
    ax.legend(handles=handles, loc="lower center", ncol=1, frameon=False,
              fontsize=9, bbox_to_anchor=(0.5, -0.12))


# --- FIGURE: prune.png — the money shot -------------------------------------

def render_prune(a_edges, roles: dict, out_path: Path,
                 instance_label: str, counts: dict) -> Path:
    """THE MONEY SHOT. One neighbourhood, two panels, ONE shared layout seed.

    Left — the neighbourhood as a name-matched graph sees it: every arm-A edge,
    with the ones type resolution does NOT confirm drawn in red. Right — the same
    neighbourhood after pruning to confirmed edges only; the red edges are gone.
    Node positions are computed once over the full arm-A graph and reused verbatim
    on both panels, so the right panel is literally the left with the red removed.
    The count of pruned edges is annotated. Empty input renders empty panels.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    full_g = arm_a_graph(a_edges)
    conf_g = confirmed_subgraph(full_g)

    # One layout over the full arm-A node set (the confirmed graph is a subset),
    # fixed seed, reused on both panels so a node never moves between them.
    union = nx.Graph()
    union.add_nodes_from(full_g.nodes)
    union.add_edges_from(full_g.edges())
    pos = nx.spring_layout(union, seed=7, k=0.7) if union.number_of_nodes() else {}

    removed = counts.get("n_unconfirmed", 0)
    kept = counts.get("n_confirmed", 0)
    total = counts.get("n_a_edges", removed + kept)

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.6))

    # Left — the name-matched graph, edges classified.
    ax = axes[0]
    if full_g.number_of_edges():
        conf = [(u, v) for u, v, d in full_g.edges(data=True) if d["confirmed"]]
        unconf = [(u, v) for u, v, d in full_g.edges(data=True) if not d["confirmed"]]
        nx.draw_networkx_edges(full_g, pos, ax=ax, edgelist=conf, width=1.4,
                               edge_color=EDGE_CONFIRMED, alpha=0.8,
                               arrows=True, arrowsize=8, node_size=150)
        nx.draw_networkx_edges(full_g, pos, ax=ax, edgelist=unconf, width=2.8,
                               edge_color=EDGE_UNCONFIRMED, alpha=0.95,
                               arrows=True, arrowsize=9, node_size=150)
    if full_g.number_of_nodes():
        nx.draw_networkx_nodes(full_g, pos, ax=ax,
                               node_color=_apply_roles(full_g, roles),
                               node_size=150, linewidths=0.0)
    ax.set_title(
        f"as a name-matched graph sees it\n{total} edges — "
        f"{removed} not confirmed by type resolution (red)", fontsize=12)
    ax.axis("off")
    _prune_legend(ax)

    # Right — pruned to confirmed edges only, identical positions.
    ax = axes[1]
    if conf_g.number_of_edges():
        nx.draw_networkx_edges(conf_g, pos, ax=ax, width=1.4,
                               edge_color=EDGE_CONFIRMED, alpha=0.85,
                               arrows=True, arrowsize=8, node_size=150)
    if full_g.number_of_nodes():
        nx.draw_networkx_nodes(full_g, pos, ax=ax,
                               node_color=_apply_roles(full_g, roles),
                               node_size=150, linewidths=0.0, alpha=0.9)
    ax.set_title(
        f"after pruning to confirmed edges\n{kept} edges kept — "
        f"{removed} pruned", fontsize=12)
    ax.axis("off")
    # Big pruned-count callout in the whitespace under the right panel.
    ax.annotate(f"−{removed} edges", xy=(0.5, -0.02),
                xycoords="axes fraction", ha="center", va="top",
                fontsize=15, color=EDGE_UNCONFIRMED, weight="bold")

    fig.suptitle(instance_label, fontsize=14.5, y=1.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def _prune_legend(ax) -> None:
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], color=EDGE_UNCONFIRMED, lw=2.8,
               label="unconfirmed by type resolution — pruned"),
        Line2D([0], [0], color=EDGE_CONFIRMED, lw=1.4,
               label="confirmed edge — kept"),
        Line2D([0], [0], marker="o", color="none", label="fix site",
               markerfacecolor=COLOURS["fix"], markersize=9),
    ]
    ax.legend(handles=handles, loc="lower center", ncol=1, frameon=False,
              fontsize=9, bbox_to_anchor=(0.5, -0.12))


# --- FIGURE: direction.png — the connectivity finding -----------------------

def render_direction(bars, out_path: Path, n: int) -> Path:
    """The fix<->test connectivity finding as three bars — nobody has published it.

    ``bars`` is ``[(label, pct, note), ...]``; the measured triple is fix->test
    0%, test->fix 55%, undirected 98% (arm B, n=44, bounded at 6 hops). fix->test
    is annotated 0% because code does not call tests; the 55%->98% jump is
    annotated as the pytest fixture / setUp / parametrize closure a static call
    graph cannot see. Empty input renders an empty axes rather than raising.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    bars = list(bars)
    labels = [b[0] for b in bars]
    pcts = [b[1] for b in bars]
    palette = [EDGE_UNCONFIRMED, ARM_A_COLOUR, COLOURS["test"]]
    colours = [palette[i % len(palette)] for i in range(len(bars))]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = list(range(len(bars)))
    ax.bar(x, pcts, color=colours, width=0.6, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("instances connected (%)", fontsize=11)
    ax.set_ylim(0, 108)
    for xi, (pct, note) in enumerate(zip(pcts, [b[2] for b in bars])):
        ax.text(xi, pct + 2, f"{pct:.0f}%", ha="center", va="bottom",
                fontsize=13, weight="bold")
        if note:
            if pct > 20:
                # Enough bar to hold the note in white, inside near the top.
                ax.text(xi, pct - 6, note, ha="center", va="top",
                        fontsize=8.5, color="white", wrap=True)
            else:
                # A short/zero bar — float the note above the value label.
                ax.text(xi, pct + 9, note, ha="center", va="bottom",
                        fontsize=8.5, color="#374151", wrap=True)

    ax.set_title(
        f"Fix-site ↔ test-target connectivity (arm B, n={n}, bounded 6 hops)\n"
        "the directed relation nobody has published", fontsize=13)
    ax.spines[["top", "right"]].set_visible(False)

    fig.text(0.5, -0.02,
             "fix→test is 0% because code does not call its tests. The "
             "55%→98% gap is the pytest fixture / setUp / parametrize "
             "closure\na static call graph never records: the test reaches the "
             "code through dispatch, not a CALLS edge.",
             ha="center", va="top", fontsize=9.5, color="#374151")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --- FIGURE: latency.png — why HydraDB --------------------------------------

def render_latency(reach_rows, enum_ms: float, out_path: Path,
                   enum_label: str = "algo.MSpaths path enumeration",
                   note: str | None = None) -> Path:
    """Bounded in-engine reachability vs path enumeration, on a log scale.

    ``reach_rows`` is ``[(k, ms), ...]`` — the measured ``count(*)`` reachability
    latency at k=1..6 on ONE graph. ``enum_ms`` is the measured ``algo.MSpaths``
    bounded-path enumeration cost on the SAME graph. Both come from
    ``docs/latency.json`` (see ``scripts/latency_measure.py``); nothing here is
    hand-entered. The log y-axis makes the gap legible. ``note`` is an optional
    caption line (used to disclose the busiest-hub operating point). Empty input
    renders an empty axes.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    reach_rows = list(reach_rows)
    ks = [f"k={k}" for k, _ in reach_rows]
    ms = [m for _, m in reach_rows]
    labels = ks + [enum_label]
    values = ms + [enum_ms]
    colours = [ARM_A_COLOUR] * len(ms) + [EDGE_UNCONFIRMED]

    fig, ax = plt.subplots(figsize=(10, 6))
    x = list(range(len(values)))
    ax.bar(x, values, color=colours, width=0.62, zorder=2)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, rotation=15, ha="right")
    ax.set_ylabel("milliseconds (log scale)", fontsize=11)
    for xi, v in zip(x, values):
        ax.text(xi, v * 1.25, f"{v:,.0f} ms", ha="center", va="bottom",
                fontsize=9.5)

    if ms:
        speedup = enum_ms / max(ms)
        ax.annotate(
            f"~{speedup:,.0f}x cheaper at k={reach_rows[len(ms) - 1][0]}\n"
            "same 34k-node django-density graph",
            xy=(len(ms) - 1, ms[-1]), xytext=(len(ms) - 2.4, enum_ms * 0.25),
            fontsize=9, color="#374151",
            arrowprops=dict(arrowstyle="->", color="#374151", lw=1.0))

    title = ("Bounded reachability `count(*)` vs path enumeration\n"
             "one 34k-node django-density graph, both queries measured cold")
    if note:
        title += "\n" + note
    ax.set_title(title, fontsize=12.0)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --- FIGURE 2: offenders.png ------------------------------------------------

def _parse_offenders(path: Path = _GRAPH_DELTA) -> list[tuple[str, int]]:
    """Read the offender table straight from the committed graph-delta report.

    Reading the numbers from docs/graph-delta.md (the pinned, reviewed source)
    rather than recomputing guarantees the figure shows the reported facts
    verbatim — no re-rounding, no drift.
    """
    rows: list[tuple[str, int]] = []
    grab = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## Where arm A"):
            grab = True
            continue
        if grab and line.startswith("## "):
            break
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|", line)
        if grab and m:
            rows.append((m.group(1), int(m.group(2))))
    return rows


def render_offenders(offenders, out_path: Path, top_n: int = 15,
                     counter_example: str = "cursor") -> Path:
    """Horizontal bar chart of the worst unconfirmed arm-A targets.

    ``cursor`` is drawn in a distinct colour and annotated as the honest
    counter-example: there the unconfirmed edges are real ``connection.cursor()``
    calls that pyright declined to resolve, so arm A was right. A chart that only
    showed arm A losing would overclaim; this one states the ceiling both ways.
    Empty input renders an empty axes rather than raising.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = list(offenders)[:top_n]
    names = [n for n, _ in rows]
    counts = [c for _, c in rows]
    # barh puts index 0 at the bottom; reverse so the largest sits at the top.
    y = list(range(len(rows)))[::-1]
    colours = [ARM_B_COLOUR if n == counter_example else EDGE_UNCONFIRMED
               for n in names]

    fig, ax = plt.subplots(figsize=(10, max(4.5, 0.42 * len(rows) + 1.5)))
    ax.barh(y, counts, color=colours, height=0.72)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{n}()" for n in names], fontsize=10)
    for yi, c in zip(y, counts):
        ax.text(c + max(counts) * 0.01, yi, str(c), va="center", fontsize=9)

    if counter_example in names:
        ci = names.index(counter_example)
        yi = y[ci]
        # Land the note in the whitespace right of the short lower bars, so it
        # never overprints the long extend/lower bars one row up.
        ax.annotate(
            "arm A was RIGHT here — real connection.cursor() calls\n"
            "pyright declined to resolve (precision is a ceiling both ways)",
            xy=(counts[ci], yi),
            xytext=(max(counts) * 0.40, yi - 1.7),
            fontsize=8.5, color=ARM_B_COLOUR, va="center",
            arrowprops=dict(arrowstyle="->", color=ARM_B_COLOUR, lw=1.0))

    ax.set_xlabel("unconfirmed arm-A edges (django, whole repo)", fontsize=11)
    ax.set_title("What name matching's unconfirmed edges point at\n"
                 "container-method name collisions — list.extend, str.lower, …",
                 fontsize=13)
    ax.set_xlim(0, max(counts) * 1.18 if counts else 1)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --- FIGURE 3: density.png --------------------------------------------------

def _read_manifest(path: Path | None = None) -> list[dict]:
    path = _manifest_path() if path is None else path
    return [json.loads(line) for line in
            Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def density_rows(manifest_path: Path | None = None,
                 path_stats_path: Path | None = None) -> list[dict]:
    """Per comparable instance: both arms' edge counts and engine-answerability.

    Reads the committed manifest (edge counts) and path_stats (the ``answered``
    flag per arm). Only the 28 ``comparable`` instances — the ones both arms
    mapped endpoints for and the engine actually attempted — are returned.
    """
    manifest_path = _manifest_path() if manifest_path is None else manifest_path
    path_stats_path = _path_stats_path() if path_stats_path is None else path_stats_path
    manifest = {r["instance_id"]: r for r in _read_manifest(manifest_path)}
    per = json.loads(Path(path_stats_path).read_text(encoding="utf-8"))["per_instance"]
    rows: list[dict] = []
    for iid, rec in manifest.items():
        if not rec.get("comparable"):
            continue
        stat = per.get(iid, {})
        rows.append({
            "instance": iid,
            "a_edges": rec["arm_a"]["edges"],
            "b_edges": rec["arm_b"]["edges"],
            "a_answered": bool(stat.get("arm_a", {}).get("answered")),
            "b_answered": bool(stat.get("arm_b", {}).get("answered")),
        })
    return rows


def render_density(rows, out_path: Path) -> Path:
    """The density paradox as a dumbbell chart.

    One row per comparable instance, sorted by arm-B size: a line from arm A's
    edge count to arm B's, a filled marker where the engine answered and a hollow
    one where it timed out or OOM'd. Median lines (median-low, the reported
    figures) anchor each arm. One glance shows arm B far to the right and mostly
    hollow — the richer graph is the one the engine cannot traverse. Empty input
    renders an empty axes rather than raising.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = sorted(rows, key=lambda r: r["b_edges"])
    y = list(range(len(rows)))

    fig, ax = plt.subplots(figsize=(11, max(5, 0.34 * len(rows) + 1.8)))
    for yi, r in zip(y, rows):
        ax.plot([r["a_edges"], r["b_edges"]], [yi, yi],
                color="#d1d5db", lw=1.2, zorder=1)
        for val, answered, colour in (
            (r["a_edges"], r["a_answered"], ARM_A_COLOUR),
            (r["b_edges"], r["b_answered"], ARM_B_COLOUR)):
            ax.scatter([val], [yi], s=46, zorder=2,
                       color=colour if answered else "white",
                       edgecolors=colour, linewidths=1.4)

    a_ans = sum(r["a_answered"] for r in rows)
    b_ans = sum(r["b_answered"] for r in rows)
    if rows:
        a_med = statistics.median_low(r["a_edges"] for r in rows)
        b_med = statistics.median_low(r["b_edges"] for r in rows)
        ax.axvline(a_med, color=ARM_A_COLOUR, ls="--", lw=1.0, alpha=0.7)
        ax.axvline(b_med, color=ARM_B_COLOUR, ls="--", lw=1.0, alpha=0.7)
        ax.text(a_med, len(rows) - 0.2, f"arm A median {a_med:,}",
                color=ARM_A_COLOUR, fontsize=8.5, ha="right", rotation=90, va="top")
        ax.text(b_med, len(rows) - 0.2, f"arm B median {b_med:,}",
                color=ARM_B_COLOUR, fontsize=8.5, ha="right", rotation=90, va="top")

    ax.set_yticks(y)
    ax.set_yticklabels([r["instance"].replace("django__django-", "#") for r in rows],
                       fontsize=8)
    ax.set_xlabel("call-graph edges", fontsize=11)
    ax.set_title(
        "The density paradox: arm B is ~4x denser and the engine can't traverse it\n"
        f"engine answered — arm A {a_ans}/{len(rows)} · arm B {b_ans}/{len(rows)} "
        "(bounded fix→test paths, maxLen 6)", fontsize=12.5)

    from matplotlib.lines import Line2D
    legend = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=ARM_A_COLOUR,
               markeredgecolor=ARM_A_COLOUR, markersize=8, label="arm A (name-matched)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=ARM_B_COLOUR,
               markeredgecolor=ARM_B_COLOUR, markersize=8, label="arm B (type-resolved)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white",
               markeredgecolor="#6b7280", markersize=8, label="engine did NOT answer"),
    ]
    ax.legend(handles=legend, loc="lower right", frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# --- FIGURE: day5-verdict.png — the thesis is dead --------------------------

def _parse_verdict(path: Path = _EVALUATION) -> dict:
    """Read the held-out verdict numbers straight from the committed evaluation.

    Everything the figure draws is parsed VERBATIM from docs/evaluation.md — the
    same discipline as :func:`_parse_offenders` reading docs/graph-delta.md — so
    the figure can never drift from the reviewed report or silently re-round a
    number. Returns a dict with:

    * ``per_repo``    — ``[(repo, n, auc | None)]`` from the leave-one-repo-out
      table, in document order; ``sympy``'s AUC is ``None`` (marked ``n/a`` in the
      table, one class only).
    * ``pooled_features`` / ``pooled_patch_lines`` — the pooled held-out AUCs.
    * ``insample_feature`` / ``insample_baseline`` — ``(name, auc)`` for the
      in-sample best feature and best baseline (kept distinct so the figure can
      label them unmistakably as NOT held-out).
    * ``delong_z`` / ``delong_p``, ``boot_dauc`` / ``boot_ci`` — the significance.
    * ``n`` / ``failed`` / ``resolved`` — the class balance.

    Any field the doc does not yield is returned as ``None`` (or an empty list),
    never a fabricated value.
    """
    text = Path(path).read_text(encoding="utf-8")

    # Leave-one-repo-out table: scope to that section, then read its rows.
    per_repo: list[tuple[str, int, float | None]] = []
    section = ""
    grab = False
    for line in text.splitlines():
        if line.startswith("## Leave-one-repo-out"):
            grab = True
            continue
        if grab and line.startswith("## "):
            break
        if grab:
            section += line + "\n"
    row = re.compile(r"^\|\s*([a-z][a-z0-9_]*)\s*\|\s*(\d+)\s*\|\s*(n/a|[\d.]+)\s*\|",
                     re.MULTILINE)
    for m in row.finditer(section):
        auc = None if m.group(3) == "n/a" else float(m.group(3))
        per_repo.append((m.group(1), int(m.group(2)), auc))

    def _f(pattern: str) -> float | None:
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    pooled_features = _f(r"Pooled held-out AUC \(features\):\s*([\d.]+)")
    pooled_patch = _f(r"alone pooled \*\*([\d.]+)\*\*")

    def _named(pattern: str) -> tuple[str, float] | None:
        m = re.search(pattern, text)
        return (m.group(1), float(m.group(2))) if m else None

    insample_feature = _named(r"\*\*Best feature:\*\*\s*`([^`]+)`\s*at\s*(\d+\.\d+)")
    insample_baseline = _named(r"\*\*Best baseline:\*\*\s*`([^`]+)`\s*at\s*(\d+\.\d+)")

    delong = re.search(r"z = (-?[\d.]+),\s*p = ([\d.]+)", text)
    boot = re.search(r"\|\s*`fanin`\s*\|\s*(-?[\d.]+)\s*\|\s*(\[[^\]]+\])\s*\|", text)
    balance = re.search(r"n=(\d+),\s*failed=(\d+),\s*resolved=(\d+)", text)

    return {
        "per_repo": per_repo,
        "pooled_features": pooled_features,
        "pooled_patch_lines": pooled_patch,
        "insample_feature": insample_feature,
        "insample_baseline": insample_baseline,
        "delong_z": float(delong.group(1)) if delong else None,
        "delong_p": float(delong.group(2)) if delong else None,
        "boot_dauc": float(boot.group(1)) if boot else None,
        "boot_ci": boot.group(2) if boot else None,
        "n": int(balance.group(1)) if balance else None,
        "failed": int(balance.group(2)) if balance else None,
        "resolved": int(balance.group(3)) if balance else None,
    }


# Dark social-card palette. Red = the dead metric (at/below chance); blue = the
# baseline that beat it; grey = the chance reference. Chosen honestly: the
# failing result is not dressed up, and the winning baseline is not a triumph.
_V_BG = "#0d1117"
_V_INK = "#e6edf5"
_V_MUTED = "#8b949e"
_V_DIM = "#586069"
_V_GRID = "#21262d"
_V_CHANCE = "#768390"
_V_RED = "#f85149"
_V_BLUE = "#58a6ff"
_V_SLATE = "#7d8590"


def render_verdict(data: dict, out_path: Path) -> Path:
    """The build-in-public obituary figure: docs/plots/day5-verdict.png.

    One wide dark card that reads at a glance and needs no caption:

    * every repo's leave-one-repo-out held-out AUC as a dot, sized by that repo's
      n (so the small-n repos that scatter high are visibly the least trustworthy),
      most of them landing on or below the 0.5 chance line;
    * the pooled contrast drawn as two full-height rules — the friction features
      at 0.483 (red, sitting on chance) and ``patch_lines`` alone at 0.628 (blue);
    * the chance line at 0.5, dashed and labelled.

    ``sympy`` is shown as an explicit ``n/a`` row (0 failures, single class), never
    dropped. In-sample numbers, if present, are printed in the footer LABELLED as
    not-held-out, so they can never be mistaken for the held-out result. Empty or
    partial input renders a card rather than raising.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    per_repo = list(data.get("per_repo") or [])
    pooled_f = data.get("pooled_features")
    pooled_p = data.get("pooled_patch_lines")

    valued = [(r, n, a) for (r, n, a) in per_repo if a is not None]
    na = [(r, n) for (r, n, a) in per_repo if a is None]
    valued.sort(key=lambda t: t[2], reverse=True)   # best AUC on top

    # Combined display order: valued repos (desc), then the n/a rows at the bottom.
    rows = valued + [(r, n, None) for (r, n) in na]
    n_rows = len(rows)
    ypos = list(range(n_rows))[::-1]                 # first row highest → at top

    fig = plt.figure(figsize=(12, 6.75), dpi=200)
    fig.patch.set_facecolor(_V_BG)
    ax = fig.add_axes([0.15, 0.17, 0.81, 0.52])
    ax.set_facecolor(_V_BG)

    x_lo, x_hi = 0.40, 0.74
    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(-0.9, n_rows - 0.1 + 0.9)

    ax.grid(axis="x", color=_V_GRID, lw=0.9, alpha=0.7, zorder=0)

    # Chance + pooled reference rules.
    ax.axvline(0.5, color=_V_CHANCE, ls=(0, (5, 4)), lw=1.7, zorder=1)
    mid_y = (n_rows - 1) / 2.0
    if pooled_f is not None:
        ax.axvline(pooled_f, color=_V_RED, lw=2.8, zorder=1)
        ax.text(pooled_f - 0.006, mid_y,
                f"friction features\npooled held-out {pooled_f:.3f}",
                rotation=90, va="center", ha="right",
                color=_V_RED, fontsize=11.5, weight="bold", linespacing=1.15)
    if pooled_p is not None:
        ax.axvline(pooled_p, color=_V_BLUE, lw=2.8, zorder=1)
        ax.text(pooled_p + 0.006, mid_y,
                f"patch_lines alone\n{pooled_p:.3f}",
                rotation=90, va="center", ha="left",
                color=_V_BLUE, fontsize=11.5, weight="bold", linespacing=1.15)
    ax.text(0.5, n_rows - 0.1 + 0.55, "chance 0.5", ha="center", va="bottom",
            color=_V_CHANCE, fontsize=11, weight="bold")

    ylabels: list[str] = []
    ycolors: list[str] = []
    for (repo, n, auc), y in zip(rows, ypos):
        ylabels.append(f"{repo}\nn={n}")
        if auc is None:
            ycolors.append(_V_DIM)
            ax.text(0.5, y, "n/a  ·  0 failures (single class)",
                    ha="center", va="center", color=_V_DIM, fontsize=10.5,
                    style="italic", zorder=3)
            continue
        colour = _V_RED if auc <= 0.5 else _V_SLATE
        ycolors.append(colour)
        size = 60 + n * 9.0                          # dot area ∝ repo test-set n
        ax.scatter([auc], [y], s=size, color=colour, edgecolors=_V_BG,
                   linewidths=1.2, zorder=3)
        # Value label placed on the open side so it never sits under the dot.
        off = 0.009 if auc >= 0.5 else -0.009
        ax.text(auc + off, y, f"{auc:.3f}",
                ha="left" if auc >= 0.5 else "right", va="center",
                color=colour, fontsize=12, weight="bold", zorder=4)

    ax.set_yticks(ypos)
    ax.set_yticklabels(ylabels, fontsize=11.5)
    for tick, colour in zip(ax.get_yticklabels(), ycolors):
        tick.set_color(colour)

    ax.set_xticks([0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70])
    ax.tick_params(axis="x", colors=_V_MUTED, labelsize=11)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("leave-one-repo-out held-out AUC   ·   dot area ∝ repo n",
                  color=_V_INK, fontsize=12.5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(_V_MUTED)

    # Headline + subtitle.
    fig.text(0.5, 0.935, "The thesis is dead — its own evaluation killed it",
             ha="center", va="center", color=_V_INK, fontsize=27, weight="bold")
    n = data.get("n")
    failed = data.get("failed")
    resolved = data.get("resolved")
    bal = (f"n={n}, {failed} failed / {resolved} resolved"
           if None not in (n, failed, resolved) else "")
    sub = ("Across 7 repos, held out one at a time, our graph-structure "
           "“friction” features land on the coin-flip line —")
    sub2 = "and below plain patch size. " + (bal + "." if bal else "")
    fig.text(0.5, 0.845, sub, ha="center", va="center",
             color=_V_MUTED, fontsize=13.5)
    fig.text(0.5, 0.805, sub2, ha="center", va="center",
             color=_V_MUTED, fontsize=13.5)

    # Footer: significance, then in-sample numbers LABELLED as not held-out.
    parts = []
    if pooled_f is not None and pooled_p is not None:
        parts.append(f"held-out: features {pooled_f:.3f} vs patch_lines {pooled_p:.3f}")
    if data.get("delong_z") is not None and data.get("delong_p") is not None:
        parts.append(f"DeLong z={data['delong_z']:.3f}, p={data['delong_p']:.3f}")
    if data.get("boot_dauc") is not None and data.get("boot_ci"):
        parts.append(f"bootstrap ΔAUC {data['boot_dauc']:+.3f}, 95% CI {data['boot_ci']}")
    if parts:
        fig.text(0.5, 0.075, "   ·   ".join(parts), ha="center", va="center",
                 color=_V_MUTED, fontsize=10.8)

    feat = data.get("insample_feature")
    base = data.get("insample_baseline")
    if feat and base:
        fig.text(0.5, 0.035,
                 f"in-sample, same instances (NOT held-out): best feature "
                 f"{feat[0]} {feat[1]:.3f} vs {base[0]} {base[1]:.3f}",
                 ha="center", va="center", color=_V_DIM, fontsize=10,
                 style="italic")

    fig.savefig(out_path, facecolor=_V_BG, dpi=200)
    plt.close(fig)
    return out_path


# ==========================================================================
# demo.html — the self-contained interactive money shot (Cytoscape.js)
# ==========================================================================

_DEMO_HTML = Path("docs/demo.html")

# Headline numbers, verbatim from the measured facts. Never re-rounded here.
_HEADLINE = {
    "precision": "0.746",
    "recall": "0.352",
    "jaccard": "0.3143",
    "compared": "5,873",
    "confirmed": "4,381",
    "only_a": "1,492",
    "only_b": "8,064",
}


def build_demo_graph(instance: str = _ARMS_INSTANCE, depth: int = _ARMS_DEPTH) -> dict:
    """Cytoscape-ready elements for ONE real instance's fix-site neighbourhood.

    Reuses :func:`joined_arm_neighbourhood`, so the nodes and the confirmed /
    unconfirmed edge split are exactly what the static arms/prune figures draw —
    no second source of truth. Returns a dict with ``nodes`` (id, label, role),
    ``edges`` (id, source, target, arm, confirmed) covering both arms, and the
    same count fields the figures annotate. Node ids are the shared ``scope::leaf``
    strings; only leaves that participate in an edge are emitted.
    """
    data = joined_arm_neighbourhood(instance, depth)
    roles = data["roles"]

    used: set[str] = set()
    edges: list[dict] = []
    for i, (s, d, ok) in enumerate(data["a_edges"]):
        edges.append({"id": f"a{i}", "source": s, "target": d,
                      "arm": "a", "confirmed": bool(ok)})
        used.update((s, d))
    for i, (s, d) in enumerate(data["b_edges"]):
        edges.append({"id": f"b{i}", "source": s, "target": d,
                      "arm": "b", "confirmed": True})
        used.update((s, d))

    nodes = [{"id": leaf, "label": leaf.split("::")[-1],
              "role": roles.get(leaf, "intermediate")}
             for leaf in sorted(used)]

    return {
        "instance": instance,
        "depth": depth,
        "fix_names": data["fix_names"],
        "nodes": nodes,
        "edges": edges,
        "n_a_edges": data["n_a_edges"],
        "n_confirmed": data["n_confirmed"],
        "n_unconfirmed": data["n_unconfirmed"],
        "n_b_edges": data["n_b_edges"],
    }


def render_demo_html(graph_data: dict, out_path: Path = _DEMO_HTML,
                     vendor_js: Path = _VENDOR_CYTOSCAPE) -> Path:
    """Write a SELF-CONTAINED interactive demo page from real graph data.

    The vendored Cytoscape.js is inlined verbatim into the page (no CDN, no
    ``fetch``), so a judge can open the single file offline from anywhere. The
    graph is embedded as inline JSON — the same neighbourhood the arms/prune
    figures draw. A "Prune wrong edges" button animates removing the unconfirmed
    arm-A edges with a live counter; a toggle swaps between the name-matched
    (arm A) and type-resolved (arm B) views; the header carries the headline
    numbers and the honest caveat that precision is a CEILING (cursor(54) is the
    counter-example). Falls back to a CDN-free notice if the vendored file is
    absent, so the generator never crashes on a partial checkout.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    vendor_js = Path(vendor_js)
    cyto_src = (vendor_js.read_text(encoding="utf-8")
                if vendor_js.exists() else "")

    h = _HEADLINE
    inst = graph_data["instance"]
    fixes = ", ".join(f"{n}()" for n in graph_data["fix_names"]) or "fix site"
    payload = json.dumps({
        "nodes": graph_data["nodes"],
        "edges": graph_data["edges"],
        "counts": {
            "n_a_edges": graph_data["n_a_edges"],
            "n_confirmed": graph_data["n_confirmed"],
            "n_unconfirmed": graph_data["n_unconfirmed"],
            "n_b_edges": graph_data["n_b_edges"],
        },
    }, separators=(",", ":"))

    html = _DEMO_TEMPLATE.format(
        cyto_src=cyto_src,
        payload=payload,
        instance=inst,
        instance_short=inst[8:] if inst.startswith("django__") else inst,
        fixes=fixes,
        precision=h["precision"], recall=h["recall"], jaccard=h["jaccard"],
        compared=h["compared"], confirmed=h["confirmed"],
        only_a=h["only_a"], only_b=h["only_b"],
        n_a_edges=graph_data["n_a_edges"],
        n_unconfirmed=graph_data["n_unconfirmed"],
        n_confirmed=graph_data["n_confirmed"],
        n_b_edges=graph_data["n_b_edges"],
    )
    out_path.write_text(html, encoding="utf-8")
    return out_path


# The page. Braces in CSS/JS are doubled for str.format; only the named fields
# above are substituted. The cytoscape source is inlined between a marker comment
# and its closing tag so the page is self-contained and offline-first.
_DEMO_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Substrate Friction — {instance_short}</title>
<style>
  :root {{
    --bg:#0b1020; --panel:#131a2e; --ink:#e6ebf5; --muted:#9aa6c0;
    --confirmed:#9ca3af; --unconfirmed:#dc2626; --fix:#2563eb; --test:#16a34a;
    --armb:#ea580c; --line:#26304d;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  header {{ padding:18px 22px 14px; border-bottom:1px solid var(--line);
    background:linear-gradient(180deg,#111a33,#0b1020); }}
  h1 {{ margin:0 0 4px; font-size:20px; letter-spacing:.2px; }}
  .sub {{ color:var(--muted); font-size:13.5px; margin-bottom:12px; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:8px; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:8px;
    padding:6px 11px; font-size:13px; }}
  .stat b {{ color:#fff; font-size:15px; }}
  .caveat {{ margin-top:11px; padding:9px 12px; border-left:3px solid var(--armb);
    background:#1a1526; border-radius:0 8px 8px 0; font-size:12.8px; color:#f2d9c8; }}
  .bar {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px;
    padding:12px 22px; border-bottom:1px solid var(--line); background:var(--panel); }}
  button {{ font:600 13.5px inherit; color:#fff; background:var(--unconfirmed);
    border:0; border-radius:8px; padding:9px 15px; cursor:pointer; }}
  button.ghost {{ background:#26304d; }}
  button:disabled {{ opacity:.45; cursor:default; }}
  .counter {{ font-variant-numeric:tabular-nums; font-size:13.5px; color:var(--muted); }}
  .counter b {{ color:#fff; font-size:16px; }}
  .legend {{ display:flex; gap:15px; margin-left:auto; flex-wrap:wrap;
    font-size:12.5px; color:var(--muted); }}
  .legend span {{ display:inline-flex; align-items:center; gap:6px; }}
  .swatch {{ width:14px; height:3px; border-radius:2px; display:inline-block; }}
  .dot {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
  #cy {{ width:100%; height:62vh; min-height:420px; background:#0b1020; }}
  footer {{ padding:10px 22px; color:var(--muted); font-size:12px;
    border-top:1px solid var(--line); }}
  .view {{ color:var(--muted); font-size:13px; }}
</style>
</head>
<body>
<header>
  <h1>Same code, two call graphs — the wrong edges, and what pruning them costs</h1>
  <div class="sub">{instance} — fix-site neighbourhood of {fixes}. Name-matched
    (arm&nbsp;A) vs type-resolved via scip-python (arm&nbsp;B).</div>
  <div class="stats">
    <span class="stat">precision ceiling <b>{precision}</b></span>
    <span class="stat">recall <b>{recall}</b></span>
    <span class="stat">Jaccard <b>{jaccard}</b></span>
    <span class="stat">compared <b>{compared}</b></span>
    <span class="stat">confirmed <b>{confirmed}</b></span>
    <span class="stat">only&nbsp;A <b>{only_a}</b></span>
    <span class="stat">only&nbsp;B <b>{only_b}</b></span>
  </div>
  <div class="caveat"><b>Honest caveat:</b> precision is a <b>CEILING</b>, not a
    verdict. pyright emits no edge for an untyped receiver, so arm&nbsp;B
    under-reports rather than inventing edges — true precision is ≥ {precision}.
    The <code>cursor()</code> family (54 edges) is the counter-example where
    arm&nbsp;A was RIGHT and type resolution missed real
    <code>connection.cursor()</code> calls.</div>
</header>

<div class="bar">
  <button id="prune">Prune wrong edges</button>
  <button id="reset" class="ghost">Reset</button>
  <button id="toggle" class="ghost">Show arm B (type-resolved)</button>
  <span class="counter">removed <b id="removed">0</b> / {n_unconfirmed}
    unconfirmed &nbsp;·&nbsp; <span id="viewname" class="view">arm A · name-matched</span></span>
  <span class="legend">
    <span><span class="swatch" style="background:var(--unconfirmed)"></span>unconfirmed (pruned)</span>
    <span><span class="swatch" style="background:var(--confirmed)"></span>confirmed</span>
    <span><span class="dot" style="background:var(--fix)"></span>fix site</span>
    <span><span class="dot" style="background:var(--test)"></span>test target</span>
    <span><span class="dot" style="background:#9ca3af"></span>intermediate</span>
  </span>
</div>

<div id="cy"></div>

<footer>Bounded fix→test reachability via in-engine <code>count(*)</code> over
  <code>[:CALLS*1..k]</code> always returns; on one 34k-node django-density graph
  it answers in 6–10&nbsp;ms (typical source) to 6.5&nbsp;s (busiest hub) while
  path enumeration on that same graph runs to tens of seconds — up to the
  30,000&nbsp;ms ceiling (see docs/latency.md). Graph data embedded inline;
  Cytoscape.js vendored
  locally — this page needs no network.</footer>

<!-- vendored: docs/vendor/cytoscape.min.js — Cytoscape.js 3.30.2 (MIT), inlined for offline use -->
<script>{cyto_src}</script>
<script>
const DATA = {payload};
const ROLE_COLOR = {{fix:"#2563eb", test:"#16a34a", intermediate:"#9ca3af"}};

const nodes = DATA.nodes.map(n => ({{data:{{id:n.id, label:n.label, role:n.role}}}}));
const aEdges = DATA.edges.filter(e => e.arm === "a").map(e => ({{
  data:{{id:e.id, source:e.source, target:e.target, arm:"a",
    kind:e.confirmed ? "confirmed" : "unconfirmed"}}}}));
const bEdges = DATA.edges.filter(e => e.arm === "b").map(e => ({{
  data:{{id:e.id, source:e.source, target:e.target, arm:"b", kind:"confirmed"}}}}));

const cy = cytoscape({{
  container: document.getElementById("cy"),
  elements: {{nodes: nodes, edges: aEdges.concat(bEdges)}},
  style: [
    {{selector:"node", style:{{
      "background-color": ele => ROLE_COLOR[ele.data("role")] || "#9ca3af",
      "label":"data(label)", "color":"#e6ebf5", "font-size":"10px",
      "text-valign":"center", "text-halign":"right", "text-margin-x":"3px",
      "width":16, "height":16, "text-outline-color":"#0b1020",
      "text-outline-width":2 }}}},
    {{selector:"edge", style:{{
      "curve-style":"bezier", "target-arrow-shape":"triangle",
      "width":2, "arrow-scale":0.8,
      "line-color":"#9ca3af", "target-arrow-color":"#9ca3af", "opacity":0.85 }}}},
    {{selector:'edge[kind="unconfirmed"]', style:{{
      "line-color":"#dc2626", "target-arrow-color":"#dc2626",
      "width":3, "opacity":0.95 }}}},
    {{selector:".hidden", style:{{"display":"none"}}}},
    {{selector:".dim", style:{{"opacity":0.08}}}}
  ],
  layout: {{name:"breadthfirst", directed:true, spacingFactor:1.15, padding:24}}
}});

let view = "a";
function applyView() {{
  cy.batch(() => {{
    cy.edges().forEach(e => {{
      const show = e.data("arm") === view;
      e.toggleClass("hidden", !show);
    }});
  }});
  document.getElementById("viewname").textContent =
    view === "a" ? "arm A · name-matched" : "arm B · type-resolved";
  document.getElementById("toggle").textContent =
    view === "a" ? "Show arm B (type-resolved)" : "Show arm A (name-matched)";
  const pruneBtn = document.getElementById("prune");
  pruneBtn.disabled = (view !== "a");
}}
applyView();

let removed = 0;
const removedEl = document.getElementById("removed");

document.getElementById("prune").addEventListener("click", () => {{
  const wrong = cy.edges('edge[arm="a"][kind="unconfirmed"]').filter(e => !e.hasClass("hidden"));
  let i = 0;
  wrong.forEach(e => {{
    setTimeout(() => {{
      e.animate({{style:{{"opacity":0}}}}, {{duration:260, complete:() => {{
        e.addClass("hidden");
        removed += 1;
        removedEl.textContent = removed;
      }}}});
    }}, i * 130);
    i += 1;
  }});
}});

document.getElementById("reset").addEventListener("click", () => {{
  cy.batch(() => cy.edges('edge[arm="a"][kind="unconfirmed"]')
    .removeClass("hidden").style("opacity", 0.95));
  removed = 0; removedEl.textContent = "0";
  applyView();
}});

document.getElementById("toggle").addEventListener("click", () => {{
  view = view === "a" ? "b" : "a";
  applyView();
}});
</script>
</body>
</html>
"""


# ==========================================================================
# entrypoint: regenerate EVERY figure and demo.html from committed data
# ==========================================================================

def generate_arms_figure(out_path: Path = _PLOTS / "arms.png") -> Path:
    data = joined_arm_neighbourhood(_ARMS_INSTANCE, _ARMS_DEPTH)
    fixes = ", ".join(f"{n}()" for n in data["fix_names"]) or "fix site"
    label = (f"{_ARMS_INSTANCE[8:]} — fix-site neighbourhood of {fixes}: "
             "same code, two call graphs")
    return render_arms(data["a_edges"], data["b_edges"], data["roles"],
                       out_path, label, data)


def generate_prune_figure(out_path: Path = _PLOTS / "prune.png") -> Path:
    """docs/plots/prune.png from the real _ARMS_INSTANCE neighbourhood.

    django__django-11490's fix site is ``get_combinator_sql``; 9 of its 21
    name-matched edges are unconfirmed by type resolution, and 4 of those point
    at ``extend`` — the ``list.extend`` name collision that tops the offenders
    table. A 43% red mass on a single-fix-site neighbourhood: the clearest visible
    prune among the comparable instances.
    """
    data = joined_arm_neighbourhood(_ARMS_INSTANCE, _ARMS_DEPTH)
    fixes = ", ".join(f"{n}()" for n in data["fix_names"]) or "fix site"
    label = (f"{_ARMS_INSTANCE[8:]} — fix-site neighbourhood of {fixes}: "
             "pruning the edges type resolution does not confirm")
    return render_prune(data["a_edges"], data["roles"], out_path, label, data)


def generate_direction_figure(out_path: Path = _PLOTS / "direction.png") -> Path:
    """docs/plots/direction.png — the measured connectivity triple, verbatim."""
    bars = [
        ("fix → test\n(directed)", 0.0, "code does not\ncall its tests"),
        ("test → fix\n(directed)", 55.0, "the natural\ndirection"),
        ("undirected\n(both)", 98.0, "shares a\nneighbourhood"),
    ]
    return render_direction(bars, out_path, n=44)


def generate_latency_figure(out_path: Path = _PLOTS / "latency.png") -> Path:
    """docs/plots/latency.png — measured on ONE 34k-node django-density graph.

    Reads the committed docs/latency.json (produced by scripts/latency_measure.py);
    the per-k reachability curve is no longer hardcoded. The bar for enumeration is
    the measured algo.MSpaths cost between connected mid-graph seeds on the SAME
    graph; the caption discloses the busiest-hub operating point, where count(*)
    still completes and enumeration grazes / hits the 30 s ceiling.
    """
    lat = load_latency()
    note = (f"busiest-hub source: count(*) still completes "
            f"({lat['hub_max_ms']:,.0f} ms, {lat['hub_reach_nodes']:,} nodes) "
            f"where enumeration grazes the 30 s ceiling")
    return render_latency(lat["reach_rows"], lat["enum_ms"], out_path, note=note)


def generate_offenders_figure(out_path: Path = _PLOTS / "offenders.png") -> Path:
    return render_offenders(_parse_offenders(), out_path)


def generate_density_figure(out_path: Path = _PLOTS / "density.png") -> Path:
    return render_density(density_rows(), out_path)


def generate_verdict_figure(out_path: Path = _PLOTS / "day5-verdict.png") -> Path:
    """docs/plots/day5-verdict.png — the held-out verdict, parsed from the eval.

    Reads every number from the committed docs/evaluation.md (see
    :func:`_parse_verdict`); nothing is hand-entered here. Regenerates from a clean
    clone.
    """
    return render_verdict(_parse_verdict(), out_path)


def generate_demo_html(out_path: Path = _DEMO_HTML) -> Path:
    return render_demo_html(build_demo_graph(), out_path)


def generate_all() -> tuple[Path, Path, Path]:
    """Write docs/plots/{arms,offenders,density}.png — kept for back-compat."""
    return (generate_arms_figure(),
            generate_offenders_figure(),
            generate_density_figure())


def generate_everything() -> list[Path]:
    """Regenerate every figure AND demo.html from committed data.

    Every source here is committed (the shipped arms fallback, docs/graph-delta.md,
    and inline constants), so this runs from a clean clone with no working corpus.
    The v1 pair/truncation figures are deliberately excluded: they read gitignored
    engine/ref caches that a clean clone does not carry.
    """
    return [
        generate_prune_figure(),
        generate_direction_figure(),
        generate_latency_figure(),
        generate_arms_figure(),
        generate_offenders_figure(),
        generate_density_figure(),
        generate_verdict_figure(),
        generate_demo_html(),
    ]


if __name__ == "__main__":
    for path in generate_everything():
        print(f"wrote {path}")

"""The identity join — one shared node space for two incompatible graphs.

Arm A (name matching) and arm B (type resolution) name the same logical symbol
in different grammars:

    arm A   django.apps.config.AppConfig::__init__          tree-sitter qualname
    arm B   data.repos.django.django.apps.config::AppConfig#__init__().   SCIP

Comparing raw ``(src, dst)`` strings across those two forms yields precision
0.0 — every edge "disagrees" purely because the strings are shaped differently.
This module performs the join the delta analysis actually needs: it maps both
arms into one ``scope::leaf`` space via four pure, reversible string transforms.

The consequential one is the **package-``__init__`` collapse**. A class defined
in ``django/conf/__init__.py`` is written ``django.conf.__init__.Settings`` by
tree-sitter (which keeps the file stem ``__init__`` as a path segment) but
``django.conf.Settings`` by scip-python (which already folds a package's
``__init__`` into the package module). Applying that collapse on both arms
brings them onto the same node; omitting it on the arm-A side drops 229 django
edges from the intersection — precision 0.746 vs 0.707. See docs/graph-delta.md.
"""

from __future__ import annotations

from friction.scip.schema import DEFINITION_ROLE
from friction.scip.symbols import PROJECT_SCHEME, parse_symbol

_PKG_INIT = ".__init__."  # a package __init__ appearing as a MID module segment


def _to_scope_leaf(dotted: str) -> str:
    """Collapse package inits, then split the trailing leaf off its scope.

    Only a middle ``.__init__.`` collapses (the package-module case); a trailing
    ``.__init__`` is a real constructor method and is preserved as the leaf.
    """
    dotted = dotted.replace(_PKG_INIT, ".")
    head, sep, tail = dotted.rpartition(".")
    return f"{head}::{tail}" if sep else dotted


def normalize_scip(canonical: str, strip_prefix: str) -> str | None:
    """SCIP canonical form -> shared ``scope::leaf`` node, or None if unjoinable.

    ``canonical`` is ``<module>::<rest>`` where ``rest`` is a SCIP descriptor
    tail such as ``AppConfig#__init__().``. The transform:
      1. strip the discovered module prefix (e.g. ``data.repos.django.``),
      2. drop trailing descriptor punctuation ``().`` / ``.`` / ``#``,
      3. flatten SCIP's ``#`` class/member separator to a dot,
      4. collapse package ``__init__`` modules and re-split the leaf.
    """
    module, sep, rest = canonical.partition("::")
    if not sep:
        return None
    if strip_prefix and module.startswith(strip_prefix):
        module = module[len(strip_prefix):]
    rest = rest.rstrip("().#").replace("#", ".")
    dotted = f"{module}.{rest}" if rest else module
    return _to_scope_leaf(dotted)


def normalize_qualname(qualname: str) -> str:
    """Tree-sitter dotted qualname -> the same shared ``scope::leaf`` node.

    Arm A already emits ``scope::leaf``; flattening ``::`` back to a dot first
    lets a ``.__init__.`` segment sitting on the scope boundary collapse the
    same way it does for arm B.
    """
    dotted = qualname.replace("::", ".")
    return _to_scope_leaf(dotted)


def discover_scip_prefix(index) -> str:
    """Derive the constant module prefix scip-python prepends, from doc paths.

    scip-python roots every project module at ``<repo-path-as-dots>.<package>``
    (e.g. ``data.repos.django.django``). A document's ``relative_path`` gives the
    module tail below the package (``apps/config.py`` -> ``apps.config``), so a
    definition symbol in that document has module ``<prefix><package>.<tail>``.
    Stripping the known tail leaves ``<prefix><package>``; the package is its
    last dotted segment (arm A keeps it), so the prefix is everything before it.
    """
    for doc in index.documents:
        rp = doc.relative_path
        if not rp.endswith(".py"):
            continue
        tail = rp[:-3].replace("/", ".")
        if tail.endswith(".__init__"):
            tail = tail[: -len(".__init__")]
        elif tail == "__init__":
            tail = ""
        for occ in doc.occurrences:
            if not (occ.symbol_roles & DEFINITION_ROLE):
                continue
            sym_str = occ.symbol
            if not sym_str.startswith(PROJECT_SCHEME) or "python-stdlib" in sym_str:
                continue
            module = parse_symbol(sym_str).module
            if not module:
                continue
            pkg_root = module
            if tail:
                if not pkg_root.endswith("." + tail):
                    continue
                pkg_root = pkg_root[: -len(tail) - 1]
            head, sep, _pkg = pkg_root.rpartition(".")
            return head + "." if sep else ""
    return ""


def _in_scope(node: str, scope: str) -> bool:
    return (
        node == scope
        or node.startswith(scope + ".")
        or node.startswith(scope + "::")
    )


def joined_edge_sets(arm_a_edges, arm_b_edges, prefix, src_scope):
    """Map both arms into the shared space and return comparable edge sets.

    Returns ``(a_set, b_set, stats)`` where the two sets contain ``(src, dst)``
    tuples in ``scope::leaf`` form, ready for :func:`friction.delta.compare`.

    Arm B contributes internal edges only (external targets are pyright's known
    blind spot and are excluded, not scored). Arm A edges whose source falls
    outside ``src_scope`` — test- and docs-sourced callers that arm B never
    indexed — are **excluded and counted**, never treated as ``only_a``
    mismatches, so the two arms share one universe of possible callers. Pass
    ``src_scope=None`` to disable scoping.
    """
    b_set: set[tuple[str, str]] = set()
    b_unmapped = 0
    for e in arm_b_edges:
        if getattr(e, "dst_external", False):
            continue
        s = normalize_scip(e.src, prefix)
        d = normalize_scip(e.dst, prefix)
        if s is None or d is None:
            b_unmapped += 1
            continue
        b_set.add((s, d))

    a_set: set[tuple[str, str]] = set()
    a_unmapped = 0
    a_out_of_scope = 0
    for e in arm_a_edges:
        s = normalize_qualname(e.src)
        d = normalize_qualname(e.dst)
        if s is None or d is None:
            a_unmapped += 1
            continue
        if src_scope is not None and not _in_scope(s, src_scope):
            a_out_of_scope += 1
            continue
        a_set.add((s, d))

    stats = {
        "arm_a_edges_compared": len(a_set),
        "arm_a_excluded_out_of_scope": a_out_of_scope,
        "arm_a_unmapped_nodes": a_unmapped,
        "arm_b_edges_compared": len(b_set),
        "arm_b_unmapped_nodes": b_unmapped,
    }
    return a_set, b_set, stats

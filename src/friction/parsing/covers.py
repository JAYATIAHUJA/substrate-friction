"""Derive COVERS edges statically: a test covers what it transitively calls.

This over-approximates relative to real execution coverage. That is declared as
a limitation in the README. The dynamic alternative (running each repo's suite
under coverage.py) is only worth the cost if the go/no-go result is weak and
COVERS quality is the suspected reason.
"""

from __future__ import annotations

from collections import defaultdict, deque

from friction.parsing.calls import Edge
from friction.parsing.symbols import SymbolTable


def derive_covers(table: SymbolTable, edges: list[Edge], max_hops: int = 3) -> list[Edge]:
    adjacency: dict[int, list[int]] = defaultdict(list)
    for e in edges:
        if e.type == "CALLS":
            adjacency[e.src].append(e.dst)

    out: list[Edge] = []
    for fn in table.functions:
        if not fn.is_test:
            continue
        seen = {fn.id}
        queue = deque([(fn.id, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for nxt in adjacency.get(node, ()):
                if nxt in seen:
                    continue
                seen.add(nxt)
                out.append(Edge(fn.id, nxt, "COVERS", 1))
                queue.append((nxt, depth + 1))
    return out

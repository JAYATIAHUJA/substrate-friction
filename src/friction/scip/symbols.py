"""SCIP symbol strings -> stable node identity.

A SCIP symbol looks like:
    scip-python python <package> <version> `<module>`/<Class>#<method>().
The package VERSION varies across SWE-bench base commits, so it must be
stripped from any identity used to compare graphs across instances.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PROJECT_SCHEME = "scip-python python"
_EXTERNAL_PACKAGES = {"python-stdlib"}
# scip-python backticks a module (namespace) descriptor only when it contains a
# character that would otherwise break the grammar (e.g. a "."). Single-segment
# modules like "builtins" or "sre_constants" are emitted WITHOUT backticks. Real
# django indexes are 929/969 stdlib and 80 project symbols in the un-backticked
# form, so the descriptor matcher must accept both. The matcher is anchored at
# the start of the descriptor tail (parts[4]).
_DESCRIPTOR = re.compile(
    r"^(?:`(?P<mb>[^`]*)`|(?P<mp>[^/`\s]+))/(?P<rest>.*)$"
)


def _descriptor(tail: str) -> "re.Match[str] | None":
    return _DESCRIPTOR.match(tail)


def _module_of(m: "re.Match[str]") -> str:
    mb = m.group("mb")
    return mb if mb is not None else m.group("mp")


@dataclass(frozen=True)
class Sym:
    symbol: str
    kind: str
    is_external: bool
    module: str
    name: str


def parse_symbol(symbol: str) -> Sym:
    if not symbol.startswith(PROJECT_SCHEME):
        # "local 12" and any non-python scheme
        return Sym(symbol, "other", False, "", symbol)

    parts = symbol.split(" ", 4)
    package = parts[2] if len(parts) > 2 else ""
    tail = parts[4] if len(parts) > 4 else ""
    external = package in _EXTERNAL_PACKAGES

    m = _descriptor(tail)
    if not m:
        return Sym(symbol, "other", external, "", tail)
    module, rest = _module_of(m), m.group("rest")

    if rest.endswith("()."):
        kind, name = "function", rest[:-3].split("#")[-1].split("/")[-1]
    elif rest.endswith("#"):
        kind, name = "class", rest[:-1].split("#")[-1].split("/")[-1]
    else:
        kind, name = "other", rest.rstrip(".#/")
    return Sym(symbol, kind, external, module, name)


def canonical(sym: Sym, path: str | None) -> str:
    """Identity that is stable across package versions and base commits.

    Uses the module descriptor rather than the file path, because a file can
    move between commits while the module path stays put.
    """
    if not sym.symbol.startswith(PROJECT_SCHEME):
        return f"?::{sym.name}"
    parts = sym.symbol.split(" ", 4)
    tail = parts[4] if len(parts) > 4 else ""
    m = _descriptor(tail)
    if not m:
        return f"?::{sym.name}"
    return f"{_module_of(m)}::{m.group('rest')}"

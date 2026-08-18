"""The terminal face of substrate—friction — the HydraDB scheme in ANSI.

One accent (#ff571a), one signal (#f9c425), a gray ramp, white ink on a
dark ground — nothing else, matching docs/site.css. Styling activates
only when stdout is a TTY (or FORCE_COLOR=1); NO_COLOR always wins.
Piped output — captures, CI logs, tests — keeps the exact plain bytes it
has always had, so every committed record stays byte-stable.
"""

from __future__ import annotations

import os
import shutil
import sys

WIDTH = 68
RULE = "─" * WIDTH

_TRUECOLOR = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")

# 256-color fallbacks: 208 ≈ #ff875f, 220 ≈ #ffd787.
_ACCENT_256 = "38;5;208"
_SIGNAL_256 = "38;5;220"
_DIM_256 = "38;5;240"
_FAINT_256 = "38;5;245"

if _TRUECOLOR:
    ACCENT = "38;2;255;87;26"       # --accent  #ff571a
    SIGNAL = "38;2;249;196;37"      # --yellow  #f9c425
    DIM = "38;2;110;110;110"        # --line ramp
    FAINT = "38;2;160;160;160"
else:
    ACCENT, SIGNAL, DIM, FAINT = (_ACCENT_256, _SIGNAL_256, _DIM_256,
                                  _FAINT_256)

_RESET = "\033[0m"
_BOLD = "1"  # SGR parameter, joined with colour codes inside paint()


def styling(stream=None) -> bool:
    """True when styling should be emitted for *stream* (default stdout)."""
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    forced = os.environ.get("FORCE_COLOR", "")
    if forced:
        return forced.lower() not in ("0", "false", "no")
    if os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def paint(text: str, *codes: str) -> str:
    """Wrap *text* in the given SGR codes (no-op per call site if disabled
    by the caller — renderers below check styling() once and branch)."""
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}{_RESET}"


# -- glyphs: the ANSI-Shadow letters needed for the wordmark -----------------

_GLYPHS: dict[str, tuple[str, ...]] = {
    "S": ("███████╗", "██╔════╝", "███████╗", "╚════██║",
          "███████║", "╚══════╝"),
    "U": ("██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "B": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗",
          "██████╔╝", "╚═════╝ "),
    "T": ("████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ",
          "   ██║   ", "   ╚═╝   "),
    "R": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗",
          "██║  ██║", "╚═╝  ╚═╝"),
    "A": (" █████╗ ", "██╔══██╗", "███████║", "██╔══██║",
          "██║  ██║", "╚═╝  ╚═╝"),
    "E": ("███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ",
          "███████║", "╚══════╝"),
    "F": ("███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ",
          "██║     ", "╚═╝     "),
    "I": ("██╗", "██║", "██║", "██║", "██║", "╚═╝"),
    "C": (" ██████╗", "██╔════╝", "██║     ", "██║     ",
          "╚██████╗", " ╚═════╝"),
    "O": (" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "N": ("███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║",
          "██║ ╚████║", "╚═╝  ╚═══╝"),
    "—": ("   ", "   ", "───", "───", "   ", "   "),
}

_WORD_TOP = "SUBSTRATE"
_WORD_BOT = "—FRICTION"


def _word(word: str) -> list[str]:
    rows = [""] * 6
    for ch in word:
        g = _GLYPHS[ch]
        for i in range(6):
            rows[i] += g[i]
    return rows


def banner(tagline: str = "measure the map before you trust it") -> str:
    """The wordmark. Empty string when styling is off — callers print it
    unconditionally and nothing appears in piped output."""
    if not styling():
        return ""
    cols = shutil.get_terminal_size((100, 24)).columns
    top, bot = _word(_WORD_TOP), _word(_WORD_BOT)
    if cols < max(len(top[0]), len(bot[0])) + 2:
        line = "substrate—friction"
        return (paint(line, ACCENT, _BOLD) + "\n"
                + paint(tagline, DIM) + "\n")
    out = [paint(r, ACCENT, _BOLD) for r in top]
    out += [paint(r, _BOLD) for r in bot]
    out.append(paint(tagline, DIM))
    return "\n".join(out) + "\n"


# -- styled primitives (plain modes reproduce the historical bytes) ----------

def rule(width: int = WIDTH) -> str:
    body = "─" * width
    return body if not styling() else paint(body, DIM)


def verdict(mark: str, decision: str, meta: str) -> str:
    """`[FAIL]  RUN_FULL      arm=arm_b  k=6` — plain form is the exact
    historical string; tokens survive ANSI-stripping either way."""
    body = f"[{mark}]  {decision}      {meta}"
    if not styling():
        return body
    bracket = paint(f"[{mark}]",
                    SIGNAL if mark == "PASS" else ACCENT, _BOLD)
    dec = paint(decision, _BOLD)
    m = paint(meta, FAINT)
    return f"{bracket}  {dec}      {m}"


def kv(key: str, value: str) -> str:
    """`  key : value` lines, keys dimmed in color mode."""
    body = f"  {key} : {value}"
    return body if not styling() else (
        f"  {paint(key, FAINT)} : {paint(value, _BOLD)}")


def bar(value: float, hi: float, width: int = 24) -> str:
    if hi <= 0:
        return ""
    filled = max(0, min(width, round(width * value / hi)))
    body = "█" * filled + "·" * (width - filled)
    return body if not styling() else (
        paint("█" * filled, ACCENT) + paint("·" * (width - filled), DIM))


def head(text: str) -> str:
    """Section heading (already-uppercase labels)."""
    return text if not styling() else paint(text, SIGNAL, _BOLD)


def flash(text: str) -> str:
    """The line the whole tool exists to print — the refusal."""
    return text if not styling() else paint(text, ACCENT, _BOLD)


def dim(text: str) -> str:
    return text if not styling() else paint(text, DIM)


__all__ = ["ACCENT", "RULE", "SIGNAL", "banner", "bar", "dim", "flash",
           "head", "kv", "paint", "rule", "styling", "verdict"]

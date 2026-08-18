"""The TUI layer: styled for humans, byte-stable for machines.

The contract under test: piped output (captures, CI logs, the walkthrough
page) must never see a single ANSI byte, while every semantic token —
[FAIL], RUN_FULL, NOT SELECTED, VERIFY OK — survives styling intact.
"""

from __future__ import annotations

import re
import sys

import pytest

from friction import tui

SGR = re.compile(r"\x1b\[[0-9;]*m")


def _plain(monkeypatch, value="", name="FORCE_COLOR"):
    monkeypatch.setenv(name, value)


def test_plain_by_default_when_piped(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    monkeypatch.setattr(sys, "stdout", type("F", (), {"isatty": lambda s: False})())
    assert tui.styling() is False


def test_plain_bytes_match_history(monkeypatch):
    _plain(monkeypatch, "0")
    assert tui.rule() == "─" * 68
    assert tui.rule(96) == "─" * 96
    assert tui.verdict("FAIL", "RUN_FULL", "arm=arm_b  k=6") == \
        "[FAIL]  RUN_FULL      arm=arm_b  k=6"
    assert tui.bar(0.545, 1.0, 18) == "██████████········"
    assert tui.banner() == ""
    assert tui.flash("VERIFY OK:") == "VERIFY OK:"
    assert tui.dim("hint") == "hint"
    assert tui.head("FEATURE BARS") == "FEATURE BARS"


def test_force_color_emits_valid_sgr(monkeypatch):
    _plain(monkeypatch, "1")
    assert tui.styling() is True
    whole = "\n".join([
        tui.banner(),
        tui.verdict("FAIL", "RUN_FULL", "arm=arm_b  k=6"),
        tui.verdict("PASS", "SKIP_SAFE", "arm=arm_b  k=6"),
        tui.bar(0.545, 1.0, 18),
        tui.rule(),
        tui.flash("  NOT SELECTED — 370 guarding test node(s) are unreachable"),
        tui.head("FEATURE BARS"),
    ])
    assert "\x1b[" in whole
    # strip every well-formed SGR; nothing escape-like may remain
    assert "\x1b" not in SGR.sub("", whole)
    # every escape present is well-formed (no dangling sequences)
    for seq in re.findall(r"\x1b\[[^m]*m", whole):
        assert re.fullmatch(r"\x1b\[[0-9;]*m", seq), seq


def test_tokens_survive_styling(monkeypatch):
    _plain(monkeypatch, "1")
    v = SGR.sub("", tui.verdict("FAIL", "RUN_FULL", "arm=arm_b  k=6"))
    assert v == "[FAIL]  RUN_FULL      arm=arm_b  k=6"
    f = SGR.sub("", tui.flash("VERIFY OK:"))
    assert f == "VERIFY OK:"


def test_no_color_wins_over_force(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")
    assert tui.styling() is False


def test_banner_wordmark_and_uniform_rows(monkeypatch):
    _plain(monkeypatch, "1")
    rows = [SGR.sub("", r) for r in tui.banner().rstrip("\n").split("\n")]
    # 6 rows SUBSTRATE + 6 rows —FRICTION + tagline
    assert len(rows) == 13
    top, bot = rows[:6], rows[6:12]
    assert len({len(r) for r in top}) == 1      # each word block uniform
    assert len({len(r) for r in bot}) == 1
    assert "measure the map before you trust it" == rows[-1]
    assert rows[0].startswith("███████╗")          # S
    assert "██" in rows[6]                          # F row begins the second word
    assert max(len(r) for r in rows[:12]) <= 80     # fits a default terminal


def test_banner_narrow_terminal_falls_back(monkeypatch):
    _plain(monkeypatch, "1")
    import friction.tui as T
    monkeypatch.setattr(T.shutil, "get_terminal_size",
                        lambda fallback: type("S", (), {"columns": 40})())
    b = SGR.sub("", T.banner())
    assert "substrate—friction" in b and "█" not in b


def test_truecolor_palette_used_when_colorterm(monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    import importlib
    import friction.tui as T
    importlib.reload(T)
    assert T.ACCENT == "38;2;255;87;26"     # #ff571a, the site accent
    monkeypatch.delenv("COLORTERM")
    importlib.reload(T)


@pytest.mark.parametrize("mark,decision", [("FAIL", "RUN_FULL"),
                                           ("PASS", "SKIP_SAFE")])
def test_verdict_plain_matches_gate_format(monkeypatch, mark, decision):
    _plain(monkeypatch, "0")
    out = tui.verdict(mark, decision, "arm=arm_b  k=6")
    assert out == f"[{mark}]  {decision}      arm=arm_b  k=6"

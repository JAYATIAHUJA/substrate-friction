#!/usr/bin/env python
"""The unlock, shown once — on a DISCLOSED synthetic audit.

`friction gate` refuses every measured graph class today: no class's recall
has a one-sided 95% Wilson lower bound at or above the 0.95 bar. This demo
constructs the audit a graph class WOULD have to earn (99 hits in 100
labelled instances — LB 0.956) and prints the verdict that follows, so the
autonomous path is visible rather than hypothetical. Nothing here is
measured; everything is labelled.

    uv run python scripts/unlock_demo.py
"""

from friction.gate import SAFE_SKIP_RECALL, RecallAudit, gate, wilson_lb
from friction.tui import banner, rule, verdict

AUDIT = RecallAudit(
    hits=99, n=100, arm="synthetic", k=6, misses=(),
    per_repo={"SYNTHETIC (disclosed)": (99, 100)}, split=None,
)


def main() -> int:
    v = gate(AUDIT, SAFE_SKIP_RECALL)
    if banner():
        print(banner(), end="")
    print(rule())
    print(verdict("PASS" if v.decision == "SKIP_SAFE" else "FAIL",
                  v.decision, "arm=synthetic  k=6  DISCLOSED DEMO"))
    print(rule())
    print(v.reason)
    print()
    print(f"  Wilson lower bound at 99/100: {wilson_lb(99, 100):.3f} "
          f"(bar {SAFE_SKIP_RECALL}) — clears it, so the gate opens.")
    print("  No MEASURED graph class is here. Today every real verdict is "
          "RUN_FULL.")
    print("  This is what a class must earn to unlock autonomy — and what "
          "a perfect 3/3 can never fake.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

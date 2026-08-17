#!/usr/bin/env python
"""The demo shown in the video: one change, one dropped test.

    uv run python scripts/gate_demo.py                 # auto-pick the first miss
    uv run python scripts/gate_demo.py --instance ID   # a specific one
"""

from __future__ import annotations

import argparse
import sys

from friction.cli import MANIFEST_PATH, main as cli_main
from friction.gate import audit_recall


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", default=None)
    ap.add_argument("--arm", default="arm_b", choices=["arm_a", "arm_b"])
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args(argv)

    instance = args.instance
    if instance is None:
        audit = audit_recall(MANIFEST_PATH, MANIFEST_PATH.parent,
                             args.arm, args.k)
        if not audit.misses:
            print("no misses in this corpus — nothing to demonstrate")
            return 0
        instance = audit.misses[0]

    print("\n>>> friction gate --arm", args.arm, "\n")
    cli_main(["gate", "--arm", args.arm, "--k", str(args.k)])

    print(f"\n>>> friction gate --instance {instance}\n")
    return cli_main(["gate", "--arm", args.arm, "--k", str(args.k),
                     "--instance", instance])


if __name__ == "__main__":
    sys.exit(main())

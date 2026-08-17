#!/usr/bin/env python
"""Pin the dev/sealed split once, deterministically, and never again.

Assignment is a SHA-256 of the instance id — not a random shuffle — so the split
is reproducible from the ids alone and cannot be quietly re-rolled to a more
flattering partition. The output is committed; `--force` exists only to make
overwriting a deliberate act.

    uv run python scripts/pin_split.py --out data/shipped/split.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def assign(instance_id: str, sealed_share: float = 0.375) -> str:
    """Hash the id into [0,1) and assign below the cut to `sealed`.

    0.375 puts roughly 3 of every 8 instances in the sealed half, mirroring the
    70/42 proportion this field's benchmarks use.
    """
    digest = hashlib.sha256(instance_id.encode("utf-8")).hexdigest()
    position = int(digest[:16], 16) / float(1 << 64)
    return "sealed" if position < sealed_share else "dev"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/shipped/arms/manifest.jsonl"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sealed-share", type=float, default=0.375)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.out.exists() and not args.force:
        raise SystemExit(
            f"{args.out} already exists. The split is pinned once by design; "
            f"pass --force only if you intend to break that.")

    split: dict[str, str] = {}
    with args.manifest.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            iid = json.loads(line)["instance_id"]
            split[iid] = assign(iid, args.sealed_share)

    args.out.write_text(json.dumps({
        "method": "sha256(instance_id) -> [0,1); < sealed_share is sealed",
        "sealed_share": args.sealed_share,
        "note": "Pinned before the final measurement. There are no fitted "
                "parameters in the selector; this guards the hop bound, the "
                "identity-join rules and the endpoint mapping, which were "
                "chosen while looking at django.",
        "assignments": split,
    }, indent=2, sort_keys=True), encoding="utf-8")

    sealed = sum(1 for v in split.values() if v == "sealed")
    print(f"wrote {args.out}: {len(split)} instances, "
          f"{sealed} sealed / {len(split) - sealed} dev")


if __name__ == "__main__":
    main()

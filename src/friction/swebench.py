"""SWE-bench Verified instances plus published per-instance outcome labels.

Outcome labels come from github.com/SWE-bench/experiments, where each
submission folder under evaluation/<split>/ holds a results JSON listing the
instance ids that submission resolved. Folder names are discovered at runtime
rather than hardcoded, so nothing here depends on a guessed path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import httpx

GITHUB_API = "https://api.github.com/repos/SWE-bench/experiments/contents"
RAW = "https://raw.githubusercontent.com/SWE-bench/experiments/main"


@dataclass(frozen=True)
class Instance:
    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    patch: str
    test_patch: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]


def _as_list(value) -> list[str]:
    if isinstance(value, str):
        return list(json.loads(value))
    return list(value or [])


def load_instances(repos: list[str] | None = None,
                   cache_dir: Path = Path("data/swebench")) -> list[Instance]:
    from datasets import load_dataset

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test",
                      cache_dir=str(cache_dir))
    out: list[Instance] = []
    for row in ds:
        if repos is not None and row["repo"] not in repos:
            continue
        out.append(Instance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            patch=row["patch"],
            test_patch=row["test_patch"],
            fail_to_pass=_as_list(row["FAIL_TO_PASS"]),
            pass_to_pass=_as_list(row["PASS_TO_PASS"]),
        ))
    return out


def list_submissions(split: str = "verified") -> list[str]:
    resp = httpx.get(f"{GITHUB_API}/evaluation/{split}", timeout=60.0)
    resp.raise_for_status()
    return sorted(item["name"] for item in resp.json() if item["type"] == "dir")


def _parse_resolved(payload) -> set[str]:
    if isinstance(payload, list):
        return set(payload)
    if isinstance(payload, dict):
        for key in ("resolved", "resolved_ids", "resolved_instances"):
            if key in payload:
                return set(payload[key])
    raise ValueError(f"unrecognised results shape: {type(payload)} {str(payload)[:120]}")


def load_resolved(submission: str, split: str = "verified") -> set[str]:
    """Fetch a submission's resolved-instance set, trying known result paths."""
    candidates = [
        f"{RAW}/evaluation/{split}/{submission}/results/results.json",
        f"{RAW}/evaluation/{split}/{submission}/results.json",
    ]
    last: Exception | None = None
    for url in candidates:
        try:
            resp = httpx.get(url, timeout=60.0)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            return _parse_resolved(resp.json())
        except Exception as exc:  # noqa: BLE001 - try next candidate
            last = exc
    raise FileNotFoundError(f"no results JSON for {submission!r}: {last}")


def outcome_table(instances: Iterable[Instance], submissions: list[str],
                  split: str = "verified",
                  resolver: Callable[[str, str], set[str]] = load_resolved
                  ) -> dict[str, dict[str, bool]]:
    resolved_by = {s: resolver(s, split) for s in submissions}
    table: dict[str, dict[str, bool]] = {}
    for inst in instances:
        table[inst.instance_id] = {
            s: inst.instance_id in resolved_by[s] for s in submissions
        }
    return table

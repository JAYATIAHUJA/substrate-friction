import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _engine_reachable() -> bool:
    for port in (7687, 1080):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def pytest_collection_modifyitems(config, items):
    """Engine-marked tests SKIP with a clear message when no HydraDB is up.

    CI's engine job sets FRICTION_REQUIRE_ENGINE=1 so the skip path can never
    swallow a dead engine there — in CI an unreachable engine is a failure.
    """
    if os.environ.get("FRICTION_REQUIRE_ENGINE"):
        return
    if _engine_reachable():
        return
    skip = pytest.mark.skip(
        reason="HydraDB engine not running (start it: docker compose up -d)")
    for item in items:
        if "engine" in item.keywords:
            item.add_marker(skip)

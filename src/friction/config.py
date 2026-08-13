"""Connection and engine settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bolt_uri: str
    http_url: str
    token: str
    namespace: str
    graph: str
    cell_id: str
    max_len: int
    path_count: int
    rel_direction: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            bolt_uri=os.environ.get("HYDRA_BOLT_URI", "bolt://127.0.0.1:7687"),
            http_url=os.environ.get("HYDRA_HTTP_URL", "http://127.0.0.1:8443"),
            token=os.environ.get("HYDRA_TOKEN", "local-development-token-32-bytes"),
            namespace=os.environ.get("HYDRA_NAMESPACE", "default"),
            graph=os.environ.get("HYDRA_GRAPH", "default"),
            cell_id=os.environ.get("HYDRA_CELL_ID", "cell-0"),
            max_len=int(os.environ.get("HYDRA_MAX_LEN", "6")),
            path_count=int(os.environ.get("HYDRA_PATH_COUNT", "20")),
            rel_direction=os.environ.get("HYDRA_REL_DIRECTION", "both"),
        )

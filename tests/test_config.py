import os
from friction.config import Settings


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("HYDRA_BOLT_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("HYDRA_TOKEN", "local-development-token-32-bytes")
    monkeypatch.setenv("HYDRA_MAX_LEN", "6")
    s = Settings.from_env()
    assert s.bolt_uri == "bolt://127.0.0.1:7687"
    assert s.token == "local-development-token-32-bytes"
    assert s.max_len == 6


def test_from_env_has_defaults(monkeypatch):
    for key in ("HYDRA_BOLT_URI", "HYDRA_HTTP_URL", "HYDRA_NAMESPACE",
                "HYDRA_GRAPH", "HYDRA_CELL_ID", "HYDRA_MAX_LEN",
                "HYDRA_FAN_IN_PATH_COUNT"):
        monkeypatch.delenv(key, raising=False)
    s = Settings.from_env()
    assert s.http_url == "http://127.0.0.1:8443"
    assert s.namespace == "default"
    assert s.graph == "default"
    assert s.cell_id == "cell-0"
    assert s.max_len == 6
    assert s.fan_in_path_count == 500


def test_from_env_reads_fan_in_path_count_override(monkeypatch):
    monkeypatch.setenv("HYDRA_FAN_IN_PATH_COUNT", "250")
    s = Settings.from_env()
    assert s.fan_in_path_count == 250

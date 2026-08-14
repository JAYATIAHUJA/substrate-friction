import json
import pytest
from friction import swebench


def test_outcome_table_marks_missing_as_failed():
    instances = [
        swebench.Instance("a-1", "django/django", "abc", "p", "d", "t", ["t1"], []),
        swebench.Instance("a-2", "django/django", "abc", "p", "d", "t", ["t2"], []),
    ]
    resolved = {"sysA": {"a-1"}, "sysB": {"a-1", "a-2"}}
    table = swebench.outcome_table(
        instances, ["sysA", "sysB"], resolver=lambda s, split: resolved[s]
    )
    assert table["a-1"] == {"sysA": True, "sysB": True}
    assert table["a-2"] == {"sysA": False, "sysB": True}


def test_parse_resolved_accepts_common_shapes():
    assert swebench._parse_resolved({"resolved": ["x", "y"]}) == {"x", "y"}
    assert swebench._parse_resolved({"resolved_ids": ["z"]}) == {"z"}
    assert swebench._parse_resolved(["p", "q"]) == {"p", "q"}


def test_parse_resolved_rejects_unknown_shape():
    with pytest.raises(ValueError):
        swebench._parse_resolved({"unexpected": 1})


def test_load_resolved_reads_cache_without_network(tmp_path, monkeypatch):
    (tmp_path / "sysX.json").write_text(
        json.dumps({"resolved": ["i-1", "i-2"], "no_logs": ["i-9"]})
    )

    def _no_network(*args, **kwargs):
        raise AssertionError("network call attempted despite cached file")

    monkeypatch.setattr(swebench.httpx, "get", _no_network)

    assert swebench.load_resolved("sysX", cache_dir=tmp_path) == {"i-1", "i-2"}


def test_load_resolved_falls_back_to_network_when_uncached(tmp_path, monkeypatch):
    calls = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"resolved": ["net-1"]}

    def _fake_get(url, *args, **kwargs):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(swebench.httpx, "get", _fake_get)

    assert swebench.load_resolved("absent", cache_dir=tmp_path) == {"net-1"}
    assert calls, "expected a network fetch when cache file is absent"


@pytest.mark.engine
def test_list_submissions_returns_folder_names():
    names = swebench.list_submissions("verified")
    assert names and all(isinstance(n, str) for n in names)

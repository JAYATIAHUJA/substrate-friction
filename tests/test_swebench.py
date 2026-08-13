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


@pytest.mark.engine
def test_list_submissions_returns_folder_names():
    names = swebench.list_submissions("verified")
    assert names and all(isinstance(n, str) for n in names)

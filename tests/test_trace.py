from pathlib import Path
import pytest
from friction import trace


def test_django_version_maps_to_an_interpreter():
    assert trace.python_for_django((2, 2)) == "3.8"
    assert trace.python_for_django((3, 0)) == "3.9"
    assert trace.python_for_django((4, 0)) == "3.10"
    assert trace.python_for_django((4, 2)) == "3.12"


def test_unknown_future_version_falls_back_to_newest():
    assert trace.python_for_django((9, 9)) == "3.12"


def test_covers_keeps_only_edges_originating_at_a_test():
    tr = trace.TraceResult(
        edges=[("tests/test_a.py::test_one", "django/db/models.py::save"),
               ("django/db/models.py::save", "django/db/base.py::_do_insert")],
        functions=3, seconds=1.0, ok=True, error="")
    got = trace.covers_edges(tr)
    assert got == [("tests/test_a.py::test_one", "django/db/models.py::save")]


def test_covers_is_empty_when_nothing_originates_at_a_test():
    tr = trace.TraceResult(edges=[("django/a.py::f", "django/b.py::g")],
                           functions=2, seconds=0.1, ok=True, error="")
    assert trace.covers_edges(tr) == []


def test_trace_result_reports_failure_without_raising():
    tr = trace.TraceResult([], 0, 0.0, False, "boom")
    assert tr.ok is False and tr.error == "boom"


class _FakeCode:
    """A stand-in for a code object: co_name always, co_qualname only if given."""

    def __init__(self, co_name, co_qualname=None):
        self.co_name = co_name
        if co_qualname is not None:
            self.co_qualname = co_qualname


class _Widget:
    pass


def test_qualify_uses_self_class_for_a_method():
    # co_name is the bare "save"; self in f_locals gives the enclosing class.
    code = _FakeCode("save")
    assert trace.qualified_name(code, {"self": _Widget()}) == "_Widget.save"


def test_qualify_uses_cls_for_a_classmethod():
    # a classmethod has no self, but cls names the class.
    code = _FakeCode("create")
    assert trace.qualified_name(code, {"cls": _Widget}) == "_Widget.create"


def test_qualify_leaves_a_module_level_function_bare():
    # no self, no cls -> the bare name is already correct.
    code = _FakeCode("set_script_prefix")
    assert trace.qualified_name(code, {}) == "set_script_prefix"


def test_qualify_prefers_co_qualname_when_present():
    # on 3.11+ co_qualname gives "Class.method" directly and wins over self.
    code = _FakeCode("save", co_qualname="Model.save")
    assert trace.qualified_name(code, {"self": _Widget()}) == "Model.save"


def test_qualify_ignores_a_non_type_cls_binding():
    # a local variable coincidentally named cls that is not a class is ignored.
    code = _FakeCode("helper")
    assert trace.qualified_name(code, {"cls": 42}) == "helper"


@pytest.mark.engine
def test_trace_a_real_django_module(tmp_path):
    """The probe, as a standing regression test. Needs a django clone."""
    repo = Path("data/repos/django")
    if not repo.exists():
        pytest.skip("django clone not present")
    ver = trace.django_version(repo)
    interp = trace.provision(repo, trace.python_for_django(ver))
    res = trace.trace_tests(repo, interp, ["dispatch"])
    assert res.ok, res.error
    assert res.functions > 100
    assert len(res.edges) > 100

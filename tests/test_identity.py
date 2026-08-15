"""The identity join is the load-bearing step of the graph delta: it maps arm A
(tree-sitter qualnames) and arm B (SCIP canonical forms) into one shared
`scope::leaf` space. A single missed normalisation — the package-``__init__``
collapse — silently drops 229 django edges from the intersection, so every
normalisation gets a test.
"""

from friction import identity as I
from friction.namematch.graph import NameEdge
from friction.scip.extract import CallEdge


# --- normalize_scip: the four reversible transforms on a canonical form -------

def test_normalize_scip_strips_discovered_module_prefix():
    out = I.normalize_scip(
        "data.repos.django.django.apps.config::AppConfig#create().",
        "data.repos.django.",
    )
    assert out == "django.apps.config.AppConfig::create"


def test_normalize_scip_flattens_hash_to_dot():
    # '#' is SCIP's class/member separator; it must become a plain dot so the
    # class scope reads the same way arm A writes it.
    out = I.normalize_scip("pkg.mod::Outer#Inner#method().", "")
    assert "#" not in out
    assert out == "pkg.mod.Outer.Inner::method"


def test_normalize_scip_strips_trailing_descriptor_punctuation():
    # function "().", class "#", and bare "." tails all reduce to the leaf.
    assert I.normalize_scip("pkg.mod::f().", "") == "pkg.mod::f"
    assert I.normalize_scip("pkg.mod::C#", "") == "pkg.mod::C"


def test_normalize_scip_returns_none_for_non_joinable_canonical():
    # a canonical with no '::' scope separator (e.g. the "?::x" degenerate form
    # loses its module) cannot be placed in the shared space.
    assert I.normalize_scip("justamodule", "") is None


# --- normalize_qualname: arm A dotted qualname into the same space ------------

def test_normalize_qualname_produces_scope_leaf():
    assert I.normalize_qualname("pkg.mod.C.method") == "pkg.mod.C::method"
    assert I.normalize_qualname("pkg.mod.C::method") == "pkg.mod.C::method"


def test_qualname_and_scip_agree_on_the_same_logical_symbol():
    # The whole point of the join: the two arms name AppConfig.__init__
    # differently, and after normalisation they must be byte-identical.
    a = I.normalize_qualname("django.apps.config.AppConfig::__init__")
    b = I.normalize_scip(
        "data.repos.django.django.apps.config::AppConfig#__init__().",
        "data.repos.django.",
    )
    assert a == b == "django.apps.config.AppConfig::__init__"


# --- the package-__init__ collapse (the 229-edge normalisation) ---------------

def test_package_init_module_segment_is_collapsed_both_arms():
    # A class in django/conf/__init__.py: tree-sitter writes the file stem as a
    # module segment (`conf.__init__.Settings`), scip-python already folds it
    # into the package (`conf.Settings`). Both must land on the same node.
    a = I.normalize_qualname("django.conf.__init__.Settings::is_overridden")
    b = I.normalize_scip(
        "data.repos.django.django.conf::Settings#is_overridden().",
        "data.repos.django.",
    )
    assert a == b == "django.conf.Settings::is_overridden"


def test_method_named_init_is_not_collapsed():
    # A *method* named __init__ is a real leaf and must survive; only a middle
    # `.__init__.` module segment collapses.
    assert I.normalize_qualname("pkg.mod.C.__init__") == "pkg.mod.C::__init__"
    assert (
        I.normalize_scip("pkg.mod::C#__init__().", "") == "pkg.mod.C::__init__"
    )


# --- discover_scip_prefix: derive the constant prefix from doc paths ----------

class _Occ:
    def __init__(self, symbol, roles=1):
        self.symbol = symbol
        self.symbol_roles = roles


class _Doc:
    def __init__(self, relative_path, occurrences):
        self.relative_path = relative_path
        self.occurrences = occurrences


class _Index:
    def __init__(self, documents):
        self.documents = documents


def _defsym(module, rest):
    return f"scip-python python . 0 `{module}`/{rest}"


def test_discover_scip_prefix_from_relative_paths():
    idx = _Index([
        _Doc("apps/config.py", [
            _Occ(_defsym("data.repos.django.django.apps.config", "AppConfig#")),
        ]),
    ])
    assert I.discover_scip_prefix(idx) == "data.repos.django."


def test_discover_scip_prefix_empty_when_no_repo_path():
    # module is just <package>.<relpath>: nothing to strip.
    idx = _Index([
        _Doc("apps/config.py", [
            _Occ(_defsym("django.apps.config", "AppConfig#")),
        ]),
    ])
    assert I.discover_scip_prefix(idx) == ""


def test_discover_scip_prefix_ignores_reference_and_stdlib_occurrences():
    idx = _Index([
        _Doc("apps/config.py", [
            _Occ(_defsym("data.repos.django.django.apps.config", "AppConfig#"),
                 roles=0),  # reference, not a definition -> ignored
            _Occ("scip-python python python-stdlib 3 `os`/getcwd().", roles=1),
            _Occ(_defsym("data.repos.django.django.apps.config", "AppConfig#"),
                 roles=1),  # the real definition
        ]),
    ])
    assert I.discover_scip_prefix(idx) == "data.repos.django."


# --- joined_edge_sets: scope exclusion counted, never a mismatch --------------

def _A(*pairs):
    return [NameEdge(s, d, 1, "bare_name") for s, d in pairs]


def _B(*pairs):
    return [CallEdge(s, d, False, 1) for s, d in pairs]


def test_joined_edge_sets_maps_both_arms_into_one_space():
    a = _A(("django.apps.config.AppConfig::create",
            "django.apps.registry.Apps::populate"))
    b = _B(("data.repos.django.django.apps.config::AppConfig#create().",
            "data.repos.django.django.apps.registry::Apps#populate()."))
    a_set, b_set, stats = I.joined_edge_sets(a, b, "data.repos.django.", "django")
    assert a_set == b_set
    assert stats["arm_a_edges_compared"] == 1
    assert stats["arm_b_edges_compared"] == 1


def test_out_of_scope_arm_a_edges_are_excluded_and_counted_not_mismatched():
    # A test-sourced edge (src outside the django package) is arm B's blind spot,
    # not a name-match error, so it must be excluded from the comparison and
    # tallied separately — never counted as an only_a mismatch.
    a = _A(("tests.foo.Bar::baz", "django.apps.config.AppConfig::create"),
           ("django.apps.config.AppConfig::create",
            "django.apps.registry.Apps::populate"))
    b = _B(("data.repos.django.django.apps.config::AppConfig#create().",
            "data.repos.django.django.apps.registry::Apps#populate()."))
    a_set, b_set, stats = I.joined_edge_sets(a, b, "data.repos.django.", "django")
    assert stats["arm_a_excluded_out_of_scope"] == 1
    assert len(a_set) == 1  # only the django-sourced edge survives
    assert a_set <= b_set  # and it is a genuine match, not a mismatch


def test_joined_edge_sets_excludes_external_arm_b_edges():
    a = _A(("django.m.C::f", "django.m.C::g"))
    b = [CallEdge(
        "data.repos.django.django.m::C#f().", "builtins::str#lower().", True, 1)]
    _, b_set, _ = I.joined_edge_sets(a, b, "data.repos.django.", "django")
    assert b_set == set()


def test_none_src_scope_disables_scoping():
    a = _A(("tests.foo.Bar::baz", "django.apps.config.AppConfig::create"))
    b = _B()
    a_set, _, stats = I.joined_edge_sets(a, b, "data.repos.django.", None)
    assert stats["arm_a_excluded_out_of_scope"] == 0
    assert len(a_set) == 1

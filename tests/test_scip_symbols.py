from friction.scip import symbols as S


FUNC = "scip-python python django 4.2 `django.db.models.query`/QuerySet#filter()."
CLS = "scip-python python django 4.2 `django.db.models.query`/QuerySet#"
STDLIB = "scip-python python python-stdlib 3.11 `builtins`/str#lower()."
BUILTIN_SUPER = "scip-python python python-stdlib 3.11 `builtins`/super#"


def test_function_symbol_parsed():
    s = S.parse_symbol(FUNC)
    assert s.kind == "function"
    assert s.name == "filter"
    assert s.module == "django.db.models.query"
    assert s.is_external is False


def test_class_symbol_parsed():
    s = S.parse_symbol(CLS)
    assert s.kind == "class"
    assert s.name == "QuerySet"


def test_stdlib_symbol_is_external():
    assert S.parse_symbol(STDLIB).is_external is True
    assert S.parse_symbol(BUILTIN_SUPER).is_external is True


def test_local_symbol_is_other():
    assert S.parse_symbol("local 12").kind == "other"


def test_canonical_is_stable_across_versions():
    a = S.parse_symbol(FUNC)
    b = S.parse_symbol(FUNC.replace("4.2", "5.0"))
    assert S.canonical(a, "django/db/models/query.py") == \
           S.canonical(b, "django/db/models/query.py")


def test_canonical_distinguishes_same_name_in_different_modules():
    other = FUNC.replace("django.db.models.query", "django.contrib.admin.views")
    assert S.canonical(S.parse_symbol(FUNC), "a.py") != \
           S.canonical(S.parse_symbol(other), "b.py")


def test_canonical_survives_a_missing_path():
    assert S.canonical(S.parse_symbol(FUNC), None).endswith("QuerySet#filter().")


# --- Real scip-python shapes (verified against django_full.scip) ---
# scip-python only backticks module descriptors that contain special chars
# (e.g. a dot). Single-segment modules like `builtins` are emitted WITHOUT
# backticks. The plan's fixtures wrongly backtick `builtins`; real output does
# not. 929/969 stdlib symbols and 80 django-package symbols take this form.
REAL_STDLIB_FUNC = "scip-python python python-stdlib 3.11 builtins/str#lower()."
REAL_STDLIB_CLASS = "scip-python python python-stdlib 3.11 sre_constants/error#"
REAL_PROJECT_NOBT = "scip-python python django 2.2 _weakref/ReferenceType#"


def test_real_stdlib_function_without_backticks():
    s = S.parse_symbol(REAL_STDLIB_FUNC)
    assert s.kind == "function"
    assert s.name == "lower"
    assert s.module == "builtins"
    assert s.is_external is True


def test_real_stdlib_class_without_backticks():
    s = S.parse_symbol(REAL_STDLIB_CLASS)
    assert s.kind == "class"
    assert s.name == "error"
    assert s.module == "sre_constants"


def test_real_project_class_without_backticks():
    s = S.parse_symbol(REAL_PROJECT_NOBT)
    assert s.kind == "class"
    assert s.name == "ReferenceType"
    assert s.module == "_weakref"


def test_canonical_uses_module_for_non_backticked_symbol():
    # No "?::" fallback: a real module was recovered, so identity is stable.
    c = S.canonical(S.parse_symbol(REAL_STDLIB_FUNC), None)
    assert c == "builtins::str#lower()."

"""ConfigKey nodes and READS_CONFIG edges from settings.<NAME> reads."""
from friction import config_keys as C
from friction.scip import schema

DEFINITION_ROLE = schema.DEFINITION_ROLE

SETTINGS = "scip-python python django v `data.repos.django.django.conf`/settings."
F_VIEW = "scip-python python django v `app.views`/render()."
CLASS_V = "scip-python python django v `app.views`/View#"


def _index(docs):
    pb = schema.scip_pb2()
    idx = pb.Index()
    for path, occs in docs.items():
        d = idx.documents.add()
        d.relative_path = path
        for sym, roles, rng in occs:
            o = d.occurrences.add()
            o.symbol = sym
            o.symbol_roles = roles
            o.range.extend(rng)
            if roles & DEFINITION_ROLE:
                # definitions carry an enclosing_range spanning their body; the
                # test passes a 4-element range that doubles as that span.
                o.enclosing_range.extend(rng)
    return idx


def _reader(lines_by_path):
    return lambda path: lines_by_path.get(path)


def test_is_settings_symbol_accepts_only_the_conf_settings_object():
    assert C.is_settings_symbol(SETTINGS) is True
    assert C.is_settings_symbol(F_VIEW) is False
    # a term named settings on some other module is not django.conf.settings
    assert C.is_settings_symbol(
        "scip-python python django v `app.models`/settings.") is False


def test_extract_reads_settings_attribute_from_source():
    idx = _index({"app/views.py": [
        (F_VIEW, DEFINITION_ROLE, [0, 0, 3, 0]),
        (SETTINGS, 0, [1, 8, 1, 16]),
    ]})
    lines = {"app/views.py": ["def render():", "    x = settings.DEBUG"]}
    reads, stats = C.extract_config_reads(idx, _reader(lines))
    assert reads == [C.ConfigRead("app.views::render().", "DEBUG")]
    assert stats["reads_resolved"] == 1


def test_distinct_config_key_created_once_per_name():
    idx = _index({"app/views.py": [
        (F_VIEW, DEFINITION_ROLE, [0, 0, 5, 0]),
        (SETTINGS, 0, [1, 8, 1, 16]),
        (SETTINGS, 0, [2, 8, 2, 16]),
        (SETTINGS, 0, [3, 8, 3, 16]),
    ]})
    lines = {"app/views.py": [
        "def render():", "    a = settings.DEBUG", "    b = settings.DEBUG",
        "    c = settings.SECRET_KEY"]}
    reads, _ = C.extract_config_reads(idx, _reader(lines))
    assert C.config_keys(reads) == ["DEBUG", "SECRET_KEY"]


def test_reads_config_pairs_are_deduped_per_function_and_key():
    idx = _index({"app/views.py": [
        (F_VIEW, DEFINITION_ROLE, [0, 0, 5, 0]),
        (SETTINGS, 0, [1, 8, 1, 16]),
        (SETTINGS, 0, [2, 8, 2, 16]),
    ]})
    lines = {"app/views.py": [
        "def render():", "    a = settings.DEBUG", "    b = settings.DEBUG"]}
    reads, _ = C.extract_config_reads(idx, _reader(lines))
    assert C.reads_config_pairs(reads) == [("app.views::render().", "DEBUG")]


def test_module_scope_read_makes_a_key_but_no_edge():
    # a settings read at module scope has no enclosing function.
    idx = _index({"app/settings_use.py": [
        (SETTINGS, 0, [0, 4, 0, 12]),
    ]})
    lines = {"app/settings_use.py": ["X = settings.INSTALLED_APPS"]}
    reads, stats = C.extract_config_reads(idx, _reader(lines))
    assert C.config_keys(reads) == ["INSTALLED_APPS"]
    assert C.reads_config_pairs(reads) == []
    assert stats["module_scope_reads"] == 1


def test_missing_source_is_counted_not_crashed():
    idx = _index({"app/views.py": [
        (SETTINGS, 0, [1, 8, 1, 16]),
    ]})
    reads, stats = C.extract_config_reads(idx, _reader({}))  # no source available
    assert reads == []
    assert stats["missing_source"] == 1


def test_unparsed_attribute_is_counted():
    # a settings reference NOT followed by .NAME (e.g. `settings` passed as arg)
    idx = _index({"app/views.py": [
        (F_VIEW, DEFINITION_ROLE, [0, 0, 3, 0]),
        (SETTINGS, 0, [1, 10, 1, 18]),
    ]})
    lines = {"app/views.py": ["def render():", "    use(settings)"]}
    reads, stats = C.extract_config_reads(idx, _reader(lines))
    assert reads == []
    assert stats["unparsed_attribute"] == 1

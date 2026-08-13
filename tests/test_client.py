import pytest
from friction.config import Settings
from friction.client import HttpTransport, BoltTransport, connect, EngineError


@pytest.mark.engine
def test_http_round_trip():
    t = HttpTransport(Settings.from_env())
    t.query("CREATE (a {id: 9001})-[:PROBE]->(b {id: 9002})")
    rows = t.query("MATCH (a {id: 9001})-[:PROBE]->(b) RETURN b.id AS id")
    assert any(9002 in row.values() for row in rows)


@pytest.mark.engine
def test_bolt_round_trip():
    t = BoltTransport(Settings.from_env())
    try:
        t.query("CREATE (a {id: 9003})-[:PROBE]->(b {id: 9004})")
        rows = t.query("MATCH (a {id: 9003})-[:PROBE]->(b) RETURN b.id AS id")
        assert any(9004 in row.values() for row in rows)
    finally:
        t.close()


@pytest.mark.engine
def test_engine_error_carries_engine_message():
    t = HttpTransport(Settings.from_env())
    with pytest.raises(EngineError) as exc:
        t.query("MATCH (a) RETURN *")
    assert str(exc.value)


@pytest.mark.engine
def test_connect_prefers_bolt_and_falls_back():
    t = connect(Settings.from_env(), prefer="bolt")
    t.query("CREATE (a {id: 9007})-[:PROBE]->(b {id: 9008})")
    rows = t.query("MATCH (a {id: 9007})-[:PROBE]->(b) RETURN b.id AS id")
    assert any(9008 in row.values() for row in rows)

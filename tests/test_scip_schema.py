from pathlib import Path

import pytest

from friction.scip import schema


def test_ensure_compiled_produces_importable_module(tmp_path):
    out = schema.ensure_compiled(out_dir=tmp_path)
    assert out.exists()
    assert out.name == "scip_pb2.py"


def test_definition_role_bit_is_one():
    assert schema.DEFINITION_ROLE == 0x1


def test_load_index_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        schema.load_index(tmp_path / "nope.scip")


def test_index_roundtrip(tmp_path):
    schema.ensure_compiled(out_dir=tmp_path)
    pb = schema.scip_pb2()
    idx = pb.Index()
    doc = idx.documents.add()
    doc.relative_path = "a/b.py"
    occ = doc.occurrences.add()
    occ.symbol = "scip-python python . . `a.b`/f()."
    occ.symbol_roles = schema.DEFINITION_ROLE
    blob = tmp_path / "x.scip"
    blob.write_bytes(idx.SerializeToString())
    back = schema.load_index(blob)
    assert back.documents[0].relative_path == "a/b.py"
    assert back.documents[0].occurrences[0].symbol_roles == schema.DEFINITION_ROLE

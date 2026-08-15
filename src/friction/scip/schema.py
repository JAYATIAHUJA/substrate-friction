"""Compile and load the SCIP protobuf schema.

There is no pip package for the SCIP schema and the npm module ships only
compiled JS, so the canonical `scip.proto` is vendored and compiled on demand
with grpc_tools.protoc.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

VENDOR_PROTO = Path(__file__).resolve().parents[3] / "vendor" / "scip.proto"
GENERATED = Path(__file__).resolve().parent / "_generated"

# scip.proto: SymbolRole.Definition = 1
DEFINITION_ROLE = 0x1

_MODULE: Any = None


def ensure_compiled(proto_path: Path = VENDOR_PROTO, out_dir: Path = GENERATED) -> Path:
    proto_path, out_dir = Path(proto_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").touch()
    target = out_dir / "scip_pb2.py"
    if target.exists() and target.stat().st_mtime >= proto_path.stat().st_mtime:
        return target
    subprocess.run(
        [sys.executable, "-m", "grpc_tools.protoc",
         f"-I{proto_path.parent}", f"--python_out={out_dir}", proto_path.name],
        check=True, capture_output=True,
    )
    if not target.exists():
        raise RuntimeError(f"protoc produced no {target}")
    return target


def scip_pb2() -> Any:
    """Import the compiled module, compiling it first if needed."""
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    target = ensure_compiled()
    spec = importlib.util.spec_from_file_location("scip_pb2", target)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scip_pb2"] = module
    spec.loader.exec_module(module)
    _MODULE = module
    return module


def load_index(path: Path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    index = scip_pb2().Index()
    index.ParseFromString(path.read_bytes())
    return index

"""Transports for the open-source HydraDB engine.

Two transports exist because they have different capabilities:

* HTTP is the documented, certain path (`POST /v1/graphs/{graph}/query` with a
  Bearer token). Whether it accepts a `params` object is established by the
  capability probe in Task 3.
* Bolt is required for `UNWIND $rows`, whose input "has to be a parameter
  holding a list of maps" and which is "only accepted via client transport".
"""

from __future__ import annotations

from typing import Any

import httpx
from neo4j import GraphDatabase, basic_auth, bearer_auth

from friction.config import Settings


class EngineError(RuntimeError):
    """Raised with the engine's own error text, unmodified."""


def _unwrap(cell: Any) -> Any:
    """Unwrap the engine's typed-cell envelope, e.g. {"type": "vertex_id",
    "value": 2} -> 2. Scalars pass through untouched."""
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return cell


class HttpTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(timeout=120.0)

    @property
    def name(self) -> str:
        return "http"

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        body: dict[str, Any] = {"cell_id": self.settings.cell_id, "query": cypher}
        if params is not None:
            body["params"] = params
        resp = self._client.post(
            f"{self.settings.http_url}/v1/graphs/{self.settings.graph}/query",
            headers={
                "Authorization": f"Bearer {self.settings.token}",
                "X-Graph-Namespace": self.settings.namespace,
                "Content-Type": "application/json",
            },
            json=body,
        )
        if resp.status_code >= 400:
            raise EngineError(self._error_text(resp))
        payload = resp.json()
        if isinstance(payload, dict) and "rows" in payload:
            columns = payload.get("columns") or []
            rows = payload.get("rows") or []
            out: list[dict] = []
            for row in rows:
                if isinstance(row, list):
                    out.append({col: _unwrap(val) for col, val in zip(columns, row)})
                elif isinstance(row, dict):
                    out.append({k: _unwrap(v) for k, v in row.items()})
                else:
                    out.append({"value": _unwrap(row)})
            return out
        if isinstance(payload, list):
            return payload
        return [payload]

    @staticmethod
    def _error_text(resp: httpx.Response) -> str:
        """Return the engine's own message text. The engine reports failures as
        {"error": {"code": ..., "message": ...}}; fall back to the raw body."""
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001 - non-JSON error body
            return resp.text.strip()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            if isinstance(err, str) and err:
                return err
        return resp.text.strip()

    def close(self) -> None:
        self._client.close()


class BoltTransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._driver = None
        last: Exception | None = None
        for auth in (bearer_auth(settings.token),
                     basic_auth("neo4j", settings.token),
                     None):
            try:
                driver = GraphDatabase.driver(settings.bolt_uri, auth=auth)
                driver.verify_connectivity()
                self._driver = driver
                self._auth_mode = type(auth).__name__ if auth else "none"
                break
            except Exception as exc:  # noqa: BLE001 - probing auth modes
                last = exc
        if self._driver is None:
            raise EngineError(f"could not open Bolt session: {last}")

    @property
    def name(self) -> str:
        return "bolt"

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict]:
        try:
            with self._driver.session() as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except Exception as exc:  # noqa: BLE001 - surface engine text verbatim
            raise EngineError(str(exc)) from exc

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()


def connect(settings: Settings, prefer: str = "bolt"):
    """Return a working transport, preferring `prefer`, falling back to the other."""
    order = [BoltTransport, HttpTransport] if prefer == "bolt" else [HttpTransport, BoltTransport]
    last: Exception | None = None
    for cls in order:
        try:
            transport = cls(settings)
            # Liveness probe: the engine's row executor only supports
            # MATCH ... RETURN queries ("RETURN 1 AS one" is rejected with
            # "row execution supports MATCH ... RETURN queries"). A MATCH by id
            # is read-only and accepted, so it verifies the transport can
            # execute a query without mutating the graph.
            transport.query("MATCH (n {id: 0}) RETURN n.id AS id")
            return transport
        except Exception as exc:  # noqa: BLE001 - transport selection
            last = exc
    raise EngineError(f"no usable transport: {last}")

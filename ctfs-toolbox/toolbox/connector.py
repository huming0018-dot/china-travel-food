"""Connector registry (M1): built-in connectors + installed plugins via
importlib.metadata.entry_points.

Loading rules (review gate):
- built-ins are a fixed whitelist of module names in this file (no arbitrary
  import paths, no exec/eval);
- plugins are loaded only through importlib.metadata entry points declared by
  installed distributions (group "ctfs.connectors");
- each connector returns an immutable Attempt; failures are returned as failed
  attempts (never raised as surprises) so the crawler can persist receipts.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .validators import stamp

# Fixed whitelist of built-in connectors: (name, module, class)
_BUILTIN_SPECS = (
    ("http-public", "toolbox.connector_http", "HttpPublicConnector"),
    ("snapshot-file", "toolbox.connector_snapshot", "SnapshotFileConnector"),
)

ENTRY_POINT_GROUP = "ctfs.connectors"


class ConnectorError(Exception):
    """Rejected or failed connector execution."""


@dataclass(frozen=True)
class FetchContext:
    """Everything a connector is allowed to know for one fetch."""
    source: dict
    project_dir: Path
    timeout_seconds: float = 30.0
    max_bytes: int = 1_000_000
    tool_version: str = "ctfs-toolbox:0.3.0"


@dataclass(frozen=True)
class Attempt:
    """Immutable result of one fetch; persisted by the crawler as a receipt."""
    ok: bool
    source_id: str
    url: str
    connector: str
    started_at: str
    finished_at: str
    code: int | None = None
    bytes_count: int = 0
    sha256: str | None = None
    body: bytes | None = None
    error: str | None = None
    error_kind: str | None = None
    note: str | None = None
    headers: dict | None = None

    def receipt(self) -> dict:
        """Receipt fields accepted by SqliteStorage.append_receipt."""
        return {
            "code": self.code,
            "bytes": self.bytes_count,
            "at": self.finished_at,
            "note": (self.note or "") if self.ok else f"error={self.error_kind}: {self.error}",
        }


class Connector:
    """Base class for fetch connectors."""
    name: str = "base"

    def fetch(self, ctx: FetchContext) -> Attempt:  # pragma: no cover - abstract
        raise NotImplementedError


def load_connectors() -> dict[str, Connector]:
    """Build the connector registry: fixed built-ins first, then plugins."""
    connectors: dict[str, Connector] = {}
    for name, module, class_name in _BUILTIN_SPECS:
        mod = importlib.import_module(module)  # fixed whitelist only
        connectors[name] = getattr(mod, class_name)()
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        eps = ()
    for ep in eps:
        if ep.name in connectors:
            continue  # built-in wins; a plugin may not shadow it
        try:
            cls = ep.load()
            instance = cls()
            if not callable(getattr(instance, "fetch", None)):
                raise ConnectorError("installed connector has no fetch method")
        except Exception as exc:  # broken plugin must not break the registry
            connectors[f"{ep.name}:broken"] = _BrokenConnector(ep.name, str(exc))
            continue
        connectors[ep.name] = instance
    return connectors


class _BrokenConnector(Connector):
    """Placeholder for a plugin that fails to load; surfaces the failure."""
    def __init__(self, name: str, error: str):
        self.name = name
        self._error = error

    def fetch(self, ctx: FetchContext) -> Attempt:
        return _failed(ctx.source.get("source_id", "?"), ctx.source.get("url", "?"),
                       self.name, "plugin-load-failed", self._error)


def _failed(source_id: str, url: str, connector: str, kind: str, error: str) -> Attempt:
    now = stamp()
    return Attempt(ok=False, source_id=source_id, url=url, connector=connector,
                   started_at=now, finished_at=now, error=error, error_kind=kind)

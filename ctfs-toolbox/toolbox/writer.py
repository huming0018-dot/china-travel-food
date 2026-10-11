"""Generic record wrapping / append / read-back for ODS/DW/APP.

Shared by CLI and SDK so the tool itself satisfies the public ODS/DW/APP
schemas (schemaVersion/project_id/layer/record_id/parent_ref/content;
APP adds schema_kind audit|view) — acceptance scripts never hand-roll records.
"""
from __future__ import annotations

import hashlib
import json

from toolbox.storage import StorageError


class WriterError(ValueError):
    pass


def record_id(kind: str, pack_id: str, revision: int, title: str | int) -> str:
    h = hashlib.sha256(json.dumps([kind, pack_id, revision, title], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{pack_id}:{revision}:{h}"


def wrap_record(layer: str, project_id: str, record_id: str, parent_ref: dict,
                content: dict, schema_kind: str | None = None) -> dict:
    rec = {
        "schemaVersion": "0.2.0",
        "project_id": project_id,
        "layer": layer,
        "record_id": record_id,
        "parent_ref": parent_ref,
        "content": content,
    }
    if schema_kind is not None:
        rec["schema_kind"] = schema_kind
    return rec


def append(storage, project_id: str, layer: str, record_id: str, parent_ref: dict,
           content: dict, schema_kind: str | None = None) -> int:
    wrapped = wrap_record(layer, project_id, record_id, parent_ref, content, schema_kind)
    return storage.append_version(project_id, layer, wrapped)


def read_latest(storage, project_id: str, layer: str, record_id: str) -> dict:
    try:
        return storage.read(project_id, layer, record_id)
    except StorageError as exc:
        raise WriterError(f"{layer} {record_id} read failed: {exc}") from exc


def content_digest(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False,
                   allow_nan=False).encode()).hexdigest()

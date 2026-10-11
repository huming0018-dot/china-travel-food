"""Layered Storage: RAW / ODS / DW / APP (audit | view).

P0 isolated backend: SQLite. PostgresStorage is a documented adapter slot
(production acceptance is NOT part of P0; see PRD / AGENTS.md).
Trust boundaries:
- RAW stores the real payload bytes; content_hash is ALWAYS recomputed from the
  stored bytes and verified on read. A caller-supplied content_hash is checked
  against the actual bytes and rejected when mismatched.
- Every write/append entry point runs the versioned schema validator.
- parent_ref must pin the parent layer/project/record/version; existence and
  parent hash are verified; failures roll back (no partial writes).
- lineage keeps the real source values (project/source_url/source_hash/batch/
  captured_at) inherited from the parent; processing time is stored separately.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .schema import SchemaError, validate_against

from . import __version__
TOOL_VERSION = "ctfs-toolbox:" + __version__

LAYER_RAW = "RAW"
LAYER_ODS = "ODS"
LAYER_DW = "DW"
LAYER_APP = "APP"
LAYERS = (LAYER_RAW, LAYER_ODS, LAYER_DW, LAYER_APP)
_PARENT_LAYER = {LAYER_ODS: LAYER_RAW, LAYER_DW: LAYER_ODS, LAYER_APP: LAYER_DW}
_SCHEMA_FOR_LAYER = {LAYER_ODS: "clean", LAYER_DW: "scored"}
_APP_KINDS = ("audit", "view")
_RECEIPT_FIELDS = {"code", "bytes", "at", "note"}
_RAW_ID_PREFIX = "raw:"


class StorageError(Exception):
    pass


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_bytes(payload: Any) -> tuple[bytes, str]:
    """Serialize payload to canonical bytes; returns (bytes, kind)."""
    if isinstance(payload, bytes):
        return payload, "bytes"
    if isinstance(payload, str):
        return payload.encode("utf-8"), "text"
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"), "json"


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class Storage(ABC):
    @abstractmethod
    def write_raw(self, project_id: str, record: dict, record_id: str | None = None) -> str: ...
    @abstractmethod
    def append_receipt(self, project_id: str, raw_id: str, receipt: dict) -> int: ...
    @abstractmethod
    def append_version(self, project_id: str, layer: str, record: dict) -> int: ...
    @abstractmethod
    def read(self, project_id: str, layer: str, record_id: str, version: int | None = None) -> dict: ...
    @abstractmethod
    def verify_lineage(self, project_id: str, layer: str, record_id: str, version: int) -> bool: ...
    @abstractmethod
    def close(self) -> None: ...

class SqliteStorage(Storage):
    """P0 isolated backend (explicitly NOT the PRD Supabase production target)."""

    def __init__(self, path: Path | str, *, read_only: bool = False):
        if type(read_only) is not bool:raise StorageError("read_only must be boolean")
        if read_only:
            db=Path(path)
            if db.is_symlink() or not db.is_file():raise StorageError("read-only database must already exist")
            self._conn=sqlite3.connect(db.absolute().as_uri()+"?mode=ro",uri=True)
            self._conn.isolation_level=None
            try:
                self._conn.execute("PRAGMA query_only=ON")
                for table in ("raw_records","versions","receipts"):self._conn.execute("SELECT 1 FROM "+table+" LIMIT 0")
            except Exception:
                self._conn.close();raise StorageError("read-only database schema unavailable")
        else:
            self._conn = sqlite3.connect(str(path))
            self._conn.isolation_level = None
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS raw_records ("
            " project_id TEXT NOT NULL, id TEXT NOT NULL, layer TEXT NOT NULL,"
            " payload BLOB NOT NULL, payload_kind TEXT NOT NULL, content_hash TEXT NOT NULL,"
            " source_url TEXT, source_hash TEXT, batch TEXT, captured_at TEXT,"
            " lineage TEXT NOT NULL, created_at TEXT NOT NULL,"
            " PRIMARY KEY (project_id, id));"
            "CREATE TABLE IF NOT EXISTS receipts ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,"
            " raw_id TEXT NOT NULL, receipt TEXT NOT NULL, created_at TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS versions ("
            " project_id TEXT NOT NULL, id TEXT NOT NULL, layer TEXT NOT NULL,"
            " schema_kind TEXT NOT NULL, version INTEGER NOT NULL,"
            " content_json TEXT NOT NULL, content_hash TEXT NOT NULL,"
            " parent_ref TEXT, lineage TEXT NOT NULL, created_at TEXT NOT NULL,"
            " PRIMARY KEY (project_id, id, layer, version));"
            "CREATE INDEX IF NOT EXISTS idx_raw_proj ON raw_records(project_id);"
            "CREATE INDEX IF NOT EXISTS idx_ver_proj ON versions(project_id, layer);"
        )
    def _kind_for(self, layer: str, record: dict) -> str:
        if layer == LAYER_ODS or layer == LAYER_DW:
            return _SCHEMA_FOR_LAYER[layer]
        if layer == LAYER_APP:
            kind = record.get("schema_kind")
            if kind not in _APP_KINDS:
                raise StorageError("APP layer record must set schema_kind to 'audit' or 'view'")
            return kind
        raise StorageError(f"append_version layer must be ODS/DW/APP, got {layer}")

    # ---- RAW -----------------------------------------------------------------

    def _schema(self, kind: str, record: dict) -> None:
        try:
            validate_against(kind, record)
        except SchemaError as exc:
            raise StorageError(str(exc)) from exc

    def write_raw(self, project_id: str, record: dict, record_id: str | None = None) -> str:
        self._schema("raw", record)
        if record["project_id"] != project_id or record["lineage"]["project"] != project_id:
            raise StorageError("raw project scope mismatch")
        for field in ("source_url", "source_hash", "batch", "captured_at"):
            if record[field] != record["lineage"][field]:
                raise StorageError("raw lineage mismatch: " + field)
        try:
            payload, kind = _stable_bytes(record["payload"])
        except (TypeError, ValueError) as exc:
            raise StorageError("payload must be finite JSON, text or bytes") from exc
        actual_hash = _sha256(payload)
        if record["source_hash"] != actual_hash or record.get("content_hash", actual_hash) != actual_hash:
            raise StorageError("raw hashes must describe the exact stored payload bytes")
        # Acquisition identity includes origin/time/batch; equal bytes from another
        # origin cannot silently inherit the first origin's attribution.
        origin = {f: record[f] for f in ("source_url", "source_hash", "batch", "captured_at")}
        origin_bytes, _ = _stable_bytes(origin)
        rid = record_id or ("raw:" + project_id + ":" + _sha256(origin_bytes))
        lineage_json = json.dumps(record["lineage"],sort_keys=True,ensure_ascii=False,allow_nan=False)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            old = self._conn.execute(
                "SELECT payload,content_hash,source_url,source_hash,batch,captured_at,lineage,payload_kind FROM raw_records WHERE project_id=? AND id=?",
                (project_id,rid)).fetchone()
            if old:
                if (bytes(old[0]),old[1],old[2],old[3],old[4],old[5],old[6],old[7]) != (
                    payload,actual_hash,record["source_url"],record["source_hash"],record["batch"],record["captured_at"],lineage_json,kind):
                    raise StorageError("immutable raw id conflict")
                self._conn.execute("COMMIT")
                return rid
            self._conn.execute(
                "INSERT INTO raw_records (project_id,id,layer,payload,payload_kind,content_hash,source_url,source_hash,batch,captured_at,lineage,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id,rid,LAYER_RAW,payload,kind,actual_hash,record["source_url"],record["source_hash"],record["batch"],record["captured_at"],lineage_json,_now_utc()))
            self._conn.execute("COMMIT")
            return rid
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def append_receipt(self, project_id: str, raw_id: str, receipt: dict) -> int:
        self._schema("receipt",receipt)
        try:
            receipt_json = json.dumps(receipt,sort_keys=True,ensure_ascii=False,allow_nan=False)
        except (TypeError,ValueError) as exc:
            raise StorageError("receipt must contain only finite JSON") from exc
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT id FROM raw_records WHERE id=? AND project_id=?", (raw_id, project_id)
            ).fetchone()
            if row is None:
                raise StorageError("receipt target raw not found for this project")
            cursor = self._conn.execute(
                "INSERT INTO receipts (project_id, raw_id, receipt, created_at) VALUES (?,?,?,?)",
                (project_id, raw_id, receipt_json, _now_utc()),
            )
            receipt_seq = int(cursor.lastrowid)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return receipt_seq
    def append_version(self, project_id: str, layer: str, record: dict, expected_version: int | None = None) -> int:
        if layer == LAYER_RAW:
            raise StorageError("RAW is immutable; use write_raw")
        kind = self._kind_for(layer,record)
        self._schema(kind,record)
        if record["project_id"] != project_id or record["layer"] != layer:
            raise StorageError("version project/layer scope mismatch")
        try:
            content_bytes, _ = _stable_bytes(record)
        except (TypeError,ValueError) as exc:
            raise StorageError("version must be finite JSON") from exc
        content_json = content_bytes.decode("utf-8")
        content_hash = _sha256(content_bytes)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            parent = self._resolve_parent(project_id,layer,record["parent_ref"])
            if not self.verify_lineage(project_id,parent["layer"],parent["record_id"],parent.get("version")):
                raise StorageError("parent integrity/lineage is broken")
            if record["parent_ref"]["hash"] != parent["content_hash"]:
                raise StorageError("pinned parent hash mismatch")
            lineage = self._inherit_lineage(parent)
            rid = record["record_id"]
            same = self._conn.execute(
                "SELECT version FROM versions WHERE project_id=? AND layer=? AND id=? AND content_hash=? ORDER BY version LIMIT 1",
                (project_id,layer,rid,content_hash)).fetchone()
            if same:
                self._conn.execute("COMMIT")
                return int(same[0])
            latest = self._conn.execute(
                "SELECT COALESCE(MAX(version),0) FROM versions WHERE project_id=? AND layer=? AND id=?",
                (project_id,layer,rid)).fetchone()[0]
            if expected_version is not None and (type(expected_version) is not int or expected_version != latest):
                raise StorageError("stale expected_version conflict")
            next_version = latest + 1
            self._conn.execute(
                "INSERT INTO versions(project_id,id,layer,schema_kind,version,content_json,content_hash,parent_ref,lineage,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (project_id,rid,layer,kind,next_version,content_json,content_hash,
                 json.dumps(record["parent_ref"],sort_keys=True,ensure_ascii=False,allow_nan=False),
                 json.dumps(lineage,sort_keys=True,ensure_ascii=False,allow_nan=False),_now_utc()))
            self._conn.execute("COMMIT")
            return next_version
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _resolve_parent(self, project_id: str, layer: str, parent_ref: dict) -> dict:
        expected_layer = _PARENT_LAYER.get(layer)
        if expected_layer is None:
            raise StorageError(f"layer {layer} has no defined parent layer")
        if not isinstance(parent_ref, dict):
            raise StorageError("parent_ref must be a dict")
        p_layer = parent_ref.get("layer")
        p_project = parent_ref.get("project_id")
        p_id = parent_ref.get("record_id")
        if p_layer != expected_layer or p_project != project_id or not p_id:
            raise StorageError(
                f"parent_ref must be layer={expected_layer} project={project_id} with record_id"
            )
        if expected_layer == LAYER_RAW:
            row = self._conn.execute(
                "SELECT content_hash FROM raw_records WHERE id=? AND project_id=?",
                (p_id, project_id),
            ).fetchone()
            if row is None:
                raise StorageError(f"parent raw record {p_id} not found")
            return {"layer": LAYER_RAW, "project_id": project_id, "record_id": p_id,
                    "version": None, "content_hash": row[0], "lineage": self._raw_lineage(project_id, p_id)}
        version = parent_ref.get("version")
        if type(version) is not int or version < 1:
            raise StorageError("parent version must be pinned (integer >= 1) for ODS/DW parents")
        row = self._conn.execute(
            "SELECT content_hash, lineage FROM versions WHERE id=? AND project_id=? AND layer=? AND version=?",
            (p_id, project_id, expected_layer, version),
        ).fetchone()
        if row is None:
            raise StorageError(f"parent {expected_layer} {p_id} version {version} not found (unknown version)")
        return {"layer": expected_layer, "project_id": project_id, "record_id": p_id,
                "version": version, "content_hash": row[0], "lineage": json.loads(row[1])}

    def _raw_lineage(self, project_id: str, raw_id: str) -> dict:
        row = self._conn.execute(
            "SELECT lineage FROM raw_records WHERE project_id=? AND id=?", (project_id, raw_id)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def _inherit_lineage(self, parent: dict, writer_version: str = TOOL_VERSION) -> dict:
        base = dict(parent.get("lineage") or {})
        # Keep REAL source values; never overwrite with processing time.
        lineage = {
            "project": base.get("project"),
            "source_url": base.get("source_url"),
            "source_hash": base.get("source_hash"),
            "batch": base.get("batch"),
            "captured_at": base.get("captured_at"),
            "steps": list(base.get("steps") or []),
            "tool_versions": list(base.get("tool_versions") or []),
        }
        if not lineage["project"] or not lineage["source_url"] or not lineage["captured_at"]:
            raise StorageError("parent lineage missing real project/source_url/captured_at")
        lineage["steps"].append(f"{parent['layer'].lower()}:{parent['record_id'][:16]}")
        lineage["tool_versions"].append(writer_version)
        return lineage

    # ---- reads & lineage -----------------------------------------------------

    def read(self, project_id: str, layer: str, record_id: str, version: int | None = None) -> dict:
        if layer not in LAYERS:
            raise StorageError(f"unknown layer {layer}")
        if layer == LAYER_RAW:
            row = self._conn.execute(
                "SELECT id, project_id, payload, payload_kind, content_hash, source_url,"
                " source_hash, batch, captured_at, lineage FROM raw_records"
                " WHERE id=? AND project_id=?",
                (record_id, project_id),
            ).fetchone()
            if row is None:
                raise StorageError("raw record not found for project")
            _id, _proj, payload_blob, kind, content_hash, source_url, source_hash, batch, captured_at, lineage = row
            if _sha256(bytes(payload_blob)) != content_hash:
                raise StorageError("raw payload hash mismatch on read (integrity)")
            if kind not in ("text","bytes","json"):
                raise StorageError("unknown durable raw payload kind")
            decoded=self._decode_payload(payload_blob,kind)
            raw_lineage=json.loads(lineage)
            check={"schemaVersion":"0.2.0","project_id":_proj,"layer":LAYER_RAW,
                   "payload":decoded,"source_url":source_url,"source_hash":source_hash,
                   "batch":batch,"captured_at":captured_at,"lineage":raw_lineage}
            self._schema("raw",check)
            if raw_lineage["project"]!=project_id or source_hash!=content_hash or any(
                check[f]!=raw_lineage[f] for f in ("source_url","source_hash","batch","captured_at")):
                raise StorageError("durable raw origin/lineage/hash mismatch")
            return {
                "record_id": _id, "project_id": _proj, "layer": LAYER_RAW,
                "payload": self._decode_payload(payload_blob, kind),
                "content_hash": content_hash, "source_url": source_url,
                "source_hash": source_hash, "batch": batch, "captured_at": captured_at,
                "lineage": json.loads(lineage),
            }
        if version is None:
            row = self._conn.execute(
                "SELECT MAX(version) FROM versions WHERE id=? AND project_id=? AND layer=?",
                (record_id, project_id, layer),
            ).fetchone()
            version = row[0] if row and row[0] else None
        if version is None:
            raise StorageError("record not found")
        row = self._conn.execute(
            "SELECT id, project_id, layer, schema_kind, version, content_json, content_hash,"
            " parent_ref, lineage FROM versions WHERE id=? AND project_id=? AND layer=? AND version=?",
            (record_id, project_id, layer, version),
        ).fetchone()
        if row is None:
            raise StorageError("versioned record not found")
        _id, _proj, _layer, schema_kind, ver, content_json, content_hash, parent_ref, lineage = row
        if _sha256(content_json.encode("utf-8")) != content_hash:
            raise StorageError("version content hash mismatch on read (integrity)")
        if not self.verify_lineage(project_id,layer,record_id,ver):
            raise StorageError("durable version lineage mismatch on read")
        out = json.loads(content_json)
        out["content_hash"] = content_hash
        out["version"] = ver
        out["lineage"] = json.loads(lineage)
        out["parent_ref"] = json.loads(parent_ref) if parent_ref else None
        return out

    @staticmethod
    def _decode_payload(blob: bytes, kind: str) -> Any:
        if kind == "bytes":
            return bytes(blob)
        if kind == "text":
            return blob.decode("utf-8")
        return json.loads(blob.decode("utf-8"))

    def verify_lineage(self, project_id: str, layer: str, record_id: str, version: int | None) -> bool:
        try:
            if layer == LAYER_RAW:
                raw = self.read(project_id,layer,record_id)
                fields = ("source_url","source_hash","batch","captured_at")
                return (raw["lineage"]["project"] == project_id and
                        raw["source_hash"] == raw["content_hash"] and
                        all(raw[f] == raw["lineage"].get(f) for f in fields))
            if layer not in _PARENT_LAYER or type(version) is not int or version < 1:
                return False
            row = self._conn.execute(
                "SELECT content_json,content_hash,parent_ref,lineage FROM versions WHERE project_id=? AND layer=? AND id=? AND version=?",
                (project_id,layer,record_id,version)).fetchone()
            if not row or _sha256(row[0].encode("utf-8")) != row[1]:
                return False
            record,parent_ref,lineage = json.loads(row[0]),json.loads(row[2]),json.loads(row[3])
            self._schema(self._kind_for(layer,record),record)
            if record["project_id"] != project_id or record["layer"] != layer or record["record_id"] != record_id or record["parent_ref"] != parent_ref:
                return False
            parent = self._resolve_parent(project_id,layer,parent_ref)
            if parent_ref["hash"] != parent["content_hash"] or not lineage.get("tool_versions") or lineage != self._inherit_lineage(parent, lineage["tool_versions"][-1]):
                return False
            return self.verify_lineage(project_id,parent["layer"],parent["record_id"],parent.get("version"))
        except (StorageError,KeyError,TypeError,ValueError):
            return False

    def close(self) -> None:
        self._conn.close()

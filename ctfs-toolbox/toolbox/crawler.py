"""Crawler SDK (M1, P1-REPAIR-02).

Runs registered connectors against manifest sources with a durable ledger:
- budget (max_requests / max_bytes / per_request_max_bytes) is reserved inside
  one BEGIN IMMEDIATE transaction: read + validate + deduct + write a PENDING
  attempt + commit. Concurrent crawlers can never overspend.
- per-source max_bytes is validated against the per-request cap (a source can
  never bypass the single-request limit).
- the pending attempt is persisted BEFORE any external call and committed;
  a crash leaves it visible; on reopen, leftover pending attempts are marked
  failed/unknown (original started_at preserved) and are NEVER re-sent.
- fetch exceptions / broken plugins are recorded as failed_unknown with their
  receipt; unknown is never implicitly retried.
- success is idempotent: same-content RAW writes reuse the existing RAW id and
  receipts append (repeated attempts never drop earlier receipts).
- failed payloads and receipts are persisted to disk under data/crawl-failures/
  but never become a successful RAW input.
- RAW.source_hash is the SHA-256 of the actual bytes this run saved; RAW carries
  independent source / time / batch identity.
"""

from __future__ import annotations

import json
import hashlib
import fcntl
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .connector import Attempt, FetchContext, load_connectors
from .manifest import Manifest
from .schema import SchemaError, validate_against
from .validators import stamp

TOOL_VERSION = f"ctfs-toolbox:{__version__}"


class CrawlerError(Exception):
    """Budget, manifest or storage failure during a crawl."""


@dataclass(frozen=True)
class Budget:
    max_requests: int = 8
    max_bytes: int = 8_000_000
    timeout_seconds: float = 30.0
    per_request_max_bytes: int = 1_000_000

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> "Budget":
        cfg = manifest.crawler or {}
        return cls(
            max_requests=int(cfg.get("max_requests", 8)),
            max_bytes=int(cfg.get("max_bytes", 8_000_000)),
            timeout_seconds=float(cfg.get("timeout_seconds", 30.0)),
            per_request_max_bytes=int(cfg.get("per_request_max_bytes", 1_000_000)),
        )


class Crawler:
    """SDK entry: Crawler(manifest, storage).crawl(...)."""

    def __init__(self, manifest: Manifest, storage, connectors: dict | None = None,
                 ledger_path: Path | None = None):
        self.manifest = manifest
        self.storage = storage
        self.connectors = connectors if connectors is not None else load_connectors()
        self.budget = Budget.from_manifest(manifest)
        ledger = ledger_path or (manifest.path.parent / "data" / "crawl-ledger.sqlite")
        ledger.parent.mkdir(parents=True, exist_ok=True)
        _ledger_path = Path(self.manifest.path.parent) / "data" / "crawl-ledger.sqlite"
        _ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_dir = Path(ledger).parent / "attempt-locks"
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self._held_locks = {}
        self.ledger = sqlite3.connect(str(ledger), timeout=30)
        self.ledger.execute(
            "CREATE TABLE IF NOT EXISTS crawl_attempts ("
            " attempt_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,"
            " url TEXT NOT NULL, connector TEXT NOT NULL, status TEXT NOT NULL,"
            " ok INTEGER NOT NULL, code INTEGER, bytes_count INTEGER NOT NULL, sha256 TEXT,"
            " error TEXT, error_kind TEXT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,"
            " failure_path TEXT, fingerprint TEXT, selected_headers TEXT, raw_id TEXT)")
        self.ledger.execute(
            "CREATE TABLE IF NOT EXISTS crawl_budget ("
            " project_id TEXT PRIMARY KEY, requests_used INTEGER NOT NULL,"
            " bytes_used INTEGER NOT NULL, updated_at TEXT NOT NULL)")
        self.ledger.execute(
            "CREATE TABLE IF NOT EXISTS raw_imports ("
            " raw_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, source_id TEXT NOT NULL,"
            " attempt_id TEXT NOT NULL, captured_at TEXT NOT NULL, source_hash TEXT NOT NULL)")
        columns = {r[1] for r in self.ledger.execute("PRAGMA table_info(crawl_attempts)")}
        for column in ("fingerprint", "selected_headers", "raw_id", "owner_lock"):
            if column not in columns:
                self.ledger.execute(f"ALTER TABLE crawl_attempts ADD COLUMN {column} TEXT")
        self.ledger.commit()

    def _lock_path(self, attempt_id):
        return self.lock_dir / (hashlib.sha256(attempt_id.encode()).hexdigest() + ".lock")

    @staticmethod
    def _source_fingerprint(source: dict) -> str:
        import hashlib
        keys = ("url", "connector", "expected_sha", "kind", "max_bytes")
        cfg = {k: source.get(k) for k in keys if source.get(k) is not None}
        return hashlib.sha256(
            json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def _recover_pending(self):
        # A file lock lives exactly as long as the owning worker. Unlike PID or
        # elapsed-time guesses this distinguishes active requests from crashes.
        recovered = set()
        rows = self.ledger.execute(
            "SELECT attempt_id, source_id, fingerprint, owner_lock FROM crawl_attempts "
            "WHERE project_id=? AND status='pending'", (self.manifest.project_id,)).fetchall()
        for aid, sid, fp, owner in rows:
            expected = self._lock_path(aid)
            if owner and Path(owner) != expected:
                raise CrawlerError("pending ownership lock path mismatch")
            fh = expected.open("a+b")
            try:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue  # alive: never overwrite an in-flight attempt
                with self.ledger:
                    changed = self.ledger.execute(
                        "UPDATE crawl_attempts SET status='failed_unknown', ok=0, "
                        "error='worker ended before durable completion; retained without retry', "
                        "error_kind='unknown', finished_at=? WHERE attempt_id=? AND status='pending'",
                        (stamp(), aid)).rowcount
                if changed:
                    recovered.add((sid, fp))
            finally:
                fh.close()
        return recovered

    def sources(self) -> list[dict]:
        return list(self.manifest.raw.get("sources", []))

    def _reserve_and_pending(self, source: dict, per_bytes: int,
                            fingerprint: str | None = None) -> str:
        """Atomic reserve + pending write in one IMMEDIATE transaction."""
        if per_bytes > self.budget.per_request_max_bytes:
            raise CrawlerError(
                f"per-source max_bytes {per_bytes} exceeds per-request cap "
                f"{self.budget.per_request_max_bytes} (cannot bypass single-request limit)")
        attempt_id = f"attempt:{self.manifest.project_id}:{source.get('source_id', '?')}:{uuid.uuid4().hex[:12]}"
        started = stamp()
        held = self._lock_path(attempt_id).open("a+b")
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self._held_locks[attempt_id] = held
        with self.ledger:
            self.ledger.execute("BEGIN IMMEDIATE")
            prior = self.ledger.execute(
                "SELECT 1 FROM crawl_attempts WHERE project_id=? AND source_id=? AND fingerprint=?",
                (self.manifest.project_id, source.get("source_id", "?"), fingerprint)).fetchone()
            if prior:
                self._held_locks.pop(attempt_id).close()
                return None  # caller reads the winning attempt without a request
            row = self.ledger.execute(
                "SELECT requests_used, bytes_used FROM crawl_budget WHERE project_id=?",
                (self.manifest.project_id,)).fetchone()
            requests_used = (row[0] if row else 0)
            bytes_used = (row[1] if row else 0)
            if requests_used >= self.budget.max_requests:
                raise CrawlerError(
                    f"request budget exhausted ({requests_used}/{self.budget.max_requests})")
            if bytes_used + per_bytes > self.budget.max_bytes:
                raise CrawlerError(
                    f"byte budget would be exceeded ({bytes_used}+{per_bytes} > {self.budget.max_bytes})")
            self.ledger.execute(
                "INSERT INTO crawl_budget(project_id, requests_used, bytes_used, updated_at)"
                " VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET"
                " requests_used=?, bytes_used=?, updated_at=?",
                (self.manifest.project_id, requests_used + 1, bytes_used + per_bytes,
                 started, requests_used + 1, bytes_used + per_bytes, started))
            self.ledger.execute(
                "INSERT INTO crawl_attempts(attempt_id, project_id, source_id, url, connector,"
                " status, ok, code, bytes_count, sha256, error, error_kind, started_at, finished_at,"
                " fingerprint, raw_id, owner_lock)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (attempt_id, self.manifest.project_id, source.get("source_id", "?"),
                 source.get("url", ""), source.get("connector", self.budget_connector_default()),
                 "pending", 0, None, 0, None, None, None, started, started, fingerprint, None, str(self._lock_path(attempt_id))))
        return attempt_id

    def _persist_failure(self, attempt_id: str, body: bytes | None) -> str | None:
        if not body:
            return None
        fail_dir = self.manifest.path.parent / "data" / "crawl-failures"
        fail_dir.mkdir(parents=True, exist_ok=True)
        path = fail_dir / f"{attempt_id}.bin"
        path.write_bytes(body)
        return str(path.relative_to(self.manifest.path.parent))

    def _finalize_attempt(self, attempt_id: str, attempt: Attempt,
                          failure_path: str | None = None,
                          fingerprint: str | None = None) -> None:
        self.ledger.execute(
            "UPDATE crawl_attempts SET status=?, ok=?, code=?, bytes_count=?, sha256=?,"
            " error=?, error_kind=?, finished_at=?, failure_path=?, fingerprint=?,"
            " selected_headers=? WHERE attempt_id=?",
            ("ok" if attempt.ok else ("failed" if attempt.error_kind not in ("unknown",)
                                      else "failed_unknown"),
             1 if attempt.ok else 0, attempt.code, attempt.bytes_count, attempt.sha256,
             attempt.error, attempt.error_kind, attempt.finished_at, failure_path,
             fingerprint, (json.dumps(attempt.headers, sort_keys=True, ensure_ascii=False)
                           if attempt.headers else None),
             attempt_id))
        self.ledger.commit()

    def _validate_result(self, value, ctx, began, connector_name):
        # Installed plugins extend transport, not the immutable acquisition
        # identity, physical byte accounting or per-request storage budget.
        errors = []
        body = value.body if isinstance(value, Attempt) and isinstance(value.body, bytes) else None
        count = len(body) if body is not None else 0
        sha = hashlib.sha256(body).hexdigest() if body is not None else None
        if not isinstance(value, Attempt):
            errors.append("result is not Attempt")
        else:
            for field, expected in (("source_id", ctx.source["source_id"]),
                                    ("url", ctx.source["url"]), ("connector", connector_name)):
                if getattr(value, field) != expected:
                    errors.append(field + " differs from reserved source")
            if type(value.ok) is not bool:
                errors.append("ok must be boolean")
            if type(value.bytes_count) is not int or value.bytes_count != count:
                errors.append("bytes_count differs from actual bytes")
            if value.body is not None and body is None:
                errors.append("body must be immutable bytes")
            if value.ok and body is None:
                errors.append("successful result requires bytes")
            if body is not None and value.sha256 != sha:
                errors.append("sha256 differs from actual bytes")
            if count > ctx.max_bytes:
                errors.append("body exceeds reserved context budget")
            if value.code is not None and (type(value.code) is not int or not 100 <= value.code <= 599):
                errors.append("invalid HTTP code")
            if value.ok and (type(value.code) is not int or not 200 <= value.code < 300):
                errors.append("unsuccessful HTTP code marked successful")
            for field in ("error", "error_kind"):
                field_value = getattr(value, field)
                if field_value is not None and not isinstance(field_value, str):
                    errors.append(field + " must be a string or null")
            from rfc3339_validator import validate_rfc3339
            for field in ("started_at", "finished_at"):
                at = getattr(value, field)
                if not isinstance(at, str) or not validate_rfc3339(at.upper()):
                    errors.append("invalid " + field + " timestamp")
            if value.headers is not None and not isinstance(value.headers, dict):
                errors.append("headers must be a mapping")
        if not errors:
            # Only selected response metadata can enter the durable ledger.
            from dataclasses import replace
            from .connector_http import _HEADER_WHITELIST
            safe = {k.lower(): v for k, v in (value.headers or {}).items()
                    if isinstance(k, str) and k.lower() in _HEADER_WHITELIST and isinstance(v, str)}
            return replace(value, headers=safe)
        code = value.code if isinstance(value, Attempt) and type(value.code) is int and 100 <= value.code <= 599 else None
        return Attempt(ok=False, source_id=ctx.source["source_id"], url=ctx.source["url"],
                       connector=connector_name, started_at=began, finished_at=stamp(), code=code,
                       bytes_count=count, sha256=sha, body=body, error="; ".join(errors),
                       error_kind="invalid-connector-result")

    def _write_raw(self, source: dict, attempt: Attempt, attempt_id: str) -> str:
        assert attempt.ok and attempt.body is not None
        sha = attempt.sha256 or ""
        record = {
            "schemaVersion": "0.2.0",
            "project_id": self.manifest.project_id,
            "layer": "RAW",
            "payload": attempt.body,
            "content_hash": sha,
            "source_url": attempt.url,
            "source_hash": sha,
            "batch": f"{source.get('source_id', '?')}:{attempt_id}",
            "captured_at": attempt.finished_at,
            "lineage": {
                "project": self.manifest.project_id,
                "source_url": attempt.url,
                "source_hash": sha,
                "batch": f"{source.get('source_id', '?')}:{attempt_id}",
                "captured_at": attempt.finished_at,
                "steps": [attempt.connector],
                "tool_versions": [TOOL_VERSION],
            },
        }
        try:
            validate_against("raw", record)
        except SchemaError as exc:
            raise CrawlerError(f"raw record failed schema: {exc}") from exc
        raw_id = self.storage.write_raw(
            self.manifest.project_id, record,
            record_id=f"raw:{source.get('source_id', '?')}:{attempt_id}")
        receipt = attempt.receipt()
        if attempt.ok and attempt.note:
            receipt["note"] = f"{attempt.note}; sha256={sha}"
        self.storage.append_receipt(self.manifest.project_id, raw_id, receipt)
        self.ledger.execute(
            "INSERT INTO raw_imports(raw_id, project_id, source_id, attempt_id,"
            " captured_at, source_hash) VALUES(?,?,?,?,?,?)",
            (raw_id, self.manifest.project_id, source.get("source_id", "?"),
             attempt_id, attempt.finished_at, sha))
        self.ledger.commit()
        return raw_id

    def crawl(self, source_id: str | None = None) -> list[dict]:
        """Crawl all (or one) manifest sources; returns attempt summaries.

        Identity rules (P1-REVIEW-GATE-03):
        - each source is keyed by project_id + source_id + config fingerprint;
          an unchanged config NEVER replays: success is read back from RAW,
          pending from another live instance is not touched, and
          failed/failed_unknown attempts are retained, not re-sent.
        - an empty sources list is an explicit unconfigured state and is
          rejected before any budget or connector work.
        """
        recovered = self._recover_pending()
        sources = self.sources()
        if not sources:
            raise CrawlerError(
                "no sources configured: add raw.sources to the manifest before crawling")
        if source_id is not None:
            sources = [s for s in sources if s.get("source_id") == source_id]
            if not sources:
                raise CrawlerError(f"no manifest source with source_id={source_id!r}")
        return [self._crawl_source(source, recovered) for source in sources]

    def _crawl_source(self, source, recovered):
        sid = source.get("source_id", "?")
        fp = self._source_fingerprint(source)
        while True:
            prior = self.ledger.execute(
                "SELECT status, ok, code, bytes_count, sha256, error, error_kind, "
                "attempt_id, finished_at, raw_id, failure_path FROM crawl_attempts "
                "WHERE project_id=? AND source_id=? AND fingerprint=? "
                "ORDER BY started_at DESC LIMIT 1", (self.manifest.project_id, sid, fp)).fetchone()
            if prior is not None:
                status, ok, code, count, sha, err, ek, aid, fin, rid, failed_path = prior
                if ok:
                    if not rid:
                        raise CrawlerError(f"ok attempt {aid} has no RAW binding; refusing re-fetch")
                    raw = self.storage.read(self.manifest.project_id, "RAW", rid)
                    if raw["content_hash"] != sha or len(raw["payload"]) != count:
                        raise CrawlerError("attempt and RAW binding mismatch")
                    return dict(attempt_id=aid, source_id=sid, url=source["url"],
                                connector=source.get("connector", self.budget_connector_default()),
                                ok=True, code=code, bytes=count, sha256=sha, raw_id=rid,
                                error=None, error_kind=None, failure_path=None, reused="raw_readback")
                kind = ("recovered_pending" if (sid, fp) in recovered else
                        "pending_skipped" if status == "pending" else "retained_failure")
                return dict(attempt_id=aid, source_id=sid, url=source["url"],
                            connector=source.get("connector", self.budget_connector_default()),
                            ok=False, code=code, bytes=count, sha256=sha, raw_id=rid,
                            error=err or "live request retained; no replay", error_kind=kind,
                            failure_path=failed_path, reused=kind)
            connector_name = source.get("connector") or self.budget_connector_default()
            connector = self.connectors.get(connector_name)
            if connector is None:
                raise CrawlerError(f"connector {connector_name!r} not registered")
            per_bytes = int(source.get("max_bytes", self.budget.per_request_max_bytes))
            attempt_id = self._reserve_and_pending(source, per_bytes, fp)
            if attempt_id is not None:
                break
        try:
            ctx = FetchContext(source=source, project_dir=self.manifest.path.parent,
                               timeout_seconds=self.budget.timeout_seconds, max_bytes=per_bytes,
                               tool_version=TOOL_VERSION)
            began = self.ledger.execute("SELECT started_at FROM crawl_attempts WHERE attempt_id=?",
                                        (attempt_id,)).fetchone()[0]
            try:
                attempt = connector.fetch(ctx)
            except Exception as exc:
                attempt = Attempt(ok=False, source_id=sid, url=source["url"], connector=connector_name,
                                  started_at=began, finished_at=stamp(), error=f"connector raised: {exc}",
                                  error_kind="unknown")
            attempt = self._validate_result(attempt, ctx, began, connector_name)
            rid = None
            if attempt.ok:
                try:
                    rid = self._write_raw(source, attempt, attempt_id)
                    self.ledger.execute("UPDATE crawl_attempts SET raw_id=? WHERE attempt_id=?",
                                        (rid, attempt_id))
                    self.ledger.commit()
                except Exception as exc:
                    from dataclasses import replace
                    attempt = replace(attempt, ok=False, error=f"storage completion failed: {exc}",
                                      error_kind="unknown")
            failure_path = self._persist_failure(attempt_id, attempt.body if not attempt.ok else None)
            self._finalize_attempt(attempt_id, attempt, failure_path, fp)
            return dict(attempt_id=attempt_id, source_id=attempt.source_id, url=attempt.url,
                        connector=attempt.connector, ok=attempt.ok, code=attempt.code,
                        bytes=attempt.bytes_count, sha256=attempt.sha256, raw_id=rid,
                        error=attempt.error, error_kind=attempt.error_kind, failure_path=failure_path)
        finally:
            held = self._held_locks.pop(attempt_id, None)
            if held:
                held.close()

    @staticmethod
    def _retained_summary(kind: str, source: dict, fp: str, note: str) -> dict:
        return {
            "attempt_id": None, "source_id": source.get("source_id", "?"),
            "url": source.get("url", ""), "connector": source.get("connector", ""),
            "ok": False, "code": None, "bytes": 0, "sha256": None,
            "raw_id": None, "error": note, "error_kind": kind,
            "failure_path": None, "reused": kind,
        }

    def budget_connector_default(self) -> str:
        cfg = self.manifest.crawler or {}
        return cfg.get("connector", "http-public")

    def ledger_snapshot(self) -> dict:
        rows = self.ledger.execute(
            "SELECT COUNT(*), SUM(bytes_count), SUM(ok) FROM crawl_attempts"
            " WHERE project_id=?", (self.manifest.project_id,)).fetchone()
        budget = self.ledger.execute(
            "SELECT requests_used, bytes_used FROM crawl_budget WHERE project_id=?",
            (self.manifest.project_id,)).fetchone()
        status_rows = self.ledger.execute(
            "SELECT status, COUNT(*) FROM crawl_attempts WHERE project_id=? GROUP BY status",
            (self.manifest.project_id,)).fetchall()
        statuses = {s: c for s, c in status_rows}
        return {
            "attempts": rows[0] or 0,
            "bytes_total": rows[1] or 0,
            "ok_total": rows[2] or 0,
            "requests_used": budget[0] if budget else 0,
            "bytes_used": budget[1] if budget else 0,
            "budget": {
                "max_requests": self.budget.max_requests,
                "max_bytes": self.budget.max_bytes,
                "per_request_max_bytes": self.budget.per_request_max_bytes,
            },
            "statuses": statuses,
        }

    def close(self) -> None:
        for held in self._held_locks.values():
            held.close()
        self._held_locks.clear()
        try:
            self.ledger.close()
        except Exception:
            pass

"""snapshot-file connector (M1): read-only import of project-internal files.

Security contract (review gate):
- the source URL is `snapshot://<relative-path>` inside the project directory;
- rejects absolute paths and any path that resolves outside the project dir
  (including '..' escapes and symlink escapes: final resolve() must stay inside);
- a declared expected_sha (64-hex) must match the actual file bytes
  (tamper/version drift rejection);
- failures never overwrite prior inputs (storage RAW layer is create-only).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

from .connector import Attempt, Connector, ConnectorError, FetchContext
from .validators import stamp, text


class SnapshotFileConnector(Connector):
    name = "snapshot-file"

    def fetch(self, ctx: FetchContext) -> Attempt:
        source = ctx.source
        source_id = source.get("source_id", "?")
        url = source.get("url", "")
        started = stamp()
        try:
            rel = self._parse_snapshot_url(url)
            project_dir = ctx.project_dir.resolve()
            candidate = project_dir / rel
            resolved = candidate.resolve()
            if not resolved.is_relative_to(project_dir):
                raise ConnectorError(
                    f"snapshot path escapes project directory: {rel}")
            if not resolved.is_file():
                raise ConnectorError(f"snapshot file not found: {rel}")
            cap = int(ctx.max_bytes)
            if cap <= 0:
                raise ConnectorError("snapshot max_bytes must be positive")
            # Walk from the project directory with openat/NOFOLLOW so a rename
            # or symlink switch cannot redirect the file outside this project.
            fd = os.open(project_dir, os.O_RDONLY | os.O_DIRECTORY)
            try:
                parts = Path(rel).parts
                for part in parts[:-1]:
                    next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = next_fd
                file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
                with os.fdopen(file_fd, "rb") as handle:
                    if os.fstat(handle.fileno()).st_size > cap:
                        raise ConnectorError("snapshot exceeds max_bytes before read")
                    body = handle.read(cap + 1)
                    if len(body) > cap:
                        raise ConnectorError("snapshot exceeds max_bytes during read")
            finally:
                os.close(fd)
            actual = hashlib.sha256(body).hexdigest()
            expected = source.get("expected_sha")
            if expected is None:
                raise ConnectorError(
                    "snapshot-file sources require expected_sha (64 hex) of the exact bytes")
            text(expected, "expected_sha", 64)
            if expected != actual:
                raise ConnectorError(
                    f"snapshot SHA mismatch: expected {expected}, actual {actual}")
            return Attempt(ok=True, source_id=source_id, url=url,
                           connector=self.name, started_at=started,
                           finished_at=stamp(), code=200,
                           bytes_count=len(body), sha256=actual, body=body,
                           note="project-internal file; SHA verified")
        except OSError as exc:
            return Attempt(ok=False, source_id=source_id, url=url, connector=self.name,
                           started_at=started, finished_at=stamp(), error=str(exc),
                           error_kind="file-unavailable")
        except ConnectorError as exc:
            return Attempt(ok=False, source_id=source_id, url=url,
                           connector=self.name, started_at=started,
                           finished_at=stamp(), error=str(exc),
                           error_kind=self._kind_of(str(exc)))

    @staticmethod
    def _parse_snapshot_url(url: str) -> str:
        text(url, "snapshot url", 4096)
        if not url.startswith("snapshot://"):
            raise ConnectorError("snapshot-file source url must be snapshot://<rel-path>")
        parsed = urlsplit(url)
        rel = parsed.netloc + parsed.path
        if not rel:
            raise ConnectorError("snapshot path is empty")
        p = Path(rel)
        if p.is_absolute():
            raise ConnectorError("snapshot path must be relative")
        if ".." in p.parts:
            raise ConnectorError("snapshot path must not contain '..'")
        return rel

    @staticmethod
    def _kind_of(message: str) -> str:
        low = message.lower()
        if "escape" in low:
            return "path-escape"
        if "sha" in low or "mismatch" in low:
            return "sha-mismatch"
        if "not found" in low:
            return "not-found"
        return "unknown"

"""Storage factory: sqlite | postgres only. PG DSN comes from an env-var NAME.

- backend=sqlite  -> SQLiteStorage(path)
- backend=postgres -> PostgresStorage; DSN is read at construction from the
  environment variable named by manifest storage.postgres.dsn_env (the env var
  NAME is what may appear in the manifest, never the DSN itself; DSN never
  lands in manifests/logs/receipts/Git).
- schema name must start with ctfs_ and stay inside that namespace.
"""
from __future__ import annotations

import os
import pathlib
import re

from toolbox.storage import SqliteStorage, StorageError


def make_storage(manifest: dict, project_root: pathlib.Path, *, read_only: bool = False):
    storage = manifest.get("storage")
    if not isinstance(storage, dict):
        raise StorageError("manifest storage section missing")
    backend = storage.get("backend")
    if backend == "sqlite":
        rel = storage.get("path")
        if not isinstance(rel, str) or not rel:
            raise StorageError("sqlite storage.path missing")
        raw = pathlib.PurePosixPath(rel.replace("\\", "/"))
        if raw.is_absolute() or ".." in raw.parts:
            raise StorageError("sqlite storage.path must stay inside the project dir")
        db_path = project_root / rel
        try:
            resolved = db_path.resolve()
        except OSError as exc:
            raise StorageError("sqlite storage.path cannot be resolved") from exc
        proj_resolved = project_root.resolve()
        if proj_resolved != resolved and proj_resolved not in resolved.parents:
            raise StorageError("sqlite storage.path escapes the project dir")
        # check only the project-relative segment for symlinks (system roots
        # like /tmp may legitimately be symlinks on macOS)
        cursor = project_root
        rel_dir = pathlib.PurePosixPath(rel.replace("\\", "/")).parent
        for seg in rel_dir.parts:
            cursor = cursor / seg
            if cursor.is_symlink():
                raise StorageError("sqlite storage.path crosses a symlink")
        # an EXISTING symlink at the db path itself is always refused, even
        # when its target resolves inside the project (replace/escape risk)
        if db_path.is_symlink():
            raise StorageError("sqlite storage.path must not be a symlink")
        if not read_only:db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteStorage(db_path,read_only=read_only)
    if backend == "postgres":
        if read_only:raise StorageError("read-only HTTP consumer currently requires sqlite backend")
        return _make_postgres(storage)
    raise StorageError(f"unsupported storage backend {backend!r} (only sqlite|postgres)")


def _make_postgres(storage: dict):
    pg = storage.get("postgres")
    if not isinstance(pg, dict):
        raise StorageError("postgres backend requires storage.postgres object")
    dsn_env = pg.get("dsn_env")
    schema = pg.get("schema")
    if not isinstance(dsn_env, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", dsn_env):
        raise StorageError("postgres.dsn_env must name an environment variable (uppercase NAME)")
    if not isinstance(schema, str) or not re.fullmatch(r"ctfs_[a-z0-9_]{1,62}", schema):
        raise StorageError("postgres.schema must match ctfs_[a-z0-9_]+")
    dsn = os.environ.get(dsn_env)
    if not dsn:
        raise StorageError(f"postgres DSN env {dsn_env!r} is not set in this process")
    from toolbox.postgres import PostgresStorage  # deferred optional dependency
    return PostgresStorage(dsn=dsn, schema=schema)

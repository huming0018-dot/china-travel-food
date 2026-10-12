"""M7-PG-READONLY-051 narrow regression, revision 2 (runs locally, offline only).

Covers the read-only PostgreSQL gate added for the HTTP consumer:
- factory no longer pre-rejects read_only+postgres; read_only is forwarded.
- PostgresStorage(read_only=True): the dedicated schema and ALL required toolbox
  tables (raw_records/versions/receipts/_toolbox_meta) plus the contract marker
  must exist; missing anything fails safely WITHOUT creating anything.
- Database-layer read-only enforcement: connection-scoped
  default_transaction_read_only and transaction_read_only are verified on.
  Opening attempts no DDL/DML; actual refusal is tested separately in engineering PG.
- Initialization failures collapse to StorageError with class-name categories:
  no DSN/SQL/credential material, and the connection is closed.
- DSN connection failures are mocked: no real network/DB access in this file.
Real PostgreSQL consumption (existing ctfs_ schema with 6-card + 2-release
data, HTTP consumer against PG read-only) is executed by Root on the cloud
isolated PG container; this file intentionally never connects to any DB.
"""

import hashlib
import inspect
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from toolbox.postgres import PostgresStorage
from toolbox.storage import LAYER_RAW, StorageError
from toolbox.storage_factory import make_storage

FAKE_DSN_ENV = "CTFS_M7_TEST_PG_DSN"
FAKE_SECRET = "supersecretpw-m7"
FAKE_DSN = "postgresql://u:" + FAKE_SECRET + "@127.0.0.1:1/ctfs_db"


def _raw(payload="hello", url="https://example.com/a", captured="2026-10-11T00:00:00Z", batch="batch-1"):
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {
        "schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "RAW",
        "payload": payload, "source_url": url, "source_hash": digest,
        "batch": batch, "captured_at": captured,
        "lineage": {"project": "proj-a", "source_url": url, "source_hash": digest,
                    "batch": batch, "captured_at": captured},
    }


def _pg_manifest(env_name=FAKE_DSN_ENV, schema="ctfs_m7test"):
    return {"storage": {"backend": "postgres",
                        "postgres": {"dsn_env": env_name, "schema": schema}}}


# ---------------------------------------------------------------------------
# Offline fake psycopg modules + fake connection (no network, no real psycopg)
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def _fake_conninfo(dsn):
    # Shape mirror of psycopg.conninfo.conninfo_to_dict; never touches the wire.
    return {"host": "127.0.0.1", "port": 1, "dbname": "ctfs_db",
            "user": "u", "password": FAKE_SECRET}


class _FakeConn:
    def __init__(self, scenario=None):
        self.scenario = scenario or {}
        self.autocommit = False
        self.closed = False
        self.search_path = None
        self.queries = []

    def execute(self, query, params=None):
        exc = self.scenario.get("query_exc")
        if exc is not None:
            raise exc
        s = str(query)
        self.queries.append(s)
        if "information_schema.schemata" in s:
            return _Result([(self.scenario.get("schema_exists", True),)])
        if "information_schema.columns" in s:
            return _Result(self.scenario.get("columns",
                                              [("_toolbox_meta", "key"), ("_toolbox_meta", "value")]))
        if "information_schema.tables" in s:
            tables = self.scenario.get("tables", ["raw_records", "versions", "receipts", "_toolbox_meta"])
            return _Result([(t,) for t in tables])
        if "SELECT value FROM" in s:
            contract = self.scenario.get("contract", "layered-storage/0.2")
            return _Result([(contract,)] if contract else [])
        if "SHOW default_transaction_read_only" in s:
            return _Result([(self.scenario.get("read_only_setting", "on"),)])
        if "SHOW transaction_read_only" in s:
            return _Result([(self.scenario.get("transaction_read_only_setting", "on"),)])
        if "SET search_path" in s:
            self.search_path = s.split("TO ", 1)[1] if "TO " in s else params
            return _Result([])
        return _Result([])

    def close(self):
        self.closed = True


def _install_fake_psycopg(connect=None):
    psycopg_mod = types.ModuleType("psycopg")
    psycopg_mod.connect = connect
    errors_mod = types.ModuleType("psycopg.errors")
    psycopg_mod.errors = errors_mod
    conninfo_mod = types.ModuleType("psycopg.conninfo")
    conninfo_mod.conninfo_to_dict = _fake_conninfo
    sql_mod = types.ModuleType("psycopg.sql")

    def _sql(template):
        return template

    def _identifier(name):
        return name

    sql_mod.SQL = _sql
    sql_mod.Identifier = _identifier
    return mock.patch.dict(sys.modules, {
        "psycopg": psycopg_mod,
        "psycopg.errors": errors_mod,
        "psycopg.conninfo": conninfo_mod,
        "psycopg.sql": sql_mod,
    })


class FactoryReadOnlyGateTest(unittest.TestCase):
    def test_read_only_must_be_bool(self):
        with self.assertRaises(StorageError):
            make_storage(_pg_manifest(), Path(tempfile.mkdtemp()), read_only="yes")

    def test_postgres_read_only_not_pre_rejected(self):
        # No DSN env set: factory must reach the DSN check (not the old
        # "read-only requires sqlite" pre-rejection).
        os.environ.pop(FAKE_DSN_ENV, None)
        with self.assertRaises(StorageError) as cm:
            make_storage(_pg_manifest(), Path(tempfile.mkdtemp()), read_only=True)
        msg = str(cm.exception)
        self.assertIn(FAKE_DSN_ENV, msg)
        self.assertIn("not set", msg)

    def test_postgres_write_mode_default_compatible(self):
        os.environ.pop(FAKE_DSN_ENV, None)
        with self.assertRaises(StorageError) as cm:
            make_storage(_pg_manifest(), Path(tempfile.mkdtemp()))
        self.assertIn("not set", str(cm.exception))

    def test_postgres_schema_must_be_ctfs(self):
        os.environ.pop(FAKE_DSN_ENV, None)
        with self.assertRaises(StorageError) as cm:
            make_storage(_pg_manifest(schema="public"), Path(tempfile.mkdtemp()))
        self.assertIn("ctfs_", str(cm.exception))

    def test_postgres_dsn_env_name_strict(self):
        os.environ.pop(FAKE_DSN_ENV, None)
        with self.assertRaises(StorageError) as cm:
            make_storage(_pg_manifest(env_name="not-a-NAME"), Path(tempfile.mkdtemp()))
        self.assertIn("dsn_env", str(cm.exception))

    def test_postgres_connect_failure_does_not_leak_dsn(self):
        os.environ[FAKE_DSN_ENV] = FAKE_DSN

        def _connect(*args, **kwargs):
            raise RuntimeError("boom https://u:" + FAKE_SECRET + "@evil.example/pg")

        try:
            with _install_fake_psycopg(connect=_connect):
                make_storage(_pg_manifest(), Path(tempfile.mkdtemp()))
                self.fail("expected connection failure")
        except StorageError as exc:
            msg = str(exc)
            self.assertNotIn(FAKE_SECRET, msg)
            self.assertIn("postgres connection failed", msg)
            self.assertIn("RuntimeError", msg)
        finally:
            os.environ.pop(FAKE_DSN_ENV, None)


class PostgresReadOnlyGuardTest(unittest.TestCase):
    """Guard logic is unit-tested via __new__ (no network, no psycopg needed)."""

    @staticmethod
    def _ro_instance():
        store = PostgresStorage.__new__(PostgresStorage)
        store._read_only = True
        return store

    def test_signature_exposes_read_only(self):
        sig = inspect.signature(PostgresStorage.__init__)
        self.assertIn("read_only", sig.parameters)

    def test_write_raw_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._ro_instance().write_raw("proj-a", _raw())
        self.assertIn("read-only", str(cm.exception))

    def test_append_receipt_rejected(self):
        with self.assertRaises(StorageError):
            self._ro_instance().append_receipt("proj-a", "raw:x",
                                               {"code": 200, "bytes": 5, "at": "2026-10-11T00:00:00Z", "note": "ok"})

    def test_append_version_rejected(self):
        with self.assertRaises(StorageError):
            self._ro_instance().append_version("proj-a", "ODS", {})

    def test_write_mode_guard_not_armed(self):
        store = PostgresStorage.__new__(PostgresStorage)
        store._read_only = False
        try:
            store.write_raw("proj-a", _raw())
        except Exception as exc:
            self.assertNotIn("read-only postgres backend rejects writes", str(exc))


class PostgresReadOnlyInitMockTest(unittest.TestCase):
    """Offline mock of the read-only initialization path (B1/B2/B3)."""

    def _open(self, scenario, dsn=FAKE_DSN, schema="ctfs_m7test"):
        conn = _FakeConn(scenario)
        store = PostgresStorage.__new__(PostgresStorage)
        store._conn = None
        store._read_only = False
        with _install_fake_psycopg(connect=lambda *a, **k: conn):
            PostgresStorage.__init__(store, dsn=dsn, schema=schema, read_only=True)
        return store, conn

    def test_init_read_only_success_and_guards(self):
        store, conn = self._open({})
        self.assertTrue(store._read_only)
        self.assertTrue(conn.autocommit)
        self.assertEqual(conn.search_path, "ctfs_m7test")
        self.assertTrue(any(q == "SHOW transaction_read_only" for q in conn.queries))
        self.assertFalse(any(q.lstrip().upper().startswith(("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "GRANT", "REVOKE")) for q in conn.queries))
        with self.assertRaises(StorageError) as cm:
            store.write_raw("proj-a", _raw())
        self.assertIn("read-only", str(cm.exception))
        with self.assertRaises(StorageError):
            store.append_receipt("proj-a", "raw:x", {"code": 200, "bytes": 5, "at": "2026-10-11T00:00:00Z", "note": "ok"})
        with self.assertRaises(StorageError):
            store.append_version("proj-a", "ODS", {})

    def test_missing_schema_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"schema_exists": False})
        self.assertIn("schema does not exist", str(cm.exception))

    def test_missing_tables_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"tables": ["raw_records", "versions", "_toolbox_meta"]})
        msg = str(cm.exception)
        self.assertIn("toolbox tables missing", msg)
        self.assertIn("receipts", msg)

    def test_missing_meta_columns_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"columns": [("_toolbox_meta", "key")]})
        self.assertIn("key/value columns", str(cm.exception))

    def test_contract_mismatch_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"contract": "some-other-contract"})
        self.assertIn("incompatible existing toolbox schema contract", str(cm.exception))

    def test_missing_contract_marker_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"contract": None})
        self.assertIn("incompatible existing toolbox schema contract", str(cm.exception))

    def test_read_only_not_enforced_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"read_only_setting": "off"})
        self.assertIn("not enforced", str(cm.exception))

    def test_current_transaction_not_readonly_rejected(self):
        with self.assertRaises(StorageError) as cm:
            self._open({"transaction_read_only_setting": "off"})
        self.assertIn("not enforced", str(cm.exception))

    def test_init_query_failure_collapses_and_closes(self):
        conn = _FakeConn({"query_exc": RuntimeError("boom https://u:pw@evil.example/pg")})
        store = PostgresStorage.__new__(PostgresStorage)
        store._conn = None
        store._read_only = False
        with _install_fake_psycopg(connect=lambda *a, **k: conn):
            with self.assertRaises(StorageError) as cm:
                PostgresStorage.__init__(store, dsn=FAKE_DSN, schema="ctfs_m7test", read_only=True)
        msg = str(cm.exception)
        self.assertIn("initialization failed", msg)
        self.assertIn("RuntimeError", msg)
        self.assertNotIn("boom", msg)
        self.assertNotIn(FAKE_SECRET, msg)
        self.assertTrue(conn.closed)


class SqliteReadOnlyRegressionTest(unittest.TestCase):
    def test_write_then_read_only_read_ok_writes_refused(self):
        tmp = tempfile.mkdtemp(prefix="ctfs-m7-sqlite-")
        manifest = {"storage": {"backend": "sqlite", "path": "proj/t.sqlite"}}
        store = make_storage(manifest, Path(tmp))
        rid = store.write_raw("proj-a", _raw("hello"))
        store.append_receipt("proj-a", rid,
                             {"code": 200, "bytes": 5, "at": "2026-10-11T00:00:00Z", "note": "ok"})
        store.close()

        ro = make_storage(manifest, Path(tmp), read_only=True)
        rec = ro.read("proj-a", LAYER_RAW, rid)
        self.assertEqual(rec["payload"], "hello")
        with self.assertRaises(Exception):
            ro.write_raw("proj-a", _raw("other"))
        with self.assertRaises(Exception):
            ro.append_receipt("proj-a", rid,
                              {"code": 200, "bytes": 5, "at": "2026-10-11T00:00:00Z", "note": "again"})
        ro.close()

    def test_read_only_missing_db_refused(self):
        tmp = tempfile.mkdtemp(prefix="ctfs-m7-sqlite-")
        manifest = {"storage": {"backend": "sqlite", "path": "missing/t.sqlite"}}
        with self.assertRaises(StorageError):
            make_storage(manifest, Path(tmp), read_only=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

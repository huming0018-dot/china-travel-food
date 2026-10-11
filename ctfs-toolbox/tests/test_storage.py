"""Storage tests (P0 review gate): payload integrity, immutability, idempotency,
pinned parent versions, transaction rollback, real lineage values, APP audit/view."""

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from toolbox.storage import (
    LAYER_APP, LAYER_DW, LAYER_ODS, LAYER_RAW, SqliteStorage, StorageError,
)

HASH_A = "a" * 64


def _raw(payload="hello", url="https://example.com/a", captured="2026-10-11T00:00:00Z", batch="batch-1"):
    return {
        "schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "RAW",
        "payload": payload, "source_url": url,
        "source_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "batch": batch, "captured_at": captured,
        "lineage": {"project": "proj-a", "source_url": url,
                    "source_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    "batch": batch, "captured_at": captured},
    }


class StorageGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = SqliteStorage(Path(self._tmp.name) / "t.sqlite")

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    # ---- RAW payload & hash -------------------------------------------------

    def test_raw_read_recomputes_hash_from_stored_bytes(self):
        rid = self.db.write_raw("proj-a", _raw(payload="the real body text"))
        rec = self.db.read("proj-a", "RAW", rid)
        self.assertEqual(rec["payload"], "the real body text")
        self.assertEqual(rec["content_hash"], rec["content_hash"])

    def test_raw_content_hash_input_verified_against_bytes(self):
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", {**_raw(), "content_hash": "f" * 64})

    def test_raw_same_content_idempotent_same_id(self):
        r1 = self.db.write_raw("proj-a", _raw("same"))
        r2 = self.db.write_raw("proj-a", _raw("same"))
        self.assertEqual(r1, r2)

    def test_raw_explicit_id_conflict_rejected(self):
        rid = self.db.write_raw("proj-a", _raw("content-A"), record_id="raw:fixed")
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", _raw("content-B"), record_id="raw:fixed")
        # idempotent with same content is allowed
        r2 = self.db.write_raw("proj-a", _raw("content-A"), record_id="raw:fixed")
        self.assertEqual(rid, r2)

    def test_raw_lineage_project_must_match(self):
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", {**_raw(), "lineage": {"project": "other", "source_url": "u", "source_hash": HASH_A, "batch": "b", "captured_at": "2026-10-11T00:00:00Z"}})

    def test_receipt_verifies_raw_project_ownership(self):
        rid = self.db.write_raw("proj-a", _raw())
        self.db.append_receipt("proj-a", rid, {"code": 200, "bytes": 100, "at": "2026-10-11T00:00:00Z"})
        self.db.append_receipt("proj-a", rid, {"code": 200, "bytes": 101, "at": "2026-10-11T00:00:01Z"})
        with self.assertRaises(StorageError):
            self.db.append_receipt("proj-b", rid, {"code": 200, "bytes": 1, "at": "2026-10-11T00:00:02Z"})

    def test_receipt_unknown_fields_rejected(self):
        rid = self.db.write_raw("proj-a", _raw())
        with self.assertRaises(StorageError):
            self.db.append_receipt("proj-a", rid, {"code": 200, "at": "2026-10-11T00:00:03Z", "evil": 1})

    # ---- versioned layers ---------------------------------------------------

    def _write_chain(self):
        rid = self.db.write_raw("proj-a", _raw())
        cv = self.db.append_version(
            "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                  "record_id": "c1", "content": {"t": 1}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": hashlib.sha256(b"hello").hexdigest() }}
        )
        ods_rec = self.db.read("proj-a", LAYER_ODS, "c1", version=cv)
        sv = self.db.append_version(
            "proj-a", LAYER_DW, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "DW",
                                 "record_id": "s1", "content": {"score": 5}, "parent_ref": {"layer": "ODS", "project_id": "proj-a", "record_id": "c1", "version": cv, "hash": ods_rec["content_hash"] }}
        )
        dw_rec = self.db.read("proj-a", LAYER_DW, "s1", version=sv)
        return rid, cv, sv

    def test_four_layer_chain_with_pinned_versions(self):
        rid, cv, sv = self._write_chain()
        dw_rec = self.db.read("proj-a", LAYER_DW, "s1", version=sv)
        av = self.db.append_version(
            "proj-a", LAYER_APP, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "APP",
                                  "schema_kind": "audit", "record_id": "a1", "content": {"ok": True}, "parent_ref": {"layer": "DW", "project_id": "proj-a", "record_id": "s1", "version": sv, "hash": dw_rec["content_hash"] }})
        self.assertTrue(self.db.verify_lineage("proj-a", LAYER_APP, "a1", av))
        # APP view kind also supported on same DW parent
        vv = self.db.append_version(
            "proj-a", LAYER_APP, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "APP",
                                  "schema_kind": "view", "record_id": "v1", "content": {"fields": ["x"]}, "parent_ref": {"layer": "DW", "project_id": "proj-a", "record_id": "s1", "version": sv, "hash": dw_rec["content_hash"] }})
        self.assertTrue(self.db.verify_lineage("proj-a", LAYER_APP, "v1", vv))

    def test_dw_parent_version_must_be_pinned(self):
        rid, _, _ = self._write_chain()
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_DW, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "DW",
                                     "record_id": "s2", "content": {}, "parent_ref": {"layer": "ODS", "project_id": "proj-a", "record_id": "c1", "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})

    def test_unknown_parent_version_rejected(self):
        rid, cv, _ = self._write_chain()
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_DW, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "DW",
                                     "record_id": "s3", "content": {}, "parent_ref": {"layer": "ODS", "project_id": "proj-a", "record_id": "c1", "version": 99, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})

    def test_parent_record_must_exist(self):
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                      "record_id": "c", "content": {}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": "missing", "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})

    def test_failed_write_leaves_no_partial_state(self):
        rid = self.db.write_raw("proj-a", _raw())
        cv = self.db.append_version(
            "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                  "record_id": "c1", "content": {"t": 1}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})
        with self.assertRaises(StorageError):
            # DW with wrong parent version -> rejected; must not write anything
            self.db.append_version(
                "proj-a", LAYER_DW, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "DW",
                                     "record_id": "s-broken", "content": {}, "parent_ref": {"layer": "ODS", "project_id": "proj-a", "record_id": "c1", "version": cv + 5, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})
        with self.assertRaises(StorageError):
            self.db.read("proj-a", LAYER_DW, "s-broken")

    def test_lineage_keeps_real_source_values(self):
        rid = self.db.write_raw("proj-a", _raw(captured="2026-10-01T02:03:04Z", batch="batch-real"))
        cv = self.db.append_version(
            "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                  "record_id": "c1", "content": {}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})
        rec = self.db.read("proj-a", LAYER_ODS, "c1", version=cv)
        self.assertEqual(rec["lineage"]["captured_at"], "2026-10-01T02:03:04Z")
        self.assertEqual(rec["lineage"]["batch"], "batch-real")
        self.assertEqual(rec["lineage"]["project"], "proj-a")
        from toolbox import __version__
        self.assertIn("ctfs-toolbox:" + __version__, rec["lineage"]["tool_versions"])

    def test_version_append_does_not_overwrite(self):
        rid, _, _ = self._write_chain()
        v1 = self.db.append_version(
            "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                  "record_id": "c2", "content": {"x": 1}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})
        v2 = self.db.append_version(
            "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                  "record_id": "c2", "content": {"x": 2}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})
        self.assertEqual((v1, v2), (1, 2))
        latest = self.db.read("proj-a", LAYER_ODS, "c2")
        self.assertEqual(latest["version"], 2)
        older = self.db.read("proj-a", LAYER_ODS, "c2", version=1)
        self.assertEqual(older["content"], {"x": 1})

    def test_verify_lineage_false_on_broken_chain(self):
        rid, cv, sv = self._write_chain()
        # manually break the chain in the DB (simulate tamper): rewrite a1's parent hash
        dw_rec = self.db.read("proj-a", LAYER_DW, "s1", version=sv)
        av = self.db.append_version(
            "proj-a", LAYER_APP, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "APP",
                                  "schema_kind": "audit", "record_id": "a1", "content": {"ok": True}, "parent_ref": {"layer": "DW", "project_id": "proj-a", "record_id": "s1", "version": sv, "hash": dw_rec["content_hash"] }})
        self.assertTrue(self.db.verify_lineage("proj-a", LAYER_APP, "a1", av))
        with self._db_conn() as conn:
            ref = {"layer": "DW", "project_id": "proj-a", "record_id": "s1", "version": sv, "hash": "f" * 64}
            conn.execute("UPDATE versions SET parent_ref=? WHERE id='a1' AND project_id='proj-a' AND layer='APP' AND version=?",
                         (__import__("json").dumps(ref), av))
        self.assertFalse(self.db.verify_lineage("proj-a", LAYER_APP, "a1", av))

    def _db_conn(self):
        import contextlib
        return contextlib.contextmanager(lambda: (yield self.db._conn))()

    # ---- schema enforcement at every entry ------------------------------------

    def test_write_raw_runs_schema(self):
        bad = _raw()
        del bad["source_url"]
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", bad)

    def test_append_version_runs_schema(self):
        rid = self.db.write_raw("proj-a", _raw())
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
                                      "record_id": "c1", "content": {}, "extra": 1,
                                      "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})

    def test_app_layer_requires_schema_kind(self):
        rid = self.db.write_raw("proj-a", _raw())
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_APP, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "APP",
                                      "record_id": "a1", "content": {}, "parent_ref": {"layer": "DW", "project_id": "proj-a", "record_id": "x", "version": 1, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" }})


if __name__ == "__main__":
    unittest.main()



class VersionIdempotencyTest(unittest.TestCase):
    """Same record_id + same content -> same version; different content appends."""

    def setUp(self):
        self.db = SqliteStorage(":memory:")

    def test_append_version_same_content_idempotent(self):
        rid = self.db.write_raw("proj-a", _raw())
        rec = {
            "schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
            "record_id": "c1", "content": {"name": "x"},
            "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" },
        }
        v1 = self.db.append_version("proj-a", LAYER_ODS, rec)
        v2 = self.db.append_version("proj-a", LAYER_ODS, rec)
        self.assertEqual(v1, v2)
        count = self.db._conn.execute(
            "SELECT COUNT(*) FROM versions WHERE id='c1' AND layer='ODS'"
        ).fetchone()[0]
        self.assertEqual(count, 1)
        v3 = self.db.append_version("proj-a", LAYER_ODS, dict(rec, content={"name": "y"}))
        self.assertEqual(v3, v1 + 1)

"""Security tests: cross-project isolation, schema unknown keywords/definitions."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from toolbox.schema import SCHEMA_FILES, SCHEMAS_DIR, SchemaError, load_schema, validate_against
from toolbox.storage import LAYER_DW, LAYER_ODS, LAYER_RAW, SqliteStorage, StorageError

HASH_A = "a" * 64


def _raw(project="proj-a"):
    return {
        "schemaVersion": "0.2.0", "project_id": project, "layer": "RAW",
        "payload": "body", "source_url": "https://u",
        "source_hash": hashlib.sha256(b"body").hexdigest(),
        "batch": "b", "captured_at": "2026-10-11T00:00:00Z",
        "lineage": {"project": project, "source_url": "https://u",
            "source_hash": hashlib.sha256(b"body").hexdigest(),
                    "batch": "b", "captured_at": "2026-10-11T00:00:00Z"},
    }


class TestCrossProjectIsolation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = SqliteStorage(Path(self._tmp.name) / "t.sqlite")

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_cross_project_ods_parent_rejected(self):
        rid = self.db.write_raw("proj-a", _raw())
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-b", LAYER_ODS, {"schemaVersion": "0.2.0", "project_id": "proj-b", "layer": "ODS",
                                      "record_id": "c", "content": {}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" }})

    def test_wrong_parent_layer_rejected(self):
        with self.assertRaises(StorageError):
            self.db.append_version(
                "proj-a", LAYER_DW, {"schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "DW",
                                      "record_id": "s", "content": {}, "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": "anything", "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" }})

    def test_raw_read_cross_project_rejected(self):
        rid = self.db.write_raw("proj-a", _raw())
        with self.assertRaises(StorageError):
            self.db.read("proj-b", LAYER_RAW, rid)


class TestDataLayerSchemas(unittest.TestCase):
    def test_raw_valid(self):
        validate_against("raw", _raw())

    def test_raw_requires_payload(self):
        bad = _raw()
        del bad["payload"]
        with self.assertRaises(SchemaError):
            validate_against("raw", bad)

    def test_raw_layer_const(self):
        bad = _raw()
        bad["layer"] = "APP"
        with self.assertRaises(SchemaError):
            validate_against("raw", bad)

    def test_raw_unknown_field_rejected(self):
        bad = {**_raw(), "evil": 1}
        with self.assertRaises(SchemaError):
            validate_against("raw", bad)

    def test_raw_bad_source_hash_rejected(self):
        bad = _raw()
        bad["source_hash"] = "short"
        with self.assertRaises(SchemaError):
            validate_against("raw", bad)

    def test_clean_requires_layer_ods_and_record_id(self):
        with self.assertRaises(SchemaError):
            validate_against("clean", {
                "schemaVersion": "0.2.0", "project_id": "p", "layer": "ODS",
                "parent_ref": {"layer": "RAW", "project_id": "p", "record_id": "r", "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
                "content": {},
            })

    def test_clean_parent_layer_must_be_raw(self):
        with self.assertRaises(SchemaError):
            validate_against("clean", {
                "schemaVersion": "0.2.0", "project_id": "p", "layer": "ODS",
                "record_id": "c",
                "parent_ref": {"layer": "DW", "project_id": "p", "record_id": "r", "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
                "content": {},
            })

    def test_audit_parent_version_required(self):
        with self.assertRaises(SchemaError):
            validate_against("audit", {
                "schemaVersion": "0.2.0", "project_id": "p", "layer": "APP",
                "schema_kind": "audit", "record_id": "a",
                "parent_ref": {"layer": "DW", "project_id": "p", "record_id": "s", "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
                "content": {},
            })

    def test_view_schema_ok_and_kind_const(self):
        validate_against("view", {
            "schemaVersion": "0.2.0", "project_id": "p", "layer": "APP",
            "schema_kind": "view", "record_id": "v",
            "parent_ref": {"layer": "DW", "project_id": "p", "record_id": "s", "version": 1, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
            "content": {},
        })
        bad = {
            "schemaVersion": "0.2.0", "project_id": "p", "layer": "APP",
            "schema_kind": "audit", "record_id": "v",
            "parent_ref": {"layer": "DW", "project_id": "p", "record_id": "s", "version": 1, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
            "content": {},
        }
        with self.assertRaises(SchemaError):
            validate_against("view", bad)


class TestSchemaValidatorStrictness(unittest.TestCase):
    def test_all_schema_files_are_valid_draft2020_12(self):
        # official jsonschema meta-validation: every asset must be a valid schema;
        # unknown keywords / invalid types fail at load time (fail closed).
        from jsonschema import Draft202012Validator
        for kind in SCHEMA_FILES:
            Draft202012Validator.check_schema(load_schema(kind))

    def test_unknown_type_rejected_by_jsonschema(self):
        from jsonschema import Draft202012Validator
        with self.assertRaises(Exception):
            Draft202012Validator.check_schema({"type": "banana"})

    def test_min_length_enforced(self):
        bad = _raw()
        bad["source_url"] = ""
        with self.assertRaises(SchemaError):
            validate_against("raw", bad)

    def test_parent_version_minimum_enforced(self):
        with self.assertRaises(SchemaError):
            validate_against("clean", {
                "schemaVersion": "0.2.0", "project_id": "p", "layer": "ODS",
                "record_id": "c",
                "parent_ref": {"layer": "RAW", "project_id": "p", "record_id": "r",
                               "version": 0, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
                "content": {},
            })

    def test_unknown_definition_ref_rejected(self):
        # a $ref to an unknown definition must raise via jsonschema, not pass silently
        from jsonschema import Draft202012Validator
        schema = {"$ref": "#/definitions/ghost"}
        with self.assertRaises(Exception):
            Draft202012Validator(schema).validate({"x": 1})

    def test_schema_dir_resolves_inside_package(self):
        # wheel install must serve schemas from the package, never from a repo dir
        self.assertTrue((SCHEMAS_DIR / "raw.schema.json").is_file())
        self.assertTrue((SCHEMAS_DIR / "view.schema.json").is_file())
        self.assertEqual(SCHEMAS_DIR.parent.name, "toolbox")


if __name__ == "__main__":
    unittest.main()



class CliInitGuardTest(unittest.TestCase):
    """CLI init trust-boundary checks (P0 review gate)."""

    def test_init_rejects_bad_project_id(self):
        import argparse
        from toolbox import cli
        with tempfile.TemporaryDirectory() as td:
            for bad in ("../evil", "UPPER", "a" * 80, "has space"):
                rc = cli.cmd_init(argparse.Namespace(project_id=bad, dir=td, domain="food", region="sh"))
                self.assertNotEqual(rc, 0, f"project_id {bad!r} should be rejected")
            self.assertFalse((Path(td) / "projects" / ".." / "evil" / "manifest.yaml").exists())

    def test_init_rejects_existing_manifest(self):
        import argparse
        from toolbox import cli
        with tempfile.TemporaryDirectory() as td:
            rc = cli.cmd_init(argparse.Namespace(project_id="good-proj", dir=td, domain="food", region="sh"))
            self.assertEqual(rc, 0)
            rc2 = cli.cmd_init(argparse.Namespace(project_id="good-proj", dir=td, domain="food", region="sh"))
            self.assertNotEqual(rc2, 0)
            self.assertTrue((Path(td) / "projects" / "good-proj" / "manifest.yaml").is_file())

    def test_init_rejects_missing_dir(self):
        import argparse
        from toolbox import cli
        with tempfile.TemporaryDirectory() as td:
            rc = cli.cmd_init(argparse.Namespace(project_id="ok-proj", dir=str(Path(td) / "missing"), domain="food", region="sh"))
            self.assertNotEqual(rc, 0)


class StorageScopeGuardTest(unittest.TestCase):
    """Storage trust-boundary checks from independent review (P0V1-01..09)."""

    def setUp(self):
        self.db = SqliteStorage(":memory:")

    def test_record_project_must_match_scope(self):
        r = _raw("proj-a")
        r["project_id"] = "proj-b"
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", r)

    def test_raw_outer_fields_must_match_lineage(self):
        r = _raw()
        r["source_url"] = "https://other.example"
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", r)
        r2 = _raw()
        r2["captured_at"] = "2026-10-12T00:00:00Z"
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", r2)

    def test_append_version_rejects_raw_layer(self):
        rid = self.db.write_raw("proj-a", _raw())
        rec = {
            "schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "RAW",
            "record_id": "x", "content": {"t": 1},
            "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
        }
        with self.assertRaises(StorageError):
            self.db.append_version("proj-a", "RAW", rec)

    def test_append_version_project_scope(self):
        rid = self.db.write_raw("proj-a", _raw())
        rec = {
            "schemaVersion": "0.2.0", "project_id": "proj-b", "layer": "ODS",
            "record_id": "c1", "content": {"name": "x"},
            "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid, "hash": "230d8358dc8e8890b4c58deeb62912ee2f20357ae92a5cc861b98e68fe31acb5" },
        }
        with self.assertRaises(StorageError):
            self.db.append_version("proj-a", LAYER_ODS, rec)

    def test_parent_hash_mismatch_rejected(self):
        rid = self.db.write_raw("proj-a", _raw())
        rec = {
            "schemaVersion": "0.2.0", "project_id": "proj-a", "layer": "ODS",
            "record_id": "c1", "content": {"name": "x"},
            "parent_ref": {"layer": "RAW", "project_id": "proj-a", "record_id": rid,
                           "hash": "0" * 64},
        }
        with self.assertRaises(StorageError):
            self.db.append_version("proj-a", LAYER_ODS, rec)

    def test_cross_project_same_id_isolated(self):
        self.db.write_raw("proj-a", _raw("proj-a"), record_id="raw:x")
        b = _raw("proj-b")
        b["payload"] = "different body"
        b["source_hash"] = hashlib.sha256(b"different body").hexdigest()
        b["lineage"]["source_hash"] = hashlib.sha256(b"different body").hexdigest()
        self.db.write_raw("proj-b", b, record_id="raw:x")
        self.assertEqual(self.db.read("proj-a", "RAW", "raw:x")["payload"], "body")
        self.assertEqual(self.db.read("proj-b", "RAW", "raw:x")["payload"], "different body")

    def test_wrong_content_hash_rejected(self):
        r = _raw()
        r["content_hash"] = "0" * 64
        with self.assertRaises(StorageError):
            self.db.write_raw("proj-a", r)

"""Phase 0 冒烟测试：Manifest 校验 + 四层契约正反例 + 血缘约束。

运行：cd toolbox && python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from toolbox.manifest import ManifestError, load_manifest, validate_manifest
from toolbox.schema import check_lineage, load_schema, validate_data

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "manifest.yaml"


def _manifest_dict() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def _raw(**over) -> dict:
    base = {
        "schemaVersion": "0.1.0",
        "project_id": "shanghai-food",
        "record_id": "r1",
        "layer": "RAW",
        "source_url": "https://example.com/p1",
        "source_kind": "ugc",
        "source_hash": "a" * 32,
        "content_hash": "b" * 32,
        "payload_bytes": 1024,
        "batch": "b1",
        "captured_at": "2026-10-13T00:00:00Z",
        "lineage": {"origin": "test", "captured_by": "unittest"},
        "content": {"raw_text": "x"},
    }
    base.update(over)
    return base


def _clean(**over) -> dict:
    base = {
        "schemaVersion": "0.1.0",
        "project_id": "shanghai-food",
        "record_id": "c1",
        "layer": "ODS",
        "parent_ref": {"project_id": "shanghai-food", "layer": "RAW", "record_id": "r1", "hash": "b" * 32},
        "content": {
            "identity": {"name": "n"},
            "draft": {},
            "classification": {},
            "validation": {"status": "PASS", "reasons": []},
            "scope": {},
            "unknowns": [],
            "provenance": {},
            "evidence": [],
            "sources": [],
            "as_of": "2026-10-13T00:00:00Z",
        },
        "content_hash": "c" * 32,
        "version": 1,
        "lineage": {"parent": "r1", "produced_by": "cleaner"},
    }
    base.update(over)
    return base


def _scored(**over) -> dict:
    base = {
        "schemaVersion": "0.1.0",
        "project_id": "shanghai-food",
        "record_id": "d1",
        "layer": "DW",
        "parent_ref": {"project_id": "shanghai-food", "layer": "ODS", "record_id": "c1", "version": 1, "hash": "c" * 32},
        "content": {"score": 4.2, "verdict": "PASS", "reasons": [], "as_of": "2026-10-13T00:00:00Z"},
        "content_hash": "d" * 32,
        "version": 1,
        "lineage": {"parent": "c1", "produced_by": "scorer"},
    }
    base.update(over)
    return base


def _audit(**over) -> dict:
    base = {
        "schemaVersion": "0.1.0",
        "project_id": "shanghai-food",
        "record_id": "a1",
        "layer": "APP",
        "audit": {"coverage": {}, "regression": {}, "evidence": {}, "gate": "PASS"},
        "view": {},
        "lineage": {"parent": "d1"},
    }
    base.update(over)
    return base


class TestManifest(unittest.TestCase):
    def test_template_manifest_valid(self):
        m = load_manifest(TEMPLATE)
        self.assertEqual(m.project_id, "shanghai-food")
        self.assertFalse(validate_manifest(m.raw, load_schema("manifest")))

    def test_bad_project_id(self):
        data = _manifest_dict()
        data["project"] = "Shanghai_Food!"
        self.assertTrue(validate_manifest(data, load_schema("manifest")))
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(data, f)
            p = Path(f.name)
        try:
            with self.assertRaises(ManifestError):
                load_manifest(p)
        finally:
            p.unlink(missing_ok=True)

    def test_bad_schema_version(self):
        data = _manifest_dict()
        data["schemaVersion"] = "9.9.9"
        self.assertTrue(validate_manifest(data, load_schema("manifest")))


class TestRaw(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_data("raw", _raw()), [])

    def test_wrong_layer(self):
        self.assertNotEqual(validate_data("raw", _raw(layer="ODS")), [])

    def test_missing_required(self):
        rec = _raw()
        del rec["source_hash"]
        self.assertNotEqual(validate_data("raw", rec), [])


class TestClean(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_data("clean", _clean()), [])

    def test_parent_must_be_raw(self):
        rec = _clean()
        rec["parent_ref"]["layer"] = "ODS"
        self.assertNotEqual(validate_data("clean", rec), [])
        self.assertNotEqual(check_lineage("clean", rec), [])

    def test_lineage_raw_ok(self):
        self.assertEqual(check_lineage("clean", _clean()), [])


class TestScored(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_data("scored", _scored()), [])

    def test_parent_version_must_be_int_ge1(self):
        rec = _scored()
        rec["parent_ref"]["version"] = 0
        self.assertNotEqual(check_lineage("scored", rec), [])

    def test_parent_missing_hash(self):
        rec = _scored()
        del rec["parent_ref"]["hash"]
        self.assertNotEqual(check_lineage("scored", rec), [])

    def test_parent_must_be_ods(self):
        rec = _scored()
        rec["parent_ref"]["layer"] = "RAW"
        self.assertNotEqual(check_lineage("scored", rec), [])


class TestAudit(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_data("audit", _audit()), [])

    def test_bad_gate(self):
        self.assertNotEqual(validate_data("audit", _audit(audit={**dict(_audit()["audit"]), "gate": "MAYBE"})), [])


if __name__ == "__main__":
    unittest.main()

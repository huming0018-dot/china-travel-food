"""Manifest load/validate tests: schema, trust boundaries, path isolation."""

import json
import tempfile
import unittest
from pathlib import Path

from toolbox.manifest import Manifest, ManifestError

def _valid() -> dict:
    """Fresh valid manifest each call (deep, no shared mutable state between tests)."""
    return {
        "schemaVersion": "0.2.0",
        "project": {"project_id": "shanghai-c3", "name": "n", "domain": "food", "region": "shanghai"},
        "storage": {"backend": "sqlite", "path": "data/x.sqlite"},
        "pipelines": {
            "raw": {"schemaVersion": "0.2.0", "target": "data/raw"},
            "clean": {"schemaVersion": "0.2.0", "target": "data/clean"},
            "scored": {"schemaVersion": "0.2.0", "target": "data/scored"},
            "audit": {"schemaVersion": "0.2.0", "target": "data/audit"},
        },
    }


class ManifestTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, data: dict, name: str = "manifest.yaml") -> Path:
        p = self.root / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p


class TestManifestValid(ManifestTestBase):
    def test_valid_manifest_loads(self):
        m = Manifest.load(self._write(_valid()))
        self.assertEqual(m.project_id, "shanghai-c3")
        self.assertEqual(m.domain, "food")
        self.assertEqual(m.region, "shanghai")

    def test_yaml_manifest_loads(self):
        p = self.root / "m.yaml"
        p.write_text(
            "schemaVersion: \"0.2.0\"\n"
            "project:\n  project_id: a-b\n  name: n\n  domain: d\n  region: r\n"
            "storage:\n  backend: sqlite\n  path: data/x.sqlite\n"
            "pipelines:\n  raw: {schemaVersion: \"0.2.0\", target: data/raw}\n"
            "  clean: {schemaVersion: \"0.2.0\", target: data/clean}\n"
            "  scored: {schemaVersion: \"0.2.0\", target: data/scored}\n"
            "  audit: {schemaVersion: \"0.2.0\", target: data/audit}\n",
            encoding="utf-8",
        )
        m = Manifest.load(p)
        self.assertEqual(m.project_id, "a-b")


class TestManifestRejects(ManifestTestBase):
    def test_unknown_top_field_rejected(self):
        bad = _valid()
        bad["extra_field"] = 1
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_unknown_project_field_rejected(self):
        bad = _valid()
        bad["project"]["hack"] = True
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_unknown_pipeline_field_rejected(self):
        bad = _valid()
        bad["pipelines"]["raw"]["bogus"] = 1
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_bad_project_id_rejected(self):
        for pid in ("UPPER", "has space", "", "a" * 65, "9-start-ok-but-Upper"):
            bad = _valid()
            bad["project"]["project_id"] = pid
            with self.assertRaises(ManifestError):
                Manifest.load(self._write(bad))

    def test_wrong_schema_version_rejected(self):
        bad = _valid()
        bad["schemaVersion"] = "99.0.0"
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_absolute_target_rejected(self):
        bad = _valid()
        bad["pipelines"]["raw"]["target"] = "/etc/passwd"
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_dotdot_escape_rejected(self):
        bad = _valid()
        bad["pipelines"]["clean"]["target"] = "../escape"
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))

    def test_banned_dynamic_keys_rejected(self):
        for key in ("eval", "exec", "command", "template", "callback"):
            bad = _valid()
            bad["pipelines"]["scored"][key] = "danger"
            with self.assertRaises(ManifestError, msg=key):
                Manifest.load(self._write(bad))

    def test_missing_pipeline_layer_rejected(self):
        bad = _valid()
        del bad["pipelines"]["audit"]
        with self.assertRaises(ManifestError):
            Manifest.load(self._write(bad))


if __name__ == "__main__":
    unittest.main()

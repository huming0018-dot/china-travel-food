"""P1 manifest 0.3.0 tests: crawler/ontology contract, 0.2.0 compatibility, archive."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from toolbox.manifest import Manifest, ManifestError
from toolbox.schema import SchemaError, load_schema


def write_manifest(root: Path, data: dict) -> Path:
    d = root / "projects" / "demo"
    d.mkdir(parents=True)
    p = d / "manifest.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def base_030() -> dict:
    return {
        "schemaVersion": "0.3.2",
        "project": {"project_id": "demo", "name": "Demo", "domain": "demo", "region": "test"},
        "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
        "crawler": {"connector": "http-public", "timeout_seconds": 30.0,
                    "max_requests": 8, "max_bytes": 8000000},
        "ontology": {"packs": ["cuisines"]},
        "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                      for k in ("raw", "clean", "scored", "audit")},
        "raw": {"sources": [
            {"source_id": "s1", "kind": "http-public",
             "url": "https://api.github.com/repos/openai/codex/releases/latest"},
        ]},
    }


class Manifest03Test(unittest.TestCase):
    def test_030_load(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(Path(td), base_030())
            m = Manifest.load(p)
            self.assertEqual(m.project_id, "demo")
            self.assertEqual(m.crawler["connector"], "http-public")
            self.assertEqual(m.ontology["packs"], ["cuisines"])
            self.assertEqual(len(m.raw["sources"]), 1)

    def test_020_compat(self):
        data = base_030()
        data["schemaVersion"] = "0.2.0"
        del data["crawler"]
        del data["ontology"]
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(Path(td), data)
            m = Manifest.load(p)
            self.assertEqual(m.crawler, {})
            self.assertEqual(m.ontology, {})

    def test_unknown_field_rejected(self):
        data = base_030()
        data["sneaky"] = {"x": 1}
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(Path(td), data)
            with self.assertRaises(ManifestError):
                Manifest.load(p)

    def test_dynamic_key_rejected(self):
        data = base_030()
        data["crawler"]["callback"] = "http://evil"
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(Path(td), data)
            with self.assertRaises(ManifestError):
                Manifest.load(p)

    def test_bad_budget_rejected(self):
        data = base_030()
        data["crawler"]["max_requests"] = 0
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(Path(td), data)
            with self.assertRaises(ManifestError):
                Manifest.load(p)

    def test_archive_schema_available(self):
        s = load_schema("manifest-archive-0.2.0")
        self.assertEqual(s["version"], "0.2.0")
        self.assertNotIn("crawler", s["properties"])

    def test_data_schemas_stay_020(self):
        for name in ("raw", "clean", "scored", "audit", "view"):
            s = load_schema(name)
            self.assertEqual(s.get("$id", "").rsplit("/", 1)[-1] if "$id" in s else None, None)
            # raw/clean/scored/audit/view schemaVersion constraints remain 0.2.0
            self.assertIn("0.2.0", s.get("properties", {}).get("schemaVersion", {}).get("const", ""))


if __name__ == "__main__":
    unittest.main()

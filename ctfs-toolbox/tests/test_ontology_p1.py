"""P1 ontology pack tests: install/verify/list/rollback, tamper, immutability."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from toolbox.ontology import OntologyManager, PackError


def sample_pack_dir(root: Path, pack_id="packs-a", version="0.1.0") -> Path:
    d = root / f"src-{pack_id}-{version}"
    d.mkdir(parents=True)
    d.joinpath("pack.yaml").write_text(f"""\
pack:
  schemaVersion: "0.1.0"
  pack_id: "{pack_id}"
  version: "{version}"
  domain: "demo"
  contract:
    fields:
      file: "fields.yaml"
      minEntries: 1
    pointers:
      file: "pointers.json"
    validation:
      file: "validation.yaml"
    rubric:
      file: "rubric.yaml"
    expectations:
      file: "expectations.yaml"
""", encoding="utf-8")
    d.joinpath("fields.yaml").write_text("mapping: {a: {field: x, pointer: /x}}\n", encoding="utf-8")
    d.joinpath("pointers.json").write_text(json.dumps({"pointers": {"/x": {"type": "string"}}}), encoding="utf-8")
    d.joinpath("validation.yaml").write_text("hash: {algorithm: sha256}\n", encoding="utf-8")
    d.joinpath("rubric.yaml").write_text("rules: []\n", encoding="utf-8")
    d.joinpath("expectations.yaml").write_text("cases: []\n", encoding="utf-8")
    return d


class OntologyTest(unittest.TestCase):
    def test_install_verify_list_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            om = OntologyManager(root)
            src = sample_pack_dir(root, "pack-a", "0.1.0")
            r1 = om.install(src)
            self.assertTrue(r1["active"])
            # immutable: same version again rejected
            with self.assertRaises(PackError):
                om.install(src)
            # list
            packs = om.list_packs()
            self.assertEqual(packs[0]["pack_id"], "pack-a")
            self.assertEqual(packs[0]["active"], "0.1.0")
            # verify
            self.assertTrue(om.verify("pack-a")["verified"])
            # install v0.2.0 -> becomes active
            src2 = sample_pack_dir(root, "pack-a", "0.2.0")
            r2 = om.install(src2)
            self.assertTrue(r2["active"])
            self.assertEqual(om.list_packs()[0]["active"], "0.2.0")
            # rollback keeps old version
            rb = om.rollback("pack-a", "0.1.0")
            self.assertEqual(rb["from"], "0.2.0")
            self.assertEqual(rb["to"], "0.1.0")
            self.assertEqual(sorted(rb["kept"]), ["0.1.0", "0.2.0"])
            self.assertEqual(om.list_packs()[0]["active"], "0.1.0")
            # load reads active version data
            loaded = om.load("pack-a")
            self.assertEqual(loaded["version"], "0.1.0")

    def test_tamper_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            om = OntologyManager(root)
            src = sample_pack_dir(root, "pack-b", "0.1.0")
            om.install(src)
            self.assertTrue(om.verify("pack-b")["verified"])
            target = root / "packs" / "pack-b" / "0.1.0" / "fields.yaml"
            target.write_text("mapping: {tampered: true}\n", encoding="utf-8")
            with self.assertRaises(PackError) as cm:
                om.verify("pack-b")
            self.assertIn("tamper", str(cm.exception))

    def test_contract_violation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "bad"
            src.mkdir()
            src.joinpath("pack.yaml").write_text(
                "pack:\n  schemaVersion: \"0.1.0\"\n  pack_id: \"bad\"\n  version: \"0.1.0\"\n"
                "  contract: {}\n", encoding="utf-8")
            om = OntologyManager(root)
            with self.assertRaises(PackError):
                om.install(src)

    def test_dynamic_code_keys_rejected_by_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "evil"
            src.mkdir()
            src.joinpath("pack.yaml").write_text(
                "pack:\n  schemaVersion: \"0.1.0\"\n  pack_id: \"evil\"\n  version: \"0.1.0\"\n"
                "  exec: \"import os\"\n  contract: {}\n", encoding="utf-8")
            om = OntologyManager(root)
            with self.assertRaises(PackError):
                om.install(src)


if __name__ == "__main__":
    unittest.main()

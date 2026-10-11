"""P1-03: regression tests mirroring the independent reviewer's 12 failed
counterexamples (additional-counterexamples.json + EARLY-FINDINGS.md)."""
import json
import pathlib
import sys
import tempfile
import threading
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml

from toolbox.ontology import OntologyManager, PackError
from toolbox.manifest import Manifest, ManifestError
from toolbox.crawler import Crawler, CrawlerError
from toolbox.storage import SqliteStorage


def make_pack(src: pathlib.Path, pack_id: str, version: str = "0.1.0") -> pathlib.Path:
    src.mkdir(parents=True, exist_ok=True)
    (src / "pack.yaml").write_text(
        "pack:\n  schemaVersion: \"0.1.0\"\n  pack_id: " + pack_id
        + '\n  version: "' + version + '"\n  domain: "demo"\n  contract:\n'
        "    fields:\n      file: fields.yaml\n"
        "    pointers:\n      file: pointers.json\n"
        "    validation:\n      file: validation.yaml\n"
        "    rubric:\n      file: rubric.yaml\n"
        "    expectations:\n      file: expectations.yaml\n", encoding="utf-8")
    (src / "fields.yaml").write_text("mappings:\n  a: b\nrequired_fields:\n  - a\n",
                                     encoding="utf-8")
    (src / "pointers.json").write_text('{"a": ["content", "a"]}', encoding="utf-8")
    (src / "validation.yaml").write_text("rules:\n  a_min: 1\nlimits:\n  a_max: 10\n",
                                         encoding="utf-8")
    (src / "rubric.yaml").write_text("admission:\n  threshold: 3.5\n", encoding="utf-8")
    (src / "expectations.yaml").write_text("expected_candidates: 1\n", encoding="utf-8")
    return src


def temp_store() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix="p1-gate03b-"))


def manifest032(proj: pathlib.Path, source: dict) -> pathlib.Path:
    doc = {
        "schemaVersion": "0.3.2",
        "project": {"project_id": "p", "name": "p", "domain": "test",
                    "region": "test"},
        "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
        "pipelines": {
            "raw": {"schemaVersion": "0.2.0", "target": "data/raw"},
            "clean": {"schemaVersion": "0.2.0", "target": "data/clean"},
            "scored": {"schemaVersion": "0.2.0", "target": "data/scored"},
            "audit": {"schemaVersion": "0.2.0", "target": "data/audit"},
        },
        "raw": {"sources": [source]},
    }
    mp = proj / "manifest.yaml"
    mp.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return mp


def manifest020(proj: pathlib.Path, source: dict,
                extra: dict | None = None) -> pathlib.Path:
    doc = {
        "schemaVersion": "0.2.0",
        "project": {"project_id": "p", "name": "p", "domain": "test",
                    "region": "test"},
        "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
        "pipelines": {
            "raw": {"schemaVersion": "0.2.0", "target": "data/raw"},
            "clean": {"schemaVersion": "0.2.0", "target": "data/clean"},
            "scored": {"schemaVersion": "0.2.0", "target": "data/scored"},
            "audit": {"schemaVersion": "0.2.0", "target": "data/audit"},
        },
        "raw": {"sources": [source]},
    }
    if extra:
        doc.update(extra)
    mp = proj / "manifest.yaml"
    mp.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return mp


class CounterexampleRegression(unittest.TestCase):

    # ---- 1) snapshot expected_sha required (missing -> rejected) ----
    def test_snapshot_expected_sha_missing_rejected(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        src = proj / "inputs" / "f.txt"
        src.parent.mkdir(parents=True)
        src.write_bytes(b"x" * 5)
        from toolbox.connector_snapshot import SnapshotFileConnector
        from toolbox.connector import FetchContext
        att = SnapshotFileConnector().fetch(FetchContext(
            source={"source_id": "s1", "kind": "snapshot-file",
                    "url": "snapshot://inputs/f.txt", "max_bytes": 100},
            project_dir=proj))
        self.assertFalse(att.ok)
        self.assertIn("expected_sha", att.error)

    # ---- 2) manifest 0.2.0 rejects new crawler/ontology/source_connector ----
    def test_manifest_020_rejects_new_crawler_fields(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        mp = manifest020(proj, {
            "source_id": "s1", "kind": "snapshot-file",
            "url": "snapshot://inputs/f.json", "expected_sha": "a" * 64,
        }, {"crawler": {"max_requests": 1, "max_bytes": 1}})
        with self.assertRaises(ManifestError):
            Manifest.load(mp)

    def test_manifest_020_rejects_new_ontology_fields(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        mp = manifest020(proj, {
            "source_id": "s1", "kind": "snapshot-file",
            "url": "snapshot://inputs/f.json", "expected_sha": "a" * 64,
        }, {"ontology": {"packs": [{"pack_id": "cuisines", "version": "0.1.0"}]}})
        with self.assertRaises(ManifestError):
            Manifest.load(mp)

    def test_manifest_020_rejects_new_source_connector(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        mp = manifest020(proj, {
            "source_id": "s1", "kind": "http-public", "connector": "my-plugin",
            "url": "https://example.com/x",
        })
        with self.assertRaises(ManifestError):
            Manifest.load(mp)

    # ---- 3) each of the five contract files missing -> PackError ----
    def test_pack_missing_contract_files(self):
        store = temp_store()
        mgr = OntologyManager(store)
        for fname in ("fields.yaml", "pointers.json", "validation.yaml",
                      "rubric.yaml", "expectations.yaml"):
            src = pathlib.Path(tempfile.mkdtemp(prefix="pack-src-"))
            make_pack(src, "pk-" + fname.split(".")[0])
            (src / fname).unlink()
            with self.assertRaises(PackError, msg=fname):
                mgr.install(src)

    # ---- 4) nested NaN in JSON -> PackError ----
    def test_pack_json_nested_nan_rejected(self):
        store = temp_store()
        mgr = OntologyManager(store)
        src = pathlib.Path(tempfile.mkdtemp(prefix="pack-nan-"))
        make_pack(src, "pknan")
        (src / "pointers.json").write_text('{"x": {"y": NaN}}', encoding="utf-8")
        with self.assertRaises(PackError):
            mgr.install(src)

    # ---- 5) hidden extra file rejected at verify ----
    def test_pack_hidden_extra_file_rejected_at_verify(self):
        store = temp_store()
        mgr = OntologyManager(store)
        src = pathlib.Path(tempfile.mkdtemp(prefix="pack-hidden-"))
        make_pack(src, "pkhidden")
        mgr.install(src)
        ver_dir = store / "packs" / "pkhidden" / "0.1.0"
        (ver_dir / ".evil.py").write_text("print('evil')", encoding="utf-8")
        with self.assertRaises(PackError):
            mgr.verify("pkhidden")

    # ---- 6) concurrent distinct-version installs keep both index entries ----
    def test_pack_concurrent_distinct_versions_index_kept(self):
        store = temp_store()
        mgr = OntologyManager(store)
        base = pathlib.Path(tempfile.mkdtemp(prefix="pack-conc-"))
        make_pack(base, "pkconc", "0.1.0")
        mgr.install(base)
        v021 = pathlib.Path(tempfile.mkdtemp(prefix="pack-conc2-"))
        make_pack(v021, "pkconc", "0.2.1")
        v022 = pathlib.Path(tempfile.mkdtemp(prefix="pack-conc3-"))
        make_pack(v022, "pkconc", "0.2.2")
        errs = []

        def run(src):
            try:
                OntologyManager(store).install(src)
            except Exception as exc:  # noqa: BLE001
                errs.append(exc)

        t1 = threading.Thread(target=run, args=(v021,))
        t2 = threading.Thread(target=run, args=(v022,))
        t1.start(); t2.start(); t1.join(); t2.join()
        if errs:
            raise errs[0]
        idx = json.loads((store / "packs" / "pkconc" / "index.json").read_text())
        self.assertIn("0.2.1", idx["versions"])
        self.assertIn("0.2.2", idx["versions"])
        dirs = sorted(d.name for d in (store / "packs" / "pkconc").iterdir()
                      if d.is_dir() and d.name not in (".stage", ".index.lock"))
        self.assertTrue(all(d in idx["versions"] for d in dirs),
                        msg=f"orphaned dirs {dirs} not in index {list(idx['versions'])}")

    # ---- 7) manifest accepts registered plugin connector; unknown fails pre-crawl ----
    def test_manifest_accepts_registered_plugin_connector_name(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        mp = manifest032(proj, {
            "source_id": "s1", "kind": "http-public", "connector": "audit-data",
            "url": "https://example.com/x",
        })
        m = Manifest.load(mp)  # must NOT raise; registry checked at crawl time
        self.assertEqual(m.raw["sources"][0]["connector"], "audit-data")

    def test_manifest_unknown_connector_fails_before_acquisition(self):
        proj = pathlib.Path(tempfile.mkdtemp())
        src = proj / "inputs" / "f.json"
        src.parent.mkdir(parents=True)
        src.write_text(json.dumps({"a": 1}), encoding="utf-8")
        mp = manifest032(proj, {
            "source_id": "s1", "kind": "snapshot-file",
            "connector": "not-installed-plugin",
            "url": "snapshot://inputs/f.json", "expected_sha": "a" * 64,
        })
        m = Manifest.load(mp)
        (proj / "data").mkdir(parents=True, exist_ok=True)
        crawler = Crawler(m, SqliteStorage(proj / "data" / "store.sqlite"))
        try:
            with self.assertRaises(CrawlerError):
                crawler.crawl("s1")
        finally:
            crawler.close()


if __name__ == "__main__":
    unittest.main()

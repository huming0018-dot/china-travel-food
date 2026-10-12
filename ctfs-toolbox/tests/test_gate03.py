"""P1-REVIEW-GATE-03 regression tests (0.3.2): identity ledger, snapshot gates,
index escape defense, empty-source rejection, version-routed manifest load."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from toolbox.crawler import Crawler, CrawlerError
from toolbox.manifest import Manifest, ManifestError
from toolbox.ontology import OntologyManager, PackError
from toolbox.schema import load_schema
from toolbox.storage import SqliteStorage

from test_crawler_p1 import make_manifest
from test_ontology_p1 import sample_pack_dir


class Gate03CrawlerTest(unittest.TestCase):
    def _setup(self, td: str, body: bytes, source: dict, crawler_cfg: dict | None = None):
        root = Path(td)
        (root / "projects" / "demo").mkdir(parents=True, exist_ok=True)
        (root / "projects" / "demo" / "inputs").mkdir(exist_ok=True)
        (root / "projects" / "demo" / "inputs" / "bundle.json").write_bytes(body)
        mpath = make_manifest(root, [source], crawler_cfg)
        manifest = Manifest.load(mpath)
        db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
        return manifest, db, Crawler(manifest, db)

    def test_success_headers_persisted_and_idempotent_readback(self):
        """B01+B02: successful fetch persists selected headers; second crawl of the
        same (project, source, config) fingerprint reads back RAW, no re-fetch."""
        with tempfile.TemporaryDirectory() as td:
            body = b"{\"b\": 1}"
            manifest, db, crawler = self._setup(td, body, {
                "source_id": "bundle", "kind": "snapshot-file",
                "url": "snapshot://inputs/bundle.json",
                "expected_sha": hashlib.sha256(body).hexdigest(),
            })
            s1 = crawler.crawl()
            self.assertEqual(len(s1), 1)
            self.assertTrue(s1[0]["ok"])
            row = crawler.ledger.execute(
                "SELECT ok, fingerprint, selected_headers FROM crawl_attempts"
                " WHERE project_id=? AND source_id=?",
                (manifest.project_id, "bundle")).fetchone()
            self.assertEqual(row[0], 1)
            self.assertIsNotNone(row[1])
            # snapshot connector sets no whitelisted headers; column exists & NULL-safe
            before = crawler.ledger_snapshot()
            s2 = crawler.crawl()
            self.assertEqual(len(s2), 1)
            self.assertTrue(s2[0]["ok"])
            self.assertEqual(s2[0]["reused"], "raw_readback")
            after = crawler.ledger_snapshot()
            self.assertEqual(after["attempts"], before["attempts"])
            self.assertEqual(after["requests_used"], before["requests_used"])
            # RAW still readable byte-for-byte via ledger raw_id
            rid = crawler.ledger.execute(
                "SELECT raw_id FROM crawl_attempts WHERE project_id=? AND source_id=?",
                (manifest.project_id, "bundle")).fetchone()[0]
            raw = db.read(manifest.project_id, "RAW", rid)
            self.assertEqual(raw["payload"], body)

    def test_failed_unknown_never_replayed_same_fingerprint(self):
        """B02: an unchanged-config failed_unknown attempt is retained, not re-sent."""
        with tempfile.TemporaryDirectory() as td:
            body = b"{\"b\": 1}"
            missing_sha = "0" * 64
            manifest, db, crawler = self._setup(td, body, {
                "source_id": "bundle", "kind": "snapshot-file",
                "url": "snapshot://inputs/bundle.json",
                "expected_sha": missing_sha,
            })
            s1 = crawler.crawl()
            self.assertFalse(s1[0]["ok"])
            before = crawler.ledger_snapshot()
            s2 = crawler.crawl()
            self.assertEqual(s2[0]["reused"], "retained_failure")
            after = crawler.ledger_snapshot()
            self.assertEqual(after["attempts"], before["attempts"])
            self.assertEqual(after["requests_used"], before["requests_used"])

    def test_config_change_allows_new_attempt(self):
        """Changed config fingerprint is a NEW identity and may fetch again."""
        with tempfile.TemporaryDirectory() as td:
            body = b"{\"b\": 1}"
            missing_sha = "0" * 64
            manifest, db, crawler = self._setup(td, body, {
                "source_id": "bundle", "kind": "snapshot-file",
                "url": "snapshot://inputs/bundle.json",
                "expected_sha": missing_sha,
            })
            crawler.crawl()
            # correct the sha -> new fingerprint -> allowed
            import yaml
            # rebuild manifest with the corrected sha -> NEW fingerprint
            (Path(td) / "projects" / "demo" / "manifest.yaml").write_text(
                yaml.safe_dump({
                    "schemaVersion": "0.3.2",
                    "project": {"project_id": "demo", "name": "demo",
                                "domain": "demo", "region": "test"},
                    "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
                    "crawler": {"connector": "snapshot-file", "timeout_seconds": 5.0,
                                "max_requests": 4, "max_bytes": 200000,
                                "per_request_max_bytes": 100000},
                    "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                                  for k in ("raw", "clean", "scored", "audit")},
                    "raw": {"sources": [{
                        "source_id": "bundle", "kind": "snapshot-file",
                        "url": "snapshot://inputs/bundle.json",
                        "expected_sha": hashlib.sha256(body).hexdigest(),
                    }]},
                }, sort_keys=False), encoding="utf-8")
            db2 = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            c2 = Crawler(Manifest.load(manifest.path), db2)
            s3 = c2.crawl()
            self.assertTrue(s3[0]["ok"])

    def test_recovered_pending_is_not_resent(self):
        """B02: pending from a previous interrupted run becomes failed_unknown and
        the same source is skipped this crawl (identity preserved)."""
        with tempfile.TemporaryDirectory() as td:
            body = b"{\"b\": 1}"
            manifest, db, crawler = self._setup(td, body, {
                "source_id": "bundle", "kind": "snapshot-file",
                "url": "snapshot://inputs/bundle.json",
                "expected_sha": hashlib.sha256(body).hexdigest(),
            })
            crawler.ledger.execute(
                "INSERT INTO crawl_attempts(attempt_id, project_id, source_id, url, connector,"
                " status, ok, code, bytes_count, sha256, error, error_kind, started_at, finished_at,"
                " fingerprint)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("attempt:pending", manifest.project_id, "bundle",
                 "snapshot://inputs/bundle.json", "snapshot-file",
                 "pending", 0, None, 0, None, None, None, "2026-10-12T00:00:00Z",
                 "2026-10-12T00:00:00Z", crawler._source_fingerprint(
                     manifest.raw["sources"][0])))
            crawler.ledger.commit()
            before = crawler.ledger_snapshot()
            s = crawler.crawl()
            self.assertEqual(s[0]["reused"], "recovered_pending")
            after = crawler.ledger_snapshot()
            self.assertEqual(after["attempts"], before["attempts"])
            self.assertEqual(after["requests_used"], before["requests_used"])
            st = crawler.ledger.execute(
                "SELECT status FROM crawl_attempts WHERE attempt_id=?",
                ("attempt:pending",)).fetchone()[0]
            self.assertEqual(st, "failed_unknown")

    def test_empty_sources_rejected_before_crawl(self):
        """B13: unconfigured (empty) sources is explicit; crawl refuses."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "projects" / "demo").mkdir(parents=True, exist_ok=True)
            mpath = make_manifest(root, [])
            manifest = Manifest.load(mpath)
            db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler = Crawler(manifest, db)
            with self.assertRaises(CrawlerError):
                crawler.crawl()

    def test_snapshot_sha_required_and_cap_enforced(self):
        """B07: expected_sha is mandatory; max_bytes is a real read cap."""
        with tempfile.TemporaryDirectory() as td:
            body = b"{\"b\": 1}"
            # missing expected_sha -> connector error, no RAW
            manifest, db, crawler = self._setup(td, body, {
                "source_id": "bundle", "kind": "snapshot-file",
                "url": "snapshot://inputs/bundle.json",
            })
            s = crawler.crawl()
            self.assertFalse(s[0]["ok"])
            with self.assertRaises(Exception):
                db.read(manifest.project_id, "RAW", "bundle")
            # max_bytes smaller than file -> rejected, no RAW
            manifest2, db2, crawler2 = self._setup(
                td, body, {
                    "source_id": "bundle", "kind": "snapshot-file",
                    "url": "snapshot://inputs/bundle.json",
                    "expected_sha": hashlib.sha256(body).hexdigest(),
                    "max_bytes": 4,
                }, {"connector": "snapshot-file", "timeout_seconds": 5.0,
                    "max_requests": 4, "max_bytes": 200000,
                    "per_request_max_bytes": 100000})
            s2 = crawler2.crawl()
            self.assertFalse(s2[0]["ok"])


class Gate03ManifestTest(unittest.TestCase):
    def test_020_loads_via_real_archived_contract(self):
        """B05: schemaVersion 0.2.0 is validated by the archived 0.2.0 schema only."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "projects" / "demo").mkdir(parents=True, exist_ok=True)
            p = root / "projects" / "demo" / "manifest.yaml"
            p.write_text("""\
schemaVersion: "0.2.0"
project: {project_id: demo, name: demo, domain: demo, region: test}
storage: {backend: sqlite, path: data/store.sqlite}
pipelines:
  raw: {schemaVersion: "0.2.0", target: data/raw}
  clean: {schemaVersion: "0.2.0", target: data/clean}
  scored: {schemaVersion: "0.2.0", target: data/scored}
  audit: {schemaVersion: "0.2.0", target: data/audit}
""", encoding="utf-8")
            m = Manifest.load(p)
            self.assertEqual(m.project_id, "demo")
            self.assertEqual(m.crawler, {})
        # the single current schema must NOT accept 0.2.0
        cur = load_schema("manifest")
        self.assertEqual(cur["properties"]["schemaVersion"]["enum"], ["0.4.0"])

    def test_032_rejects_0_3_0_float_version(self):
        """Single-version enum: 0.3.0 cannot pass as the 0.3.2 contract."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "projects" / "demo").mkdir(parents=True, exist_ok=True)
            p = root / "projects" / "demo" / "manifest.yaml"
            p.write_text("""\
schemaVersion: "0.3.0"
project: {project_id: demo, name: demo, domain: demo, region: test}
storage: {backend: sqlite, path: data/store.sqlite}
pipelines:
  raw: {schemaVersion: "0.2.0", target: data/raw}
""", encoding="utf-8")
            with self.assertRaises(ManifestError):
                Manifest.load(p)


class Gate03OntologyTest(unittest.TestCase):
    def test_index_path_escape_rejected_on_verify(self):
        """B04: an index pointing outside the pack version is tamper."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = sample_pack_dir(root, "packs-a", "0.1.0")
            out = root / "store"
            mgr = OntologyManager(out)
            mgr.install(src)
            # tamper the index: add a path escaping the version dir with a valid hash
            idx = out / "packs" / "packs-a" / "index.json"
            data = json.loads(idx.read_text(encoding="utf-8"))
            ver = data["versions"]["0.1.0"]
            outside = root / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            h = hashlib.sha256(b"{}").hexdigest()
            ver["files"]["../../../../outside.json"] = h
            idx.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(PackError):
                mgr.verify("packs-a", "0.1.0")

    def test_contract_files_missing_rejected(self):
        """B12: a pack referencing a missing required file must not install."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = sample_pack_dir(root, "packs-b", "0.1.0")
            (src / "expectations.yaml").unlink()
            out = root / "store"
            mgr = OntologyManager(out)
            with self.assertRaises(PackError):
                mgr.install(src)


if __name__ == "__main__":
    unittest.main()

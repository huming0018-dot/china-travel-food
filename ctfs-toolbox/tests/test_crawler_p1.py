"""P1 crawler tests: budget ledger, attempt receipts, RAW write + restart readback."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from toolbox.crawler import Crawler, CrawlerError
from toolbox.manifest import Manifest
from toolbox.storage import SqliteStorage


def make_manifest(root: Path, sources, crawler=None) -> Path:
    project_dir = root / "projects" / "demo"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "data").mkdir(exist_ok=True)
    manifest = {
        "schemaVersion": "0.3.2",
        "project": {"project_id": "demo", "name": "demo", "domain": "demo", "region": "test"},
        "storage": {"backend": "sqlite", "path": "data/store.sqlite"},
        "crawler": crawler or {"connector": "snapshot-file", "timeout_seconds": 5.0,
                               "max_requests": 4, "max_bytes": 200000,
                               "per_request_max_bytes": 100000},
        "pipelines": {k: {"schemaVersion": "0.2.0", "target": "data/" + k}
                      for k in ("raw", "clean", "scored", "audit")},
        "raw": {"sources": sources},
    }
    p = project_dir / "manifest.yaml"
    import yaml
    p.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return p


class CrawlerTest(unittest.TestCase):
    def test_snapshot_crawl_and_restart_readback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            body = b"{\"fixture\": \"bundle-bytes\"} " + b"x" * 100
            (root / "projects" / "demo").mkdir(parents=True)
            (root / "projects" / "demo" / "inputs").mkdir()
            (root / "projects" / "demo" / "inputs" / "bundle.json").write_bytes(body)
            mpath = make_manifest(root, [
                {"source_id": "bundle", "kind": "snapshot-file",
                 "url": "snapshot://inputs/bundle.json",
                 "expected_sha": hashlib.sha256(body).hexdigest()},
            ])
            manifest = Manifest.load(mpath)
            db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler = Crawler(manifest, db)
            try:
                summaries = crawler.crawl()
            finally:
                crawler.close()
                db.close()
            self.assertEqual(len(summaries), 1)
            s = summaries[0]
            self.assertTrue(s["ok"])
            self.assertEqual(s["bytes"], len(body))
            self.assertEqual(s["sha256"], hashlib.sha256(body).hexdigest())
            self.assertIsNotNone(s["raw_id"])

            # restart readback: byte-for-byte
            db2 = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            got = db2.read("demo", "RAW", s["raw_id"])
            self.assertEqual(got["payload"], body)
            self.assertEqual(hashlib.sha256(got["payload"]).hexdigest(), s["sha256"])
            db2.close()

    def test_failed_attempt_kept_and_budget_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mpath = make_manifest(root, [
                {"source_id": "missing", "kind": "snapshot-file", "url": "snapshot://nope.json"},
            ])
            manifest = Manifest.load(mpath)
            db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler = Crawler(manifest, db)
            try:
                summaries = crawler.crawl()
            finally:
                crawler.close()
                db.close()
            s = summaries[0]
            self.assertFalse(s["ok"])
            self.assertIsNone(s["raw_id"])
            self.assertEqual(s["error_kind"], "not-found")
            # ledger recorded the failed attempt and consumed a request slot
            db3 = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler3 = Crawler(manifest, db3)
            snap = crawler3.ledger_snapshot()
            crawler3.close()
            db3.close()
            self.assertEqual(snap["attempts"], 1)
            self.assertEqual(snap["ok_total"], 0)
            self.assertEqual(snap["requests_used"], 1)

    def test_budget_exhaustion_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "projects" / "demo").mkdir(parents=True)
            (root / "projects" / "demo" / "inputs").mkdir()
            (root / "projects" / "demo" / "inputs" / "a.json").write_bytes(b"{}")
            (root / "projects" / "demo" / "inputs" / "b.json").write_bytes(b"{}")
            mpath = make_manifest(root, [
                {"source_id": "a", "kind": "snapshot-file", "url": "snapshot://inputs/a.json"},
                {"source_id": "b", "kind": "snapshot-file", "url": "snapshot://inputs/b.json"},
            ], crawler={"connector": "snapshot-file", "timeout_seconds": 5.0,
                        "max_requests": 1, "max_bytes": 100000,
                        "per_request_max_bytes": 50000})
            manifest = Manifest.load(mpath)
            db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler = Crawler(manifest, db)
            try:
                with self.assertRaises(CrawlerError):
                    crawler.crawl()
            finally:
                crawler.close()
                db.close()

    def test_source_hash_is_this_runs_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            body = b"exact-bytes-42"
            (root / "projects" / "demo").mkdir(parents=True)
            (root / "projects" / "demo" / "inputs").mkdir()
            (root / "projects" / "demo" / "inputs" / "x.json").write_bytes(body)
            mpath = make_manifest(root, [
                {"source_id": "x", "kind": "snapshot-file",
                 "url": "snapshot://inputs/x.json",
                 "expected_sha": hashlib.sha256(body).hexdigest()},
            ])
            manifest = Manifest.load(mpath)
            db = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            crawler = Crawler(manifest, db)
            try:
                summaries = crawler.crawl()
            finally:
                crawler.close()
                db.close()
            self.assertEqual(summaries[0]["sha256"], hashlib.sha256(body).hexdigest())
            db2 = SqliteStorage(manifest.path.parent / "data" / "store.sqlite")
            got = db2.read("demo", "RAW", summaries[0]["raw_id"])
            self.assertEqual(got["source_hash"], hashlib.sha256(body).hexdigest())
            self.assertEqual(got["payload"], body)
            db2.close()


if __name__ == "__main__":
    unittest.main()

"""P1 connector security tests: URL/path trust boundaries, Unicode quote check."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toolbox.connector import FetchContext, load_connectors
from toolbox.connector_snapshot import SnapshotFileConnector
from toolbox.validators import ValidatorError, safe_url, unicode_quote_check

BAD_URLS = [
    "http://example.com/x",              # not https
    "https://localhost/x",               # localhost
    "https://127.0.0.1/x",              # loopback
    "https://10.0.0.5/x",               # private
    "https://192.168.1.10/x",           # private
    "https://172.16.0.1/x",             # private
    "https://169.254.169.254/latest",   # link-local
    "https://user:pass@example.com/x",  # credentials
    "https://example.com:8443/x",       # non-443
    "https://db.internal/x",            # .internal suffix
]


class SafeUrlTest(unittest.TestCase):
    def test_bad_urls_rejected(self):
        for url in BAD_URLS:
            with self.assertRaises(ValidatorError, msg=url):
                safe_url(url)

    def test_good_urls_accepted(self):
        for url in ("https://api.github.com/repos/openai/codex/releases/latest",
                    "https://etather.com/en/news/shanghai-september-2026-restaurant-openings"):
            self.assertEqual(safe_url(url), url)


class ConnectorSecurityTest(unittest.TestCase):
    def test_http_public_rejects_non_https_before_connect(self):
        connectors = load_connectors()
        conn = connectors["http-public"]
        with tempfile.TemporaryDirectory() as td:
            ctx = FetchContext(source={"source_id": "x", "url": "http://example.com/x"},
                               project_dir=Path(td))
            attempt = conn.fetch(ctx)
            self.assertFalse(attempt.ok)
            self.assertIn("https", attempt.error)

    def test_snapshot_rejects_escapes(self):
        conn = SnapshotFileConnector()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("hello", encoding="utf-8")
            for bad_url in ("snapshot://../etc/passwd",
                            "snapshot:///etc/passwd",
                            "snapshot://missing.txt"):
                attempt = conn.fetch(FetchContext(
                    source={"source_id": "s", "url": bad_url}, project_dir=root))
                self.assertFalse(attempt.ok, bad_url)
            # SHA mismatch
            import hashlib
            body = (root / "ok.txt").read_bytes()
            wrong = "0" * 64
            attempt = conn.fetch(FetchContext(
                source={"source_id": "s", "url": "snapshot://ok.txt",
                        "expected_sha": wrong}, project_dir=root))
            self.assertFalse(attempt.ok)
            self.assertIn("SHA mismatch", attempt.error)
            # good path
            good = hashlib.sha256(body).hexdigest()
            attempt = conn.fetch(FetchContext(
                source={"source_id": "s", "url": "snapshot://ok.txt",
                        "expected_sha": good}, project_dir=root))
            self.assertTrue(attempt.ok)
            self.assertEqual(attempt.sha256, good)

    def test_snapshot_symlink_escape(self):
        conn = SnapshotFileConnector()
        outer = tempfile.mkdtemp(prefix="ctfs-outer-")
        root = Path(tempfile.mkdtemp(prefix="ctfs-proj-"))
        try:
            outside = Path(outer) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            (root / "link.txt").symlink_to(outside)
            attempt = conn.fetch(FetchContext(
                source={"source_id": "s", "url": "snapshot://link.txt"}, project_dir=root))
            self.assertFalse(attempt.ok)
            self.assertIn("escape", attempt.error)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(outer, ignore_errors=True)


class UnicodeQuoteTest(unittest.TestCase):
    def test_exact_slice(self):
        body = "上海新店 Atelier Jiu 七月柿 Leyas"
        unicode_quote_check(body, 4, 15, body[4:15])
        with self.assertRaises(ValidatorError):
            unicode_quote_check(body, 4, 15, body[4:14])  # mismatched quote
        with self.assertRaises(ValidatorError):
            unicode_quote_check(body, -1, 15, body[-1:15])  # negative start
        with self.assertRaises(ValidatorError):
            unicode_quote_check(body, 10, 10, "")  # start == end
        with self.assertRaises(ValidatorError):
            unicode_quote_check(body, 0, 9999, "x")  # end > len


if __name__ == "__main__":
    unittest.main()

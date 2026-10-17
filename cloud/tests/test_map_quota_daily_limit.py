"""Isolated regression tests for Amap supplier daily quota vs local monthly budget."""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import map_quota as MQ


class MapQuotaDailyLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = MQ.MapQuota(str(pathlib.Path(self.tmp.name) / "ledger.json"))
        self.pool.keys = {"amap": [("a", ""), ("b", "")], "tencent": [("t", "")]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_10044_sets_supplier_daily_block_and_preserves_month_bucket(self):
        rec = self.pool._rec("amap", 0)
        rec["monthly"]["used"] = 120
        rec["daily"]["used"] = 8
        expected = 1234567890.0
        with patch.object(self.pool, "_next_midnight", return_value=expected):
            self.assertEqual(self.pool.report("amap", 0, "search", False, infocode="10044"), "rate")
        self.assertEqual(rec["dead_reason"], "daily_quota")
        self.assertEqual(rec["dead_until"], expected)
        self.assertEqual(rec["monthly"]["used"], 121)
        self.assertEqual(rec["daily"]["used"], 8)

    def test_10003_is_daily_and_10007_is_temporary_auth_circuit(self):
        rec = self.pool._rec("amap", 0)
        with patch.object(self.pool, "_next_midnight", return_value=1234567890.0):
            self.assertEqual(self.pool.report("amap", 0, "search", False, infocode="10003"), "rate")
        self.assertEqual(rec["dead_reason"], "daily_quota")
        self.assertEqual(self.pool.report("amap", 1, "search", False, infocode="10007"), "auth")
        auth = self.pool._rec("amap", 1)
        self.assertEqual(auth["dead_reason"], "auth")
        self.assertEqual(auth["monthly"]["used"], 0)

    def test_month_budget_remains_hard_limit_after_daily_rollover(self):
        rec = self.pool._rec("amap", 0)
        cap = MQ.LIMITS[("amap", "search")]
        rec["monthly"].update(window="2026-10", used=cap)
        rec["daily"].update(window="2026-10-16", used=9)
        rec.update(dead_reason="daily_quota", dead_until=9999999999)
        self.pool._rec("amap", 1)["monthly"]["used"] = cap
        with patch.object(MQ, "_today", return_value="2026-10-17"), patch.object(MQ, "_month", return_value="2026-10"):
            self.pool._roll_windows()
        self.assertEqual(rec["daily"]["used"], 0)
        self.assertEqual(rec["monthly"]["used"], cap)
        self.assertIsNone(self.pool.acquire("phone", "amap", "search"))

    def test_daily_rollover_releases_10044_but_preserves_month_usage(self):
        rec = self.pool._rec("amap", 0)
        rec["daily"].update(window="2026-10-16", used=3)
        rec["monthly"].update(window="2026-10", used=321)
        rec.update(dead_reason="daily_quota", dead_until=9999999999)
        with patch.object(MQ, "_today", return_value="2026-10-17"), patch.object(MQ, "_month", return_value="2026-10"):
            self.pool._roll_windows()
        self.assertIsNone(rec["dead_reason"])
        self.assertEqual(rec["daily"]["used"], 0)
        self.assertEqual(rec["monthly"]["used"], 321)
        self.assertIsNotNone(self.pool.acquire("phone", "amap", "search"))

    def test_per_key_states_allow_only_unblocked_key(self):
        a, b = self.pool._rec("amap", 0), self.pool._rec("amap", 1)
        a.update(dead_reason="daily_quota", dead_until=9999999999)
        a["monthly"]["used"] = 100
        b["monthly"]["used"] = 200
        self.assertEqual(self.pool.acquire("phone", "amap", "search")["index"], 1)
        b["monthly"]["used"] = MQ.LIMITS[("amap", "search")]
        self.assertIsNone(self.pool.acquire("phone", "amap", "search"))

    def test_old_monthly_quota_record_is_migrated_without_resetting_month_use(self):
        rec = self.pool._rec("amap", 0)
        rec.update(dead_reason="monthly_quota", dead_until=9999999999)
        rec["monthly"].update(window="2026-10", used=400)
        with patch.object(MQ, "_today", return_value="2026-10-17"), patch.object(MQ, "_month", return_value="2026-10"), patch.object(self.pool, "_next_midnight", return_value=1234567890.0):
            self.pool._roll_windows()
        self.assertEqual(rec["dead_reason"], "daily_quota")
        self.assertEqual(rec["dead_until"], 1234567890.0)
        self.assertEqual(rec["monthly"]["used"], 400)

    def test_block_reason_separates_daily_supplier_block_from_month_exhaustion(self):
        cap = MQ.LIMITS[("amap", "search")]
        for idx in range(2):
            self.pool._rec("amap", idx).update(dead_reason="daily_quota", dead_until=9999999999)
        self.assertEqual(self.pool.block_reason("amap", "search"), "transient")
        for idx in range(2):
            self.pool._rec("amap", idx)["monthly"]["used"] = cap
        self.assertEqual(self.pool.block_reason("amap", "search"), "exhausted")


if __name__ == "__main__":
    unittest.main()

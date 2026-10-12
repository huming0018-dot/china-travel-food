"""Offline regression: no credentials, live HTTP or database calls."""
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import map_quota as MQ


def response(provider="amap", code=None, **extra):
    data = {"status": "1" if code is None else "0", "infocode": code}
    if provider == "tencent":
        data = {"status": 0 if code is None else code}
    return Mock(json=Mock(return_value={**data, **extra}), raise_for_status=Mock())


class FailoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = MQ.MapQuota(str(pathlib.Path(self.tmp.name) / "ledger.json"))
        self.pool.keys = {"amap": [("fake-a", ""), ("fake-b", "")],
                          "tencent": [("fake-t", "")]}
        self.pool_patch = patch.object(MQ, "MapQuota", return_value=self.pool)
        self.pool_patch.start()
        self.sleep_patch = patch.object(MQ.time, "sleep")
        self.sleep_patch.start()

    def tearDown(self):
        self.pool_patch.stop()
        self.sleep_patch.stop()
        self.tmp.cleanup()

    def call(self, provider="amap", consumer="full"):
        return MQ.call(provider, "/fake", {}, "search", consumer)

    def test_first_key_quota_second_success(self):
        with patch("requests.request", side_effect=[response(code="10044"), response(pois=[])]) as req:
            self.assertEqual(self.call()[1], "ok")
            self.assertEqual(req.call_count, 2)
            self.assertIn("fake-b", req.call_args.args[1])
        self.assertEqual(self.pool._rec("amap", 0)["dead_reason"], "daily_quota")
        self.assertEqual(self.pool._rec("amap", 1)["monthly"]["used"], 1)

    def test_first_auth_second_success(self):
        with patch("requests.request", side_effect=[response(code="10001"), response()]):
            self.assertEqual(self.call()[1], "ok")
        self.assertEqual(self.pool._rec("amap", 0)["monthly"]["used"], 0)

    def test_all_auth_is_not_quota(self):
        with patch("requests.request", return_value=response(code="10007")):
            self.assertEqual(self.call()[1], "auth")

    def test_all_quota(self):
        with patch("requests.request", return_value=response(code="10044")) as req:
            self.assertEqual(self.call()[1], "no_budget")
            self.assertEqual(req.call_count, 2)

    def test_network_rotates_with_backoff(self):
        import requests
        with patch("requests.request", side_effect=[requests.Timeout("secret URL"), response()]):
            self.assertEqual(self.call()[1], "ok")
        MQ.time.sleep.assert_called_once_with(0.25)

    def test_network_failure_not_empty_or_quota(self):
        import requests
        with patch("requests.request", side_effect=requests.Timeout()):
            self.assertEqual(self.call()[1], "network")

    def test_normal_empty_success_not_retried(self):
        with patch("requests.request", return_value=response(pois=[])) as req:
            self.assertEqual(self.call()[1], "ok")
            self.assertEqual(req.call_count, 1)

    def test_reserve_no_http_phone_can_use(self):
        for i in range(2):
            self.pool._rec("amap", i)["monthly"]["used"] = MQ.LIMITS[("amap", "search")] - 100
        with patch("requests.request", return_value=response()) as req:
            self.assertEqual(self.call()[1], "reserved")
            req.assert_not_called()
            self.assertEqual(self.call(consumer="phone")[1], "ok")

    def test_attempt_bound(self):
        self.pool.keys["amap"] = [(f"fake-{i}", "") for i in range(6)]
        with patch("requests.request", return_value=response(code="10044")) as req:
            self.assertEqual(self.call()[1], "retry_limit")
            self.assertEqual(req.call_count, 4)

    def test_window_reset(self):
        rec = self.pool._rec("amap", 0)
        rec["monthly"].update(window="2000-01", used=4500)
        rec.update(dead_reason="monthly_quota", dead_until=MQ.time.time() + 99999)
        self.assertIsNotNone(self.pool.acquire("full", "amap", "search"))
        self.assertEqual(rec["monthly"]["used"], 0)
        self.assertIsNone(rec["dead_reason"])
        rec = self.pool._rec("tencent", 0)
        rec["daily"].update(window="2000-01-01", used=9000)
        rec.update(dead_reason="daily_quota", dead_until=MQ.time.time() + 99999)
        self.assertIsNotNone(self.pool.acquire("full", "tencent", "search"))
        self.assertEqual(rec["daily"]["used"], 0)

    def test_receipt_persisted_without_key(self):
        with patch("requests.request", return_value=response(code="10044")):
            self.call()
        import json
        ledger = json.loads(pathlib.Path(self.pool.ledger_path).read_text())
        self.assertEqual(ledger["keys"]["amap:0"]["last_code"], "10044")
        self.assertNotIn("fake-a", json.dumps(ledger))

    def test_midnight_is_beijing(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        fixed = datetime(2026, 10, 12, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.object(MQ, "_now", return_value=fixed):
            reset = datetime.fromtimestamp(self.pool._next_midnight(), ZoneInfo("Asia/Shanghai"))
            self.assertEqual(reset.isoformat(), "2026-10-13T00:00:00+08:00")

    def test_unconfigured_is_not_quota(self):
        self.pool.keys["amap"] = []
        with patch("requests.request") as req:
            self.assertEqual(self.call()[1], "unconfigured")
            req.assert_not_called()

    def test_tencent_invalid_key_and_normal_no_results(self):
        self.pool.keys["tencent"].append(("fake-t2", ""))
        with patch("requests.request", side_effect=[response("tencent", 190), response("tencent", 347)]):
            self.assertEqual(self.call("tencent")[1], "ok")
        self.assertEqual(self.pool._rec("tencent", 0)["dead_reason"], "auth")

    def test_transient_then_quota_does_not_return_rate(self):
        import requests
        with patch("requests.request", side_effect=[requests.Timeout(), response(code="10044")]):
            self.assertEqual(self.call()[1], "error")

    def test_account_daily_receipt_recovers_without_resetting_month_usage(self):
        with patch("requests.request", return_value=response(code="10044")):
            self.call()
        rec = self.pool._rec("amap", 0)
        rec["daily"]["window"] = "2000-01-01"
        self.pool._roll_windows()
        self.assertIsNone(rec["dead_reason"])
        self.assertEqual(rec["monthly"]["used"], 1)


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = types.ModuleType("common")
        cls.common.addr_core = lambda x: x
        cls.helpers = types.ModuleType("map_helpers")
        cls.helpers.pick_best = Mock()
        modules = {"common": cls.common, "map_helpers": cls.helpers,
                   "health": types.ModuleType("health"), "ingest": types.ModuleType("ingest")}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("fill_test", ROOT / "cloud_amap_fill.py")
            cls.fill = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.fill)

    def test_tencent_fallback_success_and_full_budget(self):
        candidate = {"title": "test", "address": "test", "tel": "123", "lng": 121, "lat": 31}
        self.helpers.pick_best.return_value = (candidate, 0.9)
        with patch.object(MQ, "call", return_value=({"data": [{**candidate, "location": {"lng": 121, "lat": 31}}]}, "ok")) as call:
            poi, status = self.fill._fallback("test", "test", "QUOTA")
            self.assertFalse(status)
            self.assertEqual(poi["source"], "tencent")
            self.assertEqual(call.call_args.args[4], "full")
            self.assertIn("map.qq.com", self.fill._poi_source(poi, "test"))

    def test_both_exhausted_stop(self):
        with patch.object(self.fill, "_tencent_poi", return_value=(None, "QUOTA")):
            self.assertEqual(self.fill._fallback("a", "b", "QUOTA"), (None, "quota"))

    def test_reserve_yields_not_quota(self):
        with patch.object(self.fill, "_tencent_poi", return_value=(None, "YIELD")):
            self.assertEqual(self.fill._fallback("a", "b", "QUOTA"), (None, "yield"))

    def test_auth_and_tencent_exhausted_not_global_quota(self):
        with patch.object(self.fill, "_tencent_poi", return_value=(None, "QUOTA")):
            self.assertEqual(self.fill._fallback("a", "b", "AUTH"), (None, "error"))

    def test_quality_gate_rejects_weak_match(self):
        self.helpers.pick_best.return_value = ({"tel": "123"}, 0.59)
        with patch.object(MQ, "call", return_value=({"data": []}, "ok")):
            self.assertEqual(self.fill._tencent_poi("a", "b"), (None, False))

    def test_amap_empty_not_retried(self):
        with patch.object(MQ, "call", return_value=({"pois": []}, "ok")) as call:
            self.assertEqual(self.fill.amap_text("a"), [])
            call.assert_called_once()

    def test_main_service_error_does_not_penalize_restaurant(self):
        with tempfile.TemporaryDirectory() as directory:
            data = pathlib.Path(directory)
            row = {"id": 1, "name": "test", "address": "test"}
            with patch.object(self.fill, "STATS_F", data / "stats.json"), \
                 patch.object(self.fill, "_read_state", return_value={}), \
                 patch.object(self.fill, "_write_state") as save, \
                 patch.object(self.fill, "_load_cache", return_value={}), \
                 patch.object(self.common, "today", return_value="2026-10-12", create=True), \
                 patch.object(self.common, "fetch_all", return_value=[row], create=True), \
                 patch.object(self.fill, "amap_text", return_value="NETWORK"), \
                 patch.object(self.fill, "_tencent_poi", return_value=(None, "QUOTA")), \
                 patch.object(MQ, "MapQuota") as pool, \
                 patch.object(MQ, "load_provider_keys", return_value=[("fake", "")]), \
                 patch.object(sys, "argv", ["fill"]):
                pool.return_value.snapshot.return_value = {}
                self.assertEqual(self.fill.main(), 0)
                self.assertEqual(save.call_args.args[0]["fail"], {})
                import json
                stats = json.loads((data / "stats.json").read_text())["amap_fill"]
                self.assertEqual(stats["service_errors"], 1)
                self.assertEqual(stats["no_match"], 0)
                self.assertFalse(stats["quota_stopped"])


if __name__ == "__main__":
    unittest.main()

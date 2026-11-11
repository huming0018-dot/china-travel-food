"""Offline regression tests: no credentials or live requests are used."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import types
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "price_realign_under_test", ROOT / "cloud/vendor/pipeline/price_realign.py")
P = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"common": types.SimpleNamespace()}):
    spec.loader.exec_module(P)

SCENES = ["正餐", "快餐小吃", "咖啡茶饮", "面包", "甜品", "酒吧"]


def thresholds():
    return [dict(scene=s, band=i + 1, lo=lo, hi=hi)
            for s in SCENES
            for i, (lo, hi) in enumerate(
                [(None, 20), (20, 40), (40, 70), (70, 90), (90, None)])]


def restaurant(rid=1, price=10, scene="正餐", status="active", band=None, label=None):
    return dict(id=rid, name=f"fixture {rid}", price_avg=price,
                price_scene=scene, status=status, price_band=band, price_position=label)


class FakeAPI:
    def __init__(self, rows=None, config=None):
        self.rows = rows if rows is not None else [
            restaurant(i + 1, scene=s) for i, s in enumerate(SCENES)]
        self.config = config if config is not None else thresholds()
        self.writes = []

    def fetch_all(self, table, *args, **kwargs):
        return copy.deepcopy(self.rows if table == "restaurants" else self.config)

    def req(self, *args, **kwargs):
        method, path = args
        query = parse_qs(urlsplit(path).query)
        rid = int(query["id"][0].removeprefix("eq."))
        rows = [r for r in self.rows if r["id"] == rid]
        if method == "PATCH":
            self.writes.append((args, kwargs))
            for row in rows:
                if all(value[0] == ("is.null" if row.get(key) is None else f"eq.{row[key]}")
                       for key, value in query.items()):
                    row.update(kwargs["json"])
            return types.SimpleNamespace(status_code=204, json=lambda: None)
        if method == "GET":
            return types.SimpleNamespace(status_code=200, json=lambda: copy.deepcopy(rows))
        raise AssertionError(f"unexpected method {method}")


def run_main(api, *args, write_enabled=True):
    out = io.StringIO()
    with patch.dict(os.environ, {"FOOD_PRICE_ALIGNMENT_WRITES_ENABLED": "1" if write_enabled else ""}), patch.object(P, "C", api), patch.object(sys, "argv", ["price_realign.py", *args]), contextlib.redirect_stdout(out):
        status = P.main()
    return status, out.getvalue()


class PriceAlignmentTests(unittest.TestCase):
    def test_apply_is_blocked_without_explicit_write_enable_before_api_access(self):
        status, output = run_main(types.SimpleNamespace(), "--apply", write_enabled=False)
        self.assertEqual(status, 2)
        self.assertIn("WRITE BLOCKED", output)

    def test_programmatic_apply_is_also_blocked_without_write_enable(self):
        with patch.dict(os.environ, {"FOOD_PRICE_ALIGNMENT_WRITES_ENABLED": ""}), patch.object(P, "C", types.SimpleNamespace()):
            with self.assertRaisesRegex(P.AlignmentError, "WRITE BLOCKED"):
                P.apply({"changes": []})

    def test_dry_run_uses_database_vocabulary_without_writes(self):
        api = FakeAPI()
        _, output = run_main(api)
        self.assertIn("经济", output)
        self.assertNotIn("旗舰", output)
        self.assertEqual(api.writes, [])

    def test_boundaries_follow_approved_configuration_not_recomputed_quantiles(self):
        prices = [0, 19, 20, 39, 40, 69, 70, 89, 90, 99999]
        api = FakeAPI([restaurant(i + 1, price=p) for i, p in enumerate(prices)])
        status, _ = run_main(api, "--apply")
        self.assertEqual(status, 0)
        self.assertEqual([r["price_band"] for r in api.rows], [1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
        self.assertEqual([r["price_position"] for r in api.rows],
                         ["经济", "经济", "平价", "平价", "中端", "中端", "高端", "高端", "奢华", "奢华"])
        self.assertTrue(all(call[0][1].startswith("/restaurants?") for call in api.writes))
        self.assertTrue(all(set(call[1]["json"]) == {"price_band", "price_position"} for call in api.writes))

    def test_repeated_run_is_idempotent(self):
        api = FakeAPI()
        self.assertEqual(run_main(api, "--apply")[0], 0)
        api.writes.clear()
        self.assertEqual(run_main(api, "--apply")[0], 0)
        self.assertEqual(api.writes, [])

    def test_each_scene_uses_its_own_thresholds(self):
        config = thresholds()
        for t in config:
            if t["scene"] == "酒吧":
                t["lo"] = t["lo"] * 10 if t["lo"] is not None else None
                t["hi"] = t["hi"] * 10 if t["hi"] is not None else None
        api = FakeAPI([restaurant(1, 50), restaurant(2, 50, "酒吧")], config)
        self.assertEqual(run_main(api, "--apply")[0], 0)
        self.assertEqual([r["price_band"] for r in api.rows], [3, 1])

    def test_incomplete_or_invalid_thresholds_abort_before_writes(self):
        variants = []
        variants.append(thresholds()[:-1])
        variants.append(thresholds() + [thresholds()[0]])
        for key, value in [("lo", 21), ("hi", 20), ("hi", "40"), ("band", True)]:
            config = thresholds()
            config[1][key] = value
            variants.append(config)
        for config in variants:
            with self.subTest(config=config[:2]):
                api = FakeAPI(config=config)
                status, output = run_main(api, "--apply")
                self.assertNotEqual(status, 0)
                self.assertIn("ERROR", output)
                self.assertEqual(api.writes, [])

    def test_invalid_prices_and_duplicate_ids_abort_before_writes(self):
        for price in [-1, 100000, float("nan"), float("inf"), "20", True, 20.5]:
            with self.subTest(price=price):
                api = FakeAPI([restaurant(price=price)])
                self.assertNotEqual(run_main(api, "--apply")[0], 0)
                self.assertEqual(api.writes, [])
        api = FakeAPI([restaurant(), restaurant()])
        self.assertNotEqual(run_main(api, "--apply")[0], 0)
        self.assertEqual(api.writes, [])

    def test_missing_price_unknown_scene_and_closed_rows_are_reported_and_preserved(self):
        api = FakeAPI([restaurant(1, None), restaurant(2, 10, "未知"),
                       restaurant(3, 10, status="closed")])
        before = copy.deepcopy(api.rows)
        status, output = run_main(api, "--apply")
        self.assertEqual(status, 0)
        self.assertIn("missing_price", output)
        self.assertIn("unknown_scene", output)
        self.assertEqual(api.rows, before)
        self.assertEqual(api.writes, [])

    def test_empty_restaurants_is_a_safe_noop(self):
        api = FakeAPI([])
        self.assertEqual(run_main(api, "--apply")[0], 0)
        self.assertEqual(api.writes, [])

    def test_patch_constraint_failure_stops_and_returns_nonzero(self):
        api = FakeAPI()
        def fail(method, path, **kwargs):
            api.writes.append((method, path))
            return types.SimpleNamespace(status_code=400, json=lambda: {"code": "23514"})
        api.req = fail
        status, output = run_main(api, "--apply")
        self.assertNotEqual(status, 0)
        self.assertIn("23514", output)
        self.assertIn("id=1", output)
        self.assertEqual(len(api.writes), 1)

    def test_noop_patch_is_not_counted_as_success(self):
        api = FakeAPI()
        original = api.req
        def noop(method, path, **kwargs):
            if method == "PATCH":
                return types.SimpleNamespace(status_code=204, json=lambda: None)
            return original(method, path, **kwargs)
        api.req = noop
        status, output = run_main(api, "--apply")
        self.assertNotEqual(status, 0)
        self.assertIn("readback", output)

    def test_stale_price_is_not_overwritten(self):
        api = FakeAPI()
        original = api.req
        def race(method, path, **kwargs):
            if method == "PATCH":
                api.rows[0]["price_avg"] = 100
            return original(method, path, **kwargs)
        api.req = race
        self.assertNotEqual(run_main(api, "--apply")[0], 0)
        self.assertIsNone(api.rows[0]["price_band"])

    def test_network_failure_is_not_retried_or_leaked(self):
        api = FakeAPI()
        calls = []
        def network_failure(*args, **kwargs):
            calls.append(kwargs.get("retries"))
            raise RuntimeError("secret_credentials_must_not_be_logged")
        api.req = network_failure
        status, output = run_main(api, "--apply")
        self.assertNotEqual(status, 0)
        self.assertEqual(calls, [1])
        self.assertNotIn("secret_credentials", output)

    def test_configuration_drift_aborts_before_patch(self):
        api = FakeAPI()
        original = api.fetch_all
        count = 0
        def changing(table, *args, **kwargs):
            nonlocal count
            if table == "price_band_thresholds":
                count += 1
                if count == 2:
                    api.config[0]["hi"] = 21
                    api.config[1]["lo"] = 21
            return original(table, *args, **kwargs)
        api.fetch_all = changing
        self.assertNotEqual(run_main(api, "--apply")[0], 0)
        self.assertEqual(api.writes, [])

    def test_threshold_change_between_rows_stops_before_next_patch(self):
        api = FakeAPI()
        original = api.req
        def change_after_first_readback(method, path, **kwargs):
            result = original(method, path, **kwargs)
            if method == "GET":
                api.config[0]["hi"] = 21
                api.config[1]["lo"] = 21
            return result
        api.req = change_after_first_readback
        status, output = run_main(api, "--apply")
        self.assertEqual(status, 1)
        self.assertEqual(len(api.writes), 1)
        self.assertIn("thresholds changed", output)

    def test_partial_failure_reports_verified_count_and_stops(self):
        api = FakeAPI()
        original = api.req
        def fail_second(method, path, **kwargs):
            if method == "PATCH" and "id=eq.2&" in path:
                return types.SimpleNamespace(status_code=400, json=lambda: {"code": "23514"})
            return original(method, path, **kwargs)
        api.req = fail_second
        status, output = run_main(api, "--apply")
        self.assertEqual(status, 1)
        self.assertIn("verified=1/6", output)
        self.assertNotIn("[apply OK]", output)
        self.assertEqual(api.rows[0]["price_position"], "经济")
        self.assertIsNone(api.rows[2]["price_position"])

    def test_offline_snapshot_and_report_need_no_api(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot, report = Path(directory) / "in.json", Path(directory) / "out.json"
            snapshot.write_text(json.dumps({"restaurants": [restaurant()], "thresholds": thresholds()}))
            status, _ = run_main(types.SimpleNamespace(), "--snapshot", str(snapshot), "--report", str(report))
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(report.read_text())["changes"][0]["after"],
                             {"price_band": 1, "price_position": "经济"})

    def test_offline_snapshot_cannot_write_production(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            run_main(types.SimpleNamespace(), "--snapshot", "unused.json", "--apply")
        self.assertEqual(error.exception.code, 2)

    def test_snapshot_cli_runs_without_live_client_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(json.dumps({"restaurants": [restaurant()], "thresholds": thresholds()}))
            result = subprocess.run([sys.executable, "-S", str(ROOT / "cloud/vendor/pipeline/price_realign.py"),
                                     "--snapshot", str(snapshot)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[dry-run]", result.stdout)


class PatrolExitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("patrol_under_test", ROOT / "cloud/cloud_patrol.py")
        cls.patrol = importlib.util.module_from_spec(spec)
        modules = {name: types.SimpleNamespace() for name in
                   ("common", "merge_duplicates", "patrol_classify", "entity_dedup", "closed_watch")}
        with patch.dict(sys.modules, modules), patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(cls.patrol)

    def test_required_child_nonzero_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "failure.py"
            script.write_text("import sys\nprint('constraint rejection')\nsys.exit(1)\n")
            with self.assertRaisesRegex(RuntimeError, "constraint rejection"):
                self.patrol.run_script([str(script)], required=True)

    def test_required_child_timeout_is_not_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "timeout"):
            self.patrol.run_script(["-c", "import time; time.sleep(10)"], timeout=0.01, required=True)

    def test_successful_child_output_is_preserved(self):
        self.assertEqual(self.patrol.run_script(["-c", "print('verified')"], required=True), "verified\n")

    def test_patrol_price_defaults_to_read_only(self):
        calls = []
        with patch.dict(os.environ, {"FOOD_PRICE_ALIGNMENT_WRITES_ENABLED": ""}), patch.object(
                self.patrol, "run_script", side_effect=lambda args, **kwargs: calls.append(args) or "summary"):
            output = self.patrol.run_price_alignment()
        self.assertNotIn("--apply", calls[0])
        self.assertIn("DRY-RUN", output)

    def test_patrol_price_write_requires_explicit_enable(self):
        calls = []
        with patch.dict(os.environ, {"FOOD_PRICE_ALIGNMENT_WRITES_ENABLED": "1"}), patch.object(
                self.patrol, "run_script", side_effect=lambda args, **kwargs: calls.append(args) or "summary"):
            self.patrol.run_price_alignment()
        self.assertIn("--apply", calls[0])


if __name__ == "__main__":
    unittest.main()

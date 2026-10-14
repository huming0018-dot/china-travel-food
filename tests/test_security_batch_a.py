"""安全 A 批（F01/F02/F14/F15/F27）离线隔离测试。

约束：无网络、无凭据、无生产数据。所有写入均用 mock 拦截，前端部分用静态门
+ node 对 esc() 行为做注入载荷断言（不依赖 jsdom）。
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PIPE = ROOT / "cloud" / "vendor" / "pipeline"
CLOUD = ROOT / "cloud"
EXT = ROOT / "crowd_extension"
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(CLOUD))
os.environ["FOOD_PIPELINE_DIR"] = str(PIPE)
for k in ("TENCENT_MAP_KEY", "TENCENT_MAP_SK", "TENCENT_MAP_KEYS", "TENCENT_MAP_SKS",
          "AMAP_KEY", "AMAP_SK", "AMAP_KEYS", "AMAP_SKS"):
    os.environ.pop(k, None)

import entity_dedup as ED          # noqa: E402
import closed_relocate as CR       # noqa: E402
import tencent_sig as TS           # noqa: E402
import map_quota as MQ             # noqa: E402
import secret_redact as SR         # noqa: E402

# 合成的假密钥（仅用于脱敏测试，形状与真实腾讯 key/SK 一致但不是真实凭据）：
# 测试绝不内嵌真实密钥——真实密钥形状检测用结构正则，避免把秘密重新写进仓库。
FAKE_TENCENT_KEY = "TE5T5-AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
FAKE_TENCENT_SK = "0123456789abcdef0123456789abcdef"
JWT = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
       "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
KEY_SHAPE = re.compile(r"[A-Z0-9]{5}(?:-[A-Z0-9]{5}){5}")
SK_SHAPE = re.compile(r"\b[A-Za-z0-9]{32}\b")


def _rests():
    return [
        dict(id=1, name="同牌餐厅", location="POINT(121.0 31.0)", status="active",
             phone=None, address=None, brand_norm=None, city="上海",
             closed_date=None, closed_source=None, data_updated_at=None,
             created_at=None, price_avg=None, evidence_summary=None,
             aliases=None, web_session=None),
        dict(id=2, name="同牌餐厅", location="POINT(121.0006 31.0)", status="active",
             phone=None, address=None, brand_norm=None, city="上海",
             closed_date=None, closed_source=None, data_updated_at=None,
             created_at=None, price_avg=None, evidence_summary=None,
             aliases=None, web_session=None),
    ]


# ---------------------------------------------------------------- A1
class EntityWriteLockTests(unittest.TestCase):
    def test_ed_apply_rejected_before_any_io(self):
        with patch.object(sys, "argv", ["entity_dedup.py", "--apply"]), \
             patch.object(ED.C, "fetch_all") as fetch, patch.object(ED.C, "req") as req:
            with self.assertRaises(SystemExit) as e:
                ED.main()
            self.assertEqual(e.exception.code, 2)
            fetch.assert_not_called()
            req.assert_not_called()

    def test_ed_migrate_functions_raise_on_import_path_and_never_write(self):
        with patch.object(ED.C, "req") as req:
            for fn in (lambda: ED.migrate_child_row(
                           "restaurant_cuisines", "restaurant_id",
                           lambda r: r.get("cuisine_id"), False,
                           {"restaurant_id": 2, "cuisine_id": 9}, 1, []),
                       lambda: ED.migrate_children(2, 1, [])):
                with self.assertRaises(ED.EntityWriteDisabled):
                    fn()
            req.assert_not_called()

    def test_cr_apply_rejected_before_any_io(self):
        with patch.object(sys, "argv", ["closed_relocate.py", "--apply"]), \
             patch.object(CR.C, "req") as req:
            with self.assertRaises(SystemExit) as e:
                CR.main()
            self.assertEqual(e.exception.code, 2)
            req.assert_not_called()

    def test_cr_readonly_plan_is_review_only(self):
        with tempfile.TemporaryDirectory() as d:
            plan = str(Path(d) / "cr_plan.json")
            with patch.object(sys, "argv", ["closed_relocate.py", "--plan", plan]), \
                 patch.object(CR.C, "req") as req, contextlib.redirect_stdout(io.StringIO()):
                CR.main()
            data = json.loads(Path(plan).read_text())
            self.assertFalse(data["executable"])
            self.assertEqual(data["status"], "REVIEW_ONLY")
            self.assertTrue(data["write_disabled"])
            # 只读 GET 允许；绝无 PATCH/DELETE/POST
            for c in req.call_args_list:
                self.assertEqual(c.args[0], "GET")

    def test_ed_readonly_plan_is_review_only(self):
        with tempfile.TemporaryDirectory() as d:
            plan = str(Path(d) / "ed_plan.json")
            def fake_fetch(table, *a, **k):
                return _rests() if table == "restaurants" else []
            get_resp = types.SimpleNamespace(json=lambda: [])
            with patch.object(sys, "argv", ["entity_dedup.py", "--plan", plan]), \
                 patch.object(ED.C, "fetch_all", side_effect=fake_fetch), \
                 patch.object(ED.C, "req", return_value=get_resp) as req, \
                 contextlib.redirect_stdout(io.StringIO()):
                ED.main()
            data = json.loads(Path(plan).read_text())
            self.assertFalse(data["executable"])
            self.assertEqual(data["status"], "REVIEW_ONLY")
            # 只读 GET 允许；绝无 PATCH/DELETE/POST
            for c in req.call_args_list:
                self.assertEqual(c.args[0], "GET")

    def test_keep_file_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(ED, "KEEP_FILES", [str(Path(d) / "k.json")]):
                # 缺失 → 空（静默跳过，keep 是可选的）
                self.assertEqual(ED.load_keep_pairs(), [])
                # 坏 JSON → fail closed
                Path(d, "k.json").write_text("{not json", encoding="utf-8")
                with self.assertRaises(ValueError):
                    ED.load_keep_pairs()
                # 非 list → fail closed
                Path(d, "k.json").write_text('{"1|2": true}', encoding="utf-8")
                with self.assertRaises(ValueError):
                    ED.load_keep_pairs()
                # 签名非法 → fail closed
                Path(d, "k.json").write_text('["a|b"]', encoding="utf-8")
                with self.assertRaises(ValueError):
                    ED.load_keep_pairs()
                # 合法 → 正常（含同簇多 id 的 keep 签名）
                Path(d, "k.json").write_text('["1|2", "3|4", "1087|1089|1094|1095"]', encoding="utf-8")
                self.assertEqual(ED.load_keep_pairs(), ["1|2", "3|4", "1087|1089|1094|1095"])

    def test_no_entity_delete_in_source(self):
        ed = (PIPE / "entity_dedup.py").read_text(encoding="utf-8")
        cr = (PIPE / "closed_relocate.py").read_text(encoding="utf-8")
        for src in (ed, cr):
            self.assertNotIn('C.req("DELETE"', src)
            self.assertNotIn('C.req("PATCH"', src)
            self.assertNotIn('C.req("POST"', src)


# ---------------------------------------------------------------- A2
class CredentialAndRedactionTests(unittest.TestCase):
    def test_tencent_no_env_raises_structured_unavailable(self):
        with self.assertRaises(TS.MapCredentialUnavailable):
            TS._configured_key_sk()
        with self.assertRaises(TS.MapCredentialUnavailable):
            TS.build_signed_url("/ws/geocoder/v1/", {"address": "x"})

    def test_tencent_signing_with_explicit_cred_never_embeds_sk(self):
        url = TS.build_signed_url("/ws/geocoder/v1/", {"address": "Mr & Mrs Bund"},
                                 key=FAKE_TENCENT_KEY, sk=FAKE_TENCENT_SK)
        self.assertIn("TE5T5", url)
        self.assertNotIn(FAKE_TENCENT_SK, url)
        self.assertIn("sig=", url)

    def test_map_quota_tencent_no_credentials_channel_stops(self):
        self.assertEqual(MQ.load_provider_keys("tencent"), [])
        j, st = MQ.call("tencent", "/x", {"q": 1}, "search", "test")
        self.assertIsNone(j)
        self.assertEqual(st, "no_credentials")

    def test_map_quota_amap_unaffected_by_tencent_missing(self):
        import requests as real_requests  # noqa: F401
        with patch.dict(os.environ, {"AMAP_KEYS": "fake-amap-key", "AMAP_SKS": ""}), \
             patch.dict(sys.modules, {"requests": _FakeRequestsModule()}):
            self.assertEqual(MQ.load_provider_keys("amap"), [("fake-amap-key", "")])
            j, st = MQ.call("amap", "/v3/place/text", {"keywords": "x"},
                            "search", "test")
            self.assertEqual(st, "ok")
            self.assertEqual(j, {"status": "1"})

    def test_no_hardcoded_secret_literals(self):
        ts = (PIPE / "tencent_sig.py").read_text(encoding="utf-8")
        mq = (CLOUD / "map_quota.py").read_text(encoding="utf-8")
        for src in (ts, mq):
            # 结构性检测：不允许出现任何腾讯 key 形态或 32 位 SK 形态的字面量
            self.assertIsNone(KEY_SHAPE.search(src), "源码中仍有腾讯 key 形态字面量")
            self.assertIsNone(SK_SHAPE.search(src), "源码中仍有 32 位 SK 形态字面量")

    def test_redact_jwt_key_url_bearer_and_containers(self):
        cases = [
            JWT,
            FAKE_TENCENT_KEY,
            "https://apis.map.qq.com/ws/geocoder/v1/?address=x&key=" + FAKE_TENCENT_KEY
            + "&sig=" + ("a" * 32),
            '{"authorization":"Bearer ' + JWT + '","apikey":"k"}',
            "Authorization: Bearer " + JWT,
        ]
        for raw in cases:
            out = SR.redact_str(raw)
            self.assertNotIn(FAKE_TENCENT_KEY, out)
            self.assertNotIn(JWT, out)
        d = SR.redact_secrets({"Authorization": "Bearer " + JWT, "apikey": FAKE_TENCENT_KEY,
                               "nested": ["sig=abcdef", {"x": 1}]})
        self.assertEqual(d["Authorization"], SR.REDACTED)
        self.assertEqual(d["apikey"], SR.REDACTED)
        # 非敏感键保留
        self.assertEqual(d["nested"][1]["x"], 1)
        # Exception 也脱敏
        exc = Exception("connect fail url=" + cases[2])
        out = SR.redact_secrets(exc)
        self.assertNotIn(FAKE_TENCENT_KEY, out)

    def test_redact_extra_secret_full_and_suffix_gone(self):
        secret = "SUPERSECRETVALUE123456"
        out = SR.redact_str("boom " + secret + " trailing", extra_secrets=[secret])
        self.assertNotIn(secret, out)
        self.assertNotIn(secret[-6:], out)
        self.assertIn(SR.REDACTED, out)


class _FakeResponse:
    def __init__(self, payload):
        self._p = payload
    def json(self):
        return self._p


class _FakeRequestsModule:
    """只够 map_quota.call 走通“发起请求→成功”的假 requests，不触网。"""
    def request(self, method, url, timeout=15):
        assert method == "GET"
        return _FakeResponse({"status": "1"})


# ---------------------------------------------------------------- A3
class XssEscapingTests(unittest.TestCase):
    FILES = {
        "owner-rate.html": EXT / "owner-rate.html",
        "status.html": EXT / "status.html",
        "submit.html": EXT / "submit.html",
        "popup.js": EXT / "src" / "popup.js",
        "onboarding.js": EXT / "src" / "onboarding.js",
    }

    def test_esc_defined_everywhere(self):
        for name, path in self.FILES.items():
            self.assertIn("function esc(s)", path.read_text(encoding="utf-8"),
                          f"{name} 缺少 esc()")

    def test_esc_neutralizes_payloads(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node 不可用，跳过 esc 行为测试（静态门仍生效）")
        src = (EXT / "submit.html").read_text(encoding="utf-8")
        m = re.search(r"function esc\(s\)\{[\s\S]*?\n\}", src)
        self.assertIsNotNone(m, "未找到 esc 函数")
        js = m.group(0) + r"""
const payloads = [
  '"><img src=x onerror=alert(1)>',
  "' onclick=alert(1) x='",
  "<script>alert(1)</script>",
  '"><svg/onload=alert(1)>',
  "\"><a href=\"javascript:alert(1)\">x</a>",
];
for (const p of payloads){
  const o = esc(p);
  // 结构性字符全部转义后，无法再构成标签/属性/事件/href 闭合，处理载荷只能是文本；
  // 不要求抹掉 onerror/javascript 这些“词”（作为文本无害），只要求无任何可解析结构。
  if (/[<>"']/.test(o)) { console.error('RAW MARKUP/QUOTE LEFT: '+o); process.exit(1); }
}
// 还原验证：把实体反转义后应等于原串（证明是无损转义，不是漏处理）
function unesc(s){
  return s.replace(/&#39;/g,"'").replace(/&quot;/g,'"').replace(/&gt;/g,'>')
          .replace(/&lt;/g,'<').replace(/&amp;/g,'&');
}
for (const p of payloads){ if (unesc(esc(p)) !== p) { console.error('not reversible: '+p); process.exit(1); } }
console.log('esc payloads neutralized');
"""
        with tempfile.TemporaryDirectory() as d:
            jf = Path(d) / "esc_test.js"
            jf.write_text(js, encoding="utf-8")
            r = subprocess.run([node, str(jf)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_static_sinks_wrapped(self):
        owner = self.FILES["owner-rate.html"].read_text(encoding="utf-8")
        self.assertIn("opt.textContent", owner)
        self.assertIn("appendChild(opt)", owner)
        self.assertNotIn("opt.outerHTML", owner)
        self.assertNotIn('storeList").innerHTML = d.map', owner)

        status = self.FILES["status.html"].read_text(encoding="utf-8")
        self.assertIn("esc(r.matched_store", status)
        self.assertIn("esc((r.participant_id", status)

        submit = self.FILES["submit.html"].read_text(encoding="utf-8")
        for needle in ("esc(d.keyword)", "esc(pid)", "esc(nid)", "esc(d.reason",
                       "esc(cnReason", "esc(failText", 'esc(url)'):
            self.assertIn(needle, submit, f"submit.html 缺少转义: {needle}")

        popup = self.FILES["popup.js"].read_text(encoding="utf-8")
        self.assertIn("esc(p.kw)", popup)

        onboarding = self.FILES["onboarding.js"].read_text(encoding="utf-8")
        self.assertIn("esc(pid)", onboarding)


if __name__ == "__main__":
    unittest.main()

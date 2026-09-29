#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_quota.py — 地图 API 配额仲裁 / 持久账本 / 统一 key 池 / POI 缓存（P1 核心）。

为什么存在（见 references/map-quota-fix.md）：
  - 高德「搜索」是【开发者账号·月】配额（个人 5000/月，10044=账号级），同账号多 key 不扩容；
  - 腾讯是【key·日】配额（个人 10000/日，121=日量）；
  - 旧实现 dead key 只在内存、腾讯单 key、电话被全字段批量饿死、同一 POI 重复调用。

本模块：
  1. 持久账本（/app/data/map_quota_ledger.json）：按 provider:key×接口 记日/月用量，
     本地日 0 点 / 月初自动滚动重置；真实返回码（腾讯121/111、高德10003/10044）驱动 dead；
  2. 统一 key 池（腾讯也支持多 key，默认回退 tencent_sig 的硬编码 key）；
  3. acquire(consumer, provider, interface) 预算仲裁：电话为最高优先并预留预算，
     全字段批量只花剩余预算，饿不死电话；
  4. 持久 POI 缓存：一次 extensions=all，电话/坐标/营业时间/全字段共享，命中不调用。

所有写盘原子（tmp+replace），异常一律回退安全值，绝不中断调用方。
"""
import hashlib
import json
import os
import re
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
LEDGER_PATH = os.environ.get("MAP_QUOTA_LEDGER", os.path.join(DATA_DIR, "map_quota_ledger.json"))
POICACHE_PATH = os.environ.get("MAP_POI_CACHE", os.path.join(DATA_DIR, "poi_cache.json"))

# ── 配额软上限（取官方值的 90%，留安全余量；可被环境覆盖）──
LIMITS = {
    ("tencent", "search"): int(os.environ.get("LIM_TENCENT_DAY", 9000)),
    ("tencent", "geocode"): int(os.environ.get("LIM_TENCENT_GEO_DAY", 9000)),
    ("amap", "search"): int(os.environ.get("LIM_AMAP_SEARCH_MONTH", 4500)),
    ("amap", "geocode"): int(os.environ.get("LIM_AMAP_GEO_DAY", 4500)),
}
# 电话任务在腾讯日池里的预留预算（低优先任务不得侵占）
PHONE_RESERVE = int(os.environ.get("MAP_PHONE_RESERVE", 3000))
# 电话在高德「搜索·月」池里的预留（保护 resolve_poi 的 amap 电话回退）
AMAP_PHONE_RESERVE = int(os.environ.get("AMAP_PHONE_RESERVE", 800))

# 消费者优先级：数字越小优先级越高
CONSUMER_PRIORITY = {"phone": 0, "coord": 1, "hours": 2, "full": 3}

# 腾讯默认 key/SK（与 tencent_sig 保持一致；可用 TENCENT_MAP_KEYS/SKS 覆盖）
TENCENT_FALLBACK_KEY = "7PQBZ-7IDKZ-YUHXF-7V2GG-M2B3O-4OBT6"
TENCENT_FALLBACK_SK = "4ibuevVyzenm3Xcz3X6b4rljRlhZHlZo"

AMAP_HTTP_BASE = "https://restapi.amap.com"
TENCENT_HTTP_BASE = "https://apis.map.qq.com"


# ───────────────────────── key 装载 ─────────────────────────
def _split_csv(raw):
    return [x.strip() for x in (raw or "").split(",")]


def load_provider_keys(provider):
    """返回 [(key, sk)]；保留位置，缺 sk 补空串。空串条目须保留位置（IP白名单key无SK）。"""
    if provider == "tencent":
        keys = [k for k in _split_csv(os.environ.get("TENCENT_MAP_KEYS")) if k]
        if not keys:
            keys = [TENCENT_FALLBACK_KEY]
        sks_raw = _split_csv(os.environ.get("TENCENT_MAP_SKS"))
        sks = sks_raw if any(s for s in sks_raw) else [TENCENT_FALLBACK_SK]
    else:  # amap
        keys = [k for k in _split_csv(os.environ.get("AMAP_KEYS")) if k]
        if not keys:
            single = os.environ.get("AMAP_KEY", "").strip()
            keys = [single] if single else []
        sks_raw = _split_csv(os.environ.get("AMAP_SKS"))
        if any(s for s in sks_raw):
            sks = sks_raw  # 保留位置，空串=IP白名单key无SK
        else:
            single_sk = os.environ.get("AMAP_SK", "").strip()
            sks = [single_sk] if single_sk else []
    sks = (sks + [""] * len(keys))[:len(keys)]
    return list(zip(keys, sks))


# ───────────────────────── 时间窗 ─────────────────────────
def _today():
    return time.strftime("%Y-%m-%d", time.localtime())


def _month():
    return time.strftime("%Y-%m", time.localtime())


def _new_key_rec(provider):
    return {"provider": provider, "daily": {"window": _today(), "used": 0},
            "monthly": {"window": _month(), "used": 0},
            "dead_until": None, "dead_reason": None}


class MapQuota:
    def __init__(self, ledger_path=LEDGER_PATH):
        self.ledger_path = ledger_path
        self.keys = {p: load_provider_keys(p) for p in ("tencent", "amap")}
        self.ledger = self._load()
        self._roll_windows()

    # ── 持久化 ──
    def _load(self):
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"keys": {}}

    def _save(self):
        try:
            tmp = self.ledger_path + ".tmp"
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.ledger, f, ensure_ascii=False)
            os.replace(tmp, self.ledger_path)
        except Exception as e:
            print(f"[map_quota] 账本保存失败: {e}")

    def _kid(self, provider, idx):
        return f"{provider}:{idx}"

    def _rec(self, provider, idx):
        kid = self._kid(provider, idx)
        rec = self.ledger["keys"].get(kid)
        if rec is None:
            rec = _new_key_rec(provider)
            self.ledger["keys"][kid] = rec
        return rec

    def _roll_windows(self):
        today, month, changed = _today(), _month(), False
        for rec in self.ledger["keys"].values():
            d, m = rec["daily"], rec["monthly"]
            if d["window"] != today:
                d.update(window=today, used=0)
                # 日级 dead（腾讯121 / 高德10003）到点清除
                if rec.get("dead_reason") in ("daily_quota",):
                    rec.update(dead_until=None, dead_reason=None)
                changed = True
            if m["window"] != month:
                m.update(window=month, used=0)
                if rec.get("dead_reason") in ("monthly_quota",):
                    rec.update(dead_until=None, dead_reason=None)
                changed = True
        if changed:
            self._save()

    # ── 配额读取 ──
    def _used_bucket(self, rec, interface):
        """搜索类 amap 走月桶；其余走日桶。"""
        return rec["monthly"] if (rec["provider"] == "amap" and interface == "search") else rec["daily"]

    def _is_dead(self, rec):
        return bool(rec.get("dead_until") and rec["dead_until"] > time.time())

    def _cap(self, provider, interface):
        return LIMITS[(provider, interface)]

    def _pool_remaining(self, provider, interface):
        """整个 provider 池在该接口上的剩余可用量（跳过 dead key）。"""
        total = 0
        for idx in range(len(self.keys[provider])):
            rec = self._rec(provider, idx)
            if self._is_dead(rec):
                continue
            bucket = self._used_bucket(rec, interface)
            total += max(0, self._cap(provider, interface) - bucket["used"])
        return total

    # ── 仲裁：领一把可用 key ──
    def acquire(self, consumer, provider, interface, need=1):
        """返回 {index,key,sk} 或 None（无预算/全 dead）。
        低优先消费者（full/hours）不得侵占电话预留预算。"""
        prio = CONSUMER_PRIORITY.get(consumer, 9)
        if prio > CONSUMER_PRIORITY["phone"] and interface == "search":
            reserve = PHONE_RESERVE if provider == "tencent" else AMAP_PHONE_RESERVE
            if self._pool_remaining(provider, interface) <= reserve:
                return None  # 剩余只够电话预留，低优先任务让路
        for idx, (key, sk) in enumerate(self.keys[provider]):
            rec = self._rec(provider, idx)
            if self._is_dead(rec):
                continue
            bucket = self._used_bucket(rec, interface)
            if bucket["used"] + need <= self._cap(provider, interface):
                return {"index": idx, "key": key, "sk": sk}
        return None

    # ── 上报真实结果：计数 + dead 判定 ──
    def report(self, provider, idx, interface, ok, code=None, infocode=None):
        rec = self._rec(provider, idx)
        bucket = self._used_bucket(rec, interface)
        bucket["used"] += 1
        result = "ok"
        if not ok:
            if provider == "tencent":
                if code == 121:
                    rec.update(dead_until=self._next_midnight(), dead_reason="daily_quota")
                    result = "rate"
                elif code == 111:
                    result = "sign_error"  # 签名问题不应 dead，调用方可清洗后重试
                else:
                    result = "error"
            else:  # amap
                ic = str(infocode)
                if ic == "10044":  # 账号级月配额
                    rec.update(dead_until=self._next_monthstart(), dead_reason="monthly_quota")
                    result = "rate"
                elif ic == "10003":  # 日配额
                    rec.update(dead_until=self._next_midnight(), dead_reason="daily_quota")
                    result = "rate"
                elif ic == "10007":
                    # 签名/鉴权错误（INVALID_USER_SIGNATURE）：不是配额耗尽。
                    # 短时熔断该 key（30min 后看门狗自动重探），且不消耗配额桶计数，
                    # 避免把鉴权错误误记成“月配额耗尽”并触发空转告警。
                    bucket["used"] -= 1
                    rec.update(dead_until=time.time() + 1800, dead_reason="auth")
                    result = "auth"
                else:
                    result = "error"
        self._save()
        return result

    @staticmethod
    def _next_midnight():
        now = time.localtime()
        return time.mktime(time.strptime(time.strftime("%Y-%m-%d", now), "%Y-%m-%d")) + 86400

    @staticmethod
    def _next_monthstart():
        y, m = int(time.strftime("%Y")), int(time.strftime("%m"))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        return time.mktime(time.strptime(f"{y:04d}-{m:02d}-01", "%Y-%m-%d"))

    # ── 快照（供播报）──
    def snapshot(self):
        out = {}
        for provider in ("tencent", "amap"):
            rows = []
            for idx in range(len(self.keys[provider])):
                rec = self._rec(provider, idx)
                rows.append({
                    "daily_used": rec["daily"]["used"],
                    "monthly_used": rec["monthly"]["used"],
                    "dead": self._is_dead(rec),
                    "reason": rec.get("dead_reason"),
                })
            out[provider] = {"keys": rows,
                             "search_remaining": self._pool_remaining(provider, "search")}
        return out


# ───────────────────────── 签名 URL 构造 ─────────────────────────
_BAD_VAL = re.compile(r"[&+=#%]")


def _clean_value(v):
    """值内结构性字符折叠，保证签名串与服务端重算一致（治腾讯 111）。"""
    s = str(v)
    s = _BAD_VAL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def tencent_signed_url(path, params, key, sk):
    p = {k: _clean_value(v) for k, v in dict(params).items()}
    p["key"] = key
    items = sorted(p.items())
    raw = "&".join(f"{k}={v}" for k, v in items)
    sig = hashlib.md5((path + "?" + raw + sk).encode("utf-8")).hexdigest()  # 小写
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)
    return TENCENT_HTTP_BASE + path + "?" + sent + "&sig=" + sig


def amap_signed_url(path, params, key, sk):
    p = dict(params)
    p["key"] = key
    items = sorted(p.items())
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)
    url = f"{AMAP_HTTP_BASE}{path}?{sent}"
    if sk:
        raw = "&".join(f"{k}={v}" for k, v in items)  # 中文原值入签名
        sig = hashlib.md5((raw + sk).encode("utf-8")).hexdigest()  # 小写
        url += "&sig=" + sig
    return url


# ───────────────────────── 统一调用（计数/池化/签名）─────────────────────────
def call(provider, path, params, interface, consumer, timeout=15, method="GET"):
    """经仲裁器发起一次地图调用。
    返回 (json_or_None, status: ok/rate/error/no_budget)。自动计数、轮换、dead 标记。"""
    import requests
    pool = MapQuota()
    cred = pool.acquire(consumer, provider, interface)
    if cred is None:
        # 可能是低优先让路；若整池确有剩余则属预留，否则真耗尽
        return None, ("no_budget" if pool._pool_remaining(provider, interface) <= 0 else "reserved")
    url = (tencent_signed_url if provider == "tencent" else amap_signed_url)(
        path, params, cred["key"], cred["sk"])
    try:
        r = requests.request(method, url, timeout=timeout)
        j = r.json()
    except Exception as e:
        print(f"[map_quota] {provider} 请求异常: {e}")
        pool.report(provider, cred["index"], interface, False)
        return None, "error"

    if provider == "tencent":
        code = j.get("status")
        ok = (code == 0)
        st = pool.report(provider, cred["index"], interface, ok, code=code)
        return j, st
    else:
        ok = (j.get("status") == "1")
        st = pool.report(provider, cred["index"], interface, ok, infocode=j.get("infocode"))
        return j, st


# ───────────────────────── 持久 POI 缓存 ─────────────────────────
class PoiCache:
    def __init__(self, path=POICACHE_PATH, max_entries=4000):
        self.path = path
        self.max_entries = max_entries
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[poi_cache] 保存失败: {e}")

    @staticmethod
    def make_key(name, address="", provider="", poi_id=""):
        if poi_id:
            return f"{provider}:{poi_id}"
        core = hashlib.md5(
            (re.sub(r"\s+", "", str(name)) + "|" + str(address)).encode("utf-8")).hexdigest()
        return f"x:{core}"

    def get(self, key, ttl_days=30):
        rec = self.data.get(key)
        if not rec:
            return None
        if time.time() - rec.get("ts", 0) > ttl_days * 86400:
            return None
        rec["last"] = time.time()
        return rec.get("payload")

    def put(self, key, payload):
        if len(self.data) >= self.max_entries:  # 简单 LRU：淘汰最久未用
            oldest = sorted(self.data.items(), key=lambda kv: kv[1].get("last", kv[1].get("ts", 0)))
            for k, _ in oldest[:max(1, self.max_entries // 20)]:
                self.data.pop(k, None)
        now = time.time()
        self.data[key] = {"ts": now, "last": now, "payload": payload}
        self._save()


if __name__ == "__main__":
    p = MapQuota()
    print(json.dumps(p.snapshot(), ensure_ascii=False, indent=1))

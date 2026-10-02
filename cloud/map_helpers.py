#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_helpers.py — 云端补齐脚本共享的地图API查询与结果匹配助手。

统一复用 tencent_sig.signed_get（腾讯SK签名），避免各脚本各写一份签名导致漂移。
提供：腾讯 suggestion/search/geocoder、高德 search/geocode、上海bbox校验、
店名+地址相似度匹配、地址补上海市前缀。

所有函数在API失败/配额超限时返回安全值，绝不抛异常中断主流程。
"""
import hashlib
import os
import re
import sys
import time
from difflib import SequenceMatcher
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
sys.path.insert(0, PIPE)
sys.path.insert(0, HERE)

import common as C
import map_quota as MQ
from tencent_sig import signed_get as tencent_signed_get

# ── 高德（独立签名，腾讯sig模块不覆盖） ──
AMAP_KEY = os.environ.get("AMAP_KEY", "").strip()
AMAP_SK = os.environ.get("AMAP_SK", "").strip()
AMAP_BASE = "https://restapi.amap.com"

# 上海包围盒（lng, lat）
SH_LNG_MIN, SH_LNG_MAX = 120.8, 122.2
SH_LAT_MIN, SH_LAT_MAX = 30.6, 31.9

# 不可编码的占位地址关键词
FAKE_ADDR_KEYWORDS = ("预约后告知", "待补", "详见点评", "电话咨询", "私信预约", "到店咨询")


# ────────────────────── 工具函数 ──────────────────────
def in_shanghai(lng, lat):
    """坐标是否在上海包围盒内。"""
    try:
        return SH_LNG_MIN <= float(lng) <= SH_LNG_MAX and SH_LAT_MIN <= float(lat) <= SH_LAT_MAX
    except (TypeError, ValueError):
        return False


def is_fake_address(addr):
    """地址是否为占位/非真实地址（无法编码）。"""
    if not addr:
        return True
    a = addr.strip()
    if len(a) < 5:
        return True
    return any(k in a for k in FAKE_ADDR_KEYWORDS)


def ensure_shanghai_prefix(address, district=""):
    """给地址补「上海市」+区划前缀，geocoder 必需。"""
    a = (address or "").strip()
    if not a:
        return ""
    if a.startswith("上海"):
        return a
    if district and not a.startswith(district):
        return f"上海市{district}{a}"
    return f"上海市{a}"


def cjk_sim(a, b):
    """CJK归一化后字符序列相似度 0~1。"""
    na = C.cjk_norm(a or "")
    nb = C.cjk_norm(b or "")
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


def addr_core_sim(a, b):
    """地址核心（路+号）相似度 0~1。"""
    ca = C.addr_core(a or "")
    cb = C.addr_core(b or "")
    if not ca or not cb:
        return 0.0
    if ca == cb:
        return 1.0
    if ca in cb or cb in ca:
        return 0.8
    return SequenceMatcher(None, ca, cb).ratio()


def area_tokens(addr):
    """从库内地址提取可区分分店的区域 token：路名 + 商场/地标名。"""
    a = (addr or "").strip()
    toks = set()
    for m in re.findall(r"[一-龥A-Za-z0-9]{1,8}?(?:路|街|大道|巷|弄)", a):
        if len(m) >= 2:
            toks.add(m)
    for kw in ("购物中心", "合生汇", "来福士", "大悦城", "印象城", "步行街",
               "百货", "商场", "大厦", "广场", "中心", "天地", "太古里",
               "太古汇", "万达", "银泰", "恒隆", "环贸", "公园", "市场"):
        i = a.find(kw)
        if i >= 0:
            toks.add(kw)                                   # 裸地标：足以区分不同商场
            for back in (2, 3, 4):                          # 地标 + 前 2/3/4 字
                t = a[max(0, i - back):i + len(kw)]
                if len(t) >= len(kw) + 1:
                    toks.add(t)
    return toks


def area_sim(db_address, cand):
    """库内区域 token 在候选标题/地址中的命中比例 0~1。"""
    toks = area_tokens(db_address)
    if not toks:
        return 0.0
    hay = f"{cand.get('title', '')} {cand.get('address', '')}"
    hit = sum(1 for t in toks if t in hay)
    return hit / len(toks)


def pick_best(results, db_name, db_address="", name_thresh=0.85):
    """从地图候选结果中选最匹配的。
    results: list of {title, address, tel, lng, lat, ...}
    返回 (best_dict, score) 或 (None, 0.0)。
    过滤：上海bbox + 店名相似度 >= name_thresh。
    打分：店名0.55 + 路号0.25 + 商场/区域token0.20。
    区域感知用于区分同品牌多分店（如合生汇店 vs 来福士店），保证只取正确分店，
    绝不因正确分店无电话而误用其他分店号码（电话宁空不假）。
    """
    if not results:
        return None, 0.0
    scored = []
    for r in results:
        lng, lat = r.get("lng"), r.get("lat")
        if lng is not None and lat is not None and not in_shanghai(lng, lat):
            continue  # 同名外地店直接排除
        ns = cjk_sim(db_name, r.get("title", ""))
        if ns < name_thresh:
            continue
        as_ = addr_core_sim(db_address, r.get("address", ""))
        ar_ = area_sim(db_address, r)
        score = ns * 0.55 + as_ * 0.25 + ar_ * 0.20
        scored.append((score, r, as_, ar_))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: -x[0])
    return scored[0][1], scored[0][0]


# ────────────────────── 统一配额调用（经 map_quota 池化/仲裁）──────────────────────
def _map_call(provider, path, params, interface, consumer, timeout=15):
    """逐把 key 尝试：某 key rate/error 自动换下一把；全 dead/无预算 → quota。
    返回 (json_or_None, "ok"/"quota"/"error")。"""
    pool = MQ.MapQuota()
    n = max(1, len(pool.keys[provider]))
    last = (None, "error")
    for _ in range(n):
        j, st = MQ.call(provider, path, params, interface, consumer, timeout=timeout)
        last = (j, st)
        if st == "ok":
            return j, "ok"
        if st in ("no_budget", "reserved"):
            return None, "quota"
        # rate / error / sign_error：换下一把 key 重试
    return (last[0], "quota" if last[1] == "rate" else "error")


# ────────────────────── 腾讯 API ──────────────────────
def tencent_suggestion(keyword, page_size=10):
    """腾讯 place/v1/suggestion —— 店名精确搜索，region_fix=1 限定上海。
    返回 list of {title, address, tel, lng, lat} 或 'QUOTA_EXCEEDED' 或 []。
    """
    j, st = _map_call("tencent", "/ws/place/v1/suggestion", {
        "keyword": keyword, "region": "上海", "region_fix": 1, "page_size": page_size,
    }, "search", "phone", timeout=15)
    if st == "quota":
        print("  [腾讯池配额超限]", file=sys.stderr)
        return "QUOTA_EXCEEDED"
    status = (j or {}).get("status")
    if st != "ok" or status != 0:
        print(f"  [腾讯suggestion st={st} status={status}] { (j or {}).get('message','') }",
              file=sys.stderr)
        return []
    out = []
    for item in j.get("data", []):
        loc = item.get("location", {})
        out.append({
            "title": item.get("title", ""),
            "address": item.get("address", ""),
            "tel": item.get("tel", "") or item.get("phone", ""),
            "lng": loc.get("lng"),
            "lat": loc.get("lat"),
        })
    return out


def tencent_search(keyword, page_size=10):
    """腾讯 place/v1/search —— 广义搜索，boundary=region(上海)。"""
    j, st = _map_call("tencent", "/ws/place/v1/search", {
        "keyword": keyword, "boundary": "region(上海)", "page_size": page_size,
    }, "search", "phone", timeout=15)
    if st == "quota":
        return "QUOTA_EXCEEDED"
    if st != "ok" or (j or {}).get("status") != 0:
        print(f"  [腾讯search st={st} status={(j or {}).get('status')}]", file=sys.stderr)
        return []
    out = []
    for item in j.get("data", []):
        loc = item.get("location", {})
        out.append({
            "title": item.get("title", ""),
            "address": item.get("address", ""),
            "tel": item.get("tel", "") or item.get("phone", ""),
            "lng": loc.get("lng"),
            "lat": loc.get("lat"),
        })
    return out


def tencent_geocode(address):
    """腾讯 geocoder/v1 —— address 必须已带上海市前缀。
    返回 (lng, lat) 或 None。
    """
    if not address:
        return None
    j, st = _map_call("tencent", "/ws/geocoder/v1/", {"address": address},
                      "geocode", "coord", timeout=15)
    if st != "ok" or (j or {}).get("status") != 0:
        print(f"  [腾讯geocoder st={st} status={(j or {}).get('status')}] addr={address[:40]}",
              file=sys.stderr)
        return None
    loc = j.get("result", {}).get("location", {})
    lng, lat = loc.get("lng"), loc.get("lat")
    if lng is None or lat is None:
        return None
    return float(lng), float(lat)


def tencent_place_detail(page_id):
    """腾讯 place/v1/detail —— 查POI详情（含营业时间business字段）。"""
    if not page_id:
        return {}
    j, st = _map_call("tencent", "/ws/place/v1/detail", {"page_id": page_id},
                      "search", "hours", timeout=15)
    if st == "ok" and (j or {}).get("status") == 0:
        return j.get("result", j.get("data", {}))
    return {}


# ────────────────────── 高德 API（多 key 池，配额耗尽自动轮换）──────────────────────
# 第二个开发者账号 = 第二份日配额。配置：
#   AMAP_KEYS=key1,key2   （多 key 逗号分隔；未配则回退单个 AMAP_KEY）
#   AMAP_SKS=sk1,sk2      （与 keys 一一对应；未配则所有 key 共用 AMAP_SK）
# 一个 key 撞 10003/10044（日配额）就在本进程内标记停用并切下一个；
# 全部 key 配额耗尽才返回 QUOTA_EXCEEDED。
def _load_keys():
    # 注意：保留每个位置（含空 SK），不能过滤空串，否则 key↔sk 会错位。
    keys = [k.strip() for k in os.environ.get("AMAP_KEYS", "").split(",")]
    keys = [k for k in keys if k]
    if not keys:
        keys = [k.strip() for k in [AMAP_KEY] if k.strip()]
    raw_sks = os.environ.get("AMAP_SKS", "")
    if raw_sks:
        sks = [s.strip() for s in raw_sks.split(",")]
    else:
        sks = [AMAP_SK] * len(keys)
    # 补齐 / 截断到与 keys 等长（缺位回退共用 AMAP_SK，通常为空=IP白名单）
    if len(sks) < len(keys):
        sks += [AMAP_SK] * (len(keys) - len(sks))
    sks = sks[:len(keys)]
    return list(zip(keys, sks))

_KEY_POOL = _load_keys()
AMAP_AVAILABLE = bool(_KEY_POOL)
_dead_keys = set()
_QUOTA_INFOCODES = {"10003", "10044"}


def _amap_get(path, params, interface="search", consumer="phone"):
    """经 map_quota 池请求高德（持久账本/轮换/仲裁）。返回 (json_or_None, ok/quota/error)。"""
    if not _KEY_POOL:
        return None, "error"
    return _map_call("amap", path, params, interface, consumer, timeout=15)


def amap_search(keywords, offset=10):
    """高德 place/text —— citylimit=true 限定上海。"""
    j, st = _amap_get("/v3/place/text", {
        "keywords": keywords, "city": "上海", "citylimit": "true",
        "offset": offset, "extensions": "all",
    })
    if st == "quota":
        return "QUOTA_EXCEEDED"
    if st != "ok":
        return []
    out = []
    for p in j.get("pois", []):
        loc_str = p.get("location", "")
        parts = loc_str.split(",") if loc_str else [None, None]
        biz_ext = p.get("biz_ext") or {}
        # 营业时间：优先opentime2（含星期范围），其次open_time
        business = biz_ext.get("opentime2") or biz_ext.get("open_time") or ""
        out.append({
            "id": p.get("id", ""),
            "title": p.get("name", ""),
            "address": p.get("address", ""),
            "tel": p.get("tel", ""),
            "business": business,
            "typecode": p.get("typecode", ""),
            "type": p.get("type", ""),
            "lng": float(parts[0]) if parts[0] else None,
            "lat": float(parts[1]) if len(parts) > 1 and parts[1] else None,
        })
    return out


def amap_geocode(address):
    """高德 geocode/geo —— address 应带城市前缀。返回 (lng,lat) 或 None。"""
    j, st = _amap_get("/v3/geocode/geo", {"address": address, "city": "上海"},
                      interface="geocode", consumer="coord")
    if st != "ok" or not j.get("geocodes"):
        return None
    loc = j["geocodes"][0].get("location", "")
    parts = loc.split(",")
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    return None


# ────────────────────── 统一查询入口 ──────────────────────
def resolve_poi(db_name, db_address="", db_district="", want_phone=False, want_coord=False):
    """统一POI解析：suggestion → search → 高德search → geocoder 逐级降级。
    命中持久 PoiCache 直接返回（电话/坐标/营业时间跨任务复用，省搜索调用）。
    返回 dict {found:bool,...} / {"quota_exceeded":True} / None。"""
    pc = MQ.PoiCache()
    cache_key = pc.make_key(db_name, db_address or db_district)
    cached = pc.get(cache_key, ttl_days=14)
    if cached:
        return cached

    def _chain():
        # 关键修复（跨源故障转移）：任一地图源配额耗尽都【不短路】，继续尝试下一源；
        # 仅当腾讯与高德全部配额耗尽且零命中时，才在末尾回报 quota_exceeded。
        quota_tencent = False
        quota_amap = False

        # ① 腾讯 suggestion（店名+地址地标，最精确）
        kw = db_name
        if db_address and not is_fake_address(db_address):
            kw = f"{db_name} {C.addr_core(db_address)}"
        res = tencent_suggestion(kw)
        if res == "QUOTA_EXCEEDED":
            quota_tencent = True          # 同一把腾讯 key，search/geocode 大概率也耗尽
        else:
            best, score = pick_best(res, db_name, db_address)
            if best:
                return {**best, "source": "tencent_suggestion", "score": score}

        # ② 腾讯 search（广义）；suggestion 已判配额耗尽则跳过，省一次调用
        if not quota_tencent:
            res = tencent_search(db_name)
            if res == "QUOTA_EXCEEDED":
                quota_tencent = True
            else:
                best, score = pick_best(res, db_name, db_address)
                if best:
                    return {**best, "source": "tencent_search", "score": score}

        # ③ 高德 search（腾讯配额耗尽/无结果时照常继续，绝不硬停）
        if AMAP_AVAILABLE:
            res = amap_search(db_name)
            if res == "QUOTA_EXCEEDED":
                quota_amap = True
            else:
                best, score = pick_best(res, db_name, db_address)
                if best:
                    return {**best, "source": "amap_search", "score": score}

        # ④ geocoder（仅当有真实地址时）；search 与 geocode 是不同接口、配额分开
        if want_coord and db_address and not is_fake_address(db_address):
            full_addr = ensure_shanghai_prefix(db_address, db_district)
            if not quota_tencent:
                coord = tencent_geocode(full_addr)
                if coord and in_shanghai(*coord):
                    return {"title": db_name, "address": full_addr, "tel": "",
                            "lng": coord[0], "lat": coord[1],
                            "source": "tencent_geocoder", "score": 0.5}
            if AMAP_AVAILABLE:
                coord = amap_geocode(full_addr)
                if coord and in_shanghai(*coord):
                    return {"title": db_name, "address": full_addr, "tel": "",
                            "lng": coord[0], "lat": coord[1],
                            "source": "amap_geocoder", "score": 0.5}

        # 仅当腾讯与（高德无 key 或高德也配额耗尽）时，才算整体配额耗尽
        if quota_tencent and (not AMAP_AVAILABLE or quota_amap):
            return {"quota_exceeded": True}
        return None

    out = _chain()
    if out and not out.get("quota_exceeded") and (
            out.get("title") or out.get("lat") is not None or out.get("tel")):
        out["found"] = True
        pc.put(cache_key, out)   # 只正缓存，quota/未找到不缓存
    return out

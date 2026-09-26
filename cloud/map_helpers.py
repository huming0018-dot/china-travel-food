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


def pick_best(results, db_name, db_address="", name_thresh=0.85):
    """从地图候选结果中选最匹配的。
    results: list of {title, address, tel, lng, lat, ...}
    返回 (best_dict, score) 或 (None, 0.0)。
    过滤：上海bbox + 店名相似度 >= name_thresh。
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
        score = ns * 0.6 + as_ * 0.4
        scored.append((score, r))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: -x[0])
    return scored[0][1], scored[0][0]


# ────────────────────── 腾讯 API ──────────────────────
def tencent_suggestion(keyword, page_size=10):
    """腾讯 place/v1/suggestion —— 店名精确搜索，region_fix=1 限定上海。
    返回 list of {title, address, tel, lng, lat} 或 'QUOTA_EXCEEDED' 或 []。
    """
    try:
        r = tencent_signed_get("/ws/place/v1/suggestion", {
            "keyword": keyword,
            "region": "上海",
            "region_fix": 1,
            "page_size": page_size,
        }, timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  [腾讯suggestion异常] {e}", file=sys.stderr)
        return []
    status = j.get("status")
    if status == 121:
        print("  [腾讯配额超限 status=121]", file=sys.stderr)
        return "QUOTA_EXCEEDED"
    if status == 348:
        print(f"  [腾讯suggestion status=348 参数错误] keyword={keyword[:30]}", file=sys.stderr)
        return []
    if status != 0:
        print(f"  [腾讯suggestion status={status}] {j.get('message','')}", file=sys.stderr)
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
    try:
        r = tencent_signed_get("/ws/place/v1/search", {
            "keyword": keyword,
            "boundary": "region(上海)",
            "page_size": page_size,
        }, timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  [腾讯search异常] {e}", file=sys.stderr)
        return []
    status = j.get("status")
    if status == 121:
        return "QUOTA_EXCEEDED"
    if status != 0:
        print(f"  [腾讯search status={status}] {j.get('message','')}", file=sys.stderr)
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
    try:
        r = tencent_signed_get("/ws/geocoder/v1/", {"address": address}, timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  [腾讯geocoder异常] {e}", file=sys.stderr)
        return None
    if j.get("status") != 0:
        print(f"  [腾讯geocoder status={j.get('status')}] {j.get('message','')} addr={address[:40]}", file=sys.stderr)
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
    try:
        r = tencent_signed_get("/ws/place/v1/detail", {"page_id": page_id}, timeout=15)
        j = r.json()
        if j.get("status") == 0:
            return j.get("result", j.get("data", {}))
    except Exception:
        pass
    return {}


# ────────────────────── 高德 API ──────────────────────
def _amap_signed_url(path, params):
    if not AMAP_KEY:
        return None
    p = dict(params)
    p["key"] = AMAP_KEY
    items = sorted(p.items())
    raw = "&".join(f"{k}={v}" for k, v in items)
    sig = hashlib.md5((raw + AMAP_SK).encode("utf-8")).hexdigest().upper()
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)
    return f"{AMAP_BASE}{path}?{sent}&sig={sig}"


def amap_search(keywords, offset=10):
    """高德 place/text —— citylimit=true 限定上海。"""
    url = _amap_signed_url("/v3/place/text", {
        "keywords": keywords, "city": "上海", "citylimit": "true",
        "offset": offset, "extensions": "all",
    })
    if not url:
        return []
    try:
        r = requests.get(url, timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  [高德search异常] {e}", file=sys.stderr)
        return []
    if j.get("status") != "1":
        if j.get("infocode") == "10003":
            return "QUOTA_EXCEEDED"
        return []
    out = []
    for p in j.get("pois", []):
        loc_str = p.get("location", "")
        parts = loc_str.split(",") if loc_str else [None, None]
        out.append({
            "title": p.get("name", ""),
            "address": p.get("address", ""),
            "tel": p.get("tel", ""),
            "lng": float(parts[0]) if parts[0] else None,
            "lat": float(parts[1]) if len(parts) > 1 and parts[1] else None,
        })
    return out


def amap_geocode(address):
    """高德 geocode/geo —— address 应带城市前缀。"""
    url = _amap_signed_url("/v3/geocode/geo", {"address": address, "city": "上海"})
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        j = r.json()
    except Exception:
        return None
    if j.get("status") != "1" or not j.get("geocodes"):
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
    """统一POI解析：suggestion → search → geocoder 逐级降级。
    返回 dict {found:bool, title, address, tel, lng, lat, source, score} 或 None。
    """
    # ① suggestion（店名+地址地标，最精确）
    kw = db_name
    if db_address and not is_fake_address(db_address):
        kw = f"{db_name} {C.addr_core(db_address)}"
    res = tencent_suggestion(kw)
    if res == "QUOTA_EXCEEDED":
        return {"quota_exceeded": True}
    best, score = pick_best(res, db_name, db_address)
    if best:
        return {**best, "source": "tencent_suggestion", "score": score}

    # ② search（广义）
    res = tencent_search(db_name)
    if res == "QUOTA_EXCEEDED":
        return {"quota_exceeded": True}
    best, score = pick_best(res, db_name, db_address)
    if best:
        return {**best, "source": "tencent_search", "score": score}

    # ③ 高德 search
    if AMAP_KEY:
        res = amap_search(db_name)
        if res == "QUOTA_EXCEEDED":
            return {"quota_exceeded": True}
        best, score = pick_best(res, db_name, db_address)
        if best:
            return {**best, "source": "amap_search", "score": score}

    # ④ geocoder（仅当有真实地址时）
    if want_coord and db_address and not is_fake_address(db_address):
        full_addr = ensure_shanghai_prefix(db_address, db_district)
        coord = tencent_geocode(full_addr)
        if coord and in_shanghai(*coord):
            return {"title": db_name, "address": full_addr, "tel": "",
                    "lng": coord[0], "lat": coord[1],
                    "source": "tencent_geocoder", "score": 0.5}
        if AMAP_KEY:
            coord = amap_geocode(full_addr)
            if coord and in_shanghai(*coord):
                return {"title": db_name, "address": full_addr, "tel": "",
                        "lng": coord[0], "lat": coord[1],
                        "source": "amap_geocoder", "score": 0.5}

    return None

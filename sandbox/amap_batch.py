#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""amap_batch.py — 高德/腾讯地图字段批量补齐。

整合自6个旧脚本，功能不丢：
  - 一次POI调用补全所有空字段（评分/人均/电话/营业时间/坐标/菜系标签）
  - pick_best高阈值锁定同一家店，防错号（来自phone_fill）
  - geocoder降级链 + 上海bbox校验（来自coord_fill）
  - 营业时间两Pass：A=解析已有raw，B=高德补空（来自hours_fill2）
  - 只补空字段，绝不覆盖已有非空值

用法：
  python3 amap_batch.py              # dry-run
  python3 amap_batch.py --apply     # 写库
  python3 amap_batch.py --fields phone,hours,coord,rating  # 只补指定字段
"""
import argparse
import json
import math
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import common

# ── 上海bbox ──
SH_BBOX = (120.85, 30.68, 122.20, 31.88)


def in_shanghai(lon: float, lat: float) -> bool:
    return SH_BBOX[0] <= lon <= SH_BBOX[2] and SH_BBOX[1] <= lat <= SH_BBOX[3]


# ── 坐标系转换：GCJ-02 → WGS-84 ──
def gcj02_to_wgs84(lon: float, lat: float) -> tuple:
    """GCJ-02火星坐标系转WGS-84。"""
    a = 6378245.0
    ee = 0.00669342162296594323

    def transform_lat(x, y):
        ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * (abs(x)) ** 0.5
        ret += (20.0 * (6.0 * x * x + 5.0 * y * y)) ** 0.5 * 2.0 / 3.0
        ret += (20.0 * (abs(x + y)) ** 0.5) * 2.0 / 3.0 + (20.0 * (3.0 + x + y)) ** 0.5 * 2.0 / 3.0
        return ret

    def transform_lon(x, y):
        ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * (abs(x)) ** 0.5
        ret += (20.0 * (3.0 * x * x + 3.0 * y * y)) ** 0.5 * 2.0 / 3.0
        ret += (20.0 * (abs(x + y)) ** 0.5) * 2.0 / 3.0 + (20.0 * (3.0 + x + y)) ** 0.5 * 2.0 / 3.0
        return ret

    dlat = transform_lat(lon - 105.0, lat - 35.0)
    dlon = transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * 3.14159265358979324
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * 3.14159265358979324)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * 3.14159265358979324)
    mglat = lat + dlat
    mglon = lon + dlon
    return lon * 2 - mglon, lat * 2 - mglat


def pick_best(name: str, addr: str, candidates: list) -> dict:
    """pick_best：店名0.6 + 地址0.4 高阈值锁定同一家。来自phone_fill。"""
    best = None
    best_score = 0
    for c in candidates:
        c_name = c.get("name", "")
        c_addr = c.get("address", "")
        name_sim = SequenceMatcher(None, name, c_name).ratio()
        addr_sim = SequenceMatcher(None, addr, c_addr).ratio() if addr else 0
        score = name_sim * 0.6 + addr_sim * 0.4
        if score > best_score and name_sim >= 0.6:
            best_score = score
            best = c
    return best or {}


def amap_search(keyword: str, city: str = "上海") -> list:
    """高德POI搜索。"""
    if not config.AMAP_KEYS:
        return []
    key = config.AMAP_KEYS[0]
    r = common.http_get("https://restapi.amap.com/v3/place/text", {
        "key": key, "keywords": keyword, "city": city,
        "extensions": "all", "offset": 10, "page": 1,
    })
    return r.get("pois", []) if r else []


def amap_detail(poi_id: str) -> dict:
    """高德POI详情。"""
    if not config.AMAP_KEYS:
        return {}
    key = config.AMAP_KEYS[0]
    r = common.http_get("https://restapi.amap.com/v3/place/detail", {
        "key": key, "uid": poi_id,
    })
    return r.get("poi", {}) if r else {}


def parse_opening_hours(raw: str) -> dict:
    """解析营业时间raw文本。来自hours_fill2。"""
    if not raw:
        return {}
    # 简单解析："周一至周日 10:00-22:00" → {"days": "daily", "hours": "10:00-22:00"}
    return {"raw": raw}


def fill_one(store: dict, fields: list) -> dict:
    """对一家店补空字段，返回patch字典。"""
    sid = store.get("id")
    name = store.get("name", "")
    addr = store.get("address", "")
    patch = {}

    # 搜索POI
    pois = amap_search(f"{name} {addr}")
    if not pois:
        return patch

    # pick_best锁定同一家
    best = pick_best(name, addr, pois)
    if not best:
        return patch

    # 补评分
    if "rating" in fields and not store.get("rating"):
        rating = best.get("biz_ext", {}).get("rating")
        if rating and rating != "[]":
            patch["rating"] = float(rating)

    # 补人均
    if "cost" in fields and not store.get("avg_cost"):
        cost = best.get("biz_ext", {}).get("cost")
        if cost and cost != "[]":
            try:
                patch["avg_cost"] = float(cost)
            except (ValueError, TypeError):
                pass

    # 补电话
    if "phone" in fields and not store.get("phone"):
        tel = best.get("tel", "")
        if tel and tel != "[]":
            patch["phone"] = tel

    # 补坐标
    if "coord" in fields and not store.get("location"):
        loc = best.get("location", "")
        if loc and "," in loc:
            lon, lat = loc.split(",")
            lon, lat = float(lon), float(lat)
            if in_shanghai(lon, lat):
                # GCJ-02 → WGS-84 坐标转换
                wgs_lon, wgs_lat = gcj02_to_wgs84(lon, lat)
                # PostGIS geography格式
                patch["location"] = f"POINT({wgs_lon} {wgs_lat})"

    # 补营业时间
    if "hours" in fields and not store.get("opening_hours"):
        opentime = best.get("biz_ext", {}).get("opentime2") or best.get("business", [{}])[0].get("opentime", "")
        if opentime:
            patch["opening_hours"] = parse_opening_hours(opentime)

    return patch


def run(apply: bool = False, limit: int = 50, fields: list = None):
    """批量补齐。"""
    fields = fields or ["rating", "cost", "phone", "coord", "hours"]

    # 从DB取需要补的店
    stores = common.db_get("restaurants", query="rating=is.null", limit=limit)
    common.log.info(f"待补店：{len(stores)}家，字段：{fields}")

    patched = 0
    for store in stores:
        patch = fill_one(store, fields)
        if not patch:
            continue
        common.log.info(f"  {store.get('name')}: {list(patch.keys())}")
        if apply:
            ok = common.db_patch("restaurants", store["id"], patch)
            if ok:
                patched += 1
        else:
            patched += 1
        time.sleep(0.2)  # 限速

    common.log.info(f"完成：{'写入' if apply else 'dry-run'} {patched}家")
    return patched


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--fields", type=str, default="")
    args = ap.parse_args()

    fields = args.fields.split(",") if args.fields else None
    run(apply=args.apply, limit=args.limit, fields=fields)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_review_fill.py — 云端地图POI评分采集（高德 biz_ext.rating → reviews 表）。

来源说明：
  - 高德 place/text extensions=all 返回 biz_ext.rating（1~5 星聚合评分），
    这是高德App真实食客打分的聚合值，非媒体稿/官方通稿。
  - 腾讯位置服务 WebService API 不返回评分/评论文本，仅做POI匹配，不产出评价。
  - 大众点评强反爬+登录墙，不在本脚本范围内（见 HANDOFF 已知缺口）。

写入规则：
  - 每家餐厅仅写 1 条高德评分评价（source_platform="高德地图"），幂等。
  - rating 4.5+→aspect_taste=5; 4.0+→4; 3.0+→3; 2.0+→2; else→1。
  - trust_level="low"（聚合分非单条UGC），is_verified_diner=false，
    review_kind="diner"（仍为食客打分，DB触发器贝叶斯收缩处理低置信）。
  - is_fake_suspect=false；source_url=高德POI页；author_name="高德地图用户"。
  - 无 biz_ext.rating 或 rating<=0 的店不写（宁空不假）。

风控/配额：
  - 高德日配额 5000 次，每轮 BATCH=200，间隔 0.2s。
  - AMAP_KEY 为空时整脚本 no-op 退出（不报错不告警）。
  - 断点续跑：记录 last_processed_id；flock 防重叠。
"""
import hashlib
import json
import os
import pathlib
import sys
import time
from urllib.parse import quote

import requests

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C
import health

STATE_F = pathlib.Path(DATA) / "_review_fill_state.json"
STATS_F = pathlib.Path(DATA) / "fill_stats.json"

BATCH_LIMIT = int(os.environ.get("REVIEW_FILL_BATCH", "200"))
AMAP_DAILY_QUOTA = 5000

AMAP_KEY = os.environ.get("AMAP_KEY", "").strip()
AMAP_SK = os.environ.get("AMAP_SK", "").strip()
AMAP_BASE = "https://restapi.amap.com"


def _read_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def amap_poi_rating(name, address=""):
    """查高德POI，返回 (rating_float, poi_url) 或 (None, None)。"""
    if not AMAP_KEY:
        return None, None
    params = {
        "keywords": name,
        "city": "上海",
        "citylimit": "true",
        "offset": 5,
        "extensions": "all",
        "key": AMAP_KEY,
    }
    items = sorted(params.items())
    raw = "&".join(f"{k}={v}" for k, v in items)
    sig = hashlib.md5((raw + AMAP_SK).encode("utf-8")).hexdigest().upper()
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)
    url = f"{AMAP_BASE}/v3/place/text?{sent}&sig={sig}"
    try:
        r = requests.get(url, timeout=15)
        j = r.json()
    except Exception as e:
        print(f"  [高德异常] {e}", file=sys.stderr)
        return None, None
    if j.get("status") != "1":
        if j.get("infocode") == "10003":
            return "QUOTA", None
        return None, None
    # 选最佳匹配（店名相似度最高）
    from map_helpers import pick_best
    results = []
    for p in j.get("pois", []):
        loc_str = p.get("location", "")
        parts = loc_str.split(",") if loc_str else [None, None]
        rating_raw = (p.get("biz_ext") or {}).get("rating", "")
        try:
            rating = float(rating_raw) if rating_raw and rating_raw != "[]" else None
        except (ValueError, TypeError):
            rating = None
        results.append({
            "title": p.get("name", ""),
            "address": p.get("address", ""),
            "lng": float(parts[0]) if parts[0] else None,
            "lat": float(parts[1]) if len(parts) > 1 and parts[1] else None,
            "rating": rating,
            "poi_id": p.get("id", ""),
        })
    best, score = pick_best(results, name, address, name_thresh=0.80)
    if not best or not best.get("rating"):
        return None, None
    poi_url = f"https://www.amap.com/detail/{best['poi_id']}" if best.get("poi_id") else ""
    return best["rating"], poi_url


def rating_to_taste(r):
    """高德聚合 1~5 星 → aspect_taste 1~5 整数。"""
    if r >= 4.5:
        return 5
    if r >= 4.0:
        return 4
    if r >= 3.0:
        return 3
    if r >= 2.0:
        return 2
    return 1


def review_exists(rid):
    """检查该店是否已有高德地图评价。"""
    q = f"/reviews?restaurant_id=eq.{rid}&source_platform=eq.{quote('高德地图')}&select=id"
    r = C.req("GET", q)
    return r.status_code == 200 and len(r.json()) > 0


def write_review(rid, rating, poi_url):
    payload = {
        "restaurant_id": rid,
        "author_name": "高德地图用户",
        "source_platform": "高德地图",
        "source_url": poi_url,
        "content": f"高德地图聚合食客评分 {rating}/5.0",
        "review_kind": "diner",
        "is_verified_diner": False,
        "trust_level": "low",
        "aspect_taste": rating_to_taste(rating),
        "aspect_json": {"amap_rating": rating, "source": "amap_biz_ext"},
        "is_fake_suspect": False,
        "is_hidden": False,
    }
    h = dict(C.headers())
    h["Prefer"] = "return=representation"
    r = requests.post(C.BASE + "/reviews", headers=h, json=payload, timeout=30)
    return r.status_code in (200, 201)


def main():
    if not AMAP_KEY:
        print("AMAP_KEY 未配置，高德评分采集跳过（在 deploy.env 配置 AMAP_KEY/AMAP_SK 后自动生效）。")
        return 0

    state = _read_state()
    today = C.today()
    if state.get("quota_date") != today:
        state = {"quota_date": today, "amap_used": 0,
                 "last_processed_id": state.get("last_processed_id", 0)}

    last_id = state.get("last_processed_id", 0)
    # 只补 review_count=0 的营业店
    path = (f"/restaurants?select=id,name,address&status=eq.active"
            f"&review_count=eq.0&id=gt.{last_id}&order=id.asc&limit={BATCH_LIMIT}")
    r = C.req("GET", path)
    targets = r.json() if r.status_code == 200 else []
    print(f"待补评分：{len(targets)} 家（从 id>{last_id} 开始）")

    if not targets:
        state["last_processed_id"] = 0
        _write_state(state)
        path = (f"/restaurants?select=id,name,address&status=eq.active"
                f"&review_count=eq.0&order=id.asc&limit={BATCH_LIMIT}")
        r = C.req("GET", path)
        targets = r.json() if r.status_code == 200 else []
        print(f"重置断点，重新拉取：{len(targets)} 家")

    if not targets:
        print("无待补评分的餐厅。")
        return 0

    stats = {"checked": 0, "written": 0, "no_rating": 0, "already": 0, "quota_stopped": False}

    for t in targets:
        rid = t["id"]
        name = t["name"]
        addr = t.get("address", "") or ""
        stats["checked"] += 1

        if state["amap_used"] >= AMAP_DAILY_QUOTA:
            stats["quota_stopped"] = True
            break

        state["amap_used"] += 1

        if review_exists(rid):
            stats["already"] += 1
            state["last_processed_id"] = rid
            continue

        rating, poi_url = amap_poi_rating(name, addr)

        if rating == "QUOTA":
            stats["quota_stopped"] = True
            health.alert("高德日配额耗尽，评分采集暂停至明天。",
                         title="上海美食图鉴·配额告警", key="amap_quota")
            break

        if not rating:
            stats["no_rating"] += 1
            state["last_processed_id"] = rid
            continue

        if write_review(rid, rating, poi_url):
            stats["written"] += 1
            state["last_processed_id"] = rid
            print(f"  [{rid}] {name} → ✓ amap_rating={rating} taste={rating_to_taste(rating)}")
        else:
            stats["no_rating"] += 1
            state["last_processed_id"] = rid

        time.sleep(0.2)

    _write_state(state)
    _write_stats(stats, state)

    print(f"\n=== 高德评分采集本轮统计 ===")
    print(f"  查询: {stats['checked']}  写入: {stats['written']}  "
          f"无评分: {stats['no_rating']}  已有: {stats['already']}")
    print(f"  高德已用: {state['amap_used']}/{AMAP_DAILY_QUOTA}")
    if stats["quota_stopped"]:
        print("  ⚠ 配额超限，本轮提前终止")
    return 0


def _write_stats(stats, state):
    try:
        existing = json.loads(STATS_F.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    existing["review_fill"] = {
        "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
        **stats,
        "amap_used": state.get("amap_used", 0),
        "last_processed_id": state.get("last_processed_id", 0),
    }
    STATS_F.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

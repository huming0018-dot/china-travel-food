#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_hours_fill.py — 云端营业时间补齐（修复版）。

修复要点：
  1. 复用 map_helpers（tencent_suggestion/search/detail + amap_search + pick_best），不再各写签名；
  2. suggestion 带 region=上海 region_fix=1 精确锁定分店；
  3. 候选过上海bbox + 店名/地址相似度，防错分店；
  4. evidence 提取优先，地图详情 business 字段兜底；只 PATCH opening_hours+open_days。
"""
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C
import health
from map_helpers import (
    tencent_suggestion, tencent_search, tencent_place_detail,
    amap_search, pick_best,
)
from opening_hours_collector import (
    parse_evidence_quotes, build_opening_hours, DAYS_CN,
)

STATS_F = pathlib.Path(DATA) / "fill_stats.json"
HOURS_BATCH = int(os.environ.get("HOURS_FILL_BATCH", "50"))


def fetch_hours_from_map(name, address=""):
    """逐级查营业时间：suggestion → search → amap，取匹配POI的business字段。
    返回 (oh_dict, open_days) 或 (None, None)。
    """
    # ① 腾讯 suggestion（最精确）
    kw = name
    if address:
        kw = f"{name} {C.addr_core(address)}"
    for search_fn in (
        lambda: tencent_suggestion(kw, page_size=5),
        lambda: tencent_search(name, page_size=5),
        lambda: amap_search(name, offset=5),
    ):
        res = search_fn()
        if res == "QUOTA_EXCEEDED" or not res:
            continue
        best, score = pick_best(res, name, address, name_thresh=0.85)
        if not best:
            continue
        # 腾讯结果可能有 page_id，查详情拿 business
        page_id = best.get("id") or best.get("page_id")
        business = best.get("business", "")
        if page_id and not business:
            detail = tencent_place_detail(page_id)
            business = detail.get("business", "") or business
        if business:
            return parse_hours_text(str(business))
    return None, None


def parse_hours_text(text):
    """从地图API business 文本解析 (oh_dict, open_days)。"""
    if not text:
        return None, None
    text = text.strip()
    if "全天" in text or "24小时" in text:
        return {d: "00:00-24:00" for d in DAYS_CN}, "周一至周日"
    oh, od, conf = build_opening_hours(text)
    if oh:
        return oh, od
    return None, None


def main():
    has_map = bool(os.environ.get("TENCENT_MAP_KEY", "").strip() or os.environ.get("AMAP_KEY", "").strip())

    path = ("/restaurants?select=id,name,address,score_total,evidence_summary,opening_hours,open_days"
            "&status=eq.active&opening_hours=is.null&order=score_total.desc.nullslast,id.asc"
            f"&limit={HOURS_BATCH}")
    r = C.req("GET", path)
    targets = r.json() if r.status_code == 200 else []
    print(f"待补营业时间：{len(targets)} 家（按score_total降序）")

    if not targets:
        _write_stats({"checked": 0, "evidence_filled": 0, "map_filled": 0, "skipped": 0})
        return 0

    stats = {"checked": 0, "evidence_filled": 0, "map_filled": 0, "skipped": 0}
    key_warned = False

    for t in targets:
        rid = t["id"]
        name = t["name"]
        stats["checked"] += 1

        # Step 1: evidence 提取
        ev_text = parse_evidence_quotes(t.get("evidence_summary"))
        oh, od, conf = build_opening_hours(ev_text)
        if oh and conf == "high":
            try:
                pr = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                           json={"opening_hours": oh, "open_days": od})
                if pr.status_code in (200, 204):
                    stats["evidence_filled"] += 1
                    print(f"  [{rid}] {name} → ✓ evidence: {od}")
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["skipped"] += 1
                print(f"  [{rid}] {name} → evidence写入异常: {e}")
            time.sleep(0.15)
            continue

        # Step 2: 地图API
        if not has_map:
            if not key_warned:
                health.alert("营业时间补齐：地图API未配置，evidence外的店无法补全。",
                             title="上海美食图鉴·营业时间补齐", key="hours_map_key_missing", once=True)
                key_warned = True
            stats["skipped"] += 1
            continue

        map_oh, map_od = fetch_hours_from_map(name, t.get("address", ""))
        if map_oh:
            try:
                pr = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                           json={"opening_hours": map_oh, "open_days": map_od})
                if pr.status_code in (200, 204):
                    stats["map_filled"] += 1
                    print(f"  [{rid}] {name} → ✓ 地图: {map_od}")
                else:
                    stats["skipped"] += 1
            except Exception as e:
                stats["skipped"] += 1
                print(f"  [{rid}] {name} → 地图写入异常: {e}")
        else:
            stats["skipped"] += 1
            print(f"  [{rid}] {name} → 无营业时间，宁空不假")

        time.sleep(0.3)

    _write_stats(stats)
    print(f"\n=== 营业时间补齐本轮统计 ===")
    print(f"  查询: {stats['checked']}  evidence成功: {stats['evidence_filled']}  "
          f"地图成功: {stats['map_filled']}  跳过: {stats['skipped']}")
    return 0


def _write_stats(stats):
    try:
        existing = json.loads(STATS_F.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    existing["hours"] = {"last_run": time.strftime("%Y-%m-%d %H:%M:%S"), **stats}
    STATS_F.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

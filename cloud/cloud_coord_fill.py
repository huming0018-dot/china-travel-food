#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_coord_fill.py — 云端坐标补齐（修复版）。

修复要点：
  1. 复用 map_helpers.resolve_poi（suggestion→search→geocoder 逐级降级），不再裸地址调geocoder；
  2. suggestion 必带 region=上海 region_fix=1，精确锁定分店；
  3. geocoder 备选时地址补「上海市」+区划前缀；
  4. 每个候选过上海bbox + 店名/地址相似度，防同名外地店与错分店；
  5. 占位地址（如「预约后告知」）跳过，列入待核实；
  6. 只 PATCH location 字段，绝不擅动其他列。
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
from map_helpers import resolve_poi, is_fake_address, in_shanghai

STATS_F = pathlib.Path(DATA) / "fill_stats.json"
PENDING_F = pathlib.Path(DATA) / "coord_pending_verification.json"


def main():
    has_tencent = bool(os.environ.get("TENCENT_MAP_KEY", "").strip())
    has_amap = bool(os.environ.get("AMAP_KEY", "").strip())
    if not has_tencent and not has_amap:
        msg = "坐标补齐脚本启动：地图API未配置，本轮跳过。"
        print(msg)
        health.alert(msg, title="上海美食图鉴·坐标补齐", key="coord_map_key_missing", once=True)
        return 0

    path = ("/restaurants?select=id,name,address,district,location&status=eq.active"
            "&location=is.null&order=id.asc")
    r = C.req("GET", path)
    targets = r.json() if r.status_code == 200 else []
    print(f"待补坐标：{len(targets)} 家")

    if not targets:
        _write_stats({"checked": 0, "filled": 0, "skipped": 0, "pending": 0})
        return 0

    stats = {"checked": 0, "filled": 0, "skipped": 0, "pending": 0}
    pending_list = []
    quota_hit = False

    for t in targets:
        rid = t["id"]
        name = t["name"]
        addr = t.get("address", "") or ""
        district = t.get("district", "") or ""
        stats["checked"] += 1

        if is_fake_address(addr):
            stats["pending"] += 1
            pending_list.append({"id": rid, "name": name, "address": addr,
                                 "reason": "占位/非真实地址，需先取真实店名/地址"})
            print(f"  [{rid}] {name} → ⚠ 占位地址，待核实: {addr[:30]}")
            continue

        poi = resolve_poi(name, db_address=addr, db_district=district, want_coord=True)

        if poi and poi.get("quota_exceeded"):
            quota_hit = True
            health.alert("腾讯/高德地图日配额耗尽，坐标补齐暂停至明天。",
                         title="上海美食图鉴·配额告警", key="coord_quota")
            break

        if not poi or poi.get("lng") is None:
            stats["skipped"] += 1
            print(f"  [{rid}] {name} → 无法解析坐标: {addr[:40]}")
            continue

        lng, lat = poi["lng"], poi["lat"]
        if not in_shanghai(lng, lat):
            stats["skipped"] += 1
            print(f"  [{rid}] {name} → 坐标({lng:.4f},{lat:.4f})超上海范围，拒绝")
            continue

        ewkt = C.point_ewkt(lng, lat)
        try:
            pr = C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"location": ewkt})
            if pr.status_code in (200, 204):
                stats["filled"] += 1
                print(f"  [{rid}] {name} → ✓ ({lng:.6f},{lat:.6f}) [{poi.get('source')}] score={poi.get('score',0):.2f}")
            else:
                stats["skipped"] += 1
                print(f"  [{rid}] {name} → PATCH失败 {pr.status_code}")
        except Exception as e:
            stats["skipped"] += 1
            print(f"  [{rid}] {name} → 写入异常: {e}")

        time.sleep(0.3)

    if pending_list:
        PENDING_F.write_text(json.dumps(pending_list, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_stats(stats)
    print(f"\n=== 坐标补齐本轮统计 ===")
    print(f"  查询: {stats['checked']}  成功: {stats['filled']}  跳过: {stats['skipped']}  待核实: {stats['pending']}")
    if quota_hit:
        print("  ⚠ 配额超限，本轮提前终止")
    return 0


def _write_stats(stats):
    try:
        existing = json.loads(STATS_F.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    existing["coord"] = {"last_run": time.strftime("%Y-%m-%d %H:%M:%S"), **stats}
    STATS_F.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

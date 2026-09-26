#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_phone_fill.py — 云端电话补齐（修复版）。

修复要点：
  1. 复用 map_helpers.resolve_poi（suggestion→search→geocoder），不再各写签名；
  2. suggestion 带 region=上海 region_fix=1，精确锁定分店防错号；
  3. 候选过上海bbox + 店名相似度≥0.85 + 地址相似度，绝不用同名他店/错分店号码；
  4. clean_phone 清洗，只 PATCH phone 字段；
  5. 断点续跑 + 配额管理（status=121/10003 自动停，次日续）+ flock 防重叠。
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
from map_helpers import resolve_poi, tencent_suggestion, tencent_search, amap_search, pick_best

STATE_F = pathlib.Path(DATA) / "_phone_fill_state.json"
STATS_F = pathlib.Path(DATA) / "fill_stats.json"

BATCH_LIMIT = int(os.environ.get("PHONE_FILL_BATCH", "100"))
TENCENT_DAILY_QUOTA = 10000
AMAP_DAILY_QUOTA = 5000


def _read_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def lookup_phone(name, address, state):
    """逐级查电话：suggestion → search → amap。返回 (tel_or_None, quota_hit_bool)。"""
    quota_hit = False

    # ① 腾讯 suggestion（最精确）
    if state["tencent_used"] < TENCENT_DAILY_QUOTA:
        kw = name
        if address:
            kw = f"{name} {C.addr_core(address)}"
        res = tencent_suggestion(kw)
        state["tencent_used"] += 1
        if res == "QUOTA_EXCEEDED":
            quota_hit = True
        else:
            best, score = pick_best(res, name, address, name_thresh=0.85)
            if best and best.get("tel"):
                return best["tel"], quota_hit

    # ② 腾讯 search
    if not quota_hit and state["tencent_used"] < TENCENT_DAILY_QUOTA:
        res = tencent_search(name)
        state["tencent_used"] += 1
        if res == "QUOTA_EXCEEDED":
            quota_hit = True
        else:
            best, score = pick_best(res, name, address, name_thresh=0.85)
            if best and best.get("tel"):
                return best["tel"], quota_hit

    # ③ 高德 search
    if not quota_hit and state["amap_used"] < AMAP_DAILY_QUOTA:
        res = amap_search(name)
        state["amap_used"] += 1
        if res == "QUOTA_EXCEEDED":
            quota_hit = True
        else:
            best, score = pick_best(res, name, address, name_thresh=0.85)
            if best and best.get("tel"):
                return best["tel"], quota_hit

    return None, quota_hit


def main():
    has_tencent = bool(os.environ.get("TENCENT_MAP_KEY", "").strip())
    has_amap = bool(os.environ.get("AMAP_KEY", "").strip())
    if not has_tencent and not has_amap:
        msg = "电话补齐脚本启动：地图API未配置，本轮跳过。"
        print(msg)
        health.alert(msg, title="上海美食图鉴·电话补齐", key="phone_map_key_missing", once=True)
        return 0

    state = _read_state()
    today = C.today()
    if state.get("quota_date") != today:
        state = {"quota_date": today, "tencent_used": 0, "amap_used": 0,
                 "last_processed_id": state.get("last_processed_id", 0)}

    last_id = state.get("last_processed_id", 0)
    path = (f"/restaurants?select=id,name,address,phone&status=eq.active"
            f"&phone=is.null&id=gt.{last_id}&order=id.asc&limit={BATCH_LIMIT}")
    r = C.req("GET", path)
    targets = r.json() if r.status_code == 200 else []
    print(f"待查电话：{len(targets)} 家（从 id>{last_id} 开始）")

    if not targets:
        state["last_processed_id"] = 0
        _write_state(state)
        path = (f"/restaurants?select=id,name,address,phone&status=eq.active"
                f"&phone=is.null&order=id.asc&limit={BATCH_LIMIT}")
        r = C.req("GET", path)
        targets = r.json() if r.status_code == 200 else []
        print(f"重置断点，重新拉取：{len(targets)} 家")

    if not targets:
        print("无待补电话的餐厅。")
        return 0

    stats = {"checked": 0, "filled": 0, "skipped": 0, "quota_stopped": False}
    quota_hit = False

    for t in targets:
        rid = t["id"]
        name = t["name"]
        addr = t.get("address", "") or ""
        stats["checked"] += 1

        raw_tel, quota_hit = lookup_phone(name, addr, state)

        if quota_hit:
            stats["quota_stopped"] = True
            health.alert("地图日配额耗尽，电话补齐暂停至明天。",
                         title="上海美食图鉴·配额告警", key="phone_quota")
            break

        if not raw_tel:
            stats["skipped"] += 1
            state["last_processed_id"] = rid
            print(f"  [{rid}] {name} → 无匹配电话，跳过")
            continue

        cleaned, issues, note = C.clean_phone(raw_tel)
        if not cleaned:
            stats["skipped"] += 1
            state["last_processed_id"] = rid
            print(f"  [{rid}] {name} → 号码不可用({issues})，宁空不假: raw={raw_tel[:40]}")
            continue

        try:
            pr = C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"phone": cleaned})
            if pr.status_code in (200, 204):
                stats["filled"] += 1
                state["last_processed_id"] = rid
                print(f"  [{rid}] {name} → ✓ phone={cleaned}")
            else:
                stats["skipped"] += 1
                print(f"  [{rid}] {name} → PATCH失败 {pr.status_code}")
        except Exception as e:
            stats["skipped"] += 1
            print(f"  [{rid}] {name} → 写入异常: {e}")

        time.sleep(0.3)

    _write_state(state)
    _write_stats("phone", stats, state)

    print(f"\n=== 电话补齐本轮统计 ===")
    print(f"  查询: {stats['checked']}  成功: {stats['filled']}  跳过: {stats['skipped']}")
    print(f"  腾讯已用: {state['tencent_used']}/{TENCENT_DAILY_QUOTA}  "
          f"高德已用: {state['amap_used']}/{AMAP_DAILY_QUOTA}")
    if stats["quota_stopped"]:
        print("  ⚠ 配额超限，本轮提前终止")
    return 0


def _write_stats(dim, stats, state):
    try:
        existing = json.loads(STATS_F.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    existing[dim] = {
        "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
        **stats,
        "tencent_used": state.get("tencent_used", 0),
        "amap_used": state.get("amap_used", 0),
        "last_processed_id": state.get("last_processed_id", 0),
    }
    STATS_F.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

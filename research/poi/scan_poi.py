#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POI 发现扫描器（只读、只产 raw/缓存/日志，不写库）。
- 通道：腾讯 location/v1/suggestion（place search 今日配额已耗尽，禁止使用）。
- 高德无 key（app/.env.local 未配置 AMAP_KEY），按规则不硬编码。
- 断点续跑：已缓存的 (keyword) 不再重复调用；POI 全量落 poi_candidates_cache.jsonl。
"""
import sys, os, json, time, re, pathlib, datetime

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path("/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline")
sys.path.insert(0, str(PIPE))
import tencent_sig as ts  # noqa
import common  # noqa

DB_PATH = HERE / "_db_restaurants.jsonl"
CACHE_PATH = HERE / "poi_candidates_cache.jsonl"
LOG_PATH = HERE / "poi_scan_log.json"
CACHE_KEYS_PATH = HERE / "_scanned_keywords.json"

TODAY = "2026-09-24"

# (keyword, cuisine_path, priority) —— cuisine_path 与 TAXONOMY_v3 叶子对齐
KEYWORDS = [
    # ---- 日料高缺叶子 ----
    ("omakase 寿司", ["亚洲菜", "日料", "Omakase板前"], "P0"),
    ("板前 omakase", ["亚洲菜", "日料", "Omakase板前"], "P0"),
    ("寿司 割烹", ["亚洲菜", "日料", "寿司"], "P0"),
    ("烧鸟 提灯", ["亚洲菜", "日料", "烧鸟"], "P0"),
    ("和牛 烧肉", ["亚洲菜", "日料", "烧肉"], "P0"),
    ("日式拉面 沾面", ["亚洲菜", "日料", "拉面"], "P0"),
    ("天妇罗 专门店", ["亚洲菜", "日料", "天妇罗"], "P0"),
    ("居酒屋 烧鸟", ["亚洲菜", "日料", "居酒屋"], "P1"),
    ("日式咖喱 猪排", ["亚洲菜", "日料", "日式咖喱"], "P1"),
    ("讚岐 乌冬", ["亚洲菜", "日料", "乌冬"], "P1"),
    ("荞麦面 涮涮锅", ["亚洲菜", "日料", "荞麦"], "P2"),
    ("怀石 会席", ["亚洲菜", "日料", "怀石"], "P1"),
    # ---- 西餐高缺 ----
    ("牛排馆 和牛", ["西餐", "牛排馆"], "P0"),
    ("意大利菜 手工意面", ["西餐", "意餐"], "P1"),
    ("法国菜 bistro", ["西餐", "法餐"], "P1"),
    ("西班牙菜 海鲜饭", ["西餐", "西班牙餐"], "P1"),
    ("德国菜 猪肘", ["西餐", "德国菜"], "P2"),
    ("俄餐 红菜汤", ["西餐", "俄餐"], "P2"),
    # ---- 中餐叶子 ----
    ("川菜 苍蝇馆子", ["中餐", "川菜"], "P1"),
    ("粤菜 烧腊 烧味", ["中餐", "粤菜"], "P1"),
    ("本帮菜 老上海", ["中餐", "本帮菜"], "P1"),
    ("淮扬菜 狮子头", ["中餐", "江浙菜"], "P2"),
    ("鲁菜 九转大肠", ["中餐", "鲁菜"], "P2"),
    ("闽菜 佛跳墙", ["中餐", "闽菜"], "P2"),
    ("湘菜 剁椒鱼头", ["中餐", "湘菜"], "P1"),
    ("徽菜 臭鳜鱼", ["中餐", "徽菜"], "P2"),
    ("东北菜 铁锅炖", ["中餐", "东北菜"], "P1"),
    ("西北菜 手抓羊肉", ["中餐", "西北菜"], "P1"),
    ("云南菜 菌子 汽锅鸡", ["中餐", "云南菜"], "P1"),
    ("贵州菜 酸汤鱼", ["中餐", "贵州菜"], "P2"),
    ("台湾菜 牛肉面", ["中餐", "台湾菜"], "P0"),
    ("潮汕菜 打冷 牛肉火锅", ["中餐", "潮汕菜"], "P0"),
    ("顺德菜 鱼生", ["中餐", "顺德菜"], "P1"),
    ("港式茶餐厅 菠萝油", ["中餐", "港式茶餐厅"], "P1"),
    # ---- 亚洲其他 ----
    ("泰餐 冬阴功 冬阴功汤", ["亚洲菜", "泰餐"], "P1"),
    ("越南菜 河粉 法包", ["亚洲菜", "越南菜"], "P2"),
    ("韩餐 烤肉 部队锅", ["亚洲菜", "韩餐"], "P1"),
    ("印度菜 咖喱 馕", ["亚洲菜", "印度菜"], "P2"),
    ("海南鸡饭 新加坡", ["亚洲菜", "新加坡菜"], "P2"),
    ("肉骨茶 马来西亚", ["亚洲菜", "马来西亚菜"], "P2"),
    # ---- 场景 ----
    ("精品咖啡 手冲", ["场景", "精品咖啡"], "P1"),
    ("甜品 烘焙 巴斯克", ["场景", "甜品烘焙"], "P1"),
    ("brunch 早午餐", ["场景", "Brunch"], "P1"),
    ("bistro 餐酒馆", ["场景", "Bistro餐酒"], "P0"),
    ("私宴 家厨 预约制", ["场景", "私宴会所"], "P1"),
    # ---- 回归点名店直查 ----
    ("Nagi 凪 拉面", ["亚洲菜", "日料", "拉面"], "REGRESSION"),
    ("鮨 天照", ["亚洲菜", "日料", "Omakase板前"], "REGRESSION"),
]

DIST_RE = re.compile(r"上海市(黄浦|徐汇|长宁|静安|普陀|虹口|杨浦|浦东新区|闵行|宝山|嘉定|金山|松江|青浦|奉贤|崇明)区")


def bucket_district(addr: str) -> str:
    if not addr:
        return "待确认"
    m = DIST_RE.search(addr)
    if m:
        return m.group(1) + "区"
    # 地址里可能省略"上海市"
    for d in ["黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "浦东新区", "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明"]:
        if d + "区" in addr:
            return d + "区"
    return "待确认"


def load_db():
    rows = common.read_jsonl(str(DB_PATH))
    norm = {}
    for r in rows:
        nm = common.norm_name(r.get("name") or "")
        norm.setdefault(nm, []).append(r)
    return rows, norm


def main():
    db_rows, db_norm = load_db()
    scanned = set()
    if CACHE_KEYS_PATH.exists():
        scanned = set(json.loads(CACHE_KEYS_PATH.read_text()))
    log = {"date": TODAY, "calls": {"suggestion": 0, "geocoder": 0, "amap": 0},
           "errors": [], "cells": {}, "quota_status": {}}
    if LOG_PATH.exists():
        try:
            old = json.loads(LOG_PATH.read_text())
            log["calls"] = old.get("calls", log["calls"])
            log["cells"] = old.get("cells", {})
            log["errors"] = old.get("errors", [])
        except Exception:
            pass

    cache_f = open(CACHE_PATH, "a", encoding="utf-8")
    new_pois = 0
    for kw, cpath, prio in KEYWORDS:
        if kw in scanned:
            continue
        try:
            r = ts.signed_get("/ws/place/v1/suggestion",
                              {"keyword": kw, "region": "上海", "region_fix": 1, "page_size": 20})
            j = r.json()
        except Exception as e:
            log["errors"].append({"kw": kw, "err": str(e)})
            time.sleep(1)
            continue
        log["calls"]["suggestion"] += 1
        st = j.get("status")
        if st != 0:
            log["quota_status"][kw] = {"status": st, "message": j.get("message")}
            # 配额耗尽即停
            if st in (121, 110, 112):
                log["errors"].append({"kw": kw, "fatal": f"quota status={st} {j.get('message')}"})
                break
            time.sleep(0.5)
            scanned.add(kw)
            continue
        pois = j.get("data", []) or []
        cell = {"platform": "tencent_suggestion", "call": 1, "returned": len(pois),
                "new_candidates": 0, "excluded_db": 0, "prio": prio, "cuisine_path": cpath}
        for p in pois:
            title = p.get("title") or ""
            addr = p.get("address") or ""
            loc = p.get("location") or {}
            lat, lng = loc.get("lat"), loc.get("lng")
            dist = bucket_district(addr)
            # DB 比对：归一名
            nm = common.norm_name(title)
            in_db = nm in db_norm
            # 分店括号内容归一后仍命中（如"X(南京西路店)" vs "X"）
            if not in_db:
                base = re.sub(r"[\(（].*?[\)）]", "", title)
                in_db = common.norm_name(base) in db_norm
            rec = {
                "keyword": kw, "cuisine_path": cpath, "prio": prio,
                "name": title, "address": addr, "lat": lat, "lng": lng,
                "category": p.get("category"), "district": dist,
                "tel": p.get("tel") or None,
                "in_db": in_db, "platform": "tencent_suggestion",
                "data_updated_at": TODAY,
            }
            cache_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            new_pois += 1
            if in_db:
                cell["excluded_db"] += 1
            else:
                cell["new_candidates"] += 1
        key = f"{kw}|{cpath[-1]}"
        log["cells"][key] = cell
        scanned.add(kw)
        time.sleep(0.35)  # 温和限速

    cache_f.close()
    CACHE_KEYS_PATH.write_text(json.dumps(sorted(scanned), ensure_ascii=False))
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    print(f"done. calls={log['calls']} pois_appended={new_pois} cells={len(log['cells'])} errors={len(log['errors'])}")


if __name__ == "__main__":
    main()

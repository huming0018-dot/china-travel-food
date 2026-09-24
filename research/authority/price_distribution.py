#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""price_distribution.py — 计算各"价格场景"下 active 店人均消费的真实分位数，
为建立客观、可复算、不含模糊语义的价格带制式提供事实依据。只做统计，不写库。"""
import sys, json, statistics
sys.path.insert(0, "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline")
import common as C

# 非正餐菜系根 cid
SCENE_ROOTS = {"咖啡": 300, "面包": 301, "甜品": 302, "酒吧": 303, "茶饮": 324}
FAST_FORM = {74, 75, 80, 84}          # 快餐/简餐、大排档、外卖外带、美食广场
BAR_FORM, TEA_FORM = 81, 82

rests = C.fetch_all("restaurants", "id,name,price_avg,status", order_col="id")
rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
cu = C.fetch_all("cuisines", "id,name,parent_category,dimension", order_col="id")

by_id = {x["id"]: x for x in cu}
name_to_ids = {}
for x in cu:
    name_to_ids.setdefault(x["name"], []).append(x["id"])

def ancestors(cid):
    """返回该标签向上的祖先 cid 集合（含自身）。parent_category 存父名。"""
    out, cur, seen = set(), cid, set()
    while cur and cur not in seen:
        seen.add(cur); out.add(cur)
        rec = by_id.get(cur)
        if not rec or not rec.get("parent_category"):
            break
        pids = name_to_ids.get(rec["parent_category"], [])
        cur = pids[0] if pids else None
    return out

# 店 -> 挂的 cid 集合
shop_tags = {}
for r in rc:
    shop_tags.setdefault(r["restaurant_id"], set()).add(r["cuisine_id"])

def scene_of(rid):
    tags = shop_tags.get(rid, set())
    # 收集所有祖先
    anc = set()
    for t in tags:
        anc |= ancestors(t)
    # 非正餐菜系场景（按价格分布特殊性给优先级）
    if (SCENE_ROOTS["酒吧"] in anc) or (BAR_FORM in anc):
        return "酒吧"
    for name in ("咖啡", "面包", "甜品", "茶饮"):
        if SCENE_ROOTS[name] in anc or (name == "茶饮" and TEA_FORM in anc):
            return name
    # 快餐小吃（形式标签）
    if tags & FAST_FORM:
        return "快餐小吃"
    return "正餐"

groups = {}
skipped = 0
for r in rests:
    if r["status"] != "active":
        continue
    p = C.to_int(r["price_avg"])
    if p is None or p <= 0:
        skipped += 1
        continue
    groups.setdefault(scene_of(r["id"]), []).append(p)

def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return round(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))

report = {}
for sc, vals in groups.items():
    sv = sorted(vals)
    report[sc] = {
        "n": len(sv),
        "min": sv[0], "max": sv[-1],
        "P10": pct(sv, .10), "P25": pct(sv, .25), "P40": pct(sv, .40),
        "P50": pct(sv, .50), "P60": pct(sv, .60), "P75": pct(sv, .75),
        "P90": pct(sv, .90), "P95": pct(sv, .95),
    }
print("active 且有人均的店：", sum(len(v) for v in groups.values()), "；缺人均跳过：", skipped)
print(json.dumps(report, ensure_ascii=False, indent=2))

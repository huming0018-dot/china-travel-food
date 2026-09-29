#!/usr/bin/env python3
# -*- coding: utf-8">
"""price_band_assign.py — 客观"场景价格带"回填（migration 009 制式）。

只依据客观变量、确定性计算：
  price_scene：由店挂的标签（非正餐菜系根 / 快餐形式）判定；
  price_band ：由 price_scene + price_avg 对照 price_band_thresholds 固定边界得到（1-5）。
不含任何主观/品质语义；替代旧 stage7_price_position 的"旗舰/进阶/高端/入门/主流"。

用法：
  python3 price_band_assign.py            # dry-run，落 price_band_plan.json
  python3 price_band_assign.py --commit   # PATCH price_scene/price_band
"""
import argparse, collections, json
import common as C

SCENE_ROOTS = {"面包": 301, "甜品": 302}
COFFEE_ROOTS = (300, 324)          # 咖啡、茶饮 → 合并"咖啡茶饮"
BAR_ROOT, BAR_FORM, TEA_FORM = 303, 81, 82
FAST_FORM = {74, 75, 80, 84}       # 快餐/简餐、大排档、外卖外带、美食广场

rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
cu = C.fetch_all("cuisines", "id,name,parent_category,dimension", order_col="id")
by_id = {x["id"]: x for x in cu}
name_to_ids = {}
for x in cu:
    name_to_ids.setdefault(x["name"], []).append(x["id"])

def ancestors(cid):
    out, cur, seen = set(), cid, set()
    while cur and cur not in seen:
        seen.add(cur); out.add(cur)
        rec = by_id.get(cur)
        if not rec or not rec.get("parent_category"):
            break
        pids = name_to_ids.get(rec["parent_category"], [])
        cur = pids[0] if pids else None
    return out

shop_tags = {}
for r in rc:
    shop_tags.setdefault(r["restaurant_id"], set()).add(r["cuisine_id"])

def scene_of(rid):
    tags = shop_tags.get(rid, set())
    anc = set()
    for t in tags:
        anc |= ancestors(t)
    if (BAR_ROOT in anc) or (BAR_FORM in anc):
        return "酒吧"
    if any(r in anc for r in COFFEE_ROOTS) or (TEA_FORM in anc):
        return "咖啡茶饮"
    if SCENE_ROOTS["面包"] in anc:
        return "面包"
    if SCENE_ROOTS["甜品"] in anc:
        return "甜品"
    if tags & FAST_FORM:
        return "快餐小吃"
    return "正餐"

def load_thresholds():
    th = C.fetch_all("price_band_thresholds", "scene,band,lo,hi", order_col="band")
    out = collections.defaultdict(list)
    for t in th:
        out[t["scene"]].append((t["band"], t["lo"], t["hi"]))
    return out

def band_of(thresholds, scene, price):
    for band, lo, hi in thresholds.get(scene, []):
        if (lo is None or price >= lo) and (hi is None or price < hi):
            return band
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    thresholds = load_thresholds()
    rests = C.fetch_all("restaurants", "id,name,price_avg,price_scene,price_band,status", order_col="id")
    plan, dist = [], collections.Counter()
    no_price = 0
    for r in rests:
        if r["status"] != "active":
            continue
        p = C.to_int(r["price_avg"])
        if p is None or p <= 0:
            no_price += 1
            continue
        scene = scene_of(r["id"])
        band = band_of(thresholds, scene, p)
        dist[(scene, band)] += 1
        patch = {}
        if r.get("price_scene") != scene:
            patch["price_scene"] = scene
        if r.get("price_band") != band:
            patch["price_band"] = band
        if patch:
            plan.append({"id": r["id"], "name": r["name"], "price": p, "patch": patch})

    print(f"待更新 {len(plan)} 家；缺人均 {no_price} 家")
    print("各场景价格带分布：")
    for scene in ("正餐", "快餐小吃", "咖啡茶饮", "面包", "甜品", "酒吧"):
        row = {b: dist[(scene, b)] for b in range(1, 6)}
        print(f"  {scene}: {row}")

    with open("price_band_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    if not args.commit:
        print("[dry-run] 确认后加 --commit")
        return
    n, fail = 0, 0
    for p in plan:
        r = C.req("PATCH", f"/restaurants?id=eq.{p['id']}", json=p["patch"])
        if r.status_code == 204:
            n += 1
        else:
            fail += 1
            print("  失败:", p["id"], r.status_code, r.text[:140])
    print(f"commit 完成 {n}/{len(plan)}，失败 {fail}")

if __name__ == "__main__":
    main()

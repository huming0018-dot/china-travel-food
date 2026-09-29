#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage7_price_position.py — 计算「品类内相对档」price_position（v2）

口径（修复跨菜系档次矛盾）：
  绝对档 tier 按人均绝对值（"花多少钱"，阈值经全库分布验证为自然断点）；
  price_position 按该店所属「定价组」内部人均分位（"在本品类里算什么档"）。

定价组分组规则（v2，关键修复）：
  1. 非正餐归一：店挂的菜系叶子沿 parent 上溯，若落在 咖啡/面包/甜品/Bar/茶饮
     这五个非正餐二级之一，定价组 = 该二级（不与正餐混排）。
  2. 正餐取「最深子流派叶子」，但排除 SINGLE_DISH（冬阴功、可颂甜品这类单品/做法词，
     它们不是定价组），避免同菜系被碎片叶子拆成不可比小组。
  3. 定价组在营有均价样本 < MIN_GROUP 时沿 parent 上溯（非正餐组不上溯）。
  4. 组内按 price_avg 排序，PERCENT_RANK 映射：
       <0.2 入门 / <0.4 主流 / <0.6 进阶 / <0.8 高端 / >=0.8 旗舰。

用法：
  python3 stage7_price_position.py            # dry-run
  python3 stage7_price_position.py --commit   # PATCH
"""
import sys, time, argparse, collections
sys.path.insert(0, "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline")
from collections import defaultdict
import common as C

VIRTUAL_ROOTS = {"中餐", "亚洲", "欧洲", "非洲", "北美洲", "南美洲", "融合菜", "非正餐",
                 "亚洲菜", "西餐", "其他"}
NON_MEAL_SECOND = {"咖啡", "面包", "甜品", "Bar", "茶饮"}
SINGLE_DISH = {"冬阴功", "可颂甜品"}
MIN_GROUP = 6


def load_tree():
    cs = C.fetch_all("cuisines", "id,name,dimension,parent_category")
    return {c["name"]: c for c in cs}


def depth_of(name, by_name):
    d, cur, seen = 0, name, set()
    while cur in by_name and cur not in seen:
        seen.add(cur)
        p = by_name[cur]["parent_category"]
        d += 1
        if p in VIRTUAL_ROOTS: break
        cur = p
    return d


def parent_of(name, by_name):
    c = by_name.get(name)
    return c["parent_category"] if c else None


def non_meal_root(cname, by_name):
    cur, seen = cname, set()
    while cur in by_name and cur not in seen:
        seen.add(cur)
        if cur in NON_MEAL_SECOND: return cur
        p = by_name[cur]["parent_category"]
        if p in VIRTUAL_ROOTS: break
        cur = p
    return None


def position_for_rank(rank):
    if rank < 0.2: return "入门"
    if rank < 0.4: return "主流"
    if rank < 0.6: return "进阶"
    if rank < 0.8: return "高端"
    return "旗舰"


def compute():
    by_name = load_tree()
    rests = C.fetch_all("restaurants", "id,name,price_avg,status")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    cid2name = {c["id"]: c["name"] for c in by_name.values()}

    tags = defaultdict(list)
    for x in rc:
        cname = cid2name.get(x["cuisine_id"])
        c = by_name.get(cname)
        if c and c["dimension"] == "菜系":
            tags[x["restaurant_id"]].append(cname)

    # 初始定价组
    init = {}
    for rid, t in tags.items():
        nms = [non_meal_root(x, by_name) for x in t]
        nms = [x for x in nms if x]
        if nms:
            init[rid] = collections.Counter(nms).most_common(1)[0][0]
            continue
        cand = [x for x in t if x not in SINGLE_DISH] or t
        init[rid] = sorted(cand, key=lambda z: depth_of(z, by_name), reverse=True)[0]

    active = [r for r in rests if r["status"] == "active" and r["price_avg"] is not None]

    def raw_count(g):
        return sum(1 for r in active if init.get(r["id"]) == g)

    final = {}
    for r in active:
        g = init.get(r["id"])
        if g in NON_MEAL_SECOND:
            final[r["id"]] = g
            continue
        guard = 0
        while g and g not in VIRTUAL_ROOTS and raw_count(g) < MIN_GROUP and guard < 6:
            p = parent_of(g, by_name)
            if not p or p in VIRTUAL_ROOTS: break
            g = p; guard += 1
        final[r["id"]] = g

    groups = defaultdict(list)
    for r in active: groups[final[r["id"]]].append(r)

    labels = {}
    for g, items in groups.items():
        items = sorted(items, key=lambda z: z["price_avg"])
        n = len(items)
        for i, r in enumerate(items):
            rank = i / (n - 1) if n > 1 else 0.5
            labels[r["id"]] = position_for_rank(rank)
    return labels, groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    labels, groups = compute()
    dist = defaultdict(int)
    for v in labels.values(): dist[v] += 1
    print("price_position 分布:", dict(dist), "在算:", len(labels))
    print("\n分组数:", len(groups))
    for g in sorted(groups, key=lambda z: -len(groups[z]))[:30]:
        prices = sorted(r["price_avg"] for r in groups[g])
        print("  %-16s n=%-3d 价格带 %d~%d" % (g, len(prices), prices[0], prices[-1]))

    if not args.commit:
        print("\n[dry-run] 加 --commit 写库")
        return
    n = 0
    for rid, pos in labels.items():
        r = C.req("PATCH", "/restaurants?id=eq.%d" % rid, json={"price_position": pos})
        r.raise_for_status()
        n += 1
        if n % 200 == 0: print("  已写", n); time.sleep(0.2)
    print("commit 完成，共", n, "家")


if __name__ == "__main__":
    main()

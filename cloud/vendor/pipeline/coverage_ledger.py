#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_ledger.py — 上海美食图鉴「四维本体覆盖账本」。

为什么存在：菜系本体(cuisines)已很全，但叶子节点到底挂了多少在营店、多少有真实食客
背书，没有量化，导致"日料深、其他菜系浅"只能凭感觉。本模块对每个节点计算：
  n_active   挂载的在营餐厅数（连锁分店各算一家）
  n_real     这些餐厅中拥有真实食客评价(trust mid/high，或小红书UGC)的餐厅数
  n_verified 其中 evidence=verified（≥2 独立真实食客）的餐厅数
并据叶子规模给出饱和状态：empty / shallow / thin / ok / rich。
非叶子(父)节点状态由子树聚合，避免重复计数。

用法：
  python3 coverage_ledger.py                 # 打印缺口总览
  python3 coverage_ledger.py --save /app/data/coverage/ledger.json
  python3 coverage_ledger.py --gaps          # 只列 empty/shallow 叶子（喂给发现引擎）
"""
import argparse
import json
import pathlib
import collections

import common as C

# 叶子饱和阈值（在营店数）。外国小众菜系天然少，阈值只用于排序，不做硬删。
SAT = [(0, "empty"), (1, "shallow"), (4, "thin"), (8, "ok"), (16, "rich")]

# ---- 宇宙分母：预期供给 expected_supply → 应入选 target_n（配额口径，见 mechanism-master P1）----
# target_n = 该叶子在「供给充足/一般/稀缺」下应达到的 verified 好店数。
TARGET_OF = {"scarce": 2, "normal": 3, "rich": 5}
# 数据驱动：地图 POI（在营候选）计数 → 供给档；阈值可调。
POI_SUPPLY = [(12, "scarce"), (40, "normal"), (10 ** 9, "rich")]
# 无 POI 数据时按根路径/名字的启发式（中文大众品类=rich；境外小众=scarce）。
RICH_HEUR = ["火锅", "烧烤", "烤肉", "面馆", "拉面", "咖啡", "面包", "烘焙", "奶茶", "茶饮",
             "本帮", "快餐", "饺子", "包子", "粥", "烧腊", "点心", "早茶", "串串", "麻辣烫"]
SCARCE_HEUR = ["非洲", "中东", "阿拉伯", "俄罗斯", "墨西哥", "秘鲁", "巴西", "阿根廷", "素食",
               "分子", "先锋", "私房", "会所", "飞行", "快闪"]
# 虚拟大陆根（用于判断境外 vs 中餐）
FOREIGN_ROOTS = {"亚洲", "欧洲", "非洲", "北美洲", "南美洲"}


def supply_from_poi(n_poi):
    for thr, name in POI_SUPPLY:
        if n_poi < thr:
            return name
    return "rich"


def supply_heuristic(name, root_names):
    """无 POI 计数时的兜底：命中大众品类词=rich；命中境外/小众=scarce；
    境外大陆下的国家叶子默认 scarce，中餐叶子默认 normal。"""
    t = str(name)
    if any(k in t for k in RICH_HEUR):
        return "rich"
    if any(k in t for k in SCARCE_HEUR):
        return "scarce"
    if any(r in root_names for r in FOREIGN_ROOTS):
        return "scarce"
    return "normal"


def sat_of(n):
    s = "empty"
    for thr, name in SAT:
        if n >= thr:
            s = name
    return s


def is_real_review(r):
    """真实食客 UGC：显式 trust mid/high，否则来源为小红书。"""
    t = (r.get("trust") or "").lower()
    if t in ("mid", "high"):
        return True
    src = " ".join(str(r.get(k, "")) for k in
                   ("source", "source_url", "url", "author_type")).lower()
    return "xiaohongshu" in src or "xhslink" in src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default="")
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--poi-counts", default="",
                    help="JSON：leaf_id -> 地图在营 POI 数（数据驱动分母，deep_discovery 产出）")
    ap.add_argument("--override", default="",
                    help="JSON：leaf_id -> scarce/normal/rich（人工校准，最高优先级）")
    args = ap.parse_args()

    poi_counts = {}
    if args.poi_counts and pathlib.Path(args.poi_counts).exists():
        poi_counts = {int(k): v for k, v in
                      json.loads(pathlib.Path(args.poi_counts).read_text("utf-8")).items()}
    overrides = {}
    if args.override and pathlib.Path(args.override).exists():
        overrides = {int(k): v for k, v in
                     json.loads(pathlib.Path(args.override).read_text("utf-8")).items()}

    cuisines = C.fetch_all("cuisines", order_col="id")
    by_id = {x["id"]: x for x in cuisines}
    children = collections.defaultdict(list)
    # 父链可能是 int 或数字字符串/名字；账本按"直接挂载"统计，同时建 int 父->子
    for x in cuisines:
        p = x.get("parent_category")
        if isinstance(p, int) and p in by_id:
            children[p].append(x["id"])
        elif isinstance(p, str) and p.isdigit() and int(p) in by_id:
            children[int(p)].append(x["id"])

    # child -> 直接父 id；用于回溯祖先（含虚拟根名字）。
    parent_of = {}
    for pid, chs in children.items():
        for ch in chs:
            parent_of[ch] = pid

    def ancestor_names(cid):
        out, cur, guard = [], cid, 0
        while True:
            raw = by_id.get(cur, {}).get("parent_category")
            if isinstance(raw, int) and raw in by_id:
                out.append(by_id[raw].get("name", "")); cur = raw
            elif isinstance(raw, str) and raw.isdigit() and int(raw) in by_id:
                out.append(by_id[int(raw)].get("name", "")); cur = int(raw)
            elif isinstance(raw, str) and raw:
                out.append(raw); break  # 虚拟根名字
            else:
                break
            guard += 1
            if guard > 20:
                break
        return out

    rests = C.fetch_all("restaurants", select="id,status", order_col="id")
    active = {r["id"] for r in rests if r.get("status") == "active"}

    rc = C.fetch_all("restaurant_cuisines", order_col="restaurant_id")
    cid_rids = collections.defaultdict(set)
    for x in rc:
        if x["restaurant_id"] in active:
            cid_rids[x["cuisine_id"]].add(x["restaurant_id"])

    # 真实食客 / verified
    revs = C.fetch_all("reviews", order_col="id")
    rid_real = collections.Counter()
    for r in revs:
        if is_real_review(r):
            rid_real[r["restaurant_id"]] += 1
    # verified 集合：优先从 taste 视图/表读 evidence；没有则按 ≥2 条真实评价近似
    ev = {}
    try:
        evrows = C.fetch_all("trg_reviews_taste", order_col="restaurant_id")
        ev = {x["restaurant_id"]: x for x in evrows}
    except Exception:
        ev = {}

    def real_count(rids):
        return sum(1 for r in rids if rid_real.get(r, 0) >= 1)

    def verified_count(rids):
        n = 0
        for r in rids:
            e = ev.get(r)
            if e and str(e.get("evidence", "")).lower() == "verified":
                n += 1
            elif rid_real.get(r, 0) >= 2:
                n += 1
        return n

    leaves = {x["id"] for x in cuisines if not children.get(x["id"])}

    def supply_for(cid, name):
        """返回 (expected_supply, target_n, supply_source)。
        优先级：人工 override > 地图 POI 计数 > 根路径启发式。"""
        if cid in overrides:
            sup = overrides[cid]; src = "override"
        elif cid in poi_counts:
            sup = supply_from_poi(int(poi_counts[cid])); src = "poi"
        else:
            sup = supply_heuristic(name, ancestor_names(cid)); src = "heuristic"
        return sup, TARGET_OF[sup], src

    ledger = {}
    for x in cuisines:
        cid = x["id"]
        if cid in leaves:
            rids = cid_rids.get(cid, set())
            n = len(rids)
            n_ver = verified_count(rids)
            sup, target, src = supply_for(cid, x["name"])
            ledger[cid] = {
                "id": cid, "name": x["name"], "leaf": True,
                "parent": x.get("parent_category"),
                "n_active": n, "n_real": real_count(rids),
                "n_verified": n_ver,
                "status": sat_of(n),
                "expected_supply": sup, "target_n": target,
                "gap_n": max(0, target - n_ver), "met": n_ver >= target,
                "supply_source": src,
            }

    # 父节点：子树聚合（递归收集叶子 rids 去重）
    def subtree_rids(cid, seen=None):
        out = set()
        for ch in children.get(cid, []):
            if ch in leaves:
                out |= cid_rids.get(ch, set())
            else:
                out |= subtree_rids(ch)
        return out

    for x in cuisines:
        cid = x["id"]
        if cid not in leaves:
            rids = cid_rids.get(cid, set()) | subtree_rids(cid)
            ledger[cid] = {
                "id": cid, "name": x["name"], "leaf": False,
                "parent": x.get("parent_category"),
                "n_active": len(rids), "n_real": real_count(rids),
                "n_verified": verified_count(rids),
                "status": "parent",
            }

    # 报告：缺口 = 未达 target_n 的叶子（met=False）；empty/shallow 作为最优先子集。
    leaf_rows = [ledger[c] for c in leaves]
    unmet = [r for r in leaf_rows if not r["met"]]
    gaps = [r for r in leaf_rows if r["status"] in ("empty", "shallow")]
    # 排序：empty→shallow→其余；同档按 gap_n 大、id 小优先。
    rank = {"empty": 0, "shallow": 1}
    unmet.sort(key=lambda r: (rank.get(r["status"], 2), -r["gap_n"], r["id"]))
    gaps.sort(key=lambda r: (r["status"] != "empty", r["id"]))

    if args.gaps:
        for r in unmet:
            print(f"  [{r['status']:<7}] {r['id']:>3} {r['name']:<14} "
                  f"ver {r['n_verified']}/{r['target_n']} gap {r['gap_n']} ({r['supply_source']})")
        print(f"\n未达标叶子 {len(unmet)}/{len(leaf_rows)}；empty+shallow {len(gaps)}；"
              f"总缺口 verified 好店 {sum(r['gap_n'] for r in unmet)}")
    else:
        dist = collections.Counter(r["status"] for r in leaf_rows)
        met_n = sum(1 for r in leaf_rows if r["met"])
        src_dist = collections.Counter(r["supply_source"] for r in leaf_rows)
        sup_dist = collections.Counter(r["expected_supply"] for r in leaf_rows)
        print(f"叶子节点 {len(leaf_rows)}：{dict(dist)}")
        print(f"达标(verified≥target) {met_n}/{len(leaf_rows)} = {met_n/len(leaf_rows):.0%}；"
              f"未达标 {len(unmet)}；总缺口 {sum(r['gap_n'] for r in unmet)}")
        print(f"供给档分布 {dict(sup_dist)}；分母来源 {dict(src_dist)}")
        print(f"全库真实食客覆盖餐厅 "
              f"{sum(1 for r in active if rid_real.get(r,0)>=1)}/{len(active)}")
        print("\n== empty 叶子（优先发现）==")
        for r in gaps:
            if r["status"] == "empty":
                print(f"  {r['id']:>3} {r['name']}（target {r['target_n']}）")

    if args.save:
        p = pathlib.Path(args.save)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(list(ledger.values()), ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"\nsaved -> {args.save}")


if __name__ == "__main__":
    main()

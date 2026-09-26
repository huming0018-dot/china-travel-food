#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage6_coverage.py — 「子品类 × 档位」网格覆盖审计（只读质量门 / 深采施工图）

为什么需要它：
  stage1~5 只保证「单条记录合格、写库正确」，无法发现结构性缺口——
  日料按 烹饪形式×档位 做到每格 3~10 家，而其他菜系要么只拆少数地域子流派、每格堆砌
  （粗），要么拆了叶子但每格只有 1~2 家种子（浅）。本脚本把「覆盖深度」变成可量化、
  可回归的质量门，并直接产出需要深采的格子任务清单（coverage_tasks.json）。

用法：
  python3 stage6_coverage.py                      # 打印 Markdown 报告
  python3 stage6_coverage.py -o coverage.md -j coverage_tasks.json
  python3 stage6_coverage.py --strict             # 未达深度标准时退出码 1（用于 CI 闸门）

深度标准（可按城市真实供给在下方常量调整，宁缺毋滥）：
  LEAF_MIN   每个叶子（细分品类/子流派）精选店下限；1~2 家=薄格，0 家=空格
  LEAF_GOOD  供给充足叶子的目标值
  EVID_MIN   evidence_summary 最少字数（薄证据=批量快采痕迹，川菜曾仅 ~117 字）
"""
import argparse
import collections
import json
import statistics
import sys

import common as C

ROOTS_ORDER = ["中餐", "亚洲菜", "西餐", "其他"]
LEAF_MIN = 3
LEAF_GOOD = 5
EVID_MIN = 200
SCENE_ROOTS = {"咖啡/甜品专门店", "酒吧/小酒馆", "融合菜/Fusion", "墨西哥/拉美菜", "非洲菜"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", help="Markdown 报告落盘路径")
    ap.add_argument("-j", "--json-out", dest="json_out", help="深采任务清单 JSON")
    ap.add_argument("--strict", action="store_true", help="不达标退出码 1")
    args = ap.parse_args()

    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    rests = C.fetch_all(
        "restaurants",
        "id,status,tier,phone,evidence_summary,score_objective,score_diner,score_taste,score_endorsement",
        order_col="id",
    )
    active = {r["id"]: r for r in rests if r.get("status") != C.STATUS_CLOSED}

    byid = {c["id"]: c for c in cuis}
    children = collections.defaultdict(list)
    for c in cuis:
        if c["dimension"] == "菜系":
            children[c.get("parent_category")].append(c)

    cnt = collections.Counter(x["cuisine_id"] for x in rc if x["restaurant_id"] in active)

    def descendants(root_name):
        seen, stack = set(), [root_name]
        while stack:
            n = stack.pop()
            for ch in children.get(n, []):
                if ch["id"] not in seen:
                    seen.add(ch["id"])
                    stack.append(ch["name"])
        return seen

    def shops_of(tag_ids, root_name):
        s = set()
        for x in rc:
            if x["restaurant_id"] not in active:
                continue
            cid = x["cuisine_id"]
            if cid in tag_ids or byid.get(cid, {}).get("name") == root_name:
                s.add(x["restaurant_id"])
        return s

    roots = []
    for vr in ROOTS_ORDER:
        for c in children.get(vr, []):
            if c["dimension"] == "菜系":
                roots.append(c["name"])

    summary, tasks = [], []
    md = ["# 网格覆盖审计（子品类 × 档位）", "",
          f"口径：active 店 {len(active)} 家；叶子精选下限 {LEAF_MIN}（薄格 1~2 / 空格 0）；"
          f"证据下限 {EVID_MIN} 字。", ""]

    for root in roots:
        desc = descendants(root)
        leaf_ids = [cid for cid in desc
                    if not [c for c in children.get(byid[cid]["name"], []) if c["dimension"] == "菜系"]]
        if not leaf_ids:  # 场景类根自身即叶子
            rself = [c["id"] for c in cuis if c["name"] == root and c["dimension"] == "菜系"]
            leaf_ids = rself
        shops = shops_of(desc, root)
        leaf_rows = []
        for cid in leaf_ids:
            name = byid[cid]["name"]
            tier_cnt = collections.Counter()
            for x in rc:
                if x["cuisine_id"] == cid and x["restaurant_id"] in active:
                    tier_cnt[active[x["restaurant_id"]].get("tier")] += 1
            n = sum(tier_cnt.values())
            state = "空" if n == 0 else "薄" if n < LEAF_MIN else "达标" if n < LEAF_GOOD else "充足"
            leaf_rows.append((name, n, state, tier_cnt))
            if state in ("空", "薄"):
                tasks.append({
                    "菜系根": root, "叶子": name, "现状店数": n, "状态": state,
                    "档位分布": {t: tier_cnt.get(t, 0) for t in C.TIERS},
                    "动作": ("新建候选池深采" if state == "空" else "补采至下限"),
                })
        # 单店质量
        evlen, thin_ev, phone, score_full = [], 0, 0, 0
        for rid in shops:
            r = active[rid]
            e = len(r.get("evidence_summary") or "")
            evlen.append(e)
            if 0 < e < EVID_MIN:
                thin_ev += 1
            if r.get("phone"):
                phone += 1
            if all(r.get(k) is not None for k in
                   ("score_objective", "score_diner", "score_taste", "score_endorsement")):
                score_full += 1
        nshop = len(shops)
        leaf_n = [r[1] for r in leaf_rows]
        empty = sum(1 for r in leaf_rows if r[2] == "空")
        thin = sum(1 for r in leaf_rows if r[2] == "薄")
        summary.append({
            "root": root, "shops": nshop, "leaves": len(leaf_rows),
            "empty": empty, "thin": thin,
            "leaf_median": statistics.median(leaf_n) if leaf_n else 0,
            "evid_median": int(statistics.median(evlen)) if evlen else 0,
            "thin_evidence_shops": thin_ev,
            "phone_rate": round(phone / nshop, 2) if nshop else 0,
        })
        if thin_ev >= max(3, int(nshop * 0.25)):
            tasks.append({"菜系根": root, "叶子": "(全菜系)", "现状店数": nshop,
                          "状态": "证据薄", "动作": f"{thin_ev} 家证据<{EVID_MIN}字，补食客点评原文",
                          "档位分布": {}})

    md += ["## 一、菜系深度总览", "",
           "| 菜系 | 店数 | 叶子数 | 空格 | 薄格(1-2) | 叶挂店中位 | 证据字中位 | 薄证据店 | 电话率 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        md.append(f"| {s['root']} | {s['shops']} | {s['leaves']} | {s['empty']} | {s['thin']} | "
                  f"{s['leaf_median']} | {s['evid_median']} | {s['thin_evidence_shops']} | {s['phone_rate']:.0%} |")

    md += ["", "## 二、各菜系 叶子 × 档位 矩阵", ""]
    for root in roots:
        desc = descendants(root)
        leaf_ids = [cid for cid in desc
                    if not [c for c in children.get(byid[cid]["name"], []) if c["dimension"] == "菜系"]]
        if not leaf_ids:
            leaf_ids = [c["id"] for c in cuis if c["name"] == root and c["dimension"] == "菜系"]
        md.append(f"### {root}")
        md.append("| 叶子 | 总 | 经济 | 平价 | 中档 | 高档 | 奢华 | 状态 |")
        md.append("|---|---|---|---|---|---|---|---|")
        for cid in sorted(leaf_ids, key=lambda i: -cnt[i]):
            tc = collections.Counter()
            for x in rc:
                if x["cuisine_id"] == cid and x["restaurant_id"] in active:
                    tc[active[x["restaurant_id"]].get("tier")] += 1
            n = sum(tc.values())
            state = "空" if n == 0 else "薄" if n < LEAF_MIN else "达标" if n < LEAF_GOOD else "充足"
            md.append(f"| {byid[cid]['name']} | {n} | " +
                      " | ".join(str(tc.get(t, 0)) for t in C.TIERS) + f" | {state} |")
        md.append("")

    md += [f"## 三、深采任务清单（{len(tasks)} 项）", "",
           "按此清单逐格补采：每格走「候选≥2×下限 → 反软广评分 → ≥2条含菜名点评 → 多渠道交叉 → 管线入库」。", ""]
    for t in tasks:
        md.append(f"- **{t['菜系根']} / {t['叶子']}**（{t['状态']}，现 {t['现状店数']}）：{t['动作']}")

    report = "\n".join(md)
    print(report)
    if args.output:
        import pathlib
        pathlib.Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n报告已写入 {args.output}", file=sys.stderr)
    if args.json_out:
        import pathlib
        pathlib.Path(args.json_out).write_text(
            json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"任务清单已写入 {args.json_out}（{len(tasks)} 项）", file=sys.stderr)

    n_empty = sum(s["empty"] for s in summary)
    n_thin = sum(s["thin"] for s in summary)
    print(f"\n汇总：空格 {n_empty} / 薄格 {n_thin} / 深采任务 {len(tasks)}", file=sys.stderr)
    if args.strict and (n_empty or n_thin):
        sys.exit(1)


if __name__ == "__main__":
    main()

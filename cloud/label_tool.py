#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud/label_tool.py — 极简种子标注工具（模块A·收录机制，与消费前端分开）。

用户只需填一列「评级」(必吃/值得/一般)；口味分(1-5,越高越好)、最近到店年份(如2025)、备注 均可选。
口径：必吃=口味确实好；值得=没太多雷点；一般=能吃但难给美食家留下深刻印象。
没有精确到店日期时，年份填最近一次到访的大概年份即可；记不清可留空。

用法（容器内）：
  python3 /app/cloud/label_tool.py init      # 生成工作表 /app/data/labels/labels_worksheet.csv
  python3 /app/cloud/label_tool.py submit    # 校验 dry-run
  python3 /app/cloud/label_tool.py submit --apply   # 校验并 upsert 入库 diner_seed_labels
"""
import os
import re
import sys
import csv
import argparse

sys.path.insert(0, "/app/pipeline")
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
OUT_CSV = os.path.join(OUT_DIR, "labels", "labels_worksheet.csv")
HEAD = ["restaurant_id", "店名", "商圈", "菜系", "评级",
        "口味分(1-5,越高越好)", "最近到店年份", "备注"]

TIER_MAP = {
    "must_eat": "must_eat", "必吃": "must_eat", "不可不吃": "must_eat",
    "一定要吃": "must_eat", "必食": "must_eat",
    "worth_eating": "worth_eating", "值得": "worth_eating",
    "值得一吃": "worth_eating", "可吃": "worth_eating", "值得去": "worth_eating",
    "average": "average", "一般": "average", "普通": "average",
}


def cmd_init(args):
    rs = C.fetch_all("restaurants", "id,name,status,business_area", order_col="id")
    rows = [r for r in rs if r.get("status") == "active"]
    # 菜系（信息列，自动填）：rid -> 菜系名（最多 2 个）
    cu = {c["id"]: c["name"] for c in C.fetch_all("cuisines", "id,name", order_col="id")}
    rid2cu = {}
    for x in C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                         order_col="restaurant_id"):
        nm = cu.get(x["cuisine_id"])
        if nm:
            rid2cu.setdefault(x["restaurant_id"], [])
            if nm not in rid2cu[x["restaurant_id"]] and len(rid2cu[x["restaurant_id"]]) < 2:
                rid2cu[x["restaurant_id"]].append(nm)
    rows.sort(key=lambda r: ((r.get("business_area") or "~"), r["name"]))  # 按商圈聚集，便于就近标注
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        for r in rows:
            w.writerow([r["id"], r["name"], r.get("business_area", ""),
                        "/".join(rid2cu.get(r["id"], [])), "", "", "", ""])
    print(f"[init] 待标注 {len(rows)} 店 -> {OUT_CSV}（菜系自动填，你只需填『评级』列）")


def parse_rows():
    valid, errs = [], []
    with open(OUT_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        k_taste = next((c for c in cols if "口味" in c), "口味分")
        k_year = next((c for c in cols if "年份" in c), "最近到店年份")
        for i, row in enumerate(reader, start=2):
            rid = (row.get("restaurant_id") or "").strip()
            tier = (row.get("评级") or "").strip()
            if not rid and not tier:
                continue
            if not rid:
                errs.append((i, "", "缺 restaurant_id")); continue
            if not tier:
                continue  # 未评级 = 未标注，跳过
            try:
                rid_i = int(rid)
            except ValueError:
                errs.append((i, rid, "restaurant_id 非整数")); continue
            t = TIER_MAP.get(tier) or TIER_MAP.get(tier.lower())
            if not t:
                errs.append((i, rid, f"评级须填 必吃/值得，当前『{tier}』")); continue
            taste = None
            ts = (row.get(k_taste) or "").strip()
            if ts:
                try:
                    taste = int(float(ts))
                    if not 1 <= taste <= 5:
                        raise ValueError
                except ValueError:
                    errs.append((i, rid, f"口味分须为 1-5，当前『{ts}』")); continue
            year = None
            ys = (row.get(k_year) or "").strip()
            if ys:
                m = re.search(r"(20\d{2})", ys)
                if not m:
                    errs.append((i, rid, f"年份须如 2025，当前『{ys}』")); continue
                year = int(m.group(1))
            note = (row.get("备注") or "").strip() or None
            valid.append({"restaurant_id": rid_i, "labeler": "expert", "tier": t,
                          "taste": taste, "visit_year": year, "evidence": note})
    return valid, errs


def cmd_submit(args):
    if not os.path.exists(OUT_CSV):
        print("[submit] 找不到 CSV，先跑 init"); return
    valid, errs = parse_rows()
    print(f"[submit] 合格 {len(valid)} 行，错误 {len(errs)} 行")
    for e in errs[:20]:
        print("  ERR line", e)
    if not args.apply:
        print("[submit] dry-run（加 --apply 才真写）"); return
    existing = {x["restaurant_id"]: x["id"] for x in C.fetch_all(
        "diner_seed_labels", "id,restaurant_id", order_col="id",
        extra="labeler=eq.expert")}
    n = 0
    for v in valid:
        rid = v.pop("restaurant_id")
        if rid in existing:
            r = C.req("PATCH", f"/diner_seed_labels?id=eq.{existing[rid]}", json=v)
        else:
            r = C.req("POST", "/diner_seed_labels", json=v)
        n += 1 if r.status_code in (200, 201, 204) else 0
    total = len(C.fetch_all("diner_seed_labels", "id", order_col="id"))
    print(f"[submit --apply] upsert {n}/{len(valid)}；写后回读共 {total} 行")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("init"); a.set_defaults(f=cmd_init)
    b = sub.add_parser("submit"); b.add_argument("--apply", action="store_true")
    b.set_defaults(f=cmd_submit)
    args = ap.parse_args()
    if not getattr(args, "f", None):
        ap.print_help(); sys.exit(1)
    args.f(args)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud/label_tool.py — 最小内部四维两层标注工具（与消费前端分开）。

用法（用户）：
  1) 导出待标注工作表：
       python3 cloud/label_tool.py init
     -> /app/data/labels/labels_worksheet.csv（id,name,菜系,商圈,人均,四维,tier,evidence,evidence_url,experienced_at,notes）
  2) 用户用 Excel/表格软件打开 CSV，填 taste/ambience/innovation/consistency(1-5)、
     tier(must_eat|worth_eating)、evidence(堂食菜名)、experienced_at(YYYY-MM-DD) 等列。
  3) 校验+入库（先 dry-run 看错误行，再加 --apply）：
       python3 cloud/label_tool.py submit
       python3 cloud/label_tool.py submit --apply

认识论：标注是 ground truth，写 diner_expert_labels（018）；不碰 score_* 触发器口径。
"""
import os, sys, csv, argparse, datetime

sys.path.insert(0, "/app/pipeline")
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
OUT_CSV = os.path.join(OUT_DIR, "labels", "labels_worksheet.csv")
COLS = ["restaurant_id", "name", "cuisine", "area", "price_avg",
        "labeler", "taste", "ambience", "innovation", "consistency",
        "tier", "evidence", "evidence_url", "experienced_at", "notes"]


def cmd_init(args):
    rs = C.fetch_all("restaurants",
                     "id,name,status,price_avg,business_area", order_col="id")
    done = set()
    try:
        for r in C.fetch_all("diner_expert_labels", "restaurant_id", order_col="restaurant_id"):
            done.add(r["restaurant_id"])
    except Exception:
        pass  # 表未建则全量导出
    rows = [r for r in rs if r.get("status") == "active" and r["id"] not in done]
    # 菜系：取主挂标签名（可选，失败留空）
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in rows:
            w.writerow([r["id"], r["name"], "", r.get("business_area", ""),
                        r.get("price_avg", ""), args.labeler, "", "", "", "",
                        "", "", "", "", ""])
    print(f"[init] 待标注 {len(rows)} 店 -> {OUT_CSV}")


def cmd_submit(args):
    if not os.path.exists(OUT_CSV):
        print("[submit] 找不到 CSV，先跑 init"); return
    ids = {r["id"] for r in C.fetch_all("restaurants", "id", order_col="id")}
    valid, errs = [], []
    with open(OUT_CSV, encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            rid = row.get("restaurant_id", "").strip()
            if not rid:
                continue
            if not row.get("taste"):  # 空行=未标注，跳过
                continue
            try:
                rid_i = int(rid)
            except ValueError:
                errs.append((i, rid, "restaurant_id 非整数")); continue
            if rid_i not in ids:
                errs.append((i, rid, "店 id 不在库")); continue
            try:
                s = {k: float(row[k]) for k in ("taste", "ambience", "innovation", "consistency")}
            except ValueError:
                errs.append((i, rid, "四维须为 1-5 数字")); continue
            if any(not (1 <= v <= 5) for v in s.values()):
                errs.append((i, rid, "四维须在 1-5")); continue
            if row["tier"] not in ("must_eat", "worth_eating"):
                errs.append((i, rid, "tier 须 must_eat/worth_eating")); continue
            if not row.get("experienced_at"):
                errs.append((i, rid, "缺 experienced_at(YYYY-MM-DD)")); continue
            valid.append({"restaurant_id": rid_i, "labeler": row["labeler"] or "expert",
                          **s, "tier": row["tier"], "evidence": row.get("evidence") or None,
                          "evidence_url": row.get("evidence_url") or None,
                          "experienced_at": row["experienced_at"], "notes": row.get("notes") or None})
    print(f"[submit] 合格 {len(valid)} 行，错误 {len(errs)} 行")
    for e in errs[:20]:
        print("  ERR line", e)
    if args.apply and valid:
        n = 0
        for v in valid:
            r = C.req("POST", "/diner_expert_labels", json=v,
                      headers={"Prefer": "return=minimal"})
            n += 1 if r.status_code in (200, 201) else 0
        print(f"[submit --apply] POST {n}/{len(valid)}，写后回读："
              f"{len(C.fetch_all('diner_expert_labels','id',order_col='id'))} 行")
    elif not args.apply:
        print("[submit] dry-run（加 --apply 才真写）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("init"); a.add_argument("--labeler", default="expert"); a.set_defaults(f=cmd_init)
    b = sub.add_parser("submit"); b.add_argument("--apply", action="store_true"); b.set_defaults(f=cmd_submit)
    args = ap.parse_args()
    args.f(args)

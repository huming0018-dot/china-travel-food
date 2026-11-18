#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opening_hours_collector.py — 从 evidence_summary 提取营业时间，写入 opening_hours(jsonb) + open_days(text)

原则：宁空不假。只提取有明确时间模式的文本；提取不到不臆造。
- opening_hours: {"周一":"11:00-22:00", "周二":"11:00-22:00", ...}
- open_days: "周一至周日" / "周二休" / "仅周末" 等

用法：
  python3 opening_hours_collector.py                # dry-run
  python3 opening_hours_collector.py --commit       # 写库
  python3 opening_hours_collector.py --commit --high-priority  # 只处理 score>75 / 米其林 / 有评价
"""
import argparse
import collections
import json
import re
import sys
import time
from collections import defaultdict

import common as C

# Compatibility exports for existing users of this batch entry point.
from opening_hours_parser import (
    DAYS_CN, DAYS_SHORT, parse_evidence_quotes, extract_time_ranges,
    extract_closed_day, extract_day_range, build_opening_hours,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--high-priority", action="store_true",
                    help="只处理 score_total>75 / 米其林黑珍珠 / review_count>0")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("拉取餐厅...", file=sys.stderr)
    rests = C.fetch_all("restaurants", order_col="id")
    awards = C.fetch_all("restaurant_awards",
                         "restaurant_id,award_type,is_current",
                         order_col="restaurant_id")
    award_rids = {a["restaurant_id"] for a in awards if a.get("is_current", True)}

    # 筛选目标
    targets = []
    for r in rests:
        if r.get("opening_hours"):
            continue
        if args.high_priority:
            score = r.get("score_total") or 0
            if score <= 75 and r["id"] not in award_rids and (r.get("review_count") or 0) == 0:
                continue
        targets.append(r)

    if args.limit:
        targets = targets[:args.limit]

    print(f"待处理: {len(targets)} 家", file=sys.stderr)

    results = []
    conf_counter = collections.Counter()
    for r in targets:
        text = parse_evidence_quotes(r.get("evidence_summary"))
        oh, od, conf = build_opening_hours(text)
        results.append({
            "id": r["id"],
            "name": r["name"],
            "opening_hours": oh,
            "open_days": od,
            "_confidence": conf,
            "_score": r.get("score_total") or 0,
        })
        conf_counter[conf] += 1

    # 打印样本
    print(f"\n=== 提取成功样本（前20条 high confidence）===")
    shown = 0
    for x in results:
        if x["_confidence"] == "high" and shown < 20:
            print(f"  [id={x['id']}] {x['name']}")
            print(f"    open_days: {x['open_days']}")
            print(f"    opening_hours: {json.dumps(x['opening_hours'], ensure_ascii=False)}")
            shown += 1
            print()

    print(f"\n=== 置信度分布 ===")
    for k, v in conf_counter.most_common():
        print(f"  {k}: {v}")

    high_n = conf_counter.get("high", 0)
    print(f"\n高置信提取率: {high_n}/{len(results)} = {high_n/max(len(results),1):.0%}")

    if not args.commit:
        print("\n[DRY-RUN] 加 --commit 写库", file=sys.stderr)
        return

    # 备份
    import pathlib
    backup_dir = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/backups")
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"opening_hours_backup_{C.today()}.jsonl"
    old = {r["id"]: {"opening_hours": r.get("opening_hours"),
                      "open_days": r.get("open_days")} for r in rests}
    C.write_jsonl(str(backup_file), [{"id": k, **v} for k, v in old.items()])
    print(f"备份: {backup_file}", file=sys.stderr)

    # 只写 high confidence 的
    to_write = [x for x in results if x["_confidence"] == "high" and x["opening_hours"]]
    print(f"写入 {len(to_write)} 家高置信营业时间", file=sys.stderr)

    BATCH = 50
    ok, fail = 0, 0
    for i in range(0, len(to_write), BATCH):
        batch = to_write[i:i+BATCH]
        for item in batch:
            rid = item["id"]
            payload = {
                "opening_hours": item["opening_hours"],
                "open_days": item["open_days"],
            }
            try:
                r = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=payload)
                if r.status_code in (200, 204):
                    ok += 1
                else:
                    fail += 1
                    print(f"  [FAIL] id={rid}: {r.status_code} {r.text[:100]}", file=sys.stderr)
            except Exception as e:
                fail += 1
                print(f"  [ERR] id={rid}: {e}", file=sys.stderr)
            time.sleep(0.05)

        # 回读验证
        ids = [str(x["id"]) for x in batch]
        try:
            rv = C.req("GET",
                       f"/restaurants?select=id,opening_hours,open_days&id=in.({','.join(ids)})")
            if rv.status_code == 200:
                checked = {row["id"]: row for row in rv.json()}
                verified = sum(1 for x in batch
                               if checked.get(x["id"], {}).get("opening_hours") == x["opening_hours"])
                print(f"  批次 {i//BATCH+1}: 写入{len(batch)}, 回读验证 {verified}/{len(batch)}",
                      file=sys.stderr)
        except Exception as e:
            print(f"  回读异常: {e}", file=sys.stderr)

    print(f"\n完成: 成功 {ok}, 失败 {fail}", file=sys.stderr)


if __name__ == "__main__":
    main()

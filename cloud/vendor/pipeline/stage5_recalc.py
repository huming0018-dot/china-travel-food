#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage5_recalc.py — 评分口径只读校验（002_harden 之后）

重要变化：score_total 现由数据库触发器 trg_restaurants_derive 独占计算，
应用/脚本手填或 PATCH score_total 都会在写库时被触发器按唯一公式覆盖：

  score_total = clamp[0,100]( round(0.4o + 0.3d + 0.2t + 0.1e - penalty, 1) )
  四项子分缺一 → score_total = NULL（ch_rest_score_complete 约束 + 触发器）

因此本脚本不再写库（历史上的 --commit PATCH score_total 已无意义）。
它只做两件事：
  1) 找出与公式不符的 total（正常应为 0；非 0 说明触发器缺失或被绕过）；
  2) 找出评分残缺的店（应回填四项子分；回填后触发器自动算 total，无需重算）。

修复残缺评分的正确方式：补齐证据后，经 stage1→stage3 写回四个子分（不要写 total）。

用法：
  python3 stage5_recalc.py --report-only     # 输出统计（默认）
  python3 stage5_recalc.py                   # 输出统计 + 残缺/不符清单
"""
import argparse
import json
import pathlib

import common as C


def expected_total(o, d, t, e, pen):
    return round(max(0.0, min(100.0, 0.4 * o + 0.3 * d + 0.2 * t + 0.1 * e - pen)), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--report", default="recalc_report.json")
    args = ap.parse_args()

    rs = C.fetch_all(
        "restaurants",
        "id,name,score_total,score_objective,score_diner,score_taste,score_endorsement,soft_ad_penalty",
        order_col="id")

    mismatch, incomplete, ok = [], [], 0
    for r in rs:
        def f(k):
            return None if r.get(k) is None else float(r[k])
        o, d, t, e = f("score_objective"), f("score_diner"), f("score_taste"), f("score_endorsement")
        pen = f("soft_ad_penalty") or 0.0
        pv = [o, d, t, e]
        if any(x is None for x in pv):
            incomplete.append({"id": r["id"], "name": r["name"]})
            continue
        exp = expected_total(o, d, t, e, pen)
        cur = r.get("score_total")
        if cur is None or abs(float(cur) - exp) > 0.15:
            mismatch.append({"id": r["id"], "name": r["name"], "db_total": cur, "expected": exp})
        else:
            ok += 1

    print(f"total 与触发器公式一致 {ok} 家；不符 {len(mismatch)} 家；评分残缺 {len(incomplete)} 家")
    if not args.report_only:
        for x in mismatch[:40]:
            print(f"  [不符] id{x['id']} {x['name'][:20]:<22} db={x['db_total']} 应为{x['expected']}")
        for x in incomplete[:40]:
            print(f"  [残缺] id{x['id']} {x['name'][:20]}（补齐四项子分后触发器自动算 total）")

    pathlib.Path(args.report).write_text(
        json.dumps({"mismatch": mismatch, "incomplete": incomplete}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    if mismatch:
        print("\n⚠️ 存在 total 与公式不符：检查触发器 trg_restaurants_derive 是否存在/启用；"
              "切勿手改 total，应核对四项子分后让触发器重算（任意 UPDATE 即触发）。")
    if incomplete:
        print(f"\n待回填 {len(incomplete)} 家：按真实堂食证据补齐四项子分，走 stage1→stage3。")
    print(f"\n只读校验完成，未写库；报告 {args.report}")


if __name__ == "__main__":
    main()

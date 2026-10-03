#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""premade_takedown.py — #39 基于标签机制下架预制/工业化餐馆（硬门，不消费先验）。

下架规则（满足其一，证据可追溯；不消费 *_prior、不靠推断）：
  A. 硬复热：is_reheat_served=true（production_model ∈ 央厨门店复热/预制料理包复热/外购无厨房）。
  B. 工业化集中出餐：chain_type=资本化 且 central_kitchen=确认
     且 production_model=中央厨房·门店加工，且 fact_claims 有 high 可信 CK 陈述明确表明
     「大部分/绝大多数烹饪工序转移至央厨」或「全自动工厂/产能规模化」（附权威来源 URL）。
不满足硬门、仅疑似/先验的店一律不下架，只列入复查清单（宁空不假）。
用法：python3 premade_takedown.py [--apply]
"""
import argparse, datetime, json, re, sys
sys.path.insert(0, "/app/cloud")
import common_core as CC

MAJ = re.compile(r"大部分|绝大多数|主要.{0,6}工序|全自动|智慧.{0,4}工厂|产能|标准化")


def rule_b_source(claims):
    for c in claims or []:
        if c.get("type") == "central_kitchen" and c.get("confidence") == "high":
            q = c.get("quote", "")
            if MAJ.search(q):
                return c.get("source_url", ""), q[:60]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rests = CC.fetch_all(
        "restaurants",
        "id,name,chain_type,central_kitchen,production_model,is_reheat_served,"
        "is_delisted,fact_claims,status",
        order_col="id")

    delist, review = [], []
    for r in rests:
        if r.get("is_delisted"):
            continue
        pm = r.get("production_model")
        reason = src = None
        if r.get("is_reheat_served") is True:
            reason, src = f"硬复热出餐（production_model={pm}）", None
        elif r.get("chain_type") == "资本化连锁" and r.get("central_kitchen") == "确认" \
                and pm == "中央厨房·门店加工":
            src, q = rule_b_source(r.get("fact_claims"))
            if src:
                reason = f"工业化集中出餐：资本化+央厨确认+门店加工，证据「{q}」"
        if reason:
            delist.append((r["id"], r["name"], reason, src))
            if args.apply:
                CC.req("PATCH", f"/restaurants?id=eq.{r['id']}", json={
                    "is_delisted": True,
                    "delist_reason": reason,
                    "delisted_at": datetime.datetime.now().isoformat(timespec="seconds")},
                    use_service=True)
        elif r.get("is_chain_standardized") or (r.get("chain_type") == "资本化连锁"):
            review.append((r["id"], r["name"], pm, r.get("central_kitchen")))

    print(f"本次下架：{len(delist)}")
    for i, n, why, s in delist:
        print(f"  [{i}] {n[:24]} :: {why[:80]} {s or ''}")
    print(f"列入复查（证据不足/字段矛盾，未下架）：{len(review)}")
    for i, n, pm, ck in review[:20]:
        print(f"  [{i}] {n[:24]:<26} pm={pm} ck={ck}")
    print("模式：", "APPLY" if args.apply else "dry-run")


if __name__ == "__main__":
    main()

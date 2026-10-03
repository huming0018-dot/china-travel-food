#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apify_priority.py — #43 为 Apify 采集提供实施名单（把钱花在刀刃上）。

按「预期信息增益」对在营未下架店排序，输出优先级 brief（JSON + Markdown）：
  高优先：人工三档标注但口味证据不足、有奖项背书但缺真实口味、curate hold/reverify、
          口味分缺失/极少；
  低优先/排除：标准化连锁、已 verified 且口味评论充足、已下架。
输出：/app/data/apify_brief.json、/app/data/apify_brief.md
用法：python3 apify_priority.py [--top N]
"""
import argparse, collections, datetime, json, sys
sys.path.insert(0, "/app/cloud")
import common_core as CC


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=150)
    args = ap.parse_args()
    rests = CC.fetch_all(
        "restaurants",
        "id,name,district,score_taste,score_objective,score_endorsement,score_evidence_level,"
        "review_count,review_confidence,curate_badge,curate_reason,"
        "is_chain_standardized,is_delisted,status,created_at",
        order_col="id")
    seed = CC.fetch_all("diner_seed_labels", "restaurant_id,tier",
                        order_col="restaurant_id")
    seed_map = {str(x["restaurant_id"]): x.get("tier") for x in seed}
    reviews = CC.fetch_all(
        "reviews", "restaurant_id,review_kind,is_fake_suspect,is_hidden,aspect_taste,rating_taste,rating_total",
        order_col="id")
    taste_n = collections.Counter()
    for x in reviews:
        if x.get("review_kind") == "diner" and not x.get("is_fake_suspect") and \
                (x.get("aspect_taste") or x.get("rating_taste") or x.get("rating_total")):
            taste_n[str(x["restaurant_id"])] += 1

    rows = []
    for r in rests:
        if r.get("status") != "active" or r.get("is_delisted"):
            continue
        tn = taste_n[str(r["id"])]
        raw_lab = seed_map.get(str(r["id"]))
        lab = {"must_eat": "必吃", "worth_eating": "值得"}.get(raw_lab)
        p = 0
        if lab == "必吃":
            p += 40
        elif lab == "值得":
            p += 30
        elif lab == "精选":
            p += 15
        if (r.get("score_endorsement") or 0) >= 80 and tn < 4:
            p += 25
        if r.get("score_taste") is None:
            p += 20
        if tn == 0:
            p += 20
        elif tn <= 2:
            p += 12
        elif tn <= 5:
            p += 6
        cr = r.get("curate_reason") or ""
        if "hold" in cr or "reverify" in cr or "复查" in cr:
            p += 15
        if r.get("is_chain_standardized"):
            p -= 30
        if r.get("score_evidence_level") == "verified" and tn >= 12:
            p -= 25
        p = max(0, min(100, p))
        if p <= 0:
            continue
        rows.append({
            "priority": p, "id": r["id"], "name": r["name"],
            "district": r.get("district"), "expert_label": lab,
            "score_taste": r.get("score_taste"),
            "score_endorsement": r.get("score_endorsement"),
            "taste_reviews": tn, "evidence_level": r.get("score_evidence_level"),
            "target_questions": "招牌菜口味与水准 / 是否现做现炒 / 与同品类头部对比 / 近期出品稳定性"
            if tn < 3 else "补足近期口味样本 / 核验出品稳定性 / 负面口味甄别"})

    rows.sort(key=lambda x: -x["priority"])
    top = rows[:args.top]
    with open("/app/data/apify_brief.json", "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "total_candidates": len(rows), "top": top}, f, ensure_ascii=False, indent=1)
    lines = [f"# Apify 采集优先级 brief（候选 {len(rows)}，列前 {len(top)}）",
             "", "| 优先级 | 店名 | 区 | 专家档 | 口味分 | 背书分 | 口味评论 | 目标问题 |",
             "|---|---|---|---|---|---|---|---|"]
    for x in top:
        lines.append("| {p} | {n} | {d} | {l} | {t} | {e} | {tn} | {q} |".format(
            p=x["priority"], n=x["name"][:22], d=x["district"] or "", l=x["expert_label"] or "",
            t=x["score_taste"] if x["score_taste"] is not None else "",
            e=x["score_endorsement"] if x["score_endorsement"] is not None else "",
            tn=x["taste_reviews"], q=x["target_questions"][:24]))
    with open("/app/data/apify_brief.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"候选 {len(rows)}；brief 输出前 {len(top)}；高优先(>=60) {sum(1 for x in rows if x['priority']>=60)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1b3_anti_softad_expand.py — Track 1B-3：反软广拓宽为可判定三类 + 综艺影视人气特征信号
============================================================================
在 Phase 0-C（phase0c_negative_tagon）之上拓宽，不碰其他块。

三类污染（独立打分，可判定）：
  · industrial 预制/中央厨房/连锁标准化 —— 由 restaurants.chain_type/central_kitchen/
    premade_risk 输入列经 trigger 派生 soft_ad_flag / is_chain_standardized（本脚本只读统计）。
  · astroturf 伪草根/刷评 —— 由 softad_distribution.py（cron 5:37）自学"正常 vs 异常评价分布"
    写 soft_ad_flag_reviews；本脚本只读其 baselines.json + 聚合 reviews.is_fake_suspect。
  · paid 硬广通投/商家自发 —— review 级：作者为商家/场地推广号、trust=low、无堂食评分的通稿，
    本脚本将其 is_hidden=true（review 级处理，不公开展示；口味计算本已排除 fake_suspect）。

一类信号（特征标签，不构成准入、不降权）：
  · 综艺/影视/明星带来的曝光（如帅帅精致=一饭封神出圈）——只挂「综艺影视人气」标签作发现信号，
    口味仍唯一；绝不因此改 chain_type/pr/score。证据必须显式，宁空不假。

写库红线：
  · soft_ad_flag / soft_ad_penalty / is_chain_standardized 全部 trigger/generated 派生，本脚本绝不直写。
  · 唯一写：① 「综艺影视人气」标签 junction（可逆，删行即撤）；② review 级 is_hidden=true（可逆）。
  · 不改菜系/电话/坐标/价格/评分/招牌菜。

用法：
  python3 1b3_anti_softad_expand.py           # dry-run，全量只读 + 计划，不写
  python3 1b3_anti_softad_expand.py --apply     # 自检全绿才写，写后回读
"""
import os, sys, json, argparse, collections, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
REPORT_DIR = os.path.join(OUT_DIR, "phase1b3")
VARIETY_TAG = "综艺影视人气"

# 综艺/影视/明星人气：仅收录【有明确证据】的店（宁空不假；泛泛"明星打卡"不计）。
# evidence 为该店证据摘要里的原话片段，供追溯。
VARIETY_SHOPS = {
    1892: "帅帅精致家常味——综艺《一饭封神》出圈，帅晓剑外婆红烧肉满分",
    904:  "福承(前滩华尔道夫)——《一饭封神》星厨杨艳彬坐镇闽菜",
    1862: "COLCA秘鲁餐厅——东方卫视《上海环球美食争霸赛》总冠军",
    1095: "姜虎东白丁——韩国综艺人姜虎东同名连锁",
}


def today():
    return datetime.date.today().isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    os.makedirs(REPORT_DIR, exist_ok=True)

    # ---------------- 拉全量（只读） ----------------
    rests = C.fetch_all("restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,soft_ad_flag,"
        "soft_ad_flag_reviews,soft_ad_penalty,is_chain_standardized,review_count,"
        "score_total,price_scene,score_evidence_level", order_col="id")
    active = [r for r in rests if r["status"] == "active"]
    byid = {r["id"]: r for r in active}

    reviews = C.fetch_all("reviews",
        "id,restaurant_id,author_name,source_platform,trust_level,is_fake_suspect,"
        "is_hidden,rating_total,review_kind", order_col="id")

    # ---------------- 1. 三类污染判定（店铺级） ----------------
    industrial, astroturf_shop, paid_shop = [], [], []
    for r in active:
        rid = r["id"]
        # industrial: 连锁标准化 / 预制
        is_ind = (r.get("chain_type") in ("大型连锁", "资本化连锁")
                  or r.get("premade_risk") in ("高", "疑似")
                  or r.get("central_kitchen") in ("确认", "疑似"))
        if is_ind:
            industrial.append(r)
        # astroturf: reviews 侧分布模型判定 != none
        if r.get("soft_ad_flag_reviews") not in (None, "none"):
            astroturf_shop.append(r)

    industrial_confirmed = [r for r in industrial if r.get("soft_ad_flag") == "confirmed"]
    industrial_suspected = [r for r in industrial if r.get("soft_ad_flag") == "suspected"]

    # ---------------- 2. review 级 paid / astroturf 帖子 ----------------
    # 商家/场地推广号自发：fake_suspect=true（作者为店方/婚庆场地号、trust=low、无评分）
    fake_reviews = [r for r in reviews if r.get("is_fake_suspect")]
    to_hide = [r for r in fake_reviews if not r.get("is_hidden")]  # 待隐藏

    # ---------------- 3. 分布学习口径（读 softad 自学结果） ----------------
    softad = {"baseline_present": False}
    bp = os.path.join(OUT_DIR, "softad", "baselines.json")
    if os.path.exists(bp):
        b = json.load(open(bp, encoding="utf-8"))
        vd = b.get("verdicts", {})
        softad = {
            "baseline_present": True, "run_date": b.get("run_date"),
            "learned_thresholds": b.get("thresholds"),
            "corpus": b.get("corpus"),
            "verdicts_dist": dict(collections.Counter(vd.values())),
            "n_scorable_shops": len(vd),
            "note": "离群信号: 五星占比/无实质占比/14天burst/近重复文本/作者集中度；阈值=语料稳健分位∩保守底线",
        }

    # ---------------- 4. 综艺影视人气特征标签计划 ----------------
    cui = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    variety_tag = next((c for c in cui if c["name"] == VARIETY_TAG and c["dimension"] == "标签"), None)
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    tagged_set = {(x["restaurant_id"], x["cuisine_id"]) for x in rc}
    variety_plan = []
    for rid, ev in VARIETY_SHOPS.items():
        r = byid.get(rid)
        if not r:
            variety_plan.append({"id": rid, "skip": "not_found", "evidence": ev})
            continue
        already = variety_tag and (rid, variety_tag["id"]) in tagged_set
        variety_plan.append({
            "id": rid, "name": r["name"], "evidence": ev,
            "already_tagged": bool(already),
            "needs_link": (not already),
            "check_pr": r.get("premade_risk"), "check_flag": r.get("soft_ad_flag"),
            "check_std": bool(r.get("is_chain_standardized")),
        })

    # ---------------- 5. 淘汰清单（预制属性连锁 移出精选） ----------------
    # 已被派生机制淘汰：flag=confirmed（penalty25，分数下沉）+ std=True（前端隐藏连锁开关过滤）
    eliminated = sorted(industrial_confirmed, key=lambda r: r["id"])
    # 在库但下沉不推荐：suspected
    downweighted = sorted(industrial_suspected, key=lambda r: r["id"])

    # ---------------- 6. 自检（反误伤为最高） ----------------
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 6a 独立店被 penalty 必须有【具体输入】：ck/pr 硬信号 或 reviews 侧分布判定(soft_ad_flag_reviews!=none)。
    #     无任何信号却被 penalty = 误杀，必须拦下。
    indep_no_signal = [r for r in active
                        if r.get("chain_type") == "独立店" and (r.get("soft_ad_penalty") or 0) > 0
                        and r.get("premade_risk") not in ("低", "疑似", "高")
                        and r.get("central_kitchen") not in ("疑似", "确认")
                        and r.get("soft_ad_flag_reviews") in (None, "none")]
    check("独立店penalty必有ck/pr或reviews分布信号(无信号误杀=0)", len(indep_no_signal) == 0,
          f"{len(indep_no_signal)}: {[(r['id'],r['name']) for r in indep_no_signal[:5]]}")
    # 6a2 reviews侧分布模型判 suspected 的独立店（borderline，留观，不手工覆写）
    rev_sus_indep = [r for r in active
                     if r.get("chain_type") == "独立店"
                     and r.get("soft_ad_flag_reviews") not in (None, "none")]
    report_borderline = [{"id": r["id"], "name": r["name"],
                          "reviews_flag": r.get("soft_ad_flag_reviews"),
                          "evidence_level": r.get("score_evidence_level"),
                          "score": r.get("score_total")} for r in rev_sus_indep]

    # 6b 综艺标签只能加在 pr=无/flag=none 的店（特征标签绝不构成降权）
    bad_variety = [v for v in variety_plan if v.get("check_pr") not in (None, "无") or v.get("check_flag") not in (None, "none")]
    check("综艺标签店均非工业化/无penalty(纯特征)", len(bad_variety) == 0,
          str([(v.get("id"), v.get("check_pr"), v.get("check_flag")) for v in bad_variety]))

    # 6c 淘汰正例（用户点名）必须 confirmed+std
    pos = {}
    for kw in ["盖饭邦", "望湘园", "小菜园"]:
        for r in eliminated:
            if kw in r["name"]:
                pos[kw] = (r["soft_ad_flag"], r["is_chain_standardized"], r["score_total"])
    check("盖饭邦/望湘园/小菜园已淘汰(confirmed+std)",
          all(v[0] == "confirmed" and v[1] for v in pos.values()), str(pos))

    # 6d 待隐藏评论必须确为 fake_suspect（不藏正常评论）
    check("待隐藏评论全部is_fake_suspect", all(x.get("is_fake_suspect") for x in to_hide),
          f"n={len(to_hide)}")

    all_ok = all(c["ok"] for c in checks)

    # ---------------- 报告 ----------------
    report = {
        "run_date": today(), "mode": "apply" if args.apply else "dry-run",
        "three_category": {
            "industrial_total": len(industrial),
            "industrial_confirmed_eliminated": len(industrial_confirmed),
            "industrial_suspected_downweighted": len(industrial_suspected),
            "astroturf_shop_level": len(astroturf_shop),
            "paid_review_level_posts": len(fake_reviews),
            "paid_shop_level": 0,
        },
        "distribution_learning": softad,
        "variety_feature_tag": {"tag_name": VARIETY_TAG, "tag_id": (variety_tag or {}).get("id"),
                                "plan": variety_plan},
        "elimination_list": [{"id": r["id"], "name": r["name"], "chain_type": r["chain_type"],
                              "premade_risk": r["premade_risk"], "score_total": r["score_total"]}
                             for r in eliminated],
        "downweighted_list": [{"id": r["id"], "name": r["name"],
                               "premade_risk": r["premade_risk"]} for r in downweighted],
        "reviews_to_hide": [{"id": x["id"], "restaurant_id": x["restaurant_id"],
                             "author": x.get("author_name"), "src": x.get("source_platform")}
                            for x in to_hide],
        "astroturf_distribution_borderline_indep": report_borderline,
        "self_checks": checks, "all_self_checks_pass": all_ok,
    }
    jpath = os.path.join(REPORT_DIR, f"report_{today()}.json")
    json.dump(report, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("=" * 64)
    print(f"Track 1B-3 反软广拓宽+负面清单/淘汰  [{report['mode']}]")
    print("=" * 64)
    tc = report["three_category"]
    print(f"三类判定(店铺级): industrial {tc['industrial_total']} "
          f"(confirmed淘汰 {tc['industrial_confirmed_eliminated']} / suspected下沉 {tc['industrial_suspected_downweighted']})"
          f" | astroturf {tc['astroturf_shop_level']} | paid店级 {tc['paid_shop_level']}")
    print(f"review级 paid/推广帖(商家号自发): {tc['paid_review_level_posts']} 条，待隐藏 {len(to_hide)}")
    print(f"分布学习: run={softad.get('run_date')} thresholds={softad.get('learned_thresholds')} "
          f"可打分店={softad.get('n_scorable_shops')} verdicts={softad.get('verdicts_dist')}")
    print(f"\n综艺影视人气标签: tag_id={report['variety_feature_tag']['tag_id']}")
    for v in variety_plan:
        print(f"   [{'LINK' if v.get('needs_link') else 'have/skip'}] id={v.get('id')} {v.get('name','?')} :: {v.get('evidence','')[:50]}")
    print(f"\n淘汰清单(pr高/ck确认,flag=confirmed,std=True) {len(eliminated)} 家:")
    for r in eliminated:
        print(f"   OUT id={r['id']:>4} {r['name'][:28]:<30} score={r['score_total']}")
    print("\n--- 自检 ---")
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}  {c['detail'][:100]}")
    print("ALL SELF CHECKS:", "PASS" if all_ok else "FAIL")

    if not args.apply:
        print(f"\n[dry-run] 报告 {jpath}；自检全绿后加 --apply")
        return
    if not all_ok:
        print("\n[ABORT] 自检未全绿，不写库。")
        sys.exit(1)

    # ---------------- APPLY ----------------
    # (a) 确保综艺影视人气标签存在
    if not variety_tag:
        r = C.req("POST", "/cuisines", json={"name": VARIETY_TAG, "dimension": "标签", "parent_category": None})
        if r.status_code not in (200, 201):
            print("建标签失败", r.status_code, r.text[:160]); sys.exit(1)
        # 回查 id
        for c in C.fetch_all("cuisines", "id,name,dimension", order_col="id"):
            if c["name"] == VARIETY_TAG and c["dimension"] == "标签":
                variety_tag = c; break
    tid = variety_tag["id"]

    ok = 0
    for v in variety_plan:
        if not v.get("needs_link"):
            continue
        r = C.req("POST", "/restaurant_cuisines",
                  json={"restaurant_id": v["id"], "cuisine_id": tid})
        if r.status_code in (200, 201) or r.status_code == 409:
            ok += 1
        else:
            print("  tag link 失败", v["id"], r.status_code, r.text[:120])
    print(f"[apply] 综艺标签 junction: 新连 {ok}/{sum(1 for v in variety_plan if v.get('needs_link'))}")

    # (b) 隐藏商家/场地号推广帖（review 级）
    hok = 0
    for x in to_hide:
        r = C.req("PATCH", f"/reviews?id=eq.{x['id']}", json={"is_hidden": True})
        if r.status_code in (200, 204):
            hok += 1
        else:
            print("  hide review 失败", x["id"], r.status_code, r.text[:120])
    print(f"[apply] review 级隐藏推广帖: {hok}/{len(to_hide)}")

    # ---------------- 回读 ----------------
    rc2 = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    after_tags = {x["restaurant_id"] for x in rc2 if x["cuisine_id"] == tid}
    rv2 = C.fetch_all("reviews", "id,is_hidden,is_fake_suspect", order_col="id")
    still_visible_fake = [r["id"] for r in rv2 if r.get("is_fake_suspect") and not r.get("is_hidden")]
    print(f"[回读] 综艺标签已连店 {sorted(after_tags)}；仍可见fake帖 {len(still_visible_fake)}")
    report["applied"] = {"variety_links": ok, "reviews_hidden": hok,
                         "readback_variety_shops": sorted(after_tags),
                         "readback_fake_still_visible": still_visible_fake}
    json.dump(report, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"报告已更新 {jpath}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
curate_score.py — 守门员·精选评分器（人工三档监督 + 贝叶斯证据 + 价位弱先验 + 软广闸门）。

设计依据（对 1473 店、123 条人工标注实测，非拍脑袋）：
  · 现有 score_diner/score_endorsement/score_objective 与人工档位几乎不相关（一般档甚至高于值得档），
    大量是 75 先验默认与单评论极端值 → 不能在噪声上回归。
  · 真正可信的只有：①人工三档（最高，直接采用）；②真实奖项 restaurant_awards（米其林/黑珍珠/Bib）；
    ③足量独立真实食客证据（n_ind>=2、带口味、有实质）。
  · 价格与档位经验上非单调（值得档最便宜）→ 价位仅作弱先验，权重由数据估、上限很小，绝不决定入选。

精选决策（按优先级）：
  人工一般 → 不入选；
  硬闸门（is_chain_standardized / 预制高 / 中央厨房确认 / 软广confirmed）→ 不入选；
  软警戒（各类 suspected）→ 仅在有强奖项或 n_ind>=3 高质量时入选；
  人工必吃/值得 → 入选；强奖项 → 入选；中奖项/足量真实证据达标 → 入选；其余 → 不入选（留在全量库）。

用法：python3 curate_score.py [--apply]
"""
import os, sys, json, math, argparse, collections, datetime, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
CUR_DIR = os.path.join(OUT_DIR, "curate"); os.makedirs(CUR_DIR, exist_ok=True)
HALF = 180.0
TIER_VAL = {"must_eat": 3, "worth_eating": 2, "average": 1}


def parse_date(s):
    s = (s or "")[:10]
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None


def substantive(t):
    if hasattr(C, "quote_has_substance"):
        try:
            return C.quote_has_substance(t or "")
        except Exception:
            pass
    han = "".join(ch for ch in (t or "") if "一" <= ch <= "鿿")
    return len(han) >= 8 or bool(re.search(r"(好吃|香|嫩|鲜|入味|正宗|地道|雷|柴|腥|咸|甜|脆)", t or ""))


def taste_of(r):
    for k in ("aspect_taste", "rating_taste", "rating_total"):
        if r.get(k) is not None:
            try:
                return float(r[k])
            except Exception:
                pass
    return None


def quantile(xs, q):
    xs = sorted(xs); n = len(xs)
    if n == 1:
        return xs[0]
    k = (n - 1) * q; lo = int(k); f = k - lo
    return xs[lo] * (1 - f) + xs[min(lo + 1, n - 1)] * f


def award_score(award_type, level):
    lv = level or ""
    if award_type == "michelin_star":
        return 98 if "三" in lv else 92 if "二" in lv else 85
    if award_type == "black_pearl":
        return 92 if "三" in lv else 82 if "二" in lv else 70
    if award_type == "bib_gourmand":
        return 72
    return 0


def evidence_by_store(revs, active_ids):
    """每店干净真实证据：独立作者、时间衰减、作者权重封顶。"""
    by = collections.defaultdict(list)
    for r in revs:
        if r.get("review_kind") != "diner" or r.get("is_fake_suspect") or r.get("is_hidden"):
            continue
        if r.get("trust_level") not in ("mid", "high"):
            continue
        tv = taste_of(r)
        if tv is None or not substantive(r.get("content")):
            continue
        if r["restaurant_id"] in active_ids:
            by[r["restaurant_id"]].append(r)
    out = {}
    today = datetime.date.today()
    for rid, rr in by.items():
        # 时间权重
        def w_of(r):
            d = parse_date(r.get("visit_date") or r.get("created_at"))
            age = max(0, (today - d).days) if d else 365
            return 0.5 ** (age / HALF)
        per_author = collections.defaultdict(float); per_author_q = collections.defaultdict(list)
        for r in rr:
            a = r.get("author_name") or "?"
            per_author[a] += w_of(r)
            per_author_q[a].append((w_of(r), (taste_of(r) - 1) / 4 * 100))
        # 作者封顶权重 2.0
        aw, aq, negw, tw = {}, {}, 0.0, 0.0
        for a, w0 in per_author.items():
            cap = min(w0, 2.0)
            mu_a = sum(w * q for w, q in per_author_q[a]) / sum(w for w, _ in per_author_q[a])
            aw[a] = cap; aq[a] = mu_a; tw += cap
            if mu_a < 40:
                negw += cap
        mu = sum(aw[a] * aq[a] for a in aw) / tw
        n_ind = len(aw)
        author_means = list(aq.values())
        spread = (max(author_means) - min(author_means)) if n_ind >= 2 else 0
        neg_share = negw / tw
        safe = mu - (6 if n_ind == 2 else 3 if n_ind == 3 else 0) \
            - 18 * neg_share - 0.25 * max(0, spread - 20)
        out[rid] = {"mu": round(mu, 1), "safe": round(safe, 1), "n_ind": n_ind,
                    "neg_share": round(neg_share, 2), "spread": round(spread, 1),
                    "v": round(tw, 2)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all(
        "restaurants",
        "id,name,status,price_avg,price_scene,price_position,chain_type,central_kitchen,"
        "premade_risk,is_chain_standardized,soft_ad_flag,soft_ad_flag_reviews",
        order_col="id")
    active = [r for r in rests if r["status"] == "active"]
    active_ids = {r["id"] for r in active}

    labels = C.fetch_all("diner_seed_labels", "restaurant_id,tier",
                        order_col="restaurant_id", extra="labeler=eq.expert")
    lab = {x["restaurant_id"]: x["tier"] for x in labels}

    revs = C.fetch_all(
        "reviews",
        "id,restaurant_id,author_name,source_platform,trust_level,review_kind,is_fake_suspect,"
        "is_hidden,aspect_taste,rating_taste,rating_total,visit_date,created_at,content",
        order_col="id")
    ev = evidence_by_store(revs, active_ids)

    awards = C.fetch_all("restaurant_awards",
                        "restaurant_id,award_type,level,year,is_current", order_col="id")
    aw_by = collections.defaultdict(list)
    for a in awards:
        if a.get("is_current"):
            aw_by[a["restaurant_id"]].append(a)

    # ---- 价位弱先验：在标注店上估“价位档→档位”的经验关系（斜率），并强收缩 ----
    pos_num = {"入门": 1, "主流": 2, "进阶": 3, "高端": 4, "旗舰": 5}
    xs, ys = [], []
    for r in active:
        rid = r["id"]
        if rid in lab and r.get("price_position") in pos_num:
            xs.append(pos_num[r["price_position"]]); ys.append(TIER_VAL[lab[rid]])
    w_price = 0.0
    if len(xs) >= 8:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        var = sum((a - mx) ** 2 for a in xs)
        w_price = max(-0.15, min(0.25, (cov / var) if var else 0))  # 强收缩到 ±0.25

    # ---- 证据阈值校准：标注店中有 n_ind>=2 者，取“好店 safe 分位”与“一般 safe 分位”之间 ----
    good_safe, avg_safe = [], []
    for r in active:
        rid = r["id"]; e = ev.get(rid)
        if not e or e["n_ind"] < 2:
            continue
        if lab.get(rid) in ("must_eat", "worth_eating"):
            good_safe.append(e["safe"])
        elif lab.get(rid) == "average":
            avg_safe.append(e["safe"])
    t_good = quantile(good_safe, .25) if good_safe else 78
    t_avg = quantile(avg_safe, .75) if avg_safe else 72
    T_ev = round(max(t_avg + 3, min(t_good, 80)), 1)  # 偏保守

    def hard_block(r):
        return bool(r.get("is_chain_standardized")) or r.get("premade_risk") == "高" \
            or r.get("central_kitchen") == "确认" or r.get("soft_ad_flag") == "confirmed" \
            or r.get("soft_ad_flag_reviews") == "confirmed"

    def soft_caution(r):
        return r.get("soft_ad_flag") == "suspected" or r.get("soft_ad_flag_reviews") == "suspected" \
            or r.get("premade_risk") == "疑似" or r.get("central_kitchen") == "疑似"

    def best_award(rid):
        sc, strong, medium = 0, False, False
        for a in aw_by.get(rid, []):
            s = award_score(a["award_type"], a["level"])
            sc = max(sc, s)
            if a["award_type"] == "michelin_star" or \
               (a["award_type"] == "black_pearl" and "二" in (a["level"] or "") or "三" in (a["level"] or "")):
                strong = True
            if a["award_type"] == "bib_gourmand" or a["award_type"] == "black_pearl":
                medium = True
        return sc, strong, medium

    results = []
    for r in active:
        rid = r["id"]; e = ev.get(rid)
        asc, astrong, amedium = best_award(rid)
        curated, badge, reason, conf = False, None, "", 0.0
        # 1 人工
        if lab.get(rid) == "average":
            reason = "专家评定一般"; conf = .9
        elif lab.get(rid) == "must_eat":
            curated, badge, reason, conf = True, "必吃", "人工必吃", .95
        elif lab.get(rid) == "worth_eating":
            curated, badge, reason, conf = True, "值得", "人工值得", .9
        elif hard_block(r):
            reason = "工业化/预制/刷评（守门员拦截）"; conf = .85
        else:
            caution = soft_caution(r)
            n_ind = e["n_ind"] if e else 0
            if astrong:
                curated, badge, reason = True, "精选", "米其林星/黑珍珠高钻"
                conf = .85
            elif amedium and (n_ind >= 1 or not caution):
                curated, badge, reason, conf = True, "精选", "必比登/黑珍珠一钻", .75
            elif n_ind >= 2 and e["safe"] >= T_ev and (not caution or n_ind >= 3):
                curated, badge, reason, conf = True, "精选", f"{n_ind}名独立食客真实口碑", .6
            elif caution:
                reason = "存疑且强证据不足"; conf = .5
            else:
                reason = "真实证据不足（保留在全量库）"; conf = .35
        # ---- curate_score：真实证据按证据量贝叶斯收缩，奖项为辅，价位弱先验，闸门压顶 ----
        K_EV, PRIOR_EV = 6.0, 72.0
        if e:
            evc = (e["v"] / (e["v"] + K_EV)) * e["mu"] \
                + (K_EV / (e["v"] + K_EV)) * PRIOR_EV
            base = 0.72 * evc + 0.28 * asc if asc else evc
        else:
            base = asc if asc else 55.0
        pn = pos_num.get(r.get("price_position"))
        if pn is not None:
            base += w_price * (pn - 3) * 6
        if not curated and hard_block(r):
            base = min(base, 45)
        score = round(max(0, min(100, base)), 1)
        results.append({"id": rid, "name": r["name"], "is_curated": curated,
                        "badge": badge, "curate_score": score,
                        "curate_confidence": round(conf, 2), "curate_reason": reason,
                        "astroturf_score": None, "n_ind": e["n_ind"] if e else 0})

    curated_rows = [x for x in results if x["is_curated"]]
    bc = collections.Counter(x["badge"] for x in curated_rows)
    summary = {"run_date": datetime.date.today().isoformat(),
               "active": len(active), "curated": len(curated_rows),
               "badges": dict(bc), "evidence_threshold": T_ev,
               "price_weight": round(w_price, 3),
               "calibration": {"good_safe": good_safe and round(quantile(good_safe,.25),1),
                               "avg_safe": avg_safe and round(quantile(avg_safe,.75),1)}}
    json.dump(summary, open(os.path.join(CUR_DIR, "summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(CUR_DIR, "curate_result.jsonl"), "w", encoding="utf-8") as f:
        for x in results:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    print(f"active {len(active)}；精选 {len(curated_rows)} {dict(bc)}")
    print(f"证据阈值 T_ev={T_ev}；价位先验权重 w_price={round(w_price,3)}（经验弱/非单调）")
    print("\n=== 守门员拦截（示例前20）===")
    for x in [x for x in results if "守门员" in x["curate_reason"]][:20]:
        print(f"  OUT id{x['id']:<5} {x['name'][:24]:<26} score={x['curate_score']}")
    print("\n=== 精选 TOP20 ===")
    for x in sorted(curated_rows, key=lambda z: -z["curate_score"])[:20]:
        print(f"  IN  id{x['id']:<5} {x['name'][:24]:<26} {x['badge']:<3} "
              f"score={x['curate_score']} {x['curate_reason']}")
    print(f"\n明细 -> {os.path.join(CUR_DIR,'curate_result.jsonl')}")

    if not args.apply:
        print("[dry-run] 加 --apply 才写库"); return

    n = 0
    for x in results:
        body = {"is_curated": x["is_curated"], "curate_badge": x["badge"],
                "curate_score": x["curate_score"], "curate_confidence": x["curate_confidence"],
                "curate_reason": x["curate_reason"]}
        r = C.req("PATCH", f"/restaurants?id=eq.{x['id']}", json=body)
        n += 1 if r.status_code in (200, 204) else 0
    print(f"[apply] PATCH {n}/{len(results)} 店")


if __name__ == "__main__":
    main()

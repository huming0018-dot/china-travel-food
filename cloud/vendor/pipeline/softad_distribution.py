#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
softad_distribution.py — 软广/伪草根「分布自学」器（cron 5:37；1b3/phase0c 引用，原脚本缺失，本文件补齐）。

不靠硬关键词拍脑袋，而是从评论语料自学“正常 vs 异常”的分布，再用专家标注与已知工业化品牌校准：
  每店特征（仅 review_kind=diner，且店有效评论 n>=3 才判，小店不判=反误伤）：
    five_star_ratio  五星占比；no_substance_ratio 无实质/模板占比；burst_14d 14天最大聚集占比；
    near_dup_ratio   近重复文本占比；author_conc 头号作者占比；promo_ratio 营销词占比；low_trust_ratio 低可信/疑似营销号占比。
  分布学习：跨店每特征取 median + MAD 稳健分位阈值（阈值=稳健高分位 ∩ 保守底线）。
  校准：已知工业化品牌应高、专家必吃/值得应低；据此定 suspected/confirmed 切点；
        专家好店永不自动 confirmed（反误杀，最高优先）。
  写：PATCH restaurants.soft_ad_flag_reviews = none/suspected/confirmed（trigger 再与 chain 侧 greatest 合并）。
  连续分 astroturf_score 随 migration 021 落库（列未建前只写 flag）。

用法：python3 softad_distribution.py [--apply]
"""
import os, sys, json, argparse, collections, datetime, re
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
SOFT_DIR = os.path.join(OUT_DIR, "softad")
os.makedirs(SOFT_DIR, exist_ok=True)

PROMO_WORDS = ("团购", "代金券", "合作", "推广", "广告", "福利", "戳左下角", "购买链接",
               "招商", "加盟", "私信", "加v", "vx", "微信咨询", "预约请")
MIN_N = 5  # n=3 全五星对顶级店很正常，样本太少不判分布（反误伤）

# 已知工业化/预制品牌（用于校准正例；与 phase0c PREMADE_HIGH_BRANDS 对齐并扩充）
KNOWN_INDUSTRIAL = ["小菜园", "望湘园", "盖饭邦", "外婆家", "绿茶", "点都德", "南京大牌档",
                    "新旺", "东发道", "丸龟", "新白鹿", "费大厨", "鲜芋仙", "圆苑", "桂满陇",
                    "绿茶餐厅", "避风塘", "唐宫", "和府捞面", "杨国福", "张亮"]
WEIGHTS = {"near_dup": .26, "low_trust": .18, "burst": .16, "promo": .12,
           "no_substance": .12, "five_star": .08, "author_conc": .08}


def parse_date(s):
    s = (s or "")[:10]
    try:
        return datetime.date.fromisoformat(s)
    except Exception:
        return None


def rating_of(r):
    for k in ("aspect_taste", "rating_taste", "rating_total"):
        if r.get(k) is not None:
            try:
                return float(r[k])
            except Exception:
                pass
    return None


def substantive(text):
    if hasattr(C, "quote_has_substance"):
        try:
            return C.quote_has_substance(text or "")
        except Exception:
            pass
    t = (text or "").strip()
    han = "".join(ch for ch in t if "一" <= ch <= "鿿")
    return len(han) >= 8 or bool(re.search(r"(好吃|香|嫩|鲜|入味|正宗|地道|雷|柴|腥|咸|甜|脆)", t))


def norm_text(t):
    t = (t or "").lower()
    return re.sub(r"[\s\u3000（）()【】\[\]，,、。.·・•:：;；!！?？'‘’\"“”\-—_/\\&+0-9a-z]+", "", t)


def near_dup_ratio(texts):
    """n 条文本中，与另一条高度近重复（含字串包含/相似度≥.82）的占比。"""
    n = len(texts)
    if n < 2:
        return 0.0
    dup = [False] * n
    K = min(n, 60)
    for i in range(K):
        ai = texts[i]
        if len(ai) < 12:  # 短/模板文本不参与近重复判定
            continue
        for j in range(i + 1, K):
            aj = texts[j]
            if len(aj) < 12:
                continue
            if ai in aj or aj in ai:
                dup[i] = dup[j] = True; continue
            r = SequenceMatcher(None, ai, aj).ratio()
            if r >= 0.82:
                dup[i] = dup[j] = True
    return sum(dup) / n


def quantile(xs, q):
    xs = sorted(xs); n = len(xs)
    if n == 1:
        return xs[0]
    k = (n - 1) * q; lo = int(k); f = k - lo
    return xs[lo] * (1 - f) + xs[min(lo + 1, n - 1)] * f


def robust_stats(xs):
    med = quantile(xs, .5)
    mad = quantile([abs(x - med) for x in xs], .5)
    return med, mad


def store_features(reviews_for):
    feats = {}
    for rid, rr in reviews_for.items():
        n = len(rr)
        if n < MIN_N:
            feats[rid] = None; continue
        rates = [rating_of(r) for r in rr]
        rates_n = [x for x in rates if x is not None]
        five = (sum(1 for x in rates_n if x >= 4.5) / len(rates_n)) if rates_n else 0.0
        nosub = sum(0 if substantive(r.get("content")) else 1 for r in rr) / n
        promo = sum(1 if any(w in (r.get("content") or "") for w in PROMO_WORDS) else 0
                    for r in rr) / n
        lowtr = sum(1 if r.get("trust_level") == "low" or
                    (r.get("author_name") or "").lower() in ("官方", "商家") else 0
                    for r in rr) / n
        authors = [(r.get("author_name") or "?") for r in rr]
        ac = collections.Counter(authors)
        author_conc = max(ac.values()) / n
        # burst 只认【真实到店日期】，且需≥60%评论有真实日期，否则=0
        # （created_at 是我们同批抓取时间，会把正常店伪造成 burst）
        real = sorted(d for d in (parse_date(r.get("visit_date")) for r in rr) if d)
        burst = 0.0
        if len(real) >= max(3, int(0.6 * n)):
            for d in real:
                c = sum(1 for x in real if d <= x <= d + datetime.timedelta(days=14))
                burst = max(burst, c / n)
        texts = [norm_text(r.get("content")) for r in rr]
        nd = near_dup_ratio(texts)
        feats[rid] = {"five_star": five, "no_substance": nosub, "burst": burst,
                      "near_dup": nd, "author_conc": author_conc, "promo": promo,
                      "low_trust": lowtr, "n": n}
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all("restaurants", "id,name,status,chain_type,soft_ad_flag_reviews",
                        order_col="id")
    active = {r["id"]: r for r in rests if r["status"] == "active"}
    revs = C.fetch_all(
        "reviews",
        "id,restaurant_id,author_name,source_platform,trust_level,review_kind,is_fake_suspect,"
        "is_hidden,aspect_taste,rating_taste,rating_total,visit_date,created_at,content",
        order_col="id")
    reviews_for = collections.defaultdict(list)
    for r in revs:
        if r["review_kind"] != "diner" or r.get("is_fake_suspect") or r.get("is_hidden"):
            continue
        if r["restaurant_id"] in active:
            reviews_for[r["restaurant_id"]].append(r)

    feats = store_features(reviews_for)
    scorable = {rid: f for rid, f in feats.items() if f}

    # ---- 跨店稳健分布 + 阈值 ----
    keys = list(WEIGHTS)
    stats = {}
    for k in keys:
        xs = [f[k] for f in scorable.values()]
        med, mad = robust_stats(xs)
        q90 = quantile(xs, .90)
        thr = max(q90, med + 2.5 * 1.4826 * (mad + 1e-6))  # 稳健高分位 ∩ 保守底线
        stats[k] = {"median": round(med, 3), "mad": round(mad, 3), "threshold": round(thr, 3)}

    # 反误杀保护集：专家必吃/值得 + 有在期真实奖项的店，绝不自动 confirmed
    labels = C.fetch_all("diner_seed_labels", "restaurant_id,tier",
                         order_col="restaurant_id", extra="labeler=eq.expert")
    good_rids = {x["restaurant_id"] for x in labels if x["tier"] in ("must_eat", "worth_eating")}
    awrows = C.fetch_all("restaurant_awards", "restaurant_id,is_current", order_col="id")
    award_rids = {a["restaurant_id"] for a in awrows if a.get("is_current")}
    protected = good_rids | award_rids

    def score_of(f):
        s, strong = 0.0, 0
        for k in keys:
            t = stats[k]["threshold"]; med = stats[k]["median"]
            if f[k] > t:
                mag = min(2.0, (f[k] - t) / ((t - med) + 1e-6))
                s += WEIGHTS[k] * mag
                if mag >= 1.0:
                    strong += 1
        return round(min(1.0, s), 3), strong

    scored = {rid: score_of(f) for rid, f in scorable.items()}

    # 切点取分数分布稳健高分位（工业化品牌靠 std/pr/ck 硬信号识别，未必呈现刷评分布，不用来定界）
    all_scores = [v[0] for v in scored.values()]
    cut_sus = round(max(quantile(all_scores, .85), .5), 3)
    cut_conf = round(max(cut_sus + .18, .72), 3)

    verdicts, per_store = {}, {}
    for rid, f in scorable.items():
        sc, strong = scored[rid]
        # 只有“我们采集造不出来”的硬信号才能 confirmed：长文近重复 / 低可信营销号 / 营销词+异常
        hard_signal = (f["near_dup"] >= .34 or f["low_trust"] >= .5
                       or (f["promo"] >= .5 and (f["low_trust"] > 0 or f["author_conc"] > .6)))
        if sc >= cut_conf and strong >= 2 and hard_signal and rid not in protected:
            v = "confirmed"
        elif sc >= cut_sus or strong >= 2:
            v = "suspected"
            if rid in protected and not hard_signal:
                v = "none"  # 受保护店且无硬信号：不标
        else:
            v = "none"
        verdicts[str(rid)] = v
        per_store[rid] = {"score": sc, "strong": strong, "verdict": v, "n": f["n"]}

    # 未达 n 的店：不判，按 none（不覆盖可能已有的人工判定除外；这里只 PATCH 有判定变化的）
    baselines = {
        "run_date": datetime.date.today().isoformat(),
        "corpus": {"active": len(active), "reviews": len(revs),
                   "scorable_shops": len(scorable)},
        "feature_stats": stats,
        "weights": WEIGHTS,
        "cuts": {"suspected": cut_sus, "confirmed": cut_conf},
        "calibration": {"protected_shops": len(protected), "award_shops": len(award_rids),
                        "good_shops": len(good_rids)},
        "verdicts": verdicts,
    }
    bp = os.path.join(SOFT_DIR, "baselines.json")
    json.dump(baselines, open(bp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    vd = collections.Counter(verdicts.values())
    print(f"可判店 {len(scorable)}（n>={MIN_N}）；verdicts: {dict(vd)}")
    print(f"切点 suspected={cut_sus} confirmed={cut_conf}；"
          f"保护店 {len(protected)}（奖项{len(award_rids)}/好店{len(good_rids)}）")
    print("\n=== confirmed / suspected（前30）===")
    for rid, p in sorted(per_store.items(), key=lambda x: -x[1]["score"])[:30]:
        if p["verdict"] != "none":
            print(f"  id{rid:<6} {active[rid]['name'][:24]:<26} score={p['score']} "
                  f"strong={p['strong']} {p['verdict']}")
    print(f"\nbaselines -> {bp}")

    if not args.apply:
        print("[dry-run] 加 --apply 才 PATCH soft_ad_flag_reviews"); return

    # ---- apply：只 PATCH 判定发生变化的店 ----
    n = 0
    for rid, p in per_store.items():
        cur = active[rid].get("soft_ad_flag_reviews")
        if cur == p["verdict"]:
            continue
        r = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                  json={"soft_ad_flag_reviews": p["verdict"]})
        n += 1 if r.status_code in (200, 204) else 0
    print(f"[apply] PATCH soft_ad_flag_reviews {n} 店")


if __name__ == "__main__":
    main()

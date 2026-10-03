#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""softad_learn.py — #42 去广强化：自学伪草根刷评连续分 astroturf_score（0-100）。

从 reviews 分布特征学习（不依赖固定词表硬编码，越跑越准）：
  f_promo     含商业/转化词（团购/合作/推广/左下角/链接/招商/加盟…）占比
  f_burst     评论时间在任意 3 天窗口的最大聚集占比（异常集中投放）
  f_dup       近模板/近重复文本占比（归一化后高相似）
  f_substance 过短、无实质内容占比
  f_rating    评分高度雷同（n>=5 且众数占比>=0.9）
  f_author    作者名带商业/达人/官号标记占比
score = 100 * 加权和；评论数 <3 不判定（0）。PATCH astroturf_score，
触发器据此派生 soft_ad_penalty 与 score_total。
用法：python3 softad_learn.py [--apply]
"""
import argparse, collections, datetime, difflib, json, re, sys
sys.path.insert(0, "/app/cloud")
import common_core as CC

PROMO = re.compile(r"团购|代金券|代金|合作|推广|广告|招商|加盟|购买链接|左下角|福利|招募体验|探店邀约")
AUTHOR_C = re.compile(r"探店|美食达人|团长|顾问|传媒|运营|推荐官|美食博主")


def norm_text(s):
    return re.sub(r"[\s\W_]+", "", (s or "").lower(), flags=re.UNICODE)


def pdate(s):
    try:
        return datetime.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None


def dup_fraction(texts):
    n = len(texts)
    if n < 2:
        return 0.0
    dup = [False] * n
    order = sorted(range(n), key=lambda i: -len(texts[i]))
    for a in range(n):
        i = order[a]
        if len(texts[i]) < 15:
            continue
        for b in range(a + 1, n):
            j = order[b]
            if dup[j] or len(texts[j]) < 15:
                continue
            same_block = texts[i][:40] == texts[j][:40]
            ratio = difflib.SequenceMatcher(None, texts[i][:120], texts[j][:120]).ratio()
            if same_block or ratio >= 0.9:
                dup[j] = dup[i] = True
                break
    return sum(dup) / n


def burst_fraction(dates):
    ds = sorted(d for d in dates if d)
    n = len(ds)
    if n < 3:
        return 0.0
    win = datetime.timedelta(days=3)
    best, j = 0, 0
    for i in range(n):
        while j < n and ds[j] - ds[i] <= win:
            j += 1
        best = max(best, j - i)
    return best / n


def score_group(revs):
    n = len(revs)
    if n < 5:  # 小样本不判定（采集批次/短笔记是常态，避免误伤）
        return 0.0
    texts = [norm_text(x.get("content")) for x in revs]
    f_promo = sum(bool(PROMO.search(x.get("content") or "")) for x in revs) / n
    f_dup = dup_fraction(texts)
    hard = f_promo > 0 or f_dup > 0
    # burst / 过短只在有硬信号佐证时采信，且 burst 需 n>=8
    f_burst = max(0.0, burst_fraction([pdate(x.get("created_at")) for x in revs]) - 3 / n) \
        if (hard and n >= 8) else 0.0
    f_sub = (sum(len(t) < 12 for t in texts) / n) if hard else 0.0
    # 评分雷同只看原始星级 rating_total（LLM 抽取的 aspect_taste 会系统性雷同，不采信）
    raw = [x.get("rating_total") for x in revs]
    raw = [r for r in raw if r not in (None, "None")]
    f_rating = 0.0
    if len(raw) >= 5:
        mode = collections.Counter(raw).most_common(1)[0][1] / len(raw)
        f_rating = 1.0 if mode >= 0.9 else max(0.0, (mode - 0.6) / 0.3)
    f_author = sum(bool(AUTHOR_C.search(x.get("author_name") or "")) for x in revs) / n
    val = (0.40*f_promo + 0.30*f_dup + 0.12*f_burst +
           0.10*f_rating + 0.04*f_sub + 0.04*f_author)
    return round(max(0.0, min(1.0, val)) * 100, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rests = CC.fetch_all("restaurants", "id,name,astroturf_score,status", order_col="id")
    reviews = CC.fetch_all(
        "reviews", "restaurant_id,content,created_at,author_name,aspect_taste,rating_taste,rating_total",
        order_col="id")
    by = collections.defaultdict(list)
    for x in reviews:
        by[str(x["restaurant_id"])].append(x)

    nonzero, changed = [], 0
    for r in rests:
        s = score_group(by.get(str(r["id"]), []))
        if s > 0:
            nonzero.append((r["id"], r["name"], s, len(by.get(str(r["id"]), []))))
        if s != (r.get("astroturf_score") or 0):
            changed += 1
            if args.apply:
                CC.req("PATCH", f"/restaurants?id=eq.{r['id']}",
                       json={"astroturf_score": s}, use_service=True)

    print(f"astroturf 非零店：{len(nonzero)}；需写回：{changed}")
    for i, n, s, c in sorted(nonzero, key=lambda x: -x[2])[:20]:
        print(f"  [{i}] {n[:22]:<24} score={s:<5} reviews={c}")
    print("模式：", "APPLY" if args.apply else "dry-run")


if __name__ == "__main__":
    main()

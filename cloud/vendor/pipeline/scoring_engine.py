#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scoring_engine.py — 评分引擎：把真实食客评价确定性聚合为店铺口味分（012 对齐）

严格对齐 db/migrations/012_scoring_realign.sql，不另起公式：
  · 只采信真实食客堂食 UGC：review_kind='diner' AND is_fake_suspect!=true AND is_hidden=false
    AND trust_level IN ('mid','high') AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL；
  · 高德聚合(trust=low)、平台星、软广/模板评论一律不作口味证据（红线）；
  · 时间衰减 w = 0.5^((今天 - COALESCE(visit_date,created_at))/180)，q=(口味分-1)/4*100；
  · v_R = Σw·q/Σw（时间加权原始均值，= score_diner，不收缩）；
  · v_C = cuisine_prior(p)（同品叶子→父类→虚拟根，取首个 Σw≥20 否则最浅层；缺省 70）；
  · score_taste = 贝叶斯收缩 round( v/(v+8)·v_R + 8/(v+8)·v_C , 2)；
  · review_count = 有效评价条数；review_confidence = round(v/(v+8),3)；无证据则 taste/diner=NULL。
  · 独立作者数 nind = COUNT(DISTINCT author_name)（由 DB 触发器 derive_restaurant 据此定 verified/provisional）。

本脚本只 PATCH 组件输入（score_taste/score_diner/review_count/review_confidence）；
score_total / score_evidence_level / soft_ad_penalty 一律由 DB 触发器 trg_restaurants_derive
在 UPDATE 时 blend，脚本不手填。服务/环境/个人情绪方面不进口味；证据不足 taste 置空（宁空不假）。

用法：
  python3 scoring_engine.py            # dry-run：打印前后分布 + 逐店 before→after 变更清单，不写库
  python3 scoring_engine.py --apply   # 仅对“需要变更”的行 PATCH 组件分（幂等，复跑 0 变更）
"""
import argparse
import collections
import datetime
import json
import sys

import common as C

HALF_LIFE = 180.0
M = 8.0  # 贝叶斯先验强度（012：m=8）
REF_DATE = datetime.date.today()  # 与 SQL CURRENT_DATE 对齐


def taste_val(r):
    for k in ("aspect_taste", "rating_taste", "rating_total"):
        if r.get(k) is not None:
            return float(r[k])
    return None


def load_all():
    revs = C.fetch_all(
        "reviews",
        "id,restaurant_id,author_name,review_kind,is_fake_suspect,is_hidden,"
        "trust_level,aspect_taste,rating_taste,rating_total,visit_date,created_at",
        order_col="id")
    rs = C.fetch_all(
        "restaurants",
        "id,name,status,score_taste,score_diner,score_objective,score_endorsement,"
        "soft_ad_penalty,score_evidence_level,score_total,review_count,review_confidence",
        order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id,is_primary",
                     order_col="restaurant_id")
    cu = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    return revs, rs, rc, cu


def compute(revs, rs, rc, cu):
    cu_by_id = {c["id"]: c for c in cu}
    cui_by_name = {c["name"]: c for c in cu if c["dimension"] == "菜系"}

    eff = []
    for r in revs:
        if r["review_kind"] != "diner":
            continue
        if r["is_fake_suspect"] or r["is_hidden"]:
            continue
        if r["trust_level"] not in ("mid", "high"):  # 红线：trust low 不作口味证据
            continue
        v = taste_val(r)
        if v is None:
            continue
        dt = r.get("visit_date") or (r.get("created_at") or "")[:10]
        try:
            d = datetime.date.fromisoformat(dt)
        except Exception:
            d = REF_DATE
        w = 0.5 ** ((REF_DATE - d).days / HALF_LIFE)
        eff.append({"rid": r["restaurant_id"], "author": r.get("author_name") or "",
                    "w": w, "q": (v - 1) / 4.0 * 100.0})

    per = collections.defaultdict(list)
    for e in eff:
        per[e["rid"]].append(e)

    res_cui = collections.defaultdict(list)
    for link in rc:
        c = cu_by_id.get(link["cuisine_id"])
        if c and c["dimension"] == "菜系":
            res_cui[link["restaurant_id"]].append((link["cuisine_id"],
                                                   bool(link.get("is_primary"))))

    tag_sum = collections.defaultdict(lambda: [0.0, 0.0])   # cuisine_id -> [Σwq, Σw]
    parent_sum = collections.defaultdict(lambda: [0.0, 0.0])  # parent_category lvl -> [Σwq, Σw]
    for e in eff:
        for (cid, _prim) in res_cui.get(e["rid"], []):
            tag_sum[cid][0] += e["w"] * e["q"]
            tag_sum[cid][1] += e["w"]
    for c in cu:
        if c["dimension"] == "菜系" and c["parent_category"]:
            t = tag_sum.get(c["id"])
            if t:
                parent_sum[c["parent_category"]][0] += t[0]
                parent_sum[c["parent_category"]][1] += t[1]

    def cuisine_prior(rid):
        tags = res_cui.get(rid)
        if not tags:
            return 70.0
        leaf = sorted(tags, key=lambda x: (not x[1], x[0]))[0][0]
        levels = []
        depth = 1
        cid, lvl, par = leaf, cu_by_id[leaf]["name"], cu_by_id[leaf]["parent_category"]
        while True:
            levels.append((cid, lvl, depth))
            if par is None:
                break
            prow = cui_by_name.get(par)
            npar = prow["parent_category"] if prow else None
            cid, lvl, par, depth = None, par, npar, depth + 1
        scored = []
        for (cid, lvl, depth) in levels:
            wq, w = (tag_sum.get(cid, [0.0, 0.0]) if cid is not None
                     else parent_sum.get(lvl, [0.0, 0.0]))
            scored.append((depth, (wq / w) if w > 0 else 70.0, w))
        # 先取 Σw>=20 的最浅层；否则最浅层
        scored.sort(key=lambda x: (1 if x[2] >= 20 else 0, -x[0]), reverse=True)
        return scored[0][1]

    clamp = lambda x: max(0.0, min(100.0, x))  # noqa: E731
    pred = {}
    for r in rs:
        rid = r["id"]
        ev = per.get(rid, [])
        sw = sum(e["w"] for e in ev)
        swq = sum(e["w"] * e["q"] for e in ev)
        nind = len(set(e["author"] for e in ev))
        if sw > 0:
            v_R = swq / sw
            v_C = cuisine_prior(rid)
            taste = round(sw / (sw + M) * v_R + M / (sw + M) * v_C, 2)
            diner = round(v_R, 2)
            conf = round(sw / (sw + M), 3)
            cnt = len(ev)
        else:
            taste = diner = None
            conf, cnt = 0, 0
        obj, end, pen = r["score_objective"], r["score_endorsement"], r["soft_ad_penalty"] or 0
        # 以下为 DB 触发器 derive_restaurant 的 blend 复算（仅用于 dry-run 预测与校验，不写库）
        if taste is not None and diner is not None:
            blend = (0.45 * taste + 0.25 * diner
                     + 0.18 * (obj if obj is not None else taste)
                     + 0.12 * (end if end is not None else 0))
            if nind >= 2:
                evl, tot = "verified", round(clamp(blend - pen), 1)
            else:
                evl, tot = "provisional", round(clamp(min(blend, 82) - pen), 1)
        elif (obj and obj > 0) or (end and end > 0):
            blend = 0.6 * (obj or 0) + 0.4 * (end or 0)
            evl, tot = "provisional", round(clamp(min(blend, 70) - pen), 1)
        else:
            evl, tot = "insufficient", None
        pred[rid] = {"taste": taste, "diner": diner, "count": cnt, "conf": conf,
                     "nind": nind, "evidence": evl, "total": tot}
    return pred, len(eff)


def near(a, b, tol):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="仅对需要变更的行 PATCH 组件分（默认 dry-run）")
    args = ap.parse_args()

    revs, rs, rc, cu = load_all()
    pred, eff_n = compute(revs, rs, rc, cu)

    def dist(rows, key):
        return dict(collections.Counter(r.get(key) for r in rows))

    before_ev = dist(rs, "score_evidence_level")
    after_ev = collections.Counter(p["evidence"] for p in pred.values())
    before_taste_n = sum(1 for r in rs if r["score_taste"] is not None)
    after_taste_n = sum(1 for p in pred.values() if p["taste"] is not None)
    before_tot = [float(r["score_total"]) for r in rs if r["score_total"] is not None]
    after_tot = [p["total"] for p in pred.values() if p["total"] is not None]

    # 需要 PATCH 的行（仅组件分，触发器会据此重算 total/evidence/penalty）
    changed = []
    for r in rs:
        rid = r["id"]
        p = pred[rid]
        fields = {}
        if not near(r["score_taste"], p["taste"], 0.011):
            fields["score_taste"] = p["taste"]
        if not near(r["score_diner"], p["diner"], 0.011):
            fields["score_diner"] = p["diner"]
        if (r["review_count"] or 0) != p["count"]:
            fields["review_count"] = p["count"]
        if not near(r["review_confidence"] or 0, p["conf"], 0.0011):
            fields["review_confidence"] = p["conf"]
        if fields:
            changed.append((rid, r["name"], fields))

    print(f"参与重算餐厅数: {len(rs)}（有效口味证据行 {eff_n}，仅 trust mid/high 真实 UGC）")
    print(f"score_taste 非空: {before_taste_n} -> {after_taste_n}")
    print(f"score_evidence_level 分布 before: {before_ev}")
    print(f"score_evidence_level 分布 after : {dict(after_ev)}")
    print(f"score_total before: n={len(before_tot)} min={min(before_tot):.1f} "
          f"max={max(before_tot):.1f} avg={sum(before_tot)/len(before_tot):.2f}")
    print(f"score_total after : n={len(after_tot)} min={min(after_tot):.1f} "
          f"max={max(after_tot):.1f} avg={sum(after_tot)/len(after_tot):.2f}")
    verified_after = after_ev.get("verified", 0)
    print(f"verified 数 after: {verified_after}")
    print(f"需要变更的行: {len(changed)}（仅 PATCH 组件分；其余行幂等无变化）")
    for rid, name, f in changed[:80]:
        print(f"  id{rid:<6} {str(name)[:20]:<22} {f}")

    if not args.apply:
        print("\n[dry-run] 未写库。加 --apply 才 PATCH 上述组件分。")
        return

    # ---- apply：逐行 PATCH 组件分（2 并发由 requests 顺序 + 退避；runbook 要求逐行 PATCH）----
    ok = 0
    for rid, name, f in changed:
        resp = C.req("PATCH", f"/restaurants?id=eq.{rid}", use_service=True, json=f)
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] id{rid}: {resp.status_code} {resp.text[:200]}")
            continue
        ok += 1
    print(f"\n[apply] PATCH 完成 {ok}/{len(changed)} 行；触发器已 blend score_total/evidence_level/penalty。")


if __name__ == "__main__":
    main()

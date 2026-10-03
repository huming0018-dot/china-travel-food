#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""platform_score.py — 平台评分柱 + 背书柱（确定性、可追溯、可复采）。

职责（对齐 db/migrations/027_platform_rating_pillar.sql）：
  1) --ingest-amap <amap_poi_cache.jsonl>：把高德门店聚合星级原始值 upsert 进 platform_ratings；
  2) 校准：平台星级明显通胀（高德多在 4.5–4.7），按平台分段线性映射去通胀 → 0–100；
     多平台按评论数可信度加权合并；
  3) 背书柱 score_endorsement 严格按 restaurant_awards 重算（非奖项一律 0），清洗历史污染；
  4) --apply 才 PATCH score_platform / score_endorsement；默认 dry-run。

只 PATCH score_platform / score_endorsement 两列；score_total 由触发器 derive_restaurant blend。
宁空不假：无原始评分则 score_platform 置 NULL。

用法：
  python3 platform_score.py --ingest-amap /app/data/amap_poi_cache.jsonl
  python3 platform_score.py            # dry-run
  python3 platform_score.py --apply
"""
import argparse
import json

import requests
import common_core as CC

# 平台原始星级 -> 0..100 分段锚点（去通胀；按观测分布，高德中位≈4.6）
CAL = {
    "amap":     [(3.0, 30), (3.5, 42), (3.8, 50), (4.0, 56), (4.2, 63), (4.3, 67),
                 (4.4, 71), (4.5, 75), (4.6, 80), (4.7, 86), (4.8, 91), (4.9, 96), (5.0, 99)],
    "dianping": [(3.0, 35), (3.5, 48), (3.8, 56), (4.0, 62), (4.2, 69), (4.3, 73),
                 (4.4, 78), (4.5, 83), (4.6, 88), (4.7, 92), (4.8, 95), (5.0, 99)],
}
DEFAULT_CAL = "amap"

# 奖项 -> 背书分（取最高）
ENDORSE = {
    "michelin_star": {"3": 98, "2": 92, "1": 85},
    "black_pearl":   {"3": 92, "2": 85, "1": 78},
    "bib_gourmand":  None,   # 必比登统一 72
    "other_list":    None,   # 米其林入选统一 65
}
BIB_SCORE, SELECTED_SCORE = 72, 65


def interp(anchors, x):
    pts = sorted(anchors)
    if x <= pts[0][0]:
        return float(pts[0][1])
    if x >= pts[-1][0]:
        return float(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


def calibrate(platform, rating):
    return interp(CAL.get(platform, CAL[DEFAULT_CAL]), float(rating))


def credibility(review_count):
    """评论数可信度权重 0..1；无计数给保守 0.5。"""
    if not review_count:
        return 0.5
    n = float(review_count)
    return n / (n + 200.0)


def ingest_amap(path):
    """从 amap_poi_cache 读原始星级，upsert platform_ratings。"""
    valid = {r["id"] for r in CC.fetch_all("restaurants", "id", order_col="id")}
    rows = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        rid = d["rid"]
        if rid not in valid:
            continue  # 已删除/不存在的 rid，FK 不允许
        p = d.get("poi") or {}
        if p.get("rating") is None:
            continue
        # 同 rid 保留最新抓取
        if rid not in rows or (d.get("date") or "") >= rows[rid]["captured_at"]:
            rows[rid] = {
                "restaurant_id": rid, "platform": "amap",
                "rating": float(p["rating"]), "review_count": None,
                "source_url": None,
                "captured_at": d.get("date") or None,
            }
    payload = [r for r in rows.values() if r["captured_at"]]
    # upsert（PK restaurant_id,platform,captured_at），用 Prefer merge-duplicates
    h = CC.headers(True)
    h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    resp = requests.post(CC._supabase_base() + "/platform_ratings",
                         headers=h, json=payload, timeout=60)
    print(f"[ingest-amap] 原始评分 {len(payload)} 行 -> {resp.status_code}")
    if resp.status_code not in (200, 201, 204):
        print("   ", resp.text[:300])


def norm_level(level):
    t = (level or "").strip()
    for ch in t:
        if ch.isdigit():
            return ch
    table = {"一": "1", "二": "2", "三": "3"}
    for k, v in table.items():
        if k in t:
            return v
    return None


def endorsement_from_awards():
    awards = CC.fetch_all(
        "restaurant_awards",
        "restaurant_id,award_type,level,is_current", order_col="id")
    best = {}
    for a in awards:
        if a.get("is_current") is False:
            continue
        at, lvl = a.get("award_type"), norm_level(a.get("level"))
        s = None
        if at in ("michelin_star", "black_pearl") and lvl:
            s = ENDORSE[at][lvl]
        elif at == "bib_gourmand":
            s = BIB_SCORE
        elif at == "other_list":
            s = SELECTED_SCORE
        if s is not None:
            rid = a["restaurant_id"]
            best[rid] = max(best.get(rid, 0), s)
    return best


def platform_scores():
    """读 platform_ratings，按平台校准并按可信度加权合并到每店。"""
    prs = CC.fetch_all(
        "platform_ratings",
        "restaurant_id,platform,rating,review_count,captured_at",
        order_col="restaurant_id")
    per = {}
    for r in prs:
        rid = r["restaurant_id"]
        cal = calibrate(r["platform"], r["rating"])
        w = credibility(r.get("review_count"))
        # 同店同平台取最新：保留 captured_at 最大
        cur = per.setdefault(rid, {}).get(r["platform"])
        if cur is None or (r.get("captured_at") or "") > cur[2]:
            per[rid][r["platform"]] = (cal, w, r.get("captured_at") or "")
    out = {}
    for rid, plats in per.items():
        num = sum(cal * w for cal, w, _ in plats.values())
        den = sum(w for _, w, _ in plats.values())
        out[rid] = round(num / den, 1) if den > 0 else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest-amap", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.ingest_amap:
        ingest_amap(args.ingest_amap)

    pscore = platform_scores()
    escore = endorsement_from_awards()

    rests = CC.fetch_all("restaurants", "id,name,score_platform,score_endorsement",
                         order_col="id")
    changes = []
    for r in rests:
        rid = r["id"]
        np_, ne = pscore.get(rid), escore.get(rid)
        f = {}
        cur_p = float(r["score_platform"]) if r.get("score_platform") is not None else None
        cur_e = float(r["score_endorsement"]) if r.get("score_endorsement") is not None else 0
        if np_ is not None and (cur_p is None or abs(cur_p - np_) > 0.05):
            f["score_platform"] = np_
        elif np_ is None and cur_p is not None:
            f["score_platform"] = None
        want_e = ne or 0
        if abs(cur_e - want_e) > 0.05:
            f["score_endorsement"] = want_e
        if f:
            changes.append((rid, r["name"], f))

    print(f"score_platform 覆盖: {len(pscore)} 店；score_endorsement>0: {len(escore)} 店（应≈奖项店数）")
    print(f"需 PATCH 行: {len(changes)}")
    for rid, name, f in changes[:20]:
        print(f"  id{rid:<5} {str(name)[:20]:<22} {f}")
    if not args.apply:
        print("\n[dry-run] 未写库；加 --apply PATCH，触发器 blend score_total。")
        return
    ok = 0
    for rid, name, f in changes:
        resp = CC.req("PATCH", f"/restaurants?id=eq.{rid}", use_service=True, json=f)
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] id{rid}: {resp.status_code} {resp.text[:200]}")
            continue
        ok += 1
    print(f"\n[apply] PATCH {ok}/{len(changes)}；触发器已按 v6 blend。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_split_apply.py — 把连锁聚合行拆成各分店独立记录（确定性、幂等、可重跑）。

数据来源：chain_branches.json（腾讯 search，地址/坐标/电话为 POI 事实）+ Gregorius 内联。
规则：
- 现有聚合行（1690/1719/1720）"认领"为坐标与其当前坐标最近的分店（改名/地址/电话/坐标）。
- 其余分店 POST 新建：继承品牌的评分、招牌菜、标签关联（同品牌标准化，口味见品牌评分）。
- 坐标写 EWKT；新建前查同名避免重复；写后回读。默认 dry-run。
"""
import argparse
import json
import pathlib
import re
import sys
import time
from math import asin, cos, radians, sin, sqrt

SKILL = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL)
import common as C  # noqa: E402

AGG_IDS = {"Gregorius": 1690, "有喜屋": 1719, "烤匠": 1720}

# Gregorius 首次采集撞额度，内联（来自腾讯 search 2026-09-23）
GREG = [
    {"title": "Gregorius航迹(愚园路店)",
     "address": "上海市长宁区愚园路991号(江苏路地铁站6号口步行120米)", "tel": "",
     "lng": 121.430433, "lat": 31.218895},
    {"title": "Gregorius SHADE(安福路店)",
     "address": "上海市徐汇区安福路53号(常熟路地铁站8号口步行300米)", "tel": "",
     "lng": 121.447036, "lat": 31.214779},
]


def meters(a, b):
    R = 6371000
    dlat = radians(b[0] - a[0]); dlng = radians(b[1] - a[1])
    x = sin(dlat / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlng / 2) ** 2
    return 2 * R * asin(sqrt(x))


def district_of(addr):
    m = re.search(r"([一-龥]{2,4}?区)", str(addr))
    return m.group(1) if m else None


def dedup(rows):
    """坐标 <80m 视为同店（同商场/同址重复 POI）。"""
    out = []
    for r in rows:
        if not r.get("lat") or not r.get("lng"):
            continue
        if any(meters((r["lat"], r["lng"]), (o["lat"], o["lng"])) < 80 for o in out):
            continue
        out.append(dict(r))
    return out


def load_branches():
    cb = json.load(open(pathlib.Path(__file__).parent / "chain_branches.json"))
    return {
        "Gregorius": dedup(GREG),
        "有喜屋": dedup(cb["有喜屋"]),
        "烤匠": dedup(cb["烤匠"]),
    }


def scores_from(agg):
    keys = ["score_objective", "score_diner", "score_taste", "score_endorsement"]
    vals = {k: agg.get(k) for k in keys}
    if any(v is None for v in vals.values()):
        return {}  # 四项要么全有要么全空（DB CHECK）
    return vals


def new_body(b, agg):
    f = {
        "name": b["title"],
        "address": b["address"],
        "district": district_of(b["address"]),
        "phone": (b.get("tel") or "").strip() or None,
        "price_avg": agg.get("price_avg"),
        "signature_dishes": agg.get("signature_dishes"),
        "soft_ad_penalty": agg.get("soft_ad_penalty"),
        "chain_type": agg.get("chain_type"),
        "central_kitchen": agg.get("central_kitchen"),
        "premade_risk": agg.get("premade_risk"),
        "status": "active",
        "data_updated_at": "2026-09-23",
        "evidence_summary": (
            f"【连锁分店】属「{agg['name']}」品牌；地址/坐标/电话事实来源：腾讯位置服务POI"
            f"（2026-09-23核验在营）。出品与口味标准化、同品牌，口味参见品牌评分。"
        ),
        "location": C.point_ewkt(b["lng"], b["lat"]),
    }
    f.update(scores_from(agg))
    return {k: v for k, v in f.items() if v is not None}


def existing_id(name):
    r = C.req("GET", "/restaurants", params={"select": "id", "name": f"eq.{name}"})
    rows = r.json()
    return rows[0]["id"] if rows else None


def build_plan():
    branches = load_branches()
    plan = []
    for brand, agg_id in AGG_IDS.items():
        agg = C.req("GET", f"/restaurants?id=eq.{agg_id}&select=*").json()[0]
        cids = sorted(x["cuisine_id"] for x in C.req(
            "GET", f"/restaurant_cuisines?select=cuisine_id&restaurant_id=eq.{agg_id}").json())
        # 全品牌近坐标查重：库中已有该品牌（含异写/早期收录，如烤匠rid1443）且 <120m 视为已存在
        exist_pts = []
        for e in C.req("GET", "/restaurants", params={
                "select": "id,location", "name": f"ilike.*{brand}*"}).json():
            _p = C.parse_location(e.get("location"))
            if _p:
                exist_pts.append((_p[1], _p[0]))  # (lat,lng)，与分店坐标顺序一致
        bl = branches[brand]
        _ll = C.parse_location(agg.get("location"))  # (lng, lat)
        agg_pos = (_ll[1], _ll[0]) if _ll else None  # → (lat, lng)，与分店坐标顺序一致
        anchor, rest = None, []
        if agg_pos:
            cand = sorted(bl, key=lambda b: meters(agg_pos, (b["lat"], b["lng"])))
            if cand and meters(agg_pos, (cand[0]["lat"], cand[0]["lng"])) < 150:
                anchor = cand[0]
        if anchor is None:
            anchor = bl[0]
        rest = [b for b in bl if b is not anchor]
        # 过滤已存在（幂等重跑）：精确店名 或 全品牌近坐标 <120m
        new_rows = []
        for b in rest:
            bp = (b["lat"], b["lng"])
            if existing_id(b["title"]) or any(meters(bp, ep) < 120 for ep in exist_pts):
                continue
            new_rows.append(b)
            time.sleep(0.05)
        plan.append({"brand": brand, "agg_id": agg_id, "agg": agg, "cids": cids,
                     "anchor": anchor, "new_rows": new_rows})
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    plan = build_plan()

    total_new = sum(len(p["new_rows"]) for p in plan)
    for p in plan:
        print(f"\n=== {p['brand']}（聚合行 {p['agg_id']}，标签 {p['cids']}）===")
        print(f"  认领→ {p['anchor']['title']} | {p['anchor']['address']}")
        for b in p["new_rows"]:
            print(f"  新建→ {b['title']} | {b['address']} | tel={b.get('tel') or '—'}")
    print(f"\n汇总：认领改名 3 家，新建 {total_new} 家。")

    if not args.commit:
        print("DRY-RUN，未写库；确认后加 --commit。")
        return

    for p in plan:
        agg_id, cids = p["agg_id"], p["cids"]
        a = p["anchor"]
        patch = {
            "name": a["title"], "address": a["address"],
            "district": district_of(a["address"]),
            "phone": (a.get("tel") or "").strip() or None,
            "location": C.point_ewkt(a["lng"], a["lat"]),
        }
        r = C.req("PATCH", f"/restaurants?id=eq.{agg_id}", json={k: v for k, v in patch.items() if v is not None})
        print(f"✓ 认领 {p['brand']}: PATCH {r.status_code} → {a['title']}")
        for b in p["new_rows"]:
            body = new_body(b, p["agg"])
            pr = C.req("POST", "/restaurants", params={"select": "id"}, json=body)
            rid = None
            if pr.status_code in (200, 201):
                try:
                    j = pr.json()
                    if j:
                        rid = j[0]["id"] if isinstance(j, list) else j["id"]
                except ValueError:
                    rid = None  # PostgREST 未回 body（缺 Prefer），改为回查
            if rid is None and pr.status_code in (200, 201, 204):
                time.sleep(0.3)
                got = C.req("GET", "/restaurants", params={
                    "name": f"eq.{b['title']}", "address": f"eq.{b['address']}",
                    "select": "id", "order": "id.desc", "limit": "1"}).json()
                if got:
                    rid = got[0]["id"]
            if rid is None:
                print(f"  ✗ 新建失败 {b['title']}: status={pr.status_code} {pr.text[:140]}"); continue
            for cid in cids:
                C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": cid})
            time.sleep(0.12)
            rb = C.parse_location(C.req("GET", f"/restaurants?id=eq.{rid}&select=location").json()[0].get("location"))
            print(f"  ✓ 新建 rid={rid} {b['title']} 标签+{len(cids)} 回读={rb}")
    print("\n完成。")


if __name__ == "__main__":
    main()

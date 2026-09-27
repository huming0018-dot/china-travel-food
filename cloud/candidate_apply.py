#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidate_apply.py — 把 admission_gate 裁决为 admit/admit* 的【库外新店】自动收录。

闭环位置：
  discovery_engine（发现）→ admission_gate（离线裁决 candidates_<cat>.jsonl）→ **本模块（收录）**

对每条 verdict ∈ {admit, admit*} 且 in_db=false 的品牌：
  1. 高德 place/text 按店名找餐饮 POI（无库地址，靠店名 + 餐饮语义，宁可不收也不锁错店）；
  2. 锁定唯一且高分的 POI（多店接近 → AMBIG，转 hold 等人工/补证）；
  3. 组装 restaurants 字段（地址/区/电话/坐标/人均/营业时间，全部宁空不假），POST 入库；
  4. 按品类挂菜系根标签（restaurant_cuisines）。
hold/reject 不入库。默认 dry-run，--commit 才写。

幂等：插入前按 name+address 回查，已存在则跳过；可重复运行。
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
from difflib import SequenceMatcher

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C          # noqa: E402
import cloud_amap_fill as AF  # noqa: E402
import discovery_keywords as K  # noqa: E402

DISC_DIR = pathlib.Path(DATA) / "discovery"


def parse_district(addr):
    for d in C.DISTRICTS:
        if d in (addr or ""):
            return d
    return None


def pick_new_poi(cands, brand):
    """无库地址，按店名 + 餐饮语义锁定唯一 POI。返回 poi / None / 'AMBIG'。"""
    dining = [c for c in cands if AF.is_dining_poi(c)]
    if not dining:
        return None
    main, _ = AF.split_name(brand)
    bn = AF.core_norm(main)
    scored = []
    for c in dining:
        cm, _ = AF.split_name(c.get("title", ""))
        cn = AF.core_norm(cm)
        if not bn or not cn:
            continue
        ratio = SequenceMatcher(None, bn, cn).ratio()
        if bn in cn or cn in bn:
            ratio = max(ratio, 0.92)
        scored.append((ratio, c))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return None
    top, poi = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if top < 0.6:
        return None
    # 多店高分且拉不开差距、又不是包含铁证 → 歧义，不锁
    if len(scored) > 1 and (top - second) < 0.12 and top < 0.9:
        return "AMBIG"
    return poi


def build_fields(brand, poi):
    fields, notes = {"name": brand, "status": "active"}, []
    if poi.get("address"):
        fields["address"] = poi["address"]
    d = parse_district(poi.get("address"))
    if d:
        fields["district"] = d
    if poi.get("tel"):
        clean, _iss, _n = C.clean_phone(poi["tel"])
        if clean:
            fields["phone"] = clean
    if poi.get("lng") is not None and poi.get("lat") is not None:
        if C.in_shanghai(poi["lng"], poi["lat"]):
            fields["location"] = C.point_ewkt(poi["lng"], poi["lat"])
    if poi.get("cost"):
        fields["price_avg"] = int(poi["cost"])
    if poi.get("hours"):
        fields["opening_hours"] = {"raw": poi["hours"]}
    return fields


def already_exists(brand, address):
    q = f"/restaurants?name=eq.{requests_q(brand)}&select=id,address"
    rows = C.req("GET", q).json()
    if not rows:
        return None
    if address:
        same = [r for r in rows if C.addr_core(r.get("address")) == C.addr_core(address)]
        if same:
            return same[0]["id"]
    return rows[0]["id"] if len(rows) == 1 else None


def requests_q(s):
    import requests
    return requests.utils.quote(s)


def insert_restaurant(fields):
    h = dict(C.headers())
    h["Prefer"] = "return=representation"
    r = __import__("requests").post(C.BASE + "/restaurants", headers=h,
                                   json=fields, timeout=45)
    if r.status_code not in (200, 201) or not r.json():
        return None, f"POST {r.status_code}: {r.text[:160]}"
    return r.json()[0]["id"], None


def tag_cuisine(rid, cuisine_id):
    r = __import__("requests").post(
        C.BASE + "/restaurant_cuisines", headers=C.headers(),
        json={"restaurant_id": rid, "cuisine_id": cuisine_id}, timeout=30)
    return r.status_code in (200, 201) or "23505" in r.text


def load_cuisine_ids():
    rows = C.fetch_all("cuisines", "id,name", order_col="id")
    return {r["name"]: r["id"] for r in rows}


def candidate_files(category):
    if category:
        f = DISC_DIR / f"candidates_{category}.jsonl"
        return [f] if f.exists() else []
    return sorted(DISC_DIR.glob("candidates_*.jsonl"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    args = ap.parse_args()

    if not AF.AMAP_KEY:
        print("AMAP_KEY 未配置，候选收录跳过。")
        return
    cuisine_ids = load_cuisine_ids()

    stats = {"admit_new": 0, "inserted": 0, "tagged": 0, "ambig": 0,
             "no_poi": 0, "exists": 0, "errors": 0}
    for cf in candidate_files(args.category):
        cat = cf.name.replace("candidates_", "").replace(".jsonl", "")
        root_name = K.CUISINE_ROOT.get(cat)
        tag_id = cuisine_ids.get(root_name) if root_name else None
        for line in cf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            p = json.loads(line)
            if not p.get("verdict", "").startswith("admit") or p.get("in_db"):
                continue
            if stats["admit_new"] >= args.limit:
                break
            stats["admit_new"] += 1
            brand = p["brand"]
            ok, why = C.looks_like_brand(brand)
            if not ok:
                stats["no_poi"] += 1
                print(f"  [非店名·跳] {brand} ({why})")
                continue
            cands = AF.amap_text(brand)
            if cands == "QUOTA":
                print("  高德配额耗尽，停止。")
                break
            poi = pick_new_poi(cands, brand)
            if poi == "AMBIG":
                stats["ambig"] += 1
                print(f"  [歧义·hold] {brand}")
                continue
            if not poi:
                stats["no_poi"] += 1
                print(f"  [无POI] {brand}")
                continue
            fields = build_fields(brand, poi)
            ex = already_exists(brand, fields.get("address"))
            if ex:
                stats["exists"] += 1
                continue
            print(f"  [{'COMMIT' if args.commit else 'DRY'}] {brand} → "
                  f"{fields.get('address','')[:34]} 标签={root_name}")
            if args.commit:
                rid, err = insert_restaurant(fields)
                if not rid:
                    stats["errors"] += 1
                    print("    ", err)
                    continue
                stats["inserted"] += 1
                if tag_id and tag_cuisine(rid, tag_id):
                    stats["tagged"] += 1
                time.sleep(0.4)
    print("\n=== 候选收录统计 ===")
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    if not args.commit:
        print("dry-run，确认后加 --commit。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 scene 坐标结果写库：校正 rid、跳过已删/closed，PATCH restaurants.location(EWKT) 并回读。
默认 dry-run；--commit 真正写入。"""
import argparse, json, pathlib, sys, time

SKILL = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL)
import common as C  # noqa

HERE = pathlib.Path(__file__).parent
RESULT = HERE / "scene_coords_result.json"
RID_FIX = {1706: 1350}  # Nono's 真实库 id（stage3 实为 update 1350）


def build():
    d = json.load(open(RESULT))
    rests = C.fetch_all("restaurants", "id,name,status", order_col="id")
    live = {r["id"]: r for r in rests}
    final, skipped = [], []
    seen = set()
    for r in d:
        if r["status"] not in ("ok", "ok_fallback"):
            skipped.append((r["rid"], r["name"], r["status"])); continue
        rid = RID_FIX.get(r["rid"], r["rid"])
        if rid not in live:
            skipped.append((rid, r["name"], "已删")); continue
        if live[rid]["status"] != "active":
            skipped.append((rid, r["name"], "closed")); continue
        if rid in seen:
            skipped.append((rid, r["name"], "重复")); continue
        seen.add(rid)
        final.append((rid, r))
    return final, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    final, skipped = build()
    print(f"将写坐标 {len(final)} 家；跳过 {len(skipped)}：{skipped}")
    if not args.commit:
        for rid, r in final:
            print(f"  rid={rid} {r['name']} ({r['status']}) {r['lng']},{r['lat']}")
        print("\n确认后加 --commit")
        return
    ok = 0
    for rid, r in final:
        ewkt = C.point_ewkt(r["lng"], r["lat"])
        resp = C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"location": ewkt})
        time.sleep(0.12)
        rb = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name,location")
        parsed = C.parse_location(rb.json()[0].get("location")) if rb.json() else None
        good = parsed is not None and abs(parsed[0] - r["lng"]) < 0.01
        ok += good
        print(f"{'✓' if good else '✗'} rid={rid} {r['name']} PATCH={resp.status_code} 回读={parsed}")
    print(f"\n成功 {ok}/{len(final)}")


if __name__ == "__main__":
    main()

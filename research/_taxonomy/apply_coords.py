#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 missing_coords_result.json 中 ok/ok_fallback 的坐标写库并逐条回读。"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).parent
PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, PIPE)
import common as C  # noqa: E402

res = json.load(open(HERE / "missing_coords_result.json"))
applied, still = [], []
for r in res:
    rid = r["rid"]
    if r.get("status") in ("ok", "ok_fallback") and r.get("lat"):
        ewkt = C.point_ewkt(r["lng"], r["lat"])
        resp = C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"location": ewkt})
        okpatch = resp.status_code in (200, 204)
        rb = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name,location").json()
        loc = C.parse_location(rb[0]["location"]) if rb else None
        verified = bool(loc) and C.in_shanghai(*loc)
        applied.append((rid, r["name"], okpatch, verified))
        print(f"{'✓' if verified else '✗'} rid {rid} {r['name']} patch={okpatch} verified={verified}")
        time.sleep(0.12)
    else:
        still.append(r)

print(f"\n写库 {len(applied)}，回读通过 {sum(1 for a in applied if a[3])}")
for a in applied:
    if not a[3]:
        print("  未通过:", a)
json.dump(still, open(HERE / "still_missing.json", "w"), ensure_ascii=False, indent=2)
print("仍缺坐标:", [(r["rid"], r["name"], r["status"]) for r in still])

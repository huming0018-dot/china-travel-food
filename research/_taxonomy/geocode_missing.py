#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对当前生产库所有 active 且无坐标的店批量补坐标（复用 geocode_scene 的 SK 签名 + 多源匹配）。
只产出 missing_coords_result.json，不写库。"""
import json
import pathlib
import sys
import time
from collections import Counter

HERE = pathlib.Path(__file__).parent
STAGE2 = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research/scene/_stage2"
PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, STAGE2)
sys.path.insert(0, PIPE)
import geocode_scene as G  # noqa: E402
import common as C  # noqa: E402

rests = C.fetch_all("restaurants", order_col="id")
tasks = []
for r in rests:
    if r.get("status") == "active" and not C.parse_location(r.get("location")):
        tasks.append({"rid": r["id"], "name": r["name"],
                      "address": r.get("address"), "district": r.get("district")})

results = []
for i, rec in enumerate(tasks, 1):
    rr = G.process(rec)
    rr["rid"] = rec["rid"]
    rr["name"] = rec["name"]
    results.append(rr)
    print(f"[{i}/{len(tasks)}] {rr['status']} {rec['name']}")
    time.sleep(0.12)

json.dump(results, open(HERE / "missing_coords_result.json", "w"),
          ensure_ascii=False, indent=2)
print("\n", dict(Counter(r["status"] for r in results)))
for r in results:
    if r["status"] in ("ambiguous", "miss", "low_confidence", "multi_no_point"):
        extra = r.get("note") or [c.get("title") for c in r.get("candidates", [])][:3]
        print(" ⚠", r["rid"], r["name"], extra)

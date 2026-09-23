#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 plan_scene.json 中所有 new（含 conflict 经研判改 new）的店批量补坐标。
复用 geocode_scene 的 suggestion/geocoder 判定；new 店暂无 rid，用临时序号。
只产出 new_coords_result.json，不写库。"""
import json
import pathlib
import sys
import time
from collections import Counter

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import geocode_scene as G  # noqa: E402

PLAN = HERE.parent / "_stage1" / "plan_scene.json"
OUT = HERE / "new_coords_result.json"


def main():
    plan = json.load(open(PLAN))
    recs = []
    for x in plan:
        if x["action"] in ("new", "conflict"):
            f = x["fields"]
            recs.append({
                "rid": 9000 + len(recs) + 1,
                "name": x["name"],
                "address": f.get("address"),
                "district": f.get("district"),
                "orig_action": x["action"],
            })
    results = []
    for i, rec in enumerate(recs, 1):
        r = G.process(rec)
        r["name"] = rec["name"]
        r["temp_rid"] = rec["rid"]
        r["orig_action"] = rec["orig_action"]
        results.append(r)
        print(f"[{i}/{len(recs)}] {r['status']} {rec['name']}")
        time.sleep(0.1)
    json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
    print("\n", dict(Counter(r["status"] for r in results)))
    for r in results:
        if r["status"] in ("ambiguous", "miss", "low_confidence", "multi_no_point"):
            extra = r.get("note") or [c["address"] for c in r.get("candidates", [])][:4]
            print(" ⚠", r["name"], extra)


if __name__ == "__main__":
    main()

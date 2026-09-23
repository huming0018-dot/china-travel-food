#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核查多址聚合店在库现状（防重复建店）+ 为低置信店精确重搜坐标。"""
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
PIPE = pathlib.Path(
    "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/"
    "agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
)
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import geocode_scene as G  # noqa: E402

for q in ["Gregorius", "有喜屋", "烤匠", "苹果花园"]:
    r = C.req("GET", "/restaurants",
              params={"select": "id,name,address,district,status",
                      "name": f"ilike.*{q}.*"})
    rows = r.json() if r.status_code == 200 else []
    print(f"查 {q}:", [(x["id"], x["name"], x.get("address")) for x in rows])

print("--- 低置信店精确 suggest ---")
for label, kw in [("麻布屋", "麻布屋 AZABUYA"),
                  ("drunkbaker", "Drunk Baker 陕康里"),
                  ("顶特勒", "顶特勒粥面馆")]:
    for c in G.suggest(kw)[:6]:
        print(label, "|", c["title"], "|", c.get("address"), "|",
              c["location"]["lat"], c["location"]["lng"])

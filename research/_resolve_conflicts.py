#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把经核实的 conflict（同栋建筑不同餐厅）改为 new。"""
import json
import pathlib

P = pathlib.Path("research/_plan.json")
plan = json.loads(P.read_text(encoding="utf-8"))
n = 0
for p in plan:
    if p["action"] == "conflict":
        p["action"] = "new"
        p["restaurant_id"] = None
        p.setdefault("warnings", []).append("经地址楼层/铺位比对：同栋建筑内不同餐厅，按新店")
        n += 1
pathlib.Path("research/_plan_final.json").write_text(
    json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
from collections import Counter
print("改判 new 的 conflict:", n)
print("最终 action:", Counter(p["action"] for p in plan))

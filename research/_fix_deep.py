#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep 机械修复：删空壳悦轩(并入柏悦完整版)、Tuttu 补高德 map 来源。"""
import pathlib
import sys

PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, PIPE)
import common as C

F = "research/_deep_all.jsonl"
rows = C.read_jsonl(F)

# 1) 删除空壳悦轩（name 恰为"悦轩" 且 address 待确认），保留"悦轩(上海柏悦酒店)"
kept, dropped = [], []
for r in rows:
    if r.get("name") == "悦轩" and (r.get("address") in ("待确认", "", None)):
        dropped.append(r["name"])
        continue
    kept.append(r)
assert any("悦轩" in r["name"] for r in kept), "删空壳后找不到完整版悦轩"
rows = kept

# 2) Tuttu 补高德地图 map 来源
for r in rows:
    if r["name"].startswith("Tuttu"):
        srcs = r.setdefault("sources", [])
        if not any("amap.com" in (s.get("url") or "") for s in srcs):
            srcs.append({
                "title": "高德地图：Tuttu(延平路)",
                "url": "https://www.amap.com/search?query=Tuttu%E5%BB%B6%E5%B9%B3%E8%B7%AF&city=310000",
                "type": "map"})

C.write_jsonl(F, rows)
print("删除空壳:", dropped, "| 剩余", len(rows), "行；Tuttu 已补高德")

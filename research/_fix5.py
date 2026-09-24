#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""残余5家收口：3家补大众点评 platform_scores，2家补高德 map 来源。"""
import json
import pathlib
import sys

PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, PIPE)
import common as C

F = pathlib.Path("research/_mine25.jsonl")
rows = C.read_jsonl(str(F))

# index -> 大众点评 (口味分, 评论数, 详情URL)
DP = {
    18: (4.7, 1680, "https://www.dianping.com/shop/G9TkAsT1S7HTLo8H"),
    19: (4.3, 2968, "https://www.dianping.com/shop/l8gntInbvmonu6Ed"),
    20: (4.2, 1541, "https://www.dianping.com/shop/l95efE1s8ITIgjyQ"),
}
# index -> 高德地图搜索页（map 类第二来源）
AMAP = {
    23: ("高德地图：来来来泰国排档(长乐路店)",
         "https://www.amap.com/search?query=%E6%9D%A5%E6%9D%A5%E6%9D%A5%E6%B3%B0%E5%9B%BD%E6%8E%92%E6%A1%A3%E9%95%BF%E4%B9%90%E8%B7%AF&city=310000"),
    24: ("高德地图：RONG融",
         "https://www.amap.com/search?query=RONG%E8%9E%8D&city=310000"),
}

for i, (sc, rc, url) in DP.items():
    ev = rows[i].setdefault("evidence", {})
    pscores = ev.setdefault("platform_scores", [])
    # 去重：移除同平台旧项
    pscores[:] = [p for p in pscores if p.get("platform") != "大众点评"]
    pscores.append({"platform": "大众点评", "score": sc, "review_count": rc, "url": url})

for i, (title, url) in AMAP.items():
    srcs = rows[i].setdefault("sources", [])
    srcs[:] = [s for s in srcs if "amap.com" not in (s.get("url") or "")]
    srcs.append({"title": title, "url": url, "type": "map"})

C.write_jsonl(str(F), rows)
print("已更新 index", sorted(DP), "评分；", sorted(AMAP), "地图来源")

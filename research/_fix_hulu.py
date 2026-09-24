#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hulu Sushi 补大众点评食客原话 + 评分。"""
import sys

PIPE = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, PIPE)
import common as C

F = "research/_deep_all.jsonl"
rows = C.read_jsonl(F)
URL = "https://www.dianping.com/shop/H1RTbWOUzRwQ0GoH"

for r in rows:
    if r["name"].startswith("Hulu Sushi"):
        ev = r.setdefault("evidence", {})
        qs = ev.setdefault("diner_quotes", [])
        if not any("dianping.com" in (q.get("url") or "") for q in qs):
            qs.append({
                "source": "大众点评",
                "dish": "安康鱼肝/鲍鱼肝酱/玉子烧",
                "quote": "上海真的好多Omakase眼花缭乱，这家不追装修、不追环境、不追出片，只追品质；从第一口开始就和朋友四目相对说好吃，20多道下来两人至少说了10次，安康鱼肝、鲍鱼肝酱、山药虾鸡蛋的玉子烧都很在线",
                "url": URL})
        ps = ev.setdefault("platform_scores", [])
        if not any(p.get("platform") == "大众点评" for p in ps):
            ps.append({"platform": "大众点评", "score": 4.8, "review_count": 720, "url": URL})
        srcs = r.setdefault("sources", [])
        if not any("dianping.com" in (s.get("url") or "") for s in srcs):
            srcs.append({"title": "大众点评商户页：Hulu Sushi葫芦寿司", "url": URL, "type": "ugc"})

C.write_jsonl(F, rows)
print("Hulu Sushi 已补点评 quote + 评分")

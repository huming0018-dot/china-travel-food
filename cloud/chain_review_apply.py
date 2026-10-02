#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chain_review_apply.py — 精选层【硬规则】下架（确定性、只降不升、宁空不假）。

ML logistic 门经 curate_v4 dry-run 验证未跑赢基线（真实食客评价覆盖不足），暂不启用。
在此之前用两条保守硬规则维护精选层 is_curated：
  A. status=closed / central_kitchen=确认 / premade_risk=高 → 移出精选；
  B. chain_type∈{大型连锁,资本化连锁} 且独立食客口味声音(不同 verified diner 作者)<2
     → 移出精选（连锁本身不是罪，但无真实食客味道交叉就不进精选）。
只 PATCH is_curated=false，绝不自动加精选；其余字段不动。
"""
import sys
from collections import defaultdict

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core

rests = core.fetch_all(
    "restaurants",
    "id,name,status,chain_type,central_kitchen,premade_risk,is_curated")
revs = core.fetch_all(
    "reviews",
    "restaurant_id,source_platform,is_verified_diner,author_name,aspect_taste")

voices = defaultdict(set)
for x in revs:
    if x.get("aspect_taste") is None:
        continue
    if x.get("source_platform") == "amap" or not x.get("is_verified_diner"):
        continue
    a = x.get("author_name")
    if a:
        voices[x["restaurant_id"]].add(a)

nA = nB = 0
listA, listB = [], []
for r in rests:
    if not r.get("is_curated"):
        continue
    rid = r["id"]
    hardA = (r.get("status") == "closed"
             or r.get("central_kitchen") == "确认"
             or r.get("premade_risk") == "高")
    chainB = (r.get("chain_type") in ("大型连锁", "资本化连锁")
              and len(voices.get(rid, ())) < 2)
    if hardA:
        listA.append(rid)
    elif chainB:
        nv = len(voices.get(rid, ()))
        listB.append((rid, nv))

for rid in listA:
    rsp = core.req("PATCH", f"/restaurants?id=eq.{rid}", json={"is_curated": False})
    nA += 1 if rsp.status_code in (200, 204) else 0
for rid, _v in listB:
    rsp = core.req("PATCH", f"/restaurants?id=eq.{rid}", json={"is_curated": False})
    nB += 1 if rsp.status_code in (200, 204) else 0

print("规则A(关店/中央厨房确认/高预制) 移出:", nA, sorted(listA))
print("规则B(大型资本连锁且食客声音<2) 移出:", nB,
      [(rid, v) for rid, v in listB])
print("当前精选总数:",
      sum(1 for r in core.fetch_all("restaurants", "id,is_curated") if r.get("is_curated")))

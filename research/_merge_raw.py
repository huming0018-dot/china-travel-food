#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 5 个补店 raw（并查集，规则化）：
- 精确同名：地址兼容 / 一方占位 → 合并；两个不兼容真实地址=分店保留。
- 近名（品牌核心相似）：地址兼容（共同道路后缀+同号）→ 合并。
- 一方占位(待确认) 且品牌核心包含 → 并入真实店。
"""
import pathlib, statistics, re, difflib
import common as C

BASE = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")
FILES = [
    "research/authority/gap_michelin/raw_gap.jsonl",
    "research/authority/gap_blackpearl/raw_gap.jsonl",
    "research/poi/raw_poi_new.jsonl",
    "research/social/raw_social_new.jsonl",
    "research/private_dining/raw_private_dining_v2.jsonl",
]
ROAD_SUF = ("大道", "公路", "路", "街", "道")

def road_num(r):
    a = (r.get("address") or "").strip()
    if "待确认" in a or len(a) < 6:
        return None
    m = re.findall(r"([\u4e00-\u9fa5A-Za-z0-9]{1,12}?(?:大道|公路|路|街|道))\s?(\d{1,5})号", a)
    if m:
        return (C.norm_name(m[-1][0]), m[-1][1])
    core = C.addr_core(a)
    return (C.norm_name(core), "") if core else None

def common_suffix(a, b):
    i = 0
    while i < min(len(a), len(b)) and a[-(i+1)] == b[-(i+1)]:
        i += 1
    return a[len(a)-i:]

def addr_compat(ka, kb):
    if ka is None or kb is None:
        return False
    r1, n1 = ka; r2, n2 = kb
    if n1 != n2:
        return False
    if r1 == r2:
        return True
    cs = common_suffix(r1, r2)
    return len(cs) >= 3 and cs.endswith(ROAD_SUF)

def brand_core(s):
    return C.norm_name(re.split(r"[（(]", str(s))[0])

def cores_similar(a, b):
    if a in b or b in a:
        return min(len(a), len(b)) >= 2
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.62

def info_score(r):
    ev = r.get("evidence") or {}
    return (len(ev.get("diner_quotes", [])) * 3 + len(r.get("sources", [])) * 2
            + len(r.get("evidence_summary") or "") / 100 + (1 if road_num(r) else 0))

def merge_group(group):
    group = sorted(group, key=info_score, reverse=True)
    base = dict(group[0])
    quotes, qseen = [], set(); sources, sseen = [], set()
    pscores, pseen = [], set(); dishes, dseen = [], set()
    prices, summaries, addrs, dists = [], [], [], set()
    for r in group:
        ev = r.get("evidence") or {}
        for q in ev.get("diner_quotes", []):
            k = q.get("url") or q.get("quote")
            if k not in qseen: qseen.add(k); quotes.append(q)
        for s in r.get("sources", []):
            if s.get("url") not in sseen: sseen.add(s["url"]); sources.append(s)
        for ps in ev.get("platform_scores", []):
            k = (ps.get("platform"), ps.get("score"))
            if k not in pseen: pseen.add(k); pscores.append(ps)
        for d in C.dishes_list(r.get("signature_dishes")):
            if d not in dseen: dseen.add(d); dishes.append(d)
        if r.get("price_avg"): prices.append(C.to_int(r["price_avg"]))
        if r.get("evidence_summary"): summaries.append(r["evidence_summary"])
        if road_num(r): addrs.append(r["address"])
        if r.get("district") and r["district"] != "待确认": dists.add(r["district"])
    ev = dict(base.get("evidence") or {})
    ev["diner_quotes"] = quotes; ev["platform_scores"] = pscores
    base["evidence"] = ev; base["sources"] = sources; base["signature_dishes"] = dishes
    if prices: base["price_avg"] = int(statistics.median(prices))
    if summaries: base["evidence_summary"] = max(summaries, key=len)
    if addrs: base["address"] = sorted(addrs, key=len, reverse=True)[0]
    if dists: base["district"] = sorted(dists)[0]
    return base

rows = []
for f in FILES:
    p = BASE / f
    if p.exists(): rows.extend(C.read_jsonl(str(p)))
print("合并前总行数:", len(rows))
roads = [road_num(r) for r in rows]
norms = [C.norm_name(r["name"]) for r in rows]
bcores = [brand_core(r["name"]) for r in rows]

def can_merge(i, j):
    ka, kb = roads[i], roads[j]
    exact = norms[i] == norms[j]
    if exact:
        if ka is None or kb is None:  # 占位并入
            return True
        return addr_compat(ka, kb)
    # 近名：需两个真实且兼容地址
    if cores_similar(bcores[i], bcores[j]):
        if ka is not None and kb is not None and addr_compat(ka, kb):
            return True
    # 一方占位且品牌核心包含
    if (ka is None or kb is None) and bcores[i] != bcores[j]:
        x, y = (bcores[i], bcores[j]) if ka is None else (bcores[j], bcores[i])
        if (x in y or y in x) and min(len(x), len(y)) >= 2:
            return True
    return False

parent = list(range(len(rows)))
def find(x):
    while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
    return x
for i in range(len(rows)):
    for j in range(i+1, len(rows)):
        if can_merge(i, j):
            ri, rj = find(i), find(j)
            if ri != rj: parent[rj] = ri

groups = {}
for i in range(len(rows)):
    groups.setdefault(find(i), []).append(rows[i])

final = []
for grp in groups.values():
    if len(grp) > 1:
        print(f"合并: {' ＋ '.join(x['name'] for x in grp)}")
        final.append(merge_group(grp))
    else:
        final.append(grp[0])

out = BASE / "research/_merged_raw.jsonl"
C.write_jsonl(str(out), final)
print(f"\n合并后: {len(final)} 行 → {out}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 25 家(>=2 规范UGC)并做机械修复：
- 规范 UGC quote 同步进 sources（按 url 去重）
- 删除无 URL 的 quote（仅当删除后仍 >=2 规范 UGC）
"""
import pathlib
import common as C

BASE = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")

def is_ugc(q):
    return (C.source_kind(q.get("source"), q.get("url")) == "ugc"
            and C.quote_has_substance(q.get("quote")) and q.get("url"))

rows = C.read_jsonl(str(BASE / "research/_merged_raw.jsonl"))
mine = [r for r in rows if sum(1 for q in (r.get("evidence") or {}).get("diner_quotes", []) if is_ugc(q)) >= 2]
print("导出 25 家:", len(mine))

out = []
for r in mine:
    r = dict(r)
    ev = dict(r.get("evidence") or {})
    quotes = ev.get("diner_quotes", [])
    n_ugc = sum(1 for q in quotes if is_ugc(q))
    # 删除无 URL quote（删后仍>=2规范UGC才删）
    new_quotes = []
    for q in quotes:
        if not (q.get("url") or "").strip():
            if n_ugc >= 2:
                continue  # 删除
        new_quotes.append(q)
    ev["diner_quotes"] = new_quotes
    r["evidence"] = ev
    # UGC quote 同步进 sources
    sources = [dict(s) for s in r.get("sources", [])]
    have_urls = {s.get("url") for s in sources}
    for q in new_quotes:
        if is_ugc(q) and q["url"] not in have_urls:
            sources.append({"title": q.get("source") or "食客评价", "url": q["url"], "type": "ugc"})
            have_urls.add(q["url"])
    r["sources"] = sources
    out.append(r)

C.write_jsonl(str(BASE / "research/_mine25.jsonl"), out)
print("→ research/_mine25.jsonl")
# 复核残余缺陷
import stage1_validate as s1
for r in out:
    errs, warns, clean = s1.validate(r)
    other = [e for e in errs if "evidence_summary" not in e]
    if other:
        print(f"{r['name']}: " + " ; ".join(other))

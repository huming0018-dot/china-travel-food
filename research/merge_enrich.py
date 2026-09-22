#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 research/enrich/raw_*_enrich.jsonl 的补强结果合并进 accepted_fanout.jsonl。
主代理独立回验后使用：坐标纠偏(湘菜片 lat/lng 颠倒)+bbox、地址覆盖并重算 district、
电话合法才补、点评/来源去重合并、柒熙里拆双店；海缘居/然记无确切地址保持占位不入库。
"""
import copy
import glob
import json
import os
import re
import sys

SKILL_SCRIPTS = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL_SCRIPTS)
import common as C  # noqa: E402

R = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research"
PH_PLACEHOLDER = re.compile(r"待核|待补|具体门牌|具体楼层|具体铺位|具体地址|具体门店")


def norm(s):
    return re.sub(r"[\s\(\)（）·\-_分店店]", "", s or "")


def district_of(addr):
    m = re.search(r"(浦东新区|黄浦|徐汇|长宁|静安|普陀|虹口|杨浦|闵行|宝山|嘉定|奉贤|松江|青浦|金山|崇明)区?", addr or "")
    if not m:
        return None
    d = m.group(1)
    if d == "浦东新区" or d.endswith("区"):
        return d if d.endswith("区") else d + "区"
    return d + "区"


def in_sh(lng, lat):
    return lng is not None and lat is not None and 120.80 <= lng <= 122.20 and 30.65 <= lat <= 31.95


def main():
    acc = [json.loads(l) for l in open(f"{R}/accepted_fanout.jsonl", encoding="utf-8") if l.strip()]
    by_norm = {norm(a["name"]): a for a in acc}

    en = {}
    for f in glob.glob(f"{R}/enrich/raw_*_enrich.jsonl"):
        for l in open(f, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                en[r["name"]] = r

    stats = {"addr": 0, "coord": 0, "phone": 0, "quotes": 0, "sources": 0, "district_fix": 0}
    still_blocked = []
    for k, e in en.items():
        base = by_norm.get(norm(k))
        if not base:
            print("⚠ enrich 未匹配:", k)
            continue
        # --- 地址（非占位才覆盖）+ 重算 district ---
        na = e.get("address")
        if na and not PH_PLACEHOLDER.search(str(na)):
            if na != base.get("address"):
                base["address"] = na
                stats["addr"] += 1
            nd = district_of(na)
            if nd and nd != base.get("district") and nd in C.DISTRICTS:
                base["district"] = nd
                stats["district_fix"] += 1
        # --- 坐标（纠偏 + bbox）---
        la, ln = e.get("lat"), e.get("lng")
        if la is not None and ln is not None and la > 90:  # 湘菜片把经纬度填反
            la, ln = ln, la
        if in_sh(ln, la):
            if (base.get("lat"), base.get("lng")) != (la, ln):
                base["lat"], base["lng"], base["coord_source"] = la, ln, e.get("coord_source") or "amap"
                stats["coord"] += 1
        elif la is not None:
            print("⚠ 坐标越界弃用:", k, la, ln)
        # --- 电话（合法且原空才补）---
        if e.get("phone_raw") and not base.get("phone"):
            phone, issues, note = C.clean_phone(e["phone_raw"])
            if phone and not any(i == "phone_unparseable" for i in issues):
                base["phone"] = phone
                stats["phone"] += 1
                bm = "；".join([x for x in [e.get("booking_method"), note] if x])
                if bm:
                    base["booking_method"] = "；".join([x for x in [base.get("booking_method"), bm] if x])
        elif e.get("booking_method"):
            base["booking_method"] = "；".join([x for x in [base.get("booking_method"), e["booking_method"]] if x])
        # --- 堂食点评合并（去重）---
        ev = base.setdefault("evidence", {})
        qs = ev.setdefault("diner_quotes", [])
        seen_q = {(q.get("url"), q.get("quote")) for q in qs}
        for q in e.get("add_quotes") or []:
            key = (q.get("url"), q.get("quote"))
            if key not in seen_q and q.get("url") and q.get("quote"):
                qs.append({"quote": q.get("quote"), "source": q.get("source"),
                           "url": q.get("url"), "dish": q.get("dish"), "date": q.get("date")})
                seen_q.add(key)
                stats["quotes"] += 1
        # --- 来源合并（去重）---
        srcs = base.setdefault("sources", [])
        seen_s = {s.get("url") for s in srcs}
        for s in e.get("add_sources") or []:
            if s.get("url") and s.get("url") not in seen_s:
                srcs.append({"title": s.get("title"), "url": s.get("url"), "type": s.get("type")})
                seen_s.add(s.get("url"))
                stats["sources"] += 1
        # --- notes 追加裁决/纠错说明 ---
        v = e.get("conflict_verdict")
        if v and v not in ("new",) and not str(v).startswith("new"):
            base["notes"] = "；".join([x for x in [base.get("notes"), f"补强核验:{v}"] if x])

    # --- 柒熙里拆双店（辛耕路徐汇老店[base] + 愚园路静安二店）---
    qxl = by_norm.get(norm("柒熙里"))
    if qxl and "辛耕路" in (qxl.get("address") or ""):
        second = copy.deepcopy(qxl)
        second["name"] = "柒熙里(愚园路店)"
        second["address"] = "上海市静安区愚园路88号静安寺108美食广场一层(观光电梯旁)"
        second["district"] = "静安区"
        second["business_area"] = "静安寺"
        second["lat"], second["lng"], second["coord_source"] = None, None, None
        second["notes"] = "柒熙里二店(静安)，与辛耕路徐汇店为同名异址连锁，坐标待拾取器补"
        qxl["name"] = "柒熙里(辛耕路店)"
        qxl["notes"] = "柒熙里老店(徐汇徐家汇)"
        acc.append(second)
        print("→ 柒熙里拆双店：辛耕路徐汇店 + 愚园路静安店")

    # --- 仍无确切地址（占位/无号）的店，标记不进第二批 ---
    for a in acc:
        if PH_PLACEHOLDER.search(a.get("address") or "") or len(a.get("address") or "") < 8:
            still_blocked.append(a["name"])

    out = f"{R}/accepted_fanout_v2.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for a in acc:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"\n合并统计: {stats}")
    print(f"输出 {len(acc)} 行 -> {out}")
    if still_blocked:
        print(f"仍无确切地址、第二批不入库({len(still_blocked)}): {still_blocked}")


if __name__ == "__main__":
    main()

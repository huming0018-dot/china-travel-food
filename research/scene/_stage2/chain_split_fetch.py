#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_split_fetch.py — 用腾讯 search(地区搜索) 列出连锁品牌在上海的全部分店 POI。
search 额度 200/日；每品牌分页(page_size=20)，调用次数很少。
输出 chain_branches.json：品牌 -> [分店 {title,address,tel,lat,lng,id,category}]。
只采集事实，不写库；坐标 GCJ-02。
"""
import json
import pathlib
import time

import requests

KEY = "7PQBZ-7IDKZ-YUHXF-7V2GG-M2B3O-4OBT6"
BASE = "https://apis.map.qq.com/ws/place/v1/search"

# 品牌 -> (搜索词, title 必须包含的判定词)
BRANDS = {
    "Gregorius": ("Gregorius", "gregorius"),
    "有喜屋": ("有喜屋", "有喜屋"),
    "烤匠": ("烤匠麻辣烤鱼", "烤匠"),
}


def list_brand(keyword, must):
    out, page = [], 1
    while True:
        p = {"keyword": keyword, "boundary": "region(上海,0)", "key": KEY,
             "page_size": 20, "page_index": page}
        j = requests.get(BASE, params=p, timeout=20).json()
        if j.get("status") != 0:
            print(f"  search 错误 status={j.get('status')} {j.get('message')}")
            break
        data = j.get("data") or []
        for c in data:
            title = c.get("title") or ""
            if must.lower() in title.lower():
                loc = c.get("location") or {}
                out.append({
                    "id": c.get("id"), "title": title,
                    "address": c.get("address"), "tel": c.get("tel"),
                    "category": c.get("category"),
                    "lat": loc.get("lat"), "lng": loc.get("lng"),
                })
        if len(data) < 20:
            break
        page += 1
        time.sleep(0.3)
    return out


def main():
    res = {}
    for brand, (kw, must) in BRANDS.items():
        rows = list_brand(kw, must)
        # POI id 去重
        seen, uniq = set(), []
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            uniq.append(r)
        res[brand] = uniq
        print(f"{brand}: {len(uniq)} 分店")
        for r in uniq:
            print(f"   - {r['title']} | {r['address']} | tel={r['tel']}")
        time.sleep(0.4)
    pathlib.Path(__file__).parent.joinpath("chain_branches.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n输出 chain_branches.json")


if __name__ == "__main__":
    main()

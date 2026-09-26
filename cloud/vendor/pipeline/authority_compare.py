#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
authority_compare.py — 权威名单（米其林 / 黑珍珠）全量比对库，输出缺失权威店。

机制目的（systematic-sourcing §1.3 / §2）：权威指南名单是确定性、可枚举的，
其上榜店应 100% 在库；本脚本做全量比对，缺的店自动转补录清单（不是手工补点名店）。
可复跑：重新抓官网名单后再跑本脚本。

输入：research/authority/michelin_shanghai_153.json（browser 采集器产物）
输出：research/authority/authority_missing.json + 控制台分组报告
用法：python3 authority_compare.py
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402

PROJ = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")
AUTH = PROJ / "research" / "authority"


def parse_distinction(rec: dict) -> str:
    """从卡片图标推算奖项：数 star svg = 星数；Bibendum = 必比登；否则入选。"""
    stars = 0
    bib = False
    for alt_file in rec.get("imgs", []):
        f = alt_file.split("|")[-1]
        if "michelin-star" in f:
            stars += 1
        if "bibendum" in f.lower():
            bib = True
    return {3: "三星", 2: "二星", 1: "一星"}.get(stars, "必比登" if bib else "入选")


def cuisine_from_all(rec: dict) -> str:
    """all 形如 '可供订位 | 店名 | Shanghai, 中国内地 | ¥¥ · 粤菜'，取 '· ' 后菜系。"""
    m = re.search(r"·\s*([^|]+)$", rec.get("all", ""))
    return m.group(1).strip() if m else ""


def core_name(s: str) -> str:
    s = re.sub(r"（.*?）|\(.*?\)", "", s or "")
    s = re.sub(r"\s+", "", s)
    return C.norm_name(s)


def main():
    michelin = json.loads((AUTH / "michelin_shanghai_153.json").read_text(encoding="utf-8"))
    rests = C.fetch_all("restaurants", "id,name,name_en,status,district")
    by_norm = {}
    for r in rests:
        by_norm.setdefault(C.norm_name(r["name"]), r)
        if r["name_en"]:
            by_norm.setdefault(C.norm_name(r["name_en"]), r)

    def match(rec):
        n = C.norm_name(rec["name"])
        if n in by_norm:
            return by_norm[n]
        c = core_name(rec["name"])
        if len(c) >= 3:
            for k, r in by_norm.items():
                if c in k or k in c:
                    return r
        return None

    hit, miss = [], []
    for rec in michelin:
        d = parse_distinction(rec)
        m = match(rec)
        row = {"name": rec["name"], "slug": rec["slug"], "distinction": d,
               "cuisine": cuisine_from_all(rec),
               "matched_id": m["id"] if m else None,
               "matched_status": m["status"] if m else None}
        (hit if m else miss).append(row)

    # 分组统计
    order = ["三星", "二星", "一星", "必比登", "入选"]
    print("=== 米其林上海 153 全量比对 ===")
    for d in order:
        h = [x for x in hit if x["distinction"] == d]
        m = [x for x in miss if x["distinction"] == d]
        print(f"{d}: 在库 {len(h)} / 缺失 {len(m)}")
    print(f"合计：在库 {len(hit)} / 缺失 {len(miss)}")

    print("\n=== 缺失权威店清单（按奖项）===")
    for d in order:
        rows = [x for x in miss if x["distinction"] == d]
        if rows:
            print(f"\n[{d}] {len(rows)} 家")
            for x in rows:
                print(f"  - {x['name']} （{x['cuisine']}） slug={x['slug']}")

    # 已匹配但已关店（权威仍挂，需复核）
    closed_hit = [x for x in hit if x["matched_status"] == "closed"]
    if closed_hit:
        print("\n=== 官网在榜但库标 closed（需复核）===")
        for x in closed_hit:
            print(f"  - {x['name']} id={x['matched_id']} {x['distinction']}")

    (AUTH / "authority_missing.json").write_text(
        json.dumps({"hit": hit, "missing": miss}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("\n已写 research/authority/authority_missing.json")


if __name__ == "__main__":
    main()

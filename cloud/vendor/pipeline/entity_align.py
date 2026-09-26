#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_align.py — 权威名单与库的确定性实体对齐器（替代逐级放宽的噪声匹配）。

三级判定：
1. high：命中品牌注册表 brand_registry.json（canonical/en/aliases 精确 norm），
   并用括号分店/行政区锚定到具体 branch；
2. medium：注册表未覆盖，品牌核心名与库名核心"完全相等"或"库名以权威核心开头"
   （只允许权威名是库名前缀，杜绝"食光→老吴的食光"这类后缀/子串误配），且区一致；
3. unmatched：真缺（自动转补录）；多分店/歧义 → need_review。

用法：python3 entity_align.py
产出：research/authority/alignment_result.json
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common as C  # noqa: E402

PROJ = pathlib.Path(
    "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")
AUTH = PROJ / "research" / "authority"

DISTRICT_HINT = {
    "黄浦": "黄浦区", "徐汇": "徐汇区", "静安": "静安区", "长宁": "长宁区",
    "浦东": "浦东新区", "闵行": "闵行区", "杨浦": "杨浦区", "虹口": "虹口区",
    "普陀": "普陀区", "嘉定": "嘉定区", "宝山": "宝山区", "松江": "松江区",
    "青浦": "青浦区", "奉贤": "奉贤区", "金山": "金山区", "崇明": "崇明区",
}


def split_brand_district(name: str):
    """'利苑 (徐汇)' -> ('利苑', '徐汇区')；'鲁采(黄浦)' 同理。"""
    m = re.search(r"[（(]([^（）()]+)[）)]", name)
    district = None
    if m:
        inside = m.group(1)
        for k, v in DISTRICT_HINT.items():
            if k in inside:
                district = v
                break
    brand = re.sub(r"[（(].*?[）)]", "", name).strip()
    return brand, district


def parse_distinction(rec):
    stars = sum(1 for x in rec.get("imgs", []) if "michelin-star" in x.split("|")[-1])
    bib = any("bibendum" in x.lower() for x in rec.get("imgs", []))
    return {3: "三星", 2: "二星", 1: "一星"}.get(stars, "必比登" if bib else "入选")


def main():
    michelin = json.loads((AUTH / "michelin_shanghai_153.json").read_text(encoding="utf-8"))
    registry = json.loads((AUTH / "brand_registry.json").read_text(encoding="utf-8"))
    rests = C.fetch_all("restaurants", "id,name,name_en,district,status")
    by_id = {r["id"]: r for r in rests}

    # 注册表：norm key -> brand
    reg = {}
    for b in registry["brands"]:
        for key in [b["canonical"]] + b.get("en", []) + b.get("aliases", []):
            reg[C.norm_name(key)] = b

    def auto_match(brand, district):
        """保守匹配：核心名相等 / 库名以权威核心开头，且区一致。"""
        cb = C.norm_name(brand)
        if len(cb) < 2:
            return None
        hits = []
        for r in rests:
            cn = C.norm_name(r["name"])
            cen = C.norm_name(r["name_en"])
            name_ok = cn == cb or cn.startswith(cb) or (cen and (cen == cb or cen.startswith(cb)))
            if not name_ok:
                continue
            if district and r["district"] and r["district"] != district:
                continue
            hits.append(r)
        return hits

    matched, need_review, unmatched = [], [], []
    for rec in michelin:
        brand, district = split_brand_district(rec["name"])
        d = parse_distinction(rec)
        bkey = C.norm_name(brand)
        chosen, conf = None, None

        if bkey in reg:  # 注册表精确命中
            b = reg[bkey]
            branches = b.get("branches", [])
            if district:
                cand = [by_id[br["id"]] for br in branches
                        if br["id"] in by_id and by_id[br["id"]]["district"] == district]
                if len(cand) == 1:
                    chosen, conf = cand[0], "high"
                elif len(cand) == 0:
                    # 注册表里没有该区分店 -> 该分店真缺
                    matched  # no-op
                    chosen = None
            else:
                if len(branches) == 1 and branches[0]["id"] in by_id:
                    chosen, conf = by_id[branches[0]["id"]], "high"
                elif len(branches) > 1:
                    need_review.append({"name": rec["name"], "distinction": d,
                                        "reason": "品牌多分店，需按地址锚定",
                                        "candidates": [br["id"] for br in branches]})
                    continue
        if chosen is None:
            hits = auto_match(brand, district)
            if hits and len(hits) == 1:
                chosen, conf = hits[0], "medium"
            elif hits and len(hits) > 1:
                need_review.append({"name": rec["name"], "distinction": d,
                                    "reason": "自动匹配多候选",
                                    "candidates": [h["id"] for h in hits]})
                continue
        row = {"name": rec["name"], "distinction": d, "brand": brand,
               "district": district,
               "matched_id": chosen["id"] if chosen else None,
               "confidence": conf}
        (matched if chosen else unmatched).append(row)

    print("=== 实体对齐结果（米其林153）===")
    print("matched:", len(matched), "(high=%d medium=%d)" % (
        sum(1 for x in matched if x["confidence"] == "high"),
        sum(1 for x in matched if x["confidence"] == "medium")))
    print("need_review:", len(need_review))
    print("unmatched(真缺):", len(unmatched))
    print("\n--- 真缺清单 ---")
    for x in unmatched:
        print(" X", x["distinction"], x["name"], x["district"] or "")
    print("\n--- 需人工/复核 ---")
    for x in need_review:
        print(" ?", x["name"], x["reason"], x.get("candidates"))

    (AUTH / "alignment_result.json").write_text(
        json.dumps({"matched": matched, "need_review": need_review,
                    "unmatched": unmatched}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("\n已写 research/authority/alignment_result.json")


if __name__ == "__main__":
    main()

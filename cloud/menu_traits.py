#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""menu_traits.py — #36 菜单特质提取（素食/全素/清真/无麸质/低卡/低糖/低脂）。

保守原则：只在店铺自有文本（招牌菜/卖点/语义简介/别名）中出现【明确特征词】才打标签，
每个标签附字段与原文片段作为证据；无信号一律留空（宁空不假），不做推断。
用法：python3 menu_traits.py            # dry-run
      python3 menu_traits.py --apply    # 写 dietary_tags
"""
import argparse, datetime, json, re, sys
sys.path.insert(0, "/app/cloud")
import common_core as CC

# 标签 -> 特征正则（多字、明确；按特异性排序，全素优先于素食友好）
TRAITS = [
    ("全素", re.compile(r"全素|纯素|素斋|vegan", re.I)),
    ("素食友好", re.compile(r"素食|素菜|vegetarian", re.I)),
    ("清真", re.compile(r"清真|halal|halāl|回民|穆斯林", re.I)),
    ("无麸质", re.compile(r"无麸质|不含麸质|无麸|gluten[\s\-]?free", re.I)),
    ("低卡", re.compile(r"低卡|低热量|低\s?gi|减脂餐|轻卡", re.I)),
    ("低糖", re.compile(r"低糖|无糖|0\s?糖|零糖", re.I)),
    ("低脂", re.compile(r"低脂", re.I)),
]
FIELDS = ("signature_dishes", "selling_points", "semantic_description", "aliases")


def snippet(text, m):
    s, e = m.span()
    return text[max(0, s - 12):e + 12].replace("\n", " ").strip()


def derive(r):
    tags, ev = [], []
    for tag, rx in TRAITS:
        for f in FIELDS:
            v = r.get(f)
            text = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if v else ""
            m = rx.search(text)
            if m:
                if tag not in tags:
                    tags.append(tag)
                ev.append({"tag": tag, "field": f, "snippet": snippet(text, m)[:60]})
                break
    # 全素时不再单列素食友好
    if "全素" in tags and "素食友好" in tags:
        tags.remove("素食友好")
        ev = [e for e in ev if not (e["tag"] == "素食友好")]
    if not tags:
        return None
    return {"tags": tags, "evidence": ev,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rests = CC.fetch_all(
        "restaurants",
        "id,name,signature_dishes,selling_points,semantic_description,aliases,status",
        order_col="id")
    n = 0
    bytag = {}
    for r in rests:
        payload = derive(r)
        if not payload:
            continue
        n += 1
        for t in payload["tags"]:
            bytag[t] = bytag.get(t, 0) + 1
        if args.apply:
            CC.req("PATCH", f"/restaurants?id=eq.{r['id']}",
                   json={"dietary_tags": payload}, use_service=True)
    print(f"菜单特质命中店铺：{n}/{len(rests)}")
    print("标签分布：", bytag)
    print("模式：", "APPLY" if args.apply else "dry-run")


if __name__ == "__main__":
    main()

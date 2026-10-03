#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chain_gate.py — #41 商业连锁门槛机：标准化连锁的精选上限。

口径（所有权与出餐方式解耦，只卡「标准化」连锁，不卡高端现做集团）：
  is_chain_standardized=true 的店：
    - 不得为「必吃」；
    - 仅当强口味证据（score_taste>=80 且 独立食客>=4 且 review_confidence>=0.5）
      才可保留/降为「值得」；
    - 否则移出精选（is_curated=false, badge=null），理由写入 curate_reason。
  is_chain_standardized=false（新荣记/大董/甬府等高端现做集团、独立店）不受影响。
用法：python3 chain_gate.py [--apply]
"""
import argparse, json, sys, collections
sys.path.insert(0, "/app/cloud")
import common_core as CC

TASTE_MIN, DINERS_MIN, CONF_MIN = 80, 4, 0.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rests = CC.fetch_all(
        "restaurants",
        "id,name,is_chain_standardized,is_curated,curate_badge,curate_reason,"
        "score_taste,review_confidence,status,is_delisted",
        order_col="id")
    reviews = CC.fetch_all(
        "reviews", "restaurant_id,author_name,review_kind,is_fake_suspect,is_hidden,aspect_taste,rating_taste,rating_total",
        order_col="id")

    diners = collections.defaultdict(set)
    for x in reviews:
        if x.get("review_kind") == "diner" and not x.get("is_fake_suspect") \
                and not x.get("is_hidden") and \
                (x.get("aspect_taste") or x.get("rating_taste") or x.get("rating_total")):
            diners[str(x["restaurant_id"])].add(x.get("author_name"))

    changed = []
    for r in rests:
        if not r.get("is_chain_standardized") or r.get("is_delisted"):
            continue
        badge = r.get("curate_badge")
        if badge not in ("必吃", "值得"):
            continue
        nd = len(diners.get(str(r["id"]), ()))
        strong = (r.get("score_taste") or 0) >= TASTE_MIN and nd >= DINERS_MIN and \
                 (r.get("review_confidence") or 0) >= CONF_MIN
        if strong:
            if badge == "必吃":
                changed.append((r["id"], r["name"], "必吃->值得", nd))
                if args.apply:
                    CC.req("PATCH", f"/restaurants?id=eq.{r['id']}", json={
                        "curate_badge": "值得",
                        "curate_reason": f"标准化连锁封顶值得（独立食客{nd}，强口味证据）"},
                        use_service=True)
        else:
            changed.append((r["id"], r["name"], f"{badge}->移出精选", nd))
            if args.apply:
                CC.req("PATCH", f"/restaurants?id=eq.{r['id']}", json={
                    "is_curated": False, "curate_badge": None,
                    "curate_reason": f"标准化连锁且强口味证据不足（独立食客{nd}），门槛机移出"},
                    use_service=True)

    print(f"门槛机处理门店：{len(changed)}")
    for i, n, act, nd in changed:
        print(f"  [{i}] {n[:24]:<26} {act} (独立食客{nd})")
    print("模式：", "APPLY" if args.apply else "dry-run")


if __name__ == "__main__":
    main()

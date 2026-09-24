#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Omakase(cid325) 挂载 + 荞麦/乌冬标签修正（确定性，默认 dry-run）。

依据 research/authority/omakase_attach_list.json：
- 12 家 high + 1 家 medium(小钵,板前割烹会席) 挂 cid325；low(烧肉至心) 不挂。
- rid43 荞麦道、rid44 纹兵卫金虹桥：错挂 cid236 乌冬 → 删 236、挂 cid261 荞麦。
- rid1870 纹兵卫天山：挂 cid261 父类。
所有 RC 操作先 GET 查重，写后回读。
"""
import argparse, sys, time
import common as C

OMAKASE_ADD_325 = [1, 2, 3, 4, 5, 6, 9, 10, 31, 37, 38, 1322, 1317]
REMOVE_WRONG = {43: [236], 44: [236]}
ADD_SOBA_261 = [43, 44, 1870]


def have_cids(rid):
    r = C.req("GET", "/restaurant_cuisines",
              params={"restaurant_id": f"eq.{rid}", "select": "cuisine_id"})
    r.raise_for_status()
    return {x["cuisine_id"] for x in r.json()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    plan = []
    for rid in OMAKASE_ADD_325:
        have = have_cids(rid)
        if 325 not in have:
            plan.append((rid, "POST", 325))
    for rid, cids in REMOVE_WRONG.items():
        have = have_cids(rid)
        for cid in cids:
            if cid in have:
                plan.append((rid, "DELETE", cid))
    for rid in ADD_SOBA_261:
        have = have_cids(rid)
        if 261 not in have:
            plan.append((rid, "POST", 261))

    print(f"将执行 {len(plan)} 条 RC 变更：")
    for rid, op, cid in plan:
        print(f"  {op} rid={rid} cid={cid}")
    if not args.commit:
        print("\n[dry-run] 确认后加 --commit")
        return

    for rid, op, cid in plan:
        if op == "POST":
            r = C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": cid})
            if r.status_code not in (200, 201) and "23505" not in r.text:
                sys.exit(f"POST 失败 rid={rid} cid={cid}: {r.status_code} {r.text[:160]}")
        else:
            r = C.req("DELETE", "/restaurant_cuisines",
                      params={"restaurant_id": f"eq.{rid}", "cuisine_id": f"eq.{cid}"})
            if r.status_code not in (200, 201, 204):
                sys.exit(f"DELETE 失败 rid={rid} cid={cid}: {r.status_code} {r.text[:160]}")
        time.sleep(0.08)

    # 回读
    print("\n=== 回读 ===")
    for rid in sorted(set(OMAKASE_ADD_325 + ADD_SOBA_261)):
        have = sorted(have_cids(rid))
        tag = []
        if 325 in have: tag.append("325✓")
        if 261 in have: tag.append("261✓")
        if 236 in have and rid in REMOVE_WRONG: tag.append("236仍在!")
        print(f"  rid={rid}: {','.join(tag) or '无变化'}")


if __name__ == "__main__":
    main()

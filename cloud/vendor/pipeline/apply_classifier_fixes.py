#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_classifier_fixes.py — Part D: 把 signature_dish_classifier 的高精度推荐写库。

原则：
- 只做"增量 ADD"，不删除任何现有分类（除裕莲茶楼按指示保留82）。
- 只采纳 signature_dishes 直接命中的推荐（why 含"招牌菜:"），证据/店名弱信号不写。
- 幂等：已存在的关联跳过。
- 先 dry-run 打印清单，--commit 才写。
"""
import sys, json, pathlib, requests
import common as C

# 裕莲茶楼特例：招牌蛋挞+乌龙奶茶 → 补 面包/烘焙(68) + 茶饮(324)，保留 茶馆/茶室(82)
YULIAN = {"restaurant_id": 1739, "add": [68, 324]}


def main():
    commit = "--commit" in sys.argv
    rep = pathlib.Path(__file__).parent / "mismatch_report.json"
    rows = json.loads(rep.read_text(encoding="utf-8"))
    current = {(l['restaurant_id'], l['cuisine_id'])
               for l in C.fetch_all('restaurant_cuisines', select='restaurant_id,cuisine_id', order_col='restaurant_id')}

    adds = []
    for r in rows:
        for m in r["missing_recs"]:
            if not any(w.startswith("招牌菜:") for w in m["why"]):
                continue  # 只采纳招牌菜直接命中
            key = (r["id"], m["cuisine_id"])
            if key in current:
                continue
            adds.append({"restaurant_id": r["id"], "cuisine_id": m["cuisine_id"], "is_primary": False})
    # 裕莲特例（去重）
    for cid in YULIAN["add"]:
        if (1739, cid) not in current and (1739, cid) not in {(a["restaurant_id"], a["cuisine_id"]) for a in adds}:
            adds.append({"restaurant_id": 1739, "cuisine_id": cid, "is_primary": False})

    shops_touched = len({a["restaurant_id"] for a in adds})
    print(f"计划新增 {len(adds)} 条标签关联，涉及 {shops_touched} 家餐厅")
    if not commit:
        print("[DRY-RUN] 加 --commit 写库。样例前10条:")
        for a in adds[:10]:
            print("  ", a)
        return
    h = C.headers(); h["Prefer"] = "return=representation"
    ra = requests.post(C.BASE + "/restaurant_cuisines", headers=h, json=adds, timeout=60)
    print("INSERT", ra.status_code, ra.text[:200])
    print(f"[COMMIT] 新增 {len(adds)} 条，涉及 {shops_touched} 家")


if __name__ == "__main__":
    main()

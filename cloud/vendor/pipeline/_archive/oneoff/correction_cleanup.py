#!/usr/bin/env python3
# -*- coding:utf-8 -*-
"""
correction_cleanup.py — 标签/名称纠错清理（stage3 只增不删，误挂标签与错名由此处理）。

确定性、可审计、可复用；默认 dry-run，--commit 才写。
清单来源：research/TAXONOMY_v3.md 与采集 fan-out 审计。
"""
import argparse
import time

import common as C

# 改名：rid -> 正名（依据 name_fixes，权威源≥2一致）
RENAMES = {
    815: "白茸 Bai Rong",   # 原误写「佰荣」，名出牡丹别称，BFC胶东海鲜鲁菜
}
# 删除误挂标签：(rid, cid) -> 原因
DETACH = [
    (1147, 73, "1929 by Guillaume Galliot 是法餐 Fine Dining，非 Bistro"),
    (1391, 44, "Ling Long 凌珑是中餐创新菜+分子先锋，非融合菜"),
    # 私宴 id83 误挂（商场会馆/连锁正餐/汉堡，非预约私宴）
    (905, 83, "CHIC1699 商场会馆且已关店，非私宴"),
    (522, 83, "闽润·福建会馆为商场会馆正餐，非私宴"),
    (525, 83, "席作·福建会馆为连锁会馆正餐，非私宴"),
    (1541, 83, "瑞狮楼潮汕会馆为正餐，非私宴"),
    (1517, 83, "乾七道文化会馆为正餐，非私宴"),
    (1234, 83, "尚牛社会为汉堡店，非私宴"),
    (1446, 83, "釜溪盐韵为自贡盐帮正餐，非私宴"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    actions = []
    for rid, new in RENAMES.items():
        cur = C.req("GET", f"/restaurants?id=eq.{rid}&select=name").json()
        if cur and cur[0]["name"] != new:
            actions.append(("rename", rid, cur[0]["name"], new))
    for rid, cid, why in DETACH:
        hit = C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}"
                           f"&cuisine_id=eq.{cid}&select=restaurant_id").json()
        if hit:
            actions.append(("detach", rid, cid, why))

    for a in actions:
        if a[0] == "rename":
            print(f"[rename] {a[1]} 「{a[2]}」->「{a[3]}」")
        else:
            print(f"[detach] rid={a[1]} cid={a[2]} （{a[3]}）")

    if not args.commit:
        print(f"\n【DRY-RUN】{len(actions)} 项。确认后加 --commit。")
        return

    for a in actions:
        if a[0] == "rename":
            C.req("PATCH", f"/restaurants?id=eq.{a[1]}", json={"name": a[3]})
        else:
            C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{a[1]}"
                            f"&cuisine_id=eq.{a[2]}")
        time.sleep(0.06)
    print(f"纠错完成 {len(actions)} 项。")


if __name__ == "__main__":
    main()

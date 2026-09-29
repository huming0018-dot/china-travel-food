#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
price_realign.py — 1B-1 定价双轨重设（确定性 / 幂等）

双轨：
  ① 绝对带 price_band（分场景 price_scene）：边界取该场景 active 店 price_avg 真实
     P25/P50/P75/P90（取整到 5），写入 price_band_thresholds 配置表；restaurant.price_band=1..5。
  ② 相对档 price_position（场景内分位）：P20/P40/P60/P80 切 入门/主流/进阶/高端/旗舰，
     每个标签绑定该场景的真实数值区间（不再是小菜系组内 PERCENT_RANK 通胀）。
  · 非正餐（快餐小吃/咖啡茶饮/面包/甜品/酒吧）各用各自分布，不套正餐。
  · tier（全局 tier_for_price）由 DB 触发器独占，本脚本不碰 price_avg/tier。

只动：price_band_thresholds 配置行 + restaurants.price_band / price_position。
不碰 phone/location/菜系/score_*/price_avg/tier 等其余字段。

用法：
  python3 price_realign.py           # dry-run：阈值表 + 受影响店 before→after，不写
  python3 price_realign.py --apply    # 写阈值表 + PATCH 变更行（幂等，复跑 0）
"""
import argparse, collections, json
import common as C

SCENES = ["正餐", "快餐小吃", "咖啡茶饮", "面包", "甜品", "酒吧"]
POS_LABELS = ["入门", "主流", "进阶", "高端", "旗舰"]


def pct(xs, q):
    xs = sorted(xs); n = len(xs)
    if n == 1: return float(xs[0])
    k = (n - 1) * q; lo = int(k); frac = k - lo
    return xs[lo] * (1 - frac) + xs[min(lo + 1, n - 1)] * frac


def r5(x):
    return int(round(x / 5.0) * 5)


def build():
    rs = C.fetch_all("restaurants",
                     "id,name,status,price_avg,price_scene,price_band,price_position",
                     order_col="id")
    active = [r for r in rs if r["status"] == "active" and r["price_avg"] is not None
              and r["price_scene"] in SCENES]
    scene_xs = {s: sorted(r["price_avg"] for r in active if r["price_scene"] == s)
                for s in SCENES}
    thr = {}
    for s in SCENES:
        xs = scene_xs[s]
        thr[s] = {q: pct(xs, q) for q in (.2, .25, .4, .5, .6, .75, .8, .9)}

    def band_of(s, price):
        b = [r5(thr[s][.25]), r5(thr[s][.5]), r5(thr[s][.75]), r5(thr[s][.9])]
        for i, hi in enumerate(b, 1):
            if price < hi: return i
        return 5

    def pos_of(s, price):
        cuts = [r5(thr[s][.2]), r5(thr[s][.4]), r5(thr[s][.6]), r5(thr[s][.8])]
        for i, c in enumerate(cuts):
            if price < c: return POS_LABELS[i]
        return POS_LABELS[4]

    plan = {}  # rid -> {price_band, price_position}
    for r in active:
        s = r["price_scene"]; p = r["price_avg"]
        plan[r["id"]] = {"price_band": band_of(s, p), "price_position": pos_of(s, p),
                         "scene": s, "price": p}
    return rs, active, thr, scene_xs, plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rs, active, thr, scene_xs, plan = build()

    print("=== 分场景真实分位与档级定义（active, n=%d）===" % len(active))
    for s in SCENES:
        p = thr[s]; n = len(scene_xs[s])
        b = [r5(p[.25]), r5(p[.5]), r5(p[.75]), r5(p[.9])]
        c = [r5(p[.2]), r5(p[.4]), r5(p[.6]), r5(p[.8])]
        print(f"\n[{s}] n={n}  raw P25={p[.25]:.0f} P50={p[.5]:.0f} P75={p[.75]:.0f} P90={p[.9]:.0f}")
        print(f"  绝对带 band: <{b[0]}/<{b[1]}/<{b[2]}/<{b[3]}/>={b[3]}")
        print(f"  相对档 position: <{c[0]}入门/{c[0]}-{c[1]}主流/{c[1]}-{c[2]}进阶/{c[2]}-{c[3]}高端/>={c[3]}旗舰")

    # diff
    changed = []
    for r in rs:
        if r["id"] not in plan: continue
        p = plan[r["id"]]
        f = {}
        if r["price_band"] != p["price_band"]: f["price_band"] = p["price_band"]
        if r["price_position"] != p["price_position"]: f["price_position"] = p["price_position"]
        if f: changed.append((r["id"], r["name"], f))
    print(f"\n=== 受影响店（price_band/price_position 变更）: {len(changed)} / {len(active)} ===")
    print("position 分布 after:", dict(collections.Counter(v["price_position"] for v in plan.values())))
    print("band 分布 after:", dict(collections.Counter(v["price_band"] for v in plan.values())))
    for rid, name, f in changed[:25]:
        print(f"  id{rid:<6} {str(name)[:24]:<26} {f}")

    # rasa/nick
    for rid in (1110, 1308):
        if rid in plan:
            p = plan[rid]
            cur = next(r for r in rs if r["id"] == rid)
            print(f"  RASA/NICK id{rid}: band {cur['price_band']}->{p['price_band']} "
                  f"position {cur['price_position']}->{p['price_position']} (¥{p['price']})")

    if not args.apply:
        print("\n[dry-run] 未写库。加 --apply 写阈值表 + PATCH 变更行。")
        return

    # 1) 写阈值配置表
    for s in SCENES:
        p = thr[s]
        bounds = [r5(p[.25]), r5(p[.5]), r5(p[.75]), r5(p[.9])]
        rows = [(1, None, bounds[0]), (2, bounds[0], bounds[1]), (3, bounds[1], bounds[2]),
                (4, bounds[2], bounds[3]), (5, bounds[3], None)]
        for band, lo, hi in rows:
            body = {"lo": lo, "hi": hi}
            r = C.req("PATCH", f"/price_band_thresholds?scene=eq.{s}&band=eq.{band}", json=body)
            if r.status_code not in (200, 204):
                print(f"  [THR FAIL] {s} band{band}: {r.status_code} {r.text[:120]}")
    print("阈值表已更新。")

    # 2) PATCH restaurants
    ok = 0
    for rid, name, f in changed:
        r = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=f)
        if r.status_code not in (200, 204):
            print(f"  [FAIL] id{rid}: {r.status_code} {r.text[:120]}"); continue
        ok += 1
    print(f"[apply] PATCH 完成 {ok}/{len(changed)} 行。")


if __name__ == "__main__":
    main()

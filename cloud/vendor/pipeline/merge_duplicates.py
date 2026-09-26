#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_duplicates.py — 写库前/保鲜期实体去重合并（默认 dry-run，绝不默认改库）

规则：
- 按品牌核心名分组，同品牌内用坐标距离单链聚类（默认 <100m 视为同一物理店）；
  同品牌、坐标明显分开 → 连锁异址分店，保留（用户定调）。
- 每个重复簇选信息最全的为 master，其余 duplicate：
  1) 迁移 5 张引用子表（RC / reviews / favorites / negotiations / price_benchmarks）并按业务键去重；
  2) 用 duplicate 补 master 为空的字段（coalesce，不覆盖已有值）；
  3) 删除 duplicate 的标签关联，最后 DELETE duplicate 实体。

用法：
  python3 merge_duplicates.py [-i 不适用，自动扫库]            # dry-run，打印合并计划
  python3 merge_duplicates.py --commit                        # 真正执行
  python3 merge_duplicates.py --threshold 80                 # 调整坐标聚类阈值(米)
"""
import argparse
import math
import re
import sys
import time
from collections import defaultdict

import common as C

CHILD_TABLES = ["restaurant_cuisines", "reviews", "favorites",
                "negotiations", "price_benchmarks"]
SCORE_KEYS = ["score_objective", "score_diner", "score_taste", "score_endorsement"]
FILL_KEYS = ["phone", "address", "name_en", "booking_method", "business_area",
             "price_range", "signature_dishes", "evidence_summary"]


def brand_core(s):
    s = re.split(r"[（(]", str(s))[0]
    m = re.search(r"[路街道里弄号镇]|广场|中心|商场", s)
    if m:
        s = s[:m.start()]
    s = re.sub(r"(上海)?(全国首店|首店|分店|总店|直营店|旗舰店|店)$", "", s)
    return C.norm_name(s)


def ll(r):
    return C.parse_location(r.get("location"))


def dist_m(a, b):
    R = 6371000
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp = math.radians(b[1] - a[1])
    dl = math.radians(b[0] - a[0])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def find_clusters(rests, thresh):
    g = defaultdict(list)
    for r in rests:
        c = brand_core(r["name"])
        if c:
            g[c].append(r)
    out = []
    for c, items in g.items():
        if len(items) < 2:
            continue
        clusters = []
        for r in items:
            placed = False
            for cl in clusters:
                for q in cl:
                    pa, pb = ll(r), ll(q)
                    if pa and pb and dist_m(pa, pb) < thresh:
                        cl.append(r)
                        placed = True
                        break
                if placed:
                    break
            if not placed:
                clusters.append([r])
        for cl in clusters:
            if len(cl) > 1:
                out.append((c, cl))
    return out


def completeness(r):
    s = 0
    if r.get("status") == "active":
        s += 3
    if r.get("location"):
        s += 3
    if r.get("phone"):
        s += 1
    if r.get("signature_dishes"):
        s += 1
    s += 2 * sum(1 for k in SCORE_KEYS if r.get(k) is not None)
    s += min(len(r.get("evidence_summary") or "") // 100, 3)
    if r.get("booking_method"):
        s += 1
    return s


def child_rows(table, rid):
    return C.req("GET", f"/{table}?restaurant_id=eq.{rid}").json()


def migrate(duplicate_id, master_id, commit_log):
    # 1) restaurant_cuisines：master 缺的 cid 补挂
    for rc in child_rows("restaurant_cuisines", duplicate_id):
        cid = rc["cuisine_id"]
        have = C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{master_id}"
                            f"&cuisine_id=eq.{cid}").json()
        if not have:
            r = C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": master_id, "cuisine_id": cid,
                            "is_primary": rc.get("is_primary")})
            commit_log.append(f"RC +{cid} -> {master_id}: {r.status_code}")
        time.sleep(0.03)

    # 2) reviews：同 user 在 master 已评 → 删重复；否则改挂
    for rv in child_rows("reviews", duplicate_id):
        uid = rv.get("user_id")
        clash = C.req("GET", f"/reviews?restaurant_id=eq.{master_id}"
                             f"&user_id=eq.{uid}").json() if uid else []
        if clash:
            r = C.req("DELETE", f"/reviews?id=eq.{rv['id']}")
            commit_log.append(f"reviews dup del {rv['id']}: {r.status_code}")
        else:
            r = C.req("PATCH", f"/reviews?id=eq.{rv['id']}",
                      json={"restaurant_id": master_id})
            commit_log.append(f"reviews {rv['id']} -> {master_id}: {r.status_code}")
        time.sleep(0.03)

    # 3) favorites：同 user 去重，否则改挂
    for fv in child_rows("favorites", duplicate_id):
        uid = fv.get("user_id")
        clash = C.req("GET", f"/favorites?restaurant_id=eq.{master_id}"
                             f"&user_id=eq.{uid}").json() if uid else []
        if clash:
            r = C.req("DELETE", f"/favorites?id=eq.{fv['id']}")
            commit_log.append(f"favorites dup del {fv['id']}: {r.status_code}")
        else:
            r = C.req("PATCH", f"/favorites?id=eq.{fv['id']}",
                      json={"restaurant_id": master_id})
            commit_log.append(f"favorites {fv['id']} -> {master_id}: {r.status_code}")
        time.sleep(0.03)

    # 4) negotiations：同 channel+status 在 master 已有 → 删重复；否则改挂
    for ng in child_rows("negotiations", duplicate_id):
        ch = ng.get("channel")
        clash = C.req("GET", f"/negotiations?restaurant_id=eq.{master_id}"
                             f"&channel=eq.{ch}").json() if ch else []
        if clash:
            r = C.req("DELETE", f"/negotiations?id=eq.{ng['id']}")
            commit_log.append(f"negotiations dup del {ng['id']}: {r.status_code}")
        else:
            r = C.req("PATCH", f"/negotiations?id=eq.{ng['id']}",
                      json={"restaurant_id": master_id})
            commit_log.append(f"negotiations {ng['id']} -> {master_id}: {r.status_code}")
        time.sleep(0.03)

    # 5) price_benchmarks：同 dish_name 在 master 已有 → 删重复；否则改挂
    for pb in child_rows("price_benchmarks", duplicate_id):
        dish = pb.get("dish_name")
        clash = C.req("GET", f"/price_benchmarks?restaurant_id=eq.{master_id}"
                             f"&dish_name=eq.{dish}").json() if dish else []
        if clash:
            r = C.req("DELETE", f"/price_benchmarks?id=eq.{pb['id']}")
            commit_log.append(f"benchmarks dup del {pb['id']}: {r.status_code}")
        else:
            r = C.req("PATCH", f"/price_benchmarks?id=eq.{pb['id']}",
                      json={"restaurant_id": master_id})
            commit_log.append(f"benchmarks {pb['id']} -> {master_id}: {r.status_code}")
        time.sleep(0.03)


def fill_master(master, dups, commit_log):
    fill = {}
    for k in FILL_KEYS:
        if not master.get(k):
            for d in dups:
                if d.get(k):
                    fill[k] = d[k]
                    break
    for k in SCORE_KEYS:
        if master.get(k) is None:
            for d in dups:
                if d.get(k) is not None:
                    fill[k] = d[k]
                    break
    if not master.get("location"):
        for d in dups:
            p = ll(d)
            if p:
                fill["location"] = C.point_ewkt(*p)
                break
    if fill:
        r = C.req("PATCH", f"/restaurants?id=eq.{master['id']}", json=fill)
        commit_log.append(f"master {master['id']} fill {list(fill)}: {r.status_code}")
        if r.status_code not in (200, 201, 204):
            sys.exit(f"补全 master 失败: {r.text[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--threshold", type=float, default=100)
    ap.add_argument("--report", default="merge_report.json")
    args = ap.parse_args()

    rests = C.fetch_all("restaurants", "*", order_col="id")
    by_id = {r["id"]: r for r in rests}
    clusters = find_clusters(rests, args.threshold)
    print(f"识别重复簇 {len(clusters)}（阈值 {args.threshold}m）\n")

    plan = []
    for c, cl in clusters:
        ranked = sorted(cl, key=completeness, reverse=True)
        master = ranked[0]
        dups = ranked[1:]
        counts = {}
        for d in dups:
            for t in CHILD_TABLES:
                n = len(child_rows(t, d["id"]))
                if n:
                    counts[t] = counts.get(t, 0) + n
        plan.append({"core": c, "master_id": master["id"],
                     "master_name": master["name"],
                     "dup_ids": [d["id"] for d in dups],
                     "dup_names": [d["name"] for d in dups],
                     "child_rows": counts})
        print(f"CORE {c}")
        print(f"  KEEP  {master['id']} {master['name']} (完整度 {completeness(master)})")
        for d in dups:
            print(f"  MERGE {d['id']} {d['name']} (完整度 {completeness(d)})")
        print(f"        待迁移子表: {counts or '无'}")

    if not args.commit:
        print(f"\n【DRY-RUN】将合并 {len(plan)} 簇、删除实体 "
              f"{sum(len(p['dup_ids']) for p in plan)} 个。确认后加 --commit。")
        return

    import json
    log = []
    for p in plan:
        master = by_id[p["master_id"]]
        dups = [by_id[i] for i in p["dup_ids"]]
        fill_master(master, dups, log)
        for d in dups:
            migrate(d["id"], master["id"], log)
            # 删除 duplicate 的 RC 关联
            C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{d['id']}")
            r = C.req("DELETE", f"/restaurants?id=eq.{d['id']}")
            log.append(f"DELETE restaurant {d['id']}: {r.status_code}")
            if r.status_code not in (200, 201, 204):
                sys.exit(f"删除重复实体 {d['id']} 失败: {r.text[:200]}")
            time.sleep(0.1)
        rb = C.req("GET", f"/restaurants?id=eq.{master['id']}").json()
        print(f"✓ {p['core']} -> master {master['id']} 回读 {'ok' if rb else 'MISSING'}")

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump({"plan": plan, "log": log}, fh, ensure_ascii=False, indent=2)
    print(f"\n合并完成 {len(plan)} 簇；明细 {args.report}")


if __name__ == "__main__":
    main()

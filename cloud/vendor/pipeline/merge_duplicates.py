#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_duplicates.py — 旧规则只读候选检测（所有写入入口已禁用）

以下旧规则仅供人工复核，不能证明同一实体，也不裁决历史 keep：
- 按品牌核心名分组，同品牌内用坐标距离单链聚类（默认 <100m 视为同一物理店）；
  同品牌、坐标明显分开 → 连锁异址分店，保留（用户定调）。
- 完整度排名仅是建议，不是 keep/merge 裁决；不得执行。

用法：
  python3 merge_duplicates.py [-i 不适用，自动扫库]            # dry-run，打印合并计划
  python3 merge_duplicates.py --commit                        # 已禁用，立即失败
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


_LATIN_STOP = {"cafe", "shop", "store", "bakery", "restaurant", "bistro", "barre",
               "the", "and", "bar", "coffee", "kitchen", "co"}


def brand_keys(s):
    """同一品牌常有多种写法，返回用于聚类的全部键：
    - 完整品牌核心（中文/混合）；
    - 外文品牌常附中文别名（'PAIN CHAUD百丘'、'Starbucks星巴克'），追加“拉丁拼写核心”，
      使 'Pain Chaud' 与 'PAIN CHAUD百丘' 归到同一品牌候选；**是否同一物理店仍由坐标距离把关**。"""
    keys = set()
    core = brand_core(s)
    if core:
        keys.add(core)
    pre = re.split(r"[（(]", str(s))[0]
    lat = [t for t in re.findall(r"[a-z0-9]+", pre.lower())
           if len(t) >= 3 and t not in _LATIN_STOP]
    latin_core = "".join(lat)
    if len(latin_core) >= 4:
        keys.add("lat:" + latin_core)
    return keys


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
    """按 brand_keys 建倒排（同一店可命中多个键），每个键内用坐标距离单链聚类；
    同品牌、坐标明显分开 → 连锁异址分店，保留。最后按 id 集合对多键发现的同一簇去重。"""
    key_map = defaultdict(list)
    for r in rests:
        for k in brand_keys(r["name"]):
            key_map[k].append(r)
    found = []
    for c, items in key_map.items():
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
                found.append((c, cl))
    uniq, sigs = [], set()
    for c, cl in found:
        sig = tuple(sorted(x["id"] for x in cl))
        if sig not in sigs:
            sigs.add(sig)
            uniq.append((c, cl))
    return uniq


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


WRITE_DISABLED = "Legacy entity merge writes disabled: use read-only review plans until a transactional executor and human adjudication exist."


def migrate(duplicate_id, master_id, commit_log):
    """Compatibility boundary: never read or mutate child tables."""
    raise RuntimeError(WRITE_DISABLED)


def fill_master(master, dups, commit_log):
    raise RuntimeError(WRITE_DISABLED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--threshold", type=float, default=100)
    ap.add_argument("--report", default="merge_report.json")
    args = ap.parse_args()

    if args.commit:
        ap.error(WRITE_DISABLED)

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
        print(f"  SUGGESTED MASTER  {master['id']} {master['name']} (完整度 {completeness(master)})")
        for d in dups:
            print(f"  REVIEW {d['id']} {d['name']} (完整度 {completeness(d)})")
        print(f"        待迁移子表: {counts or '无'}")

    import json
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump({"status": "REVIEW_ONLY", "executable": False,
                   "warning": WRITE_DISABLED,
                   "candidate_rule": "legacy brand/proximity heuristic; not identity proof; keep not adjudicated",
                   "plan": plan}, fh, ensure_ascii=False, indent=2)
    print(f"\n【REVIEW ONLY】{len(plan)} candidate clusters; no writes; report {args.report}")


if __name__ == "__main__":
    main()

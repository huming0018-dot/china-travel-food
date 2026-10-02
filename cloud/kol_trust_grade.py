#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kol_trust_grade.py — 按「可信 KOL 精选池」给 food_kol_watchlist 标 trust（机制化、幂等、可复跑）。

- 读 research/authority/kol_curated_pool.json（S/A=high，B=mid）。
- 名字/别名归一(cjk_norm)精确匹配，兜底 len>=3 互相包含。
- 默认 dry-run；--apply 才 PATCH。只改 trust，不动其他字段、不删号。
- KOL 仍只作线索/标签，不计 score_taste。
"""
import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app/pipeline")
try:
    import common as C
except Exception:
    sys.exit("需在容器/已配置环境运行（提供 common 与 Supabase 凭据）")

TIER_TRUST = {"S": "high", "A": "high", "B": "mid"}


def pool_paths():
    cand = [
        os.environ.get("KOL_CURATED_POOL"),
        "/app/data/research/authority/kol_curated_pool.json",
    ]
    for p in cand:
        if p and pathlib.Path(p).exists():
            return pathlib.Path(p)
    # repo 相对路径兜底
    here = pathlib.Path(__file__).resolve()
    for p in here.parents:
        q = p / "research" / "authority" / "kol_curated_pool.json"
        if q.exists():
            return q
    sys.exit("找不到 kol_curated_pool.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    pool = json.loads(pool_paths().read_text(encoding="utf-8"))
    name2tier = {}
    for e in pool["pool"]:
        tv = TIER_TRUST[e["tier"]]
        for nm in [e["name"]] + e.get("aliases", []):
            name2tier[C.cjk_norm(nm)] = tv

    rows = C.fetch_all("food_kol_watchlist", "id,name,platform,trust")
    patches = []
    for r in rows:
        n = C.cjk_norm(r["name"])
        tv = name2tier.get(n)
        if tv is None:
            for k, v in name2tier.items():
                if len(k) >= 3 and (k in n or n in k):
                    tv = v
                    break
        if tv and r.get("trust") != tv:
            patches.append((r["id"], tv, r["name"]))

    print(f"watchlist {len(rows)}；待标 trust {len(patches)}（dry-run）")
    for rid, tv, nm in patches:
        print(f"  {tv}  {nm}")
    if args.apply:
        for rid, tv, nm in patches:
            C.req("PATCH", f"/food_kol_watchlist?id=eq.{rid}", json={"trust": tv}).raise_for_status()
        print(f"APPLIED {len(patches)}")
    else:
        print("加 --apply 写库")


if __name__ == "__main__":
    main()

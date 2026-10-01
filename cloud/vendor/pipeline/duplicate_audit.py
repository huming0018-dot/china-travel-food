#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""duplicate_audit.py — 同址真重复只读硬门（异址连锁分店保留，不判重复）。

规则：
  按 规范名/别名/去业态后缀核心名 做实体并查集聚类；多店组里，
  若归一化地址集合恰为 1（同址）=> 真重复（应合并），exit 1；
  若地址不同 => 异址分店，正确保留，不计数。
用法：python3 duplicate_audit.py [--strict]   # 有真重复时 --strict/默认均 exit1
落盘：FOOD_AUTHORITY_DIR/duplicate_audit.json
"""
import argparse
import collections
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402


def _auth_dir():
    env = os.environ.get("FOOD_AUTHORITY_DIR")
    if env:
        return pathlib.Path(env)
    for cand in ("/app/data/authority", HERE.parent / "research" / "authority"):
        if pathlib.Path(cand).exists():
            return pathlib.Path(cand)
    return HERE.parent / "research" / "authority"


def keyset(r):
    ks = set()
    for nm in [r.get("name"), r.get("name_en")] + list(r.get("aliases") or []):
        if nm:
            c = S.core(nm)
            ks.add(c)
            d = S._distinct(c)
            if d:
                ks.add(d)
    return ks


def addrkey(r):
    a = r.get("address") or ""
    try:
        return C.addr_core(a)
    except Exception:
        return a[:20]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    R = C.fetch_all("restaurants",
                    "id,name,name_en,aliases,status,address,district,location",
                    order_col="id")
    act = [r for r in R if r.get("status") != "closed"]
    byid = {r["id"]: r for r in act}

    bycore = collections.defaultdict(set)
    for r in act:
        for k in keyset(r):
            if len(S._han(k)) >= 2 or len(k) >= 4:
                bycore[k].add(r["id"])

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for k, ids in bycore.items():
        ids = list(ids)
        for i in ids:
            find(i)
        for i in ids[1:]:
            union(ids[0], i)
    groups = collections.defaultdict(set)
    for k, ids in bycore.items():
        for i in ids:
            groups[find(i)].add(i)

    true_dup, branch_groups = [], 0
    for root, ids in groups.items():
        ids = sorted(ids)
        if len(ids) < 2:
            continue
        rows = [{"id": i, "name": byid[i]["name"], "addr": byid[i].get("address"),
                 "akey": addrkey(byid[i])} for i in ids]
        akeys = {r["akey"] for r in rows if r["akey"]}
        if len(akeys) == 1:
            true_dup.append({"ids": ids, "rows": rows})
        else:
            branch_groups += 1

    print(f"多店异址分店组（保留）: {branch_groups}")
    print(f"同址真重复组: {len(true_dup)}")
    for c in true_dup:
        print("  ids=", c["ids"])
        for r in c["rows"]:
            print("    ", r["id"], r["name"], "|", r["addr"])

    outdir = _auth_dir()
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "duplicate_audit.json").write_text(
        json.dumps({"true_dup": true_dup, "branch_groups": branch_groups},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", outdir / "duplicate_audit.json")

    if true_dup:
        print("处理：同址真重复应合并（保留信息最全一条，迁移链接后软关另一条）。")
        sys.exit(1)


if __name__ == "__main__":
    main()

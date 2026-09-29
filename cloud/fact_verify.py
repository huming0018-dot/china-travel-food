#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_verify.py — 事实层标签核验引擎（中央厨房 / 预制 / 食安 / 连锁规模）。

定位（北极星：事实与评价分离、A2 宁空不假、A3 机制优先）：
  模型只做「发现 + 判断」：用搜索引擎核验事实，产出 claims_seed.json（品牌 → 字段结论 + 可溯源主张）。
  本脚本做「机械环节」：品牌→门店匹配、字段值域校验、事实主张合并去重、幂等 PATCH、写后回读。
  新增/修正事实只需更新 claims_seed.json，不改代码。

用法（容器内先 . /app/cloud/env.sh）：
  python3 fact_verify.py                 # 打印 plan（dry-run）
  python3 fact_verify.py --apply         # 写库 + 回读校验
种子：FOOD_FACT_SEED 指定，否则 /app/data/fact_verify/claims_seed.json。
"""
import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C  # noqa: E402

ALLOWED = {
    "chain_type": {"独立店", "小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"无", "疑似", "确认"},
    "premade_risk": {"无", "低", "疑似", "高"},
    "food_safety": {"无", "疑似", "确认"},
}
FIELD_ORDER = ("chain_type", "central_kitchen", "premade_risk", "food_safety")


def seed_path():
    p = os.environ.get("FOOD_FACT_SEED")
    if p:
        return pathlib.Path(p)
    for cand in ("/app/data/fact_verify/claims_seed.json",
                 HERE.parent / "research" / "fact_verify" / "claims_seed.json"):
        q = pathlib.Path(cand)
        if q.exists():
            return q
    raise SystemExit("找不到 claims_seed.json（设 FOOD_FACT_SEED）")


def match_ids(rests, contains):
    out = []
    for r in rests:
        names = [r.get("name", "")] + list(r.get("aliases") or [])
        if any(contains in n for n in names if n):
            out.append(r)
    return out


def merge_claims(existing, new_claims):
    seen = {(c.get("type"), c.get("source_url")) for c in existing}
    merged = list(existing)
    for c in new_claims:
        k = (c.get("type"), c.get("source_url"))
        if k not in seen:
            merged.append(c)
            seen.add(k)
    return merged


def build_plan():
    seed = json.loads(seed_path().read_text(encoding="utf-8"))
    rests = C.fetch_all(
        "restaurants",
        "id,name,aliases,chain_type,central_kitchen,premade_risk,food_safety,fact_claims,status")
    plan = []
    for b in seed["brands"]:
        # 校验字段值域
        for f, v in b["fields"].items():
            if f not in ALLOWED:
                raise SystemExit(f"{b['brand']}: 未知字段 {f}")
            if v not in ALLOWED[f]:
                raise SystemExit(f"{b['brand']}: {f}={v} 非法，允许 {sorted(ALLOWED[f])}")
        targets = match_ids(rests, b["match_contains"])
        if not targets:
            print(f"⚠ 未匹配到门店：{b['brand']}（contains={b['match_contains']}）")
            continue
        for r in targets:
            field_patch = {f: b["fields"][f] for f in FIELD_ORDER
                           if f in b["fields"] and r.get(f) != b["fields"][f]}
            merged = merge_claims(r.get("fact_claims") or [], b["claims"])
            claim_changed = len(merged) != len(r.get("fact_claims") or [])
            if field_patch or claim_changed:
                plan.append({"id": r["id"], "name": r["name"], "fields": field_patch,
                             "new_claims": len(merged) - len(r.get("fact_claims") or []),
                             "total_claims": len(merged), "merged_claims": merged})
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    plan = build_plan()
    if not plan:
        print("无待变更（已全部生效，幂等）。")
        return
    print(f"=== fact_verify {'APPLY' if args.apply else 'DRY-RUN'}：{len(plan)} 店 ===")
    for x in plan:
        print(f"  id={x['id']} {x['name']}")
        if x["fields"]:
            print(f"     fields={x['fields']}")
        print(f"     claims +{x['new_claims']} -> 共{x['total_claims']}")
    if not args.apply:
        print("\n加 --apply 写库。")
        return
    for x in plan:
        body = dict(x["fields"])
        body["fact_claims"] = x["merged_claims"]
        r = C.req("PATCH", f"/restaurants?id=eq.{x['id']}", json=body)
        r.raise_for_status()
        got = C.fetch_all("restaurants", "id,chain_type,central_kitchen,premade_risk,"
                          "food_safety,fact_claims,is_chain_standardized",
                          extra=f"id=eq.{x['id']}")
        assert got, f"id={x['id']} 回读为空"
        g = got[0]
        for f, v in x["fields"].items():
            assert g.get(f) == v, f"id={x['id']} {f} 回读 {g.get(f)} != {v}"
        assert len(g.get("fact_claims") or []) == x["total_claims"], \
            f"id={x['id']} claims 回读数不符"
        print(f"  ✓ id={x['id']} std={g['is_chain_standardized']} claims={len(g['fact_claims'])}")
    print(f"\n完成：{len(plan)} 店已写并回读校验。")


if __name__ == "__main__":
    main()

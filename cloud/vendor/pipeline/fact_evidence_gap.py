#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_evidence_gap.py — 事实层「硬标签必须有可溯源证据」质量门（只读）。

北极星 A2（真实可溯、宁空不假）+ 事实层独立轴原则：
  chain_type(规模) 与 central_kitchen/premade_risk/food_safety(生产/事实) 是两条独立轴。
  硬标签（central_kitchen=确认 / premade_risk=高 / food_safety=确认）必须在
  fact_claims 中存在「同 type 且带 source_url」的主张；否则就是词表/规则裸断言，
  必须降级为「疑似」或补取证，禁止无证据硬标签。

用法（容器内先 . /app/cloud/env.sh）：
  python fact_evidence_gap.py            # 打印缺口，落 fact_evidence_gap.json
  python fact_evidence_gap.py --strict   # 有缺口时 exit 1（供 release_audit 调用）
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C  # noqa: E402

# 硬标签值 → 需要存在证据的 claim type
HARD = {
    "central_kitchen": "确认",
    "premade_risk": "高",
    "food_safety": "确认",
}


def evidenced_types(fact_claims):
    """返回已有带 source_url 证据的 claim type 集合。"""
    out = set()
    for c in fact_claims or []:
        if c.get("source_url") and c.get("type"):
            out.add(c["type"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all(
        "restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,food_safety,fact_claims",
        order_col="id")
    gaps = []
    for r in rests:
        if r.get("status") != "active":
            continue
        ev = evidenced_types(r.get("fact_claims"))
        missing = []
        for field, hard_val in HARD.items():
            if r.get(field) == hard_val and field not in ev:
                missing.append(field)
        if missing:
            gaps.append({"id": r["id"], "name": r["name"],
                         "chain_type": r.get("chain_type"),
                         "values": {f: r.get(f) for f in missing},
                         "n_claims": len(r.get("fact_claims") or [])})

    print(f"=== fact_evidence_gap：{len(gaps)} 家硬标签缺证据 ===")
    for g in gaps:
        print(f"  id={g['id']} {g['name'][:34]:34s} {g['values']} claims={g['n_claims']}")

    out = {"generated_at": C.today(), "n_gap": len(gaps), "gaps": gaps}
    pathlib.Path("fact_evidence_gap.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已落 fact_evidence_gap.json")

    if gaps:
        print("处理：对这些店逐品牌搜索取证→扩 claims_seed→fact_verify --apply；"
              "取不到证据则降级为疑似。")
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()

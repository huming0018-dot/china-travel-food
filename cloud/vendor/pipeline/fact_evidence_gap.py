#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_evidence_gap.py — 事实层「硬标签必须有可溯源证据」质量门。

北极星 A2（真实可溯、宁空不假）+ 事实层独立轴原则：
  chain_type(规模) 与 central_kitchen/premade_risk/food_safety(生产/事实) 是两条独立轴。
  hard label（central_kitchen=确认 / premade_risk=高 / food_safety=确认）必须在
  fact_claims 中存在「同 type 且带 source_url」的主张；否则就是词表/规则裸断言，
  必须降级为「疑似」或补取证，禁止无证据硬标签。

用法（容器内先 . /app/cloud/env.sh）：
  python fact_evidence_gap.py            # 打印缺口，落 fact_evidence_gap.json（只读，默认）
  python fact_evidence_gap.py --strict   # 有缺口时 exit 1（供 release_audit 调用）
  python fact_evidence_gap.py --apply    # 确定性降级：无证据硬标签 -> 疑似，幂等，写后回读

--apply 规则（机制优先、宁空不假，不手工补单店）：
  1. 仅处理 status=active 的店；
  2. 缺「同 type 且带 source_url」证据的硬标签，一律降为「疑似」；
  3. 同时在 fact_claims 追加一条治理留痕，**source_url 留空**——
     evidenced_types 只认带 source_url 的主张，故该留痕不会被当成证据、门不被绕过；
  4. 每次降级追加落盘 fact_evidence_downgrade.jsonl（审计轨迹），并回读校验；
  5. 幂等：已降级的店再次运行不再产生缺口。
"""
import argparse
import datetime
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
# 无证据硬标签的降级目标（与库值域对齐）
DOWNGRADE_TO = {
    "central_kitchen": "疑似",
    "premade_risk": "疑似",
    "food_safety": "疑似",
}


def evidenced_types(fact_claims):
    """返回已有带 source_url 证据的 claim type 集合（治理留痕 source_url 为空，不计入）。"""
    out = set()
    for c in fact_claims or []:
        if c.get("source_url") and c.get("type"):
            out.add(c["type"])
    return out


def collect_gaps(rests):
    gaps = []
    for r in rests:
        if r.get("status") != "active":
            continue
        ev = evidenced_types(r.get("fact_claims"))
        missing = [f for f, hard_val in HARD.items()
                   if r.get(f) == hard_val and f not in ev]
        if missing:
            gaps.append({"id": r["id"], "name": r["name"],
                         "chain_type": r.get("chain_type"),
                         "values": {f: r.get(f) for f in missing},
                         "n_claims": len(r.get("fact_claims") or [])})
    return gaps


def apply_downgrades(gaps, rests_by_id, ledger):
    """把缺口硬标签确定性降为「疑似」，写治理留痕，PATCH 后回读。返回 (改店数, 改字段数)。"""
    today = C.today()
    shops = fields = 0
    for g in gaps:
        rid = g["id"]
        r = rests_by_id[rid]
        patch = {}
        claims = list(r.get("fact_claims") or [])
        for field, old_val in g["values"].items():
            new_val = DOWNGRADE_TO[field]
            patch[field] = new_val
            # 治理留痕：不带 source_url，故不构成证据，仅记录为何降级、可追溯。
            claims.append({
                "type": field,
                "value": new_val,
                "confidence": "low",
                "date": today,
                "source_url": "",
                "quote": f"自动降级：原硬标签「{old_val}」无同 type 带 source_url 证据"
                         f"（fact_evidence_gap --apply，宁空不假）",
            })
            fields += 1
        patch["fact_claims"] = claims
        resp = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=patch,
                    headers={**C.headers(), "Prefer": "return=minimal"})
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] id={rid} {g['name'][:24]} PATCH {resp.status_code}: "
                  f"{resp.text[:160]}")
            continue
        # 回读校验
        chk = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,{','.join(g['values'].keys())}").json()
        ok = chk and all(chk[0].get(f) == DOWNGRADE_TO[f] for f in g["values"])
        if not ok:
            print(f"  [VERIFY-FAIL] id={rid} 回读={chk}")
            continue
        shops += 1
        ledger.append({"date": today, "id": rid, "name": g["name"],
                       "downgraded": {f: {"from": g["values"][f], "to": DOWNGRADE_TO[f]}
                                      for f in g["values"]}})
        print(f"  [OK] id={rid} {g['name'][:30]:30s} {list(g['values'])} -> 疑似")
    return shops, fields


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="有缺口 exit 1（release_audit 用）")
    ap.add_argument("--apply", action="store_true",
                    help="无证据硬标签确定性降为疑似（默认 dry-run 只读）")
    args = ap.parse_args()

    rests = C.fetch_all(
        "restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,food_safety,fact_claims",
        order_col="id")
    rests_by_id = {r["id"]: r for r in rests}
    gaps = collect_gaps(rests)

    print(f"=== fact_evidence_gap：{len(gaps)} 家硬标签缺证据 ===")
    for g in gaps:
        print(f"  id={g['id']} {g['name'][:34]:34s} {g['values']} claims={g['n_claims']}")

    out = {"generated_at": C.today(), "n_gap": len(gaps), "gaps": gaps}
    pathlib.Path("fact_evidence_gap.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.apply and gaps:
        ledger_path = pathlib.Path("fact_evidence_downgrade.jsonl")
        ledger = []
        if ledger_path.exists():
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        ledger.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        print(f"\n--- --apply：降级 {len(gaps)} 家无证据硬标签 ---")
        shops, fields = apply_downgrades(gaps, rests_by_id, ledger)
        with ledger_path.open("a", encoding="utf-8") as fh:
            for rec in ledger[-shops:] if shops else []:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"降级完成：{shops} 店 / {fields} 个字段；审计轨迹 fact_evidence_downgrade.jsonl")
        # 重新计算缺口（理论为 0）
        rests2 = C.fetch_all(
            "restaurants",
            "id,name,status,central_kitchen,premade_risk,food_safety,fact_claims",
            order_col="id")
        gaps2 = collect_gaps(rests2)
        print(f"降级后剩余缺口：{len(gaps2)}")
        gaps = gaps2
        out = {"generated_at": C.today(), "n_gap": len(gaps), "gaps": gaps,
               "applied": {"shops": shops, "fields": fields}}
        pathlib.Path("fact_evidence_gap.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    elif gaps:
        print("处理：--apply 自动降级为疑似；或逐品牌搜索取证→扩 claims_seed→"
              "fact_verify --apply 补同 type 带 URL 证据。")

    if gaps:
        if args.strict:
            sys.exit(1)
    else:
        print("PASS：硬标签证据缺口 = 0")


if __name__ == "__main__":
    main()

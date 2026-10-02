#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tool_router.py — 能力路由器：给定数据任务，输出最优工具链 plan（默认只规划、不执行、不花钱）。

用法：
  python3 tool_router.py --family C_taste --fields reviews --entity "店名"
  python3 tool_router.py --family B_facts --fields phone,location --health
  python3 tool_router.py --task '{"family":"D_events","fields":["event_note"]}'

规则（见 CRAWLER-MODULE-SPEC §9）：
  - 仅保留 provides[family] 覆盖全部 required fields 的可行工具；
  - 按数据族内置策略链排序（免费/0结果优先 → flat → 全文兜底），健康死亡工具剔除；
  - 模型只做语义，机械选路确定性；--health 实时读 Apify 额度，失败静默按 unknown。
"""
import argparse, json, os, pathlib, sys, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REG = HERE / "tool_registry.json"

# 数据族 → 首选工具链（顺序即优先级）；未列到的可行工具自动追加为额外兜底。
CHAIN_POLICY = {
    "A_universe": ["michelin_public", "blackpearl_public", "ark_fleet", "bili_monitor", "kol_cross_wechat"],
    "B_facts": ["amap_rest", "tencent_rest", "smartshanghai"],
    "C_taste": ["apify_atomus", "apify_opspilot", "apify_sian", "xhs_sig"],
    "D_events": ["apify_atomus", "apify_opspilot", "apify_sian", "bili_monitor"],
    "E_relations": ["ark_fleet", "michelin_public"],
}
# 每步付费 run 的默认封顶（USD）与日预算
PER_RUN_CHARGE_CAP = 0.30
DAILY_CAP = float(os.environ.get("APIFY_DAILY_CAP", "10") or 10)


def load_tools():
    reg = json.loads(REG.read_text(encoding="utf-8"))
    return {t["tool_id"]: t for t in reg["tools"]}


def apify_remaining():
    """最佳努力读 Apify 余量；无 token/失败返回 None（unknown）。"""
    tok = os.environ.get("APIFY_TOKEN") or os.environ.get("TOKEN")
    if not tok:
        for p in [pathlib.Path("/home/ubuntu/food-apify-fill/fill.env")]:
            if p.exists():
                for line in p.read_text().splitlines():
                    if line.startswith(("APIFY_TOKEN=", "TOKEN=")):
                        tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not tok:
        return None
    try:
        u = "https://api.apify.com/v2/users/me/limits?token=" + tok
        with urllib.request.urlopen(u, timeout=20) as r:
            d = json.load(r)["data"]
        return round(d["limits"]["maxMonthlyUsageUsd"] - d["current"]["monthlyUsageUsd"], 2)
    except Exception:
        return None


def feasible(tool, family, fields):
    have = tool.get("provides", {}).get(family, [])
    return all(f in have for f in fields)


def cost_label(tool):
    c = tool["cost"]
    if c["type"] == "free":
        return "free"
    if c["type"] == "flat":
        return f"flat ${c['unit']}/run"
    if c["type"] == "per_result":
        return "per_result (0结果=$0)"
    return c["type"]


def plan(family, fields, entity=None, use_health=False):
    tools = load_tools()
    remain = apify_remaining() if use_health else None
    ok = {tid: t for tid, t in tools.items() if feasible(t, family, fields)}

    ordered, seen = [], set()
    for tid in CHAIN_POLICY.get(family, []):
        if tid in ok and tid not in seen:
            ordered.append(tid); seen.add(tid)
    for tid in ok:  # 策略未覆盖的可行工具 → 额外兜底
        if tid not in seen:
            ordered.append(tid); seen.add(tid)

    chain = []
    for i, tid in enumerate(ordered):
        t = ok[tid]
        health = "unknown"
        if tid.startswith("apify_"):
            if remain is not None:
                health = "ready" if remain > 0.2 else "no_credit"
        elif t["auth_level"] in ("L0", "L2"):
            health = "ready"
        step = {
            "step": i + 1, "tool_id": tid, "auth": t["auth_level"],
            "cost": cost_label(t), "ban_risk": t["ban_risk"],
            "reliability": t["reliability"], "health": health,
            "max_charge_usd": PER_RUN_CHARGE_CAP if tid.startswith("apify_") else 0,
            "note": t.get("boundary", ""),
        }
        chain.append(step)

    usable = [s for s in chain if s["health"] != "no_credit"]
    return {
        "task": {"family": family, "fields": fields, "entity": entity},
        "apify_remaining_$": remain,
        "daily_cap_$": DAILY_CAP,
        "primary": (usable[0]["tool_id"] if usable else None),
        "chain": chain,
        "usable_chain": [s["tool_id"] for s in usable],
        "fallback_rule": "前一步 0 结果/不足/健康死亡 → 自动进下一步；全部失败出缺口、不硬造",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", help="A_universe/B_facts/C_taste/D_events/E_relations")
    ap.add_argument("--fields", default="", help="逗号分隔，如 reviews,comment")
    ap.add_argument("--entity", default=None)
    ap.add_argument("--task", help="直接传 JSON 任务")
    ap.add_argument("--health", action="store_true")
    args = ap.parse_args()
    if args.task:
        t = json.loads(args.task)
        fam, fields, ent = t["family"], t.get("fields", []), t.get("entity")
    else:
        if not args.family:
            sys.exit("需要 --family 或 --task")
        fam = args.family
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
        ent = args.entity
    print(json.dumps(plan(fam, fields, ent, args.health), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

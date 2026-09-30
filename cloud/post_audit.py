#!/usr/bin/env python3
# post_audit.py — 模块B·长期自运行录后校验
# 以【店名】为圆心发散词云矩阵：店名 × {连锁/加盟/预制/中央厨房/料理包/人均/客单价/
#   老板/创始人/集团/控股/投资/关店/搬迁/避雷}，做轻量二次核查。
# 单一职责：消费「已带来源 URL 的 findings」，做确定性校验+挂标+账本；不自行联网搜索
#   （联网核查由 agent/general_search 完成，结果以 findings jsonl 喂入）。
# 红线：电话/坐标/营业时间一律不动；仅高置信(confidence>=0.8)变更；幂等可复跑；
#   dry-run 出计划，--apply 才写库，写后回读。
import argparse, json, pathlib, time, os, sys

sys.path.insert(0, "/app/pipeline")
import common as C

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)

# 允许挂标字段与枚举（与 fact_verify/chain_audit 对齐）
ALLOWED = {
    "chain_type": {"独立店", "小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"无", "疑似", "确认"},
    "premade_risk": {"无", "低", "疑似", "高"},
    "investor_info": None,   # 自由文本（背后集团/控股）
    "price_avg": None,       # 数值
    "food_safety": {"无", "疑似", "问题"},
}
KEYWORDS = ["连锁", "加盟", "预制", "中央厨房", "料理包", "人均", "客单价",
            "老板", "创始人", "集团", "控股", "投资", "关店", "搬迁", "避雷"]


def emit_targets(batch, offset=0):
    """轮换选取待复核店（按 id 取模 offset），输出词云矩阵 query 供 agent 核查。"""
    res = C.fetch_all("/restaurants", "id,name,status,chain_type,price_avg,investor_info",
                      order_col="id")
    act = [r for r in res if r.get("status") == "active"]
    pick = act[offset:offset + batch]
    out = []
    for r in pick:
        out.append({
            "restaurant_id": r["id"], "name": r["name"],
            "current": {k: r.get(k) for k in ("chain_type", "price_avg", "investor_info")},
            "queries": [f"{r['name']} 上海 {kw}" for kw in KEYWORDS],
        })
    return out


def apply_findings(findings_path, apply=False):
    rows = [json.loads(l) for l in open(findings_path, encoding="utf-8") if l.strip()]
    plan = []
    for f in rows:
        rid = f.get("restaurant_id")
        field = f.get("field")
        val = f.get("value")
        conf = float(f.get("confidence", 0))
        url = f.get("source_url", "")
        reason = f.get("reason", "")
        if not rid or field not in ALLOWED:
            continue
        if conf < 0.8 or not url.startswith("http"):
            continue  # 证据不足/无 URL 不改
        enum = ALLOWED[field]
        if enum and val not in enum:
            continue
        if field == "price_avg":
            try:
                val = float(val)
            except Exception:
                continue
        plan.append({"restaurant_id": rid, "field": field, "value": val,
                     "confidence": conf, "source_url": url, "reason": reason,
                     "captured_at": f.get("captured_at") or time.strftime("%Y-%m-%dT%H:%M:%S")})
    print(f"计划 {len(plan)} 条高置信变更（已过滤低置信/无URL/非法枚举）")
    if not apply:
        for p in plan:
            print(" DRY", p["restaurant_id"], p["field"], "->", p["value"], "|", p["source_url"][:60])
        return plan
    # 按店合并 patch
    by_rid = {}
    for p in plan:
        by_rid.setdefault(p["restaurant_id"], {}).update({p["field"]: p["value"]})
    ts = time.strftime("%Y-%m-%d")
    n = 0
    for rid, patch in by_rid.items():
        C.req("PATCH", f"/restaurants?id=eq.{rid}", json=patch)
        n += 1
        # 回读
        back = C.fetch_all("/restaurants", "id," + ",".join(patch.keys()),
                           extra=f"id=eq.{rid}")
        ledger = LEDGER / f"audit_{ts}.jsonl"
        with ledger.open("a", encoding="utf-8") as fh:
            for k, v in patch.items():
                fh.write(json.dumps({"restaurant_id": rid, "field": k, "value": v,
                                     "confidence": [p["confidence"] for p in plan if p["restaurant_id"] == rid and p["field"] == k][0],
                                     "source_url": [p["source_url"] for p in plan if p["restaurant_id"] == rid and p["field"] == k][0],
                                     "reason": [p["reason"] for p in plan if p["restaurant_id"] == rid and p["field"] == k][0],
                                     "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "readback": back[0] if back else None},
                                    ensure_ascii=False) + "\n")
        print(" APPLY", rid, patch)
    print(f"已写 {n} 店，账本 {LEDGER}/audit_{ts}.jsonl")
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", type=int, default=0, help="输出 N 家待复核店+词云矩阵")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--findings", default="")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.emit:
        json.dump(emit_targets(a.emit, a.offset), sys.stdout, ensure_ascii=False, indent=1)
        return
    if a.findings:
        apply_findings(a.findings, a.apply)


if __name__ == "__main__":
    main()

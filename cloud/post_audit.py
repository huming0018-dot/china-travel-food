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

# 允许挂标字段与枚举（canonical 审计词表，用于校验入参 findings）
ALLOWED = {
    "chain_type": {"独立店", "小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"无", "疑似", "确认"},
    "premade_risk": {"无", "低", "疑似", "高"},
    "investor_info": None,   # 自由文本（背后集团/控股）
    "price_avg": None,       # 数值
    "food_safety": {"无", "疑似", "问题"},  # canonical；落库映射见 DB_VALUE_MAP
}
# canonical 审计词表 -> 数据库实际 CHECK 允许值。
# restaurants.food_safety 的 CHECK 仅允许 无/疑似/确认（2026-10-12 实测，
# 写“问题”报 23514 check_violation）；审计语义“问题”=已确认食安事件，落“确认”。
DB_VALUE_MAP = {
    "food_safety": {"问题": "确认"},
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


def load_rows(path):
    """兼容 JSONL（逐行）与 JSON 数组（findings_ingest 的 candidates 产物）。"""
    text = pathlib.Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        return json.loads(text)
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def to_db_value(field, val):
    return DB_VALUE_MAP.get(field, {}).get(val, val)


def apply_findings(findings_path, apply=False):
    rows = load_rows(findings_path)
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
    # 按店合并（同 rid+field 取文件最后一条），值映射到 DB CHECK 词表
    by_rid = {}
    for p in plan:
        by_rid.setdefault(p["restaurant_id"], {})[p["field"]] = p
    ts = time.strftime("%Y-%m-%d")
    ledger = LEDGER / f"audit_{ts}.jsonl"
    n_store = applied_fields = 0
    failures = []
    for rid, fmap in by_rid.items():
        patch_db = {f: to_db_value(f, p["value"]) for f, p in fmap.items()}
        canon = {f: p["value"] for f, p in fmap.items()}
        src = {f: p["source_url"] for f, p in fmap.items()}
        rsn = {f: p["reason"] for f, p in fmap.items()}
        con = {f: p["confidence"] for f, p in fmap.items()}
        status_by_field = {}
        resp = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=patch_db)
        if resp.status_code in (200, 204):
            for f in patch_db:
                status_by_field[f] = resp.status_code
                applied_fields += 1
        else:
            # 整店原子 PATCH 被某列（如 CHECK 约束）整包回滚 -> 逐列降级，隔离坏列
            for f, v in patch_db.items():
                rr = C.req("PATCH", f"/restaurants?id=eq.{rid}", json={f: v})
                status_by_field[f] = rr.status_code
                if rr.status_code in (200, 204):
                    applied_fields += 1
                else:
                    failures.append((rid, f, canon[f], rr.status_code, rr.text[:160]))
        n_store += 1
        back = C.fetch_all("/restaurants", "id," + ",".join(patch_db.keys()),
                           extra=f"id=eq.{rid}")
        with ledger.open("a", encoding="utf-8") as fh:
            for f in patch_db:
                fh.write(json.dumps({"restaurant_id": rid, "field": f,
                                     "value": canon[f], "db_value": patch_db[f],
                                     "http": status_by_field.get(f),
                                     "confidence": con[f], "source_url": src[f],
                                     "reason": rsn[f],
                                     "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "readback": back[0] if back else None},
                                    ensure_ascii=False) + "\n")
        print(" APPLY", rid, status_by_field, patch_db)
    print(f"已处理 {n_store} 店 / {applied_fields} 字段，账本 {ledger}")
    if failures:
        print("!! 落库失败字段：")
        for x in failures:
            print("   FAIL", x)
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

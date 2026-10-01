#!/usr/bin/env python3
# findings_planner.py — 模块B·findings 生产端 planner
# 读取 active 门店 + 游标 cursor.json + 已审计 rid，按 id 轮转输出下一批（默认25店）
# 到 /app/data/post_record/batch.json；每店附四维查询模板。
# 纯只读、确定性、断点续跑。不联网（联网由调用方 agent/general_search 完成）。
import argparse, json, os, pathlib, sys, time

sys.path.insert(0, "/app/pipeline")
import common as C

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
CURSOR = LEDGER / "cursor.json"
BATCH_OUT = LEDGER / "batch.json"

# 四维查询模板（与 post_audit.ALLOWED 字段一一对应）
QUERIES = [
    ("chain",      "{name} 连锁 加盟 分店"),
    ("premade",    "{name} 预制菜 料理包 中央厨房"),
    ("price",      "{name} 人均 价格"),
    ("group",      "{name} 老板 所属集团 投资方"),
]


def load_done_rids():
    """从历史 audit_*.jsonl 收集已审计 rid（断点续跑依据）。"""
    done = set()
    for f in LEDGER.glob("audit_*.jsonl"):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    done.add(json.loads(line).get("restaurant_id"))
        except Exception:
            continue
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--from-cursor", action="store_true", default=True)
    a = ap.parse_args()

    res = C.fetch_all("/restaurants",
                      "id,name,name_en,district,business_area,status",
                      order_col="id")
    act = [r for r in res if r.get("status") == "active"]
    done = load_done_rids()

    cur = json.loads(CURSOR.read_text(encoding="utf-8")) if CURSOR.exists() else {"last_id": 0}
    last_id = cur.get("last_id", 0)

    # 轮转：从 last_id 之后取，跳过已审计；到末尾回卷到头部
    pool = [r for r in act if r["id"] > last_id and r["id"] not in done]
    wrapped = False
    if len(pool) < a.batch:
        wrapped = True
        pool += [r for r in act if r["id"] <= last_id and r["id"] not in done]

    pick = pool[: a.batch]
    out = []
    for r in pick:
        qs = []
        for tag, tmpl in QUERIES:
            qs.append({"tag": tag, "query": tmpl.format(name=r["name"])})
        out.append({
            "restaurant_id": r["id"],
            "name": r["name"],
            "name_en": r.get("name_en") or "",
            "district": r.get("district") or r.get("business_area") or "",
            "queries": qs,
        })

    BATCH_OUT.write_text(json.dumps({
        "date": time.strftime("%Y-%m-%d"),
        "from_last_id": last_id,
        "wrapped": wrapped,
        "size": len(out),
        "restaurants": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if pick:
        cur["last_id"] = pick[-1]["id"]
        CURSOR.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"planner: active={len(act)} done={len(done)} last_id={last_id} "
          f"wrapped={wrapped} picked={len(out)} -> {BATCH_OUT}")
    for r in out[:5]:
        print(" ", r["restaurant_id"], r["name"], r["district"])


if __name__ == "__main__":
    main()

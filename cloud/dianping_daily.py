#!/usr/bin/env python3
# dianping_daily.py — 点评 cookie 日更（chain/price/关店复查）
# 复用 dianping_branch_list 的 cookie；礼貌低频；cookie 失效/被拦 -> notifier 告警，不硬刷。
# 产出 findings.jsonl 供 07:47 post_audit --apply 消费；关店只写复查账本 + 通知，不自动 PATCH。
import json, pathlib, os, sys, time, random, re
sys.path.insert(0, "/app/pipeline")
import common as C
sys.path.insert(0, "/app/cloud")
import dianping_branch_list as DBL
import notifier as N

LEDGER = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data")) / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
FINDINGS = LEDGER / "findings.jsonl"
CHECKPOINT = LEDGER / "dianping_daily.done"

UA = DBL.UA


def main():
    res = C.fetch_all("/restaurants", "id,name,status,chain_type,price_avg", order_col="id")
    act = [r for r in res if r.get("status") == "active"]
    done = set()
    if CHECKPOINT.exists():
        done = {int(l.strip()) for l in CHECKPOINT.read_text().splitlines() if l.strip()}
    todo = [r for r in act if r["id"] not in done]
    print(f"[dianping_daily] active={len(act)} done={len(done)} todo={len(todo)}")

    findings = []
    closed_watch = []
    for i, r in enumerate(todo):
        rid, name = r["id"], r["name"]
        try:
            sig = DBL.chain_signal(name)
            n = sig.get("n_branches", 0)
            if n >= 2 and r.get("chain_type") != "小型连锁":
                findings.append({
                    "restaurant_id": rid, "name": name, "field": "chain_type",
                    "value": "小型连锁", "confidence": 0.9,
                    "source_url": sig.get("source_url", ""),
                    "source_title": f"点评分店列表 {n} 家",
                    "reason": f"点评同名分店 {n} 家异址",
                    "search_date": time.strftime("%Y-%m-%d"),
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
            # 关店复查（点评卡片若显示暂停/已关闭）
            for b in sig.get("branches", []):
                if re.search(r"已关闭|暂停营业|停业", b.get("branch_name", "") + b.get("address", "")):
                    closed_watch.append({"rid": rid, "name": name, "branch": b})
        except Exception as e:
            print(f"  err rid={rid} {type(e).__name__}")
        # checkpoint fsync
        with CHECKPOINT.open("a") as fh:
            fh.write(f"{rid}\n")
        time.sleep(random.uniform(1.5, 3.0))
        if (i + 1) % 20 == 0:
            print(f"  progress {i+1}/{len(todo)} findings={len(findings)} closed_watch={len(closed_watch)}")

    # append findings (dedup)
    seen = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text().splitlines():
            if l.strip():
                d = json.loads(l)
                seen.add((d.get("restaurant_id"), d.get("field"), d.get("source_url")))
    new = [f for f in findings if (f["restaurant_id"], f["field"], f["source_url"]) not in seen]
    with FINDINGS.open("a") as fh:
        for f in new:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    print(f"[dianping_daily] new_findings={len(new)} closed_watch={len(closed_watch)}")

    if closed_watch:
        N.send("ACTION", f"点评发现 {len(closed_watch)} 家疑似关店，待 host 侧确认三要素："
                          + "; ".join(f"{c['name']}(rid{c['rid']})" for c in closed_watch[:10]))


if __name__ == "__main__":
    main()

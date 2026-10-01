#!/usr/bin/env python3
# reconcile.py — 采集→入库→打标→精选层重算 链式闭环（幂等、可自运行）
# 状态转移契约：
#   central_kitchen=确认 或 premade_risk=高  -> 自动 is_curated=false + curate_reason（硬规则先于模型）
#   疑似预制/CK                              -> 置信封顶、hold，不自动入精选
#   chain_type 打标                          -> 不自动下架，驱动筛选与模型特征
#   price_avg/investor_info/group/status     -> 各有明确落位
#   ML 口味门（curate_v4）仍需跑赢基线+用户确认，reconcile 不自动套用
import json, pathlib, sys, os, time, datetime
sys.path.insert(0, "/app/pipeline")
import common as C

LEDGER = pathlib.Path("/app/data/post_record")
FINDINGS = LEDGER / "findings.jsonl"
RUN = LEDGER / "reconcile_run.jsonl"


def ingest():
    """findings.jsonl -> 按 field 分组，返回 {rid: {field: (value, conf, url)}}"""
    out = {}
    if not FINDINGS.exists(): return out
    for l in FINDINGS.read_text().splitlines():
        if not l.strip(): continue
        d = json.loads(l)
        rid = d.get("restaurant_id")
        f = d.get("field")
        conf = d.get("confidence", 0)
        if not rid or not f or conf < 0.8: continue
        out.setdefault(rid, {})[f] = (d["value"], conf, d.get("source_url", ""))
    return out


def reconcile(apply=False):
    findings = ingest()
    rests = C.fetch_all("/restaurants",
        "id,name,is_curated,chain_type,central_kitchen,premade_risk,price_avg,investor_info,status",
        order_col="id")
    changes = {"curated_off": [], "chain_set": [], "price_set": [], "investor_set": []}
    for r in rests:
        rid = r["id"]
        cur = findings.get(rid, {})
        # price / investor / chain 落位
        if "price_avg" in cur:
            val = cur["price_avg"][0]
            if r.get("price_avg") != val:
                changes["price_set"].append((rid, r.get("price_avg"), val))
                if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"price_avg": val})
        if "investor_info" in cur:
            val = cur["investor_info"][0]
            if r.get("investor_info") != val:
                changes["investor_set"].append((rid, val[:40]))
                if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"investor_info": val})
        if "chain_type" in cur:
            val = cur["chain_type"][0]
            if r.get("chain_type") != val:
                changes["chain_set"].append((rid, r.get("chain_type"), val))
                if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"chain_type": val})
        # 硬规则：ck=确认 或 premade=高 -> 移出精选
        hard_off = (r["central_kitchen"] == "确认" or r["premade_risk"] == "高")
        if hard_off and r["is_curated"]:
            changes["curated_off"].append((rid, r["central_kitchen"], r["premade_risk"]))
            if apply:
                reason = "中央厨房确认，移出精选" if r["central_kitchen"] == "确认" else "预制风险高，移出精选"
                C.req("PATCH", f"/restaurants?id=eq.{rid}",
                      json={"is_curated": False, "curate_reason": reason})
    return changes


def verify():
    """回读断言：硬规则店必须 is_curated=false"""
    rests = C.fetch_all("/restaurants", "id,is_curated,central_kitchen,premade_risk")
    bad = [r["id"] for r in rests
           if r["is_curated"] and (r["central_kitchen"] == "确认" or r["premade_risk"] == "高")]
    return bad


def main():
    apply = "--apply" in sys.argv
    ch = reconcile(apply=apply)
    bad = verify()
    summary = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "apply": apply,
        "changes": {k: len(v) for k, v in ch.items()},
        "verify_hard_rule_violations": bad,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    with RUN.open("a") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

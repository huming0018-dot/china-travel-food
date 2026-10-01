#!/usr/bin/env python3
# reconcile.py — 统一编排整条链（Python 编排，不靠 cron &&）
# ingest -> post_audit -> curate_reconcile -> verify -> notifier 漏斗报告
# 阶段失败阻断下游 + TG/飞书告警 + 非零退出；幂等可重跑。
import json, pathlib, sys, os, time, datetime, subprocess
sys.path.insert(0, "/app/pipeline")
sys.path.insert(0, "/app/cloud")
import common as C
import notifier as N

LEDGER = pathlib.Path("/app/data/post_record")
FINDINGS = LEDGER / "findings.jsonl"
RUN = LEDGER / "reconcile_run.jsonl"


def stage_ingest():
    out = {}; n = 0
    if not FINDINGS.exists(): return out, 0
    for l in FINDINGS.read_text().splitlines():
        if not l.strip(): continue
        d = json.loads(l); n += 1
        rid = d.get("restaurant_id"); f = d.get("field")
        conf = d.get("confidence", 0)
        if not rid or not f or conf < 0.8: continue
        out.setdefault(rid, {})[f] = (d["value"], conf, d.get("source_url", ""))
    return out, n


def stage_post_audit():
    cmd = [sys.executable, "/app/cloud/post_audit.py",
           "--findings", str(FINDINGS), "--apply"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return r.returncode == 0, (r.stdout + r.stderr)[-500:]
    except Exception as e:
        return False, str(e)


def stage_curate(findings, apply=False):
    rests = C.fetch_all("/restaurants",
        "id,is_curated,chain_type,central_kitchen,premade_risk,price_avg,investor_info",
        order_col="id")
    ch = {"curated_off": [], "chain_set": [], "price_set": [], "investor_set": [], "hold_suspect": []}
    for r in rests:
        rid = r["id"]; cur = findings.get(rid, {})
        if "price_avg" in cur and r.get("price_avg") != cur["price_avg"][0]:
            ch["price_set"].append(rid)
            if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"price_avg": cur["price_avg"][0]})
        if "investor_info" in cur and r.get("investor_info") != cur["investor_info"][0]:
            ch["investor_set"].append(rid)
            if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"investor_info": cur["investor_info"][0]})
        if "chain_type" in cur and r.get("chain_type") != cur["chain_type"][0]:
            ch["chain_set"].append(rid)
            if apply: C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"chain_type": cur["chain_type"][0]})
        hard_off = (r["central_kitchen"] == "确认" or r["premade_risk"] == "高")
        if hard_off and r["is_curated"]:
            ch["curated_off"].append(rid)
            if apply:
                reason = "中央厨房确认，移出精选" if r["central_kitchen"] == "确认" else "预制风险高，移出精选"
                C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"is_curated": False, "curate_reason": reason})
        if r["central_kitchen"] == "疑似" or r["premade_risk"] == "疑似":
            ch["hold_suspect"].append(rid)
    return ch


def stage_verify(apply=False):
    rests = C.fetch_all("/restaurants", "id,is_curated,central_kitchen,premade_risk")
    bad = [r["id"] for r in rests if r["is_curated"] and (r["central_kitchen"] == "确认" or r["premade_risk"] == "高")]
    if apply and bad:
        for rid in bad:
            C.req("PATCH", f"/restaurants?id=eq.{rid}", json={"is_curated": False, "curate_reason": "verify 自动修复"})
        rests2 = C.fetch_all("/restaurants", "id,is_curated,central_kitchen,premade_risk")
        bad = [r["id"] for r in rests2 if r["is_curated"] and (r["central_kitchen"] == "确认" or r["premade_risk"] == "高")]
    total = sum(1 for r in rests if r["is_curated"])
    return bad, total


def main():
    apply = "--apply" in sys.argv
    t0 = time.time()
    findings, n_findings = stage_ingest()
    ok, audit_out = stage_post_audit() if apply else (True, "dry")
    if not ok:
        N.warn(f"reconcile 停在 post_audit：{audit_out[-200:]}", key="reconcile_stuck")
        sys.exit(1)
    ch = stage_curate(findings, apply=apply)
    bad, total = stage_verify(apply=apply)
    if bad:
        N.warn(f"reconcile verify 硬规则违规：{bad[:5]}", key="reconcile_verify")
        sys.exit(2)
    report = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z", "apply": apply,
        "findings_loaded": n_findings,
        "chain_set": len(ch["chain_set"]), "price_set": len(ch["price_set"]),
        "investor_set": len(ch["investor_set"]), "curated_off": len(ch["curated_off"]),
        "hold_suspect": len(ch["hold_suspect"]), "total_curated": total,
        "verify_bad": len(bad), "elapsed_s": round(time.time() - t0, 1),
    }
    if n_findings == 0:
        report["note"] = "无 findings（采集通道未跑或无新增）"
    elif not (ch["chain_set"] or ch["price_set"] or ch["investor_set"]):
        report["note"] = "findings 已落库，无新变更（幂等重跑）"
    N.info("reconcile 漏斗：" + json.dumps(report, ensure_ascii=False), key="reconcile_funnel")
    with RUN.open("a") as fh:
        fh.write(json.dumps(report, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

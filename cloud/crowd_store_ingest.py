#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crowd_store_ingest.py — 众包证据 → 店铺入库（审阅#13 收尾，迁移05）

链路：crowd_proofs(accepted) → crowd_store_evidence（按店聚合）
      └─ 匹配 restaurants → 更新 score_diner（≥3 条评分才动）
      └─ 无匹配 → crowd_store_candidates（待人工收录）

用法：
  export HTTPS_PROXY=http://127.0.0.1:7897
  export FOOD_APP_DIR="$(pwd)/app"
  python3 cloud/crowd_store_ingest.py --dry-run    # 只聚合预览不写库
  python3 cloud/crowd_store_ingest.py              # 执行入库 + INFO 推送
"""
import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common_core as core  # noqa: E402
import notifier  # noqa: E402

DATA = pathlib.Path(core.config("FOOD_DATA_DIR", "/app/data"))
INGEST_F = DATA / "crowd_store_ingest.jsonl"
REPORT_KEY = "crowd_store_ingest"
CADENCE = 3600


def _run_ingest(dry_run):
    try:
        r = core.req("POST", "/rpc/crowd_ingest_stores", json={"p_dry_run": dry_run})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        core.log("error", "crowd_ingest_stores RPC 失败", err=str(e))
        return {"ok": False, "error": str(e)}


def _fmt_report(res):
    evs = res.get("evidence") or []
    if res.get("dry_run"):
        body = [
            "🔍 众包入库预览（dry-run）",
            "──",
            f"证据店铺 {len(evs)} 家（未写库）",
        ]
        for e in evs[:10]:
            body.append(f"  {e.get('store_name')}: note {e.get('n_notes')} / rating {e.get('n_ratings')} avg {e.get('r_avg')}")
        if len(evs) > 10:
            body.append(f"  … 其余 {len(evs)-10} 家")
        return "\n".join(body)
    body = [
        "🏪 众包入库完成",
        "──",
        f"证据店铺 {res.get('evidence_count', 0)} 家 · 主库 score_diner 更新 {res.get('updated_restaurants', 0)} 家 · 新候选 {res.get('candidates', 0)} 家",
    ]
    if (res.get("updated_restaurants") or 0) > 0:
        body.append("（≥3 条真实评分才回写，防止 1 条污染）")
    if (res.get("candidates") or 0) > 0:
        body.append("新店候选 → crowd_store_candidates，待人工审核收录")
    return "\n".join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只聚合预览不写库")
    args = ap.parse_args()

    res = _run_ingest(args.dry_run)
    if not res.get("ok"):
        print("入库失败:", res)
        return 1

    report = _fmt_report(res)
    print(report)

    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dry_run": bool(args.dry_run),
        "evidence": res.get("evidence_count", 0),
        "updated_restaurants": res.get("updated_restaurants", 0),
        "candidates": res.get("candidates", 0),
    }
    try:
        with open(INGEST_F, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        core.log("warn", "入库落盘失败", err=str(e))

    if not args.dry_run:
        notifier.info(report, key=REPORT_KEY, cadence=CADENCE)
        print("[推送] INFO 已投递")
    return 0


if __name__ == "__main__":
    sys.exit(main())

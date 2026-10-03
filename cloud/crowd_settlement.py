#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crowd_settlement.py — 众包美食家 · 周期结算（审阅#13 结算闭环）

为什么存在（外部审阅 #13：评分/入库/结算未打通，"按条计酬"不可验证）：
  - 参与者回传的证据（note/rating accepted）累计在 crowd_proofs，但从未变成"钱"。
  - 本模块每周一自动跑 `crowd_settle(period)` 服务端聚合 → 生成结算行 → 报告推送，
    让"按条计酬"有账可查、可审计。

计酬规则（默认单价，可 UPDATE crowd_settlements 调整，下周期生效）：
  note   = 1 条有效收录证据 → ¥2.00/条
  rating = 1 条有效口味评分 → ¥1.00/条

用法：
  export HTTPS_PROXY=http://127.0.0.1:7897
  export FOOD_APP_DIR="$(pwd)/app"
  python3 cloud/crowd_settlement.py                 # 结算本周并推送（INFO）
  python3 cloud/crowd_settlement.py --period 2026-09-28   # 结算指定周一周期
  python3 cloud/crowd_settlement.py --dry-run       # 只打印不推送
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
SETTLE_F = DATA / "crowd_settlement.jsonl"
REPORT_KEY = "crowd_settlement"
CADENCE = 3600  # 每周结算属例行播报，60 分钟冷却防刷屏


def _run_settle(period):
    """调服务端 RPC crowd_settle，返回结算结果 dict。"""
    try:
        r = core.req("POST", "/rpc/crowd_settle", json={"p_period": period})
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        core.log("error", "crowd_settle RPC 失败", err=str(e))
        return {"ok": False, "error": str(e)}


def _fmt_report(res):
    rows = (res or {}).get("settled") or []
    total_amount = 0.0
    total_notes = 0
    total_ratings = 0
    lines = []
    for s in sorted(rows, key=lambda x: -(x.get("amount") or 0)):
        amt = float(s.get("amount") or 0)
        total_amount += amt
        total_notes += int(s.get("effective_notes") or 0)
        total_ratings += int(s.get("effective_ratings") or 0)
        lines.append(
            f"  {s.get('participant_id')} 笔记{s.get('effective_notes')} 评分{s.get('effective_ratings')} "
            f"→ ¥{amt:.2f} [{s.get('status')}]"
        )
    body = [
        "🧾 众包结算 · 周期 " + (res or {}).get("period", "-"),
        "──",
        f"参与者 {len(rows)} 人 · 有效笔记 {total_notes} 条 · 评分 {total_ratings} 条",
        f"应付合计 ¥{total_amount:.2f}（note ¥2/条 · rating ¥1/条，可调）",
    ]
    if lines:
        body.append("明细：")
        body.extend(lines)
    else:
        body.append("（本周期无 accepted 证据，无结算）")
    body.append("结算状态 pending → PM 确认后置 paid 打款")
    return "\n".join(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default=None, help="结算周期（周一日期 YYYY-MM-DD），默认本周")
    ap.add_argument("--dry-run", action="store_true", help="只打印不推送")
    args = ap.parse_args()

    res = _run_settle(args.period)
    if not res.get("ok"):
        print("结算失败:", res)
        return 1

    report = _fmt_report(res)
    print(report)

    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "period": res.get("period"),
        "participants": len(res.get("settled") or []),
        "amount": sum(float(s.get("amount") or 0) for s in (res.get("settled") or [])),
    }
    try:
        with open(SETTLE_F, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        core.log("warn", "结算落盘失败", err=str(e))

    if not args.dry_run:
        notifier.info(report, key=REPORT_KEY, cadence=CADENCE)
        print("[推送] INFO 已投递（冷却 3600s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crowd_tracking.py — 众包回流信息 tracking 报告（PM 窗口 · 2026-10-02）

为什么存在（AUDIT_V2 结论：回流数据无产出视角）：
  - 参与者回传后，看不到任务池推进、参与者活跃、数据质量、配额消耗。
  - 本模块每次从库实时聚合 crowd_proofs / crowd_participants / crowd_tasks，
    生成人类可读报告 → 落盘 JSONL（可回溯）→ notifier.info 柔和推送（不刷屏）。

设计原则（Lean Refactor / 统一底座）：
  - 只依赖 common_core（config/req/fetch_all/log）+ notifier（唯一通知出口）。
  - 不重复实现 HTTP/分页/脱敏；报告正文走 notifier.sanitize。
  - 默认 cadence 3600s：同一 key 心跳节流，避免打扰。

用法：
  export HTTPS_PROXY=http://127.0.0.1:7897
  export FOOD_APP_DIR="$(pwd)/app"
  python3 cloud/crowd_tracking.py                 # 生成报告并推送（INFO）
  python3 cloud/crowd_tracking.py --dry-run       # 只打印不推送
  python3 cloud/crowd_tracking.py --json          # 输出完整 JSON（供窗口/脚本消费）
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common_core as core  # noqa: E402
import notifier  # noqa: E402

DATA = pathlib.Path(core.config("FOOD_DATA_DIR", "/app/data"))
TRACK_F = DATA / "crowd_tracking.jsonl"
REPORT_KEY = "crowd_tracking"
CADENCE = 3600  # 心跳 60 分钟


# ────────────────────── 聚合（只读库） ──────────────────────
def _agg():
    """一次性拉取三表做内存聚合（几千行，开销可忽略）。"""
    participants = core.fetch_all("crowd_participants", "participant_id,status,quota_day,total_effective,reject_rate,applied_at,last_active_at", order_col="participant_id")
    tasks = core.fetch_all("crowd_tasks", "task_id,pack_type,status,kpi_min,progress,quota_day,updated_at", order_col="task_id")
    proofs = core.fetch_all("crowd_proofs", "participant_id,task_id,kind,gate_status,rating,created_at")

    # 任务池
    open_t = [t for t in tasks if t.get("status") == "open"]
    done = [t for t in tasks if t.get("status") == "fulfilled"]
    open_gap = sum(max(0, (t.get("kpi_min") or 0) - (t.get("progress") or 0)) for t in open_t)
    open_kpi = sum(t.get("kpi_min") or 0 for t in open_t)
    open_prog = sum(t.get("progress") or 0 for t in open_t)

    # 回流总量
    n_all = len(proofs)
    n_acc = sum(1 for p in proofs if p.get("gate_status") == "accepted")
    n_dup = sum(1 for p in proofs if p.get("gate_status") == "duplicate_skipped")
    n_rej = sum(1 for p in proofs if p.get("gate_status") == "rejected")
    n_rating = sum(1 for p in proofs if p.get("kind") == "rating")
    # 最近 24h 回流
    cutoff = time.time() - 86400
    day_acc = sum(1 for p in proofs
                  if p.get("gate_status") == "accepted"
                  and _ts(p.get("created_at")) >= cutoff)

    # 参与者活跃
    active_p = []
    for p in participants:
        if p.get("status") not in ("suspended", "blacklisted", "rejected"):
            pid = p.get("participant_id")
            mine = [x for x in proofs if x.get("participant_id") == pid]
            acc = sum(1 for x in mine if x.get("gate_status") == "accepted")
            rej = sum(1 for x in mine if x.get("gate_status") == "rejected")
            if acc or rej:
                active_p.append({
                    "id": pid, "acc": acc, "rej": rej,
                    "quota": p.get("quota_day"), "total": p.get("total_effective") or 0,
                    "last": p.get("last_active_at"),
                })
    active_p.sort(key=lambda x: -x["acc"])

    return {
        "ts": time.time(),
        "tasks": {"open": len(open_t), "done": len(done),
                  "open_prog": open_prog, "open_kpi": open_kpi, "open_gap": open_gap,
                  "pack_types": _pack_types(tasks)},
        "flow": {"all": n_all, "accepted": n_acc, "duplicate": n_dup,
                 "rejected": n_rej, "rating": n_rating, "day_accepted": day_acc,
                 "reject_rate": (n_rej / n_all if n_all else 0.0)},
        "participants": {"total": len(participants), "active": len(active_p),
                         "top": active_p[:5]},
    }


def _pack_types(tasks):
    d = {}
    for t in tasks:
        d[t.get("pack_type")] = d.get(t.get("pack_type"), 0) + 1
    return d


def _ts(v):
    """带时区解析（外部审计 #52：原实现去时区后按本地解释，24h 窗口漂移）"""
    try:
        from datetime import datetime, timezone
        s = str(v)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0


# ────────────────────── 报告正文（人类可读） ──────────────────────
def _n(v, default=0):
    """数值兜底：None/非法 → default（防表字段返回 null 崩溃）。"""
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _cnt(v, default=0):
    """长度兜底：对可能为 None/非容器的值安全取 len。"""
    try:
        return _n(len(v))
    except TypeError:
        return default


def render(a):
    t, f, p = a.get("tasks", {}), a.get("flow", {}), a.get("participants", {})
    open_t, done_t = _n(t.get("open")), _n(t.get("done"))
    lines = [
        f"📦 任务池 {open_t}个open/共{open_t + done_t} 已收{_cnt(t.get('pack_types'))}类",
        f"进度 {_n(t.get('open_prog'))}/{_n(t.get('open_kpi'))} 缺口{_n(t.get('open_gap'))}",
        f"↩️ 回流 {_n(f.get('accepted'))}有效/{_n(f.get('duplicate'))}去重/{_n(f.get('rejected'))}拒 评分{_n(f.get('rating'))}",
        f"近24h +{_n(f.get('day_accepted'))} 拒收率{round((float(f.get('reject_rate') or 0) * 100), 0):g}%",
    ]
    if _n(p.get("active")):
        top = "，".join(f"{x.get('id','?')[:8]} {_n(x.get('acc'))}条" for x in (p.get("top") or [])[:3])
        lines.append(f"👥 活跃 {_n(p.get('active'))}/{_n(p.get('total'))} 号（{top}）")
    else:
        lines.append(f"👥 活跃 0/{_n(p.get('total'))} 号（尚无有效回传）")
    return "\n".join(lines)


def render_json(a):
    return json.dumps(a, ensure_ascii=False, default=str)


# ────────────────────── 落盘（JSONL，可回溯） ──────────────────────
def _save(a):
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(TRACK_F, "a", encoding="utf-8") as f:
            f.write(json.dumps(a, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        core.log("warn", "tracking ledger write failed", err=repr(e)[:100])


# ────────────────────── CLI ──────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只打印不推送")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供脚本消费")
    ap.add_argument("--cadence", type=int, default=CADENCE, help="推送节流秒数")
    args = ap.parse_args()

    a = _agg()
    if args.json:
        print(render_json(a))
        return 0
    body = render(a)
    print(body)
    if args.dry_run:
        print("[dry-run] 未推送")
        return 0
    ok = notifier.info(body, key=REPORT_KEY, cadence=args.cadence,
                        footer=f"来源 crowd_tracking · {time.strftime('%m-%d %H:%M')}")
    _save(a)
    print("推送结果：", ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())

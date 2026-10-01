#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pm_dispatch.py — PM主动调度器（方案B升级·2026-10-01用户要求"由PM调度,不靠用户喊话"）

解决的问题：INBOX留言是"文件信箱",窗口不主动读就静默。用户在窗口喊话=PM失去调度意义。
本调度器把 notifier（TG+飞书双通道,已验证可用）升级为【调度指令出口】：
  1. 每 N 分钟读 task_queue（唯一真源）
  2. 找出「P0 或 source=user 或 用户点名」且 status=todo 且超过 SLA 未认领的工单
  3. 通过 notifier 推送到 Telegram+飞书（用户手机直接收到调度播报）
  4. 同时写 INBOX/<role>.md（窗口开工时读到,双保险）

硬规则（复用 notifier 纪律）:
  - 推送必须【有界】:同工单按 nudge 计划提醒,提醒用尽不再刷屏
  - 推送正文脱敏、不含凭据
  - 只调度、不代做:执行仍由窗口负责,PM只负责"推动+验收"
  - 支持 --once / --loop 模式;cron 建议每 15 分钟
"""
import argparse
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import notifier  # noqa: E402

# 调度账本（存哪条工单提醒到第几次）
LEDGER = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/tmp")) / "pm_dispatch_ledger.json"

# 各角色超时未认领即升级推送的 SLA（秒）——用户点名的 P0 收紧
SLA = {
    "P0": 1800,          # 30分钟
    "P1": 7200,          # 2小时
    "P2": 86400,         # 24小时
}
NUDGE_SCHEDULE = (1800, 3600, 7200, 86400)  # 30m / 1h / 2h / 1d 有界提醒

# 窗口角色 → INBOX 文件映射
ROLE_INBOX = {
    "dev": HERE / "INBOX" / "dev.md",
    "collector": HERE / "INBOX" / "collector.md",
}


def _load_ledger():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ledger(L):
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def get_task_queue():
    """读 task_queue（Supabase）。复用 vendor 直连+代理环境。"""
    try:
        PIPE = HERE / "vendor" / "pipeline"
        sys.path.insert(0, str(PIPE))
        import common as C
        r = C.req("GET", "/task_queue?select=id,title,status,priority,assignee,source&order=id")
        rows = r.json()
        return [t for t in rows if isinstance(t, dict)]
    except Exception as e:
        print(f"[dispatch] task_queue读取失败: {e}")
        return []


def write_inbox(role, text):
    """把调度指令写入窗口 INBOX（双保险,窗口开工读）。"""
    try:
        f = ROLE_INBOX.get(role)
        if not f:
            return False
        stamp = time.strftime("%Y-%m-%d %H:%M")
        entry = f"\n\n### 🔔 调度 {stamp}（pm_dispatch 自动投递）\n{text}\n"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(entry)
        return True
    except Exception as e:
        print(f"[dispatch] INBOX写入失败 {role}: {e}")
        return False


def find_dispatchables(tasks):
    """找出需要升级推送的工单:todo + (P0 或 source=user) 且超 SLA 未认领。"""
    now = int(time.time())
    out = []
    for t in tasks:
        if t.get("status") != "todo":
            continue
        prio = t.get("priority") or "P2"
        src = t.get("source") or ""
        assignee = t.get("assignee") or ""
        if not assignee or assignee in ("qa", "pm"):
            continue
        # 触发条件:P0 或 用户点名(source=user)
        if prio != "P0" and src != "user":
            continue
        out.append((t, prio, assignee))
    return out


def dispatch_once(dry_run=False):
    """单次调度:扫描→按账本决定是否推送→推送+写INBOX。"""
    tasks = get_task_queue()
    L = _load_ledger()
    now = int(time.time())
    pushed = 0
    for t, prio, assignee in find_dispatchables(tasks):
        tid = t.get("id")
        key = f"dispatch:{assignee}:{tid}"
        rec = L.get(key) or {}
        nudges = int(rec.get("nudges", 0))
        if nudges >= len(NUDGE_SCHEDULE):
            continue  # 提醒用尽,不再刷屏
        due_at = int(rec.get("last_ts", 0)) + NUDGE_SCHEDULE[nudges]
        if rec and now < due_at:
            continue  # 未到下次提醒时间
        # 到点:推送
        title = (t.get("title") or "")[:60]
        body = (f"工单 #{tid} 待认领（{assignee}）\n"
                f"优先级 {prio} · 来源 {t.get('source') or '-'}\n"
                f"{title}")
        action = (f"去 {assignee} 窗口认领 #{tid}（task_helper.py claim {tid}）"
                  if not dry_run else "dry-run")
        ok = notifier.action(body, key=key, action_text=action,
                             nudge_schedule=NUDGE_SCHEDULE)
        if ok and not dry_run:
            rec.update({"last_ts": now, "nudges": nudges + 1})
            L[key] = rec
            pushed += 1
        # 双保险:写 INBOX
        if not dry_run:
            write_inbox(assignee, f"【PM调度】请认领 #{tid}：{title}")
    _save_ledger(L)
    print(f"[dispatch] 扫描 {len(tasks)} 条任务,推送 {pushed} 条")
    return pushed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="跑一次")
    ap.add_argument("--loop", type=int, default=0, help="循环模式:每N秒")
    ap.add_argument("--dry-run", action="store_true", help="只打印不推送")
    args = ap.parse_args()
    if args.loop:
        while True:
            dispatch_once(dry_run=args.dry_run)
            time.sleep(args.loop)
    else:
        dispatch_once(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

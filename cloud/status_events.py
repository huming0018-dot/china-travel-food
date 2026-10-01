#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_events.py — 关键状态事件记录与通知

当关键状态变化时（Apify充值、账号登录、额度恢复等），
自动记录事件，供所有窗口开始工作时查看。

事件类型：
  apify_topup    — Apify额度充值/变化
  account_login  — 小红书账号登录成功/失效
  quota_recover  — API配额恢复
  server_status  — 服务器状态变化
  task_unblock   — 任务自动解锁

用法：
  python3 status_events.py add "apify_topup" "Apify充值$5" "collector"
  python3 status_events.py list              # 最近20条事件
  python3 status_events.py check_changes     # 自动检测状态变化并记录
"""
import sys, os, pathlib, json, time
from datetime import datetime, timezone, timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/app/pipeline")

CST = timezone(timedelta(hours=8))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
EVENTS_F = DATA / "status_events.jsonl"
SNAPSHOT_F = DATA / "status_snapshot.json"


def now_str():
    return datetime.now(CST).strftime("%m-%d %H:%M")


def add_event(event_type, message, source="system"):
    """记录一条事件"""
    EVENTS_F.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": time.time(),
        "time": now_str(),
        "type": event_type,
        "message": message,
        "source": source
    }
    with open(EVENTS_F, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    print(f"📡 事件已记录: [{event_type}] {message}")
    return event


def list_events(limit=20):
    """列出最近N条事件"""
    if not EVENTS_F.exists():
        return []
    lines = EVENTS_F.read_text(encoding="utf-8").strip().split("\n")
    events = []
    for line in lines[-limit:]:
        if line.strip():
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return list(reversed(events))  # 最新在前


def get_snapshot():
    """获取当前状态快照"""
    snap = {}
    # 1. Apify额度（如果有的话）
    try:
        apify_f = DATA / "apify_status.json"
        if apify_f.exists():
            snap["apify"] = json.loads(apify_f.read_text())
    except Exception:
        pass
    # 2. 账号状态
    try:
        pool_f = DATA / "_cookie_pool_state.json"
        if pool_f.exists():
            snap["accounts"] = json.loads(pool_f.read_text())
    except Exception:
        pass
    # 3. API配额
    try:
        ledger_f = DATA / "map_quota_ledger.json"
        if ledger_f.exists():
            snap["quota"] = json.loads(ledger_f.read_text())
    except Exception:
        pass
    return snap


def check_changes():
    """对比当前状态和上次快照，发现变化时记录事件"""
    current = get_snapshot()
    previous = {}
    if SNAPSHOT_F.exists():
        try:
            previous = json.loads(SNAPSHOT_F.read_text())
        except Exception:
            pass

    changes = []

    # 检查账号状态变化
    curr_acc = current.get("accounts", {})
    prev_acc = previous.get("accounts", {})
    for acc, info in curr_acc.items():
        curr_status = info.get("status", "?") if isinstance(info, dict) else "?"
        prev_info = prev_acc.get(acc, {})
        prev_status = prev_info.get("status", "?") if isinstance(prev_info, dict) else "?"
        if curr_status != prev_status and prev_status != "?":
            changes.append(("account_login", f"{acc}: {prev_status} → {curr_status}"))

    # 检查配额恢复
    curr_quota = current.get("quota", {}).get("keys", {})
    prev_quota = previous.get("quota", {}).get("keys", {})
    for key, rec in curr_quota.items():
        curr_dead = rec.get("dead_reason", "")
        prev_rec = prev_quota.get(key, {})
        prev_dead = prev_rec.get("dead_reason", "")
        if prev_dead and not curr_dead:
            changes.append(("quota_recover", f"{key}: 配额已恢复"))

    # 记录事件
    for ev_type, msg in changes:
        add_event(ev_type, msg, source="auto")

    # 保存当前快照
    SNAPSHOT_F.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")
    return changes


def format_events(events):
    """格式化事件列表"""
    if not events:
        return "(无新事件)"
    lines = []
    for e in events[:10]:
        icon = {
            "apify_topup": "💰",
            "account_login": "🔑",
            "quota_recover": "📊",
            "server_status": "🖥️",
            "task_unblock": "✅"
        }.get(e["type"], "📡")
        lines.append(f"{icon} {e['time']} {e['message']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 默认：列出最近事件
        events = list_events()
        print("=== 最近状态事件 ===")
        print(format_events(events))
    elif sys.argv[1] == "add":
        # add <type> <message> [source]
        ev_type = sys.argv[2]
        msg = sys.argv[3]
        source = sys.argv[4] if len(sys.argv) > 4 else "manual"
        add_event(ev_type, msg, source)
    elif sys.argv[1] == "check":
        # 自动检测变化
        changes = check_changes()
        if changes:
            print(f"检测到 {len(changes)} 个变化:")
            for t, m in changes:
                print(f"  [{t}] {m}")
        else:
            print("无状态变化")
    elif sys.argv[1] == "list":
        events = list_events(int(sys.argv[2]) if len(sys.argv) > 2 else 20)
        print(format_events(events))

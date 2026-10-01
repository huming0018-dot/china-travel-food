#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_helper.py — 跨角色任务队列管理

用法：
  python3 task_helper.py list              # 查看所有任务
  python3 task_helper.py list dev          # 查看分配给dev的任务
  python3 task_helper.py list todo          # 查看所有待办
  python3 task_helper.py claim <id>        # 认领任务（status→in_progress）
  python3 task_helper.py done <id>          # 完成任务（status→done）
  python3 task_helper.py block <id> <原因>  # 阻塞任务
  python3 task_helper.py add <标题> <assignee> <优先级>  # 新增任务
  python3 task_helper.py stats              # 统计概览
"""
import sys, os, pathlib, json

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", str(HERE / "vendor" / "pipeline")))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

# 本地开发时pipeline可能在上级目录
if not (PIPE / "common.py").exists():
    for candidate in [HERE.parent / "vendor" / "pipeline", HERE.parent / "pipeline"]:
        if (candidate / "common.py").exists():
            sys.path.insert(0, str(candidate))
            break

# 自动设置FOOD_APP_DIR（如果环境变量没设）
if not os.environ.get("FOOD_APP_DIR"):
    # 尝试找app/.env.local
    for candidate in [HERE.parent / "app", pathlib.Path.cwd() / "app"]:
        if (candidate / ".env.local").exists():
            os.environ["FOOD_APP_DIR"] = str(candidate)
            break

import common as C

TABLE = "/task_queue"

ASSIGNEE_CN = {"dev": "开发", "collector": "采集", "qa": "QA", "pm": "PM"}
STATUS_CN = {"todo": "待办", "in_progress": "进行中", "done": "已完成", "blocked": "阻塞", "cancelled": "已取消"}


def list_tasks(filter_val=None):
    path = TABLE + "?select=*&order=priority.asc,created_at.asc"
    if filter_val:
        if filter_val in ASSIGNEE_CN:
            path += f"&assignee=eq.{filter_val}"
        elif filter_val in STATUS_CN:
            path += f"&status=eq.{filter_val}"
        elif filter_val.startswith("P"):
            path += f"&priority=eq.{filter_val}"
    r = C.req("GET", path)
    tasks = r.json() if r.status_code == 200 else []
    if not tasks:
        print("（无任务）")
        return tasks
    print(f"{'ID':>4} {'优先级':>4} {'分配给':>6} {'状态':>8}  标题")
    print("-" * 70)
    for t in tasks:
        a = ASSIGNEE_CN.get(t["assignee"], t["assignee"])
        s = STATUS_CN.get(t["status"], t["status"])
        print(f"{t['id']:>4} {t['priority']:>4} {a:>6} {s:>8}  {t['title'][:40]}")
    return tasks


def claim(task_id):
    r = C.req("PATCH", f"{TABLE}?id=eq.{task_id}", json={"status": "in_progress"})
    if r.status_code == 200:
        print(f"✅ 任务 #{task_id} 已认领（进行中）")
    else:
        print(f"❌ 认领失败: {r.status_code} {r.text}")


def done(task_id):
    r = C.req("PATCH", f"{TABLE}?id=eq.{task_id}", json={"status": "done"})
    if r.status_code == 200:
        print(f"✅ 任务 #{task_id} 已完成")
    else:
        print(f"❌ 完成失败: {r.status_code} {r.text}")


def block(task_id, reason):
    r = C.req("PATCH", f"{TABLE}?id=eq.{task_id}", json={"status": "blocked", "description": reason})
    if r.status_code == 200:
        print(f"⚠️ 任务 #{task_id} 已阻塞: {reason}")
    else:
        print(f"❌ 阻塞失败: {r.status_code} {r.text}")


def auto_unblock():
    """自动检查被阻塞的任务，条件满足的自动解锁"""
    # 获取所有blocked任务
    r = C.req("GET", TABLE + "?select=id,title,description,assignee,status,priority&status=eq.blocked")
    blocked = r.json() if r.status_code == 200 else []
    if not blocked:
        print("✅ 无阻塞任务")
        return []

    # 检查当前环境状态
    import pathlib, json
    DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))

    unblocked = []
    for task in blocked:
        tid = task["id"]
        desc = task.get("description", "")
        title = task.get("title", "")
        combined = (title + " " + desc).lower()

        should_unblock = False
        reason = ""

        # 规则1：阻塞原因是"账号未登录/cookie失效"，现在账号状态变了
        if "账号" in combined or "cookie" in combined or "apify" in combined:
            # 检查Apify状态文件是否存在
            apify_f = DATA / "apify_status.json"
            if apify_f.exists():
                should_unblock = True
                reason = "Apify已配置"

        # 规则2：阻塞原因是"配额不足"，现在配额恢复了
        if "配额" in combined or "quota" in combined or "key" in combined:
            ledger_f = DATA / "map_quota_ledger.json"
            if ledger_f.exists():
                ledger = json.loads(ledger_f.read_text())
                keys = ledger.get("keys", {})
                all_dead = all(k.get("dead_reason") for k in keys.values())
                if not all_dead:
                    should_unblock = True
                    reason = "API配额已恢复"

        # 执行解锁
        if should_unblock:
            r2 = C.req("PATCH", f"{TABLE}?id=eq.{tid}",
                       json={"status": "todo", "description": f"自动解锁: {reason}"})
            if r2.status_code == 200:
                print(f"✅ 自动解锁 #{tid} {title[:30]} ({reason})")
                unblocked.append(task)
                # 记录事件
                try:
                    import status_events
                    status_events.add_event("task_unblock", f"#{tid} {title[:30]}", source="auto")
                except Exception:
                    pass
            else:
                print(f"❌ 解锁失败 #{tid}: {r2.text[:50]}")

    if not unblocked:
        print(f"ℹ️ {len(blocked)}个阻塞任务，暂不满足解锁条件")
    return unblocked


def add(title, assignee, priority="P1", description="", source="qa", issue_id=""):
    if assignee not in ASSIGNEE_CN:
        print(f"❌ assignee必须是: {list(ASSIGNEE_CN.keys())}")
        return
    if priority not in ("P0", "P1", "P2"):
        print(f"❌ priority必须是: P0/P1/P2")
        return
    body = {"title": title, "assignee": assignee, "priority": priority,
            "description": description, "source": source, "issue_id": issue_id}
    r = C.req("POST", TABLE, json=body)
    if r.status_code in (200, 201):
        print(f"✅ 任务已创建: [{priority}] {title} → {ASSIGNEE_CN[assignee]}")
    else:
        print(f"❌ 创建失败: {r.status_code} {r.text}")


def stats():
    r = C.req("GET", TABLE + "?select=id,title,assignee,status,priority")
    tasks = r.json() if r.status_code == 200 else []
    if not tasks:
        print("（无任务，表可能还没建）")
        return
    print("=== 任务统计 ===")
    by_assignee = {}
    by_status = {}
    for t in tasks:
        a = t["assignee"]
        s = t["status"]
        by_assignee[a] = by_assignee.get(a, 0) + 1
        by_status[s] = by_status.get(s, 0) + 1
    print("\n按角色:")
    for a, n in sorted(by_assignee.items()):
        print(f"  {ASSIGNEE_CN.get(a, a)}: {n}个")
    print("\n按状态:")
    for s, n in sorted(by_status.items()):
        print(f"  {STATUS_CN.get(s, s)}: {n}个")
    p0 = [t for t in tasks if t["priority"] == "P0" and t["status"] != "done"]
    if p0:
        print(f"\n🔴 P0未完成: {len(p0)}个")
        for t in p0:
            print(f"  #{t.get('id', '?')} {t['title'][:50]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "list":
        list_tasks(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "claim":
        claim(int(sys.argv[2]))
    elif cmd == "done":
        done(int(sys.argv[2]))
    elif cmd == "block":
        block(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else "")
    elif cmd == "add":
        title = sys.argv[2]
        assignee = sys.argv[3]
        priority = sys.argv[4] if len(sys.argv) > 4 else "P1"
        add(title, assignee, priority)
    elif cmd == "stats":
        stats()
    elif cmd == "unblock":
        auto_unblock()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)

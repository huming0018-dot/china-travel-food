#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_broadcast.py — QA统一播报入口

整合所有模块状态，生成一条紧凑播报，通过notifier发送到TG。
这是QA窗口的唯一对外播报出口，所有提醒都经过这里统一整理。

用法：
  python3 qa_broadcast.py           # 生成并发送一条完整播报
  python3 qa_broadcast.py --dry-run # 只打印不发送
  python3 qa_broadcast.py --action "需要用户做的事"  # 发ACTION级别提醒
"""
import sys, os, pathlib, json, time
from datetime import datetime, timezone, timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/app/pipeline")

CST = timezone(timedelta(hours=8))


def build_broadcast():
    """整合所有模块状态，生成播报正文"""
    lines = []

    # ── 1. 数据概览 ──
    try:
        import common as C
        active = C.fetch_all("restaurants", select="id,opening_hours,phone,score_taste", extra="status=eq.active")
        no_taste = sum(1 for r in active if not r.get("score_taste"))
        no_hours = sum(1 for r in active if not r.get("opening_hours"))
        lines.append(f"🍜 在营餐厅 {len(active)}家")
        lines.append(f"   口味分空 {no_taste}家 ({no_taste*100//len(active)}%)")
        lines.append(f"   营业时间空 {no_hours}家 ({no_hours*100//len(active)}%)")
    except Exception as e:
        lines.append(f"🍜 数据统计失败: {e}")

    # ── 2. 采集账号 ──
    try:
        DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
        pool_f = DATA / "_cookie_pool_state.json"
        pool = json.loads(pool_f.read_text(encoding="utf-8")) if pool_f.exists() else {}
        if pool:
            acc_parts = []
            for acc, info in pool.items():
                s = info.get("status", "?")
                icon = "🟢" if s == "active" else ("🔴" if s == "dead" else "🟡")
                acc_parts.append(f"{icon}{acc.replace('account_','')}:{s}")
            lines.append("📱 账号 " + " ".join(acc_parts))
    except Exception:
        pass

    # ── 3. API配额 ──
    try:
        DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
        ledger_f = DATA / "map_quota_ledger.json"
        ledger = json.loads(ledger_f.read_text(encoding="utf-8")) if ledger_f.exists() else {}
        keys = ledger.get("keys", {})
        if keys:
            quota_parts = []
            for kid, rec in keys.items():
                provider = rec.get("provider", "?")
                dead = rec.get("dead_reason", "")
                icon = "🔴" if dead else "🟢"
                if provider == "amap":
                    used = rec.get("monthly", {}).get("used", 0)
                    quota_parts.append(f"{icon}{kid.replace('amap:','高德')}:{used}/4500")
                else:
                    used = rec.get("daily", {}).get("used", 0)
                    quota_parts.append(f"{icon}{kid.replace('tencent:','腾讯')}:{used}/9000")
            lines.append("📊 配额 " + " ".join(quota_parts))
    except Exception:
        pass

    # ── 4. 任务队列 + 窗口状态 ──
    try:
        import task_helper
        tasks = task_helper.list_tasks()
        p0 = [t for t in tasks if t.get("priority") == "P0" and t.get("status") not in ("done", "cancelled")]
        todo = [t for t in tasks if t.get("status") == "todo"]
        doing = [t for t in tasks if t.get("status") == "in_progress"]
        done = [t for t in tasks if t.get("status") == "done"]
        total = len(tasks)
        done_pct = len(done) * 100 // total if total else 0
        lines.append(f"📌 项目进度: {done_pct}% ({len(done)}/{total}) · {len(todo)}待办/{len(doing)}进行中")
        if p0:
            for t in p0[:2]:
                lines.append(f"   🔴 P0 #{t.get('id','?')} {t.get('title','')[:25]}")
        # 各窗口当前状态（按任务统计）
        from collections import defaultdict
        by_role = defaultdict(lambda: {"todo": 0, "doing": 0})
        for t in tasks:
            a = t.get("assignee", "?")
            s = t.get("status", "?")
            if s == "todo":
                by_role[a]["todo"] += 1
            elif s == "in_progress":
                by_role[a]["doing"] += 1
        role_emoji = {"dev": "🔧", "collector": "🕷️", "qa": "🔍", "pm": "📋"}
        role_names = {"dev": "开发", "collector": "采集", "qa": "QA", "pm": "PM"}
        role_parts = []
        for role in ["dev", "collector", "qa", "pm"]:
            r = by_role.get(role, {"todo": 0, "doing": 0})
            emoji = role_emoji.get(role, "·")
            name = role_names.get(role, role)
            if r["doing"] > 0:
                role_parts.append(f"{emoji}{name}:做{r['doing']}")
            elif r["todo"] > 0:
                role_parts.append(f"{emoji}{name}:待{r['todo']}")
            else:
                role_parts.append(f"{emoji}{name}:空闲")
        lines.append("👥 " + " ".join(role_parts))
    except Exception as e:
        lines.append(f"📌 任务队列获取失败: {e}")

    # ── 5. 服务器 ──
    try:
        import subprocess
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().split("\n")[1].split()
        lines.append(f"💾 磁盘 {parts[2]}/{parts[1]} ({parts[4]})")
    except Exception:
        pass

    # ── 6. 未解决告警汇总 ──
    try:
        DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
        ledger_f = DATA / "notifier_ledger.json"
        ledger = json.loads(ledger_f.read_text(encoding="utf-8")) if ledger_f.exists() else {}
        open_warnings = []
        for key, rec in ledger.items():
            if rec.get("level") == "WARN" and rec.get("state", "open") == "open":
                open_warnings.append(key)
        if open_warnings:
            lines.append(f"⚠️ 待处理告警 {len(open_warnings)}个:")
            for w in open_warnings[:5]:
                lines.append(f"   · {w}")
    except Exception:
        pass

    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    action_idx = sys.argv.index("--action") if "--action" in sys.argv else -1
    action_text = sys.argv[action_idx + 1] if action_idx >= 0 and action_idx + 1 < len(sys.argv) else None

    body = build_broadcast()
    now = datetime.now(CST).strftime("%m-%d %H:%M")

    print(f"=== QA播报 · {now} ===")
    print(body)
    print("=" * 30)

    if dry_run:
        print("(dry-run模式，不发送)")
        return

    # 通过notifier发送
    try:
        import notifier
        if action_text:
            # ACTION级别：需要用户操作
            ok = notifier.action(body, key="qa_broadcast", action_text=action_text)
            print(f"ACTION发送: {'成功' if ok else '跳过(冷却中)'}")
        else:
            # INFO级别：例行播报
            ok = notifier.info(body, key="qa_broadcast", cadence=3600)
            print(f"INFO发送: {'成功' if ok else '跳过(冷却中)'}")
    except Exception as e:
        print(f"发送失败: {e}")
        # 降级：直接用health._telegram发
        try:
            import health
            header = f"📊 QA播报 · {now}"
            health._telegram(body, header)
            print("降级发送到TG成功")
        except Exception as e2:
            print(f"降级发送也失败: {e2}")


if __name__ == "__main__":
    main()

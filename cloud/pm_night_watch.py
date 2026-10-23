#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pm_night_watch.py — PM 夜间确定性监控（方案C·常驻腾讯云，2026-10-23）

替代 Deuce 本机 agent 定时任务（02点盘点 / 06点深度报告 / 07点录后校验）的
**确定性**部分，跑在腾讯云容器 food-cloud 的常驻 cron，不依赖任何设备睡眠/唤醒。
智能环节（自进化复盘、深度报告、录后搜索分片、周日 agent 分片）改由「开会话时
基于本脚本落盘的快照」生成，不在本无人值守脚本里做。

子命令：
  tick               每 20 分钟巡检：task_queue 盘点 + 新认领检测 +
                     未认领 P0/用户工单 nudge（复用 pm_dispatch，账本有界）+
                     关键采集管线活性元检查（独立看门狗，防止 watchdog 自身停摆）+
                     硬异常 WARN（notifier，按 key cooldown 有界）+ 写 latest/history。
  snapshot --tag 02  02:00 / 06:00 落带时间戳的夜间结构化快照（供智能复盘/报告引用）。
  morning            07:30 推送一条机械早间简报（整夜工单变化 + 活性 + 已知降级），每天一条。

纪律：
  - 只读 task_queue 与本地日志，绝不代窗口执行业务、不 patch 任何工单状态；
  - 推送全部走 notifier -> health -> external_watchdog.telegram_delivery（tg-relay），
    容器内禁直连 api.telegram.org、禁飞书；
  - 所有告警有界（warn cooldown / action nudge_schedule），安静时零打扰；
  - 状态/账本/快照只写 /app/data/pm_watch/（持久化 named volume，重建不丢）；
  - 已知持续降级（腾讯 key 耗尽、账号 dead、采集停滞）不重复 WARN，仅在简报陈述。
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline"))
for _p in (str(HERE), str(PIPE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
WATCH_DIR = DATA / "pm_watch"
LATEST = WATCH_DIR / "latest.json"
HISTORY = WATCH_DIR / "history.jsonl"

# 关键采集管线日志新鲜度阈值（分钟）。周期取自 /app/cloud/crontab.txt，阈值取 2~3 倍周期 + 缓冲。
LOG_STALE = {
    "watchdog.log": 35,    # 看门狗 :10/:30/:50（20min 周期）
    "router.log": 60,      # 浏览器轮候 */20（20min 周期）
    "amap_fill.log": 180,  # 高德 :15/:35/:55（每小时约 3 次）
    "phone_fill.log": 180, # 电话 :05/:25/:45（每小时约 3 次）
}
# 必须存活的进程（/proc 扫描，容器内无 ps 依赖）
PROC_MUST = ["cron", "gap_pool"]

WARN_COOLDOWN = 3600  # 同一硬告警 key 1 小时内不重复

import common as C  # noqa: E402
import notifier  # noqa: E402


def now():
    return int(time.time())


def iso(ts=None):
    return datetime.datetime.fromtimestamp(ts or now()).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.datetime.fromtimestamp(now()).strftime("%Y-%m-%d")


def fetch_tasks():
    """读 task_queue 全量；失败返回 None（区别于空列表）。"""
    try:
        r = C.req("GET",
                  "/task_queue?select=id,title,status,priority,assignee,source,updated_at&order=id")
        rows = r.json()
        return [t for t in rows if isinstance(t, dict)]
    except Exception as e:
        print("[nightwatch] task_queue 读取失败:", repr(e)[:140])
        return None


def proc_alive(needle):
    """扫 /proc/[pid]/cmdline 判断进程是否存活。"""
    for p in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
        except Exception:
            continue
        if needle in cmd and "pm_night_watch" not in cmd:
            return True
    return False


def log_age_minutes(fname):
    f = DATA / fname
    if not f.exists():
        return None
    return (now() - int(f.stat().st_mtime)) // 60


def tail_lines(fname, n=6):
    f = DATA / fname
    if not f.exists():
        return []
    try:
        return f.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:
        return []


def health_checks():
    """返回 {ok, checks, hard[(key,msg)], degraded[str]}。hard 触发有界 WARN，degraded 仅简报。"""
    checks = {}
    hard = []
    degraded = []

    # 1) 日志新鲜度（元监控：watchdog 自己若停摆，靠这里兜底发现）
    for fname, limit in LOG_STALE.items():
        age = log_age_minutes(fname)
        if age is None:
            checks[fname] = {"age_min": None, "ok": False}
            hard.append((f"stale:{fname}", f"{fname} 缺失（管线未产出或未挂载）"))
        else:
            ok = age <= limit
            checks[fname] = {"age_min": age, "ok": ok}
            if not ok:
                hard.append((f"stale:{fname}",
                             f"{fname} 已 {age} 分钟未更新（阈值 {limit} 分钟）"))

    # 2) 必备进程
    for proc in PROC_MUST:
        alive = proc_alive(proc)
        checks[f"proc:{proc}"] = {"alive": alive}
        if not alive:
            hard.append((f"proc:{proc}", f"必备进程 {proc} 未运行"))

    # 3) 已知降级（从 watchdog 最近输出解析，只陈述、不重复 WARN）
    wd = "\n".join(tail_lines("watchdog.log", 8))
    if "全尽" in wd:
        m = re.findall(r"解封(\d{2}-\d{2}\s*\d{2}:\d{2})", wd)
        degraded.append("腾讯地图 key 全尽（解封 " + (m[-1] if m else "见 watchdog") + "）")
    m = re.search(r"账号修复[：:]([^；;\n]+)", wd)
    if m and ("dead" in m.group(1) or "parked" in m.group(1)):
        degraded.append("XHS 账号状态：" + m.group(1).strip())
    if not any("XHS" in d for d in degraded) and "raw_xhs" in wd and "未增长" in wd:
        degraded.append("raw_xhs 采集停滞（见 watchdog/progress_broadcast）")
    wd_ok = any("OK" in ln for ln in tail_lines("watchdog.log", 2))
    checks["watchdog_last_ok"] = {"ok": wd_ok}

    return {"ok": not hard, "checks": checks, "hard": hard, "degraded": degraded}


def counts(tasks):
    out = {}
    for t in tasks:
        out[t.get("status")] = out.get(t.get("status"), 0) + 1
    return out


def load_prev():
    try:
        return json.loads(LATEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compact(t):
    return {"id": t.get("id"), "status": t.get("status"), "priority": t.get("priority"),
            "assignee": t.get("assignee"), "source": t.get("source"),
            "title": (t.get("title") or "")[:40]}


def build_state(tasks, health, extra=None):
    prev = load_prev()
    prev_status = {t["id"]: t.get("status") for t in prev.get("tasks", [])}

    new_claims = []
    for t in tasks:
        if t.get("status") == "in_progress" and prev_status.get(t["id"]) == "todo":
            new_claims.append({"id": t.get("id"), "title": t.get("title"),
                               "assignee": t.get("assignee")})

    # 满足 nudge 条件的待认领工单（与 pm_dispatch.find_dispatchables 同口径：
    # todo + (P0 或 source=user) + assignee 是可执行窗口，排除 pm/qa 自留）
    todo_p0_user = [
        {"id": t.get("id"), "title": (t.get("title") or "")[:50],
         "assignee": t.get("assignee"), "priority": t.get("priority"),
         "source": t.get("source")}
        for t in tasks
        if t.get("status") == "todo"
        and (t.get("priority") == "P0" or t.get("source") == "user")
        and (t.get("assignee") or "") not in ("", "qa", "pm")
    ]

    state = {
        "ts": now(), "iso": iso(), "counts": counts(tasks),
        "new_claims_since_prev": new_claims,
        "todo_p0_user": todo_p0_user,
        "health": health,
        "tasks": [compact(t) for t in tasks],
    }
    if extra:
        state.update(extra)
    return state


def save_state(state):
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(state, ensure_ascii=False) + "\n")


def emit_hard(hard):
    for key, msg in hard:
        try:
            notifier.warn("【PM 活性监控】" + msg +
                          "\n夜间确定性监控自动检出，请在下次开会话时核查。",
                          key=key, cooldown=WARN_COOLDOWN)
        except Exception as e:
            print("[nightwatch] warn 推送失败:", repr(e)[:100])


def run_nudge():
    """复用 pm_dispatch 有界 nudge（账本 /app/data/pm_dispatch_ledger.json）。"""
    try:
        import pm_dispatch
        return int(pm_dispatch.dispatch_once(dry_run=False))
    except Exception as e:
        print("[nightwatch] pm_dispatch 调用失败:", repr(e)[:120])
        return 0


def cmd_tick(_args):
    tasks = fetch_tasks()
    if tasks is None:
        try:
            notifier.warn("【PM 活性监控】task_queue 读取失败（Supabase 不可达？），无法盘点工单。",
                          key="watch:task_queue_unreachable", cooldown=WARN_COOLDOWN)
        except Exception:
            pass
        print("[nightwatch] tick 中止：task_queue 不可达（已按有界规则告警）")
        return 1
    health = health_checks()
    state = build_state(tasks, health)
    state["nudge_pushed"] = run_nudge()
    save_state(state)
    emit_hard(health["hard"])
    print(f"[nightwatch] tick {iso()} counts={state['counts']} "
          f"new_claims={len(state['new_claims_since_prev'])} "
          f"nudge={state['nudge_pushed']} hard={len(health['hard'])} "
          f"degraded={len(health['degraded'])}")
    return 0


def cmd_snapshot(args):
    tasks = fetch_tasks()
    if tasks is None:
        print("[nightwatch] snapshot 中止：task_queue 不可达")
        return 1
    health = health_checks()
    state = build_state(tasks, health, {"tag": args.tag})
    save_state(state)
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    f = WATCH_DIR / f"night_{today()}_{args.tag}.json"
    f.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[nightwatch] snapshot {args.tag} -> {f}")
    return 0


def cmd_morning(_args):
    tasks = fetch_tasks()
    if tasks is None:
        try:
            notifier.action("【早间简报】task_queue 读取失败，无法生成夜间报告，请人工核查 Supabase 连通。",
                            key=f"morning:fail:{today()}",
                            action_text="开会话核查容器到 Supabase 的连通性")
        except Exception as e:
            print("[nightwatch] morning fail push:", repr(e)[:100])
        return 1

    health = health_checks()
    state = build_state(tasks, health)

    # 基线：当天 02:00 快照（缺失则退化为仅报当前态）
    base = WATCH_DIR / f"night_{today()}_02.json"
    base_status = {}
    if base.exists():
        try:
            b = json.loads(base.read_text(encoding="utf-8"))
            base_status = {t["id"]: t.get("status") for t in b.get("tasks", [])}
        except Exception:
            pass

    changed = []
    for t in tasks:
        old = base_status.get(t["id"])
        if old and old != t.get("status"):
            changed.append(f"#{t['id']} {old}→{t.get('status')}（{(t.get('title') or '')[:18]}）")

    todo = [t for t in tasks if t.get("status") == "todo"]
    inp = [t for t in tasks if t.get("status") == "in_progress"]
    done = [t for t in tasks if t.get("status") == "done"]
    unclaimed = state["todo_p0_user"]

    lines = [f"🌙 夜间确定性监控简报 {today()}"]
    lines.append(f"工单：待办 {len(todo)} / 进行中 {len(inp)} / 已完成 {len(done)}（合计 {len(tasks)}）")
    if base_status:
        lines.append("夜间流转（02:00→现在）：" + ("；".join(changed) if changed else "无状态流转"))
    else:
        lines.append("夜间流转：无 02:00 基线快照，仅报当前态")
    if unclaimed:
        lines.append("待认领 P0/用户工单：" +
                     "；".join(f"#{x['id']}({x['assignee']})" for x in unclaimed))
    else:
        lines.append("待认领 P0/用户工单：无（符合 nudge 条件的工单均已认领）")
    lines.append("采集管线活性：" + ("✅ 正常" if health["ok"] else
                                  f"⚠️ 异常 {len(health['hard'])} 项（已按有界规则 WARN）"))
    for _, msg in health["hard"]:
        lines.append("  ⚠️ " + msg)
    if health["degraded"]:
        lines.append("已知降级（非新增）：" + "；".join(health["degraded"]))
    # 今日待补的智能环节（不在无人值守脚本执行，开会话时基于快照/账本生成）
    weekday = datetime.datetime.fromtimestamp(now()).weekday()  # 周一=0，周日=6
    post_audit = ("录后校验·周日全量（约1517店，开会话委派 OrganizerAgent 12分片）"
                  if weekday == 6 else
                  "录后校验·工作日增量（planner --batch 120，开会话跑搜索取证+post_audit）")
    lines.append("今日待补（会话内）：02点自进化复盘回看（容器 self_evolve 01:00 已产确定性部分）；"
                 "06点深度报告（基于本目录 06 快照）；" + post_audit)
    text = "\n".join(lines)

    # key 按天唯一（天然每天一条）；cadence=86400 双保险，防止当天内手动重跑/重复调度刷屏
    pushed = False
    try:
        pushed = bool(notifier.info(text, key=f"morning:{today()}", cadence=86400))
    except Exception as e:
        print("[nightwatch] morning push fail:", repr(e)[:100])
    state["morning_brief"] = text
    state["morning_pushed"] = pushed
    save_state(state)
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    (WATCH_DIR / f"morning_{today()}.txt").write_text(text, encoding="utf-8")
    print(f"[nightwatch] morning brief 已生成（TG 推送={'是' if pushed else '否：窗口内折叠或失败'}）")
    print(text)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tick")
    sp = sub.add_parser("snapshot")
    sp.add_argument("--tag", default="x")
    sub.add_parser("morning")
    args = ap.parse_args()
    if args.cmd == "tick":
        return cmd_tick(args)
    if args.cmd == "snapshot":
        return cmd_snapshot(args)
    if args.cmd == "morning":
        return cmd_morning(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())

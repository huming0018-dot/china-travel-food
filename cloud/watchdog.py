#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchdog.py — 采集看门狗（容器内运行）。

作用：
1. 监控采集/补齐进程，运行超过 MAX_RUN_MIN 仍未退出视为卡死（如 stage1/xhs 挂起），
   直接 SIGKILL；flock 由内核在进程死后自动释放，下一轮 cron 可正常起跑。
2. 不 kill 正常运行中的进程；不碰 watchdog 自身、不碰 cron/shell。
3. 每次动作写 /app/data/watchdog.log；发生 kill 或检测到错误日志时经 health 双通道告警。
4. 设计为幂等、可被 cron 每 20 分钟重复调用（与采集:00/:20/:40、补电话:05/:25/:45、
   review:15/:35/:55 错峰，设在 :10/:30/:50，省资源且不抢 flock）。

部署：放容器 /app/cloud/watchdog.py；crontab 增加
  10,30,50 * * * * cd /app/cloud && . /app/cloud/env.sh && python watchdog.py >> /app/data/watchdog.log 2>&1
"""
import datetime
import os
import pathlib
import signal
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 被监控的采集/补齐脚本（命令行里出现即纳入）
WATCH = [
    "run_batch.py", "xhs_collect", "cloud_phone_fill.py",
    "cloud_coord_fill.py", "cloud_hours_fill.py", "cloud_review_fill.py",
    "stage1_validate",
]
SELF = "watchdog.py"
MAX_RUN_MIN = int(os.environ.get("WATCHDOG_MAX_MIN", "30"))
LOG = pathlib.Path("/app/data/watchdog.log")


def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    line = f"[{now()}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(title: str, msg: str):
    """统一走 notifier（分级/去重/冷却），不再各自直推。"""
    try:
        import notifier
        notifier.warn(f"{title}\n{msg}", key="watchdog:killed", cooldown=3600)
        return
    except Exception:
        pass
    # 兜底：health.alert
    try:
        import health
        health.alert(msg, title=title, key="watchdog_killed", cooldown=3600)
    except Exception:
        pass


def list_procs():
    """枚举进程（不依赖 ps/procps，直接读 /proc）。返回 [(pid, etimes_sec, cmdline)]。"""
    clk = os.sysconf("SC_CLK_TCK")
    try:
        uptime = float(pathlib.Path("/proc/uptime").read_text().split()[0])
    except Exception:
        uptime = 0.0
    out = []
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore").strip()
            stat = (p / "stat").read_text()
            rpar = stat.rindex(")")
            fields = stat[rpar + 2:].split()
            starttime = int(fields[19])  # /proc stat 字段22 = starttime
            etimes = max(0, int(uptime - starttime / clk))
            out.append((pid, etimes, cmd))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except Exception:
            continue
    return out


def scan():
    killed, running = [], []
    for pid, etimes, args in list_procs():
        if not args or SELF in args:
            continue
        if not any(w in args for w in WATCH):
            continue
        running.append((pid, etimes // 60, args.split()[0]))
        if etimes > MAX_RUN_MIN * 60:
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append((pid, etimes // 60, args.split()[0]))
                log(f"KILL hung pid={pid} runtime={etimes//60}min cmd={args.split()[0]}")
            except ProcessLookupError:
                pass
            except Exception as e:
                log(f"kill pid={pid} failed: {e}")

    return killed, running


def check_error_logs():
    """扫最近日志里的错误信号，仅记录不重复告警（health 自带 6h 冷却）。"""
    hits = []
    for name in ("cron.log", "phone_fill.log", "coord_fill.log", "review_fill.log"):
        p = pathlib.Path(f"/app/data/{name}")
        if not p.exists():
            continue
        try:
            tail = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-50:]
            for ln in tail:
                if ("status=121" in ln or "status=348" in ln or "error" in ln.lower()
                        or "Traceback" in ln):
                    hits.append(f"{name}: {ln.strip()[:120]}")
        except Exception:
            pass
    return hits[-5:]


def main():
    # 0) 账号/采集池自动修复（守护 gap_pool、签名通道复核、换 IP、纠正状态；真失效才告警扫码）
    try:
        import account_repair
        results, pool_alive = account_repair.run()
        log("账号修复：" + "，".join(f"{a}={v}" for a, (v, _) in results.items())
            + f"；pool_alive={pool_alive}")
    except Exception as e:
        log(f"账号修复步骤异常：{e}")

    # 0.5) 告警专项（warning subagent）：推进登录工单——二维码刷新/限时提醒/
    #      验证重登成功/接收 TG“重拉”指令，全程与用户沟通到解决
    try:
        import warning_handler
        warning_handler.poll()
    except Exception as e:
        log(f"告警专项异常：{e}")

    # 0.7) 地图 key 看门狗：盘点腾讯/高德各接口可用 key，全尽带解封时刻告警、恢复自动收尾
    try:
        import map_key_repair
        log(map_key_repair.run())
    except Exception as e:
        log(f"地图key盘点异常：{e}")

    killed, running = scan()
    errs = check_error_logs()
    if running:
        log("运行中: " + "; ".join(f"{c}({m}m)" for _, m, c in running))
    if killed:
        body = "；".join(f"pid={p} 已运行{m}分钟被强杀({c})" for p, m, c in killed)
        log(f"ALERT 清理卡死进程: {body}")
        alert("美食图鉴·看门狗清理", f"发现并强杀 {len(killed)} 个卡死采集进程:\n{body}")
    elif errs:
        log("错误信号: " + " | ".join(errs))
    else:
        log("OK 无卡死、无新错误")
    return 0


if __name__ == "__main__":
    sys.exit(main())

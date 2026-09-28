#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_router.py — 多平台采集「轮候调度器」（资源感知，单浏览器串行）。

为什么存在：服务器同一时刻只有一个无头 Chromium。旧 cron 靠手动错峰(:00/:05/...)
+flock 调度，新平台（米其林榜单、未来抖音/公众号）插不进来，而且账号被风控时还在
硬刷小红书，容易把账号刷成 300011。本调度器每个 tick 只跑一个「需要浏览器」的任务，
按优先级 + 账号健康 + 是否有待办 决定跑谁；不依赖浏览器的任务（B站/电话/坐标/
营业时间/高德回填）保持各自 cron，不在此路由。

资源模型：
  R1 浏览器（本路由串行占用 /tmp/browser.lock）：
      P1 XHS 账号体检/告警（health.alert）——异常直接短路
      P2 小红书开放式发现 cloud_discover.py（找宝藏店主力）——需健康账号
      P3 小红书 reviews 取证 run_batch.py（519 家已采完时自空转）——需健康账号
      P4 米其林榜单抓取 michelin_collect.py（不依赖 XHS 登录）——账号全冷却时顶上
  R2 HTTP API（无浏览器）：B站 cloud_bili_collect.py，独立 cron 每 6h。
  R3 高德日配额：回填任务 + 未来枚举，夜间预算制，不在此路由。

铁律：
  - 一个 tick 只跑一个浏览器任务，跑完即退；flock 防重叠。
  - 小红书类任务前必须确认至少一个账号不在冷却；否则跳过，把浏览器让给 P4。
  - 任何异常都写 /app/data/router.log，不抛出导致 cron 报错刷屏。
"""
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime

DATA = pathlib.Path("/app/data")
LOG = DATA / "router.log"


def log(msg: str):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def xhs_usable_accounts():
    """返回 (可用账号数, summary)。summary 形如 {account_id:{status,cooling,reason}}。
    0 = 浏览器应让给不依赖 XHS 的任务。"""
    try:
        sys.path.insert(0, "/app/cloud")
        import xhs_cookie_pool as pool
        s = pool.summary() or {}
        accs = [(k, v) for k, v in s.items() if isinstance(v, dict)]
        ready = [k for k, v in accs if v.get("status") == "ok" and not v.get("cooling")]
        return len(ready), s
    except Exception as e:
        log(f"[WARN] 读账号池失败，保守认为有可用账号: {e}")
        return 1, {}


def run_script(script: str, timeout: int = 25 * 60):
    """在容器环境里跑一个采集脚本，吞掉异常。"""
    cmd = f"cd /app/cloud && . /app/cloud/env.sh && {sys.executable} {script}"
    log(f"→ 启动 {script}")
    try:
        r = subprocess.run(cmd, shell=True, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = (r.stdout or "").strip().splitlines()[-3:]
        log(f"← 完成 {script} rc={r.returncode} | 末尾: {' / '.join(tail)[:300]}")
    except subprocess.TimeoutExpired:
        log(f"!! 超时 {script}（>{timeout//60}min）")
    except Exception as e:
        log(f"!! 异常 {script}: {e}")


def reviews_done():
    return (DATA / "ALL_REVIEWS_DONE").exists()


def next_tick():
    """简单轮次计数（持久化），用于 discover / reviews 交替占用同一浏览器。"""
    f = DATA / "router_tick.txt"
    n = 0
    try:
        n = int(f.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        n = 0
    n += 1
    try:
        f.write_text(str(n), encoding="utf-8")
    except Exception:
        pass
    return n


def decide():
    """返回 (脚本, 理由)。优先级从高到低。"""
    # 并行采集池运行中：HTTP 并行已覆盖 gap 深覆盖，router 整体让位，避免重复采集。
    if (DATA / "POOL_RUNNING").exists():
        return ("", "并行采集池(POOL)运行中，router 让位，不重复调度")

    ready, s = xhs_usable_accounts()
    brief = {k: {"status": v.get("status"), "cooling": v.get("cooling")} for k, v in s.items() if isinstance(v, dict)}
    log(f"账号状态: ready={ready} ({json.dumps(brief, ensure_ascii=False)})")

    if ready <= 0:
        # 所有 XHS 账号都在冷却/不可用：不要硬刷小红书，浏览器让给榜单兜底
        return ("cloud_michelin_collect.py", "所有XHS账号冷却，浏览器让给米其林榜单")

    # 有可用 XHS 账号：discover（找宝藏店主力）与 run_batch（reviews 取证）轮替，
    # 共用同一浏览器锁，避免旧 cron 手动错峰。reviews 全部采完后只跑 discover。
    tick = next_tick()
    if not reviews_done() and tick % 2 == 1:
        return ("run_batch.py", f"tick={tick} 奇数轮，跑 reviews 取证（519 未采完）")
    return ("gap_runner.py --next --queries 8", f"tick={tick} 偶数轮，账本驱动深覆盖"
            + ("（reviews 已全部采完）" if reviews_done() else ""))


def main():
    dry = "--dry" in sys.argv
    target, why = decide()
    log(f"本轮决策: {target}（{why}）{'[DRY-RUN 不执行]' if dry else ''}")
    if dry:
        return
    if not target:
        return
    run_script(target)


if __name__ == "__main__":
    main()

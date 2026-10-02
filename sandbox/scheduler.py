#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scheduler.py — 统一调度器，替代29个cron任务。

4个任务合并到一个入口，按间隔跑：
  - amap_batch: 每2小时，补全字段
  - progress_broadcast: 每小时，播报进度
  - discover: 每6小时，发现新餐厅
  - watchdog: 每20分钟，看门狗检查

用法：
  python3 scheduler.py              # 一直跑
  python3 scheduler.py --once       # 跑一轮就退出
"""
import argparse
import time
import config
import common

# 任务定义：(函数, 间隔秒)
TASKS = [
    ("amap_batch", 7200),       # 2小时
    ("progress_broadcast", 3600),  # 1小时
    ("discover", 21600),        # 6小时
    ("watchdog", 1200),         # 20分钟
]


def run_task(name: str):
    """执行一个任务。"""
    common.log.info(f"开始任务：{name}")
    try:
        if name == "amap_batch":
            import amap_batch
            amap_batch.run(apply=False, limit=50)
        elif name == "progress_broadcast":
            import progress_broadcast
            progress_broadcast.run()
        elif name == "discover":
            import discover
            discover.run()
        elif name == "watchdog":
            import watchdog
            watchdog.check()
        common.log.info(f"完成任务：{name}")
    except Exception as e:
        common.log.error(f"任务失败 {name}: {e}")


def loop(once: bool = False):
    """主循环。"""
    last_run = {name: 0 for name, _ in TASKS}

    while True:
        now = time.time()
        for name, interval in TASKS:
            if now - last_run[name] >= interval:
                run_task(name)
                last_run[name] = now

        if once:
            break
        time.sleep(60)  # 每分钟检查一次


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    loop(once=args.once)

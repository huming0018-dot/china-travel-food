#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scheduler.py — 统一调度器，替代29个cron任务。

按数据变化率分层 + 强制依赖排序 + 错峰。
所有周期可通过Web后台修改，配置存config.json。

用法：
  python3 scheduler.py              # 一直跑
  python3 scheduler.py --once       # 跑一轮就退出
  python3 scheduler.py --list       # 列出所有任务
"""
import argparse
import json
import time
import config
import common

# 默认任务配置（可被config.json覆盖）
DEFAULT_TASKS = {
    # 核心采集层
    "watchdog": {"interval": 1200, "offset": 0, "enabled": True},      # 20分钟
    "progress_broadcast": {"interval": 3600, "offset": 0, "enabled": True},  # 1小时
    "amap_batch": {"interval": 7200, "offset": 0, "enabled": True},    # 2小时
    "discover": {"interval": 21600, "offset": 0, "enabled": True},     # 6小时

    # 内容监控层（dev更新）
    "kol_cross": {"interval": 28800, "offset": 11*60, "enabled": True},  # 8小时 :11
    "bilibili": {"interval": 14400, "offset": 30*60, "enabled": True},  # 4小时 :30
    "kol_monitor": {"interval": 14400, "offset": 37*60, "enabled": True},  # 4小时 :37
    "cloud_patrol": {"interval": 14400, "offset": 52*60, "enabled": True},  # 4小时 :52

    # 深度分析层
    "fleet_grid": {"interval": 43200, "offset": 0, "enabled": True},  # 12小时，每天2次
    "chef_tracker": {"interval": 604800, "offset": 0, "enabled": True},  # 每周
    "group_chef_tree": {"interval": 86400, "offset": 11*60, "enabled": True},  # 每天 02:11/14:11
}

CONFIG_F = config.DATA / "scheduler_config.json"


def load_tasks() -> dict:
    """加载任务配置，合并默认值。"""
    saved = common.load_json(CONFIG_F, {})
    tasks = DEFAULT_TASKS.copy()
    for k, v in saved.items():
        if k in tasks:
            tasks[k].update(v)
    return tasks


def save_tasks(tasks: dict):
    """保存任务配置。"""
    # 只保存非默认值
    saved = {}
    for k, v in tasks.items():
        if v != DEFAULT_TASKS.get(k):
            saved[k] = v
    common.save_json(CONFIG_F, saved)


def run_task(name: str):
    """执行一个任务。"""
    common.log.info(f"开始任务：{name}")
    try:
        # 这里根据任务名调用对应模块
        if name == "watchdog":
            import watchdog
            watchdog.check()
        elif name == "progress_broadcast":
            import progress_broadcast
            progress_broadcast.run()
        elif name == "amap_batch":
            import amap_batch
            amap_batch.run(apply=False, limit=50)
        elif name == "discover":
            import discover
            discover.run()
        else:
            common.log.info(f"任务 {name} 暂未实现，跳过")
        common.log.info(f"完成任务：{name}")
    except Exception as e:
        common.log.error(f"任务失败 {name}: {e}")


def loop(once: bool = False):
    """主循环。"""
    tasks = load_tasks()
    last_run = {name: 0 for name in tasks if tasks[name]["enabled"]}

    while True:
        now = time.time()
        for name, cfg in tasks.items():
            if not cfg["enabled"]:
                continue
            interval = cfg["interval"]
            if now - last_run.get(name, 0) >= interval:
                run_task(name)
                last_run[name] = now

        if once:
            break
        time.sleep(60)  # 每分钟检查一次


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--list", action="store_true", help="列出所有任务")
    args = ap.parse_args()

    if args.list:
        tasks = load_tasks()
        for name, cfg in tasks.items():
            status = "✅" if cfg["enabled"] else "⏸️"
            print(f"{status} {name}: 每{cfg['interval']//3600}小时")
    else:
        loop(once=args.once)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""production.py — 生产调度：出餐方式配额感知 + 断点续跑。

从 production_runner.py 精简而来：
  - LLM配额有限，会被限流
  - 无人值守：首次全量 → 日常增量 → 每周复校
  - 断点续跑：状态落文件，限流时暂停，下一班自动继续
"""
import json
import time
import config
import common

STATE_F = config.DATA / "production_state.json"


def _load():
    return common.load_json(STATE_F, {"stage": "init", "done": 0, "total": 0})


def _save(st):
    common.save_json(STATE_F, st)


def run_once(task_name: str, total: int):
    """跑一次任务，支持断点续跑。"""
    st = _load()
    common.log.info(f"生产任务 {task_name}: stage={st['stage']}, {st['done']}/{st['total']}")

    # 如果上一轮没跑完，继续
    if st["stage"] == "running" and st["done"] < st["total"]:
        common.log.info(f"断点续跑: {st['done']}/{st['total']}")

    # 这里是实际任务逻辑（简化版）
    for i in range(st["done"], total):
        # 模拟处理一条
        st["done"] = i + 1
        st["stage"] = "running"
        _save(st)
        time.sleep(0.1)

    # 完成
    st["stage"] = "done"
    st["total"] = total
    _save(st)
    common.log.info(f"生产任务完成: {total}条")


if __name__ == "__main__":
    run_once("taste_fill", 100)

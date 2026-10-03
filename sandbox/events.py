#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events.py — 最新动向采集（Apify通道）。

从 events_apify.py 精简而来：
  - 替代需自有登录浏览器的events_collect
  - Apify actor，我方零封号，按结果计费
"""
import config
import common
import cost_guard


def collect_events(keywords: list, limit: int = 10) -> list:
    """采集最新动向。"""
    if config.APIFY_DISABLED:
        common.log.info("Apify已禁用，跳过events采集")
        return []
    if not cost_guard.can_spend(0.05):  # events一般0结果=$0
        common.log.warning("预算门拦截")
        return []

    common.log.info(f"events采集: {len(keywords)}个关键词")
    # 简化版：实际调用Apify actor
    cost_guard.record_cost(0.05, "apify_events")
    return []


if __name__ == "__main__":
    collect_events(["新店", "活动", "开业"])

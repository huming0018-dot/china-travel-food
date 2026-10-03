#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tool_router.py — 能力路由器：给定任务，选最优工具链。

从 tool_router.py 精简而来：
  - 给定数据任务，输出最优工具链plan
  - 默认只规划、不执行、不花钱
"""
import config
import common

# 工具能力表：family → 支持的字段
TOOLS = {
    "amap": {
        "fields": ["phone", "location", "hours", "rating", "price"],
        "cost": 0,
    },
    "apify_xhs": {
        "fields": ["reviews", "taste", "notes"],
        "cost": 0.1,
    },
    "search_probe": {
        "fields": ["discover", "new_store"],
        "cost": 0,
    },
}


def plan(family: str, fields: list) -> dict:
    """给定任务，输出最优工具链。"""
    candidates = []
    for tool_name, tool in TOOLS.items():
        covered = set(tool["fields"]) & set(fields)
        if covered:
            candidates.append({
                "tool": tool_name,
                "covered": list(covered),
                "missing": list(set(fields) - covered),
                "cost": tool["cost"],
            })

    # 按成本排序，优先免费
    candidates.sort(key=lambda x: x["cost"])

    common.log.info(f"工具路由: family={family}, fields={fields}")
    for c in candidates:
        common.log.info(f"  → {c['tool']}: 覆盖{c['covered']}, 缺{c['missing']}, 成本${c['cost']}")

    return {"plan": candidates, "recommended": candidates[0] if candidates else None}


if __name__ == "__main__":
    plan("B_facts", ["phone", "location"])

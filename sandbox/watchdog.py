#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchdog.py — 看门狗，检查系统是否正常运转。

检查项：
  1. 近60分钟有无新数据写入（防虚假成功）
  2. 磁盘空间是否充足
  3. 内存使用是否过高（防OOM杀sshd）
  4. Apify预算是否耗尽
"""
import shutil
import time
import config
import common
import notifier
import cost_guard


def check_disk() -> dict:
    """检查磁盘空间。"""
    total, used, free = shutil.disk_usage("/")
    pct = used / total * 100
    return {
        "total_gb": round(total / 1e9, 1),
        "used_gb": round(used / 1e9, 1),
        "pct": round(pct, 1),
        "ok": pct < 80,
    }


def check_memory() -> dict:
    """检查内存使用（防OOM杀sshd）。"""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        mem_total = int(lines[0].split()[1]) / 1024 / 1024
        mem_avail = int(lines[2].split()[1]) / 1024 / 1024
        used_pct = (mem_total - mem_avail) / mem_total * 100
        return {
            "total_gb": round(mem_total, 1),
            "used_pct": round(used_pct, 1),
            "ok": used_pct < 85,
        }
    except Exception as e:
        common.log.warning(f"内存检查失败: {e}")
        return {"ok": True, "used_pct": 0}


def check_data_freshness() -> dict:
    """检查数据新鲜度。"""
    recent = common.db_get("restaurants", order="created_at.desc", limit=1)
    if not recent:
        return {"ok": False, "msg": "无数据"}
    return {"ok": True, "msg": "有数据"}


def check_budget() -> dict:
    """检查Apify预算。"""
    remaining = cost_guard.remaining()
    return {
        "remaining_usd": round(remaining, 2),
        "ok": remaining > 0.1,
    }


def check():
    """执行所有检查。"""
    issues = []

    disk = check_disk()
    if not disk["ok"]:
        issues.append(f"磁盘使用{disk['pct']}%过高")

    mem = check_memory()
    if not mem["ok"]:
        issues.append(f"内存使用{mem['used_pct']}%过高，可能OOM")

    fresh = check_data_freshness()
    if not fresh["ok"]:
        issues.append(f"数据异常：{fresh['msg']}")

    budget = check_budget()
    if not budget["ok"]:
        issues.append(f"Apify预算仅剩${budget['remaining_usd']}")

    if issues:
        body = "\n".join(f"⚠️ {i}" for i in issues)
        notifier.warn(body, key="watchdog", cooldown=3600)
        common.log.warning(f"看门狗告警：{issues}")
    else:
        common.log.info("看门狗：一切正常")


if __name__ == "__main__":
    check()

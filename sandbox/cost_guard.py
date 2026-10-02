#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_guard.py — 统一预算门，所有付费采集都过这里。

之前出过Apify事故：$5额度超支到$18.94。
根因：3个文件各算各的预算，toolzerhub标记price=0绕过了门。
现在：所有付费采集统一过这里，一个门管所有。
"""
import time
import config
import common

# ── 状态文件 ──
STATE = config.DATA / "cost_guard.json"


def _load():
    return common.load_json(STATE, {"month": "", "spent_usd": 0.0})


def _save(st):
    common.save_json(STATE, st)


def _reset_if_new_month(st):
    now = time.strftime("%Y-%m")
    if st.get("month") != now:
        st["month"] = now
        st["spent_usd"] = 0.0
    return st


def can_spend(per_run_cost: float) -> bool:
    """检查是否还能花钱跑一次。"""
    if config.APIFY_DISABLED:
        common.log.info("Apify已禁用，不付费采集")
        return False
    if per_run_cost <= 0:
        common.log.warning(f"预算门拦截：无效金额${per_run_cost:.2f}")
        return False
    st = _reset_if_new_month(_load())
    remaining = config.APIFY_MONTHLY_BUDGET - st["spent_usd"]
    ok = remaining >= per_run_cost
    if not ok:
        common.log.warning(
            f"预算门拦截：本月已耗${st['spent_usd']:.2f}/{config.APIFY_MONTHLY_BUDGET:.2f}"
            f"，本次需${per_run_cost:.2f}"
        )
    return ok


def record_cost(amount: float, provider: str = ""):
    """记录一笔花费。"""
    st = _reset_if_new_month(_load())
    st["spent_usd"] = round(st.get("spent_usd", 0) + amount, 4)
    _save(st)
    common.log.info(f"记账：${amount:.4f} ({provider})，本月累计${st['spent_usd']:.2f}")


def remaining() -> float:
    st = _reset_if_new_month(_load())
    return config.APIFY_MONTHLY_BUDGET - st["spent_usd"]

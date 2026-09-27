#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_ready.py — 轮换账号、打开一个通过登录+搜索校验的浏览器。

run_batch / cloud_discover 共用：
  依次从 cookie 池取可用账号 → 开浏览器 → check_login → check_search；
  登录失效 / 搜索风控 / 搜索无卡片 → 标记该账号、关掉浏览器、自动切下一个；
  全部账号都不可用 → 抛 AllAccountsBlocked（由编排统一双通道告警一次，不逐号刷屏）。
"""
import cloud_bu
import health
import xhs_cookie_pool as pool


class AllAccountsBlocked(Exception):
    def __init__(self, summary=None):
        super().__init__("全部小红书账号当前不可用")
        self.summary = summary or pool.summary()


def open_ready_browser(headless=True):
    """返回 (bu, account_id)。账号通过登录+搜索校验后返回；全不可用抛 AllAccountsBlocked。"""
    guard = 0
    n_accounts = len(pool.list_accounts())
    while guard <= n_accounts:
        guard += 1
        account_id, cookies = pool.pick_account()
        if not account_id:
            raise AllAccountsBlocked()
        bu = cloud_bu.CloudBrowser(headless=headless, cookies=cookies)
        ok, why = health.check_login(bu)
        if not ok:
            bu.close()
            pool.mark_dead(account_id, why)
            continue
        sstat, swhy = health.check_search(bu)
        if sstat == "restricted":
            bu.close()
            pool.mark_restricted(account_id, swhy)
            continue
        if sstat == "unknown":
            bu.close()
            pool.mark_restricted(account_id, "搜索无卡片：" + swhy)
            continue
        pool.mark_ok(account_id)
        return bu, account_id
    raise AllAccountsBlocked()

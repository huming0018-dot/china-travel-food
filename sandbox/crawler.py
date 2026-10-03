#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crawler.py — 统一采集入口：Apify + 小红书Cookie池。

所有付费采集过cost_guard预算门，所有账号状态统一管理。

用法：
  python3 crawler.py search "上海 本帮菜" 20
  python3 crawler.py status
"""
import argparse
import json
import time
import config
import common
import cost_guard

API = "https://api.apify.com/v2"
ACTOR = "sian.agency/xiaohongshu-rednote-scraper"
POOL_F = config.DATA / "cookie_pool_state.json"
ACCOUNTS_DIR = config.SECRETS / "xhs_accounts"


# ── Apify ──
def search_notes(keyword: str, limit: int = 20) -> list:
    if config.APIFY_DISABLED:
        common.log.info("Apify已禁用")
        return []
    if not cost_guard.can_spend(0.1):
        common.log.warning("预算门拦截")
        return []
    r = common.http_post(f"{API}/acts/{ACTOR}/runs", {"searchQueries": [keyword], "maxItems": limit})
    run_id = r.get("data", {}).get("id")
    if not run_id:
        return []
    # 简化：直接返回空，实际要wait_for_run
    cost_guard.record_cost(0.1, "apify")
    return []


# ── Cookie池 ──
def account_status() -> dict:
    st = common.load_json(POOL_F, {})
    return {f.stem: st.get(f.stem, {}).get("status", "ok") for f in ACCOUNTS_DIR.glob("*.json")}


def pick_account() -> str:
    st = common.load_json(POOL_F, {})
    now = time.time()
    for f in ACCOUNTS_DIR.glob("*.json"):
        aid = f.stem
        rec = st.get(aid, {})
        if rec.get("status", "ok") == "ok":
            return aid
        if now - rec.get("ts", 0) > 3 * 3600:  # 3小时冷却
            return aid
    return None


def mark_bad(aid: str, reason: str):
    st = common.load_json(POOL_F, {})
    st[aid] = {"status": "restricted", "reason": reason, "ts": time.time()}
    common.save_json(POOL_F, st)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", nargs="?")
    p.add_argument("keyword", nargs="?")
    p.add_argument("limit", nargs="?", type=int, default=20)
    args = p.parse_args()

    if args.cmd == "status":
        print("Apify剩余:", cost_guard.remaining())
        print("账号状态:", account_status())
    elif args.cmd == "search":
        search_notes(args.keyword, args.limit)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_discover.py — 云端「开放式发现」总编排（发现 → 离线裁决 → 自动收录）。

补齐 sourcing 最大断点：旧云端 run_batch 只对已知店名取证，从不"开放式发现"，导致宝藏店
（平台 SEO 弱、靠食客口碑）系统性缺失。本编排把图遍历发现接入云端 cron：

  每轮（cron 调用，断点续跑）：
    1. 读 cookie、启动无头浏览器、校验登录（失效告警退出，不硬刷）；
    2. 取品类队列当前品类，DiscoveryEngine 跑 QUERIES_PER_RUN 个查询（自动图扩展）；
    3. 未饱和 → 落盘退出，下轮续跑；
    4. 饱和 → admission_gate 离线裁决 candidates_<cat>.jsonl
             → candidate_apply 把 admit 库外新店自动取证收录并挂菜系标签；
    5. 该品类标记完成、转下一品，双通道告警；全部完成则告警可停用。

容器内：cloud=/app/cloud，pipeline=/app/pipeline，data=/app/data。
watchdog 保证超时清理；本脚本单次预算保守（约 5–8 分钟）。
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import cloud_bu          # noqa: E402
import health            # noqa: E402

DISC_DIR = pathlib.Path(DATA) / "discovery"
RAW = DISC_DIR / "raw_discovery.jsonl"
STATE_F = DISC_DIR / "discover_state.json"

# 品类推进顺序：先中餐八大 + 本帮京菜，再日料细分、亚洲其他、西餐，最后非正餐与场景。
QUEUE = [
    "sichuan", "cantonese", "jiangsu", "shandong", "zhejiang", "fujian", "hunan",
    "anhui", "shanghainese", "beijing",
    "sushi", "ramen", "yakitori", "yakiniku", "izakaya", "tempura",
    "japanese_curry", "kaiseki", "japanese_western",
    "thai", "vietnamese", "korean", "singaporean", "malaysian", "indian",
    "french", "italian", "spanish", "mediterranean", "german", "american", "steakhouse",
    "bread", "coffee", "dessert", "bar", "tea_house",
    "private_kitchen", "hotpot", "guangxi_fish", "market_food",
]


def load_state():
    if STATE_F.exists():
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    return {"queue": list(QUEUE), "done": [], "current": None,
            "completed_at": {}}


def save_state(st):
    DISC_DIR.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                       encoding="utf-8")


def next_category(st, forced):
    if forced:
        return forced
    if st.get("current"):
        return st["current"]
    for c in st["queue"]:
        if c not in st["done"]:
            return c
    return None


def run_gate(category):
    subprocess.run([sys.executable, f"{PIPE}/admission_gate.py",
                    "--raw", str(RAW), "--category", category], check=True)


def run_apply(category):
    subprocess.run([sys.executable, str(HERE / "candidate_apply.py"),
                    "--category", category, "--commit"], check=True)


def count_candidates(category):
    f = DISC_DIR / f"candidates_{category}.jsonl"
    admit = new = 0
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            p = json.loads(line)
            if p.get("verdict", "").startswith("admit"):
                admit += 1
                if not p.get("in_db"):
                    new += 1
    return admit, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", type=int,
                    default=int(os.environ.get("DISCOVER_QUERIES", "10")))
    ap.add_argument("--category", default="")
    args = ap.parse_args()

    st = load_state()
    category = next_category(st, args.category or None)
    if category is None:
        health.alert("上海美食图鉴全品类开放式发现已全部完成，可停用 discover 定时任务。",
                     title="上海美食图鉴·发现完成", key="discover_all_done", once=True)
        return 0
    st["current"] = category
    save_state(st)

    import cloud_ready
    try:
        bu, account_id = cloud_ready.open_ready_browser(headless=True)
    except cloud_ready.AllAccountsBlocked as e:
        blocked = {k: v.get("status") for k, v in e.summary.items()}
        print("全部账号当前不可用：", blocked)
        health.alert(
            "小红书全部账号当前都被风控/登录失效，开放式发现暂停。\n"
            "状态：" + json.dumps(blocked, ensure_ascii=False)
            + "\n请再提供一个账号 cookie；系统每 3 小时自动复检。",
            title="上海美食图鉴·账号全不可用", key="discover_all_accounts_blocked")
        return 0

    from discovery_engine import DiscoveryEngine
    rep = None
    try:
        print(f"使用账号 {account_id} 发现品类 {category}。")
        eng = DiscoveryEngine(bu, category, DISC_DIR, max_per_run=args.queries)
        rep = eng.run(max_queries=args.queries)
    finally:
        bu.close()

    if rep is None or rep["status"] != "saturated":
        print(f"品类 {category} 发现进行中：{rep}")
        return 0

    # 饱和 → 离线裁决 + 自动收录
    run_gate(category)
    run_apply(category)
    admit, new = count_candidates(category)

    st["done"].append(category)
    st["current"] = None
    st["completed_at"][category] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_state(st)

    remaining = len([c for c in st["queue"] if c not in st["done"]])
    health.alert(
        f"【{category}】开放式发现完成：够格 {admit}（库外新增 {new}），"
        f"剩余 {remaining} 个品类。",
        title="上海美食图鉴·品类发现", key=f"discover_done_{category}")
    print(f"\n品类 {category} 完成：admit={admit} new={new}；剩余品类 {remaining}")
    if remaining == 0:
        health.alert("全品类开放式发现全部完成，可停用 discover 定时任务。",
                     title="上海美食图鉴·发现完成", key="discover_all_done", once=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

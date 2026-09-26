#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_batch.py — 云端一轮采集编排（断点续跑；采集→转换→入库）。

流程：
  1. 从 XHS_COOKIE 读登录态，启动无头 Chromium；
  2. health.check_login 探测，失效则标记+告警+退出（不硬刷）；
  3. 读 raw_xhs 已采集集合，从 reviews_priority 取前 N 家未采集，
     逐家 collect_restaurant，采完一家立即落盘；
  4. xhs_to_reviews 全量重算 raw_reviews（口味整数分，无口味不打分）；
  5. atlas_write --domain reviews --commit 幂等入库，触发器自动重算口味分；
  6. 打印/回报统计；519 家全部完成则写标记并告警可停用。

容器内路径：pipeline=/app/pipeline，data=/app/data（可用环境变量覆盖）。
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

import cloud_bu
import health

XHS_DIR = pathlib.Path(DATA) / "research/atlas/xhs"
RAW = XHS_DIR / "raw_xhs.jsonl"
RAW_REVIEWS = XHS_DIR / "raw_reviews.jsonl"
PRIORITY = pathlib.Path(DATA) / "research/atlas/reviews_priority.json"


def done_names():
    s = set()
    if RAW.exists():
        for line in RAW.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    s.add(json.loads(line).get("name"))
                except json.JSONDecodeError:
                    pass
    return s


def next_batch(n):
    pri = json.loads(PRIORITY.read_text(encoding="utf-8"))
    items = pri if isinstance(pri, list) else (
        pri.get("restaurants") or pri.get("items") or [])
    done = done_names()
    return [x["name"] for x in items if x.get("name") not in done][:n]


def count_reviews():
    total = taste = 0
    if RAW_REVIEWS.exists():
        for line in RAW_REVIEWS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                if json.loads(line).get("aspect_taste") is not None:
                    taste += 1
            except json.JSONDecodeError:
                pass
    return total, taste


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=int(os.environ.get("BATCH", "10")))
    ap.add_argument("--max-notes", type=int, default=3)
    ap.add_argument("--headless", action="store_true", default=True)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    if not PRIORITY.exists():
        sys.exit(f"找不到重点店清单: {PRIORITY}")

    cookies = cloud_bu.load_cookies_from_env()
    if not cookies:
        print("未配置 XHS_COOKIE，无法采集（请先导出 cookie）。")
        health.mark_invalid("缺少 XHS_COOKIE")
        health.alert("云端未配置 XHS_COOKIE，采集未启动。", key="cookie_missing")
        return 2

    names = next_batch(args.batch)
    if not names:
        print("519 家全部已采集。")
        health.alert("小红书 519 家重点店评价已全部采集完成，可停用采集定时任务。",
                     title="上海美食图鉴·任务完成", key="all_done", once=True)
        (pathlib.Path(DATA) / "ALL_REVIEWS_DONE").write_text(
            "519 家全部完成\n", encoding="utf-8")
        return 0

    bu = cloud_bu.CloudBrowser(headless=not args.headed, cookies=cookies)
    try:
        ok, why = health.check_login(bu)
        if not ok:
            print("cookie 失效：", why)
            health.mark_invalid(why)
            health.alert(f"小红书 cookie 已失效（{why}），本轮跳过。请重新导出并更新 XHS_COOKIE。",
                         key="cookie_invalid")
            return 2
        health.clear_invalid()

        added = 0
        import xhs_collect as X
        for i, name in enumerate(names, 1):
            try:
                rec = X.collect_restaurant(bu, name, max_notes=args.max_notes)
                X.append_jsonl(str(RAW), rec)
                added += 1
                print(f"[{i}/{len(names)}] ✓ {name} notes={len(rec.get('notes', []))}")
            except Exception as e:
                print(f"[{i}/{len(names)}] ✗ {name} 跳过: {repr(e)[:120]}")
            time.sleep(1.0)
    finally:
        bu.close()

    # 转换（读全部 raw_xhs 重算 raw_reviews）
    subprocess.run([sys.executable, f"{PIPE}/xhs_to_reviews.py"], check=True)
    # 入库（幂等）
    subprocess.run([sys.executable, f"{PIPE}/atlas_write.py",
                    "--domain", "reviews", "--input", str(RAW_REVIEWS),
                    "--commit"], check=True)

    total, taste = count_reviews()
    done = len(done_names())
    print(f"\n本轮新增 {added} 家；累计 {done}/519；"
          f"reviews {total} 行（含口味 {taste}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

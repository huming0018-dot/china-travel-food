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
  6. 打印/回报统计；重点队列全部“有真实笔记证据”才写完成标记（访问过≠完成）。

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


def covered_names():
    """真正采到 ≥1 条笔记的店名（区别于仅访问过）。"""
    s = set()
    if RAW.exists():
        for line in RAW.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            notes = rec.get("notes")
            has = bool(notes) if isinstance(notes, list) else bool(notes)
            if has:
                s.add(rec.get("name"))
    return s


def priority_items():
    pri = json.loads(PRIORITY.read_text(encoding="utf-8"))
    return pri if isinstance(pri, list) else (
        pri.get("restaurants") or pri.get("items") or [])


def next_batch(n):
    items = priority_items()
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

    items = priority_items()
    total = len(items)
    pri_names = set(x.get("name") for x in items)
    visited = done_names() & pri_names
    covered = covered_names() & pri_names
    names = next_batch(args.batch)
    if not names:
        # 全部“访问过”不等于完成：完成以“有真实笔记证据”为准，避免误报全完成
        print(f"重点店已全部访问 {len(visited)}/{total}；"
              f"有真实笔记证据 {len(covered)}/{total}。")
        prog = pathlib.Path(DATA) / "REVIEWS_PROGRESS"
        prog.write_text(
            f"visited={len(visited)}/{total} covered(有笔记)={len(covered)}/{total}\n",
            encoding="utf-8")
        old = pathlib.Path(DATA) / "ALL_REVIEWS_DONE"
        if old.exists():
            old.unlink()  # 删除旧的“519全完成”误报标记
        if len(covered) >= total:
            health.alert(
                f"小红书重点店 {total} 家评价已全部采集完成，可停用采集定时任务。",
                title="上海美食图鉴·任务完成", key="all_done", once=True)
        # 即使采集中止，仍回收既有 unmatched 笔记进发现管线（幂等）
        run_unmatched_bridge()
        return 0

    import cloud_ready
    try:
        bu, account_id = cloud_ready.open_ready_browser(headless=not args.headed)
    except cloud_ready.AllAccountsBlocked as e:
        blocked = {k: v.get("status") for k, v in e.summary.items()}
        print("全部账号当前不可用：", blocked)
        health.alert(
            "小红书全部账号当前都被风控/登录失效，浏览器采集暂停。\n"
            "状态：" + json.dumps(blocked, ensure_ascii=False)
            + "\n请再提供一个账号 cookie；系统每 3 小时自动复检已冷却账号。",
            title="上海美食图鉴·账号全不可用", key="all_accounts_blocked")
        return 0

    added = 0
    try:
        print(f"使用账号 {account_id} 采集。")
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

    # 回收 unmatched 笔记 → 开放式发现 → 准入 → 自动收录（失败不阻断本轮）
    run_unmatched_bridge()

    total, taste = count_reviews()
    done = len(done_names())
    print(f"\n本轮新增 {added} 家；累计访问 {done} 家（重点队列 {len(priority_items())}）；"
          f"reviews {total} 行（含口味 {taste}）。")
    return 0


def run_unmatched_bridge():
    """把锚不入库的笔记（库内无此店/合集）喂回 admission→apply 管线。幂等、失败告警不抛。"""
    bridge = HERE / "unmatched_bridge.py"
    if not bridge.exists():
        return
    print("\n--- unmatched → discovery 桥接 ---")
    try:
        subprocess.run([sys.executable, str(bridge)], check=False)
    except Exception as e:  # noqa: BLE001
        print("unmatched bridge 异常:", repr(e)[:160])


if __name__ == "__main__":
    sys.exit(main())

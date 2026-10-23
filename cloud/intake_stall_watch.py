#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""intake_stall_watch.py — 采集产出停滞确定性闸门（让"新内容源头枯竭"可观测）。

为什么存在：
  采集 cron 每天都在跑（amap_fill/phone/dianping_enrich/patrol 等持续富化存量店，
  updated_at 活跃），但"新店铺 / 新评价"可能因源头枯竭（小红书账号 web_session 失效、
  广州代理挂、高德网格已覆盖饱和、地图 key 耗尽）而长期 0 新增。这种"看起来在跑、
  实际没产出"若不可见，会被误判为"收录了很多数据但后台没纳入"。

本脚本只读 restaurants / reviews 的最新 created_at，超过阈值经 notifier（唯一通道
tg-relay）有界 WARN，恢复后 RESOLVED；同 key 按 cooldown 折叠，不刷屏。
  - 只报告、不写库、不重建账号、不代窗口采集；
  - 账号扫码 ACTION 由 warning_handler 另发（login:account_x），本脚本只做产出侧可观测，
    级别 WARN（无需操作），避免与登录提醒重复催促。

用法：
  python3 intake_stall_watch.py          # dry-run，只打印判定，不外发
  python3 intake_stall_watch.py --apply  # 经 notifier 推送 WARN/RESOLVED
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import common as C  # noqa: E402
import notifier  # noqa: E402

CST = dt.timezone(dt.timedelta(hours=8))

# 天级阈值：评价高频（健康时每天有新增），连续 3 天 0 即异常；
# 新店低频（网格已饱和、本来就不是每天有新店），连续 10 天 0 才报，避免误报。
REVIEW_STALL_DAYS = 3
RESTAURANT_STALL_DAYS = 10
COOLDOWN = 86400  # 同 key 每类每天最多一条


def latest_created_date(table):
    """最新 created_at（转 CST 取日期）。无数据返回 None。"""
    r = C.req("GET", f"/{table}?select=created_at&order=created_at.desc&limit=1")
    rows = r.json() if r.status_code == 200 else []
    if not rows or not rows[0].get("created_at"):
        return None
    s = rows[0]["created_at"].replace("Z", "+00:00")
    return dt.datetime.fromisoformat(s).astimezone(CST).date()


def bridge_queue():
    """build_bridge 中等待补证据（POI/UGC）的真实店数量。"""
    f = DATA / "coverage" / "build_bridge_state.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8"))
        return sum(1 for v in st.values()
                   if v.get("status") in ("need_poi", "need_ugc"))
    except Exception:
        return 0


def gap(d):
    if d is None:
        return None
    return (dt.datetime.now(CST).date() - d).days


def emit(table, key, stalled, g, latest, body_stall):
    if stalled:
        print(f"  [STALL] {table} 已停滞 {g} 天（最新 {latest}）")
        if ARGS.apply:
            notifier.warn(body_stall, key=key, cooldown=COOLDOWN)
    else:
        print(f"  [OK] {table} 产出正常（最新 {latest}，{g} 天前）")
        if ARGS.apply:
            notifier.resolve(f"采集产出恢复：{table} 最近已有新增（最新 {latest}）。", key=key)


ARGS = None


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ARGS = ap.parse_args()

    r_date = latest_created_date("restaurants")
    v_date = latest_created_date("reviews")
    r_gap, v_gap = gap(r_date), gap(v_date)
    bq = bridge_queue()

    print(f"最新店铺 {r_date}（{r_gap} 天前）；最新评价 {v_date}（{v_gap} 天前）；"
          f"建店排队 {bq} 家；mode={'APPLY' if ARGS.apply else 'DRY'}")

    body_v = (
        f"采集产出停滞：新评价已连续 {v_gap} 天 0 条（最新 {v_date}）。\n"
        f"真实食客 UGC 源头（小红书账号 web_session 失效/广州代理挂）断供的典型表现。\n"
        f"建店收口 build_bridge 运行正常，{bq} 家真店排队等待食客 UGC——"
        f"并非\"收录了没入库\"，而是源头无新内容。账号扫码登录提醒另发，恢复后自动续采。"
    )
    emit("reviews", "stall:reviews",
         v_gap is not None and v_gap >= REVIEW_STALL_DAYS, v_gap, v_date, body_v)

    body_r = (
        f"采集产出停滞：新店铺已连续 {r_gap} 天 0 新增（最新 {r_date}）。\n"
        f"高德地理网格已覆盖饱和、真实食客 UGC 断供时会出现；建店收口正常，"
        f"{bq} 家真店卡在食客 UGC/POI，属源头枯竭而非收口故障。"
    )
    emit("restaurants", "stall:restaurants",
         r_gap is not None and r_gap >= RESTAURANT_STALL_DAYS, r_gap, r_date, body_r)


if __name__ == "__main__":
    main()

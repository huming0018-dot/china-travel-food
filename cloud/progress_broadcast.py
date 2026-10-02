#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress_broadcast.py v2 — 每 10 分钟进度播报（实时计数 + 停滞检测）。

v2 修复"播报冻结、看起来像停采"：
  - 旧版用静态 coverage/ledger.json（不随 deuce 采集更新）+ 坏掉的 HEAD 计数（返回空）
    + 冻结的 work_progress 文字，导致连续数小时发同一句话、真实增长（reviews 1199→1445）看不见。
  - v2 每次直接从库实时统计（在营/评价总数/小红书/真实食客覆盖店/≥2），并显示"近 Xmin +Δ"。
  - 停滞检测：评价数连续 STALL_MIN 不增长 → 自动判因（上游 deuce/中继未送 raw，还是
    raw 在涨但评论被合集/匹配丢弃的低产）→ notifier.action 有界提醒；恢复流动自动 resolve。

只读 + 计数，不触发采集、不占浏览器；离线由容器 cron 保证。
"""
import datetime
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/app/pipeline")
import notifier  # noqa: E402

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
RAW_XHS = DATA / "research/atlas/xhs/raw_xhs.jsonl"
STATE_P = DATA / "progress_state.json"
STALL_MIN = 60          # 评价数 60min 不增长才判停滞（原30min，减少误报）
CADENCE = 3600           # 心跳节奏 60 分钟（原10分钟，柔和模式）


def now_str():
    return datetime.datetime.now().strftime("%H:%M")


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def live_counts():
    """实时从库统计（每 10min 一次，几千个小行，开销可忽略、可靠）。"""
    import common as C
    rests = C.fetch_all("restaurants", "id,status", order_col="id")
    active = sum(1 for r in rests if r.get("status") != "closed")
    revs = C.fetch_all(
        "reviews", "id,source_platform,is_verified_diner,restaurant_id", order_col="id")
    xhs = sum(1 for r in revs if r.get("source_platform") == "小红书")
    rids = {}
    for r in revs:
        if r.get("is_verified_diner"):
            rids[r["restaurant_id"]] = rids.get(r["restaurant_id"], 0) + 1
    return {
        "active": active,
        "rev": len(revs),
        "xhs": xhs,
        "ver_stores": len(rids),
        "ge2": sum(1 for v in rids.values() if v >= 2),
    }


def account_line():
    st = load_json(DATA / "_cookie_pool_state.json", {})
    accs = st.get("accounts", st) if isinstance(st, dict) else {}
    bits = []
    if isinstance(accs, dict):
        for aid, info in accs.items():
            short = aid.replace("account_", "").upper() if "account_" in aid else aid
            code = (info.get("status") or info.get("state") or "?") if isinstance(info, dict) else info
            bits.append(f"{short}={code}")
    return "账号：" + ("，".join(bits) if bits else "状态缺失")


def raw_idle_min():
    try:
        return (time.time() - RAW_XHS.stat().st_mtime) / 60.0
    except Exception:
        return 9999.0


def load_state():
    return load_json(STATE_P, {"rev": None, "ts": 0, "last_growth_ts": time.time(),
                               "stall_open": False})


def apify_cost_line():
    """当月 Apify 实际消耗（USD），从 Apify API 实时拉取。"""
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        fp = DATA / ".secrets" / "apify_token"
        try:
            token = fp.read_text(encoding="utf-8").strip()
        except Exception:
            token = ""
    if not token:
        return ""
    try:
        import requests
        d = requests.get(
            "https://api.apify.com/v2/users/me/usage/monthly",
            params={"token": token}, timeout=15).json().get("data", {})
        used = float(d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0)
        return f"💰 Apify本月已耗 ${used:.2f}"
    except Exception:
        return ""


def heartbeat_body(c, delta, mins):
    trend = f"近{mins}min +{delta}条 · 流动正常" if delta > 0 else f"近{mins}min +0条"
    lines = [
        f"口味覆盖：{c['ver_stores']} 店有真实食客评价（≥2条 {c['ge2']}）",
        f"评价库：{c['rev']} 条（小红书 {c['xhs']}）｜在营 {c['active']} 家",
        account_line(),
    ]
    apify = apify_cost_line()
    if apify:
        lines.append(apify)
    lines.append(f"进度（{now_str()}）：{trend}")
    return "\n".join(lines)


def stall_body(c, mins, raw_idle):
    if raw_idle > STALL_MIN:
        cause = ("上游未送新数据：raw_xhs 已 %.0fmin 未增长 → 检查 deuce 采集器 / 网络 / rsync / 云端relay"
                 % raw_idle)
        action_text = "请检查 deuce 采集器、网络或云端中继"
    else:
        cause = ("raw 在涨但评论 %.0fmin 0 新增 → 笔记被『合集/分店名匹配』丢弃（低产），需修锚定逻辑"
                 % mins)
        action_text = "需修 xhs 锚定/合集判定（机制侧）"
    body = "\n".join([
        f"口味覆盖：{c['ver_stores']} 店（≥2 {c['ge2']}）｜评价 {c['rev']} 条",
        account_line(),
        "判定：采集疑似停滞 —— " + cause,
    ])
    return body, action_text


def main():
    c = live_counts()
    st = load_state()
    nowt = time.time()
    prev_rev = st.get("rev")
    prev_ts = st.get("ts") or nowt
    mins = max(1, round((nowt - prev_ts) / 60))
    delta = c["rev"] - prev_rev if prev_rev is not None else 0
    moving = delta > 0

    if moving:
        st["last_growth_ts"] = nowt
    stall_min = (nowt - float(st.get("last_growth_ts", nowt))) / 60.0
    was_stall = bool(st.get("stall_open"))

    if stall_min >= STALL_MIN:
        # 真停滞：判因并 ACTION 有界提醒（notifier 内部去重/nudge，不刷屏）
        body, action_text = stall_body(c, stall_min, raw_idle_min())
        ok = notifier.action(body, key="collect_stall", action_text=action_text)
        st["stall_open"] = True
        print(body)
        print("停滞升级推送：", ok)
    else:
        body = heartbeat_body(c, delta, mins)
        ok = notifier.info(body, key="heartbeat", cadence=CADENCE)
        if was_stall:
            # 恢复流动：收尾旧停滞单
            notifier.resolve("采集已恢复流动（评价重新增长）", key="collect_stall")
        st["stall_open"] = False
        print(body)
        print("推送结果：", ok)

    st["rev"] = c["rev"]
    st["ts"] = nowt
    STATE_P.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

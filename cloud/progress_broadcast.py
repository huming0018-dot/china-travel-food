#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实时计数与周期心跳。保留账号状态和费用显示。

旧 reviews 自动认证链已退出；计数不增长不再自动归因为采集故障，
不催修旧采集器、匹配器或中继，也不把数值增长称为旧故障恢复。
本脚本仍读取统计并发送心跳；源码整理不等于线上已停用旧告警。
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
STATE_P = DATA / "progress_state.json"
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


def load_state():
    return load_json(STATE_P, {"rev": None, "ts": 0})


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


def main():
    c = live_counts()
    st = load_state()
    nowt = time.time()
    prev_rev = st.get("rev")
    prev_ts = st.get("ts") or nowt
    mins = max(1, round((nowt - prev_ts) / 60))
    delta = c["rev"] - prev_rev if prev_rev is not None else 0
    body = heartbeat_body(c, delta, mins)
    ok = notifier.info(body, key="heartbeat", cadence=CADENCE)
    # 仅清理本地旧状态字段；不发送“故障恢复”或操作历史通知工单。
    st.pop("last_growth_ts", None)
    st.pop("stall_open", None)
    print(body)
    print("推送结果：", ok)

    st["rev"] = c["rev"]
    st["ts"] = nowt
    STATE_P.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

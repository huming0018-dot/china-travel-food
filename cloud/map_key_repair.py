#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_key_repair.py — 地图 key 看门狗（R0 重探 / R1 轮换 / R2 出口 / R3 全尽告警）。

由 watchdog 每 20 分钟调用一次（省资源），不直接跑批量采集。

阶梯：
  R0 重探：日/月窗口过重置点的 key，MapQuota._roll_windows 自动清 dead；
           仅当“本应恢复却仍无可用 key”时才发一次最小调用确认（避免误判 dead）。
  R1 轮换：日常由 map_helpers._map_call 逐把 key 自动切换；本模块只做健康盘点。
  R2 出口：若配置 MAP_EGRESS（key→代理），可换出口复核（默认未配，跳过）。
  R3 全尽：某 provider×接口确实无可用 key，才告警一次，附【最早解封时刻】；
           恢复后自动推一条收尾，不重复刷屏（走 notifier 去重/冷却）。

账本 schema（map_quota）：ledger["keys"]["<provider>:<idx>"] =
  {provider, daily:{window,used}, monthly:{window,used}, dead_until, dead_reason}。
口径：amap search 走月桶；其余走日桶。
"""
import datetime
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map_quota as MQ  # noqa: E402

PROVIDERS = ("tencent", "amap")
INTERFACES = ("search", "geocode")


def _fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def _key_usable(rec, provider, interface, pool):
    """返回 (usable, unblock_ts)。"""
    now_i = time.time()
    reason = rec.get("dead_reason")
    until = rec.get("dead_until")
    monthly_bucket = (provider == "amap" and interface == "search")

    if until and until > now_i:
        if reason == "auth":
            # 鉴权/签名错误：该 key 冷却期内全接口不可用（非配额，到点自动重探）
            return False, until
        if reason == "monthly_quota":
            if monthly_bucket:
                return False, until
            # 月配额 dead 不影响日桶接口（geocode）
        else:  # daily_quota：日桶/月桶接口都拦
            return False, until

    cap = MQ.LIMITS[(provider, interface)]
    used = rec["monthly"]["used"] if monthly_bucket else rec["daily"]["used"]
    if used >= cap:
        nxt = pool._next_monthstart() if monthly_bucket else pool._next_midnight()
        return False, nxt
    return True, 0


def assess(provider, interface, active_probe=True):
    pool = MQ.MapQuota()
    pool._roll_windows()
    kids = sorted((k for k in pool.ledger["keys"] if k.startswith(provider + ":")),
                  key=lambda k: int(k.rsplit(":", 1)[1]))
    n_avail, earliest = 0, None
    for kid in kids:
        ok, unblock = _key_usable(pool.ledger["keys"][kid], provider, interface, pool)
        if ok:
            n_avail += 1
        elif unblock:
            earliest = unblock if earliest is None else min(earliest, unblock)

    probe = ""
    if n_avail == 0 and active_probe and earliest and earliest <= time.time():
        _j, st = _minimal_probe(provider, interface)
        probe = f"重探→{st}"
        if st == "ok":
            n_avail = 1
    return {"n_keys": len(kids), "n_avail": n_avail,
            "earliest_unblock": earliest, "probe": probe}


def _minimal_probe(provider, interface):
    """最小成本真实调用（page_size/offset=1），consumer=watchdog。"""
    if interface == "geocode":
        if provider == "tencent":
            return MQ.call(provider, "/ws/geocoder/v1/", {"address": "上海市人民广场"},
                           "geocode", "watchdog", timeout=12)
        return MQ.call(provider, "/v3/geocode/geo",
                       {"address": "上海市人民广场", "city": "上海"},
                       "geocode", "watchdog", timeout=12)
    if provider == "tencent":
        return MQ.call(provider, "/ws/place/v1/suggestion",
                       {"keyword": "餐厅", "region": "上海", "region_fix": 1, "page_size": 1},
                       "search", "watchdog", timeout=12)
    return MQ.call(provider, "/v3/place/text",
                   {"keywords": "餐厅", "city": "上海", "citylimit": "true",
                    "offset": 1, "extensions": "base"},
                   "search", "watchdog", timeout=12)


def run():
    """盘点全部 provider×interface，合并成【一条】消息（不再每个接口各发一条）。

    - 有接口全尽：单条 WARN（key=map:quota），逐行列接口+最早解封；
    - 全部恢复：单条 RESOLVED 收尾；
    - 内容哈希不变且在冷却内 → notifier 自动折叠，不重复刷屏。
    """
    import notifier
    key = "map:quota"
    oks, downs, summary = [], [], []
    for provider in PROVIDERS:
        for interface in INTERFACES:
            r = assess(provider, interface)
            label = f"{provider}/{interface}"
            if r["n_avail"] >= 1:
                oks.append(label)
                summary.append(f"{label}=ok({r['n_avail']}/{r['n_keys']})")
            else:
                unblock = _fmt_ts(r["earliest_unblock"])
                downs.append((label, r["n_keys"], unblock))
                summary.append(f"{label}=全尽(解封{unblock})")

    if downs:
        lines = [f"{label}：{n} 把 key 均不可用，最早解封 {ub}"
                 for label, n, ub in downs]
        lines.append("系统将在重置点自动恢复（日配额 0 点 / 高德搜索月初），无需操作。")
        notifier.warn("\n".join(lines), key=key, cooldown=3600)
    else:
        notifier.resolve(
            "地图通道全部恢复：" + "、".join(oks) + " 均有可用 key。", key)

    line = "地图key盘点：" + "；".join(summary)
    print(line)
    return line


if __name__ == "__main__":
    run()

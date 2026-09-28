#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reap_claims.py — 清理没有活 worker 持有的陈旧叶子认领。

为什么存在：gap_pool 重启 / worker 崩溃 / 容器重启后，coverage/claims.json 会残留，
而对应 gap_runner 已不存在；claim_next_leaf 见到 lid 被占就永不重领，导致叶子被永久卡死、
采集空转（worker 一启动即“没有可认领的缺口叶子”）。

判定：扫描 /proc，存在 cmdline 同时含 gap_runner 与该 account 的进程，才算该 claim 仍被持有；
否则删除。gap_pool 启动时调用一次，watchdog 每轮也可调用，做到自愈。
"""
import fcntl
import json
import os
import pathlib

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
COVDIR = DATA / "coverage"
CF = COVDIR / "claims.json"
LOCK = COVDIR / "claims.lock"


def live_worker_accounts():
    accs = set()
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
        except Exception:
            continue
        if "gap_runner" in cmd and "--account" in cmd:
            toks = cmd.split()
            for i, t in enumerate(toks):
                if t == "--account" and i + 1 < len(toks):
                    accs.add(toks[i + 1])
    return accs


def reap():
    """返回清理掉的陈旧 claim 数。"""
    if not CF.exists():
        return 0
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        claims = json.loads(CF.read_text(encoding="utf-8"))
        live = live_worker_accounts()
        kept = {lid: info for lid, info in claims.items()
                if info.get("account", "") in live}
        removed = len(claims) - len(kept)
        if removed:
            CF.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        return removed


if __name__ == "__main__":
    print("reaped stale claims:", reap())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notifier.py — 统一通知出口，只发人类可读信息，不发原始JSON。"""
import hashlib
import time
import config
import common

LEDGER = config.DATA / "notify_ledger.json"


def _send_tg(text: str) -> bool:
    if not config.TG_TOKEN:
        return False
    url = f"{config.TG_API_BASE}/bot{config.TG_TOKEN}/sendMessage"
    r = common.http_post(url, {
        "chat_id": config.TG_CHAT_ID,
        "text": text,
    })
    return r.get("ok", False)


def _load():
    return common.load_json(LEDGER, {})


def _save(L):
    try:
        common.save_json(LEDGER, L)
    except Exception as e:
        common.log.error(f"ledger写入失败：{e}（可能导致重复通知）")


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def info(body: str, key: str = "heartbeat", cadence: int = 3600):
    """例行播报，按节奏节流。"""
    L = _load()
    rec = L.get(key)
    now = int(time.time())
    if rec and now - rec.get("last_ts", 0) < cadence:
        return False
    header = f"🟢 播报 · 上海美食图鉴 · {time.strftime('%m-%d %H:%M')}"
    msg = f"{header}\n{'─'*16}\n{body}\n\n（无需操作）"
    ok = _send_tg(msg)
    if ok:
        L[key] = {"last_ts": now, "hash": _hash(body)}
        _save(L)
    return ok


def warn(body: str, key: str, cooldown: int = 86400 * 7):
    """告警，按冷却折叠。"""
    L = _load()
    rec = L.get(key)
    now = int(time.time())
    if rec and now - rec.get("last_ts", 0) < cooldown:
        return False
    header = f"🟡 自动处理中 · 上海美食图鉴 · {time.strftime('%m-%d %H:%M')}"
    msg = f"{header}\n{'─'*16}\n{body}\n\n（无需操作）"
    ok = _send_tg(msg)
    if ok:
        L[key] = {"last_ts": now, "hash": _hash(body)}
        _save(L)
    return ok


def action(body: str, key: str, action_text: str):
    """需要用户操作，首次立即推。"""
    L = _load()
    rec = L.get(key)
    now = int(time.time())
    if rec and rec.get("state") == "resolved":
        return False
    header = f"🔴 需要你操作 · 上海美食图鉴 · {time.strftime('%m-%d %H:%M')}"
    msg = f"{header}\n{'─'*16}\n{body}\n\n👉 需要你做：{action_text}"
    ok = _send_tg(msg)
    if ok:
        L[key] = {"last_ts": now, "state": "open"}
        _save(L)
    return ok

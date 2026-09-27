#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_cookie_pool.py — 小红书多账号 Cookie 池 + 自动轮换。

解决单账号搜索被风控(300011)就整体停摆：一个账号搜索被风控或登录失效 → 标记并在冷却期内
跳过、自动切下一个账号；只有全部账号都不可用才告警暂停。加号 = 往账号目录丢一个 json，零改代码。

账号目录 XHS_ACCOUNTS_DIR（默认 /secrets/xhs_accounts），每个文件 = 一个账号：
  - 文件名 stem 即 account_id（account_a.json → account_a）
  - 内容形态见 cloud_bu.load_cookies_from_text（请求头字符串 / cookie JSON 数组 /
    {"cookies":[...]} / {"cookie_str":"..."}）

状态持久化 DATA_DIR/_cookie_pool_state.json：每账号 status(ok/restricted/dead/unknown)、
ts、last_used、reason。冷却时长 ACCOUNT_RETRY_SEC（默认 3 小时，与搜索复检一致）。

兼容：账号目录不存在或为空时，回退单账号 XHS_COOKIE / XHS_COOKIE_FILE（account_id="default"）。
"""
import json
import os
import pathlib
import time

import cloud_bu

DATA_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
STATE_F = pathlib.Path(DATA_DIR) / "_cookie_pool_state.json"
RETRY_SEC = int(os.environ.get("ACCOUNT_RETRY_SEC", str(3 * 3600)))

OK = "ok"
RESTRICTED = "restricted"
DEAD = "dead"
UNKNOWN = "unknown"


def accounts_dir():
    d = os.environ.get("XHS_ACCOUNTS_DIR", "/secrets/xhs_accounts")
    return pathlib.Path(d)


def list_accounts():
    """返回 account_id 列表（按文件名排序）。无账号目录/为空 → 旧单账号 ["default"]。"""
    d = accounts_dir()
    if d.exists() and d.is_dir():
        ids = sorted(p.stem for p in d.glob("*.json") if p.is_file())
        if ids:
            return ids
    return ["default"]


def load_account_cookies(account_id):
    if account_id == "default" and not (
            accounts_dir().exists() and list(accounts_dir().glob("*.json"))):
        return cloud_bu.load_cookies_from_env()
    return cloud_bu.load_cookies_from_file(accounts_dir() / f"{account_id}.json")


# ------------------------------------------------ 状态
def _read_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def _rec(st, account_id):
    return st.setdefault(account_id, {"status": UNKNOWN, "ts": 0,
                                      "last_used": 0, "reason": ""})


def is_cooling(account_id):
    """该账号当前是否处于 restricted/dead 冷却窗口内（不可用）。"""
    rec = _read_state().get(account_id)
    if not rec or rec.get("status") not in (RESTRICTED, DEAD):
        return False
    return int(time.time()) - int(rec.get("ts", 0)) < RETRY_SEC


def pick_account():
    """挑一个当前可用的账号，返回 (account_id, cookies)。
    跳过冷却中的账号，其余按 last_used 最久优先（轮询均衡）。
    全部冷却/取不到 cookie → (None, None)。"""
    st = _read_state()
    usable = [a for a in list_accounts() if not is_cooling(a)]
    usable.sort(key=lambda a: int(st.get(a, {}).get("last_used", 0)))
    for account_id in usable:
        try:
            cookies = load_account_cookies(account_id)
        except Exception as e:
            print(f"账号 {account_id} cookie 读取失败，跳过：{repr(e)[:100]}")
            continue
        if not cookies:
            continue
        rec = _rec(st, account_id)
        rec["last_used"] = int(time.time())
        _write_state(st)
        return account_id, cookies
    return None, None


def mark_restricted(account_id, reason):
    st = _read_state()
    rec = _rec(st, account_id)
    rec.update(status=RESTRICTED, ts=int(time.time()), reason=reason)
    _write_state(st)


def mark_dead(account_id, reason):
    st = _read_state()
    rec = _rec(st, account_id)
    rec.update(status=DEAD, ts=int(time.time()), reason=reason)
    _write_state(st)


def mark_ok(account_id):
    st = _read_state()
    rec = _rec(st, account_id)
    rec.update(status=OK, ts=int(time.time()), reason="")
    _write_state(st)


def all_unavailable():
    accounts = list_accounts()
    return bool(accounts) and all(is_cooling(a) for a in accounts)


def summary():
    st = _read_state()
    out = {}
    for a in list_accounts():
        r = st.get(a, {})
        out[a] = {"status": r.get("status", UNKNOWN),
                  "cooling": is_cooling(a),
                  "reason": r.get("reason", "")}
    return out


if __name__ == "__main__":
    print("账号目录:", accounts_dir())
    print("账号:", list_accounts())
    print(json.dumps(summary(), ensure_ascii=False, indent=1))

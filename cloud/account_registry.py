#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""account_registry.py — 全平台账号唯一登记 / 状态 / 选用门面（#11，P0）。

为什么存在：
  旧代码里账号状态被 11 个模块各自判定（health / xhs_cookie_pool / map_quota / 各 fill…），
  同账号在不同模块结论打架（“其实在干活却报死号”）。自本模块起，
  **账号的列举 / 状态读写 / 选用一律经本模块**，业务代码不再直接判账号。

关键设计（不制造第二真源）：
  - 本模块是统一“门面 + 路由”，不复制各子系统的状态：
      * xhs（小红书）        → 权威状态在 xhs_cookie_pool（_cookie_pool_state.json），写操作路由过去；
      * tencent_map/amap_map → 权威状态在 map_quota（map_quota_ledger.json，真实返回码驱动），只读；
      * 其它平台（dianping/apify/llm/bilibili…）→ 本模块独占账本 account_registry.json。
  - 账号统一标识 “platform:id”（如 xhs:account_a、tencent_map:0）。

API：
  list(platform=None)                 {platform: [id,...]}
  status("xhs:account_a")             {status, reason, ts, ...}
  probe("xhs:account_a", bu=None)     读当前状态；传入浏览器 bu 可对 xhs 做一次活体探测
  mark("xhs:account_a","dead","原因") 写状态（路由到权威子系统）
  pick("xhs")                         选一个当前可用账号（轮询均衡），返回标识或 None
  summary(platform=None)              全平台状态汇总
"""
import json as _json
import os as _os
import pathlib as _pl
import sys as _sys
import time as _time

HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE))

import common_core as core  # noqa: E402

DATA = _pl.Path(core.DATA_DIR)
LEDGER_F = DATA / "account_registry.json"

# 统一状态词
OK, RESTRICTED, DEAD, UNKNOWN, DISABLED = "ok", "restricted", "dead", "unknown", "disabled"

# 平台 → 权威子系统类型
_XHS = "xhs"
_MAP_PLATFORMS = {"tencent_map": "tencent", "amap_map": "amap"}


# ────────────────────── 通用账本（独占平台） ──────────────────────
def _load_ledger():
    try:
        return _json.loads(LEDGER_F.read_text(encoding="utf-8"))
    except Exception:
        return {"accounts": {}}


def _save_ledger(L):
    try:
        LEDGER_F.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(LEDGER_F) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(L, f, ensure_ascii=False, indent=1)
        _os.replace(tmp, LEDGER_F)
    except Exception as e:
        core.log("error", "account_registry 写账本失败", err=repr(e)[:80])


def register(platform, account_id, meta=None):
    """登记一个通用平台账号（xhs/地图走各自子系统，不在此登记）。"""
    L = _load_ledger()
    key = f"{platform}:{account_id}"
    rec = L["accounts"].setdefault(key, {})
    rec.update({"platform": platform, "id": account_id, "status": OK,
                "ts": int(_time.time()), "last_used": 0, "reason": ""})
    if meta:
        rec.setdefault("meta", {}).update(meta)
    _save_ledger(L)
    return key


# ────────────────────── 子系统懒加载 ──────────────────────
def _xhs_pool():
    import xhs_cookie_pool as P
    return P


def _map_quota():
    import map_quota as M
    return M


# ────────────────────── 列举 ──────────────────────
def list(platform=None):
    """返回 {platform: [account_id,...]}。"""
    out = {}

    # xhs
    if platform in (None, _XHS):
        out[_XHS] = _xhs_pool().list_accounts()

    # 地图
    for pname, prov in _MAP_PLATFORMS.items():
        if platform in (None, pname):
            try:
                keys = _map_quota().load_provider_keys(prov)
                out[pname] = [str(i) for i in range(len(keys))]
            except Exception:
                out[pname] = []

    # 通用账本
    L = _load_ledger()
    for key, rec in L["accounts"].items():
        p = rec["platform"]
        if platform in (None, p):
            out.setdefault(p, []).append(rec["id"])

    return {p: ids for p, ids in out.items() if platform is None or p == platform}


# ────────────────────── 状态 ──────────────────────
def _split(key):
    if ":" not in key:
        raise ValueError(f"账号标识应为 platform:id，得到 {key}")
    p, aid = key.split(":", 1)
    return p, aid


def status(key):
    p, aid = _split(key)
    if p == _XHS:
        s = _xhs_pool().summary().get(aid, {})
        return {"key": key, "platform": p, "id": aid,
                "status": s.get("status", UNKNOWN),
                "cooling": s.get("cooling", False),
                "reason": s.get("reason", ""), "ts": int(_time.time())}
    if p in _MAP_PLATFORMS:
        return _map_status(p, aid)
    rec = _load_ledger()["accounts"].get(key)
    if not rec:
        return {"key": key, "platform": p, "id": aid, "status": UNKNOWN,
                "reason": "未登记", "ts": 0}
    return {"key": key, "platform": p, "id": aid, "status": rec.get("status", UNKNOWN),
            "reason": rec.get("reason", ""), "ts": rec.get("ts", 0),
            "last_used": rec.get("last_used", 0)}


def _map_status(p, aid):
    M = _map_quota()
    prov = _MAP_PLATFORMS[p]
    try:
        q = M.MapQuota()
        krec = q.ledger.get("keys", {}).get(prov, [])
        idx = int(aid)
        info = krec[idx] if idx < len(krec) else {}
    except Exception:
        info = {}
    dead_until = info.get("dead_until")
    now = int(_time.time())
    st = DEAD if (dead_until and _parse_ts(dead_until) > now) else OK
    return {"key": f"{p}:{aid}", "platform": p, "id": aid, "status": st,
            "reason": info.get("dead_reason", "") or "",
            "daily_used": (info.get("daily") or {}).get("used", 0),
            "monthly_used": (info.get("monthly") or {}).get("used", 0),
            "ts": now}


def _parse_ts(v):
    """dead_until 可能是 epoch 或日期串；统一宽松处理。"""
    try:
        return int(v)
    except Exception:
        try:
            return int(_time.mktime(_time.strptime(str(v)[:10], "%Y-%m-%d")))
        except Exception:
            return 0


# ────────────────────── 活体探测 ──────────────────────
def probe(key, bu=None):
    """读当前状态；xhs 且传入浏览器 bu 时做一次真实登录/搜索探测并回写状态。"""
    p, aid = _split(key)
    if p == _XHS and bu is not None:
        import health as H
        ok, why = H.check_login(bu)
        pool = _xhs_pool()
        if ok:
            pool.mark_ok(aid)
        else:
            pool.mark_dead(aid, why)
        return status(key)
    return status(key)


# ────────────────────── 写状态（路由） ──────────────────────
def mark(key, new_status, reason=""):
    p, aid = _split(key)
    if p == _XHS:
        pool = _xhs_pool()
        if new_status == OK:
            pool.mark_ok(aid)
        elif new_status == RESTRICTED:
            pool.mark_restricted(aid, reason)
        elif new_status == DEAD:
            pool.mark_dead(aid, reason)
        else:
            raise ValueError(f"xhs 状态仅支持 ok/restricted/dead，得到 {new_status}")
        return status(key)
    if p in _MAP_PLATFORMS:
        # 地图 key 的死活只能由真实返回码在 map_quota 内驱动，禁止手工改，避免绕过配额仲裁。
        raise PermissionError(
            f"{p} 状态由 map_quota 依返回码维护，不支持手工 mark；请在 map_quota 路径处理")
    L = _load_ledger()
    rec = L["accounts"].get(key)
    if not rec:
        raise KeyError(f"账号未登记：{key}（先 register）")
    rec.update({"status": new_status, "reason": reason, "ts": int(_time.time())})
    _save_ledger(L)
    return status(key)


# ────────────────────── 选用 ──────────────────────
def pick(platform, want_credentials=False):
    """选一个当前可用账号，返回账号标识；全不可用返回 None。
    xhs 且 want_credentials=True 时返回 (key, cookies)。"""
    if platform == _XHS:
        aid, cookies = _xhs_pool().pick_account()
        if aid is None:
            return None
        key = f"{_XHS}:{aid}"
        return (key, cookies) if want_credentials else key
    if platform in _MAP_PLATFORMS:
        prov = _MAP_PLATFORMS[platform]
        ids = list(platform).get(platform, [])
        for aid in ids:
            if status(f"{platform}:{aid}")["status"] == OK:
                return f"{platform}:{aid}"
        return None
    # 通用账本：跳过非 ok，按 last_used 最久优先
    L = _load_ledger()
    cands = [(k, rec) for k, rec in L["accounts"].items()
             if rec["platform"] == platform and rec.get("status") == OK]
    if not cands:
        return None
    cands.sort(key=lambda kr: kr[1].get("last_used", 0))
    key, rec = cands[0]
    rec["last_used"] = int(_time.time())
    _save_ledger(L)
    return key


# ────────────────────── 汇总 ──────────────────────
def summary(platform=None):
    out = {}
    for p, ids in list(platform).items():
        out[p] = {"total": len(ids),
                  "by_status": {},
                  "accounts": [status(f"{p}:{aid}") for aid in ids]}
        for stt in out[p]["accounts"]:
            b = out[p]["by_status"]
            b[stt["status"]] = b.get(stt["status"], 0) + 1
    return out


# ────────────────────── CLI ──────────────────────
if __name__ == "__main__":
    if len(_sys.argv) > 1 and _sys.argv[1] == "summary":
        print(_json.dumps(summary(), ensure_ascii=False, indent=1))
    else:
        print(_json.dumps(list(), ensure_ascii=False, indent=1))

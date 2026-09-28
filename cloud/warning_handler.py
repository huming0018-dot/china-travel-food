#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""warning_handler.py — 看门狗「告警专项」（统一处理 warning、与用户沟通到解决）。

推送整顿后的关键收敛（2026-09-28）：
  - 【停用云端 headless 二维码】实测它在手机“确认登录”环节必 fail（服务端拒绝数据中心
    IP/自动化会话），继续推送=无效打扰。因此 -100 不再拉起/推送 headless 二维码。
  - 真·登录失效（双出口 -100）→ 推一条 ACTION 工单：指引用户在【本机真实 Chrome】重登
    （唯一可用路径，见 references/xhs-login-runbook）；按计划有界提醒，不刷屏。
  - poll() 每轮轻量复核：探测 code=0 → 自动关单并推一条 RESOLVED。
  - 所有文本外发统一走 notifier（分级/去重/冷却）；本模块不再直接拼通道。

由 watchdog 每 20 分钟调用 poll()；account_repair 在判定 dead 时调 request_login()。
"""
import json
import os
import pathlib
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, "/app/pipeline")

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "warning_tickets.json"

ACCT_LABEL = {"account_a": "账号A（主力·默认出口）",
              "account_b": "账号B（广州独立出口）"}


# ────────────────────── 工单账本（仅元数据 + TG offset） ──────────────────────
def _load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {"tickets": {}, "tg_offset": 0}


def _save(L):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(L, ensure_ascii=False, indent=2), encoding="utf-8")


# ────────────────────── TG 指令（非阻塞） ──────────────────────
def tg_commands(L):
    """收“已扫/好了/重拉”→ 对未决登录工单置 recheck（触发立即复核）。"""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        return
    base = (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")
    try:
        r = requests.get(f"{base}/bot{tok}/getUpdates",
                         params={"offset": L.get("tg_offset", 0), "timeout": 0}, timeout=15)
        ups = r.json().get("result", [])
    except Exception:
        return
    for u in ups:
        L["tg_offset"] = u["update_id"] + 1
        txt = (u.get("message", {}).get("text", "") or "")
        if any(k in txt for k in ("已扫", "好了", "登录好", "重拉", "刷新", "重登")):
            for t in L["tickets"].values():
                if t.get("kind") == "login" and t.get("state") in ("open", "waiting_user"):
                    t["recheck"] = True


# ────────────────────── 登录工单文案 ──────────────────────
def _login_body(account, detail):
    label = ACCT_LABEL.get(account, account)
    return (
        f"{label} 小红书登录已失效。\n"
        f"探测结论：{detail or '默认 + 广州两出口均 -100（web_session 过期）'}\n\n"
        "云端无法自助重登：云端/无头浏览器在手机“确认登录”环节会被服务端拒绝（已多次实测）。\n"
        "唯一可用路径是在这台 Mac 上用【真实 Google Chrome】登录后导出会话：\n"
        "1. 回到豆包对话对我说「重登」，我会在你电脑打开一个干净的真实 Chrome 登录窗口；\n"
        "   （也可按 skill 文档 xhs-login-runbook 手动操作）\n"
        "2. 用小红书 App 扫码并在手机上点确认，看到首页信息流即成功；\n"
        "3. 我会自动检测并恢复采集，无需回复结果。\n\n"
        "注意：同一账号不要在多个新窗口/设备重复登录，会把已有会话顶掉；\n"
        "若要第二个账号做独立出口，请用【另一个小红书账号】扫码。"
    )


_LOGIN_ACTION = "回到豆包对我说「重登」，我打开真实 Chrome 窗口给你扫码"


def request_login(account, detail="", restart=False):
    """account_repair R3 调用：登记登录工单 + 经 notifier 推一条 ACTION（不再拉云端二维码）。"""
    import notifier
    import xhs_qr_login as Q   # 仅用于清理可能残留的 headless worker（死路）
    now_i = int(time.time())
    L = _load()
    key = f"login:{account}"
    t = L["tickets"].get(key)
    try:
        if Q.is_running(account):
            Q.stop(account)
    except Exception:
        pass
    if not t or t.get("state") == "resolved":
        t = {"kind": "login", "account": account, "state": "waiting_user",
             "detail": detail, "created": now_i, "updated": now_i,
             "recheck": False}
        L["tickets"][key] = t
        _save(L)
    notifier.action(_login_body(account, detail), key=key, action_text=_LOGIN_ACTION)
    print(f"[warn] request_login {account} → 已发真实Chrome重登工单")
    return t


# ────────────────────── 复核与关单 ──────────────────────
def _recoverable(account):
    """轻量双出口探测：任一出口 code=0 → 可恢复。"""
    import account_repair as AR
    if AR.probe(account, use_proxy=False) == 0:
        return True
    time.sleep(4)
    return AR.probe(account, use_proxy=True) == 0


def poll():
    """watchdog 每轮：收指令 → 逐工单复核（恢复则关单；否则交给 notifier 有界提醒）。"""
    import notifier
    L = _load()
    tg_commands(L)
    now_i = int(time.time())

    for key, t in L["tickets"].items():
        if t.get("kind") != "login" or t.get("state") not in ("open", "waiting_user"):
            continue
        account = t["account"]
        force = bool(t.get("recheck"))
        if force or (now_i - int(t.get("updated", 0)) >= 1200):
            try:
                recovered = _recoverable(account)
            except Exception:
                recovered = False
            t["recheck"] = False
            t["updated"] = now_i
            if recovered:
                try:
                    import xhs_cookie_pool as Pool
                    Pool.mark_ok(account)
                except Exception:
                    pass
                t["state"] = "resolved"
                t["resolved"] = now_i
                notifier.resolve(
                    f"{ACCT_LABEL.get(account, account)} 已重登成功，采集自动恢复。", key=key)
                print(f"[warn] {account} 恢复，工单关闭")
            else:
                notifier.action(_login_body(account, t.get("detail", "")),
                                key=key, action_text=_LOGIN_ACTION)
        else:
            # 非复核窗口：仍让 notifier 按其计划判断是否到提醒点（函数内部节流）
            notifier.action(_login_body(account, t.get("detail", "")),
                            key=key, action_text=_LOGIN_ACTION)
    _save(L)
    return L


# ────────────────────── 通用非登录告警（统一走 notifier WARN） ──────────────────────
def warn(title, message, key, cooldown=3600):
    import notifier
    body = f"{title}\n{message}" if title else message
    return notifier.warn(body, key=f"misc:{key}", cooldown=cooldown)


if __name__ == "__main__":
    poll()

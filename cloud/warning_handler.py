#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""warning_handler.py — 看门狗的「告警专项」子代理（专门处理 warning、与用户沟通到解决）。

为什么单独存在：account_repair R3 原本只发一条一次性告警“请扫码”，之后无人跟进——
不会拉二维码、不会刷新、不会确认是否重登成功。本专项拥有告警的完整生命周期：

  open（检测到问题）
   → waiting_user（已把二维码推到 TG + 飞书，等你扫）
   → resolved（探测确认登录恢复，推送成功，关单）
   期间：二维码过期自动重拉、限时提醒、回复“重拉”可立即换新码。

由 watchdog 每 20 分钟调用 poll()；账号真失效时 account_repair 调 request_login()。
登录二维码由 xhs_qr_login 在后台隔离 headless 生成；成功后 cookie 由【宿主机安装器】搬运。

也提供通用 warn()：非登录类告警同样建工单、去重、双通道推送，使本模块成为统一 warning 入口。
"""
import json
import os
import pathlib
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "warning_tickets.json"
PROXY_F = DATA / "account_proxies.json"

WINDOW_SEC = 3600          # 单个登录 worker 存活（持续刷新二维码）
MAX_RESTARTS = 6           # worker 超时后自动重拉次数
ACCT_LABEL = {"account_a": "账号A（主力·默认出口）",
              "account_b": "账号B（广州独立出口）"}


# ────────────────────── 工单账本 ──────────────────────
def _load():
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {"tickets": {}, "tg_offset": 0}


def _save(L):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(L, ensure_ascii=False, indent=2), encoding="utf-8")


def _proxy_for(account):
    try:
        return json.loads(PROXY_F.read_text(encoding="utf-8")).get(account)
    except Exception:
        return None


# ────────────────────── 通道：Telegram ──────────────────────
def _tg():
    base = (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return base, tok, chat


def tg_text(text):
    base, tok, chat = _tg()
    if not (tok and chat):
        return False
    try:
        r = requests.post(f"{base}/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text,
                                "disable_web_page_preview": True}, timeout=20)
        return r.json().get("ok") is True
    except Exception as e:
        print("[warn] tg_text", e)
        return False


def tg_photo(path, caption):
    base, tok, chat = _tg()
    if not (tok and chat):
        return False
    try:
        with open(path, "rb") as f:
            r = requests.post(f"{base}/bot{tok}/sendPhoto",
                              data={"chat_id": chat, "caption": caption},
                              files={"photo": (pathlib.Path(path).name, f, "image/png")},
                              timeout=30)
        return r.json().get("ok") is True
    except Exception as e:
        print("[warn] tg_photo", e)
        return False


def tg_commands(L):
    """非阻塞拉取 TG 指令（重拉/已扫），更新 offset。"""
    base, tok, chat = _tg()
    if not tok:
        return
    try:
        r = requests.get(f"{base}/bot{tok}/getUpdates",
                         params={"offset": L.get("tg_offset", 0), "timeout": 0},
                         timeout=15)
        ups = r.json().get("result", [])
    except Exception:
        return
    for u in ups:
        L["tg_offset"] = u["update_id"] + 1
        try:
            txt = (u.get("message", {}).get("text", "") or "")
        except Exception:
            txt = ""
        low = txt.lower()
        if any(k in txt for k in ("重拉", "重新生成", "换新", "刷新")) or "refresh" in low:
            for key, t in L["tickets"].items():
                if t["kind"] == "login" and t["state"] in ("open", "waiting_user"):
                    t["restarts"] = MAX_RESTARTS  # 强制下轮重拉
                    t["force"] = True
        elif any(k in txt for k in ("已扫", "好了", "登录好")) or "done" in low:
            for key, t in L["tickets"].items():
                if t["kind"] == "login" and t["state"] in ("open", "waiting_user"):
                    t["recheck"] = True


# ────────────────────── 通道：飞书自建应用 ──────────────────────
def _fs_token():
    base = (os.environ.get("FEISHU_API_BASE") or "https://open.feishu.cn/open-apis").rstrip("/")
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not (app_id and app_secret):
        return None, base
    try:
        r = requests.post(base + "/auth/v3/tenant_access_token/internal",
                          json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
        return r.json().get("tenant_access_token"), base
    except Exception:
        return None, base


def fs_text(text):
    token, base = _fs_token()
    chat = os.environ.get("FEISHU_CHAT_ID", "").strip()
    if not (token and chat):
        return False
    try:
        r = requests.post(base + "/im/v1/messages?receive_id_type=chat_id",
                          headers={"Authorization": "Bearer " + token},
                          json={"receive_id": chat, "msg_type": "text",
                                "content": json.dumps({"text": text}, ensure_ascii=False)},
                          timeout=20)
        return r.json().get("code") == 0
    except Exception as e:
        print("[warn] fs_text", e)
        return False


def fs_photo(path, caption):
    token, base = _fs_token()
    chat = os.environ.get("FEISHU_CHAT_ID", "").strip()
    if not (token and chat):
        return False
    try:
        with open(path, "rb") as f:
            up = requests.post(base + "/im/v1/images",
                               headers={"Authorization": "Bearer " + token},
                               data={"image_type": "message"},
                               files={"image": (pathlib.Path(path).name, f, "image/png")},
                               timeout=30).json()
        image_id = up.get("data", {}).get("image_key")
        if not image_id:
            return False
        requests.post(base + "/im/v1/messages?receive_id_type=chat_id",
                      headers={"Authorization": "Bearer " + token},
                      json={"receive_id": chat, "msg_type": "image",
                            "content": json.dumps({"image_id": image_id})}, timeout=20)
        if caption:
            requests.post(base + "/im/v1/messages?receive_id_type=chat_id",
                          headers={"Authorization": "Bearer " + token},
                          json={"receive_id": chat, "msg_type": "text",
                                "content": json.dumps({"text": caption}, ensure_ascii=False)},
                          timeout=20)
        return True
    except Exception as e:
        print("[warn] fs_photo", e)
        return False


def _both_text(text):
    a = tg_text(text)
    b = fs_text(text)
    return a or b


def _both_photo(path, caption):
    a = tg_photo(path, caption)
    b = fs_photo(path, caption)
    return a or b


# ────────────────────── 登录重登（交互式） ──────────────────────
def _caption(account, detail):
    label = ACCT_LABEL.get(account, account)
    return (f"🍜 {label} 小红书登录已失效，需要你扫码重登\n\n"
            "1️⃣ 打开小红书 App →「我」→ 右上角扫一扫\n"
            "2️⃣ 扫描下方二维码（每分钟自动刷新，以最新一张为准）\n"
            "3️⃣ 确认登录即可，成功后我会立刻在此通知，无需回复\n\n"
            f"原因：{detail or '双出口探测 web_session 过期'}")


def _push_fresh_qr(account, caption, t):
    import xhs_qr_login as Q
    P = Q.paths(account)
    for _ in range(16):  # 等二维码就绪（最多 ~16s）
        st = Q.status(account)
        if st.get("state") == "waiting" and P["qr"].exists():
            break
        time.sleep(1)
    if P["qr"].exists():
        ok = _both_photo(str(P["qr"]), caption)
        now = int(time.time())
        t["last_qr_push"] = now
        t["qr_pushed"] = t.get("qr_pushed") or now
        return ok
    return False


def request_login(account, detail=""):
    """account_repair R3 调用：建工单 + 后台拉二维码 + 双通道推送。"""
    import xhs_qr_login as Q
    L = _load()
    key = f"login:{account}"
    t = L["tickets"].get(key)
    if t and t["state"] in ("open", "waiting_user") and Q.is_running(account) and not t.get("force"):
        return t
    now = int(time.time())
    keep_restarts = t.get("restarts", 0) if t else 0
    t = {"kind": "login", "account": account, "state": "open", "detail": detail,
         "created": t.get("created", now) if t else now, "updated": now,
         "qr_pushed": None, "last_qr_push": 0, "reminders": 0,
         "restarts": keep_restarts, "resolved": None, "force": False, "recheck": False}
    L["tickets"][key] = t
    _save(L)
    Q.start(account, _proxy_for(account), WINDOW_SEC)
    _push_fresh_qr(account, _caption(account, detail), t)
    t["state"] = "waiting_user"
    t["updated"] = int(time.time())
    _save(L)
    print(f"[warn] request_login {account} → 二维码已推送")
    return t


def _verify_installed(account, t, wait_sec=90):
    """等宿主机安装器搬 cookie，再探测 code=0。返回 bool。"""
    import xhs_qr_login as Q
    import account_repair as AR
    P = Q.paths(account)
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if t.get("recheck") or not P["new"].exists():
            code = AR.probe(account, use_proxy=False)
            if code == 0:
                try:
                    import xhs_cookie_pool as Pool
                    Pool.mark_ok(account)
                except Exception:
                    pass
                return True
        time.sleep(10)
    return False


def poll():
    """看门狗每轮调用：处理指令 + 推进每张登录工单。"""
    import xhs_qr_login as Q
    L = _load()
    tg_commands(L)

    for key, t in L["tickets"].items():
        if t["kind"] != "login" or t["state"] not in ("open", "waiting_user"):
            continue
        account = t["account"]
        now = int(time.time())
        P = Q.paths(account)

        # ① 已扫码成功（worker 写出 new cookie）→ 等安装 → 验证 → 关单
        if Q.status(account).get("state") == "done" or P["new"].exists():
            if _verify_installed(account, t):
                t["state"] = "resolved"
                t["resolved"] = now
                label = ACCT_LABEL.get(account, account)
                _both_text(f"✅ {label} 已重登成功，采集自动恢复，无需操作。")
                print(f"[warn] {account} 重登成功，工单关闭")
            t["recheck"] = False
            t["updated"] = now
            _save(L)
            continue

        # ② 用户回复“重拉”或 worker 已退出（超时）→ 重新生成二维码
        need_restart = t.get("force") or not Q.is_running(account)
        if need_restart:
            t["force"] = False
            if t["restarts"] < MAX_RESTARTS or t.get("force"):
                t["restarts"] += 1
                Q.start(account, _proxy_for(account), WINDOW_SEC)
                cap = _caption(account, t.get("detail", "")) + "\n\n（旧二维码已过期，这是新的）"
                _push_fresh_qr(account, cap, t)
                t["state"] = "waiting_user"
            else:
                # 多次重拉仍未扫：慢速提醒，每 2h 一次，工单保持
                if now - t.get("last_qr_push", 0) >= 7200:
                    _both_text(_caption(account, t.get("detail", ""))
                               + "\n\n（如需新二维码，回复“重拉”）")
                    t["last_qr_push"] = now
            t["updated"] = now
            _save(L)
            continue

        # ③ worker 运行中、仍待扫：限时推送刷新后的二维码（20/40min，然后每 60min）
        elapsed = now - t.get("last_qr_push", 0)
        due = (t["reminders"] < 2 and elapsed >= 1200) or \
              (t["reminders"] >= 2 and elapsed >= 3600)
        if due and P["qr"].exists():
            _both_photo(str(P["qr"]), _caption(account, t.get("detail", ""))
                        + f"\n\n（提醒 {t['reminders']+1}：仍待扫码）")
            t["reminders"] += 1
            t["last_qr_push"] = now
            t["updated"] = now
            _save(L)

    _save(L)
    return L


# ────────────────────── 通用非登录告警（统一 warning 入口） ──────────────────────
def warn(title, message, key, cooldown=21600):
    L = _load()
    t = L["tickets"].get(f"misc:{key}")
    now = int(time.time())
    if t and t["state"] == "open" and now - t["updated"] < cooldown:
        return t
    L["tickets"][f"misc:{key}"] = {
        "kind": "misc", "state": "open", "title": title, "detail": message,
        "created": now, "updated": now}
    _save(L)
    _both_text(f"{title}\n{message}")
    return t


if __name__ == "__main__":
    poll()

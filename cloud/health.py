#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""health.py — 小红书登录态失效检测 + 多通道告警（Telegram / 飞书 / Bark / Server酱）。

云端无法自己扫码，cookie 过期必须让人知道。每次采集前探测 explore，
被重定向登录 / 出现遮罩 / 拉不到笔记流即判失效：
  1. 写标记 /app/data/COOKIE_INVALID；
  2. 多通道推送（按环境变量启用：Telegram + 飞书，可再叠加 Bark/Server酱）；
  3. 编排据此跳过本轮，不硬刷。

防刷屏：每类告警带冷却（ALERT_COOLDOWN_SEC，默认 21600=6 小时），
状态记录在 /app/data/_alert_state.json；任务完成类 once=True 只发一次。

环境变量：
  TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
  TELEGRAM_API_BASE（可选，国内服务器用反代；默认 https://api.telegram.org）
  FEISHU_WEBHOOK、FEISHU_SECRET（可选，自定义机器人 webhook + 签名校验）
  FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_CHAT_ID（可选，开放平台应用机器人）
  FEISHU_API_BASE（可选，默认 https://open.feishu.cn/open-apis）
  ALERT_WEBHOOK（可选，Bark / Server酱 / 通用）
  HTTPS_PROXY / HTTP_PROXY（可选，容器出口代理，requests 自动识别）
  ALERT_COOLDOWN_SEC（默认 21600）
"""
import base64
import hashlib
import hmac
import json
import os
import pathlib
import time
import urllib.parse

import requests

DATA_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
STATE_F = pathlib.Path(DATA_DIR) / "_alert_state.json"


# ------------------------------------------------ 登录态探测
def check_login(bu):
    """返回 (ok: bool, 原因: str)。bu 为已注入 cookie 的浏览器。"""
    bu.navigate("https://www.xiaohongshu.com/explore")
    bu.wait(3.0)
    info = bu.js(r"""
    const t=document.body.innerText||'';
    const mask=/扫码登录|手机号登录|验证码登录/.test(t) &&
      !!(document.querySelector('.login-container,#login-container,.qrcode-container, .reds-mask'));
    return {
      href: location.href,
      loginMask: !!mask,
      items: document.querySelectorAll('section.note-item').length,
      blocked: /当前笔记暂时无法浏览|登录后查看/.test(t)
    };
    """)
    if "login" in info.get("href", ""):
        return False, "被重定向到登录页"
    if info.get("loginMask"):
        return False, "出现登录遮罩"
    if info.get("blocked"):
        return False, "页面要求登录后查看"
    if info.get("items", 0) < 3:
        return False, "拉不到笔记流（items=%s）" % info.get("items")
    return True, ""


def _pool():
    import xhs_cookie_pool as P
    return P


def mark_invalid(reason, account_id="default"):
    _pool().mark_dead(account_id, reason)


def clear_invalid(account_id="default"):
    _pool().mark_ok(account_id)


# ------------------------------------------------ 搜索风控探测（300011）
# explore 首页正常 ≠ 搜索可用。账号被风控时搜索整页跳 website-login/error（300011），
# 旧逻辑只探 explore 会误判"登录正常"，然后空跑 0 笔记。
SEARCH_MARK = "SEARCH_RESTRICTED"
SEARCH_RETRY_SEC = 3 * 3600  # 风控后每 3 小时才真正重开浏览器复检，期间直接跳过


def check_search(bu):
    """返回 (状态, 原因)。状态：ok / restricted / unknown。"""
    bu.navigate("https://www.xiaohongshu.com/search_result?keyword="
                + urllib.parse.quote("美食"))
    bu.wait_for_load(timeout=15)
    bu.wait(2.5)
    info = bu.js(r"""
    const t=document.body.innerText||'';
    return {
      href: location.href,
      items: document.querySelectorAll('section.note-item').length,
      err: /当前账号存在异常|安全限制|300011/.test(t)
    };
    """)
    href = info.get("href", "")
    if "website-login/error" in href or info.get("err"):
        return "restricted", "搜索被风控（300011 当前账号存在异常）"
    if info.get("items", 0) >= 3:
        return "ok", ""
    return "unknown", "搜索无卡片且未见明确风控页"


def mark_search_restricted(reason, account_id="default"):
    _pool().mark_restricted(account_id, reason)


def clear_search_restricted(account_id="default"):
    _pool().mark_ok(account_id)


def search_recently_restricted(account_id="default"):
    """该账号是否在搜索风控冷却窗口内（委托 cookie 池，按账号计时）。"""
    return _pool().is_cooling(account_id)


# ------------------------------------------------ 防刷屏状态
def _read_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st):
    try:
        STATE_F.parent.mkdir(parents=True, exist_ok=True)
        STATE_F.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def should_send(key, cooldown=None, once=False):
    """该类告警现在是否应发送。once=True 只发一次；否则按冷却秒数。"""
    cd = int(os.environ.get("ALERT_COOLDOWN_SEC", "21600")
             if cooldown is None else cooldown)
    rec = _read_state().get(key, {})
    if rec.get("sent"):
        if once:
            return False
        if int(time.time()) - int(rec.get("ts", 0)) < cd:
            return False
    return True


def note_sent(key):
    st = _read_state()
    st[key] = {"sent": True, "ts": int(time.time())}
    _write_state(st)


# ------------------------------------------------ 通道开关（可独立暂停）
CHANNELS_FILE = pathlib.Path(DATA_DIR) / "notify_channels.json"
_CHANNEL_ENV = {"telegram": "NOTIFY_TELEGRAM", "feishu_app": "NOTIFY_FEISHU_APP",
                "feishu": "NOTIFY_FEISHU"}


def channel_enabled(name):
    """通道总开关，默认全开。判定顺序：NOTIFY_* 环境变量 → notify_channels.json → 开。
    name: telegram / feishu_app / feishu。所有通道原语与 health.alert 都先过此闸，
    暂停某通道（如飞书）即可一处覆盖看门狗/播报/各补齐脚本的全部外发。"""
    env = _CHANNEL_ENV.get(name)
    if env:
        v = os.environ.get(env)
        if v is not None:
            return v.strip().lower() not in ("0", "false", "no", "off")
    try:
        m = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        return bool(m.get(name, True))
    except Exception:
        return True


# ------------------------------------------------ 各通道
def _post_with_retry(url, **kw):
    """带指数退避的 POST（2s/4s）；返回最后一个 Response 或抛最后异常。"""
    last = None
    for i in range(3):
        try:
            return requests.post(url, timeout=20, **kw)
        except requests.RequestException as e:
            last = e
            time.sleep(min(2 ** i, 4))
    raise last


def _telegram(message, title):
    """TG：反代(TELEGRAM_API_BASE)失败自动降级直连；每个 base 带退避重试。"""
    if not channel_enabled("telegram"):
        return None
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    body = {"chat_id": chat, "text": f"{title}\n{message}",
            "disable_web_page_preview": True}
    cfg = (os.environ.get("TELEGRAM_API_BASE") or "").strip().rstrip("/")
    bases = [b for b in (cfg, "https://api.telegram.org") if b]
    bases = list(dict.fromkeys(bases))   # 配置在前、直连兜底在后；去重
    for base in bases:
        try:
            r = _post_with_retry(f"{base}/bot{token}/sendMessage", json=body)
            if r.status_code == 200 and r.json().get("ok") is True:
                return True
            print("TG", base, "异常响应", r.status_code, r.text[:120])
        except Exception as e:
            print("TG", base, "失败", repr(e)[:120])
    return False


# 飞书 tenant_access_token 进程内缓存（提前 5 分钟刷新；失效码强制重取）
_FS_TOKEN = {"tok": None, "exp": 0}
_FS_TOKEN_INVALID = {99991663, 99991664, 99991668, 99991661}


def _fs_tenant_token(base, force=False):
    now = time.time()
    if not force and _FS_TOKEN["tok"] and now < _FS_TOKEN["exp"]:
        return _FS_TOKEN["tok"]
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return None
    try:
        tr = _post_with_retry(base + "/auth/v3/tenant_access_token/internal",
                              json={"app_id": app_id, "app_secret": app_secret})
        j = tr.json()
        tok = j.get("tenant_access_token")
        if tok:
            _FS_TOKEN["tok"] = tok
            _FS_TOKEN["exp"] = now + int(j.get("expire", 7200)) - 300
        else:
            print("飞书应用: 取 token 失败", j.get("code"), j.get("msg"))
        return tok
    except Exception as e:
        print("飞书应用: 取 token 异常", repr(e)[:120])
        return None


def _feishu(message, title):
    """飞书自定义 webhook（带签名）；退避重试。"""
    if not channel_enabled("feishu"):
        return None
    url = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not url:
        return None
    body = {"msg_type": "text", "content": {"text": f"{title}\n{message}"}}
    secret = os.environ.get("FEISHU_SECRET", "").strip()
    if secret:
        ts = str(int(time.time()))
        sig = hmac.new(f"{ts}\n{secret}".encode("utf-8"),
                       digestmod=hashlib.sha256).digest()
        body["timestamp"] = ts
        body["sign"] = base64.b64encode(sig).decode("utf-8")
    try:
        r = _post_with_retry(url, json=body)
        data = r.json()
        return data.get("StatusCode", data.get("code", -1)) == 0
    except Exception as e:
        print("飞书 webhook 失败", repr(e)[:120])
        return False


def _feishu_app(message, title):
    """飞书自建应用：token 缓存+失效自动刷新；失败退避重试；与其它通道独立判定。"""
    if not channel_enabled("feishu_app"):
        return None
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    chat_id = os.environ.get("FEISHU_CHAT_ID", "").strip()
    if not app_id or not os.environ.get("FEISHU_APP_SECRET", "").strip() or not chat_id:
        return None
    base = (os.environ.get("FEISHU_API_BASE")
            or "https://open.feishu.cn/open-apis").rstrip("/")
    content = json.dumps({"text": f"{title}\n{message}"}, ensure_ascii=False)
    for attempt in range(2):
        tok = _fs_tenant_token(base, force=(attempt == 1))
        if not tok:
            time.sleep(2)
            continue
        try:
            r = _post_with_retry(
                base + "/im/v1/messages?receive_id_type=chat_id",
                headers={"Authorization": "Bearer " + tok,
                         "Content-Type": "application/json; charset=utf-8"},
                json={"receive_id": chat_id, "msg_type": "text", "content": content})
            j = r.json()
            if j.get("code") == 0:
                return True
            print("飞书应用:", j.get("code"), j.get("msg"))
            if j.get("code") in _FS_TOKEN_INVALID:   # token 失效→强制刷新重试一次
                _FS_TOKEN["tok"] = None
                continue
            return False
        except Exception as e:
            print("飞书应用发送异常", repr(e)[:120])
            time.sleep(min(2 ** attempt, 4))
    return False


# ------------------------------------------------ 统一入口
def alert(message, title="上海美食图鉴·采集告警", key="default", once=False, cooldown=None):
    if not should_send(key, cooldown=cooldown, once=once):
        print(f"【告警】冷却中，跳过重复推送：{key}")
        return
    results = {}
    tg = _telegram(message, title)
    if tg is not None:
        results["telegram"] = tg
    fs = _feishu(message, title)
    if fs is not None:
        results["feishu"] = fs
    fsa = _feishu_app(message, title)
    if fsa is not None:
        results["feishu_app"] = fsa
    wh = _legacy_webhook(message, title)
    if wh is not None:
        results["webhook"] = wh
    if not results:
        print("【告警】（未配置任何通道）", title, message)
        return
    print("告警推送结果：", results)
    if any(results.values()):
        note_sent(key)


if __name__ == "__main__":
    # 手动自检：python3 health.py
    print("DATA_DIR", DATA_DIR)
    print("Telegram:", "已配置" if os.environ.get("TELEGRAM_BOT_TOKEN") else "未配置")
    print("飞书webhook:", "已配置" if os.environ.get("FEISHU_WEBHOOK") else "未配置")
    print("飞书应用:", "已配置" if (os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_CHAT_ID")) else "未配置")
    print("ALERT_WEBHOOK:", "已配置" if os.environ.get("ALERT_WEBHOOK") else "未配置")

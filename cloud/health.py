#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""health.py — 小红书登录态失效检测 + Telegram 告警（飞书通道已彻底移除）。

云端无法自己扫码，cookie 过期必须让人知道。每次采集前探测 explore，
被重定向登录 / 出现遮罩 / 拉不到笔记流即判失效：
  1. 写标记 /app/data/COOKIE_INVALID；
  2. 经 Telegram 推送；
  3. 编排据此跳过本轮，不硬刷。

防刷屏：每类告警带冷却（ALERT_COOLDOWN_SEC，默认 21600=6 小时），
状态记录在 /app/data/_alert_state.json；任务完成类 once=True 只发一次。

环境变量：
  TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID
  TELEGRAM_API_BASE（可选，国内服务器用反代；默认 https://api.telegram.org）
  ALERT_WEBHOOK（可选，Bark / Server酱 / 通用）
  HTTPS_PROXY / HTTP_PROXY（可选，容器出口代理，requests 自动识别）
  ALERT_COOLDOWN_SEC（默认 21600）
"""
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
_CHANNEL_ENV = {"telegram": "NOTIFY_TELEGRAM"}


def channel_enabled(name):
    """通道总开关，默认全开。判定顺序：NOTIFY_* 环境变量 → notify_channels.json → 开。
    name: telegram。所有通道原语与 health.alert 都先过此闸。"""
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
    # 2026-10-06 Supabase RPC relay first (pg_net from DB reaches TG; deno relay suspended, direct TG blocked from CN)
    sb_url = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
    sb_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    ops_secret = (os.environ.get("CROWD_OPS_SECRET") or "").strip()
    if sb_url and sb_key and ops_secret:
        try:
            r = _post_with_retry(sb_url + "/rest/v1/rpc/crowd_notify_tg",
                                 json={"p_text": body["text"], "p_secret": ops_secret},
                                 headers={"apikey": sb_key,
                                          "Authorization": "Bearer " + sb_key})
            if r.status_code == 200 and r.json().get("ok") is True:
                return True
            print("TG supabase-relay bad", r.status_code, r.text[:120])
        except Exception as e:
            print("TG supabase-relay fail", repr(e)[:120])
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


# ------------------------------------------------ 统一入口
def alert(message, title="上海美食图鉴·采集告警", key="default", once=False, cooldown=None):
    if not should_send(key, cooldown=cooldown, once=once):
        print(f"【告警】冷却中，跳过重复推送：{key}")
        return
    results = {}
    tg = _telegram(message, title)
    if tg is not None:
        results["telegram"] = tg
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
    print("ALERT_WEBHOOK:", "已配置" if os.environ.get("ALERT_WEBHOOK") else "未配置")

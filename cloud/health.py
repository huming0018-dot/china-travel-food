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


def mark_invalid(reason):
    p = pathlib.Path(DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    (p / "COOKIE_INVALID").write_text(
        "小红书 cookie 已失效：%s\n请重新导出 cookie 并更新 XHS_COOKIE。\n" % reason,
        encoding="utf-8")


def clear_invalid():
    f = pathlib.Path(DATA_DIR) / "COOKIE_INVALID"
    if f.exists():
        f.unlink()


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


# ------------------------------------------------ 各通道
def _telegram(message, title):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    api_base = (os.environ.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")
    url = f"{api_base}/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat,
            "text": f"{title}\n{message}",
            "disable_web_page_preview": True,
        }, timeout=20)
        return r.status_code == 200 and r.json().get("ok") is True
    except requests.RequestException as e:
        print("Telegram 推送失败:", e)
        return False


def _feishu(message, title):
    url = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not url:
        return None
    body = {
        "msg_type": "text",
        "content": {"text": f"{title}\n{message}"},
    }
    secret = os.environ.get("FEISHU_SECRET", "").strip()
    if secret:
        ts = str(int(time.time()))
        # 飞书官方签名：hmac key="{timestamp}\n{secret}"，message 为空，sha256 后 base64
        string_to_sign = f"{ts}\n{secret}".encode("utf-8")
        hmac_code = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
        body["timestamp"] = ts
        body["sign"] = base64.b64encode(hmac_code).decode("utf-8")
    try:
        r = requests.post(url, json=body, timeout=15)
        data = r.json()
        # 自定义机器人成功为 StatusCode=0；部分网关返回 code=0
        return data.get("StatusCode", data.get("code", -1)) == 0
    except requests.RequestException as e:
        print("飞书推送失败:", e)
        return False


def _feishu_app(message, title):
    """飞书开放平台企业自建应用机器人（app_id/app_secret -> tenant_access_token -> im/v1/messages）。

    环境变量：FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_CHAT_ID；
    可选 FEISHU_API_BASE（默认 https://open.feishu.cn/open-apis）。
    """
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    chat_id = os.environ.get("FEISHU_CHAT_ID", "").strip()
    if not app_id or not app_secret or not chat_id:
        return None
    base = (os.environ.get("FEISHU_API_BASE")
            or "https://open.feishu.cn/open-apis").rstrip("/")
    try:
        tr = requests.post(base + "/auth/v3/tenant_access_token/internal",
                           json={"app_id": app_id, "app_secret": app_secret},
                           timeout=15)
        token = tr.json().get("tenant_access_token")
        if not token:
            print("飞书应用：取 tenant_access_token 失败", tr.text[:160])
            return False
        content = json.dumps({"text": f"{title}\n{message}"}, ensure_ascii=False)
        r = requests.post(base + "/im/v1/messages?receive_id_type=chat_id",
                          headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "application/json; charset=utf-8"},
                          json={"receive_id": chat_id, "msg_type": "text",
                                "content": content}, timeout=15)
        data = r.json()
        if data.get("code", -1) != 0:
            print("飞书应用：发消息失败", data.get("code"), data.get("msg"))
        return data.get("code", -1) == 0
    except requests.RequestException as e:
        print("飞书应用推送失败:", e)
        return False


def _legacy_webhook(message, title):
    url = os.environ.get("ALERT_WEBHOOK", "").strip()
    if not url:
        return None
    try:
        low = url.lower()
        if "bark" in low:  # Bark: {host}/{key}/{title}/{body}
            u = url.rstrip("/") + "/" + urllib.parse.quote(title) + "/" + urllib.parse.quote(message)
            requests.get(u, timeout=15)
        elif "ftqq" in low or "sctapi" in low or "server" in low:  # Server酱
            requests.get(url, params={"title": title, "desp": message}, timeout=15)
        else:  # 通用 POST
            requests.post(url, json={"title": title, "text": message,
                                     "content": message}, timeout=15)
        return True
    except requests.RequestException as e:
        print("Webhook 推送失败:", e)
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

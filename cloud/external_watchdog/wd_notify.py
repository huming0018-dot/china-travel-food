#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wd_notify.py — 外部入站看门狗的独立通知（Telegram + 飞书自建应用）。

凭据来自同目录 notify.env（chmod 600，值不入库/不回显）。
通道实现与仓库 cloud/health.py 等价：TG 走 TELEGRAM_API_BASE 反代、失败降级直连；
飞书自建应用取 tenant_access_token 后发 im 文本，token 失效自动刷新重试。
"""
import json
import os
import pathlib
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent


def load_env():
    f = HERE / "notify.env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.strip().partition("=")
            if k and k not in os.environ:
                os.environ[k] = v


def _post(url, **kw):
    return requests.post(url, timeout=20, **kw)


def _telegram(title, message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return False
    body = {"chat_id": chat, "text": f"{title}\n{message}",
            "disable_web_page_preview": True}
    cfg = (os.environ.get("TELEGRAM_API_BASE") or "").strip().rstrip("/")
    bases = list(dict.fromkeys([b for b in (cfg, "https://api.telegram.org") if b]))
    for base in bases:
        try:
            r = _post(f"{base}/bot{token}/sendMessage", json=body)
            if r.status_code == 200 and r.json().get("ok") is True:
                return True
        except Exception as e:
            print("TG fail", base, repr(e)[:100])
    return False


_TOK = {"t": None, "exp": 0}


def _fs_token(base, force=False):
    now = time.time()
    if not force and _TOK["t"] and now < _TOK["exp"]:
        return _TOK["t"]
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return None
    try:
        r = _post(base + "/auth/v3/tenant_access_token/internal",
                  json={"app_id": app_id, "app_secret": app_secret})
        j = r.json()
        if j.get("tenant_access_token"):
            _TOK["t"] = j["tenant_access_token"]
            _TOK["exp"] = now + int(j.get("expire", 7200)) - 300
            return _TOK["t"]
    except Exception as e:
        print("FS token fail", repr(e)[:100])
    return None


def _feishu(title, message):
    chat = os.environ.get("FEISHU_CHAT_ID", "").strip()
    if not chat:
        return False
    base = (os.environ.get("FEISHU_API_BASE")
            or "https://open.feishu.cn/open-apis").rstrip("/")
    content = json.dumps({"text": f"{title}\n{message}"}, ensure_ascii=False)
    for attempt in range(2):
        tok = _fs_token(base, force=(attempt == 1))
        if not tok:
            time.sleep(2)
            continue
        try:
            r = _post(base + "/im/v1/messages?receive_id_type=chat_id",
                      headers={"Authorization": "Bearer " + tok,
                               "Content-Type": "application/json; charset=utf-8"},
                      json={"receive_id": chat, "msg_type": "text", "content": content})
            if r.json().get("code") == 0:
                return True
        except Exception as e:
            print("FS send fail", repr(e)[:100])
        time.sleep(2)
    return False


def send(title, message):
    load_env()
    t = _telegram(title, message)
    f = _feishu(title, message)
    print(f"notify tg={t} fs={f}")
    return t or f


if __name__ == "__main__":
    send("上海美食图鉴·看门狗自检", "通知通道测试：收到说明外部入站看门狗推送正常。无需操作。")

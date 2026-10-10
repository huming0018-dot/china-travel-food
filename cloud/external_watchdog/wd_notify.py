#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wd_notify.py — 外部入站看门狗的独立通知（仅 Telegram；飞书通道已彻底移除）。

凭据来自同目录 notify.env（chmod 600，值不入库/不回显）。
TG 走 TELEGRAM_API_BASE 反代、失败降级直连。
"""
import os
import pathlib

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


def send(title, message):
    load_env()
    t = _telegram(title, message)
    print(f"notify tg={t}")
    return t


if __name__ == "__main__":
    send("上海美食图鉴·看门狗自检", "通知通道测试：收到说明外部入站看门狗推送正常。无需操作。")

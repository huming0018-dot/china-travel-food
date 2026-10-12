#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deuce 本地 Telegram 推送（容器 notifier / Deno 反代失效后的统一出口）。

背景：腾讯云容器直连 api.telegram.org 被墙、Deno 免费反代会 503 USAGE_EXCEEDED；
而定时任务的运行环境是 deuce 本机（可直连，或走本地代理 127.0.0.1:7897）。
故所有由定时任务 / 看门狗 / 告警对话发出的 TG 消息，一律在 deuce 本地用本脚本发送；
容器内 /usr/sbin/cron 的完全无人值守作业不经 agent，无法用本通道（需另配容器出口）。

用法：
  python3 tg_send.py "消息文本"
  echo "消息" | python3 tg_send.py
  python3 tg_send.py -c <chatId> "文本"
凭据读取顺序（KEY=VALUE，token 不得写进本脚本）：
  环境变量 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID
  -> 本目录 .tg_env -> skill 根 .tg_env
  -> ~/.config/food-atlas/tg.env
  -> ~/work/china-travel-food/cloud/deploy.env
退出码：0 成功（打印 message_id）；2 缺凭据/正文；1 发送失败。
"""
import os
import sys
import json
import pathlib
import urllib.request
import urllib.parse

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
OFFICIAL = "https://api.telegram.org"
LOCAL_PROXY = "http://127.0.0.1:7897"
# 海外边缘反代（Supabase Edge tg-relay）：连不上 api.telegram.org 的环境（如 Linux 沙箱）
# 可经它转发；容器用 TELEGRAM_API_BASE 指向同一地址。
RELAY_DEFAULT = "https://bdwrhshgdeghgyzwpxnl.supabase.co/functions/v1/tg-relay"
ENV_FILES = [
    SCRIPT_DIR / ".tg_env",
    SKILL_ROOT / ".tg_env",
    pathlib.Path.home() / ".config" / "food-atlas" / "tg.env",
    pathlib.Path.home() / "work" / "china-travel-food" / "cloud" / "deploy.env",
]


def load_env_files():
    for p in ENV_FILES:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except FileNotFoundError:
            pass


def post(token, payload, proxy=None):
    url = "%s/bot%s/sendMessage" % (OFFICIAL, token)
    data = urllib.parse.urlencode(payload).encode()
    handlers = (
        [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    )
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=data, method="POST")
    with opener.open(req, timeout=20) as r:
        return json.loads(r.read().decode())


def post_relay(base, token, payload, proxy=None):
    url = "%s/bot%s/sendMessage" % (base.rstrip("/"), token)
    data = json.dumps(payload).encode()
    handlers = (
        [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    )
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=25) as r:
        return json.loads(r.read().decode())


def main():
    load_env_files()
    args = sys.argv[1:]
    chat = None
    if args and args[0] == "-c":
        chat, args = args[1], args[2:]
    text = " ".join(args).strip() if args else sys.stdin.read().strip()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    chat = chat or os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TG_CHAT_ID")
    if not token or not chat or not text:
        print("ERR missing token/chat/text", file=sys.stderr)
        return 2

    attempts = []
    hp = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if hp:
        attempts.append(hp)
    attempts.append(None)  # 直连
    if LOCAL_PROXY not in attempts:
        attempts.append(LOCAL_PROXY)  # 本地代理兜底

    payload = {
        "chat_id": chat,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }
    last = None
    for px in attempts:
        try:
            res = post(token, payload, px)
            if res.get("ok"):
                route = "proxy:%s" % px if px else "direct"
                print("OK message_id=%s route=%s" % (res["result"]["message_id"], route))
                return 0
            last = "api:%s" % res
        except Exception as e:  # noqa: BLE001
            last = ("%s " % px if px else "direct ") + repr(e)

    # 官方域名所有出口都失败 → 走海外边缘反代（直连 + 代理各试一次）
    relay = os.environ.get("TELEGRAM_API_BASE") or RELAY_DEFAULT
    relay_attempts = [None, hp] if hp else [None]
    for px in relay_attempts:
        try:
            res = post_relay(relay, token, payload, px)
            if res.get("ok"):
                route = "relay" + (":proxy" if px else ":direct")
                print("OK message_id=%s route=%s" % (res["result"]["message_id"], route))
                return 0
            last = "relay:%s" % res
        except Exception as e:  # noqa: BLE001
            last = "relay " + repr(e)
    print("ERR " + str(last), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

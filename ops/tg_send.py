#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deuce 本地 Telegram 推送（容器 notifier / Deno 反代失效时的统一出口）。

容器直连 api.telegram.org 被墙、Deno 免费反代会 503 USAGE_EXCEEDED；定时任务运行在
deuce 本机，可直连或走本地代理 127.0.0.1:7897。故定时任务/看门狗/告警的 TG 优先在
deuce 本地用本脚本发送；容器侧无人值守作业仍走 Deno 反代（TELEGRAM_API_BASE）。

用法: python3 ops/tg_send.py "正文"  或  echo "正文" | python3 ops/tg_send.py
     python3 ops/tg_send.py -c <chatId> "正文"
凭据读取顺序(KEY=VALUE, token 不得写入本脚本/任何被 git 跟踪文件):
  环境变量 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID
  -> <repo>/cloud/deploy.env -> ~/.config/food-atlas/tg.env -> 脚本同目录 .tg_env
网络顺序: HTTPS_PROXY -> 直连 -> 本地代理 http://127.0.0.1:7897 兜底。
退出码: 0 成功(打印 message_id)；2 缺凭据/正文；1 发送失败。
"""
import os, sys, json, pathlib, urllib.request, urllib.parse

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
OFFICIAL = "https://api.telegram.org"
LOCAL_PROXY = "http://127.0.0.1:7897"
ENV_FILES = [
    REPO / "cloud" / "deploy.env",
    pathlib.Path.home() / ".config" / "food-atlas" / "tg.env",
    SCRIPT_DIR / ".tg_env",
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
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    with opener.open(urllib.request.Request(url, data=data, method="POST"), timeout=20) as r:
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
        print("ERR missing token/chat/text", file=sys.stderr); return 2
    attempts = []
    hp = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if hp:
        attempts.append(hp)
    attempts.append(None)
    if LOCAL_PROXY not in attempts:
        attempts.append(LOCAL_PROXY)
    payload = {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}
    last = None
    for px in attempts:
        try:
            res = post(token, payload, px)
            if res.get("ok"):
                print("OK message_id=%s route=%s" % (res["result"]["message_id"], "proxy" if px else "direct")); return 0
            last = "api:%s" % res
        except Exception as e:  # noqa
            last = ("%s " % px if px else "direct ") + repr(e)
    print("ERR " + str(last), file=sys.stderr); return 1


if __name__ == "__main__":
    sys.exit(main())

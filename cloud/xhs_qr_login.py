#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_qr_login.py — 服务端「隔离会话」生成小红书登录二维码，扫码后导出 cookie（任意账号）。

与正在采集的浏览器完全隔离：每个账号一个独立 headless Chromium + 独立 context，
在后台常驻运行，二维码约每 40s 自动刷新（会过期），出现 web_session+id_token 即成功。

按账号落盘（DATA/qr/）：
  <account>.png            最新二维码
  <account>_status.json    {state: starting/waiting/done/timeout, ts, qr, pid, n}
  <account>_new.json       成功后导出的 cookie（JSON 数组）；由【宿主机安装器】搬进账号目录
  <account>_pid            后台 worker pid

用法：
  python xhs_qr_login.py --start account_a [--proxy http://user:pass@host:port] [--window 900]
  python xhs_qr_login.py --worker account_a [--proxy ...] [--window 900]   # 后台实际执行
"""
import argparse
import glob
import json
import pathlib
import subprocess
import sys
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

DATA = pathlib.Path("/app/data") / "qr"


def paths(account):
    DATA.mkdir(parents=True, exist_ok=True)
    return {
        "qr": DATA / f"{account}.png",
        "status": DATA / f"{account}_status.json",
        "new": DATA / f"{account}_new.json",
        "pid": DATA / f"{account}_pid",
    }


def chromium_path():
    cands = sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
    return cands[-1] if cands else None


def proxy_dict(proxy_url):
    """tinyproxy URL -> Playwright proxy 参数。"""
    if not proxy_url:
        return None
    u = urlparse(proxy_url)
    d = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        d["username"] = u.username
        d["password"] = u.password or ""
    return d


QR_SELECTORS = [
    ".qrcode-img img", "img.qrcode-img", ".qrcode img", "canvas.qrcode",
    ".login-qrcode img", ".qrcode-img", "[class*=qrcode] img", "[class*=qrcode]",
]


def set_status(account, **kw):
    P = paths(account)
    cur = {}
    try:
        cur = json.loads(P["status"].read_text(encoding="utf-8"))
    except Exception:
        pass
    cur.update(kw)
    cur["ts"] = int(time.time())
    P["status"].write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")


def capture_qr(page, account):
    P = paths(account)
    for sel in QR_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                box = el.bounding_box()
                if box and box["width"] > 60:
                    el.screenshot(path=str(P["qr"]))
                    return True
        except Exception:
            continue
    for sel in [".login-container", "[class*=login]"]:
        try:
            el = page.query_selector(sel)
            if el:
                el.screenshot(path=str(P["qr"]))
                return True
        except Exception:
            continue
    page.screenshot(path=str(P["qr"]))
    return True


def has_session(context):
    """登录成功可靠标志：同时具备 web_session 与 id_token（访客只有 web_session）。"""
    names = {c.get("name") for c in context.cookies()}
    return "web_session" in names and "id_token" in names


def worker(account, proxy_url=None, window_sec=900):
    """实际登录流程（在后台进程里跑）。"""
    P = paths(account)
    set_status(account, state="starting", pid=0)
    with sync_playwright() as p:
        launch = {"headless": True, "executable_path": chromium_path(),
                  "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}
        pd = proxy_dict(proxy_url)
        if pd:
            launch["proxy"] = pd
        browser = p.chromium.launch(**launch)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"))
        page = context.new_page()
        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        capture_qr(page, account)
        set_status(account, state="waiting", qr=str(P["qr"]))
        print("QR_READY", P["qr"], flush=True)
        deadline = time.time() + window_sec
        last_cap = time.time()
        while time.time() < deadline:
            if has_session(context):
                cookies = context.cookies()
                P["new"].write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
                set_status(account, state="done", n=len(cookies), out=str(P["new"]))
                print("LOGIN_OK", len(cookies), flush=True)
                browser.close()
                return 0
            if time.time() - last_cap > 40:
                capture_qr(page, account)
                set_status(account, state="waiting", qr=str(P["qr"]))
                last_cap = time.time()
                print("QR_REFRESH", flush=True)
            time.sleep(3)
        set_status(account, state="timeout")
        print("QR_TIMEOUT", flush=True)
        browser.close()
    return 0


def _pid_alive(pid):
    return pathlib.Path(f"/proc/{pid}").exists()


def is_running(account):
    P = paths(account)
    try:
        pid = int(P["pid"].read_text().strip())
    except Exception:
        return False
    return _pid_alive(pid)


def status(account):
    P = paths(account)
    try:
        return json.loads(P["status"].read_text(encoding="utf-8"))
    except Exception:
        return {"state": "none"}


def start(account, proxy_url=None, window_sec=900):
    """后台拉起登录 worker（已在跑则不重复拉起）。返回 True=新启动。"""
    if is_running(account):
        return False
    args = [sys.executable, str(pathlib.Path(__file__).resolve()),
            "--worker", account, "--window", str(window_sec)]
    if proxy_url:
        args += ["--proxy", proxy_url]
    logf = open(DATA / f"{account}_worker.log", "a")
    proc = subprocess.Popen(args, start_new_session=True, stdout=logf, stderr=subprocess.STDOUT)
    paths(account)["pid"].write_text(str(proc.pid))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker")
    ap.add_argument("--start")
    ap.add_argument("--proxy", default="")
    ap.add_argument("--window", type=int, default=900)
    a = ap.parse_args()
    if a.worker:
        return worker(a.worker, a.proxy or None, a.window)
    if a.start:
        started = start(a.start, a.proxy or None, a.window)
        print("started" if started else "already running")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

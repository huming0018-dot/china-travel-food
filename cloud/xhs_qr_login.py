#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_qr_login.py — 服务端隔离会话生成小红书登录二维码，扫码后导出 cookie。

与本地浏览器(已登录 account_a)完全隔离：独立 headless Chromium + 独立 context。
流程：
  1. 打开 https://www.xiaohongshu.com，未登录会弹登录框（二维码）。
  2. 截取二维码存 QR_PNG，写状态；约每 40s 刷新一次（二维码会过期）。
  3. 轮询 cookies，出现 web_session 即登录成功，导出 JSON 数组到 OUT_JSON。
cookie 文件随后由宿主机移动到账号目录（容器内 /secrets 为 ro 挂载）。
"""
import json
import glob
import pathlib
import time

from playwright.sync_api import sync_playwright

DATA = pathlib.Path("/app/data")
QR_PNG = DATA / "qr_b.png"
STATUS = DATA / "qr_b_status.json"
OUT_JSON = DATA / "account_b_new.json"


def chromium_path():
    cands = sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
    return cands[-1] if cands else None

QR_SELECTORS = [
    ".qrcode-img img", "img.qrcode-img", ".qrcode img", "canvas.qrcode",
    ".login-qrcode img", ".qrcode-img", "[class*=qrcode] img", "[class*=qrcode]",
]


def set_status(**kw):
    STATUS.write_text(json.dumps(kw, ensure_ascii=False), encoding="utf-8")


def capture_qr(page):
    for sel in QR_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el:
                box = el.bounding_box()
                if box and box["width"] > 60:
                    el.screenshot(path=str(QR_PNG))
                    return True
        except Exception:
            continue
    # 兜底：截登录框
    for sel in [".login-container", "[class*=login]"]:
        try:
            el = page.query_selector(sel)
            if el:
                el.screenshot(path=str(QR_PNG))
                return True
        except Exception:
            continue
    page.screenshot(path=str(QR_PNG))
    return True


def has_session(context):
    """登录成功的可靠标志：同时具备 web_session 与 id_token（访客只有 web_session）。"""
    names = {c.get("name") for c in context.cookies()}
    return "web_session" in names and "id_token" in names


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    set_status(state="starting", ts=int(time.time()))
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, executable_path=chromium_path(),
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"))
        page = context.new_page()
        page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        capture_qr(page)
        set_status(state="waiting", ts=int(time.time()), qr=str(QR_PNG))
        print("QR_READY", QR_PNG)
        deadline = time.time() + 300
        last_cap = time.time()
        while time.time() < deadline:
            if has_session(context):
                cookies = context.cookies()
                OUT_JSON.write_text(json.dumps(cookies, ensure_ascii=False),
                                    encoding="utf-8")
                set_status(state="done", ts=int(time.time()),
                          n=len(cookies), out=str(OUT_JSON))
                print("LOGIN_OK", len(cookies))
                browser.close()
                return
            if time.time() - last_cap > 40:
                capture_qr(page)
                set_status(state="waiting", ts=int(time.time()), qr=str(QR_PNG))
                last_cap = time.time()
                print("QR_READY", QR_PNG)
            time.sleep(3)
        set_status(state="timeout", ts=int(time.time()))
        print("QR_TIMEOUT")
        browser.close()


if __name__ == "__main__":
    main()

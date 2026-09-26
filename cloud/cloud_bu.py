#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_bu.py — 用 Playwright(无头 Chromium) 实现 xhs_collect 依赖的浏览器接口（bu）。

xhs_collect 只用到 5 个动作：navigate / wait_for_load / wait / js / click_xy。
本类逐个对齐，使整套为豆包内置浏览器写的采集脚本，能在任何云服务器/容器里原样运行。

关键（教训 #54）：click_xy 用 page.mouse（真实 CDP 鼠标事件）点击，
让小红书详情页 URL 带 xsec_token；绝不用 element.click() 直接导航（会被风控 300031）。
"""
import os
import glob
import json
import pathlib


def chromium_executable():
    """只装了完整 Chromium（npmmirror 无 headless_shell）时，显式定位完整 chrome。
    可用环境变量 CHROMIUM_EXECUTABLE_PATH 覆盖。"""
    p = os.environ.get("CHROMIUM_EXECUTABLE_PATH", "")
    if p and pathlib.Path(p).exists():
        return p
    cands = sorted(glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
    if not cands:  # 本机 / 其他目录布局兜底
        cands = sorted(glob.glob(os.path.expanduser(
            "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")))
    return cands[-1] if cands else None


class CloudBrowser:
    def __init__(self, headless=True, width=1280, height=900,
                 cookies=None, locale="zh-CN", timezone="Asia/Shanghai",
                 user_agent=None):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = dict(headless=headless,
                  args=["--no-sandbox", "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage"])
        exe = chromium_executable()
        if exe:
            kw["executable_path"] = exe
        self.browser = self._pw.chromium.launch(**kw)
        ctx_kw = {"viewport": {"width": width, "height": height},
                  "locale": locale, "timezone_id": timezone}
        if user_agent:
            ctx_kw["user_agent"] = user_agent
        self.context = self.browser.new_context(**ctx_kw)
        # 降低自动化特征
        self.context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
        if cookies:
            self.add_cookies(cookies)
        self.page = self.context.new_page()

    # ---- cookie 注入 ----
    def add_cookies(self, cookies):
        if isinstance(cookies, str):
            cookies = parse_cookie_header(cookies)
        if cookies:
            self.context.add_cookies(cookies)

    # ---- 与 seed_browser_use 对齐的 5 个动作 ----
    def navigate(self, url):
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            # 小红书搜索页常因长连接不触发完成；DOM 就绪即可，超时不报错
            pass

    def wait_for_load(self, timeout=15):
        try:
            self.page.wait_for_load_state("networkidle", timeout=int(timeout) * 1000)
        except Exception:
            pass

    def wait(self, seconds):
        self.page.wait_for_timeout(int(float(seconds) * 1000))

    def js(self, script):
        sc = script.strip()
        # 采集脚本多为"语句序列 + 末尾 return"，统一包成函数体；纯语句也合法（返回 None）
        if not sc.startswith("(") and not sc.startswith("function"):
            sc = "() => {\n" + sc + "\n}"
        return self.page.evaluate(sc)

    def click_xy(self, x, y):
        vp = self.page.viewport_size or {"width": 1280, "height": 900}
        px = float(x) / 1000.0 * vp["width"]
        py = float(y) / 1000.0 * vp["height"]
        # 先移动再按下抬起，模拟真实鼠标轨迹
        self.page.mouse.move(px, py)
        self.page.mouse.click(px, py)

    def snapshot_text(self):
        try:
            return self.page.inner_text("body")
        except Exception:
            return ""

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


def parse_cookie_header(header, domain=".xiaohongshu.com", path="/"):
    """把请求头里复制出的 Cookie 字符串（"a=b; c=d"）转成 Playwright cookie 列表。"""
    out = []
    for part in str(header).split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k = k.strip()
        if k:
            out.append({"name": k, "value": v.strip(),
                        "domain": domain, "path": path})
    return out


def load_cookies_from_env():
    """从环境变量 XHS_COOKIE 读取 cookie：可为请求头字符串，或 JSON 数组/文件路径。"""
    import os
    raw = os.environ.get("XHS_COOKIE", "").strip()
    if not raw:
        p = os.environ.get("XHS_COOKIE_FILE", "")
        if p and pathlib.Path(p).exists():
            raw = pathlib.Path(p).read_text(encoding="utf-8").strip()
    if not raw:
        return None
    if raw.startswith("[") or raw.startswith("{"):
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    return parse_cookie_header(raw)

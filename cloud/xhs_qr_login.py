#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_qr_login.py — 服务端「隔离会话」生成小红书登录二维码，扫码后导出 cookie（任意账号）。

与正在采集的浏览器完全隔离：每个账号一个独立 headless Chromium + 独立 context，
在后台常驻运行，二维码约每 40s 自动刷新（会过期），出现 web_session+id_token 即成功。

按账号落盘（DATA/qr/）：
  <account>.png            最新二维码（精确截 img.qrcode-img，绝不截登录容器/遮罩）
  <account>_status.json    {state: starting/waiting/done/timeout, ts, qr, pid, n}
  <account>_new.json       成功后导出的 cookie（JSON 数组）；由【宿主机安装器】搬进账号目录
  <account>_pid            后台 worker pid

关键修正（教训：曾把登录页遮罩文字“扫码登录/请在手机确认/重新”当成二维码推送）：
  - 只认 img.qrcode-img，且必须 src=data:image、盒子≥110px（已放大到全尺寸128）才截图；
  - 截图前若提示“二维码已失效/点击刷新”，先点 .qrcode 重新生成再等新码；
  - 截不到就继续等，绝不回退截 .login-container / 整页。

用法：
  python xhs_qr_login.py --start account_a [--proxy http://user:pass@host:port] [--window 900]
  python xhs_qr_login.py --worker account_a [--proxy ...] [--window 900]
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

QR_IMG = ["img.qrcode-img", ".qrcode img.qrcode-img", ".qrcode img"]


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


def _refresh_if_expired(page):
    """仅当二维码区域【可见文字】明确提示已失效时才点击刷新。
    innerText 只含可见文本（display:none 的 lottie 不计）；用强短语，避免把正常态误判。
    返回 True=本次点击了刷新。"""
    try:
        expired = page.evaluate(
            """()=>{const c=document.querySelector('.code-area'); if(!c) return false;
               const t=c.innerText||'';
               return /二维码已失效|二维码失效|点击刷新|QR code expired|已过期，请刷新|二维码过期/.test(t)}""")
        if expired:
            for sel in (".qrcode", ".code-area"):
                try:
                    page.click(sel, timeout=1500)
                    return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


def looks_like_qr(raw):
    """校验解码图确实是二维码，而非登录页双语占位图（占位图非正方形128x129、含红色按钮与灰色文字）。
    判据：正方形且≥100px；采样像素几乎无彩色、中间灰占比低（二维码为纯黑白+少量抗锯齿）。"""
    import io
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return False
    w, h = im.size
    if w != h or w < 100:
        return False
    px = im.load()
    step = max(1, w // 64)
    n = colored = mid = 0
    for x in range(0, w, step):
        for y in range(0, h, step):
            r, g, b = px[x, y]
            n += 1
            if max(r, g, b) - min(r, g, b) > 25:
                colored += 1
            elif 90 < max(r, g, b) < 160:
                mid += 1
    return colored / n < 0.01 and mid / n < 0.20


def capture_qr(page, account, timeout=25):
    """直接解码 img.qrcode-img 的 data:image base64 写出原始二维码像素。
    不截图——截图会把绝对定位的遮罩（扫码登录/请在手机确认/重新）一起截进去。
    只在当前 src 不是有效二维码时，才按 8s 节流尝试点“刷新”。
    成功 True；否则 False（不覆盖旧码）。"""
    import base64
    P = paths(account)
    end = time.time() + timeout
    last_click = 0
    while time.time() < end:
        try:
            src = page.evaluate(
                "()=>{const e=document.querySelector('img.qrcode-img');return e?e.src:''}")
            if src and src.startswith("data:image"):
                raw = base64.b64decode(src.split(",", 1)[1])
                if raw[:8] == b"\x89PNG\r\n\x1a\n" and looks_like_qr(raw):
                    P["qr"].write_bytes(raw)
                    return True
            # 当前不是有效二维码：若明确提示失效则点刷新（8s 节流）
            if time.time() - last_click > 8 and _refresh_if_expired(page):
                last_click = time.time()
        except Exception:
            pass
        time.sleep(1)
    return False


def has_session(context):
    """登录成功可靠标志：同时具备 web_session 与 id_token（访客只有 web_session）。"""
    names = {c.get("name") for c in context.cookies()}
    return "web_session" in names and "id_token" in names


def _goto_login(page):
    """打开登录页（首页会重定向到 /login）；失败容错。"""
    for url in ("https://www.xiaohongshu.com/login", "https://www.xiaohongshu.com"):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            return True
        except Exception:
            continue
    return False


def ensure_qr(page, account, reloads=3):
    """确保拿到有效二维码：先在当前页抓；连续失败则【重新打开登录页】再抓（自愈限流/错误页）。"""
    if capture_qr(page, account, timeout=10):
        return True
    for k in range(reloads):
        print(f"QR_RELOAD {k+1}/{reloads}", flush=True)
        _goto_login(page)
        time.sleep(2)
        if capture_qr(page, account, timeout=15):
            return True
    return False


def worker(account, proxy_url=None, window_sec=900):
    """实际登录流程（在后台进程里跑）。带自愈重载与定时刷新。"""
    P = paths(account)
    set_status(account, state="starting", pid=0)
    P["qr"].unlink(missing_ok=True)  # 清掉上一轮残留，避免把旧占位图当新码推送
    with sync_playwright() as p:
        launch = {"headless": True, "executable_path": chromium_path(),
                  "args": ["--no-sandbox", "--disable-blink-features=AutomationControlled"]}
        pd = proxy_dict(proxy_url)
        if pd:
            launch["proxy"] = pd
        browser = p.chromium.launch(**launch)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 900}, locale="zh-CN")
        page = context.new_page()
        _goto_login(page)
        time.sleep(2)
        ok = ensure_qr(page, account)
        if ok:
            set_status(account, state="waiting", qr=str(P["qr"]))
            print("QR_READY", P["qr"], flush=True)
        else:
            set_status(account, state="starting")
            print("QR_NOT_READY", flush=True)
        deadline = time.time() + window_sec
        last_good = time.time()
        QR_FRESH_SEC = 100   # 二维码有效期：到点重新打开登录页换新（像素无法判断过期）
        while time.time() < deadline:
            if has_session(context):
                cookies = context.cookies()
                P["new"].write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
                set_status(account, state="done", n=len(cookies), out=str(P["new"]))
                print("LOGIN_OK", len(cookies), flush=True)
                browser.close()
                return 0
            # 二维码缺失/无效立即修；到保鲜点强制换新
            need = (not P["qr"].exists()) or (time.time() - last_good > QR_FRESH_SEC)
            if need:
                if time.time() - last_good > QR_FRESH_SEC:
                    _goto_login(page); time.sleep(2)
                if ensure_qr(page, account, reloads=2):
                    set_status(account, state="waiting", qr=str(P["qr"]))
                    last_good = time.time()
                    print("QR_REFRESH", flush=True)
            time.sleep(3)
        set_status(account, state="timeout")
        print("QR_TIMEOUT", flush=True)
        browser.close()
    return 0


def _cmdline(pid):
    try:
        return open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "ignore").split("\x00")
    except Exception:
        return []


def _is_worker_toks(toks, account):
    return any("xhs_qr_login" in t for t in toks) and "--worker" in toks and account in toks


def _worker_pid(account):
    """找到本账号真正在跑的 worker pid；pid 文件失效则全量扫描 /proc 兜底。返回 pid 或 None。"""
    P = paths(account)
    try:
        pid = int(P["pid"].read_text().strip())
        if _is_worker_toks(_cmdline(pid), account):
            return pid
    except Exception:
        pass
    # pid 文件陈旧/被复用：全量扫描找真 worker（防止孤儿 worker 重复拉起）
    for d in glob.glob("/proc/[0-9]*"):
        try:
            p = int(d.split("/")[-1])
        except Exception:
            continue
        if _is_worker_toks(_cmdline(p), account):
            P["pid"].write_text(str(p))
            return p
    return None


def is_running(account):
    return _worker_pid(account) is not None


def status(account):
    P = paths(account)
    try:
        return json.loads(P["status"].read_text(encoding="utf-8"))
    except Exception:
        return {"state": "none"}


def stop(account):
    import os
    pid = _worker_pid(account)
    if not pid:
        try:
            paths(account)["pid"].unlink()
        except Exception:
            pass
        return False
    try:
        os.kill(pid, 9)
    except Exception:
        return False
    try:
        paths(account)["pid"].unlink()
    except Exception:
        pass
    return True


def start(account, proxy_url=None, window_sec=900):
    """后台拉起登录 worker（已在跑则不重复拉起；陈旧 pid 文件自动覆盖）。返回 True=新启动。"""
    if _worker_pid(account):
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
    ap.add_argument("--stop")
    ap.add_argument("--proxy", default="")
    ap.add_argument("--window", type=int, default=900)
    a = ap.parse_args()
    if a.worker:
        return worker(a.worker, a.proxy or None, a.window)
    if a.start:
        started = start(a.start, a.proxy or None, a.window)
        print("started" if started else "already running")
        return 0
    if a.stop:
        print("stopped" if stop(a.stop) else "not running")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())

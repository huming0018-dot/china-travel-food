#!/usr/bin/env python
"""
大众点评采集器（Playwright 持久化方案）

背景
----
1. wongben/dianping-crawler 依赖的 mapi.dianping.com/searchshop.json 已返回 403
   （2017 年项目，完全失效），不再使用。
2. curl 直连 www.dianping.com 各页面均 302 跳转风控。
3. Playwright headless 访问搜索页命中「验证中心」；headful 同样被拦。
   → 结论：点评必须走 **持久化登录态 + 人工过一次验证**，之后长期复用。

设计
----
用 `launch_persistent_context` 建独立用户目录（与日常 Chrome 隔离），
首次运行弹出窗口让人工登录/验证，登录态落盘后后续运行免登录。

用法
----
    # 首次：需要人工在弹出的窗口里登录并通过验证
    python dianping_fetch.py --keyword 当霁 --login
    # 之后：复用登录态
    python dianping_fetch.py --keyword 当霁 --out result.json
"""
import argparse
import asyncio
import json
from datetime import date
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
PROFILE = Path(__file__).resolve().parent.parent / "browser_data" / "dianping_user_data_dir"


def detect_block(title: str, body: str, url: str = "") -> bool:
    """识别风控/未登录/错误页。注意移动端搜索未登录会静默跳到 /error/error_page，
    标题仍是「大众点评网」，必须靠 URL 判断，否则会误判为成功。"""
    markers = ["验证中心", "安全验证", "robot", "异常流量", "访问受限", "请稍后",
               "登录后查看", "请先登录"]
    if any(m in (title + body) for m in markers):
        return True
    low = url.lower()
    if "/error/" in low or "login" in low and "passport" in low:
        return True
    return False


async def collect(page, keyword: str, mobile: bool) -> dict:
    if mobile:
        url = f"https://m.dianping.com/shanghai/search/keyword?keyword={quote(keyword)}"
    else:
        url = f"https://www.dianping.com/search/keyword/1/0_{quote(keyword)}"
    print(f"[1] 打开: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        return {"status": "goto_error", "error": repr(e)[:200]}
    await page.wait_for_timeout(4500)

    title = await page.title()
    body = await page.content()
    cur = page.url
    if detect_block(title, body, cur):
        return {"status": "blocked", "title": title, "url": url, "final_url": cur,
                "reason": "风控验证 / 未登录 / 错误页"}
    print(f"[2] 标题: {title} | 最终URL: {cur}")
    sels = ["li.shop-item", "div.shop-item", "li[class*=shop]", "div[class*=shopItem]"]
    items = []
    for s in sels:
        items = await page.query_selector_all(s)
        if items:
            print(f"[3] 选择器 {s} 命中 {len(items)}")
            break
    out = []
    for el in items[:20]:
        async def t(sel):
            n = await el.query_selector(sel)
            return (await n.inner_text()).strip() if n else None
        name = await t(".shop-name") or await t("[class*=shopName]") or await t("a")
        if not name:
            continue
        out.append({
            "name": name.strip()[:60],
            "rating": await t(".score") or await t("[class*=score]"),
            "review_count": await t(".review-num") or await t("[class*=comment]"),
            "avg_price": await t("[class*=price]") or await t(".avg-price"),
        })
    return {"status": "ok", "title": title, "url": url, "count": len(out), "shops": out}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--login", action="store_true",
                    help="登录模式：等待人工在窗口中登录并通过验证")
    ap.add_argument("--wait", type=int, default=180)
    ap.add_argument("--mobile", action="store_true", help="使用移动端站点")
    a = ap.parse_args()

    PROFILE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=False,
            user_agent=UA, viewport={"width": 1440, "height": 900},
            locale="zh-CN", args=["--disable-blink-features=AutomationControlled"],
        )
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        if a.login:
            print(f"[!] 登录模式：请在弹出的浏览器窗口中登录大众点评并通过验证，"
                  f"最多等待 {a.wait} 秒。完成后程序自动继续。")
            await page.goto("https://www.dianping.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(a.wait * 1000)
            print("[*] 等待结束，开始采集")
            data = await collect(page, a.keyword, a.mobile)
        else:
            data = await collect(page, a.keyword, a.mobile)

        data["fetched_at"] = date.today().isoformat()
        data["source"] = ("dianping.com Playwright 持久化浏览器"
                          + ("（移动端）" if a.mobile else "（网页端）"))
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if a.out:
            Path(a.out).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            print(f"[saved] {a.out}")
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
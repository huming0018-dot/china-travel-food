#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""大众点评采集器（Playwright 直采方案，已实测跑通 2026-10-17）

踩坑记录（务必先读）
  1. wongben/dianping-crawler 依赖的 mapi.dianping.com/searchshop.json
     已返回 403，2017 年项目彻底失效，不要再用。
  2. curl 直连 www.dianping.com 各页面均 302 跳风控。
  3. Playwright 无头会被识别并拿到 no-result 模板；必须 headless=False + 持久化登录态。
  4. 搜索结果容器是 a[href*='/shop/'] 所在卡片，不是 div.shop-wrap（历史类名）。
  5. .no-result 元素（"商户没有被收录？添加商户"）永远存在于 DOM，
     不能用它判断无结果——会误判。应检查是否搜到 shop 链接。
  6. 详情页首屏信息不在 innerText 前段，需截图或正则兜底。

用法: python dianping_fetch.py --keyword 当霁 --detail --out dp.json
"""
import argparse
import asyncio
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
PROFILE = Path(__file__).resolve().parent / "dianping_profile"
SHOP_HREF = re.compile(r"/shop/([A-Za-z0-9]+)")


def parse_detail(text, html):
    flat = re.sub(r"<[^>]+>", " ", html)

    def g(*pats):
        for p in pats:
            m = re.search(p, text) or re.search(p, flat)
            if m:
                return (m.group(1) if m.groups() else m.group(0)).strip()
        return None

    m3 = re.search(r"口味[:：]?\s*([\d.]+)\s*环境[:：]?\s*([\d.]+)\s*服务[:：]?\s*([\d.]+)", flat)
    return {
        "score": g(r"([0-5]\.\d)\s*分数"),
        "review_count": g(r"(\d+)\s*条评价"),
        "avg_price": g(r"¥\s*(\d+)\s*/人", r"人均\s*[¥￥]\s*(\d+)"),
        "taste_env_service": ("口味%s/环境%s/服务%s" % m3.groups() if m3 else None),
        "honor": g(r"(虹口区[^\n]{0,20}榜[^\n]{0,10})", r"([^\n<>]{0,18}榜\s*·?\s*第1名)"),
        "open_time": g(r"营业时间[:：]?\s*([\d:]+[-–][^\n<]{2,30})"),
        "address": g(r"(北外滩街道[,，][^\n<]{2,40})", r"([^\n<>]{4,40}号[^\n<>]{0,20}楼)"),
        "metro": g(r"(地铁[^\n<]{2,40}步行[0-9]+m)"),
    }


async def search(page, kw):
    url = "https://www.dianping.com/search/keyword/1/0_%s" % quote(kw)
    print("[1] 搜索: %s" % kw)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(9000)
    for _ in range(2):
        await page.mouse.wheel(0, 300)
        await page.wait_for_timeout(1000)
    links = await page.query_selector_all("a[href*='/shop/']")
    print("[2] 搜到 %d 个商户" % len(links))
    out = []
    for a in links[:10]:
        name = (await a.inner_text()).strip()
        href = await a.get_attribute("href")
        h = await a.evaluate_handle("e=>e.closest('li')")
        li = await h.as_element()
        card = (await li.inner_text()).replace("\n", " ").strip() if li else ""
        m = SHOP_HREF.search(href or "")
        out.append({"name": name, "shop_id": m.group(1) if m else None,
                    "url": href, "card_text": card[:160]})
        print("    -> %s | %s" % (name, card[:80]))
    return out


async def detail(page, url):
    print("[3] 详情页: %s" % url)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(11000)
    text = await page.evaluate("document.body.innerText")
    html = await page.content()
    d = parse_detail(text, html)
    m = SHOP_HREF.search(url)
    d["shop_id"] = m.group(1) if m else None
    d["url"] = url
    d["page_text"] = text[:600]
    d["recommended_dishes"] = [{"name": n.strip(), "votes": int(v)}
                               for v, n in re.findall(r"(\d+)人推荐\s*([^\n]{1,20})", text)]
    d["group_buy"] = [{"set": a, "price_yuan": int(b)}
                      for a, b in re.findall(r"(【[^】]+】[^\n]{0,30})[^\n]*?¥(\d+)", text)]
    await page.screenshot(path="/tmp/dp_detail.png")
    return d


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--shot", default="")
    a = ap.parse_args()

    PROFILE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, user_agent=UA,
            viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        shops = await search(page, a.keyword)
        if a.shot:
            await page.screenshot(path=a.shot)
        out = {"keyword": a.keyword, "fetched_at": date.today().isoformat(),
               "source": "dianping.com Playwright 直采（headful + 持久化登录态）",
               "shops": shops}
        if a.detail and shops:
            out["detail"] = await detail(page, shops[0]["url"])
        print(json.dumps(out, ensure_ascii=False, indent=2))
        if a.out:
            Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            print("[saved] %s" % a.out)
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""大众点评采集器（Playwright 直采）

前置条件
--------
- 需要 playwright（可复用 media-crawler 的 venv）
- 需一次人工登录，登录态落盘到<skill>/browser_data/dianping_user_data_dir/
- 必须 headless=False：无头会被识别并返回 no-result 模板
- 必须等待 9-11 秒：结果为懒加载

城市 ID
-------
  1=上海 2=北京 3=广州 10=杭州 16=深圳
换城市只需 --city 传数字；未收录城市返回 0 个商户属正常。

踩坑记录
--------
1. wongben/dianping-crawler 的 mapi.dianping.com/searchshop.json 已 403，该
   2017 年项目彻底失效，不要再用。
2. curl 直连 www.dianping.com 均 302 跳风控。
3. .no-result（"商户没有被收录？添加商户"）是常驻模板，永远存在于 DOM，
   不能用它判断无结果——会误判。正确判据：是否搜到 a[href*='/shop/']。
4. div.shop-wrap 是已下线的历史类名，真实结果在 a[href*='/shop/'] 所在卡片。
5. JSHandle.as_element() 是同步方法，返回 ElementHandle|None，不能加 await
   （加了会抛 "object ElementHandle can't be used in 'await' expression"）。
6. m.dianping.com 移动端未登录静默跳 /error/error_page，标题仍是"大众点评网"，
   必须检测最终 URL。
7. 详情页首屏信息不在 innerText 前段，需截图或正则兜底。

用法
----
    python dianping_fetch.py --keyword 当霁 --city 1 --detail --out dp.json
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

# 与 preflight.sh / media-crawler 同一约定：<skill>/browser_data/<平台>_user_data_dir
PROFILE = Path(__file__).resolve().parent.parent / "browser_data" / "dianping_user_data_dir"

SHOP_HREF = re.compile(r"/shop/([A-Za-z0-9]+)")
CITY_ID = {"上海": 1, "北京": 2, "广州": 3, "杭州": 10, "深圳": 16}


def parse_detail(text: str, html: str) -> dict:
    """多级正则兜底，取不到就 None，绝不编造。已解除城市/行政区硬编码。"""
    flat = re.sub(r"<[^>]+>", " ", html)

    def g(*pats):
        for p in pats:
            m = re.search(p, text) or re.search(p, flat)
            if m:
                return (m.group(1) if m.groups() else m.group(0)).strip()
        return None

    m3 = (re.search(r"口味[:：]?\s*([\d.]+)\s*环境[:：]?\s*([\d.]+)\s*服务[:：]?\s*([\d.]+)", text)
          or re.search(r"口味[:：]?\s*([\d.]+)\s*环境[:：]?\s*([\d.]+)\s*服务[:：]?\s*([\d.]+)", flat))
    return {
        # 评分只认显式"X.X 分数"标记。
        # 曾尝试用"临近评价数的浮点数"兜底，但会误抓 环境/服务 分项分数，
        # 按 field-spec"拿不到填 null，禁止估算"原则，宁缺毋滥。
        "score": g(r"([0-5]\.\d)\s*分数"),
        "review_count": g(r"(\d+)\s*条评价"),
        "avg_price": g(r"¥\s*(\d+)\s*/人", r"人均\s*[¥￥]\s*(\d+)"),
        "taste_env_service": ("口味%s/环境%s/服务%s" % m3.groups() if m3 else None),
        "honor": g(r"([\u4e00-\u9fa5]{2,8}(?:区|县)[\u4e00-\u9fa5A-Za-z0-9]{0,12}榜[^\n<>]{0,10})"),
        "open_time": g(r"营业时间[:：]?\s*([\d:]+[-–][^\n<]{2,30})"),
        # 非贪婪 + 不跨空白/标点，避免吞入相邻字段；号/弄 两种门牌都要覆盖
        "address": g(r"([^\s\n<>，,]{0,18}?(?:路|街|道|大道)\s*\d+\s*[号弄][^\s\n<>，,]{0,20})"),
        "metro": g(r"(地铁[^\n<]{2,40}步行[0-9]+m)"),
    }


async def search(page, kw, city_id):
    url = "https://www.dianping.com/search/keyword/%d/0_%s" % (city_id, quote(kw))
    print("[1] 搜索: %s (cityid=%d)" % (kw, city_id))
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
        # as_element() 是同步方法，不能 await
        li = await a.evaluate_handle("e=>e.closest('li')")
        li = li.as_element()
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
    ap.add_argument("--city", default="上海", help="城市名或数字ID")
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--shot", default="")
    a = ap.parse_args()

    city_id = CITY_ID.get(a.city)
    if city_id is None:
        try:
            city_id = int(a.city)
        except ValueError:
            ap.error("未知城市：%s（内置：%s，或直接传数字ID）"
                     % (a.city, "/".join(CITY_ID)))

    PROFILE.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, user_agent=UA,
            viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        shops = await search(page, a.keyword, city_id)
        if a.shot:
            await page.screenshot(path=a.shot)
        out = {"keyword": a.keyword, "city_id": city_id, "fetched_at": date.today().isoformat(),
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
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
michelin_collect.py — browser-use 驱动的米其林上海全量采集器（确定性、可复跑）。

为什么用浏览器：米其林官网有反爬，纯 requests 返回 HTTP 202 空体；
正确可访问前缀 /sg/zh_CN/（/cn/zh/ 已 404、/en 无上海数据）。
机制要点：只取主列表容器 .js-restaurant__list_items 内卡片（每页48），
排除 .js-restaurants__empty_items 的跨页重复推荐卡。

用法：python3 michelin_collect.py
产出：research/authority/michelin_shanghai_153.json（随后跑 authority_compare.py 比对）
"""
import json
import pathlib
import time

import seed_browser_use as bu

BASE = "https://guide.michelin.com/sg/zh_CN/shanghai-municipality/shanghai/restaurants"
OUT = pathlib.Path(
    "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"
) / "research" / "authority" / "michelin_shanghai_153.json"

EXTRACT = """(()=>{
 const root=document.querySelector('.js-restaurant__list_items');
 const cards=root?[...root.querySelectorAll('.card__menu')]:[];
 return cards.map(c=>{
  const title=c.querySelector('.card__menu-content--title');
  const link=c.querySelector('a[href*="/restaurant/"]');
  const imgs=[...c.querySelectorAll('img')].map(i=>((i.alt||'')+'|'+(i.src.split('/').pop()||''))).filter(x=>x!='|');
  return {name:title?title.innerText.trim():'',
          slug:link?(link.href.match(/\\/restaurant\\/([^?#]+)/)||[])[1]:'',
          all:c.innerText.replace(/\\n+/g,' | ').replace(/\\s+/g,' ').trim(),imgs};
 });
})()"""


def get_page(p: int):
    url = BASE if p == 1 else BASE + "/page/" + str(p)
    rows = []
    for attempt in range(3):
        try:
            bu.navigate(url)
            try:
                bu.wait_for_load(timeout=18)
            except Exception:
                pass
            for _ in range(8):  # 轮询等卡片渲染
                rows = bu.js(EXTRACT)
                if isinstance(rows, str):
                    rows = json.loads(rows)
                if len(rows) >= 40:
                    return rows
                time.sleep(1.5)
            return rows
        except Exception as e:
            print("retry page", p, "attempt", attempt, e)
            time.sleep(3)
    return rows


def main():
    allc, p = {}, 1
    while True:
        rows = get_page(p)
        before = len(allc)
        for r in rows:
            allc[r["slug"]] = r
        print("page", p, "got", len(rows), "new", len(allc) - before, "total", len(allc))
        if len(rows) < 48:  # 最后一页
            break
        if p >= 8:
            break
        p += 1
    OUT.write_text(json.dumps(list(allc.values()), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print("TOTAL", len(allc), "saved", OUT)


if __name__ == "__main__":
    main()

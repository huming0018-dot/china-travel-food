#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_michelin_collect.py — 容器内可跑的米其林上海全量采集器。

与本机 michelin_collect.py 同逻辑，但用 cloud_bu.CloudBrowser（无头 Chromium）
而非 Mac 端 seed_browser_use，因此能被 cloud_router 在「小红书账号全冷却」时顶上跑。
不依赖小红书登录态，纯抓米其林列表 .js-restaurant__list_items。

产出：/app/data/michelin_shanghai.json（权威榜单层，只负责"不漏"，收录仍需口味证据）。
"""
import json
import pathlib
import time

from cloud_bu import CloudBrowser

BASE = "https://guide.michelin.com/sg/zh_CN/shanghai-municipality/shanghai/restaurants"
OUT = pathlib.Path("/app/data/michelin_shanghai.json")

EXTRACT = """(()=>{
 const root=document.querySelector('.js-restaurant__list_items');
 const cards=root?[...root.querySelectorAll('.card__menu')]:[];
 return cards.map(c=>{
  const title=c.querySelector('.card__menu-content--title');
  const link=c.querySelector('a[href*="/restaurant/"]');
  return {name:title?title.innerText.trim():'',
          slug:link?(link.href.match(/\\/restaurant\\/([^?#]+)/)||[])[1]:'',
          all:c.innerText.replace(/\\n+/g,' | ').replace(/\\s+/g,' ').trim()};
 });
})()"""


def get_page(bu, p):
    url = BASE if p == 1 else BASE + "/page/" + str(p)
    rows = []
    for attempt in range(3):
        try:
            bu.navigate(url)
            bu.wait_for_load(timeout=18)
            for _ in range(8):
                rows = bu.js(EXTRACT)
                if isinstance(rows, str):
                    rows = json.loads(rows)
                if len(rows) >= 40:
                    return rows
                bu.wait(1.5)
            return rows
        except Exception as e:
            print("retry page", p, "attempt", attempt, e, flush=True)
            time.sleep(3)
    return rows


def main():
    bu = CloudBrowser(headless=True)
    try:
        allc, p = {}, 1
        while True:
            rows = get_page(bu, p)
            before = len(allc)
            for r in rows:
                if r.get("slug"):
                    allc[r["slug"]] = r
            print("page", p, "got", len(rows), "new", len(allc) - before,
                  "total", len(allc), flush=True)
            if len(rows) < 48:
                break
            if p >= 8:
                break
            p += 1
        OUT.write_text(json.dumps(list(allc.values()), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print("TOTAL", len(allc), "saved", OUT, flush=True)
    finally:
        bu.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_api.py — 小红书「签名直连 HTTP」后端（纯 Python，不依赖浏览器、不受浏览器搜索风控 300011 影响）。

关键事实（2026-09 实测）：
  - 关键词搜索必须带登录态（匿名 a1 返回 -101）；
  - 但浏览器里被标记 restricted(300011) 的账号，走本签名 HTTP API 仍 code=0 正常返回；
  - 签名用 xhshow（x-s / x-t / x-s-common / x-b3-traceid），cookie 池轮换 + 限速。

对外提供与浏览器采集相同形状的结果，供 DiscoveryEngine 经 monkeypatch 替换 D._gather_one_query：
  gather_query(keyword, npq) -> [{title, desc, url, author, date, comments:[{name,text}]}]
"""
import json
import pathlib
import random
import time

import requests

from xhshow import Xhshow

EDITH = "https://edith.xiaohongshu.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.xiaohongshu.com",
    "Referer": "https://www.xiaohongshu.com/",
}
# 需要换号/冷却的返回码
ROTATE_CODES = {-100, -101, 300011, 300012, 1203, 406}
# 搜索端点安全节奏（2026-09-28 实测）：≤2 次/分钟（间隔≥28s）可持续返回；
# 更快的连续爆发会触发「code=0 但 data 空」的数分钟软限流冷却，停顿后自恢复。
SEARCH_MIN_GAP = 28.0


class AllAccountsBlocked(RuntimeError):
    pass


class XhsApi:
    def __init__(self, accounts_dir="/secrets/xhs_accounts", min_gap=2.2,
                 city="上海", timeout=20, pin=None, proxies=None):
        self.sign = Xhshow()
        self.min_gap = min_gap
        self.city = city
        self.timeout = timeout
        self.pin = pin
        self.proxies = proxies  # {"http": url, "https": url}；每账号独立出口
        self.empty_streak = 0
        self._last = 0.0
        self._search_last = 0.0  # 搜索端点专用节流（比全局 _gap 更慢）
        self.accounts = []
        d = pathlib.Path(accounts_dir)
        if d.exists():
            for f in sorted(d.glob("*.json")):
                try:
                    ck = {c["name"]: c["value"] for c in json.loads(f.read_text())}
                except Exception:
                    continue
                if ck.get("web_session"):
                    self.accounts.append({"name": f.stem, "ck": ck, "bad": 0})
        self.idx = 0
        if pin:
            for i, a in enumerate(self.accounts):
                if a["name"] == pin:
                    self.idx = i
                    break

    # ------------------------------------------------------------ 底层
    def _gap(self):
        dt = time.time() - self._last
        if dt < self.min_gap:
            time.sleep(self.min_gap - dt + random.uniform(0, 0.6))
        self._last = time.time()

    def _cookie_header(self, ck):
        return "; ".join(f"{k}={v}" for k, v in ck.items())

    def _send(self, method, uri, *, params=None, payload=None, _retried=False):
        if not self.accounts:
            raise AllAccountsBlocked("无带 web_session 的账号")
        acc = self.accounts[self.idx % len(self.accounts)]
        ck = acc["ck"]
        self._gap()
        if method == "POST":
            h = self.sign.sign_headers("POST", uri, ck, payload=payload)
        else:
            h = self.sign.sign_headers("GET", uri, ck, params=params)
        h.update(BASE_HEADERS)
        h["Cookie"] = self._cookie_header(ck)
        url = EDITH + uri
        try:
            if method == "POST":
                r = requests.post(url, headers=h,
                                  data=self.sign.build_json_body(payload),
                                  timeout=self.timeout, proxies=self.proxies)
            else:
                r = requests.get(url, headers=h, params=params,
                                 timeout=self.timeout, proxies=self.proxies)
            j = r.json()
        except (requests.RequestException, ValueError):
            acc["bad"] += 1
            time.sleep(2.0)
            j = None

        if j is None:
            if _retried:
                return {}
            self.idx += 1
            return self._send(method, uri, params=params, payload=payload,
                              _retried=True)

        code = j.get("code")
        if code in ROTATE_CODES:
            acc["bad"] += 1
            if self.pin:
                # 绑定账号：不占用其他 worker 的账号。登录过期(-100)对该 cookie 是致命的，
                # 直接返回让 worker 退出；其余风控冷却后在本账号重试一次。
                if not _retried and code != -100:
                    time.sleep(12)
                    return self._send(method, uri, params=params,
                                      payload=payload, _retried=True)
            elif not _retried and len(self.accounts) > 1:
                self.idx += 1
                return self._send(method, uri, params=params, payload=payload,
                                  _retried=True)
        return j

    # ------------------------------------------------------------ 三个端点
    def _search_pace(self):
        """搜索端点强制 ≥SEARCH_MIN_GAP 间隔（实测安全节奏 2 次/分钟）。"""
        dt = time.time() - self._search_last
        if dt < SEARCH_MIN_GAP:
            time.sleep(SEARCH_MIN_GAP - dt + random.uniform(0, 0.8))

    def search(self, keyword, page=1, page_size=20):
        kw = keyword if (not self.city or self.city in keyword) else f"{keyword} {self.city}"
        items, code = [], None
        for attempt in range(3):  # 软限流空页(code0/0条)：长冷却后最多重试 2 次，宁慢不硬刷
            self._search_pace()
            payload = {"keyword": kw, "page": page, "page_size": page_size,
                       "search_id": self.sign.get_search_id(),
                       "sort": "general", "note_type": 0}
            j = self._send("POST", "/api/sns/web/v1/search/notes", payload=payload)
            self._search_last = time.time()
            code = j.get("code")
            items = (j.get("data") or {}).get("items") or []
            if items:
                self.empty_streak = 0
                return items
            if code == 0:  # 速率软限流：60–180s 长冷却，停顿后自恢复，不硬刷
                self.empty_streak = getattr(self, "empty_streak", 0) + 1
                time.sleep(min(60 * self.empty_streak, 180))
                continue
            return []
        return items

    def feed(self, nid, tok):
        payload = {"source_note_id": nid, "xsec_token": tok,
                   "xsec_source": "pc_search",
                   "image_formats": ["jpg", "webp", "avif"],
                   "extra": {"need_body_topic": "1"}}
        j = self._send("POST", "/api/sns/web/v1/feed", payload=payload)
        items = (j.get("data") or {}).get("items") or []
        return (items[0].get("note_card") or {}) if items else {}

    def comments(self, nid, tok, cursor="", pages=1):
        # 实测必须带 xsec_token + xsec_source=pc_search，否则 300031；
        # 且不可带 top_comment_id/image_formats，否则 code -1。
        out, seen = [], set()
        for _ in range(pages):
            params = {"note_id": nid, "cursor": cursor,
                      "xsec_token": tok, "xsec_source": "pc_search"}
            j = self._send("GET", "/api/sns/web/v2/comment/page", params=params)
            d = j.get("data") or {}
            for c in d.get("comments") or []:
                txt = c.get("content") or ""
                name = (c.get("user_info") or {}).get("nickname") or ""
                if txt and len(txt) < 600 and txt not in seen:
                    seen.add(txt)
                    out.append({"name": name, "text": txt})
            if not d.get("has_more"):
                break
            cursor = d.get("cursor") or ""
        return out

    # ------------------------------------------------------------ 引擎适配
    def gather_query(self, query, npq=3, city=None):
        old = self.city
        if city:
            self.city = city
        try:
            items = self.search(query)
        finally:
            self.city = old
        notes = []
        for it in items[:npq]:
            nid, tok = it.get("id"), it.get("xsec_token")
            if not nid or not tok:
                continue
            sc = it.get("note_card") or {}
            nc = self.feed(nid, tok) or sc
            cm = self.comments(nid, tok, pages=2)
            notes.append({
                "title": nc.get("title") or sc.get("display_title") or "",
                "desc": nc.get("desc") or "",
                "author": ((nc.get("user") or {}).get("nickname")
                          or (sc.get("user") or {}).get("nickname") or ""),
                "date": nc.get("time") or "",
                "url": (f"https://www.xiaohongshu.com/explore/{nid}"
                        f"?xsec_token={tok}&xsec_source=pc_search"),
                "comments": cm,
            })
        return notes


if __name__ == "__main__":
    import sys
    api = XhsApi()
    print("可用账号：", [a["name"] for a in api.accounts])
    kw = sys.argv[1] if len(sys.argv) > 1 else "本场博多豚骨拉面"
    notes = api.gather_query(kw, npq=3)
    print(f"gather {kw} → {len(notes)} 篇")
    for n in notes:
        print(f"  - {n['title']} | 评论{len(n['comments'])} | desc{n['desc'][:30]}")
        for c in n["comments"][:2]:
            print(f"      {c['name']}: {c['text'][:36]}")

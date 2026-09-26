#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
atlas_write.py — 幂等写 Atlas v2 新表（chefs / restaurant_chefs / restaurant_awards /
food_events / reviews）。默认 dry-run，--commit 才写；应用层 GET 查重，写后回读。

用法：
  python3 atlas_write.py --domain reviews --input <文件或目录>           # 预演
  python3 atlas_write.py --domain all     --input research/atlas --commit
  python3 atlas_write.py --domain chefs   --input research/atlas/chefs --commit

规则：
- 子代理只产 raw，本脚本统一写；service key（common），写新表绕过 RLS。
- chefs 按 name、awards 按(restaurant_id,award_type,year)、events 按(title,event_date)、
  reviews 按(restaurant_id,source_url 或 content) 查重，天然幂等可重跑。
- reviews 插入由触发器 trg_reviews_taste 自动重算 score_taste。
- 非法字段 / 缺 restaurant_id / 缺 content 直接跳过并计数，不硬写。
"""
import argparse
import glob
import json
import pathlib
import sys
import time

import requests

import common as C

CHEF_COLS = ["name", "name_en", "title", "bio", "origin", "is_traveling",
             "social_xhs", "social_douyin", "social_weibo", "reputation", "data_updated_at"]
RCHEF_COLS = ["restaurant_id", "chef_id", "role", "is_current", "started", "ended", "source_url"]
AWARD_COLS = ["restaurant_id", "award_type", "level", "year", "season",
              "is_current", "source_url", "source_name"]
EVENT_COLS = ["scope", "category", "title", "summary", "event_date", "restaurant_id",
              "related_restaurant_id", "chef_id", "city", "district",
              "sources", "confidence", "status", "expires_on"]
REVIEW_COLS = ["restaurant_id", "user_id", "author_name", "source_platform", "source_url",
               "rating_total", "rating_taste", "content", "visit_date", "review_kind",
               "is_verified_diner", "trust_level", "aspect_taste", "aspect_service",
               "aspect_env", "aspect_value", "aspect_json", "is_fake_suspect", "is_hidden"]

Q = requests.utils.quote


def pick(row, cols):
    return {k: row[k] for k in cols if k in row and row[k] is not None}


def get_rows(path):
    r = C.req("GET", path)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


def post_one(table, payload):
    h = dict(C.headers())
    h["Prefer"] = "return=representation"
    r = requests.post(C.BASE + "/" + table, headers=h, json=payload, timeout=45)
    return r


def patch_one(table, match, payload):
    return C.req("PATCH", "/" + table + "?" + match, json=payload)


class Stats:
    def __init__(self):
        self.d = {}

    def add(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n


def find_chef(name):
    rows = get_rows(f"/chefs?name=eq.{Q(name)}&select=id")
    return rows[0]["id"] if rows else None


def write_chef(row, commit, st):
    name = row.get("name")
    if not name:
        st.add("skip")
        return
    data = pick(row, CHEF_COLS)
    cid = find_chef(name)
    if cid is None:
        st.add("chef_new")
        if commit:
            r = post_one("chefs", data)
            if r.status_code in (200, 201) and r.json():
                cid = r.json()[0]["id"]
            else:
                cid = find_chef(name)  # 空 body / 已落，回查
                if cid is None:
                    st.add("fail"); print("  FAIL chef", name, r.status_code, r.text[:160]); return
    else:
        st.add("chef_keep")
        if commit and len(data) > 1:
            patch_one("chefs", f"id=eq.{cid}", data)
    for link in row.get("restaurants", []) or []:
        rid = link.get("restaurant_id")
        role = link.get("role", "主厨")
        if not rid:
            continue
        exists = get_rows(
            f"/restaurant_chefs?restaurant_id=eq.{rid}&chef_id=eq.{cid}"
            f"&role=eq.{Q(role)}&select=restaurant_id")
        if not exists:
            st.add("rchef_new")
            if commit:
                payload = pick(link, RCHEF_COLS)
                payload["chef_id"] = cid
                payload.setdefault("role", role)
                r = post_one("restaurant_chefs", payload)
                if r.status_code not in (200, 201, 409):
                    st.add("fail"); print("  FAIL rchef", rid, cid, r.status_code, r.text[:160])
            time.sleep(0.05)


def write_award(row, commit, st):
    rid = row.get("restaurant_id")
    t = row.get("award_type")
    if not rid or not t:
        st.add("skip"); return
    y = row.get("year")
    q = f"/restaurant_awards?restaurant_id=eq.{rid}&award_type=eq.{Q(t)}&select=id"
    if y is not None:
        q += f"&year=eq.{y}"
    if get_rows(q):
        st.add("award_keep"); return
    st.add("award_new")
    if commit:
        r = post_one("restaurant_awards", pick(row, AWARD_COLS))
        if r.status_code not in (200, 201):
            st.add("fail"); print("  FAIL award", rid, t, r.status_code, r.text[:160])


def write_event(row, commit, st):
    title = row.get("title")
    if not title:
        st.add("skip"); return
    ed = row.get("event_date")
    q = f"/food_events?title=eq.{Q(title)}&select=id"
    if ed:
        q += f"&event_date=eq.{ed}"
    if get_rows(q):
        st.add("event_keep"); return
    st.add("event_new")
    if commit:
        r = post_one("food_events", pick(row, EVENT_COLS))
        if r.status_code not in (200, 201):
            st.add("fail"); print("  FAIL event", title[:30], r.status_code, r.text[:160])


def write_review(row, commit, st):
    rid = row.get("restaurant_id")
    content = row.get("content")
    if not rid or not content:
        st.add("skip"); return
    url = row.get("source_url")
    # 评论共享笔记 URL，查重必须加 content，否则同帖多条评论只入库第一条
    if url:
        q = (f"/reviews?restaurant_id=eq.{rid}&source_url=eq.{Q(url)}"
             f"&content=eq.{Q(content, safe='')}&select=id")
    else:
        q = f"/reviews?restaurant_id=eq.{rid}&content=eq.{Q(content, safe='')}&select=id"
    if get_rows(q):
        st.add("review_keep"); return
    st.add("review_new")
    if commit:
        payload = pick(row, REVIEW_COLS)
        payload["user_id"] = None
        r = post_one("reviews", payload)
        if r.status_code not in (200, 201):
            st.add("fail"); print("  FAIL review", rid, r.status_code, r.text[:200])
        time.sleep(0.05)


WRITERS = {"chefs": ("raw_chefs", write_chef),
           "awards": ("raw_awards", write_award),
           "events": ("raw_events", write_event),
           "reviews": ("raw_reviews", write_review)}


def load_files(domain, inp):
    prefix = WRITERS[domain][0]
    p = pathlib.Path(inp)
    paths = []
    if p.is_dir():
        paths = sorted(glob.glob(str(p / "**" / f"{prefix}*.jsonl"), recursive=True))
    else:
        paths = [str(p)]
    rows = []
    for fp in paths:
        for i, line in enumerate(pathlib.Path(fp).read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [坏行] {fp}:{i} {e}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, choices=list(WRITERS) + ["all"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    domains = list(WRITERS) if args.domain == "all" else [args.domain]
    mode = "COMMIT" if args.commit else "DRY-RUN"
    for dom in domains:
        writer = WRITERS[dom][1]
        rows = load_files(dom, args.input)
        st = Stats()
        for row in rows:
            writer(row, args.commit, st)
        print(f"[{mode}] {dom}: {len(rows)} 行 -> " +
              ", ".join(f"{k}={v}" for k, v in sorted(st.d.items())))
    if not args.commit:
        print("\n确认无误后加 --commit 写库。")


if __name__ == "__main__":
    main()

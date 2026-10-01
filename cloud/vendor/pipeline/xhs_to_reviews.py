#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw_xhs.jsonl -> raw_reviews.jsonl  (v6：实体匹配统一复用 entity_match)。

v6：品牌匹配 / 分店消歧 / 合集判定 / 口味与疑问 / 正文清洗全部来自 entity_match，
本脚本只保留「读 raw_xhs → 锚定 → 过滤 → 生成 raw_reviews」的管线逻辑，
不再各写一套匹配（也修掉旧版 NEG["油腻"] 符号错误）。
"""
import datetime
import json
import os
import pathlib
import re
import sys
import fcntl

PIPE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))
import common as C          # noqa: E402
import entity_match as EM  # noqa: E402

# 单实例锁
_lk = open("/tmp/xhs_to_reviews.lock", "w")
try:
    fcntl.flock(_lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("另一个 xhs_to_reviews 正在运行，本次跳过")
    sys.exit(0)

_cands = [os.environ.get("FOOD_DATA_DIR"), "/app/data",
          "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food",
          "/Users/deuce/Doubao/chats/2026-09-28/new-chat-1/china-travel-food"]
DATA = next(pathlib.Path(p) for p in _cands if p and pathlib.Path(p).exists())
XDIR = DATA / "research/atlas/xhs"
raw_p, out_p, unmatched_p = (XDIR/"raw_xhs.jsonl", XDIR/"raw_reviews.jsonl",
                             XDIR/"unmatched_shops.jsonl")

# 评论区过滤专用（管线特有）
OUT_TOWN = re.compile(r"当地|本地|老家|原产地|来[一-龥]{1,4}(?:吃|当地|本地)|去[一-龥]{1,4}吃")
PRAISE_OTHER = re.compile(
    r"(?:隔壁|旁边|对面|斜对面|楼上下|附近)[^，。！？]{0,10}(?:好吃|香|正宗|更强|更好)|"
    r"[^，。！？]{2,8}(?:好吃|香|正宗)(?:一百倍|好多倍|得多|太多)")
ROUNDUP_CMT = re.compile(r"(?i)\bp?\d{1,2}[\s.、]|[①②③④⑤⑥⑦⑧⑨⑩]|第[一二三四五六七八九十\d]{1,3}家")


def same_person(a, b):
    return bool(EM.SQ(a)) and EM.SQ(a) == EM.SQ(b)


def parse_note_date(d):
    if not d:
        return None
    if isinstance(d, (int, float)):
        t = float(d)
        if t > 1e12:
            t /= 1000.0
        try:
            return datetime.date.fromtimestamp(t).isoformat()
        except Exception:
            return None
    d = d.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{2})-(\d{2})", d)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            now = datetime.date.today()
            yr = now.year
            if mm > now.month or (mm == now.month and dd > now.day):
                yr -= 1
            return f"{yr}-{mm:02d}-{dd:02d}"
    return None


def main():
    idx = EM.get_index()
    reviews, unmatched = [], []
    for line in open(raw_p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        for note in rec["notes"]:
            rid, reason = idx.anchor_note(note, rec["name"])
            author = (note.get("author") or "")[:20]
            body = EM.clean_content(note.get("desc", ""))
            if rid is None:
                unmatched.append({"search_name": rec["name"],
                                  "note_title": note.get("title"),
                                  "note_url": note.get("url"),
                                  "guess": note.get("title", "")[:30],
                                  "reason": reason})
            else:
                if not re.search(r"文[｜|]|编辑[｜|]|记者|图文制作|商业思维|商业模式",
                                 note.get("desc", "")) \
                   and len(body) >= 8 and C.quote_has_substance(body) \
                   and not EM.is_question(body):
                    a, raw = EM.taste_sent(body)
                    vd = parse_note_date(note.get("date"))
                    if a is not None:
                        trust = "mid" if "待核" in reason else "high"
                        rev = {"restaurant_id": rid, "author_name": author,
                               "source_platform": "小红书", "source_url": note.get("url"),
                               "content": body, "review_kind": "diner",
                               "is_verified_diner": True, "trust_level": trust,
                               "aspect_taste": a, "aspect_json": {"taste_raw": raw}}
                        if vd:
                            rev["visit_date"] = vd
                        reviews.append(rev)
            if rid:
                for c in note.get("comments", []):
                    ct = EM.clean_content(c.get("text", ""))
                    cname = (c.get("name") or "").strip()
                    if len(ct) < 4 or EM.is_question(ct) or same_person(cname, author):
                        continue
                    if not C.quote_has_substance(ct) or OUT_TOWN.search(ct):
                        continue
                    if PRAISE_OTHER.search(ct) or ROUNDUP_CMT.search(ct):
                        continue
                    cmen = idx.shops_mentioned(ct)
                    other = [x for x in cmen if x.id != rid and not x.is_ref]
                    if other:
                        continue
                    a, raw = EM.taste_sent(ct)
                    if a is None:
                        continue
                    vd = parse_note_date(note.get("date"))
                    rev = {"restaurant_id": rid,
                           "author_name": (cname or "小红书用户")[:20],
                           "source_platform": "小红书", "source_url": note.get("url"),
                           "content": ct, "review_kind": "diner",
                           "is_verified_diner": True, "trust_level": "mid",
                           "aspect_taste": a, "aspect_json": {"taste_raw": raw}}
                    if vd:
                        rev["visit_date"] = vd
                    reviews.append(rev)

    pathlib.Path(out_p).write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in reviews), encoding="utf-8")
    pathlib.Path(unmatched_p).write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in unmatched), encoding="utf-8")
    print("生成 reviews:", len(reviews), "| 未锚笔记:", len(unmatched))
    from collections import Counter
    print("有口味分:", sum(1 for x in reviews if x["aspect_taste"] is not None))
    print("未锚原因分布:", dict(Counter(x["reason"] for x in unmatched)))


if __name__ == "__main__":
    main()

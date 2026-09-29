#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/bili_enrich.py — Track 1B：B站视频 enrichment（标题-only → 详情/字幕/评论）。

北极星对齐：
  - A1 口味唯一最高：从「UP主自己的视频文本」与「评论区食客」分别提取【真实堂食口味信号】，
    并区分声音——KOL/curator（UP主本人，半商业、 curated list，权重低，绝不冒充独立食客）
    vs diner_comment（评论区真实食客，独立声音，keyless 未验证 trust=low）。
  - A2 宁空不假：详情为空 / 无公开字幕 / 评论拿不到就如实记 0，绝不编造信号。
  - A5 keyless 优先：只用匿名公开接口；被风控(code!=0)即记 blocked 不硬刷。
  - 绝不直接插 restaurants；信号只落 discovery/bili_signals.jsonl，交 admission_gate 聚合。

通道（实测 2026-09-29，容器出口 IP）：
  - x/web-interface/view?bvid=  code=0 → full desc / aid / cid（搜索 desc 常为 "-"，这里才补全）。
  - x/player/v2?bvid=&cid=       code=0 → 公开字幕轨（探店视频多数 subtitles=[]，机会性提取）。
  - x/v2/reply?oid=<aid>&type=1&sort=2  code=0（Referer 必须是视频页 URL，否则被风控）→ 评论。

确定性 / 幂等：状态 /app/data/bili_enrich_state.json 记录已 enrich 的 post_id，重跑跳过；
默认 dry-run 只打印报告；--apply 才追加信号文件。不写 restaurants、不改 posts/mentions 字段。
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import requests  # noqa: E402
import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402
import kol_monitor as KM  # noqa: E402

STATE_F = DATA / "bili_enrich_state.json"
SIGNAL_F = DATA / "discovery" / "bili_signals.jsonl"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
VIEW_API = "https://api.bilibili.com/x/web-interface/view"
PLAYER_API = "https://api.bilibili.com/x/player/v2"
REPLY_API = "https://api.bilibili.com/x/v2/reply"
MIN_INTERVAL = 1.0
MAX_COMMENTS = 15

_SENT_SPLIT = re.compile(r"[。！？!?\n；;]+")


def sentences(text):
    return [s.strip() for s in _SENT_SPLIT.split(str(text or "")) if len(s.strip()) >= 6]


# ------------------------------------------------------------------ keyless 通道
def view_detail(bvid):
    try:
        j = requests.get(VIEW_API, params={"bvid": bvid},
                        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
                        timeout=15).json()
    except Exception as e:
        return None, f"view异常 {e}"
    if j.get("code") != 0:
        return None, f"view code={j.get('code')}"
    d = j["data"]
    return {"aid": d["aid"], "cid": d["cid"],
            "desc": (d.get("desc") or "").strip(),
            "title": d.get("title") or ""}, None


def get_subtitle(bvid, cid):
    """返回字幕纯文本；无公开字幕/失败返回 ""（不视为错误）。"""
    try:
        j = requests.get(PLAYER_API, params={"bvid": bvid, "cid": cid},
                         headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"},
                         timeout=15).json()
        subs = (j.get("data") or {}).get("subtitle", {}).get("subtitles") or []
    except Exception:
        return "", False
    if not subs:
        return "", False
    url = subs[0].get("subtitle_url", "")
    if url.startswith("//"):
        url = "https:" + url
    try:
        body = requests.get(url, headers={"User-Agent": UA}, timeout=15).json().get("body") or []
        return " ".join(x.get("content", "") for x in body), True
    except Exception:
        return "", False


def get_comments(aid, video_url, up_name):
    """评论区（食客声音）。Referer 必须是视频页，否则风控。返回 [{name,content,likes}]。"""
    try:
        j = requests.get(REPLY_API, params={"oid": aid, "type": 1, "sort": 2, "ps": MAX_COMMENTS},
                         headers={"User-Agent": UA, "Referer": video_url}, timeout=15).json()
    except Exception:
        return [], "reply异常"
    if j.get("code") != 0:
        return [], f"reply code={j.get('code')}"
    out = []
    for r in (j.get("data") or {}).get("replies") or []:
        member = r.get("member") or {}
        name = member.get("uname") or ""
        if C.cjk_norm(name) == C.cjk_norm(up_name):
            continue  # UP主本人回复 = KOL 声音，不算独立食客
        out.append({"name": name, "content": r.get("content", {}).get("message", ""),
                    "likes": r.get("like", 0)})
    return out, None


# ------------------------------------------------------------------ 信号提取
def kol_signals_from_text(text, core2rests, post):
    """KOL/curator 声音：UP主视频正文/字幕里、提到某库内店且含实物词的句子。"""
    sigs = []
    for s in sentences(text):
        cs = C.cjk_norm(s)
        for core, rests in core2rests.items():
            if core not in cs:
                continue
            if not C.quote_has_substance(s):
                continue  # 空话（绝绝子/天花板）不计口味证据
            rid = rests[0]["id"] if len(rests) == 1 else None
            sigs.append({
                "restaurant_id": rid,
                "mentioned_raw": rests[0]["name"],
                "voice": "kol_curator",
                "trust": "low",          # KOL curated，半商业，权重低
                "polarity": KM.polarity_for(s),
                "text": s[:200],
                "author": post["kol_name"],
                "post_id": post["id"],
                "url": post["post_url"],
            })
            break  # 一句只挂一个核心（最长优先近似：core2rests 已按调用方迭代，去重在调用方）
    # 去重：同一 post+restaurant_id+text
    seen = set(); uniq = []
    for x in sigs:
        k = (x["restaurant_id"], x["text"])
        if k in seen:
            continue
        seen.add(k); uniq.append(x)
    return uniq


def diner_signals_from_comments(comments, core2rests, known_leads, post):
    """食客声音：评论里提到库内店/线索名且含实物词。"""
    sigs = []
    for c in comments:
        content = c.get("content", "")
        if not C.quote_has_substance(content):
            continue
        cn = C.cjk_norm(content)
        matched_any = None
        for core, rests in core2rests.items():
            if core in cn:
                matched_any = (rests[0]["id"] if len(rests) == 1 else None, rests[0]["name"])
                break
        lead = None
        if not matched_any:
            for ld in known_leads:
                if C.cjk_norm(ld) and C.cjk_norm(ld) in cn:
                    lead = ld
                    break
        if not matched_any and not lead:
            continue
        rid = matched_any[0] if matched_any else None
        name = matched_any[1] if matched_any else lead
        sigs.append({
            "restaurant_id": rid,
            "mentioned_raw": name,
            "voice": "diner_comment",
            "trust": "low",          # keyless 评论，未验证
            "polarity": KM.polarity_for(content),
            "text": content[:200],
            "author": c.get("name", ""),
            "likes": c.get("likes", 0),
            "post_id": post["id"],
            "url": post["post_url"],
        })
    return sigs


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done_posts": [], "runs": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    apply = args.apply

    SIGNAL_F.parent.mkdir(parents=True, exist_ok=True)
    _, core2rests = KM.build_rest_index()
    known_leads = set()  # 线索名从 mentions unmatched 取
    posts = C.fetch_all("food_kol_posts",
                        "id,kol_id,platform,post_url,title,summary",
                        order_col="id")
    bili = [p for p in posts if p.get("platform") == "bilibili"]
    if args.limit:
        bili = bili[:args.limit]

    # KOL 名映射 + unmatched 线索名
    kols = {k["id"]: k["name"] for k in C.fetch_all(
        "food_kol_watchlist", "id,name", order_col="id")}
    ments = C.fetch_all("food_kol_mentions", "post_id,mentioned_raw,match_status,restaurant_id",
                        order_col="id")
    leads_by_post = {}
    for m in ments:
        if m.get("match_status") == "unmatched":
            leads_by_post.setdefault(m["post_id"], set()).add(m.get("mentioned_raw"))
            known_leads.add(m.get("mentioned_raw"))

    st = load_state()
    done = set(st.get("done_posts", []))

    report = {"mode": "apply" if apply else "dry-run",
              "posts": 0, "already": 0, "blocked": [],
              "with_rich_desc": 0, "with_subtitle": 0, "with_comments": 0,
              "kol_signals": 0, "diner_signals": 0,
              "restaurants_with_signal": set(), "comments_fetched": 0}
    all_sigs = []

    for p in bili:
        pid = p["id"]
        if pid in done:
            report["already"] += 1
            continue
        bvid = (p.get("post_url") or "").rstrip("/").split("/")[-1]
        if not bvid:
            continue
        up_name = kols.get(p.get("kol_id"), "")
        p["kol_name"] = up_name

        det, err = view_detail(bvid)
        if err:
            report["blocked"].append({"post_id": pid, "bvid": bvid, "why": err})
            time.sleep(MIN_INTERVAL)
            continue
        report["posts"] += 1

        desc = det["desc"]
        if len(desc) >= 40:
            report["with_rich_desc"] += 1
        sub, has_sub = get_subtitle(bvid, det["cid"])
        if has_sub:
            report["with_subtitle"] += 1
        comments, cerr = get_comments(det["aid"], p["post_url"], up_name)
        if not cerr and comments:
            report["with_comments"] += 1
            report["comments_fetched"] += len(comments)

        enriched = f"{p.get('title') or ''}。{desc} {sub}".strip()
        ksig = kol_signals_from_text(enriched, core2rests, p)
        dsig = diner_signals_from_comments(comments, core2rests,
                                           leads_by_post.get(pid, set()), p)
        report["kol_signals"] += len(ksig)
        report["diner_signals"] += len(dsig)
        for x in ksig + dsig:
            if x["restaurant_id"]:
                report["restaurants_with_signal"].add(x["restaurant_id"])
        all_sigs.extend(ksig + dsig)
        done.add(pid)
        time.sleep(MIN_INTERVAL)

    report["restaurants_with_signal"] = len(report["restaurants_with_signal"])

    if apply and all_sigs:
        with SIGNAL_F.open("a", encoding="utf-8") as f:
            for x in all_sigs:
                x["captured_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        st["done_posts"] = sorted(done)
        st["runs"] = st.get("runs", 0) + 1
        st["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=" * 90)
    print(f"B站 enrichment — {report['mode']}")
    print("=" * 90)
    print(f"待 enrich posts={len(bili)} 已完成跳过={report['already']} 本轮处理={report['posts']} "
          f"阻塞={len(report['blocked'])}")
    print(f"  view 详情补全(desc>=40)={report['with_rich_desc']}  公开字幕={report['with_subtitle']}  "
          f"拿到评论={report['with_comments']} (评论{report['comments_fetched']}条)")
    print(f"  提取信号：KOL/curator={report['kol_signals']}  食客评论={report['diner_signals']}  "
          f"覆盖库内店={report['restaurants_with_signal']}家")
    if report["blocked"]:
        print("  阻塞样例：", report["blocked"][:3])
    if apply:
        print(f"  → 信号已追加 {SIGNAL_F}（共{len(all_sigs)}条；restaurants/posts/mentions 零变化）")
    else:
        print(f"  (dry-run；--apply 才写 {SIGNAL_F} 并推进幂等游标)")


if __name__ == "__main__":
    main()

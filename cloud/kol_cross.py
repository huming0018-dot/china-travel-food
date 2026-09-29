#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/kol_cross.py — Track 1C：KOL 跨平台身份归一 + 开放平台定点采集。

上位契约：references/source-classes-and-calibration.md §3（三类来源/校准闭环）。
  - food_kol_watchlist 是主实体；跨平台 handle 挂在 handles jsonb（migration 016）。
  - 跨平台同款内容按【内容指纹】去重，只算 1 个独立声音。
  - KOL 内容只作线索，不回写 score_*；新提及店过 admission_gate 才入库。

通道现实（2026-09-29 容器出口 IP 实测，L0/L1/L2 优先、不硬闯）：
  - bilibili：开放搜索/详情/评论已由 kol_monitor.py + bili_enrich.py 覆盖（本连接器不重复采）。
  - 公众号：搜狗微信 weixin.sogou.com/weixin?type=2&query=<博主名> code=200 无验证码，
    可确定性提取标题+摘要+跳转链接。按博主名搜，找该博主的公众号文章。
  - 微博 s.weibo.com / 知乎 / 抖音：keyless 解析不可靠（微博 0 cards、知乎 403、抖音 JS 壳），
    本连接器【不硬刷】，标记 blocked/skipped，留待有浏览器/账号时再接。

归属谨慎原则（A2 宁空不假）：
  - 搜狗按博主名搜出的文章，未必都是该博主【本人公众号】所发（可能是他人提及/转载）。
  - 因此本连接器【不把这些文章写成 food_kol_posts 并硬绑 kol_id】，而是作为【探店线索】
    落 discovery gap pool（raw_cross.jsonl），由 admission_gate / 人工归属裁决。
  - handle 解析：只有当结果账号名 cjk_norm 与博主名一致才记 handle；本 keyless 通道拿不到
    可靠账号名时，只报「该博主在公众号有公开痕迹」，不写 handles（等 016 列就绪+人工确认）。

幂等：内容指纹 sha1(cjk_norm(title)) + 跳转链接 去重；状态 /app/data/kol_cross_state.json。
默认 dry-run；--apply 才追加线索文件。绝不写 restaurants、绝不改 posts/mentions。
"""
import argparse
import datetime
import hashlib
import html
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = "/app/pipeline"
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import requests  # noqa: E402
import common as C  # noqa: E402
import kol_monitor as KM  # noqa: E402

STATE_F = pathlib.Path("/app/data/kol_cross_state.json")
LEAD_F = pathlib.Path("/app/data/discovery/raw_cross.jsonl")
SOGOU = "https://weixin.sogou.com/weixin"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MIN_INTERVAL = 1.0


def clean(x):
    return html.unescape(re.sub(r"<[^>]+>", "", x or "")).strip()


def fp(title):
    return hashlib.sha1(C.cjk_norm(title).encode("utf-8")).hexdigest()[:16]


def sogou_wechat(name):
    """按博主名搜搜狗微信文章。返回 [{title,snippet,url}]；失败/风控返回 ([], err)。"""
    try:
        r = requests.get(SOGOU, params={"type": 2, "query": name},
                         headers={"User-Agent": UA}, timeout=15)
    except Exception as e:
        return [], f"请求异常 {e}"
    if r.status_code != 200 or "antispider" in r.text or "验证码" in r.text:
        return [], f"风控/验证码 http={r.status_code}"
    items = re.findall(r'<li id="sogou_vr_.*?</li>', r.text, re.S)
    out = []
    for it in items:
        mt = re.search(r"<h3>.*?<a[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", it, re.S)
        ms = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', it, re.S)
        if not mt:
            continue
        href = mt.group(1)
        if href.startswith("/link"):
            href = "https://weixin.sogou.com" + href
        out.append({"title": clean(mt.group(2)), "snippet": clean(ms.group(1)) if ms else "",
                    "url": href})
    return out, None


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen_fp": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    _, core2rests = KM.build_rest_index()
    known_cores = set(core2rests.keys())
    kols = C.fetch_all("food_kol_watchlist", "id,name,platform,mid,kol_type,status",
                      order_col="id", extra="status=eq.active")

    # 已有帖子指纹（跨平台同款去重：B站已采标题不算新声音）
    existing_fps = set()
    for p in C.fetch_all("food_kol_posts", "title", order_col="id"):
        if p.get("title"):
            existing_fps.add(fp(p["title"]))

    st = load_state()
    seen = set(st.get("seen_fp", []))

    cross = [k for k in kols if k.get("platform") == "cross"]
    bili = [k for k in kols if k.get("platform") == "bilibili"]

    rep = {"mode": "apply" if args.apply else "dry-run",
           "identity": {"bilibili_with_mid": 0, "wechat_present": 0,
                        "weibo_resolved": 0, "zhihu_resolved": 0, "douyin_resolved": 0},
           "wechat": {"queried": 0, "articles": 0, "new_after_dedup": 0,
                      "matched": 0, "ambiguous": 0, "leads": 0},
           "blocked": []}
    for k in bili:
        if k.get("mid"):
            rep["identity"]["bilibili_with_mid"] += 1

    lead_buf = []
    for k in cross:
        name = k["name"]
        rep["wechat"]["queried"] += 1
        arts, err = sogou_wechat(name)
        if err:
            rep["blocked"].append({"kol": name, "why": err})
            time.sleep(MIN_INTERVAL)
            continue
        if arts:
            rep["identity"]["wechat_present"] += 1
        for a in arts:
            rep["wechat"]["articles"] += 1
            f = fp(a["title"])
            if f in seen or f in existing_fps:
                continue  # 跨平台同款/已采，只算 1 个声音
            seen.add(f)
            rep["wechat"]["new_after_dedup"] += 1
            text = f"{a['title']}。{a['snippet']}"
            matched, ambiguous = KM.anchor_mentions(text, core2rests)
            leads = KM.extract_leads(a["title"], a["snippet"], known_cores)
            rep["wechat"]["matched"] += len(matched)
            rep["wechat"]["ambiguous"] += len(ambiguous)
            rep["wechat"]["leads"] += len(leads)
            # 线索入 gap pool（不写 posts/mentions/restaurants；归属待 gate/人工确认）
            lead_buf.append({"kind": "discover", "category": "kol_cross", "city": "上海",
                             "source": "wechat_sogou", "queried_kol": name,
                             "note": {"title": a["title"], "snippet": a["snippet"],
                                      "url": a["url"],
                                      "matched": [m["mentioned_raw"] for m in matched],
                                      "leads": leads}})
        time.sleep(MIN_INTERVAL)

    if args.apply and lead_buf:
        LEAD_F.parent.mkdir(parents=True, exist_ok=True)
        with LEAD_F.open("a", encoding="utf-8") as f:
            for r in lead_buf:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        st["seen_fp"] = sorted(seen)
        st["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=" * 90)
    print(f"KOL 跨平台采集 — {rep['mode']}")
    print("=" * 90)
    print("身份归一（handle 确定性解析，不硬猜）：")
    print(f"  bilibili 已知 mid = {rep['identity']['bilibili_with_mid']}/{len(bili)}")
    print(f"  公众号(搜狗有公开痕迹) = {rep['identity']['wechat_present']}/{len(cross)} "
          f"(keyless 拿不到可靠账号名→不写 handles，待 016 列+人工确认)")
    print(f"  微博/知乎/抖音 keyless 不可采 = 0（不硬刷，标记 skipped）")
    w = rep["wechat"]
    print(f"公众号采集：cross KOL 查 {w['queried']}，抓文章 {w['articles']}，"
          f"跨指纹去重后新 {w['new_after_dedup']}")
    print(f"  提及：matched={w['matched']} ambiguous={w['ambiguous']} 线索={w['leads']}")
    if rep["blocked"]:
        print("  阻塞样例：", rep["blocked"][:2])
    if args.apply:
        print(f"  → 线索追加 {LEAD_F}（共{len(lead_buf)}条；posts/mentions/restaurants 零写入）")
    else:
        print(f"  (dry-run；--apply 才写线索文件并推进指纹游标)")


if __name__ == "__main__":
    main()

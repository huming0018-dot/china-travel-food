#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kol_post_ingest.py — KOL/美食家「帖子归档 + 提及店名」确定性入库（平台无关）。

为什么存在：各平台连接器（bilibili 已采、douyin/wechat 待建）只负责把帖子拉成统一记录；
本模块做机械环节——
  1) 从帖子（标题+摘要+正文）里【按在库餐厅名 + 别名词典】抽取提及（归一化 + 最长匹配）；
  2) 归档 food_kol_posts（post_url 唯一）；
  3) 提及写 food_kol_mentions：matched / ambiguous / unmatched；
     - 提及只作线索/特征标签，绝不计入 taste；
     - 未匹配的店名线索由连接器侧另入发现队列喂 sourcing。
  4) 提及情感用【归属窗口 + 口味词】判定：每个提及拥有“自己起点→下一个提及起点”之间的
     描述，名字后的赞美/批评归该名字、不越过下一个名字；服务/情绪词不算口味；默认 neu。

输入 jsonl，每行：
  {"kol_id":102,"platform":"cross","post_url":"https://...","title":"...",
   "summary":"...","published_at":"2026-09-01","text":"正文，可含店名"}
用法：
  python3 kol_post_ingest.py posts.jsonl            # dry-run，只打印
  python3 kol_post_ingest.py posts.jsonl --commit   # 写库
"""
import json
import pathlib
import sys

try:
    import common as C
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import common as C
import requests

# 口味词（用于提及归属窗口的情感判定；服务/情绪/环境词刻意不收）
POS_WORDS = ["好吃", "惊艳", "香", "嫩滑", "鲜嫩", "鲜美", "正宗", "地道", "回购", "入味",
             "酥脆", "浓郁", "满足", "天花板", "锅气", "层次", "软糯", "回甘", "值得", "现炒"]
NEG_WORDS = ["难吃", "踩雷", "失望", "齁咸", "腥", "发柴", "预制", "不新鲜", "寡淡",
             "嚼不烂", "糊了", "变质", "雷区", "不推荐", "徒有虚名", " reheated"]

NAME_MIN_CJK = 2   # 少于 2 个汉字的店名不做正文子串匹配（误报太多）


def _han(s):
    return "".join(ch for ch in s if "一" <= ch <= "鿿")


def build_name_index(rests):
    """返回 [(core, rid, canonical, n_cjk)]，含 name / name_en / 别名；长名优先。"""
    idx = {}
    for r in rests:
        if r.get("status") not in (None, "active"):
            continue
        cands = [r.get("name"), r.get("name_en")]
        ali = r.get("aliases")
        if isinstance(ali, str):
            try:
                ali = json.loads(ali)
            except Exception:
                ali = [ali]
        if isinstance(ali, list):
            cands += [a for a in ali if a]
        for nm in cands:
            if not nm:
                continue
            core = C.cjk_norm(str(nm))
            if core:
                idx.setdefault(core, (r["id"], r.get("name"), len(_han(core))))
    return sorted([(k, *v) for k, v in idx.items()], key=lambda x: -len(x[0]))


def _polarity_counts(seg):
    return (sum(w in seg for w in POS_WORDS),
            sum(w in seg for w in NEG_WORDS))


def _label(pos, neg):
    if pos > neg and pos:
        return "pos"
    if neg > pos and neg:
        return "neg"
    if pos and neg and pos == neg:
        return "mixed"
    return "neu"


def find_mentions(text, name_idx):
    """整篇归一化文本上最长匹配店名，按提及位置切归属窗口；同店多次出现按口味计数聚合。"""
    cn = C.cjk_norm(text or "")
    if not cn:
        return []
    spans = []  # (start,end,core,rid,canonical)
    for core, rid, canonical, n_cjk in name_idx:
        if n_cjk < NAME_MIN_CJK and not (core.isascii() and len(core) >= 4):
            continue
        pos = cn.find(core)
        if pos < 0:
            continue
        if any(not (pos >= b or pos + len(core) <= a) for a, b, *_ in spans):
            continue  # 与更长命中重叠
        spans.append((pos, pos + len(core), core, rid, canonical))
    spans.sort()
    agg = {}
    for i, (s, e, core, rid, canonical) in enumerate(spans):
        win_start = 0 if i == 0 else s
        win_end = spans[i + 1][0] if i + 1 < len(spans) else len(cn)
        cp, cneg = _polarity_counts(cn[win_start:win_end])
        rec = agg.setdefault(rid, [0, 0, canonical, core])
        rec[0] += cp
        rec[1] += cneg
    return [{"rid": rid, "name": v[2], "core": v[3], "polarity": _label(v[0], v[1])}
            for rid, v in agg.items()]


def ingest_one(rec, name_idx, commit=False):
    text = " ".join(str(rec.get(k, "")) for k in ("title", "summary", "text"))
    mentions = find_mentions(text, name_idx)
    if not commit:
        return mentions
    # 1) 归档帖子
    post = {"kol_id": rec.get("kol_id"), "platform": rec.get("platform"),
            "post_url": rec["post_url"], "title": rec.get("title"),
            "summary": rec.get("summary"), "published_at": rec.get("published_at"),
            "raw_mentions": [m["name"] for m in mentions]}
    h = C.headers()
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    r = requests.post(C.BASE + "/food_kol_posts?on_conflict=post_url",
                      headers=h, json=post, timeout=45)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"post upsert {r.status_code}: {r.text[:200]}")
    rep = r.json()
    if isinstance(rep, list) and rep:
        post_id = rep[0]["id"]
    else:
        got = requests.get(
            C.BASE + f"/food_kol_posts?post_url=eq.{rec['post_url']}&select=id",
            headers=C.headers(), timeout=30).json()
        post_id = got[0]["id"]
    # 2) 提及
    mrows = [{"post_id": post_id, "restaurant_id": m["rid"],
              "mentioned_raw": m["name"], "match_status": "matched",
              "polarity": m["polarity"]} for m in mentions]
    if mrows:
        h2 = C.headers()
        h2["Prefer"] = "resolution=merge-duplicates"
        rr = requests.post(
            C.BASE + "/food_kol_mentions?on_conflict=post_id,mentioned_raw",
            headers=h2, json=mrows, timeout=45)
        if rr.status_code not in (200, 201):
            raise RuntimeError(f"mention upsert {rr.status_code}: {rr.text[:200]}")
    return mentions


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    commit = "--commit" in sys.argv
    if not args:
        raise SystemExit("用法: kol_post_ingest.py posts.jsonl [--commit]")
    rests = C.fetch_all("restaurants", "id,name,name_en,aliases,status", order_col="id")
    name_idx = build_name_index(rests)
    n_post = n_men = 0
    for line in pathlib.Path(args[0]).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        ms = ingest_one(rec, name_idx, commit=commit)
        n_post += 1
        n_men += len(ms)
        flag = "COMMIT" if commit else "DRY"
        print(f"[{flag}] {rec.get('post_url', '')[:60]} -> {len(ms)} 提及: "
              + ", ".join(f"{m['name']}({m['polarity']})" for m in ms))
    print(f"\n帖子 {n_post}，提及 {n_men}，模式={'写库' if commit else 'dry-run'}")


if __name__ == "__main__":
    main()

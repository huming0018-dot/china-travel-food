#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admission_gate.py v2 — 社交声音聚合 + 收录门槛（离线、确定性、不耗浏览器）。

v2 相比 v1 的修正（面包线做精时暴露的问题）：
  1) 自由文本英文 NER 太脆弱（"L'Atelier Over Bakery" 被切成 over/overl/latelierover 等5个碎片）
     → 改为以【合集结构化锚点】为主："- 店名 ："、"📍店名"、"店名丨菜品"、编号/图X；
  2) 品牌异写归一：BRAND_DICT 把 over / atelier over / L'Atelier Over Bakery 等别名归到一个品牌实体；
  3) 限定主营面包：库内店须挂面包标签，非面包店（蜀宴赋）排除；
  4) 评论区按【评论者 name】计独立声音（v1 错把笔记作者当评论者，声音被低估）；
  5) 单一博主合集不构成收录，必须有独立交叉（多合集 / 评论区独立食客 / 专门笔记）。

用法：
  python3 admission_gate.py --raw research/social/raw_discovery.jsonl --category bread
"""
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

import common as C

# ---------------------------------------------------------------- 口味
POS = {"好吃": .35, "正宗": .3, "惊艳": .4, "鲜嫩": .25, "入味": .25, "地道": .3, "值得": .2,
       "香": .15, "酥脆": .25, "弹": .2, "浓郁": .15, "回购": .25, "新鲜": .25, "爆汁": .3,
       "鲜美": .25, "嫩滑": .25, "层次": .15, "外脆里韧": .3, "必买": .25, "天花板": .25}
NEG = {"难吃": -.6, "避雷": -.5, "踩雷": -.5, "失望": -.4, "一般": -.3, "不好吃": -.55,
       "腥": -.35, "柴": -.35, "预制": -.4, "冷冻": -.3, "不新鲜": -.45, "太咸": -.25,
       "糊弄": -.4, "无味": -.4, "寡淡": -.3, "嚼不动": -.4, "名不副实": -.4, "怕了": -.15,
       "没记忆点": -.2, "两头不着": -.2, "平平无奇": -.25}
PROMO_WORDS = ("团购", "代金券", "套餐", "合作", "推广", "广告", "福利", "戳左下角",
               "购买链接", "招商", "加盟")
BAKED_ITEMS = ("可颂", "贝果", "酸种", "酸面包", "欧包", "吐司", "乡村", "全麦", "肉桂卷",
               "司康", "法棍", "恰巴塔", "佛卡夏", "丹麦", "菠萝包", "盐面包", "碱水",
               "生吐司", "酥皮", "牛角", "黑麦", "核桃", "布里欧", "戚风", "明太子", "苏打面包")
BREAD_SECTION = re.compile(r"(可颂|酥皮|盐面包|欧包|酸面?包|贝果|吐司|日式|面包|烘焙|bagel|croissant|sourdough|bakery)")
# 定向取证搜索词 → 实际规范品牌（anchor 按店名搜，品牌由取证确认；解决 token 顺序/异写，如 Time&Flour 实为 Flour Time）
ANCHOR_BRAND = {"Orenda Bay": "Orenda Bay", "Time & Flour": "Flour Time",
                "时光 面粉 面包": "Flour Time"}

# ---------------------------------------------------------------- 品牌异写词典（seed，持续扩充）
# canonical + aliases（都会 cjk_norm；短别名只在结构化锚点精确匹配，不做自由子串，防 over/soso 误锚）
BRAND_DICT = [
    ("L'Atelier Over Bakery", ["latelieroverbakery", "atelieroverbakery", "atelierover",
                               "latelierover", "overbakery", "over", "overl", "latelieroveromakase",
                               "atelieroveromakase"]),
    ("B+Baked", ["bbaked", "bebaked", "baked", "b+baked"]),
    ("Proust Moment", ["proustmoment", "proustmomentbakery", "proust"]),
    ("BAsdBAN", ["basdban", "巴适得板"]),
    ("Dear You", ["dearyou", "dear"]),
    ("MBD", ["mbd"]),
    ("Shiopon", ["shiopon"]),
    ("FASCINO", ["fascino"]),
    ("ComeCome", ["comecome"]),
    ("O'mills", ["omills", "omillssourdoughbakery", "omillssourdough"]),
    ("7RIVERLIGHT", ["7riverlight", "riverlight"]),
    ("Table A Deli", ["tableadeli", "tablea"]),
    ("Lilis", ["lilis"]),
    ("山醒", ["山醒"]),
    ("Folder", ["folder"]),
    ("Soso", ["soso"]),
    ("Punch Monday", ["punchmonday", "punchmondaybakery"]),
    ("银座仁志川", ["银座仁志川", "仁志川"]),
    ("27Bakery", ["27bakery"]),
    ("Skroll", ["skroll"]),
    ("狮子山", ["狮子山"]),
    ("Kojic", ["kojic"]),
]


def build_alias_map():
    alias2canon, short = {}, set()
    for canon, aliases in BRAND_DICT:
        for a in [canon] + aliases:
            na = C.cjk_norm(a)
            if na:
                alias2canon[na] = canon
                if len(na) <= 4:
                    short.add(na)
    return alias2canon, short


# ---------------------------------------------------------------- 未知专名开放式发现（线索）
# 结构化锚点管"准"，这里管"全"：捞不在品牌词典/库里的新店名（如 Orenda Bay），只作线索、需锚定取证。
EN_STOP = {"best", "top", "bakery", "bakeries", "bread", "sourdough", "croissant", "bagel",
           "shanghai", "recipe", "recipes", "food", "guide", "the", "and", "a", "an", "of",
           "in", "to", "for", "with", "is", "are", "homemade", "artisan", "fresh", "new",
           "good", "great", "musttry", "must", "try", "love", "so", "soo", "super", "really",
           "very", "delicious", "yummy", "omg", "lol", "imho", "btw", "michelin", "star",
           "restaurant", "restaurants", "cafe", "coffee", "bistro", "brunch", "morning",
           "day", "today", "post", "link", "bio", "check", "recommend", "plus", "me", "my",
           "it", "this", "that", "you", "i", "we", "they", "he", "she", "at", "on", "be",
           "was", "were", "been", "am", "do", "does", "did", "have", "has", "had", "will",
           "would", "can", "could", "should", "if", "as", "by", "or", "not", "but", "from",
           "up", "out", "into", "about", "more", "also", "just", "one", "no", "yes"}
_EN = re.compile(r"[A-Za-z][A-Za-z0-9'&+.\-]{1,30}(?:\s+[A-Za-z0-9'&+.\-]{1,30}){0,5}")


def collect_leads(text, known, leads):
    """从文本提取未知英文专名（最长匹配）。known=已知名 norm 集合，命中则跳过。"""
    for m in _EN.finditer(text):
        raw = re.sub(r"\s+", " ", m.group()).strip(" .-'&+")
        toks = [t for t in re.split(r"[\s&+]+", raw.lower().replace(".", " ").replace("'", " "))
                if t]
        distinctive = [t for t in toks if t not in EN_STOP]
        if not distinctive:
            continue
        key = C.cjk_norm(raw)
        if len(key) < 4:
            continue
        if any((len(k) >= 5 and k in key) or (len(key) >= 5 and key in k) for k in known):
            continue
        leads[key] += 1


def merge_leads(leads):
    """子串碎片归并到最长专名，频次相加。"""
    keys = sorted(leads, key=lambda x: -len(x))
    keep = {}
    for k in keys:
        longer = [L for L in keep if k in L]
        if longer:
            keep[longer[0]] += leads[k]
        else:
            keep[k] = keep.get(k, 0) + leads[k]
    return keep


def taste_raw(text):
    pos = sum(w for k, w in POS.items() if k in text)
    neg = sum(w for k, w in NEG.items() if k in text)
    if pos == 0 and neg == 0:
        return None
    return max(1.0, min(5.0, round(3.8 + pos + neg, 2)))


def has_neg_word(t):
    return bool(re.search(r"难吃|避雷|踩雷|失望|一般|不好吃|名不副实|平平无奇|没记忆点|两头不着|怕了|寡淡", t))


# ---------------------------------------------------------------- 结构化锚点
# "- Basdban ：..." / "- bebaked ：..."
RE_DASH = re.compile(r"^\s*[-•·▪️◦]?\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,22}?)\s*[:：]\s*(.+)$")
RE_PIN = re.compile(r"📍\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,22})")          # 📍over
RE_BAR = re.compile(r"([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,18}?)\s*丨\s*")      # lilis丨菜品
RE_NUM = re.compile(r"(?:^|\s)(?:[①-⑳㉑-㉟]|\d{1,2}[.、)]|\d️⃣)\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,20}?)(?:[:：]|\s{2,}|$)")
GENERIC_ANCHOR = {"面包", "面包店", "可颂", "贝果", "欧包", "酸种", "吐司", "甜品", "蛋糕",
                  "盐面包", "酥皮", "烘焙", "bakery", "bread", "croissant", "bagel"}


def clean_anchor(s):
    s = (s or "").strip(" -•·▪️.")
    s = re.sub(r"^(图|P|p)\d+[\s\-—~至到]*\d*", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------- 加载库
def load_db():
    rests = C.fetch_all("restaurants",
                        "id,name,status,price_scene,price_band,score_taste,score_diner,review_count,district,address",
                        order_col="id")
    cuis = C.fetch_all("cuisines", "id,name,parent_category", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    # 面包标签子树
    name2id = {c["name"]: c["id"] for c in cuis}
    bread_root = name2id.get("面包")
    children = {c["id"] for c in cuis if c["parent_category"] == bread_root}
    bread_tags = {bread_root} | children
    rid_tags = defaultdict(set)
    for x in rc:
        rid_tags[x["restaurant_id"]].add(x["cuisine_id"])
    rbyid = {r["id"]: r for r in rests}
    # 库内 forms
    db = []
    for r in rests:
        full = re.split(r"[（(]", r["name"])[0].strip()
        forms = {C.cjk_norm(r["name"]), C.cjk_norm(full)}
        for seg in re.split(r"[·・•&]", full):
            s = C.cjk_norm(seg)
            if s and len(s) >= 2:
                forms.add(s)
        db.append({"id": r["id"], "name": r["name"], "status": r["status"], "full": full,
                   "forms": {f for f in forms if f and len(f) >= 2},
                   "has_bread_tag": bool(bread_tags & rid_tags.get(r["id"], set())),
                   "row": r})
    return db, rbyid


def match_db_anchor(anchor, db):
    """结构化锚点名 → 库内店（要求唯一且挂面包标签，或唯一强匹配）。"""
    na = C.cjk_norm(anchor)
    if not na or na in {C.cjk_norm(g) for g in GENERIC_ANCHOR}:
        return None
    exact = [d for d in db if na in d["forms"] or d["forms"] and any(f == na for f in d["forms"])]
    if exact:
        bread = [d for d in exact if d["has_bread_tag"]] or exact
        return bread[0] if len(bread) == 1 else None
    # 子串
    hits = [d for d in db if (len(na) >= 4 and na in C.cjk_norm(d["name"]))
            or (len(na) >= 4 and C.cjk_norm(d["full"]) in na)]
    bread = [d for d in hits if d["has_bread_tag"]]
    if len(bread) == 1:
        return bread[0]
    return None


def split_lines(t):
    return [l for l in (t or "").replace("\r", "").split("\n") if l.strip()]


def sents(t):
    t = (t or "").replace("\n", "。")
    return [s for s in re.split(r"[。！？!?；;]", t) if s.strip()]


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--category", default="bread")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rawp = pathlib.Path(args.raw)
    raw_files = [rawp]
    _anchor_f = rawp.parent / "raw_anchor.jsonl"
    if _anchor_f.exists() and _anchor_f != rawp:
        raw_files.append(_anchor_f)
    records = []
    for rf in raw_files:
        for line in rf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("kind") in ("discover", "anchor") and (not args.category or r.get("category") == args.category):
                    records.append(r)

    db, rbyid = load_db()
    alias2canon, short_alias = build_alias_map()
    # 已知名（品牌词典别名 + 库内 forms），未知专名提取时用于去重
    known_names = set(alias2canon)
    for dd in db:
        known_names.update(dd["forms"])
    leads = defaultdict(int)

    profiles = {}

    def get_brand(canon):
        if canon not in profiles:
            profiles[canon] = {
                "brand": canon, "rid": None, "in_db": False, "db_has_bread_tag": False,
                "status": "unknown", "compiler_voices": {},   # url/author -> 结构化描述
                "diner_voices": {},                          # 评论者/独立食客 key -> text
                "taste_vals": [], "items": set(), "has_negative": False,
                "sections": set(), "evidence": [], "promo": 0, "old_taste": None,
                "review_count": 0, "district": None, "address": None}
        return profiles[canon]

    def bind_db(brand, d):
        p = get_brand(brand)
        if d:
            p["rid"] = d["id"]; p["in_db"] = True
            p["db_has_bread_tag"] = d["has_bread_tag"]; p["status"] = d["status"]
            p["old_taste"] = d["row"].get("score_taste")
            p["review_count"] = d["row"].get("review_count")
            p["district"] = d["row"].get("district"); p["address"] = d["row"].get("address")

    def resolve_anchor_name(name):
        """锚点名 → (brand, db)。先品牌词典，再库内。"""
        na = C.cjk_norm(name)
        if not na:
            return None, None
        if na in alias2canon:
            return alias2canon[na], None
        # 别名作为子串（长别名）
        for al, canon in alias2canon.items():
            if len(al) >= 6 and (al in na or na in al):
                return canon, None
        d = match_db_anchor(name, db)
        if d:
            return d["full"], d
        # 未知名（看起来像品牌：含字母或≥3字且非品类词）
        if (re.search(r"[A-Za-z]", name) or len(na) >= 3) and na not in {C.cjk_norm(g) for g in GENERIC_ANCHOR}:
            return name.strip(), None
        return None, None

    for rec in records:
        for note in rec["notes"]:
            title, desc = note.get("title", ""), note.get("desc", "")
            author = (note.get("author") or "")[:20]
            url = note.get("url", "")
            is_promo_note = any(w in desc for w in PROMO_WORDS)
            cur_section = ""

            # ---- anchor（定向取证）：强制品牌，整篇正文作为一个整理者声音
            force_brand = ANCHOR_BRAND.get(rec["query"]) if rec.get("kind") == "anchor" else None
            if force_brand:
                pf = get_brand(force_brand)
                pf["sections"].add("面包")
                pf["compiler_voices"][f"{url}#{author}"] = re.sub(r"\s+", " ", desc).strip()[:200]
                tv = taste_raw(title + "。" + desc)
                if tv is not None:
                    pf["taste_vals"].append(tv)
                if has_neg_word(desc):
                    pf["has_negative"] = True
                for it in BAKED_ITEMS:
                    if it in desc or it in title:
                        pf["items"].add(it)

            # ---- 逐行找结构化锚点
            for line in split_lines(desc):
                sec = BREAD_SECTION.search(line)
                if sec and len(line) < 14:
                    cur_section = sec.group(1)
                m = RE_DASH.match(line)
                if m:
                    anchor, detail = clean_anchor(m.group(1)), m.group(2)
                    brand, d = resolve_anchor_name(anchor)
                    if brand:
                        p = get_brand(brand); bind_db(brand, d)
                        if cur_section:
                            p["sections"].add(cur_section)
                        vk = f"{url}#{author}"
                        p["compiler_voices"][vk] = detail.strip()[:200]
                        tv = taste_raw(detail)
                        if tv is not None:
                            p["taste_vals"].append(tv)
                        if has_neg_word(detail):
                            p["has_negative"] = True
                        for it in BAKED_ITEMS:
                            if it in detail or it in anchor:
                                p["items"].add(it)
                        if is_promo_note:
                            p["promo"] += 1
                        if len(p["evidence"]) < 8:
                            p["evidence"].append(f"{anchor}：{detail.strip()[:90]}")
                    continue
                for rx in (RE_PIN, RE_BAR, RE_NUM):
                    for mm in rx.finditer(line):
                        anchor = clean_anchor(mm.group(1))
                        if not anchor or C.cjk_norm(anchor) in {C.cjk_norm(g) for g in GENERIC_ANCHOR}:
                            continue
                        brand, d = resolve_anchor_name(anchor)
                        if brand:
                            p = get_brand(brand); bind_db(brand, d)
                            rest = line[mm.end():].strip()
                            p["compiler_voices"].setdefault(f"{url}#{author}", (rest or anchor)[:200])
                            tv = taste_raw(line)
                            if tv is not None:
                                p["taste_vals"].append(tv)
                            if has_neg_word(line):
                                p["has_negative"] = True
                            for it in BAKED_ITEMS:
                                if it in line:
                                    p["items"].add(it)

            # ---- 正文里的品牌词典补充（长别名自由匹配）
            body_nt = C.cjk_norm(title + desc)
            for al, canon in alias2canon.items():
                if len(al) >= 6 and al in body_nt:
                    p = get_brand(canon)
                    for s in sents(title + "。" + desc):
                        if al in C.cjk_norm(s):
                            tv = taste_raw(s)
                            if tv is not None:
                                p["taste_vals"].append(tv)
                            if has_neg_word(s):
                                p["has_negative"] = True
                            for it in BAKED_ITEMS:
                                if it in s:
                                    p["items"].add(it)

            # ---- 评论区：按评论者 name 计独立声音
            for c in note.get("comments") or []:
                cname = (c.get("name") or "").replace("作者", "").strip()
                ctext = (c.get("text") or "").strip()
                if not ctext or len(ctext) < 4:
                    continue
                cnt = C.cjk_norm(ctext)
                # 评论里提到的品牌（anchor 时初始为强制品牌；再先词典、库内）
                brands_here = {force_brand} if force_brand else set()
                for al, canon in alias2canon.items():
                    if (len(al) >= 4 and al in cnt) or (al in cnt and al not in short_alias):
                        brands_here.add(canon)
                if not brands_here:
                    d = None
                    for dd in db:
                        if dd["has_bread_tag"] and any(len(f) >= 4 and f in cnt for f in dd["forms"]):
                            brands_here.add(dd["full"]); d = dd
                    if d:
                        bind_db(d["full"], d)
                for brand in brands_here:
                    p = get_brand(brand)
                    if C.cjk_norm(cname) == C.cjk_norm(author) or "官方" in cname:
                        continue
                    key = f"cmt:{cname}:{url}"
                    if C.quote_has_substance(ctext) or taste_raw(ctext):
                        p["diner_voices"][key] = ctext[:200]
                        tv = taste_raw(ctext)
                        if tv is not None:
                            p["taste_vals"].append(tv)
                        if has_neg_word(ctext):
                            p["has_negative"] = True
                        for it in BAKED_ITEMS:
                            if it in ctext:
                                p["items"].add(it)

            # ---- 收集未知专名开放式线索（正文+评论，最长匹配）
            _alltext = title + "\n" + desc + "\n" + " ".join(
                c.get("text", "") for c in note.get("comments") or [])
            collect_leads(_alltext, known_names, leads)

    # ---------------------------------------------------------------- 门槛裁决
    def verdict(p):
        n_comp = len(p["compiler_voices"])
        n_diner = len(p["diner_voices"])
        tv = p["taste_vals"]
        avg = round(sum(tv) / len(tv), 2) if tv else None
        items = len(p["items"])
        is_bread = bool(p["sections"]) or p["db_has_bread_tag"] or items >= 1
        comp_authors = {k.split("#", 1)[1] for k in p["compiler_voices"]}
        independent_sources = len(comp_authors) + n_diner  # 整理者(去重) + 独立食客
        # 关店 / 营销 / 口味差
        if p["status"] == "closed":
            return "reject", "已关店", independent_sources, avg, items
        if avg is not None and avg < 3.3:
            return "reject", f"口味均分 {avg} 偏低", independent_sources, avg, items
        if not is_bread:
            return "reject", "非主营面包（排除跨品类噪声）", independent_sources, avg, items
        # admit：主营面包 + ≥2 独立声音（不能只有单一整理者）+ 招牌口感 + 正向
        if independent_sources >= 2 and items >= 1 and avg is not None and avg >= 3.5:
            if n_diner == 0 and len(comp_authors) == 1:
                return "hold", "仅单一博主整理、无独立食客交叉", independent_sources, avg, items
            tag = "admit" if p["has_negative"] else "admit*"
            tail = "" if p["has_negative"] else "（无差评交叉,全好评置信略降）"
            return tag, f"独立声音{independent_sources}(整理{len(comp_authors)}/食客{n_diner})、均分{avg}、招牌{items}{tail}", independent_sources, avg, items
        if independent_sources == 0:
            return "hold", "无真实食客声音（旧主观分不采信）", independent_sources, avg, items
        return "hold", f"独立声音{independent_sources}/均分{avg}/招牌{items}，证据不足", independent_sources, avg, items

    rows, counts = [], defaultdict(int)
    for p in profiles.values():
        v, why, src, avg, items = verdict(p)
        p["verdict"], p["why"] = v, why
        p["independent_sources"], p["avg_taste"], p["item_count"] = src, avg, items
        counts[v] += 1
        rows.append(p)

    def jsonable(p):
        q = dict(p)
        for k in ("items", "sections"):
            q[k] = sorted(q[k])
        q["compiler_voices"] = p["compiler_voices"]
        q["diner_voices"] = p["diner_voices"]
        return q

    out_path = args.out or str(pathlib.Path(args.raw).parent / f"candidates_{args.category}.jsonl")
    pathlib.Path(out_path).write_text(
        "\n".join(json.dumps(jsonable(p), ensure_ascii=False) for p in rows), encoding="utf-8")

    # ---------------------------------------------------------------- 打印
    print(f"发现笔记 {sum(len(r['notes']) for r in records)} 篇；品牌候选 {len(rows)} 个")
    print("裁决统计:", dict(counts))
    print("\n=== admit / admit*（够格收录）===")
    for p in sorted(rows, key=lambda x: -x["independent_sources"]):
        if p["verdict"].startswith("admit"):
            tag = "库内" if p["in_db"] else "新增"
            print(f"  [{tag}] {p['brand'][:26]:<28} 独立声音{p['independent_sources']} 均分{p['avg_taste']} 招牌{p['item_count']} {p['verdict']}")
    print("\n=== 用户点名店核对 ===")
    watch = {"Proust Moment": "proust", "Time & Flour(Flour Time)": "flourtime", "B+Baked": "bbaked",
             "L'Atelier Over Bakery": "over", "Orenda Bay": "orenda"}
    for label, w in watch.items():
        hit = [p for p in rows if w in C.cjk_norm(p["brand"]) or
               any(w in C.cjk_norm(a) for a in p.get("evidence", []))]
        if hit:
            for p in hit:
                print(f"  {label}: {p['brand']} -> {p['verdict']}（{p['why']}）")
        else:
            print(f"  {label}: 未在现有40篇出现（需补采集/换平台）")
    print("\n=== hold 数 / reject 数 ===")
    print(f"  hold={counts['hold']} reject={counts['reject']}；明细见 {out_path}")

    # ---------------------------------------------------------------- 未知线索（需锚定取证）
    lead_merged = merge_leads(dict(leads))
    lead_top = sorted(lead_merged.items(), key=lambda x: -x[1])
    leads_path = str(pathlib.Path(out_path).parent / f"leads_{args.category}.json")
    pathlib.Path(leads_path).write_text(
        json.dumps(lead_merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n=== 未知新店线索 TOP（不直接收录，需按店名锚定取证）===")
    for k, c in lead_top[:20]:
        print(f"  {k:<28} 提及{c}")
    print(f"\n输出: {out_path}\n线索: {leads_path}")


if __name__ == "__main__":
    main()

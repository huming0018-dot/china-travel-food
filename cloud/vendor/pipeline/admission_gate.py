#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""admission_gate.py v3 — 全品类社交声音聚合 + 收录门槛（离线、确定性、不耗浏览器）。

v3 在 v2（面包做精）基础上【参数化到任意品类】，使日料/面包跑通的方法论可回滚所有菜系：
  - 主营判定 / 招牌词 / 标签子树全部按 --category 动态生成（不再硬编码面包）；
  - 品类根标签子树来自 discovery_keywords.CUISINE_ROOT；
  - 招牌/食物信号 = 品类专属词 ∪ 通用食物词；
  - 门槛阈值不变（独立声音≥2、口味均分≥3.5、<3.3 淘汰、全好评 admit* 降置信）。

v2 关键修正（保留）：合集结构化锚点为主、品牌异写归一、评论者计独立声音、单一博主不构成收录。

用法：
  python3 admission_gate.py --raw <raw_discovery.jsonl> --category sichuan
  python3 admission_gate.py --raw ... --category bread
"""
import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

import common as C
import discovery_keywords as K

# ---------------------------------------------------------------- 口味
POS = {"好吃": .35, "正宗": .3, "惊艳": .4, "鲜嫩": .25, "入味": .25, "地道": .3, "值得": .2,
       "香": .15, "酥脆": .25, "弹": .2, "浓郁": .15, "回购": .25, "新鲜": .25, "爆汁": .3,
       "鲜美": .25, "嫩滑": .25, "层次": .15, "外脆里韧": .3, "必买": .25, "天花板": .25,
       "入口即化": .35, "必吃": .25, "封神": .3}
NEG = {"难吃": -.6, "避雷": -.5, "踩雷": -.5, "失望": -.4, "一般": -.3, "不好吃": -.55,
       "腥": -.35, "柴": -.35, "预制": -.4, "冷冻": -.3, "不新鲜": -.45, "太咸": -.25,
       "糊弄": -.4, "无味": -.4, "寡淡": -.3, "嚼不动": -.4, "名不副实": -.4, "怕了": -.15,
       "没记忆点": -.2, "两头不着": -.2, "平平无奇": -.25}
PROMO_WORDS = ("团购", "代金券", "套餐", "合作", "推广", "广告", "福利", "戳左下角",
               "购买链接", "招商", "加盟")

# 负面品牌硬清单：工业化连锁/预制/大众烘焙——即使独立声音≥2、均分≥3.5 也 reject。
# 匹配时经 normalize_brand_name 归一，故「苹果花园面包」「苹果花园」均命中。
NEGATIVE_BRANDS = {
    "苹果花园", "盖饭邦", "望湘园", "小菜园",
    "外婆家", "绿茶餐厅", "绿茶", "避风塘", "广州酒家", "点都德",
    "和府捞面", "遇见小面", "陈香贵", "马记永", "张拉拉",
    "西贝", "西贝莜面村", "眉州东坡", "俏江南", "小南国",
    "海底捞", "呷哺呷哺", "巴奴",
    "瑞幸", "luckin", "星巴克", "starbucks", "麦当劳", "mcdonald",
    "肯德基", "kfc", "必胜客", "pizzahut", "汉堡王", "burgerking",
    "85度C", "85度c", "85c", "巴黎贝甜", "parisbaguette",
    "好利来", "holiland", "味多美", "面包新语", "breadtalk",
    "元祖", "元祖食品", "克莉丝汀", "克里斯汀",
}
# 非正餐品类豁免连锁扣分（与前端隐藏连锁逻辑一致）
NON_MAIN_CATS = {"bread", "coffee", "bar", "dessert", "tea", "bistro", "bakery"}

# ---------------------------------------------------------------- 食物 / 招牌词
BAKED_ITEMS = ("可颂", "贝果", "酸种", "酸面包", "欧包", "吐司", "乡村", "全麦", "肉桂卷",
               "司康", "法棍", "恰巴塔", "佛卡夏", "丹麦", "菠萝包", "盐面包", "碱水",
               "生吐司", "酥皮", "牛角", "黑麦", "核桃", "布里欧", "戚风", "明太子", "苏打面包")
# 通用食物词（多字优先，避免单字误命中；覆盖各菜系主食/肉菜/甜品/饮品）
GENERIC_ITEMS = (
    "拉面", "乌冬", "荞麦面", "蘸面", "豚骨", "米粉", "河粉", "粿条", "米线", "炒饭", "盖饭",
    "便当", "定食", "饭团", "三明治", "汉堡", "披萨", "意面", "烩饭", "包子", "饺子", "馄饨",
    "锅贴", "生煎", "烧麦", "小笼", "汤圆", "春卷", "法包", "肉夹馍", "葱油饼", "烧饼",
    "烧鸟", "烤串", "烧肉", "烤肉", "和牛", "牛排", "猪排", "炸鸡", "鸡肉", "牛肉", "羊肉",
    "猪肉", "鸭肉", "海鲜", "鳗鱼", "天妇罗", "关东煮", "火锅", "辣子鸡", "回锅肉",
    "麻婆豆腐", "水煮鱼", "酸菜鱼", "烤鱼", "佛跳墙", "烧鹅", "烧腊", "点心", "虾饺", "肠粉",
    "牛肉丸", "卤味", "凉菜", "香肠", "咖喱", "冬阴功", "沙拉", "巴斯克", "提拉米苏", "慕斯",
    "布丁", "冰淇淋", "冰激凌", "刨冰", "舒芙蕾", "松饼", "可丽饼", "马卡龙", "泡芙", "奶油",
    "拿铁", "手冲", "美式", "奶茶", "鸡尾酒", "威士忌", "精酿", "抹茶", "和果子", "蛋挞",
    "糖水", "肉冻", "鹅肝", "蜗牛", "龙虾", "螃蟹", "生蚝", "三文鱼", "金枪鱼", "鸭肝",
    "ramen", "pho", "curry", "steak", "pizza", "pasta", "croissant", "bagel", "cake",
    "coffee", "cocktail", "tacos", "burger", "lobster", "crab", "salmon", "tuna", "toast",
    "brunch", "sourdough", "bakery", "noodle", "bbq",
)
# 品类专属额外食物词（在通用之外补充）
CATEGORY_ITEMS = defaultdict(tuple)


def item_words(cat):
    words = set(GENERIC_ITEMS)
    if cat == "bread":
        words |= set(BAKED_ITEMS)
    for x in CATEGORY_ITEMS.get(cat, ()):
        words.add(x)
    spec = K.CATEGORY_SPEC.get(cat, {})
    for s in spec.get("subs", []):
        if len(s) >= 2:
            words.add(s)
    return words


BREAD_SECTION = re.compile(r"(可颂|酥皮|盐面包|欧包|酸面?包|贝果|吐司|日式|面包|烘焙|bagel|croissant|sourdough|bakery)")


def section_regex(cat):
    if cat == "bread":
        return BREAD_SECTION
    spec = K.CATEGORY_SPEC.get(cat, {})
    words = list(spec.get("names", [])) + list(spec.get("ens", []))
    words += [s for s in spec.get("subs", []) if len(s) >= 3][:8]
    words = sorted(set(words), key=len, reverse=True)
    pat = "|".join(re.escape(w) for w in words if w)
    return re.compile(pat, re.I) if pat else None


# 定向取证搜索词 → 规范品牌（仅面包需要；其余品类为空）
ANCHOR_BRAND = {"Orenda Bay": "Orenda Bay", "Time & Flour": "Flour Time",
                "时光 面粉 面包": "Flour Time"}

# ---------------------------------------------------------------- 品牌异写词典
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


# ---------------------------------------------------------------- 未知英文专名
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
           "up", "out", "into", "about", "more", "also", "just", "one", "no", "yes", "go",
           "hidden", "spot"}
_EN = re.compile(r"[A-Za-z][A-Za-z0-9'&+.\-]{1,30}(?:\s+[A-Za-z0-9'&+.\-]{1,30}){0,5}")


def collect_leads(text, known, leads):
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
    keys = sorted(leads, key=lambda x: -len(x))
    keep = {}
    for k in keys:
        longer = [L for L in keep if k in L]
        if longer:
            keep[longer[0]] += leads[k]
        else:
            keep[k] = keep.get(k, 0) + 1
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
RE_DASH = re.compile(r"^\s*[-•·▪️◦]?\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,22}?)\s*[:：]\s*(.+)$")
RE_PIN = re.compile(r"📍\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,22})")
RE_BAR = re.compile(r"([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,18}?)\s*丨\s*")
RE_NUM = re.compile(r"(?:^|\s)(?:[①-⑳㉑-㉟]|\d{1,2}[.、)]|\d️⃣)\s*([A-Za-z一-龥][A-Za-z一-龥'&+.・\s]{0,20}?)(?:[:：]|\s{2,}|$)")
GENERIC_ANCHOR = {"面包", "面包店", "可颂", "贝果", "欧包", "酸种", "吐司", "甜品", "蛋糕",
                  "盐面包", "酥皮", "烘焙", "bakery", "bread", "croissant", "bagel", "餐厅",
                  "饭店", "美食", "大家", "指数", "店铺"}


def clean_anchor(s):
    s = (s or "").strip(" -•·▪️.")
    s = re.sub(r"^(图|P|p)\d+[\s\-—~至到]*\d*", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


# ---------------------------------------------------------------- 加载库
def load_db(category):
    root_name = K.CUISINE_ROOT.get(category)
    rests = C.fetch_all("restaurants",
                        "id,name,status,score_taste,score_diner,review_count,district,address",
                        order_col="id")
    cuis = C.fetch_all("cuisines", "id,name,parent_category", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    name2id = {c["name"]: c["id"] for c in cuis}
    root_id = name2id.get(root_name)
    children = {c["id"] for c in cuis if c["parent_category"] == root_id}
    tagset = ({root_id} | children) if root_id is not None else set()
    rid_tags = defaultdict(set)
    for x in rc:
        rid_tags[x["restaurant_id"]].add(x["cuisine_id"])
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
                   "has_cat_tag": bool(tagset & rid_tags.get(r["id"], set())),
                   "row": r})
    return db


def match_db_anchor(anchor, db):
    na = C.cjk_norm(anchor)
    if not na or na in {C.cjk_norm(g) for g in GENERIC_ANCHOR}:
        return None
    exact = [d for d in db if na in d["forms"] or d["forms"] and any(f == na for f in d["forms"])]
    if exact:
        tagged = [d for d in exact if d["has_cat_tag"]] or exact
        return tagged[0] if len(tagged) == 1 else None
    hits = [d for d in db if (len(na) >= 4 and na in C.cjk_norm(d["name"]))
            or (len(na) >= 4 and C.cjk_norm(d["full"]) in na)]
    tagged = [d for d in hits if d["has_cat_tag"]]
    if len(tagged) == 1:
        return tagged[0]
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
    category = K.normalize_category(args.category)

    rawp = pathlib.Path(args.raw)
    raw_files = [rawp]
    _af = rawp.parent / "raw_anchor.jsonl"
    if _af.exists() and _af != rawp:
        raw_files.append(_af)
    records = []
    for rf in raw_files:
        for line in rf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("kind") in ("discover", "anchor") and r.get("category") == category:
                    records.append(r)

    db = load_db(category)
    alias2canon, short_alias = build_alias_map()
    known_names = set(alias2canon)
    for dd in db:
        known_names.update(dd["forms"])
    leads = defaultdict(int)
    _NEG_NORM = {C.normalize_brand_name(b) for b in NEGATIVE_BRANDS}
    items_set = item_words(category)
    sec_re = section_regex(category)
    profiles = {}

    def get_brand(canon):
        key = C.normalize_brand_name(canon)
        if key not in profiles:
            profiles[key] = {
                "brand": canon, "rid": None, "in_db": False, "db_has_cat_tag": False,
                "status": "unknown", "compiler_voices": {}, "diner_voices": {},
                "taste_vals": [], "items": set(), "has_negative": False,
                "sections": set(), "evidence": [], "promo": 0, "review_count": 0,
                "aliases": set()}
        p = profiles[key]
        p["aliases"].add(canon)
        # 显示名取最短写法（MBD 优先于 MBD面包）
        if len(canon) < len(p["brand"]):
            p["brand"] = canon
        return p

    def bind_db(brand, d):
        p = get_brand(brand)
        if d:
            p["rid"] = d["id"]; p["in_db"] = True
            p["db_has_cat_tag"] = d["has_cat_tag"]; p["status"] = d["status"]
            p["review_count"] = d["row"].get("review_count")

    def resolve_anchor_name(name):
        na = C.cjk_norm(name)
        if not na:
            return None, None
        if na in alias2canon:
            return alias2canon[na], None
        for al, canon in alias2canon.items():
            if len(al) >= 6 and (al in na or na in al):
                return canon, None
        d = match_db_anchor(name, db)
        if d:
            return d["full"], d
        if (re.search(r"[A-Za-z]", name) or len(na) >= 3) and \
           na not in {C.cjk_norm(g) for g in GENERIC_ANCHOR}:
            ok, _reason = C.looks_like_brand(name)
            if ok:
                return name.strip(), None
            return None, None  # 菜名/路名/泛词/元话术 → 不建 profile
        return None, None

    _SHOP_END = re.compile(r"[店坊馆苑屋堂房铺室社家行记]$")

    def pin_name(raw):
        """📍 后店名常带空格再接描述。逐级缩短前缀只认词典/库，再退回中文后缀前导词。"""
        parts = raw.strip().split()
        for cut in range(len(parts)):
            cand = " ".join(parts[:len(parts) - cut]).strip()
            na = C.cjk_norm(cand)
            if not na:
                continue
            if na in alias2canon:
                return alias2canon[na], None
            hit = [canon for al, canon in alias2canon.items()
                   if len(al) >= 6 and (al in na or na in al)]
            if hit:
                return hit[0], None
            d = match_db_anchor(cand, db)
            if d:
                return d["full"], d
        head = parts[0] if parts else raw.strip()
        if _SHOP_END.search(head):
            return head, None
        if len(parts) == 1 and re.fullmatch(r"[一-龥]{3,}", head):
            ok, _r = C.looks_like_brand(head)
            if ok:
                return head, None
        return None, None

    def collect_items(p, *texts):
        for t in texts:
            for it in items_set:
                if it in t:
                    p["items"].add(it)

    out_of_sh = 0
    for rec in records:
        for note in rec["notes"]:
            title, desc = note.get("title", ""), note.get("desc", "")
            # 城市闸门：正文明确外地且无上海证据 → 整篇丢弃
            if C.note_is_out_of_shanghai(title, desc):
                out_of_sh += 1
                continue
            author = (note.get("author") or "")[:20]
            url = note.get("url", "")
            is_promo_note = any(w in desc for w in PROMO_WORDS)
            cur_section = ""

            force_brand = ANCHOR_BRAND.get(rec["query"]) if (
                rec.get("kind") == "anchor" and category == "bread") else None
            if force_brand:
                pf = get_brand(force_brand)
                pf["sections"].add(category)
                pf["compiler_voices"][f"{url}#{author}"] = re.sub(r"\s+", " ", desc).strip()[:200]
                tv = taste_raw(title + "。" + desc)
                if tv is not None:
                    pf["taste_vals"].append(tv)
                if has_neg_word(desc):
                    pf["has_negative"] = True
                collect_items(pf, desc, title)

            for line in split_lines(desc):
                if sec_re and len(line) < 14:
                    sm = sec_re.search(line)
                    if sm:
                        cur_section = sm.group(0)
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
                        collect_items(p, detail, anchor)
                        if is_promo_note:
                            p["promo"] += 1
                        if len(p["evidence"]) < 8:
                            p["evidence"].append(f"{anchor}：{detail.strip()[:90]}")
                    continue
                for mm in RE_PIN.finditer(line):
                    brand, d = pin_name(mm.group(1))
                    if brand:
                        p = get_brand(brand); bind_db(brand, d)
                        if cur_section:
                            p["sections"].add(cur_section)
                        rest = line[mm.end():].strip()
                        p["compiler_voices"].setdefault(f"{url}#{author}",
                                                        (rest or brand)[:200])
                        tv = taste_raw(line)
                        if tv is not None:
                            p["taste_vals"].append(tv)
                        if has_neg_word(line):
                            p["has_negative"] = True
                        collect_items(p, line)
                for rx in (RE_BAR, RE_NUM):
                    for mm in rx.finditer(line):
                        anchor = clean_anchor(mm.group(1))
                        if not anchor or C.cjk_norm(anchor) in {
                                C.cjk_norm(g) for g in GENERIC_ANCHOR}:
                            continue
                        brand, d = resolve_anchor_name(anchor)
                        if brand:
                            p = get_brand(brand); bind_db(brand, d)
                            rest = line[mm.end():].strip()
                            p["compiler_voices"].setdefault(f"{url}#{author}",
                                                            (rest or anchor)[:200])
                            tv = taste_raw(line)
                            if tv is not None:
                                p["taste_vals"].append(tv)
                            if has_neg_word(line):
                                p["has_negative"] = True
                            collect_items(p, line)

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
                            collect_items(p, s)

            for c in note.get("comments") or []:
                cname = (c.get("name") or "").replace("作者", "").strip()
                ctext = (c.get("text") or "").strip()
                if not ctext or len(ctext) < 4:
                    continue
                cnt = C.cjk_norm(ctext)
                brands_here = {force_brand} if force_brand else set()
                for al, canon in alias2canon.items():
                    if (len(al) >= 4 and al in cnt) or (al in cnt and al not in short_alias):
                        brands_here.add(canon)
                if not brands_here:
                    for dd in db:
                        if dd["has_cat_tag"] and any(len(f) >= 4 and f in cnt for f in dd["forms"]):
                            brands_here.add(dd["full"])
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
                        collect_items(p, ctext)

            _alltext = title + "\n" + desc + "\n" + " ".join(
                c.get("text", "") for c in note.get("comments") or [])
            collect_leads(_alltext, known_names, leads)

    # ---------------------------------------------------------------- 裁决
    def verdict(p):
        n_comp = len(p["compiler_voices"])
        n_diner = len(p["diner_voices"])
        tv = p["taste_vals"]
        avg = round(sum(tv) / len(tv), 2) if tv else None
        items = len(p["items"])
        is_cat = bool(p["sections"]) or p["db_has_cat_tag"] or items >= 1
        comp_authors = {k.split("#", 1)[1] for k in p["compiler_voices"]}
        independent_sources = len(comp_authors) + n_diner
        if p["status"] == "closed":
            return "reject", "已关店", independent_sources, avg, items
        # 负面品牌硬闸门：连锁/预制/大众烘焙，命中即 reject（非正餐品类不额外扣）
        if C.normalize_brand_name(p["brand"]) in _NEG_NORM:
            return "reject", "negative_brand（工业化连锁/预制，不进精选）", independent_sources, avg, items
        if avg is not None and avg < 3.3:
            return "reject", f"口味均分 {avg} 偏低", independent_sources, avg, items
        if not is_cat:
            return "reject", "非本品类（排除跨品类噪声）", independent_sources, avg, items
        if independent_sources >= 2 and items >= 1 and avg is not None and avg >= 3.5:
            if n_diner == 0 and len(comp_authors) == 1:
                return "hold", "仅单一博主整理、无独立食客交叉", independent_sources, avg, items
            tag = "admit" if p["has_negative"] else "admit*"
            tail = "" if p["has_negative"] else "（无差评交叉,全好评置信略降）"
            return tag, (f"独立声音{independent_sources}(整理{len(comp_authors)}/食客{n_diner})、"
                         f"均分{avg}、招牌{items}{tail}"), independent_sources, avg, items
        if independent_sources == 0:
            return "hold", "无真实食客声音（旧主观分不采信）", independent_sources, avg, items
        return "hold", f"独立声音{independent_sources}/均分{avg}/招牌{items}，证据不足", \
            independent_sources, avg, items

    rows, counts = [], defaultdict(int)
    for p in profiles.values():
        v, why, src, avg, items = verdict(p)
        p["verdict"], p["why"] = v, why
        p["independent_sources"], p["avg_taste"], p["item_count"] = src, avg, items
        counts[v] += 1
        rows.append(p)

    def jsonable(p):
        q = dict(p)
        for k in ("items", "sections", "aliases"):
            if k in q and isinstance(q[k], set):
                q[k] = sorted(q[k])
        return q

    out_path = args.out or str(pathlib.Path(args.raw).parent / f"candidates_{category}.jsonl")
    pathlib.Path(out_path).write_text(
        "\n".join(json.dumps(jsonable(p), ensure_ascii=False) for p in rows), encoding="utf-8")

    print(f"发现笔记 {sum(len(r['notes']) for r in records)} 篇（外地丢弃 {out_of_sh}）；品牌候选 {len(rows)} 个")
    print("裁决统计:", dict(counts))
    print("\n=== admit / admit*（够格收录）===")
    for p in sorted(rows, key=lambda x: -x["independent_sources"]):
        if p["verdict"].startswith("admit"):
            tag = "库内" if p["in_db"] else "新增"
            print(f"  [{tag}] {p['brand'][:26]:<28} 独立声音{p['independent_sources']} "
                  f"均分{p['avg_taste']} 招牌{p['item_count']} {p['verdict']}")
    if category == "bread":
        print("\n=== 用户点名店核对 ===")
        watch = {"Proust Moment": "proust", "Time & Flour(Flour Time)": "flourtime",
                 "B+Baked": "bbaked", "L'Atelier Over Bakery": "over", "Orenda Bay": "orenda"}
        for label, w in watch.items():
            hit = [p for p in rows if w in C.cjk_norm(p["brand"])
                   or any(w in C.cjk_norm(a) for a in p.get("evidence", []))]
            if hit:
                for p in hit:
                    print(f"  {label}: {p['brand']} -> {p['verdict']}（{p['why']}）")
            else:
                print(f"  {label}: 未在现有笔记出现（需补采集/换平台）")
    print(f"\nhold={counts['hold']} reject={counts['reject']}；明细见 {out_path}")

    lead_merged = merge_leads(dict(leads))
    leads_path = str(pathlib.Path(out_path).parent / f"leads_{category}.json")
    pathlib.Path(leads_path).write_text(
        json.dumps(lead_merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print("未知新店线索 TOP（不直接收录，需按店名锚定取证）:")
    for k, c in sorted(lead_merged.items(), key=lambda x: -x[1])[:12]:
        print(f"  {k:<28} 提及{c}")
    print(f"\n输出: {out_path}\n线索: {leads_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw_xhs.jsonl -> raw_reviews.jsonl  (v4)

治四类错锚（在 v3 核心专名召回 + 分店冲突基础上）：
1. **合集/攻略笔记不锚单一店**：正文出现≥2个非参照店名、或≥2处"地址："→ 判合集，
   不挂到其中某一家（登记 unmatched:合集），其评论也不归属。
2. **评论独立过滤，不一刀切归主体**：评论提到他店→弃；出现"本地/当地/老家/来X吃"等
   外地信号→弃；疑问/互动/作者本人→弃；只有围绕主体且有口味信号才归主体。
3. **对比参照物不作主体**："还是X最好吃/不如X/没X好吃/比X"里的 X 是参照，不锚。
4. 核心专名（·第一段/去后缀，如 桂山禾）命中且库内唯一才采信；"新店/PLUS"降 mid。
口味情感为确定性整数 1-5，无口味信号不打分。
"""
import sys, json, re, pathlib
SP = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SP)
import common as C

base = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"
raw_p = base + "/research/atlas/xhs/raw_xhs.jsonl"
out_p = base + "/research/atlas/xhs/raw_reviews.jsonl"
unmatched_p = base + "/research/atlas/xhs/unmatched_shops.jsonl"

rests = C.fetch_all("restaurants", "id,name,status,district")
def norm(s):
    # 统一跨字形归一（繁简 + 日文汉字 → 简体），治 和菓子↔和果子 / 寛↔宽 / 本舖↔本铺
    return C.cjk_norm(s)
def strip_branch(s):
    return re.sub(r"（.*?）|\(.*?\)", "", s or "").strip()

_GEO = ("上海|北京|武汉|四川|重庆|成都|广州|湖南|湖北|河南|江苏|浙江|云南|贵州|安徽|山东|"
        "福建|广东|陕西|新疆|西藏|青海|甘肃|江西|广西|海南|宁夏|辽宁|吉林|黑龙江|内蒙古|"
        "绵阳|泸州|宜宾|自贡|潮汕|潮州|顺德|客家|港式|温州|杭州|宁波|无锡|南京|苏州|常州|"
        "绍兴|嘉兴|金华|台州|镇江|扬州|徐州|盐城|淮安|连云港|奉贤|淮南")
_CAT = ["绵阳米粉","热干面","水煎包","米粉","川味","寿司","拉面","烧肉","咖喱","咖啡","面馆",
        "牛肉","烤肉","烧烤","火锅","饺子","包子","甜品","料理","食研","小馆","酒馆","餐室",
        "餐厅","饭店","酒楼","酒家","老铺","饼","饭","面","汤"]
_CAT_EXTRA = ["铜锣烧","胡辣汤","卤菜","牛肉汤","牛肉面","冰浆","糖水","小笼","生煎","锅贴",
              "烧麦","汤圆","烧饼","葱油饼","可丽饼","薄饼","三明治","贝果","酸种","可颂",
              "起酥","蛋糕","布丁","果冻","麻薯","鲷鱼烧","和果子","抹茶","冰淇淋","冰激凌",
              "刨冰","松饼","甜汤","法式甜品","乌冬","荞麦","烧鸟","天妇罗","鳗鱼","寿喜烧",
              "铁板","炉端","居酒屋","怀石","洋食","盖饭","便当","定食","釜饭","粉"]
_CAT_ALL = sorted(set(_CAT + _CAT_EXTRA), key=len, reverse=True)

def _clean_seg(seg):
    s = re.sub(_GEO, "", seg)
    for w in _CAT_ALL:
        s = s.replace(w, "")
    return re.sub(r"[·・•\s]+", "", s).strip()

def brand_forms(full):
    full = strip_branch(full)
    forms = {full}
    m = re.search(r"([一-龥A-Za-z0-9]{1,4}记)", full)
    if m:
        forms.add(m.group(1))
    for seg in re.split(r"[·・•]+", full):
        s = _clean_seg(seg.strip())
        if s and len(s) >= 2:
            forms.add(s)
    s = _clean_seg(full)
    if s and len(s) >= 2:
        forms.add(s)
    # 统一 cjk 归一并去重
    out = set()
    for f in forms:
        cf = norm(f)
        if cf and len(cf) >= 2 and cf not in _CAT_ALL:
            out.add(cf)
    # 去尾部系列名的品牌主体前缀（和果子本铺四叶→和果子本铺）；core_unique 护栏防宽泛误锚
    fullc = norm(full)
    for cut in (1, 2, 3):
        if len(fullc) - cut >= 4:
            out.add(fullc[:-cut])
    return sorted(out)

def head_token(name):
    full = strip_branch(name)
    seg = re.split(r"[·・•]", full)[0]
    s = _clean_seg(seg)
    return s or seg

# 预计算每店元信息，加速
RMD = []
for r in rests:
    RMD.append({"id": r["id"], "name": r["name"], "status": r["status"],
                "full": strip_branch(r["name"]), "ht": head_token(r["name"]),
                "forms": brand_forms(r["name"])})

def match_id(name):
    if not name:
        return None
    target = norm(name)
    exact = [m for m in RMD if norm(m["name"]) == target]
    if exact:
        act = [x for x in exact if x["status"] == "active"] or exact
        return act[0]["id"]
    core = norm(strip_branch(name))[:6]
    if len(core) < 2:
        return None
    hits = [m for m in RMD if core in norm(m["name"])]
    if len(hits) == 1:
        return hits[0]["id"]
    return None

def core_unique(core, rid):
    hits = [m for m in RMD if norm(core) in norm(m["name"])]
    return len(hits) == 1 and hits[0]["id"] == rid

MALLS = sorted(set(["国贸汇","ITC","itc","美罗城","静安大悦城","大悦城","港汇恒隆","港汇",
    "恒隆广场","恒隆","来福士","万象城","太古汇","环球港","正大广场","正大","国金中心","国金",
    "IFC","ifc","环贸","IAPM","iapm","合生汇","龙之梦","万象天地","天安千树","今潮8弄","新天地",
    "七宝万科","万达广场","万达","大宁国际","久光","仲盛","印象城","嘉亭荟","又一城","宝龙城",
    "前滩太古里","太古里","兴业太古汇","张园","丰盛里","上海中心","金茂"]), key=len, reverse=True)
def branch_malls(name):
    found = []
    for p in re.findall(r"[（(]([^）)]+)[）)]", name):
        found += [x for x in MALLS if x in p]
    return found
def mall_conflict(text, rec_name):
    tm = branch_malls(rec_name)
    if not tm:
        return False, []
    nm = [x for x in MALLS if x in text]
    extra = [x for x in nm if not any(x == t or x in t or t in x for t in tm)]
    return bool(extra), extra

# 对比参照："还是X最好吃 / 不如X / 没X好吃 / 比X"
_REF_PAT = [r"还是([^，。！？\s、]{2,10}?)(?:最好吃|最好|最正|好吃|正宗|靠谱)",
            r"不如([^，。！？\s、]{2,10})",
            r"没有([^，。！？\s、]{2,10})好吃",
            r"没([^，。！？\s、]{2,10})好吃"]
def ref_groups(text):
    g = set()
    for p in _REF_PAT:
        for mm in re.finditer(p, text):
            if mm.group(1):
                g.add(norm(mm.group(1)))
    return g

class M:
    def __init__(s, d, score, is_ref):
        s.id, s.name, s.score, s.is_ref = d["id"], d["name"], score, is_ref

def shops_mentioned(text):
    refs = ref_groups(text)
    nt = norm(text)
    out = []
    for d in RMD:
        score = 0
        if d["full"] and len(d["full"]) >= 3 and d["full"] in text:
            score = 3
        elif d["full"] and len(norm(d["full"])) >= 3 and norm(d["full"]) in nt:
            score = 2
        elif d["ht"] and len(norm(d["ht"])) >= 2 and (d["ht"] in text or norm(d["ht"]) in nt):
            score = 1
        if not score:
            continue
        isref = bool(d["full"]) and any(
            g and (g in norm(d["full"]) or norm(d["full"])[:4] in g) for g in refs)
        out.append(M(d, score, isref))
    return sorted(out, key=lambda z: -z.score)

_TITLE_ROUNDUP = re.compile(
    r"VS|vs|PK|pk|对决|横评|比拼|巨头|哪家强|红黑榜|排行|排名|合集|盘点|\d+家|\d+碗|\d+家店")
_CIRCLED = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚")
def is_roundup(title, text, mentioned):
    # 标题定性（PK/对决/排行/盘点/N家/N碗）→ 必然多店
    if _TITLE_ROUNDUP.search(title or ""):
        return True
    nonref = [x for x in mentioned if not x.is_ref]
    # 完整提到店名(score>=2)≥2 才算多店；score1 弱命中不计
    if len([x for x in nonref if x.score >= 2]) >= 2:
        return True
    if len(re.findall(r"地址[：:]", text)) >= 2:
        return True
    # 圈号编号列表 ≥3（①②③…）
    if len(set(ch for ch in text if ch in _CIRCLED)) >= 3:
        return True
    # 多行数字/中文编号 ≥3
    if len(re.findall(r"(?m)^\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])", text)) >= 3:
        return True
    return False

NEW_SHOP = re.compile(r"新店|PLUS|plus|首店|二店|2店|新开")
def anchor_note(note, rec_name):
    text = note.get("title", "") + "\n" + note.get("desc", "")
    mm = re.search(r"商家[：:]\s*([^\n，。#]+)", note.get("desc", ""))
    if mm:
        rid = match_id(mm.group(1).strip())
        if rid:
            return rid, "显式商家"
    mentioned = shops_mentioned(text)
    nonref = [x for x in mentioned if not x.is_ref]
    rec_rid = match_id(rec_name)
    if rec_rid:
        conf, extra = mall_conflict(text, rec_name)
        if conf:
            return None, "分店冲突:" + "/".join(extra)
    if is_roundup(note.get("title", ""), text, mentioned):
        return None, "合集"
    if rec_rid:
        d0 = next(x for x in RMD if x["id"] == rec_rid)
        rec_core = strip_branch(rec_name)
        nt = norm(text)
        if norm(rec_core) in nt:
            return rec_rid, "搜索目标在正文"
        for bf in d0["forms"]:
            bfc = norm(bf)
            if bfc in nt and core_unique(bfc, rec_rid):
                if NEW_SHOP.search(text) and re.search(r"[（(]", rec_name):
                    return rec_rid, "核心专名(新店待核)"
                return rec_rid, "核心专名:" + bf
    if len(nonref) == 1 and nonref[0].score >= 2:
        return nonref[0].id, "唯一主角:" + nonref[0].name
    return None, "库内无此店"

QUESTION = re.compile(
    r"[?？]|想问|吗\b|么\b|嘛\b|请问|在哪|哪里|哪家|哪个|求问|求安利|求坐标|求地址|求个|"
    r"有人知道|是不是|对不对|好吃吗|正宗吗|真的吗|怎么样|哪家平台|什么菜|哪一家")
def is_question(t):
    return bool(QUESTION.search(t))

OUT_TOWN = re.compile(r"当地|本地|老家|原产地|来[一-龥]{1,4}(?:吃|当地|本地)|去[一-龥]{1,4}吃")
# 评论捧他店：隔壁/旁边/对面的XX好吃、XX好吃一百倍（情感对象是他店，不作为主体评价）
PRAISE_OTHER = re.compile(
    r"(?:隔壁|旁边|对面|斜对面|楼上下|附近)[^，。！？]{0,10}(?:好吃|香|正宗|更强|更好)|"
    r"[^，。！？]{2,8}(?:好吃|香|正宗)(?:一百倍|好多倍|得多|太多)")
# 合集编号评论：p1/p2、①②、第N家（合集正文已不锚，双保险，避免编号评论串店）
ROUNDUP_CMT = re.compile(r"(?i)\bp?\d{1,2}[\s.、]|[①②③④⑤⑥⑦⑧⑨⑩]|第[一二三四五六七八九十\d]{1,3}家")

POS = {"好吃":.35,"正宗":.3,"惊艳":.4,"鲜嫩":.25,"入味":.25,"地道":.3,"值得":.2,"香":.15,
       "酥脆":.25,"弹":.2,"浓郁":.15,"回购":.25,"必吃":.25,"天花板":.3,"封神":.3,
       "新鲜":.25,"入口即化":.35,"爆汁":.3,"鲜美":.25,"嫩滑":.25}
NEG = {"难吃":-.6,"避雷":-.5,"踩雷":-.5,"失望":-.4,"一般":-.3,"不好吃":-.55,"腥":-.35,
       "柴":-.35,"预制":-.4,"冷冻":-.3,"不新鲜":-.45,"太咸":-.25,"油腻":.3,"糊弄":-.4,
       "无味":-.4,"寡淡":-.3,"嚼不动":-.4}
def taste_sent(text):
    pos = sum(w for k, w in POS.items() if k in text)
    neg = sum(w for k, w in NEG.items() if k in text)
    if pos == 0 and neg == 0:
        return None, None
    raw = max(1.0, min(5.0, round(3.8 + pos + neg, 1)))
    return max(1, min(5, int(raw + 0.5))), raw

def clean_content(t):
    t = re.sub(r"#\S+", "", t or "")
    t = t.replace("\t", " ").replace("\u200b", " ")
    return re.sub(r"\n{2,}", "\n", t).strip()

def same_person(a, b):
    return norm(a) and norm(a) == norm(b)

def parse_note_date(d):
    """笔记日期 → ISO date string (YYYY-MM-DD) 或 None。
    格式：'2024-05-05' / '编辑于 01-19' / '04-13'。"""
    if not d:
        return None
    d = d.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{2})-(\d{2})", d)
    if m:
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            import datetime
            now = datetime.date.today()
            yr = now.year
            if mm > now.month or (mm == now.month and dd > now.day):
                yr -= 1
            return f"{yr}-{mm:02d}-{dd:02d}"
    return None

reviews, unmatched = [], []
for line in open(raw_p, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    rec = json.loads(line)
    for note in rec["notes"]:
        rid, reason = anchor_note(note, rec["name"])
        author = (note.get("author") or "")[:20]
        body = clean_content(note.get("desc", ""))
        if rid is None:
            unmatched.append({"search_name": rec["name"], "note_title": note.get("title"),
                              "note_url": note.get("url"), "guess": note.get("title", "")[:30],
                              "reason": reason})
        else:
            if not re.search(r"文[｜|]|编辑[｜|]|记者|图文制作|商业思维|商业模式", note.get("desc", "")) \
               and len(body) >= 8 and C.quote_has_substance(body) and not is_question(body):
                a, raw = taste_sent(body)
                vd = parse_note_date(note.get("date"))
                if a is not None:  # 无口味信号的定位/品牌/合集内容不进口味库
                    trust = "mid" if "新店待核" in reason else "high"
                    rev = {"restaurant_id": rid, "author_name": author,
                        "source_platform": "小红书", "source_url": note.get("url"), "content": body,
                        "review_kind": "diner", "is_verified_diner": True, "trust_level": trust,
                        "aspect_taste": a, "aspect_json": {"taste_raw": raw}}
                    if vd:
                        rev["visit_date"] = vd
                    reviews.append(rev)
        # 评论：仅单一主体笔记处理；独立过滤他店/外地/疑问
        if rid:
            for c in note.get("comments", []):
                ct = clean_content(c.get("text", ""))
                cname = (c.get("name") or "").strip()
                if len(ct) < 4 or is_question(ct) or same_person(cname, author):
                    continue
                if not C.quote_has_substance(ct) or OUT_TOWN.search(ct):
                    continue
                if PRAISE_OTHER.search(ct) or ROUNDUP_CMT.search(ct):
                    continue
                cmen = shops_mentioned(ct)
                other = [x for x in cmen if x.id != rid and not x.is_ref]
                if other:
                    continue  # 评论讲他店，不挂主体
                a, raw = taste_sent(ct)
                if a is None:
                    continue
                vd = parse_note_date(note.get("date"))
                rev = {"restaurant_id": rid, "author_name": (cname or "小红书用户")[:20],
                    "source_platform": "小红书", "source_url": note.get("url"), "content": ct,
                    "review_kind": "diner", "is_verified_diner": True, "trust_level": "mid",
                    "aspect_taste": a, "aspect_json": {"taste_raw": raw}}
                if vd:
                    rev["visit_date"] = vd
                reviews.append(rev)

pathlib.Path(out_p).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in reviews), encoding="utf-8")
pathlib.Path(unmatched_p).write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in unmatched), encoding="utf-8")
print("生成 reviews:", len(reviews), "| 未锚笔记:", len(unmatched))
from collections import Counter
print("按店分布:", dict(Counter(x["restaurant_id"] for x in reviews)))
print("有口味分:", sum(1 for x in reviews if x["aspect_taste"] is not None))
for x in unmatched:
    print("  unmatched:", x["search_name"], "=>", (x["note_title"] or "")[:24], "|", x["reason"])

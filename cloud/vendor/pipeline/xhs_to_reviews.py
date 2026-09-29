#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw_xhs.jsonl -> raw_reviews.jsonl  (v5)

v5 修复"低产：真实单店评论被大量误丢"（一批 417 行仅 +14）：
A. 匹配归一化升级 SQ：在 cjk_norm 基础上去掉所有空白/分隔符/标点，并补 CJK-only、
   Latin-only 品牌核心 —— 修"炎珀EMBER / 炎珀 EMBER / EMBER"因空格或拉丁边界匹配失败。
B. 合集判定证据化：
   - 高置信（≥2 个完整非参照店名 / ≥2 个地址块 / ≥3 个"含门店或地址的编号或圈号"）→ 合集；
   - 标题强词（合集/盘点/排行/N家/横评…）需有任意多店佐证才判；弱词（VS/PK/N碗…）同样需佐证；
   - 纯步骤/高亮编号（1.预约 2.点单）不含门店地址 → 不再误判合集。
其余（评论独立过滤、对比参照、口味整数分、日期解析、宁空不假）沿用 v4。
"""
import os, sys, json, re, pathlib, fcntl

PIPE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))
import common as C

# 单实例锁：relay/手动并发时后来者直接退出，避免 2 核机器上互相抢 CPU
_lk = open("/tmp/xhs_to_reviews.lock", "w")
try:
    fcntl.flock(_lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("另一个 xhs_to_reviews 正在运行，本次跳过")
    sys.exit(0)

# 数据目录自适应：容器 /app/data；本地各机回落到项目根
_cands = [os.environ.get("FOOD_DATA_DIR"), "/app/data",
          "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food",
          "/Users/deuce/Doubao/chats/2026-09-28/new-chat-1/china-travel-food"]
DATA = next(pathlib.Path(p) for p in _cands if p and pathlib.Path(p).exists())
XDIR = DATA / "research/atlas/xhs"
raw_p, out_p, unmatched_p = XDIR/"raw_xhs.jsonl", XDIR/"raw_reviews.jsonl", XDIR/"unmatched_shops.jsonl"

rests = C.fetch_all("restaurants", "id,name,status,district,address")


def norm(s):
    return C.cjk_norm(s)


_SQUISH = re.compile(r"[\s·・•,，。._\-—/、|｜~～:：;；]+")
def SQ(s):
    """匹配专用强归一：cjk_norm 后去所有空白/分隔/标点（保留 CJK、拉丁、数字）。"""
    return _SQUISH.sub("", C.cjk_norm(s or ""))


def strip_branch(s):
    return re.sub(r"（.*?）|\(.*?\)", "", s or "").strip()


def _cjk_only(s):
    return "".join(ch for ch in s if "一" <= ch <= "鿿")


def _latin_only(s):
    return "".join(ch for ch in s if ("a" <= ch.lower() <= "z" or ch.isdigit()))


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
    """返回 SQ 归一后的品牌核心集合（含·分段、整段、CJK-only、Latin-only、去尾系列名）。"""
    full = strip_branch(full)
    forms = set()
    for seg in re.split(r"[·・•]+", full):
        s = _clean_seg(seg.strip())
        if s and len(s) >= 2:
            forms.add(s)
        cj, lt = _cjk_only(seg), _latin_only(seg)
        if len(cj) >= 2:
            forms.add(cj)
        if len(lt) >= 4:
            forms.add(lt)
    s = _clean_seg(full)
    if s and len(s) >= 2:
        forms.add(s)
    cj, lt = _cjk_only(full), _latin_only(full)
    if len(cj) >= 2:
        forms.add(cj)
    if len(lt) >= 4:
        forms.add(lt)
    fullc = SQ(full)
    for cut in (1, 2, 3):
        if len(fullc) - cut >= 4:
            forms.add(fullc[:-cut])
    out = set()
    for f in forms:
        cf = SQ(f)
        if cf and len(cf) >= 2 and cf not in _CAT_ALL:
            out.add(cf)
    return sorted(out)


def head_token(name):
    full = strip_branch(name)
    seg = re.split(r"[·・•]", full)[0]
    s = _clean_seg(seg)
    return s or seg


def _is_cjk(ch):
    return bool(ch) and ("一" <= ch <= "鿿")


# 纯通用词（去 geo/品类后若只剩这些 → 该品牌"无特异性"，匹配从严，避免子串/词内误命中）
_GW_RAW = ("味道 美食 打卡 探店 宝藏 分享 推荐 好吃 餐厅 饭店 料理 小馆 餐室 酒楼 酒家 "
           "环境 服务 口味 口感 招牌 人气 排队 预约 新店 老店 咖啡 甜品 烘焙 工坊 厨房 "
           "生活 碎片 日常 记录 食客 朋友")
GENERIC_WORDS = {SQ(w) for w in _GW_RAW.split() if SQ(w)}


def _strip_generic(s):
    s = re.sub(_GEO, "", s)
    for w in _CAT_ALL:
        s = s.replace(SQ(w), "")
    for gw in GENERIC_WORDS:
        s = s.replace(gw, "")
    return s


def is_generic_name(name):
    """去 geo/品类/通用词后无任何特异字符 → 通用品牌（如"上海餐厅""徐州味道"）。"""
    return len(_strip_generic(SQ(strip_branch(name)))) < 1


def head_usable(ht):
    """head token 是否具品牌特异性（通用词如"味道"不可作弱命中）。"""
    return len(_strip_generic(SQ(ht))) >= 1


def _bounded(needle, hay, specific):
    """needle 在 hay 中的边界判定。specific 品牌允许后接 CJK；通用品牌要求前后均非 CJK。"""
    i = hay.find(needle)
    while i != -1:
        before = hay[i - 1] if i > 0 else ""
        after = hay[i + len(needle)] if i + len(needle) < len(hay) else ""
        if specific:
            return True
        if not _is_cjk(after) and not _is_cjk(before):
            return True
        i = hay.find(needle, i + 1)
    return False


RMD = []
for r in rests:
    RMD.append({"id": r["id"], "name": r["name"], "status": r["status"],
                "full": strip_branch(r["name"]), "ht": head_token(r["name"]),
                "forms": brand_forms(r["name"]), "address": r.get("address"),
                "gen": is_generic_name(r["name"])})

# 精确/包含索引：key(SQ) -> set(rids)
KEY2RIDS = {}
for d in RMD:
    for k in [SQ(d["name"]), SQ(d["full"])] + d["forms"]:
        if k and len(k) >= 2:
            KEY2RIDS.setdefault(k, set()).add(d["id"])

# 前缀索引（首2字 → keys），把模糊包含从全表 O(K) 降到同前缀常数级
PREF = {}
for k in KEY2RIDS:
    PREF.setdefault(k[:2], []).append(k)
_BC_CACHE = {}

BYID = {d["id"]: d for d in RMD}

# 提及倒排：品牌 key 首2字 → (key, rid, level, generic)；shops_mentioned 改为 O(文本长度)
HEAD2 = {}
def _add_mention(key, d, level):
    if key and len(key) >= 2:
        HEAD2.setdefault(key[:2], []).append((key, d["id"], level, d["gen"]))
for d in RMD:
    fsq = SQ(d["full"])
    if fsq and len(fsq) >= 3:
        _add_mention(fsq, d, 3)
    hsq = SQ(d["ht"])
    if hsq and len(hsq) >= 2 and head_usable(d["ht"]):
        _add_mention(hsq, d, 1)
    for f in d["forms"]:
        _add_mention(f, d, 1)


def _active_first(rids):
    ids = list(rids)
    act = [i for i in ids if next(x for x in RMD if x["id"] == i)["status"] != "closed"]
    return (act or ids)


MALLS = sorted(set(["国贸汇","ITC","itc","美罗城","静安大悦城","大悦城","港汇恒隆","港汇",
    "恒隆广场","恒隆","来福士","万象城","太古汇","环球港","正大广场","正大","国金中心","国金",
    "IFC","ifc","环贸","IAPM","iapm","合生汇","龙之梦","万象天地","天安千树","今潮8弄","新天地",
    "七宝万科","万达广场","万达","大宁国际","久光","仲盛","印象城","嘉亭荟","又一城","宝龙城",
    "前滩太古里","太古里","兴业太古汇","张园","丰盛里","上海中心","金茂","恒隆二期","恒隆三期"]),
    key=len, reverse=True)


def branch_malls(name):
    found = []
    for p in re.findall(r"[（(]([^）)]+)[）)]", name):
        found += [x for x in MALLS if x in p]
    return found


def malls_in(text):
    return [x for x in MALLS if x in text]


def brand_candidates(name):
    """品牌匹配：(rids, 输入名自带分店mall)。
    全名(含分店)精确命中 → 唯一，不再并入裸品牌；否则裸品牌→同前缀包含；记忆化。"""
    q, qb = SQ(name), SQ(strip_branch(name))
    if q in _BC_CACHE:
        return _BC_CACHE[q]
    bm = branch_malls(name)
    if q in KEY2RIDS:
        r = (set(KEY2RIDS[q]), bm)
        _BC_CACHE[q] = r
        return r
    rids = set()
    if qb in KEY2RIDS:
        rids |= KEY2RIDS[qb]
    if not rids and len(qb) >= 2:
        cj = _cjk_only(qb)
        ok_len = len(qb) >= 2 if cj else len(qb) >= 4
        if ok_len:
            for k in PREF.get(qb[:2], []):
                if k.startswith(qb) or qb in k:
                    rids |= KEY2RIDS[k]
    r = (rids, bm)
    _BC_CACHE[q] = r
    return r


def branch_addr_token(addr):
    """门店地址 → 路+门牌 强特征（如 延安中路1238号）。"""
    if not addr:
        return None
    m = re.search(r"([一-龥]{2,8}[路街弄道][^，。\n]{0,12}?号)", addr)
    return SQ(m.group(1)) if m else None


def disambiguate(rids, bmalls, text):
    """多分店 → 输入分店mall → 正文mall → 正文路牌地址 → 唯一active；冲突返回 (None,原因)。"""
    if not rids:
        return None, "库内无此店"
    if len(rids) == 1:
        return next(iter(rids)), ""
    text_malls = malls_in(text)
    if bmalls:
        pick = {i for i in rids if any(SQ(m) in SQ(BYID[i]["name"]) for m in bmalls)}
        if len(pick) == 1:
            return next(iter(pick)), "分店:" + "/".join(bmalls)
    if text_malls:
        pick = {i for i in rids if any(SQ(m) in SQ(BYID[i]["name"]) for m in text_malls)}
        if len(pick) == 1:
            return next(iter(pick)), "正文分店"
        if not pick:
            return None, "分店冲突:" + "/".join(text_malls)
    sqt = SQ(text)
    addr_hits = set()
    for i in rids:
        tok = branch_addr_token(BYID[i].get("address"))
        if tok and tok in sqt:
            addr_hits.add(i)
    if len(addr_hits) == 1:
        return next(iter(addr_hits)), "正文地址"
    act = _active_first(rids)
    if len(act) == 1:
        return act[0], "唯一active分店"
    return None, "多分店待核"


def match_id(name):
    rids, bm = brand_candidates(name)
    rid, _ = disambiguate(rids, bm, "")
    return rid


def core_unique(core, rid):
    rids = KEY2RIDS.get(SQ(core), set())
    return len(rids) == 1 and rid in rids


# 对比参照
_REF_PAT = [r"还是([^，。！？\s、]{2,10}?)(?:最好吃|最好|最正|好吃|正宗|靠谱)",
            r"不如([^，。！？\s、]{2,10})",
            r"没有([^，。！？\s、]{2,10})好吃",
            r"没([^，。！？\s、]{2,10})好吃"]
def ref_groups(text):
    g = set()
    for p in _REF_PAT:
        for mm in re.finditer(p, text):
            if mm.group(1):
                g.add(SQ(mm.group(1)))
    return g


class M:
    def __init__(s, d, score, is_ref):
        s.id, s.name, s.score, s.is_ref = d["id"], d["name"], score, is_ref


def shops_mentioned(text):
    refs = ref_groups(text)
    sqt = SQ(text)
    n = len(sqt)
    best = {}  # rid -> level
    for i in range(n - 1):
        for key, rid, level, gen in HEAD2.get(sqt[i:i + 2], ()):
            L = len(key)
            if sqt[i:i + L] != key:
                continue
            if gen:  # 通用品牌要求边界，防"上海餐厅"命中"上海餐厅周"
                before = sqt[i - 1] if i > 0 else ""
                after = sqt[i + L] if i + L < n else ""
                if _is_cjk(after) or _is_cjk(before):
                    continue
            if best.get(rid, 0) < level:
                best[rid] = level
    out = []
    for rid, level in best.items():
        d = BYID[rid]
        fsq = SQ(d["full"])
        isref = bool(fsq) and any(
            g and (g in fsq or fsq[:4] in g or g in fsq) for g in refs)
        out.append(M(d, level, isref))
    return sorted(out, key=lambda z: -z.score)


_ADDRISH = r"地址[：:]|📍|[路街][^，。\n]{0,10}号|\d+楼|弄\d+号"
_TITLE_STRONG = re.compile(
    r"合集|盘点|排行|排名|红黑榜|哪家强|横评|\d+家店?|攻略大全")
_TITLE_WEAK = re.compile(r"VS|vs|PK|pk|对决|比拼|巨头|\d+碗")
_CIRCLED = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚")


def _numbered_store_lines(text):
    cnt = 0
    for line in text.splitlines():
        if re.match(r"\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])", line):
            if re.search(_ADDRISH, line) or line.strip().endswith("店"):
                cnt += 1
    return cnt


def _circled_store(text):
    parts = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚]", text)
    return sum(1 for seg in parts if re.search(_ADDRISH, seg) or seg.strip().endswith("店"))


def _any_multi_hint(text, mentioned, title):
    nonref = [x for x in mentioned if not x.is_ref]
    if len(nonref) >= 2:
        return True
    if len(re.findall(_ADDRISH, text)) >= 2:
        return True
    if len(set(ch for ch in text if ch in _CIRCLED)) >= 2:
        return True
    if len(re.findall(r"(?m)^\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])", text)) >= 2:
        return True
    if re.search(r"\d+家|\d+碗", title):
        return True
    return False


def is_roundup(title, text, mentioned):
    nonref = [x for x in mentioned if not x.is_ref]
    if len([x for x in nonref if x.score >= 2]) >= 2:
        return True
    if len(re.findall(r"地址[：:]|📍", text)) >= 2:
        return True
    if _numbered_store_lines(text) >= 3:
        return True
    if _circled_store(text) >= 3:
        return True
    hint = _any_multi_hint(text, mentioned, title)
    if _TITLE_STRONG.search(title or "") and hint:
        return True
    if _TITLE_WEAK.search(title or "") and hint:
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
    cands, bmalls = brand_candidates(rec_name)
    if is_roundup(note.get("title", ""), text, mentioned):
        return None, "合集"
    rec_rid, why = disambiguate(cands, bmalls, text)
    if rec_rid:
        d0 = next(x for x in RMD if x["id"] == rec_rid)
        rec_core = strip_branch(rec_name)
        sqt = SQ(text)
        if SQ(rec_core) in sqt or SQ(d0["full"]) in sqt:
            return rec_rid, "搜索目标在正文"
        for bf in d0["forms"]:
            if bf in sqt and core_unique(bf, rec_rid):
                if NEW_SHOP.search(text) and re.search(r"[（(]", rec_name):
                    return rec_rid, "核心专名(新店待核)"
                return rec_rid, "核心专名:" + bf
    nonref = [x for x in mentioned if not x.is_ref]
    if len(nonref) == 1 and nonref[0].score >= 2:
        return nonref[0].id, "唯一主角:" + nonref[0].name
    return None, why or "库内无此店"


QUESTION = re.compile(
    r"[?？]|想问|吗\b|么\b|嘛\b|请问|在哪|哪里|哪家|哪个|求问|求安利|求坐标|求地址|求个|"
    r"有人知道|是不是|对不对|好吃吗|正宗吗|真的吗|怎么样|哪家平台|什么菜|哪一家")
def is_question(t):
    return bool(QUESTION.search(t))


OUT_TOWN = re.compile(r"当地|本地|老家|原产地|来[一-龥]{1,4}(?:吃|当地|本地)|去[一-龥]{1,4}吃")
PRAISE_OTHER = re.compile(
    r"(?:隔壁|旁边|对面|斜对面|楼上下|附近)[^，。！？]{0,10}(?:好吃|香|正宗|更强|更好)|"
    r"[^，。！？]{2,8}(?:好吃|香|正宗)(?:一百倍|好多倍|得多|太多)")
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
    t = t.replace("\t", " ").replace("​", " ")
    return re.sub(r"\n{2,}", "\n", t).strip()


def same_person(a, b):
    return SQ(a) and SQ(a) == SQ(b)


def parse_note_date(d):
    if not d:
        return None
    if isinstance(d, (int, float)):
        import datetime
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
        import datetime
        mm, dd = int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 1 <= dd <= 31:
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
                if a is not None:
                    trust = "mid" if ("新店待核" in reason or "待核" in reason) else "high"
                    rev = {"restaurant_id": rid, "author_name": author,
                        "source_platform": "小红书", "source_url": note.get("url"), "content": body,
                        "review_kind": "diner", "is_verified_diner": True, "trust_level": trust,
                        "aspect_taste": a, "aspect_json": {"taste_raw": raw}}
                    if vd:
                        rev["visit_date"] = vd
                    reviews.append(rev)
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
                    continue
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

pathlib.Path(out_p).write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in reviews), encoding="utf-8")
pathlib.Path(unmatched_p).write_text(
    "\n".join(json.dumps(x, ensure_ascii=False) for x in unmatched), encoding="utf-8")
print("生成 reviews:", len(reviews), "| 未锚笔记:", len(unmatched))
from collections import Counter
print("有口味分:", sum(1 for x in reviews if x["aspect_taste"] is not None))
rc = Counter(x["reason"] if "reason" in x else "" for x in unmatched)
print("未锚原因分布:", dict(rc))

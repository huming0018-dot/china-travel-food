#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""entity_match.py — 统一的餐厅实体解析 / 笔记锚定 / 口味判定核心（可导入、可测试）。

定位：把原 xhs_to_reviews.py 里成熟的「品牌多形态 + 前缀/二元索引 + 分店消歧 +
证据化合集判定」匹配器抽成独立模块，供 cookie 采集（xhs_to_reviews）与
商业采集（review_apify_fill）共用，杜绝各采集器各写一套粗糙匹配（曾出现
"要求完整长店名子串"导致真实食客笔记 78% 误判"正文无目标店"）。

用法：
    import entity_match as EM
    idx = EM.get_index()                 # 缓存的全库索引（经 common 拉 restaurants）
    idx = EM.EntityIndex(rests)          # 或用给定餐厅列表构建（测试用）
    mentioned = idx.shops_mentioned(text)
    rid, why   = idx.anchor_note(note, rec_name)
    score, raw = EM.taste_sent(text)
"""
import os
import pathlib
import re
import sys

PIPE = pathlib.Path(__file__).resolve().parent
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))
import common as C  # noqa: E402


# ------------------------------------------------------------ 归一与品牌形态
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
_CAT = ["绵阳米粉", "热干面", "水煎包", "米粉", "川味", "寿司", "拉面", "烧肉", "咖喱", "咖啡",
        "面馆", "牛肉", "烤肉", "烧烤", "火锅", "饺子", "包子", "甜品", "料理", "食研", "小馆",
        "酒馆", "餐室", "餐厅", "饭店", "酒楼", "酒家", "老铺", "饼", "饭", "面", "汤"]
_CAT_EXTRA = ["铜锣烧", "胡辣汤", "卤菜", "牛肉汤", "牛肉面", "冰浆", "糖水", "小笼", "生煎",
              "锅贴", "烧麦", "汤圆", "烧饼", "葱油饼", "可丽饼", "薄饼", "三明治", "贝果",
              "酸种", "可颂", "起酥", "蛋糕", "布丁", "果冻", "麻薯", "鲷鱼烧", "和果子",
              "抹茶", "冰淇淋", "冰激凌", "刨冰", "松饼", "甜汤", "法式甜品", "乌冬", "荞麦",
              "烧鸟", "天妇罗", "鳗鱼", "寿喜烧", "铁板", "炉端", "居酒屋", "怀石", "洋食",
              "盖饭", "便当", "定食", "釜饭", "粉"]
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
    return len(_strip_generic(SQ(strip_branch(name)))) < 1


def head_usable(ht):
    return len(_strip_generic(SQ(ht))) >= 1


def _bounded(needle, hay, specific):
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


MALLS = sorted(set(["国贸汇", "ITC", "itc", "美罗城", "静安大悦城", "大悦城", "港汇恒隆", "港汇",
    "恒隆广场", "恒隆", "来福士", "万象城", "太古汇", "环球港", "正大广场", "正大", "国金中心",
    "国金", "IFC", "ifc", "环贸", "IAPM", "iapm", "合生汇", "龙之梦", "万象天地", "天安千树",
    "今潮8弄", "新天地", "七宝万科", "万达广场", "万达", "大宁国际", "久光", "仲盛", "印象城",
    "嘉亭荟", "又一城", "宝龙城", "前滩太古里", "太古里", "兴业太古汇", "张园", "丰盛里",
    "上海中心", "金茂", "恒隆二期", "恒隆三期"]), key=len, reverse=True)


def branch_malls(name):
    found = []
    for p in re.findall(r"[（(]([^）)]+)[）)]", name):
        found += [x for x in MALLS if x in p]
    return found


def malls_in(text):
    return [x for x in MALLS if x in text]


def branch_addr_token(addr):
    """门店地址 → 路+门牌 强特征（如 延安中路1238号）。"""
    if not addr:
        return None
    m = re.search(r"([一-龥]{2,8}[路街弄道][^，。\n]{0,12}?号)", addr)
    return SQ(m.group(1)) if m else None


# ------------------------------------------------------------ 口味 / 疑问 / 清洗
POS = {"好吃": .35, "正宗": .3, "惊艳": .4, "鲜嫩": .25, "入味": .25, "地道": .3,
       "值得": .2, "香": .15, "酥脆": .25, "弹": .2, "浓郁": .15, "回购": .25,
       "必吃": .25, "天花板": .3, "封神": .3, "新鲜": .25, "入口即化": .35,
       "爆汁": .3, "鲜美": .25, "嫩滑": .25,
       # —— 扩充：真实食客高频正评（diag：27.8% 笔记"无口味信号"被误杀）——
       "不错": .2, "喜欢": .2, "推荐": .2, "很嫩": .2, "软烂": .2, "回头客": .25,
       "惊喜": .3, "用心": .2, "超赞": .3, "靠谱": .2, "现做": .15, "锅气": .25,
       "外酥里嫩": .3, "外焦里嫩": .3, "汁水": .2, "软糯": .2, "松软": .2,
       "回甘": .25, "满足": .15, "嫩": .15, "酥": .12, "鲜": .12}
NEG = {"难吃": -.6, "避雷": -.5, "踩雷": -.5, "失望": -.4, "一般": -.3,
       "不好吃": -.55, "腥": -.35, "柴": -.35, "预制": -.4, "冷冻": -.3,
       "不新鲜": -.45, "太咸": -.25, "油腻": -.3, "糊弄": -.4, "无味": -.4,
       "寡淡": -.3, "嚼不动": -.4,
       # —— 修正：原 xhs_to_reviews "油腻":.3 符号错误；并扩充负评 ——
       "普通": -.2, "平庸": -.25, "没味道": -.35, "没什么味道": -.3,
       "偏咸": -.2, "偏甜": -.2, "太甜": -.2, "齁": -.3, "硬": -.2,
       "发苦": -.3, "不值": -.25, "后悔": -.3, "不会再来": -.35, "拉黑": -.3,
       "名不副实": -.35, "言过其实": -.3, "中看不中吃": -.4, "又贵又难吃": -.5}


def taste_sent(text):
    pos = sum(w for k, w in POS.items() if k in text)
    neg = sum(w for k, w in NEG.items() if k in text)
    if pos == 0 and neg == 0:
        return None, None
    raw = max(1.0, min(5.0, round(3.8 + pos + neg, 1)))
    return max(1, min(5, int(raw + 0.5))), raw


QUESTION = re.compile(
    r"[?？]|想问|吗\b|么\b|嘛\b|请问|在哪|哪里|哪家|哪个|求问|求安利|求坐标|求地址|求个|"
    r"有人知道|是不是|对不对|好吃吗|正宗吗|真的吗|怎么样|哪家平台|什么菜|哪一家")


def is_question(t):
    return bool(QUESTION.search(t))


def clean_content(t):
    t = re.sub(r"#\S+", "", t or "")
    t = t.replace("\t", " ").replace("\u200b", " ")
    return re.sub(r"\n{2,}", "\n", t).strip()


# ------------------------------------------------------------ 索引
class M:
    def __init__(self, d, score, is_ref):
        self.id, self.name, self.score, self.is_ref = d["id"], d["name"], score, is_ref


class EntityIndex:
    def __init__(self, rests):
        self.RMD = []
        for r in rests:
            self.RMD.append({"id": r["id"], "name": r["name"], "status": r.get("status"),
                             "full": strip_branch(r["name"]), "ht": head_token(r["name"]),
                             "forms": brand_forms(r["name"]),
                             "address": r.get("address"),
                             "gen": is_generic_name(r["name"])})
        self.KEY2RIDS = {}
        for d in self.RMD:
            for k in [SQ(d["name"]), SQ(d["full"])] + d["forms"]:
                if k and len(k) >= 2:
                    self.KEY2RIDS.setdefault(k, set()).add(d["id"])
        self.PREF = {}
        for k in self.KEY2RIDS:
            self.PREF.setdefault(k[:2], []).append(k)
        self.BYID = {d["id"]: d for d in self.RMD}
        self.HEAD2 = {}
        for d in self.RMD:
            fsq = SQ(d["full"])
            if fsq and len(fsq) >= 3:
                self._add_mention(fsq, d, 3)
            hsq = SQ(d["ht"])
            if hsq and len(hsq) >= 2 and head_usable(d["ht"]):
                self._add_mention(hsq, d, 1)
            for f in d["forms"]:
                self._add_mention(f, d, 1)
        self._bc_cache = {}

    def _add_mention(self, key, d, level):
        if key and len(key) >= 2:
            self.HEAD2.setdefault(key[:2], []).append((key, d["id"], level, d["gen"]))

    # -- 分店
    def _active_first(self, rids):
        act = [i for i in rids if self.BYID[i]["status"] != "closed"]
        return act or list(rids)

    def brand_candidates(self, name):
        q, qb = SQ(name), SQ(strip_branch(name))
        if q in self._bc_cache:
            return self._bc_cache[q]
        bm = branch_malls(name)
        if q in self.KEY2RIDS:
            r = (set(self.KEY2RIDS[q]), bm)
            self._bc_cache[q] = r
            return r
        rids = set()
        if qb in self.KEY2RIDS:
            rids |= self.KEY2RIDS[qb]
        if not rids and len(qb) >= 2:
            cj = _cjk_only(qb)
            ok_len = len(qb) >= 2 if cj else len(qb) >= 4
            if ok_len:
                for k in self.PREF.get(qb[:2], []):
                    if k.startswith(qb) or qb in k:
                        rids |= self.KEY2RIDS[k]
        r = (rids, bm)
        self._bc_cache[q] = r
        return r

    def disambiguate(self, rids, bmalls, text):
        """多分店 → 输入分店mall → 正文mall → 正文路牌地址 → 唯一active；冲突 (None,原因)。"""
        if not rids:
            return None, "库内无此店"
        if len(rids) == 1:
            return next(iter(rids)), ""
        text_malls = malls_in(text)
        if bmalls:
            pick = {i for i in rids if any(SQ(m) in SQ(self.BYID[i]["name"]) for m in bmalls)}
            if len(pick) == 1:
                return next(iter(pick)), "分店:" + "/".join(bmalls)
        if text_malls:
            pick = {i for i in rids if any(SQ(m) in SQ(self.BYID[i]["name"]) for m in text_malls)}
            if len(pick) == 1:
                return next(iter(pick)), "正文分店"
            if not pick:
                return None, "分店冲突:" + "/".join(text_malls)
        sqt = SQ(text)
        addr_hits = set()
        for i in rids:
            tok = branch_addr_token(self.BYID[i].get("address"))
            if tok and tok in sqt:
                addr_hits.add(i)
        if len(addr_hits) == 1:
            return addr_hits.pop(), "正文地址"
        act = self._active_first(rids)
        if len(act) == 1:
            return act[0], "唯一active分店"
        return None, "多分店待核"

    def match_id(self, name):
        rids, bm = self.brand_candidates(name)
        rid, _ = self.disambiguate(rids, bm, "")
        return rid

    def core_unique(self, core, rid):
        rids = self.KEY2RIDS.get(SQ(core), set())
        return len(rids) == 1 and rid in rids

    def shops_mentioned(self, text):
        sqt = SQ(text)
        n = len(sqt)
        best = {}
        for i in range(n - 1):
            for key, rid, level, gen in self.HEAD2.get(sqt[i:i + 2], ()):
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
        refs = self._ref_groups(text)
        out = []
        for rid, level in best.items():
            d = self.BYID[rid]
            fsq = SQ(d["full"])
            isref = bool(fsq) and any(
                g and (g in fsq or fsq[:4] in g or g in fsq) for g in refs)
            out.append(M(d, level, isref))
        return sorted(out, key=lambda z: -z.score)

    _REF_PAT = [r"还是([^，。！？\s、]{2,10}?)(?:最好吃|最好|最正|好吃|正宗|靠谱)",
                r"不如([^，。！？\s、]{2,10})",
                r"没有([^，。！？\s、]{2,10})好吃",
                r"没([^，。！？\s、]{2,10})好吃"]

    def _ref_groups(self, text):
        g = set()
        for p in self._REF_PAT:
            for mm in re.finditer(p, text):
                if mm.group(1):
                    g.add(SQ(mm.group(1)))
        return g

    # -- 合集
    _ADDRISH = r"地址[：:]|📍|[路街][^，。\n]{0,10}号|\d+楼|弄\d+号"
    _TITLE_STRONG = re.compile(r"合集|盘点|排行|排名|红黑榜|哪家强|横评|\d+家店?|攻略大全")
    _TITLE_WEAK = re.compile(r"VS|vs|PK|pk|对决|比拼|巨头|\d+碗")
    _CIRCLED = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚")

    def _numbered_store_lines(self, text):
        cnt = 0
        for line in text.splitlines():
            if re.match(r"\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])", line):
                if re.search(self._ADDRISH, line) or line.strip().endswith("店"):
                    cnt += 1
        return cnt

    def _circled_store(self, text):
        parts = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚]", text)
        return sum(1 for seg in parts
                   if re.search(self._ADDRISH, seg) or seg.strip().endswith("店"))

    def _any_multi_hint(self, text, mentioned, title):
        nonref = [x for x in mentioned if not x.is_ref]
        if len(nonref) >= 2:
            return True
        if len(re.findall(self._ADDRISH, text)) >= 2:
            return True
        if len(set(ch for ch in text if ch in self._CIRCLED)) >= 2:
            return True
        if len(re.findall(r"(?m)^\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])",
                          text)) >= 2:
            return True
        if re.search(r"\d+家|\d+碗", title):
            return True
        return False

    def is_roundup(self, title, text, mentioned=None):
        mentioned = mentioned if mentioned is not None else self.shops_mentioned(text)
        nonref = [x for x in mentioned if not x.is_ref]
        if len([x for x in nonref if x.score >= 2]) >= 2:
            return True
        if len(re.findall(r"地址[：:]|📍", text)) >= 2:
            return True
        if self._numbered_store_lines(text) >= 3:
            return True
        if self._circled_store(text) >= 3:
            return True
        hint = self._any_multi_hint(text, mentioned, title)
        if self._TITLE_STRONG.search(title or "") and hint:
            return True
        if self._TITLE_WEAK.search(title or "") and hint:
            return True
        return False

    # --------------------------------------------------------- 笔记锚定
    NEW_SHOP = re.compile(r"新店|PLUS|plus|首店|二店|2店|新开")

    def anchor_note(self, note, rec_name):
        text = note.get("title", "") + "\n" + note.get("desc", "")
        mm = re.search(r"商家[：:]\s*([^\n，。#]+)", note.get("desc", ""))
        if mm:
            rid = self.match_id(mm.group(1).strip())
            if rid:
                return rid, "显式商家"
        mentioned = self.shops_mentioned(text)
        cands, bmalls = self.brand_candidates(rec_name)
        if self.is_roundup(note.get("title", ""), text, mentioned):
            return None, "合集"
        rec_rid, why = self.disambiguate(cands, bmalls, text)
        if rec_rid:
            d0 = self.BYID[rec_rid]
            rec_core = strip_branch(rec_name)
            sqt = SQ(text)
            if SQ(rec_core) in sqt or SQ(d0["full"]) in sqt:
                return rec_rid, "搜索目标在正文"
            for bf in d0["forms"]:
                if bf in sqt and self.core_unique(bf, rec_rid):
                    if self.NEW_SHOP.search(text) and re.search(r"[（(]", rec_name):
                        return rec_rid, "核心专名(新店待核)"
                    return rec_rid, "核心专名:" + bf
        nonref = [x for x in mentioned if not x.is_ref]
        if len(nonref) == 1 and nonref[0].score >= 2:
            return nonref[0].id, "唯一主角:" + nonref[0].name
        if rec_rid is not None:
            # 目标店确实在候选中，但正文无任何目标证据（搜索返回了跑题笔记）
            return None, "正文非目标店"
        return None, why or "库内无此店"


# ------------------------------------------------------------ 缓存默认索引
_INDEX = None


def get_index(force=False):
    global _INDEX
    if _INDEX is None or force:
        rests = C.fetch_all("restaurants", "id,name,status,district,address")
        _INDEX = EntityIndex(rests)
    return _INDEX

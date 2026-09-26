#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage2_prepare.py — 实体对齐 + 标签解析 + 地理编码，生成入库计划 plan.json（默认不写库）

用法：
  python3 stage2_prepare.py -i accepted.jsonl -o plan.json                 # 预演（不建标签、跑地理编码）
  python3 stage2_prepare.py -i accepted.jsonl --create-tags                # 缺标签时按规则新建并回读
  python3 stage2_prepare.py -i accepted.jsonl --no-geocode                 # 跳过地理编码
"""
import argparse
import json
import pathlib
import sys
import time

import requests

import common as C
import nondiner_main as N

# raw 形式值 -> 库内标签名（dimension=形式）
FORM_MAP = {
    "Finedining": ["Finedining", "Fine Dining", "Fine dining"],
    "Casual Dining": ["Casual Dining", "Casual", "Casual Dining 休闲西餐"],
    "Bistro": ["Bistro/小酒馆", "Bistro", "小酒馆"],
    "快餐简餐": ["快餐/简餐", "快餐", "快餐简餐"],
    "Brunch": ["Brunch", "早午餐"],
    "下午茶": ["下午茶"],
    "私宴会所": ["私宴/会所", "私宴", "会所"],
    "自助放题": ["自助/放题", "自助", "放题"],
    "酒吧清吧": ["酒吧/清吧", "酒吧", "清吧"],
    "夜宵": ["夜宵/深夜食堂", "夜宵", "深夜食堂"],
    "大排档": ["大排档/路边摊", "大排档", "路边摊"],
}
VIRTUAL_ROOTS = {"中餐", "亚洲", "欧洲", "非洲", "北美洲", "南美洲", "融合菜", "非正餐"}
# raw 旧根/场景根 → 新虚拟根归一
RAW_ROOT_NORM = {"亚洲菜": "亚洲", "西餐": "欧洲", "其他": "非正餐", "非正餐（轻食·饮品）": "非正餐"}
# raw 国家名/地域名 → 库内菜系标签名
COUNTRY_ALIAS = {"日本": "日料/日本料理", "泰国": "泰餐", "法国": "法餐", "韩国": "韩餐",
                 "越南": "越餐", "希腊": "地中海/希腊菜", "墨西哥": "墨西哥菜", "印度": "印度菜",
                 "泰国菜": "泰餐", "厦门菜": "闽南菜", "融合菜": "融合菜/Fusion"}
# 路径叶子是"风味+形式"组合：拆出形式标签，菜系挂国家，不建菜系叶子
LEAF_FORM_HINT = {"创意泰式Bistro": "Bistro", "曼谷早午餐Brunch": "Brunch"}

# —— 标签归一：子代理常自造同义词、或把品类/FineDining 塞进菜系路径，统一收口到库标准标签 ——
import difflib as _difflib
import re as _re
# 品类/店型词 -> 库【食材/形式】标签（中餐第二轴由食材/形式维度承载，不建菜系叶子）
CAT_ING = {
    "卤味": ["烧腊/卤味"], "烧腊": ["烧腊/卤味"], "烧腊/烧味": ["烧腊/卤味"],
    "潮汕卤味/打冷/生腌": ["烧腊/卤味", "海鲜"], "海鲜打冷/潮汕海鲜": ["海鲜", "烧腊/卤味"],
    "海鲜酒楼": ["海鲜"], "水产": ["海鲜"], "蟹/海鲜": ["海鲜"], "臭鳜鱼专门店": ["河鲜"],
    "家禽/鸭": ["肉禽"], "鸭/禽": ["肉禽"], "家禽": ["肉禽"],
    "潮汕牛肉火锅": ["火锅/锅物", "肉禽"], "牛肉火锅": ["火锅/锅物", "肉禽"],
    "早茶点心": ["甜品/点心"], "淮扬细点/茶点": ["甜品/点心"], "甜品": ["甜品/点心"],
    "甜品点心": ["甜品/点心"], "潮汕小吃甜品": ["小吃/街头", "甜品/点心"],
    "豆制品": ["豆制品/豆花"], "豆制品/豆腐": ["豆制品/豆花"],
    "粥": ["粥/泡饭"], "砂锅粥/粿条": ["粥/泡饭"], "粥粉面": ["粥/泡饭", "面"],
    "面包烘焙": ["面包/烘焙"],
    "湖南米粉": ["面"], "苏式汤面/早面": ["面"], "闽南沙茶面/海蛎煎/姜母鸭": ["面", "小吃/街头"],
    "面/饼": ["面", "饼"], "面食/点心": ["面"], "鲅鱼饺子/山东面食": ["饺子/馄饨", "面"],
    "啫啫煲": ["汤/煲"], "湘西酸汤": ["汤/煲"],
    "湘西熏腊山珍": ["肉禽", "菌菇/山珍"], "潮汕小吃": ["小吃/街头"],
    "闽南小吃/甜品": ["小吃/街头", "甜品/点心"],
    # —— 地方菜（本帮/京/东北/西北/新疆/西南/台湾/湖北/河南/江西/海南）品类第二轴 → 食材 ——
    "生煎": ["包子/馒头", "小吃/街头"], "小笼包": ["包子/馒头"], "锅贴": ["饺子/馄饨", "小吃/街头"],
    "葱油拌面·冷面": ["面"], "本帮面": ["面"], "炸酱面": ["面", "小吃/街头"], "京味小吃": ["小吃/街头"],
    "排骨年糕·炸猪排": ["小吃/街头", "肉禽"], "白斩鸡·熟食": ["肉禽"],
    "腌笃鲜·糟货": ["汤/煲"], "点心团膳": ["甜品/点心"],
    "东北烧烤": ["烧烤/烤串"], "西北烧烤": ["烧烤/烤串"], "云南烧烤": ["烧烤/烤串"],
    "东北麻辣烫": ["火锅/锅物", "小吃/街头"], "云南米线": ["面"],
    "野生菌火锅": ["火锅/锅物", "菌菇/山珍"], "酸汤鱼火锅": ["火锅/锅物", "河鲜"], "火锅": ["火锅/锅物"],
    "大盘鸡": ["肉禽"], "卤肉饭·小吃": ["饭", "小吃/街头"], "茶饮·甜品": ["饮品", "甜品/点心"],
    "水煎包": ["包子/馒头"], "海南鸡饭": ["饭", "肉禽"],
    # —— 食材去斜杠同义词 / 泛称 → 库精确食材名（ingredients 数组与菜系路径通用）——
    "内脏": ["肉禽"], "小吃": ["小吃/街头"], "汤": ["汤/煲"], "火锅锅物": ["火锅/锅物"],
    "烧烤烤串": ["烧烤/烤串"], "菌菇类": ["菌菇/山珍"], "蔬菜素食": ["蔬菜/素食"],
    "豆制品": ["豆制品/豆花"], "甜品点心": ["甜品/点心"], "面包烘焙": ["面包/烘焙"],
    "水产": ["海鲜"], "鱼": ["河鲜"], "鸭": ["肉禽"], "饺子": ["饺子/馄饨"],
    # —— 场景类（咖啡/甜品/Brunch/Bistro）食材词收口 ——
    "沙拉": ["蔬菜/素食"], "健康轻食": ["蔬菜/素食"],
    "蛋": ["肉禽"],
    "创意特调": ["饮品"], "抹茶": ["饮品"],
    "中式糖水": ["甜品/点心"], "法式甜品": ["甜品/点心"], "可丽饼": ["甜品/点心"], "点心": ["甜品/点心"],
    "烤鱼": ["烧烤/烤串"], "炭烤": ["烧烤/烤串"], "直火炭烤": ["烧烤/烤串"],
    "酸面包烘焙": ["面包/烘焙"],
    "冰淇淋": ["甜品/点心"],
    # —— v0924 补店：品类词转食材标签 ——
    "江鲜": ["河鲜"],
    "上海小吃": ["小吃/街头"],
    "生煎/锅贴": ["包子/馒头", "小吃/街头"],
    "面食": ["面"],
}
# 场景类【形式】词 -> 库形式标签（子代理把店型写进菜系路径，统一收口，不建菜系叶子）
FORM_CAT = {
    "Brunch": ["早午餐 Brunch"],
    "Deli": ["Bistro/小酒馆"], "Pasta Bar": ["Bistro/小酒馆"], "杂货铺": ["Bistro/小酒馆"],
    "意式食堂": ["Bistro/小酒馆"], "餐酒馆": ["Bistro/小酒馆"], "北京开来": ["Bistro/小酒馆"],
    "北欧bistro": ["Bistro/小酒馆"], "融合bistro": ["Bistro/小酒馆"],
    "中式融合bistro": ["Bistro/小酒馆"], "中西融合bistro": ["Bistro/小酒馆"],
    "直火烤bistro": ["Bistro/小酒馆"], "新疆bistro": ["Bistro/小酒馆"],
    "云贵川bistro": ["Bistro/小酒馆"],
    "夜宵": ["夜宵/深夜食堂"],
    "深夜食堂": ["夜宵/深夜食堂"], "夜宵大排档": ["夜宵/深夜食堂"],
    "自然酒吧": ["酒吧/清吧"], "鸡尾酒酒吧": ["酒吧/清吧"], "黑胶餐酒吧": ["酒吧/清吧"],
    "新中式下午茶": ["下午茶"], "日式下午茶": ["下午茶"], "英式下午茶": ["下午茶"],
    "粤式早茶": ["下午茶"],
    "Bistro餐酒": ["Bistro/小酒馆"],
}
CATEGORY_TO_DIM = {**{k: ("食材", v) for k, v in CAT_ING.items()},
                   "大排档": ("形式", ["大排档/路边摊"]),
                   **{k: ("形式", v) for k, v in FORM_CAT.items()}}
INGREDIENT_CANON = CAT_ING  # ingredients 数组按同一词典归一
# 菜系路径里的泛区域/泛称词：父根已在路径上层挂过，直接忽略，不建泛称叶子
PATH_WORDS_IGNORE = {"东南亚", "欧式", "欧陆", "场景", "苏浙菜"}
# 自造【地域叶子】词 -> 库已有菜系叶子名（对齐，不新建）
CUISINE_LEAF_ALIAS = {
    "长沙小炒": "长沙菜", "湘江流域(长沙)": "长沙菜",
    "洞庭湖区(常德/岳阳)": "洞庭湖区菜", "常德钵子菜": "洞庭湖区菜",
    "湘西山区(怀化/张家界)": "湘西菜",
    "皖南菜(徽州/黄山)": "徽州菜", "沿淮菜(蚌埠/宿州)": "皖北菜",
    "闽北山珍熏味": "闽北菜", "闽南/潮汕跨界": "闽南菜",
    "广府菜": "广府菜(广州)", "港式茶餐厅": "港式茶餐厅/冰室",
    "成都家常菜": "成都家常菜/苍蝇馆子",
    # 地方菜叶子变体 -> 库精确叶名
    "涮羊肉铜锅": "老北京铜锅涮肉", "胡同家常": "京味家常", "宫廷菜官府": "宫廷官府菜",
    "武汉过早": "武汉过早·热干面小吃", "小龙虾": "潜江小龙虾·湖北夜宵", "藕汤·洪湖菜": "湖北家常菜馆·藕汤",
    "铁锅炖": "东北铁锅炖", "东北饺子": "东北饺子馆",
    "陕西菜": "西安菜(正餐/泡馍/葫芦鸡)", "宁夏手抓": "宁夏·西北清真手抓羊肉",
    "胡辣汤": "豫菜·胡辣汤", "江西米粉": "江西炒粉/拌粉",
    "牛肉面": "台湾牛肉面·小吃", "台菜小炒": "台湾家常菜", "眷村": "台湾家常菜",
    "手抓饭·拌面": "新疆手抓饭/面馆",
    # 一级菜系别称（=父菜系本身，主循环遇到与父名相同则跳过，避免重复/误建）
    "赣菜": "江西菜", "桂菜": "广西菜", "荆楚": "湖北菜", "豫菜": "河南菜",
    # —— 场景类菜系叶子对齐 ——
    "美式": "美餐",
    "滇菜": "云南菜", "云南傣味": "云南菜",
    "法式": "法餐", "爱尔兰菜": "英国菜", "现代爱尔兰": "英国菜",
    "意中融合": "融合菜/Fusion", "意式融合": "融合菜/Fusion", "地中海亚洲": "融合菜/Fusion",
    "精品咖啡": "咖啡/甜品专门店", "社区咖啡": "咖啡/甜品专门店", "连锁咖啡": "咖啡/甜品专门店",
    "咖啡甜品": "咖啡/甜品专门店", "咖啡+甜品": "咖啡/甜品专门店", "主理人品牌": "咖啡/甜品专门店",
    "手冲专门": "咖啡/甜品专门店", "日式手冲": "咖啡/甜品专门店", "自烘豆": "咖啡/甜品专门店",
    "单品专门店": "咖啡/甜品专门店", "烘焙一体主理人品牌": "咖啡/甜品专门店",
    "手工披萨": "那不勒斯披萨",
    # 希腊叶子（国家映射 id32 地中海/希腊菜，叶子即菜品/形式，折叠到国家不另建）
    "Moussaka慕莎卡/Souvlaki烤串": "地中海/希腊菜",
    "希腊Taverna正餐": "地中海/希腊菜",
    # —— v0924 补店：子代理自用词对齐库内标准标签（不新建重复叶子）——
    "牛排馆": "美式牛排",
    "法国菜": "法餐",
    "欧陆菜": "法餐",  # 实测 Aster(Paris)/Trine(意法融合) 均以法餐为底色
    "本帮融合": "海派融合",
    "Omakase板前": "Omakase 板前",  # cid325 名含空格
    "精致本帮家常菜": "上海家常",
    "意大利菜": "意餐",
    "沪菜": "本帮菜",
    "上海本帮": "本帮菜",
    "台山菜": "广府菜(广州)",  # 台山属五邑广府
    "潮州菜": "潮汕菜",
    "融合创意菜": "融合菜/Fusion",
    "湖州菜": "浙菜",  # 菰城=湖州，浙北
    "湛江菜": "广府菜(广州)",  # 湛江属粤西
    "泰北街边": "泰北菜",
}
# 一级菜系简写 -> 库标准名
ROOT_CUISINE_ALIAS = {"浙": "浙菜"}
# 仅这些库内确实缺失的【地域叶子】允许 --create-tags 自动建（值=必须匹配的父菜系名）
ALLOW_CREATE_CUISINE = {
    "川北·绵阳菜": "川菜", "川南·内江菜": "川菜", "川南·泸州菜": "川菜",
    "金华/衢州菜": "浙菜", "闽北菜": "闽菜", "博山菜": "鲁菜",
    # 地方菜流派叶子（库确缺、双轴网格需要）
    "本帮浓油赤酱老字号": "本帮菜", "海派融合": "本帮菜", "上海家常": "本帮菜",
    "京味家常": "京菜", "宫廷官府菜": "京菜",
    "桂林米粉": "广西菜",
}
FD_RE = _re.compile(r"fine\s?dining|finedining", _re.I)
MEAL_ALIAS = {"早餐": "早午餐"}
SPECIAL_ALIAS = {
    "团购": "团购优惠", "工业化出品": "工业化餐饮", "central_kitchen": "工业化餐饮",
    "工业化": "工业化餐饮", "连锁品牌": "工业化餐饮", "连锁": "工业化餐饮",
    "分子料理": "分子/先锋料理", "分子/先锋": "分子/先锋料理", "先锋料理": "分子/先锋料理",
    "纯素": "素食/纯素", "素食": "素食/纯素", "vegan": "素食/纯素",
    "米其林": "米其林星级", "黑珍珠": "黑珍珠餐厅",
    "预约": "可预订", "可预约": "可预订", "预订": "可预订",
}
IGNORE_SPECIAL = {"江景"}  # 库不设环境/景观标签；连锁在 chain_type/notes 体现，不建标签
MALL_RE = _re.compile(r"广场|购物中心|商场|万象城|太古里|大悦城|日月光|来福士|恒隆|太古汇|龙之梦|印象城|"
                      r"环宇荟|久光|美罗城|太阳宫|大丸|百货|荟聚|CP静安|瑞虹|鸿寿坊|慎余里|老码头|"
                      r"环球港|合生汇|正大|国金|BFC|金融中心|仲盛|近铁|百联|万达|银泰|嘉里|利邻荟|新乐坊|"
                      r"南丰城|K11|新世界|尚浦汇|大融城|宝龙|世茂|创邑|复悦荟|丽宝|虹桥天地|汇智|欢乐颂|"
                      r"新天地|金虹桥|环贸|IAPM|iapm|芮欧|上海中心|越洋|前滩|梦中心|西岸|白玉兰|IM")


def _brand_core(s):
    """剥离括号分店后缀与路名/商场尾巴，取品牌核心名（避免'XX日月光店'共同后缀误判同店）。"""
    s = str(s)
    s = _re.split(r"[（(]", s)[0]
    m = _re.search(r"[路街道里弄号镇]|广场|中心|商场|万象城|太古|大悦城|日月光|来福士|恒隆|龙之梦|印象城|百货", s)
    if m:
        s = s[:m.start()]
    s = _re.sub(r"(上海)?(全国首店|首店|分店|总店|直营店|旗舰店|店)$", "", s)
    return C.norm_name(s)


def name_similar(a, b):
    """品牌核心名是否高度相似（同店异写）：互相包含且足够长，或编辑相似度≥0.6。"""
    ca, cb = _brand_core(a), _brand_core(b)
    if not ca or not cb:
        return False
    if ca in cb or cb in ca:
        return min(len(ca), len(cb)) >= 2
    return _difflib.SequenceMatcher(None, ca, cb).ratio() >= 0.6


UA = {"User-Agent": "ShanghaiFoodGuide-PWA/1.0 (curation; contact=local)"}


def build_evidence_text(rec):
    """可读证据文本：风味综合 + 编号堂食原话(含菜名/平台/URL) + 差评，供前端 <p> 直接展示。"""
    txt = (rec.get("evidence_summary") or "").strip()
    ev = rec.get("evidence") or {}
    lines = [txt] if txt else []
    qs = ev.get("diner_quotes", [])
    if qs:
        lines.append("— 食客堂食原话 —")
        for i, q in enumerate(qs, 1):
            dish = q.get("dish") or ""
            head = f"{i}. [{q.get('source')}" + (f"·{dish}" if dish else "") + "]"
            lines.append(f"{head} {q.get('quote','')} ({q.get('url')})")
    neg = ev.get("negative_signals", [])
    if neg:
        lines.append("差评/风险：" + "；".join(str(x) for x in neg))
    return "\n".join(lines)


class TagResolver:
    def __init__(self, create=False):
        self.cuisines = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
        self.by_name = {}
        for c in self.cuisines:
            self.by_name.setdefault((c.get("name") or "").strip(), []).append(c)
        self.create = create
        self.created = []

    def _find(self, name, dimension=None, parent=None):
        cands = self.by_name.get(name)
        if not cands:
            return None
        if dimension:
            cands = [c for c in cands if c.get("dimension") == dimension] or cands
        if parent:
            exact = [c for c in cands if c.get("parent_category") == parent]
            if exact:
                cands = exact
        return cands[0]

    def get(self, name, dimension=None, parent=None, create_parent_dimension="菜系"):
        hit = self._find(name, dimension, parent)
        if hit:
            return hit["id"], False
        # 同维度内包含匹配（应对"日料/日本料理"类差异）
        for c in self.cuisines:
            cn = c.get("name") or ""
            if dimension and c.get("dimension") != dimension:
                continue
            # 不得把叶子折叠到它的直接父标签或虚拟根：如"海派改良川菜"含"川菜"，
            # 不能因此只挂父标签"川菜"而丢失子流派叶子。
            if parent and (cn == parent or cn in VIRTUAL_ROOTS):
                continue
            if name and (name in cn or cn in name) and len(cn) >= 2:
                return c["id"], False
        if not self.create:
            return None, ("need_create", name, dimension or create_parent_dimension, parent)
        body = {"name": name, "dimension": dimension or create_parent_dimension}
        if parent:
            body["parent_category"] = parent
        r = C.req("POST", "/cuisines", json=body)
        if r.status_code not in (200, 201):
            sys.exit(f"建标签失败 {body}: {r.status_code} {r.text[:200]}")
        # PostgREST 默认不返回响应体（未显式 Prefer: return=representation），
        # 不能 r.json()；按 name+dimension+parent 回查拿新行。
        time.sleep(0.2)
        q = {"name": f"eq.{name}", "dimension": f"eq.{body['dimension']}",
             "select": "id,name,dimension,parent_category"}
        rows = C.req("GET", "/cuisines", params=q).json()
        if parent:
            rows = [x for x in rows if x.get("parent_category") == parent]
        if not rows:
            sys.exit(f"建标签后回查不到: {body}（POST {r.status_code}）")
        new = rows[0]
        self.cuisines.append(new)
        self.by_name.setdefault(new["name"], []).append(new)
        self.created.append(new)
        return new["id"], True

    def form_id(self, form):
        for alias in FORM_MAP.get(form, [form]):
            hit = self._find(alias, dimension="形式")
            if hit:
                return hit["id"]
        return None

    def by_dim_name(self, name, dimension):
        hit = self._find(name, dimension=dimension)
        return hit["id"] if hit else None

    def leaf_match(self, name, parent=None):
        """菜系叶子匹配：先精确，再去括号核心名包含匹配（'广府菜'->'广府菜(广州)'、
        '济南菜(历下派)'->'济南菜'）；不得折叠到父标签或虚拟根。"""
        # 先按 name 精确（dimension=菜系，不限 parent）：唯一命中直接用，
        # 使"拉面·虾白汤"等"·"细分叶子能按名定位（其 parent 是"拉面"而非路径上层国家）
        exact = [c for c in self.cuisines
                 if c.get("dimension") == "菜系" and (c.get("name") or "") == name]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1 and parent:
            pe = [c for c in exact if c.get("parent_category") == parent]
            if pe:
                return pe[0]
        h = self._find(name, "菜系", parent)
        if h:
            return h
        core = _re.sub(r"[（(].*?[）)]", "", str(name)).strip()
        cands = []
        for c in self.cuisines:
            if c.get("dimension") != "菜系":
                continue
            cn = c.get("name") or ""
            if cn in VIRTUAL_ROOTS or (parent and cn == parent):
                continue
            if core and len(core) >= 2 and (core in cn or cn in core):
                cands.append(c)
        if parent:
            ex = [c for c in cands if c.get("parent_category") == parent]
            if ex:
                cands = ex
        return cands[0] if cands else None


def geocode(district, address, business_area=None):
    qs = [f"上海市{district or ''}{address}", f"上海市{address} {business_area or ''}".strip()]
    for q in [x for x in qs if x]:
        try:
            r = requests.get("https://nominatim.openstreetmap.org/search",
                             params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "cn"},
                             headers=UA, timeout=25)
            if r.status_code == 200 and r.json():
                d = r.json()[0]
                lng, lat = float(d["lon"]), float(d["lat"])
                if C.in_shanghai(lng, lat) and "上海" in d.get("display_name", ""):
                    return lng, lat, "nominatim", d.get("display_name", "")
        except requests.RequestException:
            pass
        time.sleep(1.1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", default="accepted.jsonl")
    ap.add_argument("-o", "--output", default="plan.json")
    ap.add_argument("--create-tags", action="store_true")
    ap.add_argument("--no-geocode", action="store_true")
    args = ap.parse_args()

    rows = C.read_jsonl(args.input)
    rests = C.fetch_all("restaurants", "id,name,address,district,status", order_col="id")
    by_name, by_addr = {}, {}
    for r in rests:
        by_name.setdefault(C.norm_name(r["name"]), []).append(r)
        ac = C.addr_core(r.get("address") or "")
        if ac:
            by_addr.setdefault(ac, []).append(r)

    resolver = TagResolver(create=args.create_tags)
    plan, stats = [], {"new": 0, "update": 0, "conflict": 0, "needs_amap": 0, "tag_created": 0}
    pending_tags = []

    for rec in rows:
        nn, ac = C.norm_name(rec["name"]), C.addr_core(rec["address"])
        action, rid, conflicts = "new", None, []
        # 人工实体裁决锚定：同店异写/分店名差异/地址写法不同导致自动对齐失灵时，
        # raw 可给 match_restaurant_id 直接指定库内同店，优先于名字/地址模糊匹配。
        anchor = rec.get("match_restaurant_id")
        if anchor and any(r["id"] == anchor for r in rests):
            action, rid = "update", anchor
        else:
            # 同名
            same_name = by_name.get(nn, [])
            if same_name:
                same_addr = [r for r in same_name if C.addr_core(r.get("address") or "") == ac] \
                    or [r for r in same_name if r.get("district") == rec["district"]]
                if same_addr:
                    action, rid = "update", same_addr[0]["id"]
                else:
                    action = "new"  # 同名异址：连锁分店，保留
                    conflicts.append("同名异址(连锁分店?)，确认后入库")
            elif ac and ac in by_addr:
                hits = by_addr[ac]
                sim = [h for h in hits if name_similar(nn, C.norm_name(h["name"]))]
                if sim:  # 同址且店名高度相似（紫荆阁/徽味轩/嘉良驿园类同店异写）
                    hit = sim[0]
                    action, rid = "conflict", hit["id"]
                    conflicts.append(f"同址异名但店名高度相似，库内为「{hit['name']}」，疑同店异写，需锚定/裁决")
                elif MALL_RE.search(rec.get("address") or ""):
                    action = "new"  # 商场/美食广场内不同铺位，同址不同店（邓凳面≠隔壁云南菜）
                    conflicts.append(f"商场同址不同铺位（库内另有 {'、'.join(h['name'] for h in hits[:2])}），按新店")
                else:
                    hit = hits[0]
                    action, rid = "conflict", hit["id"]
                    conflicts.append(f"街铺同址异名，库内为「{hit['name']}」，需人工裁决")

        # ---- 标签解析 ----
        cids, missing = set(), []
        # 菜系路径里出现 Fine Dining 且人均≥250：升级为形式标签（它不是菜系叶子）
        rec_form = rec.get("form")
        for path in rec["cuisine_paths"]:
            for lv0 in path:
                if FD_RE.search(str(lv0)) and (rec.get("price_avg") or 0) >= 250:
                    rec_form = "Finedining"
        # 非正餐主营优先（机制 v3，教训 #61）：招牌主体是甜品/面包/咖啡/茶饮/Bar 时，
        # 菜系以非正餐根+叶为准，原路径里的正餐地域菜系不挂（形式/食材由独立字段承载）
        _nd = N.classify(rec.get("name"), rec.get("signature_dishes"),
                         form_names=[rec_form] if rec_form else [])
        parse_paths = rec["cuisine_paths"]
        if _nd["is_nondiner_main"] and _nd["root"]:
            parse_paths = [["非正餐", _nd["root"]]
                           + ([_nd["leaf"]] if _nd["leaf"] else [])]
        for path in parse_paths:
            prev_parent = None
            for level0 in path:
                lv = str(level0).strip()
                lv = RAW_ROOT_NORM.get(lv, lv)
                if lv in VIRTUAL_ROOTS:
                    prev_parent = lv
                    continue
                # 风味+形式组合叶子：拆形式，菜系（国家）已由上层挂
                if lv in LEAF_FORM_HINT:
                    fmap = {"Bistro": "Bistro/小酒馆", "Brunch": "早午餐 Brunch"}
                    fid2 = resolver.by_dim_name(fmap[LEAF_FORM_HINT[lv]], "形式")
                    if fid2:
                        cids.add(fid2)
                    continue
                if lv == "素食":
                    cids.add(45)
                    continue
                if lv in PATH_WORDS_IGNORE:
                    continue  # 泛区域/泛称（东南亚/欧式/欧陆），父根已挂，不建泛称叶子
                if FD_RE.search(lv):
                    continue  # Fine Dining 归形式，已在上面处理
                # 非正餐菜系根（甜品/咖啡/面包/Bar/茶饮）：挂菜系根，
                # 不被同名食材词（CAT_ING 里裸"甜品"等）拦截转食材
                if prev_parent == "非正餐" and lv in ("咖啡", "面包", "甜品", "Bar", "茶饮"):
                    _rh = resolver._find(lv, dimension="菜系", parent="非正餐")
                    if _rh:
                        cids.add(_rh["id"])
                    prev_parent = lv
                    continue
                # 纯品类/店型词：转食材/形式标签，不作菜系叶子
                if lv in CATEGORY_TO_DIM:
                    dim, names = CATEGORY_TO_DIM[lv]
                    for nm in names:
                        xid = resolver.by_dim_name(nm, dim)
                        (cids.add(xid) if xid else missing.append(("need_create", nm, dim, None)))
                    prev_parent = lv
                    continue
                # 自造地域叶子词/国家名/一级菜系简写对齐到库标准名
                lv = CUISINE_LEAF_ALIAS.get(lv, lv)
                lv = COUNTRY_ALIAS.get(lv, lv)
                lv = ROOT_CUISINE_ALIAS.get(lv, lv)
                if lv in CATEGORY_TO_DIM:
                    dim, names = CATEGORY_TO_DIM[lv]
                    for nm in names:
                        xid = resolver.by_dim_name(nm, dim)
                        (cids.add(xid) if xid else missing.append(("need_create", nm, dim, None)))
                    prev_parent = lv
                    continue
                if lv == prev_parent:
                    continue  # 别称归一后即父菜系本身（赣菜=江西菜、荆楚=湖北菜），父标签上一轮已挂，不重建
                hitc = resolver.leaf_match(lv, prev_parent)
                if hitc:
                    cids.add(hitc["id"])
                elif args.create_tags and lv in ALLOW_CREATE_CUISINE \
                        and ALLOW_CREATE_CUISINE[lv] == prev_parent:
                    cid, made = resolver.get(lv, dimension="菜系", parent=prev_parent)
                    if cid is not None:
                        cids.add(cid)
                        if made is True:
                            stats["tag_created"] += 1
                    else:
                        missing.append(("need_create", lv, "菜系", prev_parent))
                else:
                    missing.append(("need_create", lv, "菜系", prev_parent))
                prev_parent = lv
        fid = resolver.form_id(rec_form)
        if fid:
            cids.add(fid)
        else:
            missing.append(("need_create", rec_form, "形式", "正餐"))
        for m0 in rec.get("meals", []):
            m = MEAL_ALIAS.get(m0, m0)
            mid = resolver.by_dim_name(m, "时段")
            cids.add(mid) if mid else missing.append(("need_create", m, "时段", None))
        for ing0 in rec.get("ingredients", []):
            for ing in INGREDIENT_CANON.get(ing0, [ing0]):
                iid = resolver.by_dim_name(ing, "食材")
                if iid:
                    cids.add(iid)
                else:
                    missing.append(("need_create", ing, "食材", None))
        aw = rec.get("awards") or {}
        if aw.get("michelin") and aw["michelin"] != "无":
            cids.add(159)
        if C.to_int(aw.get("black_pearl")):
            cids.add(160)
        for st0 in rec.get("special_tags", []):
            st = SPECIAL_ALIAS.get(st0, st0)
            if st in IGNORE_SPECIAL:
                continue
            # 受控白名单：special_tags 只接受能映射到库内 标签/认证 的标签；
            # 子代理常把"楼层/商圈/年份/人气/装修/风格"等描述短语塞进 special_tags，
            # 未识别项一律忽略、不自动建标签，避免标签污染。
            sid = resolver.by_dim_name(st, "标签") or resolver.by_dim_name(st, "认证")
            if sid:
                cids.add(sid)
        pending_tags.extend([m for m in missing if isinstance(m, tuple)])

        # ---- 坐标 ----
        loc, needs_amap, coord_src = None, False, rec.get("coord_source")
        lng, lat = rec.get("lng"), rec.get("lat")
        if lng is not None and lat is not None and C.in_shanghai(lng, lat):
            loc = C.point_ewkt(lng, lat)
        elif not args.no_geocode and rec["status"] == C.STATUS_OPEN:
            g = geocode(rec["district"], rec["address"], rec.get("business_area"))
            if g:
                lng, lat, coord_src, _ = g
                loc = C.point_ewkt(lng, lat)
            else:
                needs_amap, stats["needs_amap"] = True, stats["needs_amap"] + 1

        # 派生列 tier / score_total / search_vector / updated_at 由数据库触发器
        # trg_restaurants_derive 在写库时计算，禁止手填（详见 db/migrations/002_harden.sql）。
        fields = {
            "name": rec["name"], "name_en": rec.get("name_en"),
            "price_avg": rec["price_avg"],
            "price_range": rec.get("price_range"), "address": rec["address"],
            "district": rec["district"], "business_area": rec.get("business_area"),
            "phone": rec.get("phone"), "booking_method": rec.get("booking_method"),
            "signature_dishes": rec["signature_dishes"],
            "investor_info": rec.get("brand_group"),
            "score_objective": rec["scores"]["objective"], "score_diner": rec["scores"]["diner"],
            "score_taste": rec["scores"]["taste"], "score_endorsement": rec["scores"]["endorsement"],
            "soft_ad_penalty": rec["scores"]["soft_ad_penalty"],
            "evidence_summary": build_evidence_text(rec),
            "status": rec["status"], "data_updated_at": rec["data_updated_at"],
            "closed_date": rec.get("closed_date"), "closed_source": rec.get("closed_source"),
        }
        if loc:
            fields["location"] = loc
        if rec["status"] == C.STATUS_CLOSED:
            fields["discount_info"] = None
            fields["evidence_summary"] = (f"【{rec.get('closed_date')} 关店】来源:{rec.get('closed_source')} "
                                          + fields["evidence_summary"])
        fields = {k: v for k, v in fields.items() if v is not None}

        plan.append({
            "action": action, "restaurant_id": rid, "name": rec["name"],
            "fields": fields, "cids_add": sorted(c for c in cids if c),
            "needs_amap": needs_amap, "coord_source": coord_src,
            "missing_tags": sorted({json.dumps(m, ensure_ascii=False) for m in missing}),
            "conflicts": conflicts, "warnings": rec.get("_warnings", []),
        })
        stats[action if action in ("new", "update") else "conflict"] = \
            stats.get(action if action in ("new", "update") else "conflict", 0) + 1
        time.sleep(0.1)

    pathlib.Path(args.output).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"计划: 新增 {stats['new']} / 更新 {stats['update']} / 冲突待裁 {stats.get('conflict',0)}")
    print(f"待高德补坐标 {stats['needs_amap']}；新建标签 {stats['tag_created']}")
    uniq_tags = sorted({json.dumps(m, ensure_ascii=False) for m in pending_tags})
    if uniq_tags:
        print(f"\n=== 缺失标签（{len(uniq_tags)}，加 --create-tags 自动建，或人工确认）===")
        for t in uniq_tags[:60]:
            print("  ", t)
    cf = [p for p in plan if p["conflicts"]]
    if cf:
        print(f"\n=== 冲突待人工裁决（{len(cf)}）===")
        for p in cf[:30]:
            print(f"  {p['name']}: {'; '.join(p['conflicts'])}")
    print(f"\n输出: {args.output}（dry-run，未写库；确认后跑 stage3_upsert.py --commit）")


if __name__ == "__main__":
    main()

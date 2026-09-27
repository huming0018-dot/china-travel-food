#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discovery_keywords.py — 全品类「开放式发现词矩阵」自动生成器。

为什么存在：social_discovery.DISCOVERY_QUERIES 是手写、只覆盖 6 个品类的固定词表，
八大菜系 / 拉面 / 咖啡 / 各国菜都没有发现词，这是"日料深、其他菜系浅"的直接原因之一。
本模块用「通用句式模板 + 每品类种子词（称呼/子品类/地域/跨语）」自动展开成 15~25 个
发现词；新增菜系只需登记种子，不必手写 10 组词。

种子只给"起点"：自驱动引擎（discovery_engine）还会从笔记正文 / 评论区自动发现
新的子品类、商圈、店名并加入 frontier，因此种子不必穷尽。

用法：
  from discovery_keywords import build_queries
  qs = build_queries("sichuan")          # -> list[str]
  qs = build_queries("bread", city="上海")
"""
import re

# 发现词通用句式模板。占位：
#   {name} 品类称呼（轮替 names）；{sub} 子品类；{region} 地域/子流派；{en} 英文称呼
# 与 BREAD-SOURCING-METHOD §二 / discovery-playbook §3 的词组一一对应。
TEMPLATES = [
    "{name} 私藏 回购 舍不得公开",
    "{name} 老饕 懂吃的朋友 无广",
    "{name} 红黑榜 合集 盘点",
    "社区{name} 本地人 常吃 回头客",
    "{name} 无广 真实测评 踩雷",
    "{name} 主厨 大师 传承 工作室",
    "{name} 综艺 纪录片 同款 冠军",
    "{name} 预约 排队 老顾客",
]
SUB_TEMPLATES = [
    "{sub} 推荐 好吃 口感",
    "{sub} 天花板 层次 正宗",
]
REGION_TEMPLATES = [
    "{region}{name} 好吃 推荐 正宗",
    "{region} {name} 本地人 老乡",
]
EN_TEMPLATES = [
    "best {en} shanghai",
    "{en} recommendation authentic",
]

# 每品类种子：names=称呼词；subs=子品类/店型/招牌垂直；regions=地域子流派/商圈；ens=英文
# 子流派参照 discovery-playbook §1、cuisine-map；只给核心种子，余下图遍历自扩展。
CATEGORY_SPEC = {
    # ---------- 非正餐 ----------
    "bread": {
        "names": ["面包店", "面包"], "ens": ["bakery", "sourdough"],
        "subs": ["酸种面包", "可颂", "贝果", "欧包", "日式面包", "生吐司", "碱水结", "肉桂卷", "恰巴塔"],
        "regions": [],
    },
    "coffee": {
        "names": ["咖啡店", "咖啡馆"], "ens": ["coffee shop", "cafe", "specialty coffee"],
        "subs": ["手冲咖啡", "意式浓缩", "奶咖", "拿铁", "澳白", "单品咖啡", "自烘豆"],
        "regions": [],
    },
    "dessert": {
        "names": ["甜品店", "甜品"], "ens": ["dessert", "patisserie"],
        "subs": ["法式甜品", "巴斯克", "提拉米苏", "蛋糕", "布丁", "慕斯", "刨冰", "舒芙蕾"],
        "regions": [],
    },
    "bar": {
        "names": ["酒吧", "清吧"], "ens": ["cocktail bar", "speakeasy"],
        "subs": ["鸡尾酒", "威士忌吧", "精酿啤酒", "金酒", "自然酒", "调酒师"],
        "regions": [],
    },
    "tea_house": {
        "names": ["茶馆", "茶室"], "ens": ["tea house"],
        "subs": ["工夫茶", "岩茶", "普洱", "老白茶", "围炉煮茶"],
        "regions": ["老洋房"],
    },
    # ---------- 日料细分 ----------
    "sushi": {
        "names": ["寿司", "寿司店"], "ens": ["sushi", "omakase"],
        "subs": ["江户前寿司", "板前寿司", "omakase", "主厨发办", "鲔鱼大腹", "熟成寿司"],
        "regions": [],
    },
    "ramen": {
        "names": ["拉面", "拉面店"], "ens": ["ramen"],
        "subs": ["豚骨拉面", "酱油拉面", "味噌拉面", "蘸面", "鸡白汤拉面", "荞麦面", "乌冬面", "博多拉面"],
        "regions": ["博多"],
    },
    "yakitori": {
        "names": ["烧鸟", "烧鸟店"], "ens": ["yakitori"],
        "subs": ["烧鸟 omakase", "备长炭烧鸟", "鸡白汤", "稀有部位"],
        "regions": [],
    },
    "yakiniku": {
        "names": ["烧肉", "烧肉店"], "ens": ["yakiniku", "bbq"],
        "subs": ["和牛烧肉", "炭火烧肉", "韩式烧肉", "烤肉套餐"],
        "regions": [],
    },
    "izakaya": {
        "names": ["居酒屋"], "ens": ["izakaya"],
        "subs": ["日式小酒馆", "烤串", "关东煮", "日式下酒菜"],
        "regions": [],
    },
    "tempura": {
        "names": ["天妇罗", "天妇罗专门店"], "ens": ["tempura"],
        "subs": ["天妇罗 omakase", "车虾天妇罗", "野菜天妇罗"],
        "regions": [],
    },
    "japanese_curry": {
        "names": ["日式咖喱", "咖喱饭"], "ens": ["japanese curry"],
        "subs": ["咖喱猪排饭", "咖喱乌冬", "汤咖喱"],
        "regions": [],
    },
    "kaiseki": {
        "names": ["怀石料理", "怀石"], "ens": ["kaiseki"],
        "subs": ["怀石 omakase", "茶怀石", "会席料理"],
        "regions": [],
    },
    # ---------- 中餐八大菜系 ----------
    "sichuan": {
        "names": ["川菜", "四川菜"], "ens": [],
        "subs": ["自贡盐帮菜", "江湖菜", "成都苍蝇馆子", "重庆火锅", "串串香", "冒菜",
                 "重庆小面", "宜宾燃面", "绵阳米粉", "富顺豆花", "烤鱼", "酸菜鱼", "辣子鸡"],
        "regions": ["自贡", "宜宾", "泸州", "重庆", "成都", "绵阳", "南充", "内江"],
    },
    "cantonese": {
        "names": ["粤菜", "广东菜"], "ens": ["cantonese"],
        "subs": ["广式早茶", "点心", "烧腊", "茶餐厅", "潮汕牛肉火锅", "潮汕生腌",
                 "砂锅粥", "粿条", "顺德菜", "打冷"],
        "regions": ["广州", "潮汕", "顺德", "客家", "港式"],
    },
    "jiangsu": {
        "names": ["苏菜", "江苏菜"], "ens": [],
        "subs": ["淮扬菜", "苏式汤面", "南京盐水鸭", "淮扬细点", "狮子头", "蟹粉", "无锡排骨"],
        "regions": ["淮扬", "南京", "苏州", "无锡"],
    },
    "shandong": {
        "names": ["鲁菜", "山东菜"], "ens": [],
        "subs": ["胶东海鲜", "九转大肠", "糖醋鲤鱼", "山东饺子", "葱烧海参", "爆炒腰花"],
        "regions": ["济南", "胶东", "福山"],
    },
    "zhejiang": {
        "names": ["浙菜", "浙江菜"], "ens": [],
        "subs": ["杭帮菜", "东坡肉", "西湖醋鱼", "宁波海鲜", "绍兴菜", "金华菜"],
        "regions": ["杭州", "宁波", "绍兴", "金华", "衢州"],
    },
    "fujian": {
        "names": ["闽菜", "福建菜"], "ens": [],
        "subs": ["佛跳墙", "福州菜", "闽南菜", "潮汕海鲜", "闽菜 fine dining", "沙茶面"],
        "regions": ["福州", "闽南", "莆田", "泉州", "厦门"],
    },
    "hunan": {
        "names": ["湘菜", "湖南菜"], "ens": [],
        "subs": ["湖南米粉", "剁椒鱼头", "辣椒炒肉", "小炒黄牛肉", "湘西菜", "口味虾"],
        "regions": ["长沙", "湘西", "常德"],
    },
    "anhui": {
        "names": ["徽菜", "安徽菜"], "ens": [],
        "subs": ["臭鳜鱼", "毛豆腐", "胡适一品锅", "黄山炖鸽", "问政山笋"],
        "regions": ["徽州", "黄山"],
    },
    "shanghainese": {
        "names": ["本帮菜", "上海菜"], "ens": ["shanghainese"],
        "subs": ["红烧肉", "生煎", "小笼包", "葱油拌面", "白斩鸡", "油爆虾", "熏鱼", "本帮面馆"],
        "regions": ["上海"],
    },
    "beijing": {
        "names": ["京菜", "北京菜"], "ens": [],
        "subs": ["北京烤鸭", "炸酱面", "涮羊肉", "卤煮", "豆汁", "京味点心"],
        "regions": ["北京"],
    },
    # ---------- 亚洲其他 ----------
    "thai": {
        "names": ["泰餐", "泰国菜"], "ens": ["thai food"],
        "subs": ["冬阴功", "泰式炒河粉", "青木瓜沙拉", "咖喱蟹", "芒果糯米饭", "泰北菜"],
        "regions": ["曼谷", "泰北", "清迈"],
    },
    "vietnamese": {
        "names": ["越南菜", "越南粉"], "ens": ["vietnamese food", "pho"],
        "subs": ["河粉", "pho", "生春卷", "法包", "滴漏咖啡", "越南火锅"],
        "regions": ["河内", "西贡"],
    },
    "korean": {
        "names": ["韩餐", "韩国菜"], "ens": ["korean food"],
        "subs": ["韩式烤肉", "部队火锅", "炸鸡", "拌饭", "酱蟹", "冷面"],
        "regions": ["首尔", "釜山"],
    },
    "singaporean": {
        "names": ["新加坡菜", "海南鸡饭"], "ens": ["singaporean food"],
        "subs": ["海南鸡饭", "辣椒螃蟹", "叻沙", "肉骨茶", "咖椰吐司"],
        "regions": ["新加坡"],
    },
    "malaysian": {
        "names": ["马来西亚菜"], "ens": ["malaysian food"],
        "subs": ["叻沙", "椰浆饭", "肉骨茶", "沙嗲", "炒粿条"],
        "regions": ["吉隆坡", "槟城"],
    },
    "indian": {
        "names": ["印度菜", "咖喱"], "ens": ["indian food"],
        "subs": ["咖喱", "烤饼", "印度飞饼", "比尔亚尼", "坦都里烤鸡", "玛萨拉"],
        "regions": ["北印度", "南印度"],
    },
    "japanese_western": {
        "names": ["洋食", "日式洋食"], "ens": ["yoshoku"],
        "subs": ["蛋包饭", "炸猪排", "可乐饼", "汉堡排", "日式咖喱"],
        "regions": [],
    },
    # ---------- 西餐 ----------
    "french": {
        "names": ["法餐", "法国菜"], "ens": ["french restaurant"],
        "subs": ["法式 fine dining", "鹅肝", "蜗牛", "可丽饼", "布列塔尼", "红酒炖牛肉", "法式小馆 bistro"],
        "regions": ["巴黎", "里昂", "布列塔尼"],
    },
    "italian": {
        "names": ["意餐", "意大利菜"], "ens": ["italian restaurant"],
        "subs": ["手工意面", "披萨", "烩饭", "提拉米苏", "海鲜", "托斯卡纳"],
        "regions": ["罗马", "那不勒斯", "西西里", "托斯卡纳"],
    },
    "spanish": {
        "names": ["西班牙菜"], "ens": ["spanish food", "tapas"],
        "subs": ["tapas", "海鲜饭", "伊比利亚火腿", "土豆蛋饼", "烤乳猪"],
        "regions": ["巴塞罗那", "巴斯克", "马德里"],
    },
    "mediterranean": {
        "names": ["地中海菜"], "ens": ["mediterranean food"],
        "subs": ["希腊菜", "土耳其菜", "烤肉串", "皮塔饼", "鹰嘴豆泥", "海鲜"],
        "regions": ["希腊", "土耳其", "黎巴嫩"],
    },
    "german": {
        "names": ["德餐", "德国菜"], "ens": ["german food"],
        "subs": ["猪肘", "香肠", "碱水面包", "啤酒"],
        "regions": ["巴伐利亚", "慕尼黑"],
    },
    "american": {
        "names": ["美餐", "美国菜"], "ens": ["american restaurant"],
        "subs": ["牛排馆", "汉堡", "烤肉 bbq", "炸鸡", "龙虾", "brunch"],
        "regions": ["纽约", "德州", "加州"],
    },
    "steakhouse": {
        "names": ["牛排馆", "牛排"], "ens": ["steakhouse"],
        "subs": ["干式熟成牛排", "和牛牛排", "战斧牛排", "美式牛排"],
        "regions": [],
    },
    # ---------- 场景/其他 ----------
    "private_kitchen": {
        "names": ["私房菜", "私宴"], "ens": ["private kitchen", "chef's table"],
        "subs": ["家宴", "主厨发办", "无菜单料理", "厨师上门", "楼中店"],
        "regions": ["洋房", "小区"],
    },
    "hotpot": {
        "names": ["火锅"], "ens": ["hotpot"],
        "subs": ["重庆火锅", "潮汕牛肉火锅", "老北京涮肉", "花胶鸡火锅", "椰子鸡", "猪肚鸡", "高端火锅"],
        "regions": [],
    },
    "guangxi_fish": {
        "names": ["广西鱼生", "横县鱼生"], "ens": [],
        "subs": ["顺德鱼生", "吊水皖鱼", "脆肉鲩", "横县鱼生配料"],
        "regions": ["横县", "顺德", "广西"],
    },
    "market_food": {
        "names": ["菜市场美食", "菜场"], "ens": ["wet market food"],
        "subs": ["熏鱼", "羌饼", "爆鱼", "白斩鸡", "手工肉丸", "油条豆浆", "熟食"],
        "regions": [],
    },
}

# category key → 菜系根名（挂标签 / 裁决时定位标签子树用）。
CUISINE_ROOT = {
    "bread": "面包", "coffee": "咖啡", "dessert": "甜品", "bar": "酒吧",
    "tea_house": "茶馆", "sushi": "寿司", "ramen": "拉面", "yakitori": "烧鸟",
    "yakiniku": "烧肉", "izakaya": "居酒屋", "tempura": "天妇罗",
    "japanese_curry": "日式咖喱", "kaiseki": "怀石", "sichuan": "川菜",
    "cantonese": "粤菜", "jiangsu": "苏菜", "shandong": "鲁菜",
    "zhejiang": "浙菜", "fujian": "闽菜", "hunan": "湘菜", "anhui": "徽菜",
    "shanghainese": "本帮菜", "beijing": "京菜", "thai": "泰餐",
    "vietnamese": "越南菜", "korean": "韩餐", "singaporean": "新加坡菜",
    "malaysian": "马来西亚菜", "indian": "印度菜", "japanese_western": "洋食",
    "french": "法餐", "italian": "意餐", "spanish": "西班牙菜",
    "mediterranean": "地中海菜", "german": "德餐", "american": "美餐",
    "steakhouse": "牛排馆", "private_kitchen": "私房菜", "hotpot": "火锅",
    "guangxi_fish": "广西菜", "market_food": "小吃",
}

# 同一含义的别名 → 规范 category key（容错）
ALIASES = {
    "bread": "bread", "面包": "bread", "bakery": "bread",
    "sushi": "sushi", "寿司": "sushi",
    "sichuan": "sichuan", "川菜": "sichuan", "四川": "sichuan",
    "cantonese": "cantonese", "粤菜": "cantonese", "广东": "cantonese",
    "ramen": "ramen", "拉面": "ramen",
    "coffee": "coffee", "咖啡": "coffee",
}


def normalize_category(cat):
    c = str(cat or "").strip().lower()
    if c in CATEGORY_SPEC:
        return c
    return ALIASES.get(c, c)


def _fill(template, name="", sub="", region="", en=""):
    try:
        return template.format(name=name, sub=sub, region=region, en=en).strip()
    except Exception:
        return ""


def build_queries(category, city="", dense=False):
    """生成某品类的发现词列表（去重、保序）。

    - 默认精简密度：主称呼跑通用模板，每个子品类/地域/英文各 1 词，别名只补关键 2 词。
    - dense=True：子品类、地域用双模板，别名称呼跑全套（发现要更密时用）。
    - city：xhs_collect.search 会自动拼城市，故默认留空、不复制整表；仅当目标平台
      不自动加城市时才传。
    """
    key = normalize_category(category)
    spec = CATEGORY_SPEC.get(key)
    if spec is None:
        # 未登记品类：用品类名本身做最小种子，引擎图遍历再扩展
        base = str(category)
        spec = {"names": [base], "subs": [], "regions": [], "ens": []}
    names = spec.get("names") or [str(category)]
    subs = spec.get("subs") or []
    regions = spec.get("regions") or []
    ens = spec.get("ens") or []

    out, seen = [], set()

    def add(q):
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)

    # 主称呼跑全部通用模板；别名称呼只补关键前 2 词（dense 时跑全套）
    for i, name in enumerate(names):
        for t in (TEMPLATES if i == 0 or dense else TEMPLATES[:2]):
            add(_fill(t, name=name))
    # 子品类：默认每词 1 条，dense 时 2 条
    for sub in subs:
        for t in (SUB_TEMPLATES if dense else SUB_TEMPLATES[:1]):
            add(_fill(t, sub=sub))
    # 地域：默认每地 1 条，dense 时 2 条
    for region in regions:
        for name in names[:1]:
            for t in (REGION_TEMPLATES if dense else REGION_TEMPLATES[:1]):
                add(_fill(t, name=name, region=region))
    # 英文：默认每词 1 条，dense 时 2 条
    for en in ens:
        for t in (EN_TEMPLATES if dense else EN_TEMPLATES[:1]):
            add(_fill(t, en=en))

    if city:
        for q in list(out):
            add(f"{city} {q}")
    return out


def all_categories():
    return list(CATEGORY_SPEC)


if __name__ == "__main__":
    import sys
    for cat in (sys.argv[1:] or ["bread", "sichuan", "ramen"]):
        qs = build_queries(cat)
        qd = build_queries(cat, dense=True)
        print(f"\n=== {cat}（默认 {len(qs)} 词 / dense {len(qd)} 词）===")
        for q in qs:
            print(" ", q)

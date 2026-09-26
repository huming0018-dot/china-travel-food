#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nondiner_main.py — 「非正餐主营」判定共享模块（机制 v3，2026-09-24）。

解决：鲜芋仙（台式芋圆/仙草甜品连锁）被挂正餐「台湾菜」、price_scene 误判正餐。
原则：**当一家店的主营出品是非正餐品类（甜品/面包/咖啡/茶饮/Bar）时，非正餐菜系
优先于地域来源（台湾/日本/法国）**；地域只在子叶/食材里体现，不挂正餐地域菜系。

为避免把"正餐店套餐里的一道面包/甜品"误判为非正餐，判定采用多信号、默认保守：
  auto（is_nondiner_main=True）必须同时满足：
    1) 非 Fine Dining；
    2) 招牌菜经菜级正餐否定后，非正餐命中占比 ≥ 0.75；
    3) 正餐主菜（猪肘/香肠/牛排/整鱼/龙虾/炖肉/千层面…）占比 < 0.25；
    4) 有业态背书：非正餐形式标签（Brunch/下午茶/酒吧/茶馆/快餐）或 店名业态词，
       或招牌非正餐占比 ≥ 0.9。
  review：占比 ≥0.5 但不满足 auto（正餐信号也强/样本不全），交裁决，不硬改。

被 cuisine_classify_audit.py（R5）与 stage2_prepare.py（源头防复发）共同 import。
"""

# (根, 子叶, [关键词])
LEAVES = [
    ("甜品", "冰淇淋Gelato", ["gelato", "冰淇淋", "冰激凌", "雪糕"]),
    ("甜品", "刨冰", ["刨冰", "冰沙", "冰浆", "かき氷", "沙冰", "雪花冰", "绵绵冰"]),
    ("甜品", "松饼/薄饼", ["松饼", "舒芙蕾", "可丽饼", "薄饼", "galette", "pancake", "souffle",
                  "crepe", "华夫", "格子饼", "法式吐司"]),
    ("甜品", "糖水/甜汤", ["糖水", "甜汤", "椰奶", "糖葱", "双皮奶", "杨枝甘露", "芝麻糊", "杏仁",
                  "豆花", "芋圆", "仙草", "爱玉", "麻薯", "布丁", "银耳", "圆子", "甜羹",
                  "奶冻", "西米", "芋泥", "芭菲", "圣代"]),
    ("甜品", "蛋糕/法式甜品", ["蛋糕", "慕斯", "提拉米苏", "泡芙", "马卡龙", "闪电", "法式甜品",
                    "芝士蛋糕", "千层", "mille", "蛋挞", "甜品", "甜点", "西点",
                    "布列斯特", "国王饼", "巴斯克", "戚风"]),
    ("甜品", "铜锣烧/和果子", ["铜锣烧", "和果子", "羊羹", "最中", "日式甜品", "团子"]),
    ("面包", "可颂/起酥专门", ["可颂", "牛角包", "起酥", "丹麦", "咸派", "quiche"]),
    ("面包", "日式面包", ["日式面包", "咖喱面包", "蜜瓜包", "红豆面包", "生吐司", "米面包"]),
    ("面包", "社区烘焙坊", ["面包", "烘焙", "吐司", "软欧"]),
    ("面包", "贝果专门", ["贝果", "bagel"]),
    ("面包", "酸种面包专门", ["酸种", "酸面包", "sourdough", "欧包"]),
    ("咖啡", "创意特调咖啡", ["特调咖啡", "创意咖啡"]),
    ("咖啡", "手冲/自烘豆专门", ["手冲", "单品咖啡", "自烘"]),
    ("咖啡", "社区精品咖啡", ["咖啡", "拿铁", "美式", "卡布", "澳白", "flat white",
                    "espresso", "latte", "cappuccino", "mocha"]),
    ("茶饮", "茶饮", ["奶茶", "果茶", "柠檬茶", "茶饮", "奶盖", "抹茶", "珍珠",
              "奶青", "春茶", "红茶", "青茶", "泡茶"]),
    ("Bar", "威士忌吧", ["威士忌", "whisky", "whiskey"]),
    ("Bar", "精酿啤酒吧", ["精酿", "自酿啤酒", "啤酒", "craft beer"]),
    ("Bar", "葡萄酒/自然酒吧", ["葡萄酒", "自然酒", "红酒", "wine"]),
    ("Bar", "鸡尾酒吧", ["鸡尾酒", "cocktail", "调酒", "金酒", "朗姆"]),
]
ROOT_NAMES = ("咖啡", "面包", "甜品", "Bar", "茶饮")

# 菜级正餐否定：命中非正餐词、但同菜含正餐上下文（咸豆花 / 啤酒烹饪 / 红酒炖煮）→ 该菜算正餐
SAVORY = [
    (["豆花", "豆腐脑"], ["饭", "鱼", "牛蛙", "荤", "肠", "血", "肉", "辣", "沸腾", "烧", "炒"]),
    (["啤酒"], ["鱼", "鸭", "鸡", "肉", "虾", "蟹", "牛腩"]),
    (["红酒", "葡萄酒"], ["炖", "煮", "烩", "牛舌", "牛腩", "肉", "牛排"]),
]

# 正餐主菜词（店级占比，判定正餐主导）
DINER_MAIN = ["龙虾", "螯虾", "蟹", "牛排", "猪肘", "香肠", "烤鸡", "炸鸡", "炖牛", "牛舌",
              "肋排", "rib", "烤鸭", "烤鱼", "火锅", "海鲜", "三文鱼", "热狗", "汉堡",
              "smorrebrod", "鲱鱼", "蛋包饭", "咖喱饭", "牛丼", "烤肉", "炸猪排", "千层面",
              "烩饭", "意面", "猪里脊", "和牛", "taco", "卷", "鱼", "鸡", "肉", "牛", "排"]
PURE_ND = ["刨冰", "冰沙", "奶茶", "蛋糕", "冰淇淋", "gelato", "咖啡", "拿铁", "茶饮",
           "糖水", "松饼", "可丽饼", "布丁", "珍珠", "抹茶", "蛋挞", "贝果", "可颂"]

# 店名强非正餐业态词
NAME_ND = ["刨冰", "冰屋", "可丽饼", "creperie", "松饼", "冰淇淋", "gelato", "冰激凌",
           "咖啡", "coffee", "面包", "bakery", "烘焙", "奶茶", "茶饮", "酒吧", "bar",
           "清吧", "甜品", "甜点", "糖水", "茶楼", "抹茶", "pop"]
# 店名正餐业态词（小样本保护）
NAME_DINER = ["diner", "餐厅", "食堂", "饭", "馆", "bistro", "grill", "扒房", "酒楼", "酒家"]

# 形式标签 id
FORM_ND = {76, 77, 81, 82, 74, 80}
FORM_DINER = {71, 72, 73, 83}
FINE = 71


def _clean_sig(sig):
    if sig is None:
        return []
    if isinstance(sig, str):
        sig = [sig]
    out = []
    for s in sig:
        t = str(s).strip().strip('"[]')
        if t:
            out.append(t)
    return out


def _false_coffee(dish):
    """「美式松饼/美式牛排/美式热狗」里的"美式"是风格，不是美式咖啡。"""
    t = str(dish)
    if "美式" in t and not any(k in t for k in
           ["美式咖啡", "拿铁", "咖啡", "espresso", "latte", "卡布", "澳白", "mocha", "dirty"]):
        if any(w in t for w in ["松饼", "牛排", "热狗", "挞", "饼", "排", "堡", "餐", "风"]):
            return True
    return False


def dish_hits(dish):
    """该菜非正餐命中 [(根,叶)]，已做菜级正餐否定。"""
    t = str(dish).lower()
    hits = [(r, l) for r, l, kws in LEAVES if any(k.lower() in t for k in kws)]
    for nd_words, sv_words in SAVORY:
        if any(w in str(dish) for w in nd_words) and any(w in str(dish) for w in sv_words):
            return []
    if _false_coffee(dish):
        hits = [(r, l) for (r, l) in hits if l != "社区精品咖啡"]
    return hits


# 非正餐"载体"词：命中即该菜以非正餐主体论（松饼/吐司上的培根、可丽饼里的海鲜是配料），不算正餐主菜
CARRIER = ["松饼", "舒芙蕾", "可丽饼", "华夫", "法式吐司", "吐司", "galette",
           "crepe", "pancake", "souffle"]


def _is_diner_main_dish(dish):
    t0 = str(dish)
    if any(k.lower() in t0.lower() for k in CARRIER):
        return False
    if dish_hits(dish) and not any(k in t0 for k in
           ["龙虾", "蟹", "牛排", "猪肘", "鱼", "虾", "鸡", "肉", "肠", "肋", "和牛", "猪排", "排"]):
        return False
    t = t0.lower()
    return any(k.lower() in t for k in DINER_MAIN)


def classify(name, signature_dishes, form_ids=(), form_names=(), current_roots=()):
    """返回主营判定 dict。
    form_ids：库内形式标签 id；form_names：raw 形式名（小写匹配）；
    current_roots：当前已挂的非正餐菜系根 id（辅助咖啡 vs 烘焙仲裁）。"""
    import collections
    sig = _clean_sig(signature_dishes)
    current_roots = set(current_roots or ())
    n = len(sig)
    form_ids = set(form_ids or ())
    form_names = {str(x).lower() for x in (form_names or ())}
    is_fine = (FINE in form_ids) or any("fine" in x and "dining" in x for x in form_names)
    form_nd = bool(form_ids & FORM_ND) or any(
        any(k in x for k in ("brunch", "下午茶", "酒吧", "清吧", "茶馆", "快餐", "外带")) for x in form_names)
    form_diner = bool(form_ids & FORM_DINER)
    nm = (name or "")
    name_nd = any(k.lower() in nm.lower() for k in NAME_ND)
    name_diner = any(k.lower() in nm.lower() for k in NAME_DINER)

    root_c, leaf_c = collections.Counter(), collections.Counter()
    nd_n, dinner_n = 0, 0
    for d in sig:
        h = dish_hits(d)
        if h:
            nd_n += 1
            for ro, lf in h:
                root_c[ro] += 1
                leaf_c[lf] += 1
        if _is_diner_main_dish(d):
            dinner_n += 1

    ratio = nd_n / n if n else 0.0
    dinner_ratio = dinner_n / n if n else 0.0
    root = root_c.most_common(1)[0][0] if root_c else None
    leaf = None
    if root:
        cand = [l for ro, l, _ in LEAVES if ro == root]
        for l, _ in leaf_c.most_common():
            if l in cand:
                leaf = l
                break

    # 咖啡 vs 烘焙（面包/甜品）主营仲裁。
    # 不能"招牌里有一道咖啡就翻咖啡"（PAIN CHAUD/RAC 是烘焙店、咖啡配套）；
    # 也不能让"城是/星巴克"因自烘面包款多被翻成烘焙。综合 店名强信号 + 当前已挂根 + 招牌款数。
    COFFEE_DRINK = ("拿铁", "美式咖啡", "美式", "手冲", "意式", "浓缩", "espresso",
                    "dirty", "澳白", "flat white", "卡布", "latte", "冷萃", "咖啡",
                    "拼配", "单品豆", "mocha", "cappuccino", "虹吸", "冰滴")
    NAME_COFFEE = ("咖啡", "coffee", "roaster", "roastery")
    NAME_BAKERY = ("bakery", "baker", "boulangerie", "patisserie", "面包", "西点",
                   "蛋糕", "甜品", "甜点", "饼屋", "冰淇淋", "冰激凌", "雪糕")
    CHAIN_COFFEE = ("星巴克", "manner", "瑞幸", "tims", "costa", "太平洋咖啡",
                    "peet", "seesaw", "arabica")
    COFFEE_ROOT_ID = 300

    def _is_coffee_dish(d):
        return any(k in str(d).lower() for k in COFFEE_DRINK)

    c_dishes = [d for d in sig if _is_coffee_dish(d)]
    c_n, b_n = len(c_dishes), nd_n - len(c_dishes)
    name_is_coffee = any(k in nm.lower() for k in NAME_COFFEE)
    name_is_bakery = any(k in nm.lower() for k in NAME_BAKERY)
    name_is_chain_coffee = any(k in nm.lower() for k in CHAIN_COFFEE)

    if name_is_chain_coffee:
        want_coffee = True
    elif name_is_coffee and not name_is_bakery:
        want_coffee = True
    elif name_is_bakery and not name_is_coffee:
        want_coffee = False
    elif COFFEE_ROOT_ID in current_roots:
        # 中性名但已挂咖啡根：咖啡是主营，烘焙是配套（城是/星巴克/且乐）
        want_coffee = c_n >= 1 and b_n <= 3 * max(c_n, 1)
    else:
        # 未挂咖啡根：按招牌款数，烘焙明显多则烘焙（PAIN CHAUD/RAC）
        want_coffee = c_n > b_n

    if want_coffee and root in ("面包", "甜品"):
        root = "咖啡"
        leaf_c2 = collections.Counter()
        for d in c_dishes:
            t = str(d).lower()
            if any(k in t for k in ("手冲", "单品", "自烘", "虹吸", "冰滴")):
                leaf_c2["手冲/自烘豆专门"] += 1
            elif any(k in t for k in ("特调", "创意")):
                leaf_c2["创意特调咖啡"] += 1
            else:
                leaf_c2["社区精品咖啡"] += 1
        leaf = leaf_c2.most_common(1)[0][0] if leaf_c2 else "社区精品咖啡"
    if name_is_chain_coffee and root == "咖啡":
        leaf = "连锁咖啡"

    # 小样本保护：招牌 ≤2 且店名是正餐业态、形式无明确非正餐背书 → 不 auto
    small_sample = (n <= 2 and name_diner and not form_nd)
    backing = form_nd or name_nd or ratio >= 0.9
    is_main = (not is_fine) and ratio >= 0.75 and dinner_ratio < 0.25 and backing \
        and (not small_sample) and (not (form_diner and not form_nd and dinner_n > 0))
    needs_review = (not is_main) and ratio >= 0.5
    why = []
    if is_fine: why.append("FineDining")
    if ratio < 0.75: why.append(f"非正餐占比{round(ratio,2)}<0.75")
    if dinner_ratio >= 0.25: why.append(f"正餐主菜占比{round(dinner_ratio,2)}")
    if not backing: why.append("无业态/形式背书")
    if small_sample: why.append("小样本+店名正餐业态")
    return {"is_nondiner_main": bool(is_main), "needs_review": bool(needs_review),
            "root": root, "leaf": leaf, "ratio": round(ratio, 2),
            "dinner_ratio": round(dinner_ratio, 2), "n": n, "nd_n": nd_n,
            "form_nd": form_nd, "name_nd": name_nd, "reason": "; ".join(why)}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cuisine_knowledge.py — 菜系知识学习层（1A-Part2）。

为什么存在：过去"抓了招牌菜关键词却不联动菜系"，且凭名字里的国别/佐餐酒/吧台
机械定类（pain chaud 法式面包被归法餐、有葡萄酒就归法餐/意餐）。本模块把"行家
怎么定义一个菜系的主营"沉淀成**可复用的 canonical 菜品集 + 框架排除规则**，供
cuisine_classify_audit / signature_dish_classifier 调用。

原则（与 north-star 一致）：
- 主营出品是判据，不是名字里的地名/国别词，也不是"菜单上出现一道某菜"。
- 框架排除：一家店的"形态/场景"决定它属于非正餐（面包/甜品/咖啡/茶饮/Bar），
  即使出品带有法国/日本/中国地名，也不挂地域正餐菜系。
- 宁空不假：信号弱返回 None，不硬推。

被调用方：传 signature_dishes(list) + name(str)，返回提案 dict。
"""
from __future__ import annotations
import re
from typing import List, Optional, Dict


# ─────────────────────────────────────────────────────────────────────
# 1. canonical 菜品 → 菜系叶（强证据，招牌菜命中即高置信）
#    键=菜系叶名（与库内 cuisines.name 对齐），值=该叶的 canonical 菜品正则
#    收录标准：这道菜是该品类"主营出品"的标志，不是顺带一道。
# ─────────────────────────────────────────────────────────────────────
DISH2LEAF: Dict[str, List[str]] = {
    # —— 非正餐：面包/烘焙 ——
    "可颂/起酥专门": [r"可颂", r"牛角包", r"起酥", r"丹麦(?!语)"],
    "贝果专门": [r"贝果", r"bagel"],
    "酸种面包专门": [r"酸种", r"sourdough", r"欧包"],
    "日式面包": [r"咖喱面包", r"蜜瓜包", r"生吐司", r"米面包", r"红豆面包"],
    # —— 非正餐：甜品 ——
    "冰淇淋Gelato": [r"gelato", r"意式冰淇淋", r"雪葩"],
    "刨冰": [r"刨冰", r"かき氷", r"冰浆", r"绵绵冰"],
    "糖水/甜汤": [r"糖水", r"甜汤", r"杨枝甘露", r"双皮奶", r"芋圆", r"仙草",
                r"大满贯", r"糖葱", r"椰奶"],
    "蛋糕/法式甜品": [r"千层", r"泡芙", r"马卡龙", r"闪电", r"慕斯", r"巴斯克",
                    r"可丽露", r"费南雪", r"玛德琳", r"蛋挞"],
    "铜锣烧/和果子": [r"铜锣烧", r"和果子", r"羊羹", r"最中", r"鲷鱼烧"],
    # —— 正餐地域：菜级强信号 ——
    "台湾牛肉面·小吃": [r"台湾牛肉面", r"台式牛肉", r"半筋半肉"],
    "兰州牛肉面": [r"兰州牛肉面", r"清汤牛肉", r"牛骨汤面"],
    "日式拉面": [r"豚骨拉面", r"味噌拉面", r"蘸面", r"沾面"],
    "烧鸟": [r"烧鸟", r"烤鸡串"],
    "怀石": [r"怀石", r"会席", r"omakase.*(料理|套餐)"],
    "寿司": [r"江户前", r"板前寿司", r"omakase.*(寿司|鮨)"],
    "潮汕牛肉火锅": [r"潮汕牛肉", r"吊龙", r"匙仁", r"五花趾"],
    "新疆菜": [r"大盘鸡", r"烤包子", r"馕", r"手抓饭", r"羊肉串"],
    "新加坡菜": [r"海南鸡饭", r"叻沙", r"辣椒螃蟹", r"咖椰"],
}

# ─────────────────────────────────────────────────────────────────────
# 2. 框架排除（framework exclusions）：命中这些"形态"时，即使菜品带外国地名，
#    也不挂地域正餐菜系。
# ─────────────────────────────────────────────────────────────────────
# 法式烘焙/简餐：pain chaud / verie / rac 等 boulangerie-pâtisserie-café
# 主营面包/甜品，不挂「法餐」。判据：招牌主体是可颂/面包/泡芙/咖啡，而非
# 法式正餐主菜（油封鸭/牛排鞑靼/勃艮第炖牛肉/法式鹅肝主菜）。
FRENCH_BAKERY = re.compile(r"可颂|面包|法棍|泡芙|蛋挞|丹麦|司康|肉桂卷|贝果|起酥", re.I)
FRENCH_DINER_MAIN = re.compile(r"油封鸭|鸭肝|鹅肝|勃艮第|牛排鞑靼|法式洋葱汤|\bcoq au vin\b|"
                               r"勃艮第炖|羊肚菌烩|煎鸭胸", re.I)

# bistro 判定不凭"有佐餐酒/吧台/红酒"——酒吧/酒是配套形式；主营是餐还是酒才定类。
WINE_PAIRING = re.compile(r"葡萄酒|红酒|自然酒|wine|配酒|佐酒", re.I)


def french_framework_decision(dishes: List[str], name: str) -> Optional[str]:
    """法餐框架：返回应归属，或 None（不属本框架）。
    - 招牌主体是烘焙/甜品且无法式正餐主菜 → 归「面包/甜品」，非法餐。
    - 有法式正餐主菜 → 才考虑法餐（交正餐逻辑）。
    """
    text = " ".join(str(d) for d in dishes)
    if FRENCH_DINER_MAIN.search(text):
        return None  # 有法式正餐主菜，交正餐逻辑，不在这里降级
    if FRENCH_BAKERY.search(text) and re.search(r"boulanger|baker|面包|bakery|chaud|verie|百丘",
                                                name, re.I):
        return "非正餐·面包/甜品"
    return None


def dish_proposals(dishes: List[str], name: str) -> Dict[str, float]:
    """招牌菜 → 菜系叶提案（score 命中条数）。只读、确定性。"""
    text = " ".join(str(d) for d in dishes).lower()
    out: Dict[str, float] = {}
    for leaf, pats in DISH2LEAF.items():
        hits = sum(1 for p in pats if re.search(p, text, re.I))
        if hits:
            out[leaf] = hits
    return out


def explain() -> str:
    return ("cuisine_knowledge: canonical菜品集 %d 叶；法餐框架排除法式烘焙(非法餐)；"
            "bistro 不凭佐餐酒定类。" % len(DISH2LEAF))


if __name__ == "__main__":
    import json
    demo = ["可颂", "法棍", "开心果泡芙", "手冲咖啡"]
    print(explain())
    print("pain chaud dishes ->", dish_proposals(demo, "PAIN CHAUD"))
    print("french framework ->", french_framework_decision(demo, "PAIN CHAUD"))

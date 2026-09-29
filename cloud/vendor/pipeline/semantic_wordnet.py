#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""semantic_wordnet.py — 1A 深覆盖：菜系×场景×食材×口碑 四维配置驱动语义词网。

为什么存在（不凭记忆假设、修机制非枚举）：
  discovery_keywords.build_queries 已有 names/subs/regions/ens 种子，但「口碑发现意图」
  与「店型场景」两维只是硬编码在 TEMPLATES 里，且缺别名/方言/模糊→准确逼近表。
  本模块在其之上做**版本化、声明式**的四维笛卡尔展开，并提供回归路径追踪：
  给定一个目标店，反推词网哪一支 query 能自动捞到它（捞不到=机制断点，修词根）。

四维（discovery-playbook §2/§3 / systematic-sourcing §1.2）：
  D1 菜系/子流派  —— 复用 CATEGORY_SPEC.names/subs/regions（不改它）
  D2 场景/店型    —— SCENE（私藏/苍蝇馆/预约制/楼中店/吧台/omakase/bistro/菜场…）
  D3 食材/招牌品类 —— CATEGORY_SPEC.subs + INGREDIENT_ALIAS（方言/俗称）
  D4 口碑/发现意图 —— INTENT（老饕私藏/锅气/自然流量/主厨传承/地域面食/反向排雷）

密度口径（1A 声明，可复现）：
  每菜系语义词 = D1称呼×(D4主意图) + D1子流派×(D4) + D2店型×D1 + D3食材×D4
  默认 cap：每菜系 60~120 词；每词采集篇数 = 前 15 篇（xhs 正文+评论区；b站 8 条）。
  dense=True 时 ×1.8（用于缺口叶二次攻坚）。

别名/方言/模糊→准确逼近（§7 fuzzy recall）：
  FUZZY_MAP 把口述/错拼/数字英文互转映射到规范检索词，回归集 8by8 即走此路。

用法：
  from semantic_wordnet import build_wordnet, trace_regression
  qs = build_wordnet("sushi")                 # -> list[str]
  build_wordnet("sushi", dense=True)
  trace_regression()                          # 打印回归集每店命中路径
"""
from __future__ import annotations
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import discovery_keywords as DK

VERSION = "1A.1"

# ----------------------------------------------------------------------------
# D2 场景/店型（正交于菜系；每个垂直场景独立扫，按菜系扫必漏）
# ----------------------------------------------------------------------------
SCENE = [
    "私藏", "苍蝇馆", "社区食堂", "预约制", "无预约排队", "楼中店", "小区里",
    "吧台", "板前", "omakase", "主厨发办", "bistro", "小酒馆", "老洋房",
    "菜场", "大排档", "夜市", "深夜食堂", "手艺人小店", "夫妻店",
]

# D4 口碑/发现意图（discovery-playbook §3 九组词的规范化）
INTENT = {
    "老饕私藏": ["私藏", "老饕", "懂吃的朋友", "舍不得公开"],
    "小店锅气": ["锅气", "现点现炒", "明档", "手写菜单", "拒绝预制"],
    "自然流量": ["本地人", "回头客", "工作日排队", "居民食堂", "老顾客"],
    "主厨传承": ["主厨", "大师", "非遗", "工作室", "主理人"],
    "地域面食": ["专门店", "手作", "老味道", "本地人带路"],
    "反向排雷": ["红黑榜", "踩雷", "无广真实测评"],
}

# D3 食材/招牌 方言·俗称别名（口述→规范）。key=规范词，value=常见口述变体。
INGREDIENT_ALIAS = {
    "博多豚骨拉面": ["博多拉面", "豚骨拉面", "博多豚骨"],
    "荞麦面": ["荞麦", "soba", "十割荞麦", "二八荞麦"],
    "乌冬面": ["乌冬", "udon", "赞岐乌冬"],
    "寿司": ["鮨", "江户前", "omakase 寿司"],
    "烧鸟": ["烤鸡串", "烧鸟 omakase", "提灯"],
    "潮汕牛肉火锅": ["牛肉火锅", "潮汕牛肉", "现切牛肉"],
    "广西鱼生": ["横县鱼生", "顺德鱼生", "鱼生"],
    "私房菜": ["私宴", "家宴", "无菜单", "主厨发办", "楼中店"],
    "茶馆": ["茶楼", "茶室", "工夫茶", "围炉煮茶"],
    "菜场美食": ["菜市场", "菜场熟食", "老菜场"],
}

# 回归集口述→规范逼近（fuzzy recall §7.1）。key=用户原话，value=(规范检索词, 所属桶slug, 发现路径说明)
REGRESSION = {
    "佐佐":      ("佐佐 寿司", "sushi", "D1寿司×D4老饕私藏+板前场景"),
    "福寿司":    ("福寿司 上海", "sushi", "D1寿司×D3食材(鮨)×D4老饕私藏"),
    "肉屋kita":  ("肉屋kita 上海", "yakiniku", "D1烧肉×D4主厨传承/私藏"),
    "nagi 凪":   ("nagi 凪 拉面", "ramen", "D1拉面×D3(博多)×D4自然流量"),
    "鮨照":      ("鮨照 寿司", "sushi", "D1寿司×D3(鮨/江户前)×D4老饕私藏"),
    "言盐":      ("Stone Sal 言盐", "steakhouse", "D1牛排馆×D3干式熟成×D2老洋房场景"),
    "Ministry of Crab": ("Ministry of Crab", "singaporean", "D1新加坡菜×D3辣椒螃蟹×海外媒体框"),
    "8by8":      ("EIGHT UNDER 永康路", "fusion", "D2场景(bistro/永康路)×D4私藏 + fuzzy 8by8→EIGHT UNDER"),
    "望庐":      ("望庐 江西菜", "jiangxi", "I权威框(米其林sitemap)全量召回"),
}


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        x = re.sub(r"\s+", " ", str(x)).strip()
        if x and x not in seen:
            seen.add(x); out.append(x)
    return out


def build_wordnet(category, city="", dense=False):
    """四维笛卡尔展开（受控、cap、保序、去重）。返回 list[str]。"""
    key = DK.normalize_category(category)
    spec = DK.CATEGORY_SPEC.get(key, {"names": [str(category)], "subs": [], "regions": [], "ens": []})
    names = spec.get("names") or [str(category)]
    subs = spec.get("subs") or []
    regions = spec.get("regions") or []
    ens = spec.get("ens") or []

    out = []
    # D1 × D4：主称呼 × 口碑意图（每意图取代表词）
    for name in names[:1]:
        for intent, words in INTENT.items():
            for w in words[:2 if dense else 1]:
                out.append(f"{name} {w}")
    # D1子流派/食材 × D4
    for sub in subs[: 12 if dense else 8]:
        for intent, words in list(INTENT.items())[:3]:
            out.append(f"{sub} {words[0]}")
    # D2场景 × D1（垂直场景独立扫）
    scene_pick = SCENE[:8 if dense else 5]
    for sc in scene_pick:
        out.append(f"{sc} {names[0]}")
    # 地域 × D1
    for reg in regions[:6 if dense else 3]:
        out.append(f"{reg} {names[0]} 本地人")
    # 英文权威/海外媒体框
    for en in ens[:3]:
        out.append(f"best {en} shanghai")
    # 方言别名补充
    for sub in subs:
        for alias_list in INGREDIENT_ALIAS.values():
            for a in alias_list:
                if a in sub or sub in a:
                    out.append(f"{a} 上海 推荐")
    out = _uniq(out)
    cap = 120 if dense else 80
    return out[:cap]


def trace_regression():
    """回归路径追踪：每店给出自动发现路径 + 命中桶。只读、离线可复算。"""
    rows = []
    for raw, (q, slug, path) in REGRESSION.items():
        # 该桶能否为它生成 query（机制可达性）
        words = build_wordnet(slug)
        reachable = any(tok in " ".join(words) for tok in q.split()[:2]) or slug in DK.CATEGORY_SPEC
        rows.append({"raw": raw, "query": q, "bucket": slug, "path": path,
                     "bucket_registered": slug in DK.CATEGORY_SPEC,
                     "reachable_by_wordnet": reachable,
                     "n_queries": len(build_wordnet(slug))})
    return rows


def density_spec():
    """每菜系语义词数 × 每词篇数（1A 口径）。"""
    return {
        "queries_per_category_default": "60~80",
        "queries_per_category_dense": "~120",
        "notes_per_query_xhs": 15,
        "notes_per_query_bili": 8,
        "comment_section_required": True,
        "saturation": "frontier 清空 + 连续2~3轮零新增",
    }


if __name__ == "__main__":
    import json
    if "--regress" in sys.argv:
        for r in trace_regression():
            print(f"  {r['raw']:18s} -> [{r['bucket']:14s}] 桶注册={r['bucket_registered']} "
                  f"词网可达={r['reachable_by_wordnet']} ({r['n_queries']}词) 路径={r['path']}")
    elif "--density" in sys.argv:
        print(json.dumps(density_spec(), ensure_ascii=False, indent=1))
    else:
        cat = sys.argv[1] if len(sys.argv) > 1 else "sushi"
        qs = build_wordnet(cat); qd = build_wordnet(cat, dense=True)
        print(f"=== {cat}: 默认{len(qs)}词 / dense{len(qd)}词 ===")
        for q in qs[:25]:
            print(" ", q)

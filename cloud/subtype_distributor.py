#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""subtype_distributor.py — 招牌菜联动归类：把 category 根下在营店分发到 subtype 细叶。

为什么存在（细叶分发）：candidate_apply 收录新店时只挂菜系【根】，细叶 n_active 不增长。
本模块是下游、确定性的「招牌菜 → 细叶」归类 pass，**只新增标签、不改其它字段、不删标签**。

机制（数据驱动 + 词典，不靠逐店枚举）：
  - 工作单元复用 gap_runner.category_worklist / category_supply（LCA 根 + 细叶）。
  - 每个细叶的指示词 = LEAF_KW  curated 表（leaf_id→词，权威）＋叶名自动派生（兜底）。
    新增细叶/风格：在 LEAF_KW 加词即可，引擎不变。
  - 两类分发：
      · 风格叶（cuisine 根，如拉面/荞麦/乌冬/甜品…）：根下店本就是该品类专门店，按
        店名/招牌菜/英文名的风格标记打分，取唯一最高分（要求领先），无信号留根。
      · 形式叶（form 根，包馅面食/饼/茶饮）：先过【主营专门店门槛】——店名含品类标记，
        或 ≥2 招牌菜属该品；正餐大店名不副实、仅一道菜沾边的一律不挂，避免污染细叶。
  - 宁空不假；不确定/并列 → 留根，输出 hold 清单。

用法：python3 subtype_distributor.py [--category ramen] [--commit]
"""
import argparse
import collections
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
for p in ("/app/pipeline", "/app/cloud", str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C              # noqa: E402
import gap_runner as G         # noqa: E402
import category_resolver as R  # noqa: E402

# ───────────────────────── curated 细叶指示词（leaf_id -> [kw...]）─────────────────────────
# 风格/概念级同义词（含英文/罗马字/假名），不是逐店、逐菜枚举。
LEAF_KW = {
    # ramen（根 89）
    264: ["博多", "豚骨", "tonkotsu", "hakata", "赤丸", "白丸", "背脂", "とんこつ"],
    265: ["蘸面", "沾面", "tsukemen", "つけ麺", "つけめん"],
    266: ["二郎", "jiro", "二郎系"],
    267: ["家系", "横滨", "横浜", "iekei", "横浜家系"],
    268: ["纪州", "醤油豚骨", "酱油豚骨"],
    269: ["熊本", "黑蒜", "黑麻油", "kumamoto", "黑蒜油", "蒜味"],
    262: ["虾白汤", "虾汤", "海老白汤", "鲜虾汤", "えび"],
    263: ["鸡白汤", "柚子盐", "盐味鸡", "鸡汤", "柚子塩", "とり白汤"],
    # soba（根 261）
    272: ["十割", "二八", "生粉打", "生粉", "十割蕎麦"],
    270: ["冷荞麦", "山药泥", "笊荞麦", "ざるそば", "冷やし", "山かけ"],
    271: ["天妇罗荞麦", "天ぷらそば", "天盛", "天妇罗盛"],
    # udon（根 236）
    273: ["赞岐", "讃岐", "sanuki", "丸龟", "丸亀", "marugame"],
    274: ["咖喱乌冬", "カレーうどん", "咖喱うどん"],
    275: ["手打乌冬", "手打ち", "手打"],
    # stuffed 包馅面食（根 326，形式叶）
    332: ["烧卖", "烧麦", "shumai", "焼売", "肖米"],
    340: ["汤包", "小笼", "灌汤包", "xiaolongbao", "小笼馒头", "蟹粉小笼", "小笼包"],
    341: ["包子", "肉包", "菜包", "大肉包", "baozi", "三丁包", "大包"],
    329: ["锅贴", "potsticker", "煎饺", "锅贴儿"],
    333: ["汤圆", "汤团", "元宵", "tangyuan", "黑芝麻汤团", "圆子"],
    # dessert 甜品（根 302）
    344: ["可丽饼", "crepe", "crêpe", "甜可丽", "クレープ"],
    345: ["舒芙蕾", "松饼", "pancake", "pan cake", "hotcake", "パンケーキ", "奇迹舒", "厚松饼"],
    314: ["刨冰", "shaved ice", "かき氷", "冰沙", "炒冰"],
    318: ["铜锣烧", "和果子", "和菓子", "だんご", "団子", "最中", "どら焼き"],
    # french 法餐（根 26）
    351: ["bistro", "bistrot", "小酒馆", "自然酒", "杯卖酒", "wine bar", "酒馆",
           "法式小酒馆", "小酒馆菜", "前菜拼盘", "cuivre", "polux", "saleya",
           "verre", "nuits", "coquille"],
    189: ["可颂", "croissant", "boulangerie", "patisserie", "法式面包", "牛角包"],
    # tea_drink 茶饮（根 324，形式叶）
    352: ["新中式茶饮", "中式茶", "原叶茶", "普洱", "岩茶", "白茶", "龙井", "宋代点茶",
          "茶馆", "茶楼", "茶社", "茶集", "煮茶", "中国茶"],
    354: ["港式奶茶", "丝袜奶茶", "港式", "hong kong milk", "港式茶"],
    353: ["奶茶专门", "milk tea", "奶茶店"],
}

# 形式根 category（需要主营专门店门槛）；其余按风格叶处理。
FORM_CATEGORIES = {"stuffed", "bing", "tea_drink"}

# 强「形式定义」词：决定品类形态（蘸面/二郎/家系/松饼…），权重高于泛汤头词（豚骨/盐/味噌）。
STRONG_TERMS = {"蘸面", "沾面", "二郎", "二郎系", "家系", "十割", "二八",
                "舒芙蕾", "松饼", "可丽饼", "法式小酒馆"}

# 人工复核例外（rid）：语义陷阱，单独一道菜形似但非该品类主营，强制 hold。
# 不是逐店枚举，而是已 review 的例外登记；新增需写明理由。
HOLD_OVERRIDE = {
    1486: "汕鹤潮式甜汤：糖葱可丽饼为潮汕传统小吃，非西式可丽饼专门店",
}


def _strip_note(dish):
    """去掉菜名末尾括号注释，便于判「头名词」。"""
    s = str(dish)
    for l, r in (("（", "）"), ("(", ")")):
        if l in s:
            s = s.split(l)[0]
    return s.strip()


# 店名命中权重：店名是最强的主营信号（如「横滨家系」「无锡小笼」），应压过泛汤头词次。
NAME_WEIGHT = 4

# 负向语境（leaf_id -> [出现即不算命中的上下文]）：防子串假阳性。
LEAF_EXCLUDE = {
    329: ["地锅", "贴饼"],          # 地锅贴饼/锅贴饼是贴饼子，非锅贴
}


# ───────────────────────── 树/账本辅助 ─────────────────────────
def _children_map(byid, byname):
    children = collections.defaultdict(list)
    for cid, row in byid.items():
        p = R._parent(row, byid, byname)
        if p:
            children[p["id"]].append(cid)
    return children


def _subtree(root, children):
    out, stack = {root}, [root]
    while stack:
        c = stack.pop()
        for ch in children.get(c, []):
            if ch not in out:
                out.add(ch)
                stack.append(ch)
    return out


def _auto_terms(leaf_name):
    """从叶名自动派生指示词：取「·」后子名，再按分隔符拆片段。"""
    sub = str(leaf_name)
    if "·" in sub:
        sub = sub.split("·")[-1]
    terms = [sub]
    for sep in ("/", "、", "（", "(", "·", " "):
        sub = sub.replace(sep, " ")
    for tok in sub.split():
        if len(tok) >= 2 and tok not in terms:
            terms.append(tok)
    return [t for t in terms if t and t not in ("系",)]


def _leaf_terms(leaf_id, leaf_name):
    terms = list(LEAF_KW.get(int(leaf_id), []))
    for t in _auto_terms(leaf_name):
        if t not in terms:
            terms.append(t)
    return terms


def _norm(s):
    return C.cjk_norm(str(s or ""))


# ───────────────────────── 单店打分 ─────────────────────────
def _dish_match(dish, terms, excludes=()):
    """一道菜对某细叶的命中：返回 (effective_weight, is_strong_head)。
    - 命中的词若在菜名【头位】（去注释后以该词结尾）且属强形式词 → 3 分、strong_head；
    - 强形式词作修饰（后接 拉面/面/荞麦/乌冬 等头名）→ 降为 1 分；
    - 普通词一律 1 分。同一道菜只取最高分，杜绝「小笼/小笼包」重复计数。
    - 命中负向语境（excludes）→ 视为不命中（如 地锅贴饼 ≠ 锅贴）。
    """
    d = _norm(dish)
    if any(_norm(x) in d for x in excludes):
        return 0, False
    head = _norm(_strip_note(dish))
    best, strong_head = 0, False
    for t in terms:
        tt = _norm(t)
        if tt and tt in d:
            if tt in STRONG_TERMS and head.endswith(tt):
                best, strong_head = 3, True
            elif best < 1:
                best = 1
    return best, strong_head


def classify_restaurant(cat, leaves, r):
    """返回 (best_leaf_id or None, debug_str)。"""
    if r.get("id") in HOLD_OVERRIDE:
        return None, "override:" + HOLD_OVERRIDE[r["id"]][:18]

    name = _norm(r.get("name"))
    name_en = _norm(r.get("name_en"))
    dishes = r.get("signature_dishes") or []
    if isinstance(dishes, str):
        dishes = [dishes]
    sem = _norm(r.get("semantic_description"))

    form_mode = cat in FORM_CATEGORIES
    scored = []
    for leaf_id, leaf_name in leaves:
        terms = [_norm(t) for t in _leaf_terms(leaf_id, leaf_name)]
        terms = [t for t in terms if t]
        excludes = LEAF_EXCLUDE.get(int(leaf_id), [])
        name_hit = any(t in name or t in name_en for t in terms)
        support, n_dishes, has_strong_head = 0, 0, False
        for dish in dishes:
            w, sh = _dish_match(dish, terms, excludes)
            if w:
                support += w
                n_dishes += 1
                has_strong_head = has_strong_head or sh
        if name_hit:
            support += NAME_WEIGHT  # 店名主营信号，压过泛词次
        # 简介里的命中只作弱补充（+1，至多 1），不构成主营证据
        if not name_hit and n_dishes == 0 and any(t in sem for t in terms):
            support += 1
        scored.append({"leaf": leaf_id, "name_hit": name_hit,
                       "support": support, "n": n_dishes,
                       "strong_head": has_strong_head})

    scored.sort(key=lambda x: -x["support"])
    B, S = scored[0], scored[1]["support"] if len(scored) > 1 else 0
    if B["support"] <= 0 or B["support"] <= S:
        return None, (f"no-signal" if B["support"] <= 0
                      else f"tie({B['support']}={S})")

    # 统一判定（precision-first）：必须领先，且有主营证据。
    # 形式叶：店名命中 或 ≥2 道不同菜；风格叶还允许「强头名单菜」。
    ok = B["name_hit"] or B["n"] >= 2
    if not form_mode and not ok and B["strong_head"]:
        ok = True
    if not ok:
        return None, f"weak(nh{B['name_hit']},n{B['n']})"

    return B["leaf"], (f"sup={B['support']}(nh{B['name_hit']},"
                       f"n{B['n']},head{B['strong_head']},lead{B['support']-S})")


# ───────────────────────── 写库 ─────────────────────────
def _insert(rid, leaf_id):
    r = __import__("requests").post(
        C.BASE + "/restaurant_cuisines", headers=C.headers(),
        json={"restaurant_id": rid, "cuisine_id": leaf_id}, timeout=30)
    return r.status_code in (200, 201) or "23505" in r.text


# ───────────────────────── 主流程 ─────────────────────────
def run(only_cat="", commit=False):
    wl = G.category_worklist()
    R.load_cuisines()
    byid, byname = R._CACHE["by_id"], R._CACHE["by_name"]
    children = _children_map(byid, byname)

    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    tag2rids = collections.defaultdict(set)
    for x in rc:
        tag2rids[x["cuisine_id"]].add(x["restaurant_id"])

    rests = C.fetch_all(
        "restaurants",
        "id,name,name_en,signature_dishes,semantic_description,status",
        order_col="id")
    byrid = {r["id"]: r for r in rests}

    report = {}
    for cat, e in wl.items():
        if only_cat and cat != only_cat:
            continue
        cs = G.category_supply(cat, wl)
        if not cs:
            continue
        root = cs["root_id"]
        leaf_pairs = [(int(l), byid[int(l)]["name"]) for l in e["leaves"]
                      if int(l) in byid]
        distinct = [(i, n) for i, n in leaf_pairs if i != root]
        if not distinct:
            continue  # 单叶/根即叶，无需分发

        sub = _subtree(root, children)
        cand = set()
        for n in sub:
            cand |= tag2rids.get(n, set())
        already = set()
        for i, _ in distinct:
            already |= tag2rids.get(i, set())
        cand = sorted(cand - already)

        assigns, holds = [], []
        for rid in cand:
            r = byrid.get(rid)
            if not r or r.get("status") != "active":
                continue
            leaf_id, dbg = classify_restaurant(cat, distinct, r)
            if leaf_id:
                assigns.append((rid, r["name"], leaf_id, dbg))
            else:
                holds.append((rid, r["name"], dbg))

        if commit:
            done = 0
            for rid, _n, leaf_id, _d in assigns:
                if _insert(rid, leaf_id):
                    done += 1
                time.sleep(0.15)
            applied = done
        else:
            applied = 0

        report[cat] = {"root": root, "candidates": len(cand),
                       "assign": len(assigns), "hold": len(holds),
                       "applied": applied}
        print(f"\n[{cat}] root={root} candidates={len(cand)} "
              f"assign={len(assigns)} hold={len(holds)}"
              f"{'  >>> COMMITTED ' + str(applied) if commit else '  (dry)'}")
        for rid, nm, leaf_id, dbg in assigns:
            tgt = next((n for i, n in distinct if i == leaf_id), leaf_id)
            print(f"    + {rid} {nm} -> {tgt}  [{dbg}]")
        for rid, nm, dbg in holds:
            print(f"    . {rid} {nm}  ({dbg})")

    tot_a = sum(v["assign"] for v in report.values())
    tot_h = sum(v["hold"] for v in report.values())
    print(f"\n===== 合计：可分发 {tot_a}，hold {tot_h}，覆盖 category {len(report)} =====")
    if not commit:
        print("dry-run，确认后加 --commit。")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    run(args.category, args.commit)

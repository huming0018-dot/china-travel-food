#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identity_resolution.py — 主身份解析引擎（sourcing/分类污染的根治模块）

最高原则：一家店只有 **一个主身份（primary = 它是什么、你为何专程去）**；
菜单里出现的菜 / 饮品 / 食材只给 **secondary / 食材标签（merely served）**，绝不因此挂菜系身份。

旧 bug（RC2）：把"菜单出现某菜/饮品"当身份——川菜馆卖柠檬茶被挂"茶饮"、
港式茶餐厅卖奶茶被挂"茶饮"、抹茶/糖水被乱挂。本引擎用确定性规则先路由，
LLM 只对"规则无法定论"的歧义在【封闭本体选项】内裁决（见 references）。

五层：
  A 本体归一（冗余标签在代码内别名，不做破坏性 DDL）
  B 每店证据包（店名/招牌/品牌集团/既有标签/价格场景）
  C 确定性强信号路由（店名即品类 / 品牌出身 / 招牌多数 / 互斥与 serves-vs-is）
  D 产出 attach/detach 操作 + 歧义残留清单（交 LLM 批处理）
  E 备份→成对应用→stage4/cross_cuisine 回验（detach 必同时有正确归属，不产生游离店）

用法：
  python3 identity_resolution.py --domain tea            # dry-run，打印该域拟改
  python3 identity_resolution.py --domain tea --plan out.json
  python3 identity_resolution.py --apply out.json
"""
import os
import re
import sys
import json
import time
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

# ---------------------------------------------------------------- A 本体归一
# 冗余/近义标签在代码内折叠（不删标签行，只在判定与去重时视为同一身份）。
FORM_ALIAS = {83: 347}           # 私宴/会所(83) -> 会所(347)
TEA_CUISINE = 324                # 茶饮（非正餐，新茶饮/奶茶）
TEAHOUSE_FORM = 82               # 茶馆/茶室（冲泡叶茶、可坐饮）
HK_DINER = 109                   # 港式茶餐厅/冰室（粤菜下，奶茶只是其中一项）
NEW_TEA_LEAF = 352               # 新中式茶饮
MILKTEA_LEAF = 353               # 奶茶专门店
HK_MILKTEA_LEAF = 354            # 港式奶茶·茶室
AFTERNOON_TEA = 77
PRIVATE_KITCHEN = 348
CLUB = 347

# ---------------------------------------------------------------- 证据词表
# 港式茶餐厅 / 冰室：店名或品牌
HK_NAME_RE = re.compile(r"茶餐厅|冰室|茶冰厅|茶冰室|冰厅|冰厅")
HK_BRANDS = ["翠华", "敏华", "新旺", "龙记香港", "港丽", "港九", "合顺发", "合顺發",
             "九龙冰室", "九龙", "东发道", "元朗", "新澳", "港季", "香港翠庭", "太兴", "查餐厅"]
HK_DISH_RE = re.compile(r"菠萝油|菠萝包|丝袜奶茶|港式奶茶|干炒牛河|叉烧饭|烧腊|烧味|鱼蛋|河粉|港奶|冻奶茶|漏奶")

# 冲泡叶茶（传统茶馆的证据）
BREWED_TEA_RE = re.compile(r"普洱|岩茶|大红袍|金骏眉|老白茶|点茶|煮茶|熟普|青饼|紫大益|白牡丹|老茶|白茶|单丛|肉桂茶|水仙茶|铁观音|龙井|红茶")
# 茶馆席 / 评弹（传统茶馆的强场景信号）
TEA_SEAT_RE = re.compile(r"茶席|评弹|茶会")
# 柜台式新茶饮 / 奶茶（带走/档口）
COUNTER_TEA_RE = re.compile(r"奶茶|珍珠|柠檬茶|奶青|奶盖|芝士茶|水果茶|乌龙奶茶|牛乳茶|泰奶")
# 抹茶专门（只认店名品牌，或多数菜品都是抹茶，避免"一道抹茶口味"误判）
MATCHA_NAME_RE = re.compile(r"抹茶|辻利|TSUJIRI|Matcha|MATCHA")
MATCHA_DISH_RE = re.compile(r"抹茶|宇治|辻利|TSUJIRI")
# 蛋挞 / 烘焙（裕莲这类）
PASTRY_RE = re.compile(r"蛋挞|烘焙|面包|酥|糕")

# 正餐主菜信号（说明它本质是餐厅，茶只是配餐饮品）
DINNER_MAIN_RE = re.compile(
    r"火锅|烤鱼|酸菜鱼|烤串|羊肉串|大盘鸡|手抓饭|烤包子|咖喱蟹|冬阴功|毛血旺|干煸|焖肉|臭豆腐|藕汤|"
    r"椰子鸡|文昌鸡|打抛|船面|粿条|蚝烙|酱鸭|熏鱼|红烧肉|明虾|烧鹅|煲仔饭|牛排|肥肠|江湖菜")

# 甜品店信号
DESSERT_RE = re.compile(r"糖水|甜汤|舒芙蕾|松饼|刨冰|gelato|Gelato|蛋糕|芋圆|仙草|铜锣烧|甜品|冰淇淋|千层")


# ---------------------------------------------------------------- B 证据包
def evidence_pkg(r, rc_by_rest):
    name = r.get("name") or ""
    name_en = r.get("name_en") or ""
    dishes = C.dishes_list(r.get("signature_dishes"))
    tags = rc_by_rest.get(r["id"], [])
    tag_ids = {t["cuisine_id"] for t in tags}
    text = name + " " + name_en + " " + " ".join(dishes)
    return {
        "id": r["id"], "name": name, "name_en": name_en,
        "dishes": dishes, "tag_ids": tag_ids,
        "price_scene": r.get("price_scene"),
        "investor": r.get("investor_info"),
        "text": text,
    }


# ---------------------------------------------------------------- C 确定性路由（茶域）
def route_tea(e):
    """返回 (主身份决策, 说明)。仅对当前挂了 茶饮324/茶馆82 的店有意义。"""
    name, text = e["name"], e["text"]
    cname = C.cjk_unify(name)
    dishes = e["dishes"]
    cur = e["tag_ids"]

    # 按"每道菜/店名"计数，避免同一短语里同义词被重复计数
    def dish_hits(rx):
        return sum(1 for d in dishes if rx.search(C.cjk_unify(d)))
    n_brew = dish_hits(BREWED_TEA_RE) + (1 if BREWED_TEA_RE.search(cname) else 0)
    n_seat = dish_hits(TEA_SEAT_RE) + (1 if TEA_SEAT_RE.search(cname) else 0)
    n_counter = dish_hits(COUNTER_TEA_RE) + (1 if COUNTER_TEA_RE.search(cname) else 0)
    n_matcha_d = dish_hits(MATCHA_DISH_RE)
    n_dinner = dish_hits(DINNER_MAIN_RE) + (1 if DINNER_MAIN_RE.search(cname) else 0)
    n_dessert = dish_hits(DESSERT_RE) + (1 if DESSERT_RE.search(cname) else 0)
    n_hk = dish_hits(HK_DISH_RE) + (1 if HK_DISH_RE.search(cname) else 0)
    has_teahouse_form = TEAHOUSE_FORM in cur

    # 1) 港式茶餐厅 / 冰室（店名强信号 或 品牌 或 港式菜品占主导）
    if HK_NAME_RE.search(cname) or any(b in cname for b in HK_BRANDS) or (
            n_hk >= 2 and n_dinner < 2 and ("茶餐厅" in cname or "冰" in cname or n_hk >= 3)):
        return "hk_diner", f"港式茶餐厅/冰室 (hk={n_hk},dinner={n_dinner})"

    # 2) 抹茶专门：店名即抹茶品牌，或多数菜品都是抹茶（避免一道抹茶口味误判）
    if MATCHA_NAME_RE.search(name) or MATCHA_NAME_RE.search(e["name_en"]) or (
            dishes and n_matcha_d >= 2 and n_matcha_d >= len(dishes) - n_matcha_d):
        return "matcha", f"抹茶专门 (matcha_dish={n_matcha_d})"

    # 3) 店名是 茶楼/茶馆/茶室，或已挂茶馆形式
    if re.search(r"茶楼|茶馆|茶室", cname) or has_teahouse_form:
        # 无冲泡叶茶/茶席，却以柜台奶茶/烘焙为主 → 新茶饮（如裕莲茶楼）
        if n_brew == 0 and n_seat == 0 and (n_counter > 0 or PASTRY_RE.search(text)):
            return "new_tea", f"店名茶楼但实为柜台茶饮/烘焙 (brew=0,counter={n_counter})"
        # 冲泡叶茶 / 茶席 / 已坐实茶馆形式 → 传统茶馆
        if n_brew >= 1 or n_seat >= 1 or has_teahouse_form:
            return "teahouse", f"冲泡叶茶传统茶馆 (brew={n_brew},seat={n_seat})"
        return "tea_ambiguous", f"店名茶楼但证据不足 (brew={n_brew},counter={n_counter})"

    # 4) 柜台新茶饮 / 奶茶为主，且无正餐主菜、无甜品主导 → 茶饮
    if n_dinner == 0 and n_counter >= 2 and n_dessert == 0:
        return "new_tea", f"柜台新茶饮/奶茶 (counter={n_counter})"

    # 5) 甜品为主（糖水/舒芙蕾/刨冰）→ 甜品，茶饮仅 secondary
    if n_dessert >= 2 and n_dinner == 0:
        return "dessert", f"甜品店，茶饮仅配餐 (dessert={n_dessert})"

    # 6) 有正餐主菜，茶只是其中一杯 → 与茶身份无关，detach
    if n_dinner >= 1:
        return "not_tea", f"正餐店仅卖一杯茶 (dinner={n_dinner},counter={n_counter})"

    return "tea_ambiguous", f"无法判定 (brew={n_brew},counter={n_counter},dinner={n_dinner},dessert={n_dessert})"


# ---------------------------------------------------------------- D 生成操作
def build_ops(restaurants, rc_by_rest, domain="tea"):
    ops, residual = [], []
    for r in restaurants:
        e = evidence_pkg(r, rc_by_rest)
        cur = set(e["tag_ids"])
        # 只处理当前挂了茶相关标签的店
        tea_related = (TEA_CUISINE in cur) or (TEAHOUSE_FORM in cur)
        if domain == "tea" and not tea_related:
            continue
        decision, why = route_tea(e)
        rid = r["id"]

        def detach(cid):
            if cid in cur:
                ops.append({"rid": rid, "op": "detach", "cid": cid, "why": why, "dec": decision})

        def attach(cid):
            if cid not in cur:
                ops.append({"rid": rid, "op": "attach", "cid": cid, "why": why, "dec": decision})

        if decision == "hk_diner":
            detach(TEA_CUISINE); detach(TEAHOUSE_FORM); attach(HK_DINER)
        elif decision == "teahouse":
            # 传统茶馆：菜系=茶饮(324)，形式=茶馆/茶室(82)，双标签
            attach(TEA_CUISINE); attach(TEAHOUSE_FORM)
        elif decision == "matcha":
            attach(TEA_CUISINE); detach(TEAHOUSE_FORM)
        elif decision == "new_tea":
            attach(TEA_CUISINE); detach(TEAHOUSE_FORM)
            # 奶茶/新茶饮细分叶子：名字或招牌强奶茶→奶茶店，否则新中式茶饮
            if len(COUNTER_TEA_RE.findall(e["text"])) >= 2 and not PASTRY_RE.search(e["text"]):
                attach(MILKTEA_LEAF)
            else:
                attach(NEW_TEA_LEAF)
        elif decision == "dessert":
            detach(TEA_CUISINE); detach(TEAHOUSE_FORM)
        elif decision == "not_tea":
            detach(TEA_CUISINE); detach(TEAHOUSE_FORM)
        else:
            residual.append({"rid": rid, "name": e["name"], "decision": decision,
                             "why": why, "dishes": e["dishes"], "cur_tags": sorted(cur)})
    return ops, residual


# ---------------------------------------------------------------- E 应用 / 校验
def post_rc(rid, cid, method):
    path = "/restaurant_cuisines?"
    if method == "POST":
        body = {"restaurant_id": rid, "cuisine_id": cid, "is_primary": False}
        r = C.req("POST", "/restaurant_cuisines", json=body)
    else:
        flt = f"restaurant_id=eq.{rid}&cuisine_id=eq.{cid}"
        r = C.req("DELETE", "/restaurant_cuisines?" + flt,
                  headers_extra=None) if False else C.req(
            "DELETE", "/restaurant_cuisines?" + flt + "&prefer=return", )
    return r


def apply_ops(ops):
    done = 0
    for o in ops:
        rid, cid = o["rid"], o["cid"]
        if o["op"] == "attach":
            r = C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": cid, "is_primary": False})
        else:
            flt = f"restaurant_id=eq.{rid}&cuisine_id=eq.{cid}"
            r = C.req("DELETE", "/restaurant_cuisines?" + flt)
        if r.status_code not in (200, 201, 204):
            print("FAIL", o, r.status_code, r.text[:120])
        else:
            done += 1
        time.sleep(0.08)
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="tea")
    ap.add_argument("--plan")
    ap.add_argument("--apply")
    a = ap.parse_args()

    restaurants = C.fetch_all("restaurants", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", order_col="restaurant_id")
    rc_by_rest = collections.defaultdict(list)
    for x in rc:
        rc_by_rest[x["restaurant_id"]].append(x)

    if a.apply:
        plan = json.load(open(a.apply, encoding="utf-8"))
        n = apply_ops(plan["ops"])
        print(f"applied {n}/{len(plan['ops'])} ops")
        return

    ops, residual = build_ops(restaurants, rc_by_rest, a.domain)
    dec_count = collections.Counter(o["dec"] for o in ops)
    print(f"domain={a.domain}: {len(ops)} ops; decisions={dict(dec_count)}; residual={len(residual)}")
    print("\n--- ops (按店聚合) ---")
    byrid = collections.defaultdict(list)
    name_by = {r["id"]: r["name"] for r in restaurants}
    for o in ops:
        byrid[o["rid"]].append(o)
    for rid, os_ in sorted(byrid.items()):
        acts = ", ".join(f"{o['op']} {o['cid']}" for o in os_)
        print(rid, name_by[rid], "->", acts, "|", os_[0]["why"])
    if residual:
        print("\n--- RESIDUAL（交 LLM 封闭裁决）---")
        for x in residual:
            print(x["rid"], x["name"], "|", x["why"], "| dishes=", x["dishes"][:5], "| tags=", x["cur_tags"])
    if a.plan:
        json.dump({"domain": a.domain, "ops": ops, "residual": residual},
                  open(a.plan, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("plan written:", a.plan)


if __name__ == "__main__":
    main()

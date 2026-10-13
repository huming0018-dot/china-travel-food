#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
identity_conflicts.py — 跨传统根冲突裁决（确定性规则 + 封闭残留）

一家店只有一个主传统根。通用规则（不是逐店枚举）：
  R1 关店(closed)：不动。
  R2 食物型 bar：pasta bar→意餐；bistro/brunch/小酒馆/餐酒馆/eatery→融合菜；
     仅 wine bar/cocktail/whisky/酒吧/清吧 才是 drinking Bar。
  R3 店名品类词：私房菜→私房菜(348)、会所→会所(347)，缺则补挂。
  R4 融合菜(44)是风格：店名无 fusion/融合 时，让位给具体国菜。
  R5 单一正餐根 + 非正餐 minority 且非正餐无店名强信号 → 正餐胜。
  R6 大洲/区域泛节点（亚洲菜/非洲菜/欧洲菜/新马印…）+ 具体国家 → 具体国家。
  R7 品牌出身 / 店名强信号 / ≥3票且领先2票。
  其余（两个对等正餐根，如川粤海棠）→ residual。

用法：
  python3 identity_conflicts.py --plan /app/data/conflict_plan.json
  python3 identity_conflicts.py --apply /app/data/conflict_plan.json
"""
import os, re, sys, json, time, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

VIRT = {"中餐", "亚洲", "欧洲", "北美洲", "南美洲", "非洲", "融合菜", "非正餐", "认证", "时段"}
R_COFFEE, R_BREAD, R_DESSERT, R_BAR, R_TEA = 300, 301, 302, 303, 324
R_FUSION = 44
NON_DINNER = {R_COFFEE, R_BREAD, R_DESSERT, R_BAR, R_TEA}
ING_BREAD = 68
PRIVATE_K, CLUB = 348, 347

cs = {c["id"]: c for c in C.fetch_all("cuisines", order_col="id")}
name_by = {i: c["name"] for i, c in cs.items()}
GENERIC_GROUP_NAMES = {"亚洲菜", "非洲菜", "欧洲菜", "南美洲菜", "北美洲菜", "南美菜", "北美菜", "新马印"}
GENERIC_GROUPS = {i for i, c in cs.items() if c["name"] in GENERIC_GROUP_NAMES}


def trad_root(cid):
    # parent_category 为文本列，id 可能存成数字字符串（如 "85"）；统一归一为 int
    def _coerce(p):
        if isinstance(p, str) and p.strip().isdigit():
            return int(p.strip())
        return p
    seen = set(); cur = _coerce(cid)
    while cur in cs and cur not in seen:
        seen.add(cur); node = cs[cur]; par = _coerce(node.get("parent_category"))
        if par in VIRT or par is None:
            return cur if node.get("dimension") == "菜系" else None
        cur = par if isinstance(par, int) else None
        if cur is None:
            return None
    return None


ROOT_OF = {cid: trad_root(cid) for cid in cs}

RE_COFFEE = re.compile(r"咖啡|拿铁|澳白|卡布|手冲|espresso|latte|Flat White|美式|Dirty")
RE_BREAD = re.compile(r"面包|可颂|贝果|酸种|吐司|croissant|bagel|法棍|司康|酥皮")
RE_DESSERT = re.compile(r"甜品|甜点|蛋糕|gelato|冰淇淋|糖水|舒芙蕾|松饼|刨冰|甜汤|慕斯|布丁|挞|马卡龙|提拉米苏|巴斯克|千层|芋圆|铜锣烧")
RE_BAR = re.compile(r"鸡尾酒|威士忌|精酿|调酒|cocktail|whisky|葡萄酒|自然酒|啤酒|清酒|金酒|朗姆")
RE_TEA = re.compile(r"奶茶|柠檬茶|抹茶|奶盖|水果茶|茶饮|乌龙茶|普洱|岩茶")
RE_DINNER = re.compile(
    r"火锅|烤鱼|酸菜鱼|烤串|羊肉串|大盘鸡|手抓饭|烤包子|咖喱|冬阴功|毛血旺|干煸|焖肉|臭豆腐|藕汤|"
    r"椰子鸡|文昌鸡|打抛|船面|粿条|蚝烙|酱鸭|熏鱼|红烧肉|明虾|烧鹅|煲仔饭|牛排|肥肠|意面|披萨|汉堡|"
    r"pasta|pizza|burger|steak|蟹|虾|牛|羊|鸡|猪|鱼|饭|面|粉|汤|烤|煎|炖|焖|烧|炒")

NAME_ROOT = [
    (re.compile(r"酒吧|清吧|酒馆|whisky|wine bar|cocktail|[Bb]ar(?![a-z])|鸡尾"), R_BAR),
    (re.compile(r"咖啡|cafe|coffee|咖"), R_COFFEE),
    (re.compile(r"面包|烘焙|bakery|bake"), R_BREAD),
    (re.compile(r"甜品|甜点|糖水|gelato|冰淇淋|cake|糕|甜"), R_DESSERT),
    (re.compile(r"奶茶|柠檬茶|抹茶|奶盖|水果茶|茶饮"), R_TEA),
]
BRAND_ROOT = [
    (re.compile(r"星巴克|Starbucks|Gregorius|堀口|HORIGUCHI|%\s?Arabica|Peet|皮爷|Manner|M Stand|"
                r"Blue Bottle|蓝瓶|瑞幸|Costa|老麦咖啡|马里昂巴|Marienbad|一木家|HUGO HUSKY|雨果咖啡|"
                r"Sumerian|DayDreaming|白日梦|且乐|cheer"), R_COFFEE),
    (re.compile(r"1929 by Guillaume|Guillaume Galliot"), 26),
    (re.compile(r"Pain Chaud|PAIN CHAUD|百丘|Baker & Spice|BAsdBAN|巴适得板|Bebaked|苹果花园|"
                r"乔尔卢布松美食坊|Boulangerie"), R_BREAD),
    (re.compile(r"Luneurs|LUNEURS|月乐诗|Sloppy Gin"), R_DESSERT),
    (re.compile(r"Kartel|Pecher|Le Verre . vin|Speak Low|彼楼|LONG BAR|长吧|505[Bb]ar|"
                r"海仑宾馆505|Justgrapes|萄醉|Vinism"), R_BAR),
]
# R2 食物型 bar
FOOD_PASTA_BAR = re.compile(r"pasta\s?bar", re.I)
FOOD_BISTRO = re.compile(r"bistro|小酒馆|餐酒馆|eatery|brunch", re.I)
PURE_DRINK = re.compile(r"wine bar|cocktail|whisky|酒吧|清吧|(?<!小)酒馆|威士忌|鸡尾酒", re.I)
# R3 店名品类词
NAME_LEAF = [(re.compile(r"私房菜|私厨"), PRIVATE_K), (re.compile(r"会所|私宴"), CLUB)]
FUSION_WORD = re.compile(r"融合|fusion", re.I)


def dish_root(dish):
    d = C.cjk_unify(dish)
    if RE_BAR.search(d): return R_BAR
    if RE_COFFEE.search(d): return R_COFFEE
    if RE_BREAD.search(d): return R_BREAD
    if RE_DESSERT.search(d): return R_DESSERT
    if RE_TEA.search(d): return R_TEA
    if RE_DINNER.search(d): return "dinner"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan"); ap.add_argument("--apply")
    a = ap.parse_args()
    R = C.fetch_all("restaurants", order_col="id")
    RC = C.fetch_all("restaurant_cuisines", order_col="restaurant_id")
    byr = collections.defaultdict(set); leaves_by = collections.defaultdict(set)
    for x in RC:
        rt = ROOT_OF.get(x["cuisine_id"])
        if rt:
            byr[x["restaurant_id"]].add(rt); leaves_by[x["restaurant_id"]].add(x["cuisine_id"])
    rby = {r["id"]: r for r in R}

    if a.apply:
        plan = json.load(open(a.apply, encoding="utf-8")); done = 0
        for o in plan["ops"]:
            rid, cid = o["rid"], o["cid"]
            if o["op"] == "attach":
                resp = C.req("POST", "/restaurant_cuisines",
                             json={"restaurant_id": rid, "cuisine_id": cid, "is_primary": False})
            else:
                resp = C.req("DELETE",
                             f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
            if resp.status_code in (200, 201, 204, 409): done += 1
            else: print("FAIL", o, resp.status_code, resp.text[:100])
            time.sleep(0.07)
        print(f"applied {done}/{len(plan['ops'])}")
        return

    ops, residual = [], []
    for rid, roots in [(rid, s) for rid, s in byr.items() if len(s) > 1]:
        r = rby[rid]; nm = r.get("name") or ""; ne = r.get("name_en") or ""
        full = nm + " " + ne
        dishes = C.dishes_list(r.get("signature_dishes"))
        dinner_roots = [x for x in roots if x not in NON_DINNER]
        score = collections.Counter(); strong = set(); forced = None; forced_leaf = None

        # R1 关店
        if r.get("status") == "closed":
            residual.append({"rid": rid, "name": nm, "status": "closed",
                             "roots": [name_by.get(x) for x in sorted(roots)], "score": {},
                             "dishes": dishes[:6]}); continue

        # R2 食物型 bar（在品牌/店名通用 Bar 之前判定）
        if FOOD_PASTA_BAR.search(full):
            forced, forced_leaf = 27, 27
        elif FOOD_BISTRO.search(full) and not PURE_DRINK.search(full):
            forced, forced_leaf = R_FUSION, R_FUSION

        # R3 店名即 私房菜/会所：补形式标签，菜系现状保留（传统需另行发现，不自动改写）
        form_attach = None
        for rx, leaf in NAME_LEAF:
            if rx.search(nm):
                form_attach = leaf
        if form_attach is not None:
            if form_attach not in leaves_by[rid]:
                ops.append({"rid": rid, "op": "attach", "cid": form_attach,
                            "why": f"补形式 {name_by.get(form_attach)}（店名即品类，菜系保留）"})
            continue

        # 品牌 / 店名强信号 / 菜品投票
        brand_root = None
        for rx, rt in BRAND_ROOT:
            if rx.search(full): score[rt] += 6; strong.add(rt); brand_root = rt
        for rx, rt in NAME_ROOT:
            # 附带的 "& Bar / and Bar"（牛排馆/餐厅常见，serves≠is）不算酒吧主身份
            if rt == R_BAR:
                t_nm = re.sub(r"\s*(?:&|and|＆)\s*[Bb]ar(?![a-zA-Z])", "", nm)
                t_ne = re.sub(r"\s*(?:&|and|＆)\s*[Bb]ar(?![a-zA-Z])", "", ne)
                hit = rx.search(t_nm) or rx.search(t_ne)
            else:
                hit = rx.search(nm) or rx.search(ne)
            if hit: score[rt] += 5; strong.add(rt)
        for d in dishes:
            dr = dish_root(d)
            if dr == "dinner":
                if len(dinner_roots) == 1: score[dinner_roots[0]] += 1
            elif dr in roots:
                score[dr] += 1

        winner = forced
        if winner is None:
            # R4 融合菜让位（店名无 fusion 词）
            nonfusion = [x for x in roots if x != R_FUSION]
            if R_FUSION in roots and not FUSION_WORD.search(full) and len(nonfusion) == 1:
                winner = nonfusion[0]
            # R5 单一正餐根压过非正餐 minority
            if winner is None and len(dinner_roots) == 1 and \
                    not (strong & set(NON_DINNER)) and \
                    all(x in NON_DINNER for x in roots if x not in dinner_roots):
                winner = dinner_roots[0]
            # R6 泛节点让位给具体国家
            if winner is None:
                specific = [x for x in roots if x not in GENERIC_GROUPS]
                if len(specific) == 1 and len(roots) > 1:
                    winner = specific[0]
            # R7 品牌 / 强信号 / 票数
            if winner is None and score:
                top = score.most_common(2); cand = top[0][0]
                margin = top[0][1] - (top[1][1] if len(top) > 1 else 0)
                if (brand_root == cand) or (cand in strong and margin >= 2) or \
                        (score[cand] >= 3 and margin >= 2):
                    winner = cand

        # 安全闸：零证据（无任何菜品/品牌/店名票、且非店名 forced）不自动裁决，转 residual
        if winner is not None and forced is None and not score:
            residual.append({"rid": rid, "name": nm, "status": r.get("status"),
                             "roots": [name_by.get(x) for x in sorted(roots)],
                             "score": {"__unevidenced__": True},
                             "dishes": dishes[:6]}); continue

        if winner is None:
            residual.append({"rid": rid, "name": nm, "status": r.get("status"),
                             "roots": [name_by.get(x) for x in sorted(roots)],
                             "score": {name_by.get(k): v for k, v in score.items()},
                             "dishes": dishes[:6]}); continue

        # detach 非 winner 的【菜系】叶子；食材/形式/认证/时段（非菜系维度）一律保留
        for cid in leaves_by[rid]:
            if cs.get(cid, {}).get("dimension") == "菜系" and \
                    ROOT_OF.get(cid) is not None and ROOT_OF.get(cid) != winner:
                ops.append({"rid": rid, "op": "detach", "cid": cid,
                            "why": f"winner={name_by.get(winner)} score={dict(score)}"})
        canon_leaf = forced_leaf if forced_leaf and ROOT_OF.get(forced_leaf) == winner else winner
        if canon_leaf not in leaves_by[rid]:
            ops.append({"rid": rid, "op": "attach", "cid": canon_leaf,
                        "why": f"补挂主身份 {name_by.get(canon_leaf)}"})
        if R_BREAD in roots and winner != R_BREAD and ING_BREAD not in leaves_by[rid]:
            ops.append({"rid": rid, "op": "attach", "cid": ING_BREAD,
                        "why": "保留'也卖面包'(食材)"})

    print(f"conflicts: {len(ops)} ops, residual={len(residual)}")
    byrid = collections.defaultdict(list)
    for o in ops: byrid[o["rid"]].append(o)
    for rid, os_ in sorted(byrid.items()):
        print(rid, rby[rid]["name"], "->", ", ".join(f"{o['op']} {o['cid']}" for o in os_),
              "|", os_[0]["why"])
    print("\n--- RESIDUAL ---")
    for x in residual:
        print(x["rid"], x["name"], x["status"], "| roots=", x["roots"], "| score=", x["score"],
              "| dishes=", x["dishes"][:5])
    if a.plan:
        json.dump({"ops": ops, "residual": residual},
                  open(a.plan, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("plan written:", a.plan)


if __name__ == "__main__":
    main()

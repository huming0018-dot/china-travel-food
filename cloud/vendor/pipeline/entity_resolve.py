#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_resolve.py — 多信号实体归并（默认 dry-run），LLM+代码有序结合。
三桶：
  AUTO   品牌相关 + (同固话/同完整门牌/同铺位/坐标<25m) 等强信号
  REVIEW 品牌相关 + 同商场/坐标<120m 但缺强信号；或同铺位不同牌（疑似更名）
  PHONE  同号但品牌无关（酒店总机/错号），不合并
注意：商场共用中心坐标 ≠ 同店；无匹配铺位号禁止合并（教训#28）。

用法:
  python3 entity_resolve.py --plan /app/data/entity_plan.json
  python3 entity_resolve.py --apply verdicts.json
verdicts: {"merge":{"<sig>":{"action":"merge|keep","keeper":id}},
           "phone":{"<sig>":{"action":"keep|null_one|null_both","keep_id":id}}}
"""
import argparse, json, math, os, re, sys, time
from collections import defaultdict
import common as C
import merge_duplicates as M

KEEP_FILE = "/app/data/entity_keep_pairs.json"

GENERIC_WORDS = [
    "全国首店","专门店","专卖店","直营店","旗舰店","自助","寿喜烧","居酒屋","大排档",
    "餐厅","酒家","酒楼","食堂","小馆","料理","美食","烧烤","烤肉","牛排","咖啡","烘焙",
    "面包","甜品","蛋糕","茶社","茶馆","茶饮","小鲜","小厨","厨房","工坊","点心","面馆",
    "饭店","饭铺","海鲜","火锅","寿司","拉面","烧鸟","天妇罗","咖喱","洋食","铁板",
    "酱蟹","参鸡汤","土豆汤","炸鸡","定食","冷面","汤饭","米线","米粉","螺蛳粉","粿条",
    "肠粉","早茶","烧鹅","烧腊","卤味","包子","饺子","馄饨","锅贴","生煎","凉皮",
    "肉夹馍","串串","冒菜","烤鱼","酸菜鱼","牛蛙","龙虾","总店","分店","首店","食集",
    "市集","超市","便利店","酒场","店","粥","饼","馍","串","蟹","虾","鱼","鸡","牛",
    "羊","猪","鸭","面","上海","露台","外滩","空中","景观","三号"]
GENERIC_RE = re.compile("|".join(sorted(GENERIC_WORDS, key=len, reverse=True)))
PLACEHOLDER_RE = re.compile(r"多区连锁|多家分店|多店连锁|待核|待补|具体门牌|地址待|门牌待")

def pre_paren(s):
    return re.split(r"[（(]", str(s))[0].strip()

def cjk_cores(s):
    pre = pre_paren(s)
    cj = C.cjk_norm("".join(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff]", pre)))
    cj = GENERIC_RE.sub("", cj)
    return {cj} if len(cj) >= 2 else set()

_LATIN_CUISINE = {"indian","chinese","thai","italian","french","japanese","asian",
                  "mexican","spanish","greek","turkish","korean","vietnamese","german",
                  "american","british","russian","lebanese","peruvian","japan"}

def latin_cores(s):
    pre = re.sub(r"(?<=[A-Za-z])[.\-·’']+(?=[A-Za-z])", "", pre_paren(s))
    toks = [t for t in re.findall(r"[a-z0-9]+", pre.lower())
            if len(t) >= 3 and t not in M._LATIN_STOP and t not in _LATIN_CUISINE]
    joined = "".join(toks)
    out = {joined} if len(joined) >= 3 else set()
    return out | {t for t in toks if len(t) >= 4}

def phone_parts(s):
    land, mob = set(), set()
    for p in re.split(r"[/,，;；]", str(s or "")):
        d = re.sub(r"\D", "", p)
        if len(d) < 7:
            continue
        if d.startswith("021") or d.startswith("400"):
            land.add(d)
        elif len(d) == 11:
            mob.add(d)
    return land, mob

MALL_WORDS = r"广场|商场|购物中心|大悦城|来福士|太古汇|太古里|恒隆|万象城|万象天地|环球港|" \
             r"龙之梦|万达|日月光|久光|国金|IFC|ifc|iapm|越洋|芮欧|晶品|嘉里中心|新天地|" \
             r"世博源|世博天地|上生新所|井亭天地|天乐广场|宝龙城|丽宝|大拇指|太阳宫|合生汇|" \
             r"南丰城|港汇|高岛屋|大丸|白玉兰|张园|丰盛里|黑石公寓|翡悦里|爱琴海|帝璟大厦"

def mall_of(s):
    if PLACEHOLDER_RE.search(str(s or "")):
        return ""
    m = re.search(MALL_WORDS, str(s or ""))
    if not m:
        return ""
    pre = "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]",
                             str(s)[max(0, m.start()-5):m.start()]))
    return C.cjk_norm(pre + m.group(0))

def addr_full(s):
    if PLACEHOLDER_RE.search(str(s or "")):
        return ""
    t = re.sub(r"^(中国|上海市|上海)", "", str(s or ""))
    t = t.replace("幢", "栋")
    return C.cjk_norm(t)

def mall_unit(s):
    """商场内 (楼层, 铺位) ；取层后第一个/末尾数字作铺位。"""
    t = str(s or "")
    if PLACEHOLDER_RE.search(t):
        return None
    fl = re.search(r"[LB]?(\d+)层", t)
    tail = re.search(r"层.*?(\d{2,4})", t)
    if fl and tail:
        return (fl.group(1), tail.group(1))
    return None

def ll(r):
    return C.parse_location(r.get("location"))

def distm(a, b):
    if not a or not b:
        return None
    R = 6371000
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla = math.radians(b[1]-a[1]); dlo = math.radians(b[0]-a[0])
    h = math.sin(dla/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return 2*R*math.asin(math.sqrt(h))

def brand_related(A, B):
    for x in A["cjk"]:
        for y in B["cjk"]:
            if x == y or (len(x) >= 2 and len(y) >= 2 and (x in y or y in x)) \
               or (len(x) >= 3 and x[:3] == y[:3]):
                return True
    for x in A["lat"]:
        for y in B["lat"]:
            if x == y or (len(x) >= 4 and len(y) >= 4 and (x in y or y in x)):
                return True
    return False

class UF:
    def __init__(self, n): self.p = list(range(n))
    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[rb] = ra

def build(rests):
    R = []
    for r in rests:
        land, mob = phone_parts(r.get("phone"))
        R.append({"id": r["id"], "r": r, "cjk": cjk_cores(r.get("name")),
                  "lat": latin_cores(r.get("name")), "land": land, "mob": mob,
                  "mall": mall_of(r.get("address")), "full": addr_full(r.get("address")),
                  "unit": mall_unit(r.get("address")), "ll": ll(r)})
    n = len(R)
    auto, review, phone = [], [], []
    for i in range(n):
        for j in range(i+1, n):
            A, B = R[i], R[j]
            related = brand_related(A, B)
            land_share = A["land"] & B["land"]
            mob_share = A["mob"] & B["mob"]
            full_same = A["full"] and A["full"] == B["full"]
            mall_same = A["mall"] and A["mall"] == B["mall"]
            unit_same = mall_same and A["unit"] and A["unit"] == B["unit"]
            d = distm(A["ll"], B["ll"]) if (A["ll"] and B["ll"]) else None
            very_close = d is not None and d < 25
            near = d is not None and d < 120
            why = []
            if related:
                strong = bool(land_share) or full_same or unit_same
                mobile_strong = bool(mob_share) and (full_same or unit_same or mall_same or very_close)
                if land_share: why.append("landline")
                if mob_share: why.append("mobile")
                if full_same: why.append("fulladdr")
                if unit_same: why.append("unit")
                if d is not None: why.append(f"{int(d)}m")
                if strong or mobile_strong:
                    auto.append((i, j, why))
                elif very_close or mob_share or mall_same or near:
                    review.append((i, j, why))
            else:
                if unit_same or (full_same and (d is None or d < 60)):
                    review.append((i, j, ["sameunit_rename"] + ([f"{int(d)}m"] if d is not None else [])))
                elif land_share or mob_share:
                    phone.append((i, j, "landline" if land_share else "mobile"))
    return R, auto, review, phone

def components(edges, n):
    uf = UF(n)
    for a, b, *_ in edges:
        uf.union(a, b)
    g = defaultdict(list)
    for i in range(n):
        g[uf.find(i)].append(i)
    return [v for v in g.values() if len(v) > 1]

def sig_of(idxs, R):
    return "|".join(str(R[k]["id"]) for k in sorted(idxs, key=lambda x: R[x]["id"]))

def print_group(idxs, R, tag):
    print(f"\n● {tag} [{sig_of(idxs,R)}]")
    ranked = sorted(idxs, key=lambda k: M.completeness(R[k]["r"]), reverse=True)
    for k in ranked:
        r = R[k]["r"]
        print(f"   id={R[k]['id']:<5} comp={M.completeness(r):<2} {r['status']:<7} {r['name']}")
        print(f"        addr={r.get('address')} ph={r.get('phone')} ll={R[k]['ll']} unit={R[k]['unit']}")
    return [R[k] for k in ranked]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply"); ap.add_argument("--plan")
    args = ap.parse_args()
    rests = C.fetch_all("restaurants", "*", order_col="id")
    by_id = {r["id"]: r for r in rests}
    R, auto, review, phone = build(rests)
    n = len(R)

    auto_groups = components(auto, n)
    all_groups = components(auto + review, n)
    auto_sigs = {sig_of(g, R) for g in auto_groups}
    review_groups = [g for g in all_groups if sig_of(g, R) not in auto_sigs]

    keep = set()
    for kf in (KEEP_FILE, "/app/pipeline/entity_keep_pairs.json"):
        if os.path.exists(kf):
            keep |= set(json.load(open(kf, encoding="utf-8")))
    auto_groups = [g for g in auto_groups if sig_of(g, R) not in keep]
    review_groups = [g for g in review_groups if sig_of(g, R) not in keep]
    phone = [p for p in phone
             if "|".join(str(R[k]["id"]) for k in
                         sorted((p[0], p[1]), key=lambda x: R[x]["id"])) not in keep]

    plan_merge = {}
    print(f"==== AUTO 合并簇 {len(auto_groups)} ====")
    for g in auto_groups:
        ranked = print_group(g, R, "AUTO")
        plan_merge[sig_of(g, R)] = {"action": "merge", "keeper": ranked[0]["id"],
                                    "drop": [k["id"] for k in ranked[1:]]}
    print(f"\n==== REVIEW 待裁决簇 {len(review_groups)} ====")
    for g in review_groups:
        ranked = print_group(g, R, "REVIEW")
        plan_merge[sig_of(g, R)] = {"action": "review", "keeper": ranked[0]["id"],
                                    "drop": [k["id"] for k in ranked[1:]]}

    print(f"\n==== PHONE 电话问题对 {len(phone)} ====")
    plan_phone = {}
    for a, b, kind in phone:
        sig = "|".join(str(R[k]["id"]) for k in sorted((a, b), key=lambda x: R[x]["id"]))
        print_group([a, b], R, f"PHONE({kind})")
        plan_phone[sig] = {"action": "review", "kind": kind,
                           "ids": [R[a]["id"], R[b]["id"]]}

    if args.plan:
        json.dump({"merge": plan_merge, "phone": plan_phone},
                  open(args.plan, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n计划写 {args.plan}：AUTO {len(auto_groups)} / REVIEW {len(review_groups)} / PHONE {len(phone)}")

    if args.apply:
        V = json.load(open(args.apply, encoding="utf-8"))
        log = []
        for sig, v in V.get("merge", {}).items():
            if v.get("action") != "merge":
                continue
            keeper = v["keeper"]; drops = [i for i in (v.get("drop") or []) if i != keeper]
            master = by_id[keeper]; dups = [by_id[i] for i in drops]
            M.fill_master(master, dups, log)
            for d in dups:
                M.migrate(d["id"], keeper, log)
                C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{d['id']}")
                r = C.req("DELETE", f"/restaurants?id=eq.{d['id']}")
                log.append(f"DELETE {d['id']}:{r.status_code}")
                if r.status_code not in (200, 201, 204):
                    sys.exit(f"删除 {d['id']} 失败: {r.text[:200]}")
                time.sleep(0.1)
            print(f"✓ merge -> {keeper} {by_id[keeper]['name']}")
        # 电话纠正
        for sig, v in V.get("phone", {}).items():
            act = v.get("action")
            ids = v.get("ids")
            if act == "null_one":
                bad = [i for i in ids if i != v.get("keep_id")]
                for i in bad:
                    C.req("PATCH", f"/restaurants?id=eq.{i}", json={"phone": None})
                    log.append(f"phone null {i}")
            elif act == "null_both":
                for i in ids:
                    C.req("PATCH", f"/restaurants?id=eq.{i}", json={"phone": None})
                    log.append(f"phone null {i}")
        json.dump(log, open("/app/data/entity_merge_log.json", "w"), ensure_ascii=False, indent=2)
        print("\n应用完成。")

if __name__ == "__main__":
    main()

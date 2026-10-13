#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entity_resolve.py — 多信号实体归并（默认 dry-run），LLM+代码有序结合。
三桶：
  AUTO   品牌相关 + 完整门牌/同铺位（每对均有强证据，无 keep 冲突）
  REVIEW 品牌相关 + 同商场/坐标<120m 但缺强信号；或同铺位不同牌（疑似更名）
  PHONE  同号但品牌无关（酒店总机/错号），不合并
注意：商场共用中心坐标 ≠ 同店；无匹配铺位号禁止合并（教训#28）。

用法:
  python3 entity_resolve.py --plan /app/data/entity_plan.json
  --apply 暂停：旧 REST 多步执行器缺事务/关系完整性保护。
计划只供人工审阅，AUTO 是证据桶而非写入授权；所有 action 均为 review。
"""
import argparse, json, math, re
from itertools import combinations
from pathlib import Path
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
    fl = re.search(r"([LB]?)(\d+)层", t)
    tail = re.search(r"层.*?(\d{2,4})", t)
    if fl and tail:
        return (fl.group(1), fl.group(2), tail.group(1))
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
                # 电话、商场中心坐标和无铺位的商场地址均不能证明同店。
                conflict = (d is not None and d >= 120) or (
                    mall_same and A["unit"] and B["unit"] and A["unit"] != B["unit"])
                address_strong = bool(full_same) and bool(re.search(r"\d+号", str(A["r"].get("address") or ""))) and not (A["mall"] or B["mall"])
                strong = not conflict and bool(address_strong or unit_same)
                if land_share: why.append("landline")
                if mob_share: why.append("mobile")
                if full_same: why.append("fulladdr")
                if unit_same: why.append("unit")
                if d is not None: why.append(f"{int(d)}m")
                if strong:
                    auto.append((i, j, why))
                elif very_close or land_share or mob_share or full_same or mall_same or near:
                    review.append((i, j, why))
            else:
                if unit_same or (full_same and (d is None or d < 60)):
                    review.append((i, j, ["sameunit_rename"] + ([f"{int(d)}m"] if d is not None else [])))
                if land_share or mob_share:
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

def load_keep():
    """Fail closed on malformed history; include the canonical adjacent file."""
    keep = set()
    for path in (Path(KEEP_FILE), Path("/app/pipeline/entity_keep_pairs.json"),
                 Path(__file__).with_name("entity_keep_pairs.json")):
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                raise ValueError("keep history must be a list")
            for sig in entries:
                if not isinstance(sig, str):
                    raise ValueError("invalid keep signature")
                ids = sig.split("|")
                if len(ids) < 2 or any(not i.isdigit() for i in ids) or len(set(ids)) != len(ids):
                    raise ValueError("invalid keep signature")
                keep.add(frozenset(int(i) for i in ids))
    return keep


def candidate_groups(R, auto, review, keep):
    """One disjoint partition. Strong chains require review, not transitive AUTO.

    A historical keep cluster forbids every internal pair from merging, even
    when the current component grows or shrinks. This is deliberately conservative.
    """
    strong = {frozenset((a, b)) for a, b, *_ in auto}
    auto_groups, review_groups = [], []
    for group in components(list(auto) + list(review), len(R)):
        ids = {R[k]["id"] for k in group}
        conflict = any(len(ids & old) >= 2 for old in keep)
        complete = all(frozenset(pair) in strong for pair in combinations(group, 2))
        (auto_groups if complete and not conflict else review_groups).append(group)
    return auto_groups, review_groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply"); ap.add_argument("--plan")
    args = ap.parse_args()
    if args.apply is not None:
        ap.error("--apply disabled: requires an audited transactional executor, "
                 "fresh human verdicts, verified backup, FK inventory and durable receipts; no data read or written")
    keep = load_keep()
    rests = C.fetch_all("restaurants", "*", order_col="id")
    if len({r["id"] for r in rests}) != len(rests):
        raise ValueError("duplicate restaurant IDs")
    R, auto, review, phone = build(rests)
    auto_groups, review_groups = candidate_groups(R, auto, review, keep)
    plan_merge = {}
    for tag, groups in (("AUTO", auto_groups), ("REVIEW", review_groups)):
        print(f"==== {tag} 候选簇 {len(groups)} ==== ")
        for group in groups:
            ranked = print_group(group, R, tag)
            ids = {R[k]["id"] for k in group}
            plan_merge[sig_of(group, R)] = {
                "action": "review", "bucket": tag, "keeper": ranked[0]["id"],
                "drop": [k["id"] for k in ranked[1:]],
                "keep_constraints": [sorted(ids & old) for old in sorted(keep, key=lambda x: sorted(x))
                                     if len(ids & old) >= 2]}
    plan_phone = {}
    for a, b, kind in phone:
        sig = sig_of([a, b], R)
        print_group([a, b], R, f"PHONE({kind})")
        plan_phone[sig] = {"action": "review", "kind": kind,
                           "ids": [R[a]["id"], R[b]["id"]]}
    if args.plan:
        with open(args.plan, "w", encoding="utf-8") as fh:
            json.dump({"dry_run": True, "apply_enabled": False,
                       "merge": plan_merge, "phone": plan_phone},
                      fh, ensure_ascii=False, indent=2)
    print("DRY-RUN only: no restaurant or relationship writes")


if __name__ == "__main__":
    main()

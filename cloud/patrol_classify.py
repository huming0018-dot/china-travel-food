#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patrol_classify.py — 菜系「概念语义校验」：招牌菜 / 店名 / 别名 → 菜系主身份，
输出 ADD / REMOVE / REVIEW（默认 dry-run，绝不默认写库）。由 cloud_patrol 周期调用。

为什么存在（治反复出现的分类错）：
- 旧逻辑按“关键词出现”挂标签：'韩式拉面''牛肉拉面''一份雨天拉面'都被当成日式拉面；
  且只加不删，'老乾杯'同时挂 烧肉+美式牛排。本质是缺少“菜系概念本体 + 主身份判定”。

原则：
1. 概念本体：每个菜系叶子有【强特征 / 弱特征 / 有序改道路由】，显式区分易混兄弟品类。
2. 主身份靠强特征与改道，不靠单个弱词；**REMOVE 必须有肯定的反向证据**
   （店名命中区域，或 ≥2 道招牌菜命中兄弟品类）。不因为“拉面只占少数”就误删名店
   （一风堂有豚骨强信号即保留）。
3. 路由判定【店名优先于菜品】（店名=品牌身份）；ADD 兄弟菜系只在“店名强锚定”时发生，
   仅凭菜品命中不 ADD；无区域锚 → REVIEW，绝不自动。
4. 互斥组（烧肉 vs 美式牛排 …）：保留有强证据/品牌命中者，移除另一方，势均则 REVIEW。
5. 品牌注册表是“数据”（如 老乾杯→烧肉），通用判定仍由规则完成，可持续扩充。宁空不假。

用法：
  python3 patrol_classify.py                 # 全量扫描，落 patrol/classify_plan.json
  python3 patrol_classify.py --spot 1083     # 单店调试
  python3 patrol_classify.py --apply         # 仅高置信写库（service key，逐笔幂等）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import common as C  # noqa: E402

# 拉面（日式）概念
RAMEN_STRONG = r"豚骨|鸡白汤|虾白汤|蘸面|沾面|家系|二郎|背脂|鱼介|博多|猪骨|鱼白汤|盐味拉面|酱油拉面|味噌拉面|鱼粉"
RAMEN_WEAK = r"拉面"

# 有序改道路由：(正则, 目标菜系)。店名命中优先；否则按菜品多数命中。顺序=特异性优先。
# 目标统一用“安全父类”，避免过度细分；子叶留待后续/人工精修。
REROUTES = [
    (r"酱蟹|韩式|韩国|韩餐|韩国料理|泡菜|部队|韩定食|韩式拉面", "韩餐"),
    (r"新疆|大盘鸡|沙湾|椒麻鸡|缸缸肉|烤羊肉串|拉条子|抓饭|伊宁|锡伯|塔城|耶里夏丽|西域|游牧", "新疆菜"),
    (r"宁夏|清真|手抓羊肉", "西北菜"),
    (r"兰州|毛细|牛肉拉面|纯汤牛肉面|酿皮|敦煌|一清二白", "兰州牛肉面"),
    (r"肉夹馍|凉皮|陕西|油泼面", "陕西小吃(肉夹馍/凉皮/油泼面)"),
    (r"台北|台湾|七条通", "台湾菜"),
    (r"川味|泸州|成都|担担面|燃面|四川", "川菜"),
    (r"葱油拌面|鸡汁拌面|开洋葱油|葱油", "本帮菜"),
]

# 互斥组：member.support=该菜系支持特征。赢家=品牌命中 > 强特征数；零支持移除；势均→REVIEW。
MUTEX = [
    {
        "group": "烧肉 vs 美式牛排",
        "members": [
            {"cuisine": "烧肉",
             "support": r"烧肉|炭火|和牛|牛舌|横膈膜|西冷|眼肉|小排|卡卢比|烤肉|五花|肋条"},
            {"cuisine": "美式牛排",
             "support": r"美式|干式熟成|dry.?aged|战斧|纽约客|t骨|牛排馆|美式牛排|烤架"},
        ],
    },
    {
        "group": "日式拉面 vs 兰州牛肉面",
        "members": [
            {"cuisine": "拉面", "support": r"豚骨|鸡白汤|蘸面|家系|二郎|背脂|鱼介|博多"},
            {"cuisine": "兰州牛肉面", "support": r"兰州|牛肉面|毛细|新疆|拌面|清真|酿皮|牛肉拉面"},
        ],
    },
]

# 品牌注册表（数据）：品牌关键写法 → 主菜系。
BRAND_HINTS = [
    (["老乾杯", "老干杯"], "烧肉"),
]

# 店名明确指向“别的业态”（仅弱信号时据此移除误挂菜系）。
OTHER_FORMAT = r"wine|bar|酒吧|酒铺|咖啡|coffee|espresso|茶馆|茶室|面包|烘焙|bakery|甜品|甜点|蛋糕|鳗|gelato|冰淇淋"


def brand_hint_for(name):
    raw = str(name or "")
    norm = C.cjk_norm(raw)
    for keys, cui in BRAND_HINTS:
        for k in keys:
            if k in raw or C.cjk_norm(k) in norm:
                return cui
    return None


def resolve_cuisine(label, cname2id, all_rows):
    if label in cname2id:
        return cname2id[label]
    cands = []
    for token in re.split(r"[/／()（）]", label):
        token = token.strip()
        if len(token) < 2:
            continue
        for row in all_rows:
            if token in str(row.get("name") or ""):
                cands.append(row["id"])
    return min(cands) if cands else None


def first_route(text):
    for pat, target in REROUTES:
        m = re.search(pat, text)
        if m:
            return target, m.group(0)
    return None, None


def evaluate_ramen(rest, cname2id, all_rows):
    """日式拉面概念校验。返回 finding 列表（可能 ADD/REMOVE/REVIEW）。"""
    name0 = re.split(r"[（(]", str(rest.get("name") or ""))[0]
    alias = rest.get("aliases")
    alias = " ".join(alias) if isinstance(alias, list) else str(alias or "")
    name_blob = name0 + " " + alias
    dishes = C.dishes_list(rest.get("signature_dishes"))
    nd = len(dishes)
    dish_blob = " ".join(dishes)

    ramen_cid = resolve_cuisine("拉面", cname2id, all_rows)
    tagged_ramen = ramen_cid in rest["_tagset"]

    # 日式强信号（含虾白汤）；存在时即便有一两道兄弟品类词也不按菜品路由
    # （如 麺屋KING 的“超浓厚虾白汤担担面”，虾白汤是日式拉面子叶）
    strong_jp = [d for d in dishes if re.search(RAMEN_STRONG, d)]
    # 路由：店名优先；无日式强信号时才按菜品命中路由
    name_target, name_tok = first_route(name_blob)
    dish_target, dish_tok = None, None
    dish_hits = []
    if not strong_jp:
        for pat, target in REROUTES:
            hits = [d for d in dishes if re.search(pat, d)]
            if hits:
                dish_target, dish_tok, dish_hits = target, (re.search(pat, dish_blob).group(0)), hits
                break

    out = []
    if tagged_ramen and (name_target or dish_target):
        target = name_target or dish_target
        if name_target:
            conf, why = "high", f"店名命中『{name_tok}』→ {target}"
        else:
            need = 1 if nd <= 2 else 2
            if len(dish_hits) >= need:
                conf = "high"
            else:
                conf = "mid"
            why = f"{len(dish_hits)} 道招牌菜命中『{dish_tok}』:{dish_hits[:3]} → {target}"
        out.append({"action": "REMOVE", "cuisine": "拉面", "cuisine_id": ramen_cid,
                    "route": target,
                    "route_id": resolve_cuisine(target, cname2id, all_rows),
                    "conf": conf, "why": why})

    # ADD 兄弟菜系：仅店名强锚定
    if name_target:
        rid = resolve_cuisine(name_target, cname2id, all_rows)
        if rid is not None and rid not in rest["_tagset"]:
            out.append({"action": "ADD", "cuisine": name_target, "cuisine_id": rid,
                        "conf": "high", "why": f"店名强锚定『{name_tok}』→ {name_target}"})

    if out:
        return out

    # 无路由：日式强信号或品牌命中 → 保留
    brand = brand_hint_for(rest.get("name")) == "拉面"
    if strong_jp or brand:
        return []
    weak = [d for d in dishes if re.search(RAMEN_WEAK, d)]
    if weak and tagged_ramen:
        other = re.search(OTHER_FORMAT, name0, re.I)
        if other:
            return [{"action": "REMOVE", "cuisine": "拉面", "cuisine_id": ramen_cid,
                     "conf": "high",
                     "why": f"仅弱信号 {weak[:2]}，店名明确为别的业态（{other.group(0)}）"}]
        return [{"action": "REVIEW", "cuisine": "拉面", "cuisine_id": ramen_cid,
                 "conf": "review", "why": f"仅弱信号无强特征:{weak[:2]}，无反向证据，保留待查"}]
    return []


def evaluate_mutex(rest, group, cname2id, all_rows):
    present = []
    dishes = C.dishes_list(rest.get("signature_dishes"))
    for m in group["members"]:
        cid = resolve_cuisine(m["cuisine"], cname2id, all_rows)
        if cid is not None and cid in rest["_tagset"]:
            sup = len([d for d in dishes if re.search(m["support"], d, re.I)])
            present.append((m, cid, sup))
    if len(present) < 2:
        return []
    brand = brand_hint_for(rest.get("name"))
    winner = next((p for p in present if brand == p[0]["cuisine"]), None)
    if winner is None:
        ranked = sorted(present, key=lambda x: -x[2])
        winner = ranked[0] if ranked[0][2] > ranked[1][2] else None
    if winner is None:
        return [{"action": "REVIEW", "cuisine": m["cuisine"], "cuisine_id": cid,
                 "conf": "review",
                 "why": f"互斥组『{group['group']}』势均(support={sup})，人工裁决"}
                for m, cid, sup in present]
    out = []
    for m, cid, sup in present:
        if cid == winner[1]:
            continue
        conf = "high" if (brand == winner[0]["cuisine"] or sup == 0) else "mid"
        out.append({"action": "REMOVE", "cuisine": m["cuisine"], "cuisine_id": cid,
                    "conf": conf,
                    "why": f"互斥『{group['group']}』主身份={winner[0]['cuisine']}"
                           f"(support={winner[2]})，本方 support={sup}"})
    return out


def run(apply=False, spot=None):
    cuis_rows = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    cname2id = {r["name"]: r["id"] for r in cuis_rows}
    rests = C.fetch_all("restaurants",
                        "id,name,aliases,signature_dishes,evidence_summary,price_scene,status",
                        order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    tagset_by = defaultdict(set)
    for x in rc:
        tagset_by[x["restaurant_id"]].add(x["cuisine_id"])
    for r in rests:
        r["_tagset"] = tagset_by.get(r["id"], set())

    findings = []
    for r in rests:
        if spot and r["id"] != spot:
            continue
        for f in evaluate_ramen(r, cname2id, cuis_rows):
            f["id"] = r["id"]
            f["name"] = r["name"]
            findings.append(f)
        for g in MUTEX:
            for f in evaluate_mutex(r, g, cname2id, cuis_rows):
                f["id"] = r["id"]
                f["name"] = r["name"]
                findings.append(f)

    # 去重：同 (id, action, cuisine_id) 保留最高置信
    rank = {"high": 3, "mid": 2, "review": 1}
    best = {}
    for f in findings:
        key = (f["id"], f["action"], f["cuisine_id"])
        if key not in best or rank[f["conf"]] > rank[best[key]["conf"]]:
            best[key] = f
    findings = sorted(best.values(), key=lambda f: (f["id"], f["action"]))

    if spot:
        for f in findings:
            print(json.dumps(f, ensure_ascii=False))
        return findings

    high = [f for f in findings if f["conf"] == "high" and f["action"] in ("ADD", "REMOVE")]
    mid = [f for f in findings if f["conf"] == "mid"]
    review = [f for f in findings if f["conf"] == "review"]

    plan_f = DATA / "patrol" / "classify_plan.json"
    plan_f.parent.mkdir(parents=True, exist_ok=True)
    plan_f.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"扫描 {len(rests)} 家：high={len(high)} mid={len(mid)} review={len(review)}")
    for f in findings[:50]:
        print(f"  [{f['conf']:6s}] {f['action']:6s} id={f['id']} {f['name'][:20]:20s} "
              f"{f['cuisine']} | {f['why'][:50]}")

    if apply and high:
        applied = 0
        for f in high:
            rid, cid = f["id"], f["cuisine_id"]
            if cid is None:
                continue
            if f["action"] == "REMOVE":
                rr = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
            else:
                rr = C.req("POST", "/restaurant_cuisines", json={"restaurant_id": rid, "cuisine_id": cid})
            if rr.status_code in (200, 201, 204):
                applied += 1
            print(f"   apply {f['action']} {cid} -> {rid}: {rr.status_code}")
            time.sleep(0.05)
        print(f"已写库 {applied}/{len(high)}")
    return findings


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spot", type=int)
    a = ap.parse_args()
    run(apply=a.apply, spot=a.spot)

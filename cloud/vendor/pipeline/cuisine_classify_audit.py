#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cuisine_classify_audit.py — 分类引擎审计/校准脚本（配合 cuisine-classification-engine.md）

检测"把菜单单品当主营品类""地名/食材词机械定类"造成的误挂：
  R1 非正餐叶子主营复核（Gelato 误挂：甜汤店/泡芙店/冰浆店）
  R2 面/粉按做法分流派（牛肉面：兰州/台湾/川南；黄启云误挂粤菜）
  R3 地名/食材陷阱（海南鸡饭、大富贵等）
  R4 冲突检测（非正餐叶 × 正餐菜系、招牌主体不符）
  R5 非正餐主营优先（鲜芋仙类：主营甜品/面包/咖啡/茶饮/Bar 时，非正餐菜系优先于地域正餐菜系）

用法：
  python3 cuisine_classify_audit.py                 # dry-run，打印并落 classify_plan.json / conflicts.tsv
  python3 cuisine_classify_audit.py --commit        # 成对 DELETE/ADD 标签关联并回读
只改 restaurant_cuisines 关联，不删餐厅、不改其他字段。
"""
import argparse
import collections
import json
import sys

import common as C
import nondiner_main as N

GELATO = "冰淇淋Gelato"
SHAVED = "刨冰"
SWEET_SOUP = "糖水/甜汤"
FRENCH_PAST = "蛋糕/法式甜品"
DESSERT = "甜品"

# 牛肉面流派关键词 -> (叶子标签名, 根菜系标签名)
BEEF_NOODLE = [
    (("兰州", "清汤", "纯汤", "一碗兰", "有德", "德元"), ("兰州牛肉面", "西北菜")),
    (("台湾", "台北", "老张", "七条通", "黄启云"), ("台湾牛肉面·小吃", "台湾菜")),
    (("内江",), ("川南·内江菜", "川菜")),
    (("泸州",), ("川南·泸州菜", "川菜")),
]

# 地名/食材陷阱：店名关键词 -> (应删菜系名, 应加菜系名列表)
PREFIX_TRAPS = [
    ("海南鸡饭", ("海南菜",), ["新加坡菜", "马来西亚菜"]),
    # 大富贵：上海徽帮老字号，招牌臭鳜鱼/葡萄鱼/杨梅圆子等徽菜；本帮菜为误挂，删而不补
    ("大富贵", ("本帮菜",), []),
]

GELATO_KW = ("gelato", "冰淇淋", "冰激凌")
# 主营 gelato 的品牌白名单（招牌常只写口味、不出现 gelato 字样）
GELATO_BRANDS = ("麻布屋", "azabuya", "mimilato", "达可芮", "dal cuore", "野人先生",
                 "bonus", "sit gelato", "制冰", "makinggelato", "spiceman", "辣男")
SWEET_SOUP_KW = ("甜汤", "糖水", "椰奶", "糖葱", "大满贯", "芋泥")
FRENCH_KW = ("泡芙", "马卡龙", "闪电", "法式甜品", "可颂")
SHAVED_KW = ("冰浆", "刨冰", "かき氷", "冰沙")


def dish_text(r):
    sig = r.get("signature_dishes") or []
    if isinstance(sig, str):
        sig = [sig]
    return " ".join(str(x) for x in sig), sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    rests = C.fetch_all("restaurants", "id,name,status,signature_dishes", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    name2id = {c["name"]: c["id"] for c in cuis}
    id2c = {c["id"]: c for c in cuis}
    rmap = {r["id"]: r for r in rests}
    tags = collections.defaultdict(set)
    for x in rc:
        tags[x["restaurant_id"]].add(x["cuisine_id"])
    tagnames = {rid: {id2c[t]["name"] for t in ts if t in id2c} for rid, ts in tags.items()}

    actions, conflicts = [], []

    def act(rid, op, tagname, reason, conf="high"):
        if tagname not in name2id:
            conflicts.append((rid, rmap[rid]["name"], op, tagname, reason + "（标签不存在，需先建）"))
            return
        cid = name2id[tagname]
        cur = tags[rid]
        if op == "DELETE" and cid not in cur:
            return
        if op == "ADD" and cid in cur:
            return
        actions.append({"restaurant_id": rid, "name": rmap[rid]["name"], "op": op,
                        "cuisine_id": cid, "tag": tagname, "reason": reason, "confidence": conf})

    active = [r for r in rests if r["status"] == "active"]

    # R1: Gelato 主营复核
    gel_id = name2id.get(GELATO)
    for r in active:
        rid = r["id"]
        if gel_id not in tags[rid]:
            continue
        text, sig = dish_text(r)
        low = text.lower()
        name = r["name"]
        n = max(1, len(sig))
        gel_n = sum(1 for d in sig if any(k in str(d).lower() for k in GELATO_KW))
        name_is_gel = any(k in name.lower() for k in GELATO_KW + GELATO_BRANDS)
        if name_is_gel or gel_n / n >= 0.5:
            continue  # 主营 gelato，保留
        # 非主营：按实际出品改挂
        if any(k in text or k in name for k in SWEET_SOUP_KW):
            act(rid, "DELETE", GELATO, "R1 gelato非主营(甜汤店)")
            act(rid, "ADD", SWEET_SOUP, "R1 主营潮汕/中式甜汤")
        elif any(k in text or k in name for k in FRENCH_KW):
            act(rid, "DELETE", GELATO, "R1 gelato非主营(法式甜品店)")
            act(rid, "ADD", FRENCH_PAST, "R1 主营法式甜品")
        elif any(k in text or k in name for k in SHAVED_KW):
            act(rid, "DELETE", GELATO, "R1 gelato非主营(刨冰/冰浆店)")
            act(rid, "ADD", SHAVED, "R1 主营刨冰/冰浆")
        else:
            conflicts.append((rid, name, "REVIEW", GELATO, "R1 gelato占比低但无法确定主营甜品类"))

    # R2: 牛肉面流派
    for r in active:
        rid, name = r["id"], r["id"] and r["name"]
        if "牛肉面" not in name:
            continue
        for kws, (leaf, root) in BEEF_NOODLE:
            if any(k in name for k in kws):
                cur_food = {t for t in tagnames[rid] if t}
                # 若已挂正确叶子则跳过
                if leaf in tagnames[rid] or root in tagnames[rid]:
                    break
                # 误挂：删与面不符的菜系（如粤菜），加正确叶子/根
                for wrong in ("粤菜", "本帮菜", "京菜"):
                    if wrong in tagnames[rid]:
                        act(rid, "DELETE", wrong, f"R2 牛肉面误挂{wrong}")
                act(rid, "ADD", leaf, f"R2 按做法归{leaf}")
                act(rid, "ADD", root, f"R2 归{root}")
                break

    # R3: 地名/食材陷阱
    for r in active:
        rid, name = r["id"], r["name"]
        for key, wrongs, rights in PREFIX_TRAPS:
            if key in name:
                for w in wrongs:
                    if w in tagnames[rid]:
                        act(rid, "DELETE", w, f"R3 地名陷阱{key}")
                for rr_ in rights:
                    act(rid, "ADD", rr_, f"R3 {key}实际归属", conf="medium")

    # R5: 非正餐主营优先（鲜芋仙类：招牌主体是甜品/面包/咖啡/茶饮/Bar 时，
    # 非正餐菜系优先于地域来源；逐标签裁决，删正餐地域菜系与错挂根/叶，成对补主营根+叶）
    ND_ROOT_IDS = {300, 301, 302, 303, 324}
    ND_LEAF_IDS = set(range(304, 323))
    LEGACY_KW = {
        98: ["抹茶", "和果子", "铜锣烧", "刨冰", "团子", "羊羹", "日式", "宇治",
             "甘酒", "最中", "芭菲", "圣代", "日式甜品"],
        189: ["可颂", "起酥", "牛角", "丹麦", "咸派", "quiche", "法式", "闪电",
              "马卡龙", "泡芙"],
    }
    leaf_kws = {l: kws for _r, l, kws in N.LEAVES}
    root_kws = collections.defaultdict(list)
    for rr, _l, kk in N.LEAVES:
        root_kws[rr].extend(kk)
    leaf_root_name = {l: rr for rr, l, _k in N.LEAVES}

    def hits(sig, kws):
        return any(any(k.lower() in str(d).lower() for k in kws) for d in sig)

    for r in active:
        rid = r["id"]
        food_tags = [t for t in tags[rid] if t in id2c and id2c[t].get("dimension") == "菜系"]
        form_ids = [t for t in tags[rid] if t in id2c and id2c[t].get("dimension") == "形式"]
        cur_roots = {t for t in food_tags if t in ND_ROOT_IDS}
        res = N.classify(r["name"], r.get("signature_dishes"),
                         form_ids=form_ids, current_roots=cur_roots)
        if not res["is_nondiner_main"]:
            continue
        sig = N._clean_sig(r.get("signature_dishes"))
        R, L = res["root"], res["leaf"]
        R_id, L_id = name2id.get(R), name2id.get(L)
        strong = False
        if L:
            mkw = leaf_kws.get(L, [])
            mn = sum(1 for d in sig
                     if any(k.lower() in str(d).lower() for k in mkw))
            strong = bool(sig) and mn / len(sig) >= 0.75
        for t in food_tags:
            tname = id2c[t]["name"]
            if t == R_id or t == L_id:
                continue
            if t in ND_ROOT_IDS:
                # 其他非正餐根：招牌0命中→错根删（柏悦Bar）；有命中→复合保留
                if not hits(sig, root_kws.get(tname, [])):
                    act(rid, "DELETE", tname,
                        f"R5 主营{R}，招牌无「{tname}」，删错挂根")
                continue
            if t in ND_LEAF_IDS:
                # 非正餐子叶：强主营或跨根、且招牌0命中→错挂删；否则保留
                if (strong or leaf_root_name.get(tname) != R) \
                        and not hits(sig, leaf_kws.get(tname, [])):
                    act(rid, "DELETE", tname,
                        f"R5 招牌无「{tname}」、主营{L or R}，清错挂子叶")
                continue
            if t in LEGACY_KW:
                # 正餐树下旧非正餐标签（日式甜品98/可颂甜品189）：招牌复核，0命中删
                if not hits(sig, LEGACY_KW[t]):
                    act(rid, "DELETE", tname,
                        f"R5 招牌无「{tname}」对应出品，清错挂")
                continue
            # 正餐地域菜系：主营非正餐，让位
            act(rid, "DELETE", tname,
                f"R5 主营{R}，正餐地域菜系「{tname}」让位")
        act(rid, "ADD", R, "R5 非正餐主营根")
        if L:
            act(rid, "ADD", L, f"R5 主营子叶{L}")

    # 汇总去重（同 rid+op+cid）
    seen, uniq = set(), []
    for a in actions:
        k = (a["restaurant_id"], a["op"], a["cuisine_id"])
        if k not in seen:
            seen.add(k)
            uniq.append(a)
    actions = uniq

    by_rest = collections.defaultdict(list)
    for a in actions:
        by_rest[a["restaurant_id"]].append(a)

    print(f"分类审计：涉及 {len(by_rest)} 家、{len(actions)} 个动作、{len(conflicts)} 个待裁决")
    for rid in sorted(by_rest):
        a = by_rest[rid]
        print(f"\n#{rid} {a[0]['name']}")
        for x in a:
            print(f"  {x['op']:6} {x['tag']}  ({x['reason']}, {x['confidence']})")
    if conflicts:
        print("\n=== 待 LLM/人工裁决 ===")
        for c in conflicts:
            print(" ", c)

    with open("classify_plan.json", "w", encoding="utf-8") as f:
        json.dump(actions, f, ensure_ascii=False, indent=2)
    with open("classify_conflicts.tsv", "w", encoding="utf-8") as f:
        f.write("restaurant_id\tname\top\ttag\treason\n")
        for c in conflicts:
            f.write("\t".join(str(x) for x in c) + "\n")
    print("\n已落 classify_plan.json / classify_conflicts.tsv")

    if not args.commit:
        print("[dry-run] 确认后加 --commit 成对执行")
        return

    import time
    import requests as _rq
    n, fail = 0, 0
    base_h = C.headers()
    for a in actions:
        rid, cid = a["restaurant_id"], a["cuisine_id"]
        h = dict(base_h); h["Prefer"] = "return=representation"
        try:
            if a["op"] == "DELETE":
                url = f"{C.BASE}/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}"
                r = _rq.request("DELETE", url, headers=h, timeout=45)
                got = r.json() if r.status_code == 200 else None
                ok = isinstance(got, list) and len(got) == 1
            else:
                url = f"{C.BASE}/restaurant_cuisines"
                r = _rq.request("POST", url, headers=h,
                                json={"restaurant_id": rid, "cuisine_id": cid}, timeout=45)
                got = r.json() if r.status_code == 201 else None
                ok = isinstance(got, list) and len(got) == 1
        except Exception as e:
            ok, r = False, None
            print("  异常:", e)
        if ok:
            n += 1
        else:
            fail += 1
            print("  失败:", getattr(r, "status_code", "?"), getattr(r, "text", "")[:150])
        time.sleep(0.05)
    print(f"commit 完成 {n}/{len(actions)} 个动作，失败 {fail}")


if __name__ == "__main__":
    main()

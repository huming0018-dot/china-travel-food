#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_audit.py v2 — 连锁 / 中央厨房 / 预制菜 甄别审计（值域对齐 migration 003 CHECK）

chain_type: 独立店 / 小型连锁 / 大型连锁 / 资本化连锁
central_kitchen: 无 / 疑似 / 确认
premade_risk: 无 / 低 / 疑似 / 高

v2 甄别（确定性，多信号，修"收录没 tag on 连锁"）：
  1. 权威词表（CAPITAL/LARGE/HIGH_GROUP/REGIONAL_HINT）。
  2. brand_registry.json：canonical(+aliases/en) 命中，同品牌 ≥2 分店或带 group → 连锁。
  3. 品牌核心名（英文去空格、去括号分店、去店尾缀）在库 ≥2 分店 → 至少小型连锁。
  4. investor_info 同一集团在库 ≥2 店 → 连锁。
  5. 单店且无任何上述信号 → 显式"独立店"（消除 None 的"独立/未审"混杂）。
分级口径：
  资本化连锁（上市/融资千店级、强中央厨房）、大型连锁（数百~数千、标准化）→ 不进宝藏。
  高端餐饮集团（新荣记/大董/甬府/鲁采）：多店但 ck=无、pr=无 → 不惩罚、可进精选。
  小型连锁：标准化(pr=低)标注可隐藏；同城现做多店(pr=无)保留。
用法：
  python3 chain_audit.py            # dry-run，落 chain_plan.json
  python3 chain_audit.py --commit   # PATCH
"""
import argparse
import collections
import json
import pathlib
import re

import common as C

ROOT = pathlib.Path(C.DEFAULT_APP).parent

# (品牌匹配词, chain_type, central_kitchen, premade_risk)
CAPITAL = [
    ("小菜园", "资本化连锁", "确认", "高"), ("瑞幸", "资本化连锁", "确认", "高"),
    ("麦当劳", "资本化连锁", "确认", "高"), ("肯德基", "资本化连锁", "确认", "高"),
    ("味千", "资本化连锁", "确认", "高"), ("必胜客", "资本化连锁", "确认", "高"),
    ("汉堡王", "资本化连锁", "确认", "高"),
    ("海底捞", "资本化连锁", "疑似", "疑似"), ("星巴克", "资本化连锁", "确认", "疑似"),
    ("Manner", "资本化连锁", "确认", "疑似"), ("喜茶", "资本化连锁", "确认", "疑似"),
    ("奈雪", "资本化连锁", "确认", "疑似"), ("霸王茶姬", "资本化连锁", "确认", "疑似"),
    ("Tims", "资本化连锁", "确认", "疑似"), ("东来顺", "资本化连锁", "疑似", "疑似"),
    ("茶百道", "资本化连锁", "确认", "疑似"), ("古茗", "资本化连锁", "确认", "疑似"),
    ("蜜雪冰城", "资本化连锁", "确认", "高"), ("沪上阿姨", "资本化连锁", "确认", "疑似"),
]
LARGE = [
    ("望湘园", "大型连锁", "确认", "高"), ("盖饭邦", "大型连锁", "确认", "高"),
    ("外婆家", "大型连锁", "确认", "高"), ("绿茶", "大型连锁", "确认", "高"),
    ("点都德", "大型连锁", "确认", "高"), ("南京大牌档", "大型连锁", "确认", "高"),
    ("新旺", "大型连锁", "确认", "高"), ("东发道", "大型连锁", "确认", "高"),
    ("吉野家", "大型连锁", "确认", "高"), ("食其家", "大型连锁", "确认", "高"),
    ("莆田", "大型连锁", "疑似", "疑似"), ("松鹤楼", "大型连锁", "疑似", "疑似"),
    ("萨莉亚", "大型连锁", "确认", "疑似"), ("Wagas", "大型连锁", "疑似", "疑似"),
    ("蓝蛙", "大型连锁", "疑似", "疑似"), ("捞王", "大型连锁", "疑似", "疑似"),
    ("避风塘", "大型连锁", "疑似", "疑似"), ("旺角", "大型连锁", "疑似", "低"),
    ("巴奴", "大型连锁", "疑似", "疑似"), ("左庭右院", "大型连锁", "疑似", "低"),
    ("赤坂亭", "大型连锁", "确认", "疑似"), ("和府", "大型连锁", "确认", "疑似"),
]
HIGH_GROUP = [
    ("新荣记", "大型连锁", "无", "无"), ("荣府宴", "大型连锁", "无", "无"),
    ("大董", "大型连锁", "无", "无"), ("小大董", "大型连锁", "无", "无"),
    ("甬府", "大型连锁", "无", "无"), ("鲁采", "大型连锁", "无", "无"),
]
REGIONAL_HINT = [
    "有喜屋", "翠蝶", "本来川菜", "三木川菜", "威海渔村", "威海小馆", "东莱", "郭姐",
    "徽廷宴", "璞徽", "徽商故里", "皖宴", "潮界", "家府", "潮禧", "十八梯", "芳邻",
    "椰子不语", "西贡妈妈", "fat pho", "fatpho", "大發", "芽笼", "otantik", "brothers", "kebab",
    "crazyones", "克芮旺斯", "bruteatery", "悦璞", "painchaud", "百丘", "fascino",
    "麻布屋", "烤匠", "老头儿油爆", "张生记", "桂满陇", "孔乙己", "甬府小鲜", "福兴荟",
    "遇外滩", "唐宫", "顺峰顺水", "龙筵轩", "蜀谭记", "对酒当歌", "映水芙蓉", "柴门荟",
    "绿杨邨", "沧浪亭", "小金陵", "徐州味道", "城南往事", "小吊梨汤", "莲餐厅", "秦香岚",
    "东北四季", "老门框", "京悦", "南里山房", "浙时码头", "屿园", "钵湘", "柒熙里", "锦楼",
    "宝莱纳", "鲜得来", "大富贵", "丹凤楼", "肥仔", "pho", "saigon", "crazy",
]


def brand_core(n):
    n = re.split(r"[（(]", n)[0]
    n = re.sub(r"(上海|全国|首店|旗舰店|总店|分店|店)$", "", n.strip())
    return C.norm_name(n)


def match_reg(name):
    low = name.lower()
    for reg in (CAPITAL, LARGE, HIGH_GROUP):
        for kw, ct, ck, pr in reg:
            if kw.lower() in low:
                return ct, ck, pr
    for kw in REGIONAL_HINT:
        if kw.lower() in low:
            return "小型连锁", "", "低"
    return None


# ---- 品牌注册表 ----
def load_registry():
    p = ROOT / "research/authority/brand_registry.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("brands", [])


def reg_brand(name, brands):
    low = name.lower()
    for b in brands:
        forms = [b.get("canonical")] + b.get("aliases", []) + b.get("en", [])
        for f in forms:
            if f and len(f) >= 2 and f.lower() in low:
                return b["canonical"], b
    return None, None


def norm_inv(v):
    return C.norm_name(str(v or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all("restaurants",
                        "id,name,status,chain_type,central_kitchen,premade_risk,investor_info",
                        order_col="id")
    active = [r for r in rests if r["status"] == "active"]
    brands = load_registry()

    core_groups = collections.defaultdict(list)
    canon_groups = collections.defaultdict(list)
    inv_groups = collections.defaultdict(set)
    for r in active:
        core_groups[brand_core(r["name"])].append(r["id"])
        canon, _ = reg_brand(r["name"], brands)
        if canon:
            canon_groups[canon].append(r["id"])
        inv = norm_inv(r.get("investor_info"))
        if inv:
            inv_groups[inv].add(r["id"])

    plan = []
    for r in active:
        rid, name = r["id"], r["name"]
        m = match_reg(name)
        if m:
            ct, ck, pr = m
        else:
            canon, bobj = reg_brand(name, brands)
            if canon and (len(canon_groups[canon]) >= 2 or bobj.get("group")):
                ct, ck, pr = "小型连锁", "", "无"
            elif len(core_groups[brand_core(name)]) >= 2:
                ct, ck, pr = "小型连锁", "", "无"
            else:
                inv = norm_inv(r.get("investor_info"))
                if inv and len(inv_groups[inv]) >= 2:
                    ct, ck, pr = "小型连锁", "", "无"
                else:
                    ct, ck, pr = "独立店", "", ""
        patch = {}
        if ct and r.get("chain_type") != ct:
            patch["chain_type"] = ct
        if ck and r.get("central_kitchen") != ck:
            patch["central_kitchen"] = ck
        if pr and r.get("premade_risk") != pr:
            patch["premade_risk"] = pr
        if patch:
            plan.append({"id": rid, "name": name, "patch": patch})

    ctc = collections.Counter()
    for p in plan:
        if "chain_type" in p["patch"]:
            ctc[p["patch"]["chain_type"]] += 1
    print(f"连锁审计 v2：{len(plan)} 家待更新")
    print("chain_type 变更:", dict(ctc))

    with open("chain_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print("已落 chain_plan.json")

    if not args.commit:
        print("[dry-run] 确认后加 --commit")
        return
    n, fail = 0, 0
    for p in plan:
        r = C.req("PATCH", f"/restaurants?id=eq.{p['id']}", json=p["patch"])
        if r.status_code == 204:
            n += 1
        else:
            fail += 1
            print("  失败:", p["id"], r.status_code, r.text[:160])
    print(f"commit 完成 {n}/{len(plan)}，失败 {fail}")


if __name__ == "__main__":
    main()

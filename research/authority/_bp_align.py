#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 2026 Black Pearl Shanghai full list and align against DB snapshot."""
import json, pathlib, re, sys

PROJ = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")
AUTH = PROJ / "research" / "authority"

# --- Load DB snapshot ---
db = json.loads((AUTH / "_db_snapshot.json").read_text(encoding="utf-8"))
by_id = {r["id"]: r for r in db}

def norm(s):
    s = (s or "").lower()
    s = re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]]+", "", s)
    return s

# --- Load brand registry ---
registry = json.loads((AUTH / "brand_registry.json").read_text(encoding="utf-8"))
reg = {}
for b in registry["brands"]:
    for key in [b["canonical"]] + b.get("en", []) + b.get("aliases", []):
        reg[norm(key)] = b

# --- Compile full 2026 list ---
# Each: name, diamond, cuisine, district, address(optional), source_url, branch_hint
THREE = [
    {"name": "遇外滩(新天地店)", "diamond": 3, "cuisine": "闽菜/福建菜", "district": "黄浦区",
     "address": "黄浦区马当路245号新天地", "source_url": "http://m.toutiao.com/group/7600207294030234112/"},
    {"name": "菁禧荟(外滩店)", "diamond": 3, "cuisine": "潮州菜", "district": "黄浦区",
     "address": "黄浦区中山东二路600号BFC外滩金融中心", "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-3-diamond"},
    {"name": "甬府·北外滩", "diamond": 3, "cuisine": "宁波菜", "district": "虹口区",
     "address": "虹口区东大名路300号北外滩来福士东塔56层", "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-3-diamond"},
]

TWO = [
    {"name": "福和慧", "diamond": 2, "cuisine": "素食", "district": "长宁区",
     "address": "长宁区愚园路1037号", "source_url": "https://www.enprimeurclub.com/restaurants/fu-he-hui-shanghai-restaurant"},
    {"name": "荣府宴(南阳路店)", "diamond": 2, "cuisine": "中餐/私房", "district": "静安区",
     "address": "静安区南阳路48号贝轩大公馆", "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "中国菜·头灶", "diamond": 2, "cuisine": "中餐板前", "district": "静安区",
     "address": "静安区南京西路1376号上海商城", "source_url": "http://m.toutiao.com/group/7600207294030234112/"},
    {"name": "8½ Otto e Mezzo BOMBANA(洛克外滩源店)", "diamond": 2, "cuisine": "意餐", "district": "黄浦区",
     "address": "黄浦区圆明园路169号洛克外滩源", "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "Ling Long(上海总会店)", "diamond": 2, "cuisine": "中餐创新", "district": "黄浦区",
     "address": "黄浦区中山东一路2号上海总会大楼", "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "DA VITTORIO SHANGHAI(外滩店)", "diamond": 2, "cuisine": "意餐", "district": "黄浦区",
     "address": "黄浦区中山东一路6号外滩6号", "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
]

ONE = [
    # --- 静安 11 ---
    {"name": "Horita堀田", "diamond": 1, "cuisine": "日料", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "IL RISTORANTE - NIKO ROMITO", "diamond": 1, "cuisine": "意餐", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "MERCADO 505 Gourmet Restaurant", "diamond": 1, "cuisine": "西班牙/南美", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "宝丽轩中餐厅 BAOLIXUAN", "diamond": 1, "cuisine": "粤菜", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "斐霓丝 PHÉNIX(璞丽酒店)", "diamond": 1, "cuisine": "法餐", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "福廬 FULL HOUSE", "diamond": 1, "cuisine": "淮扬/川扬", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "家全七福酒家(丰盛商业中心店)", "diamond": 1, "cuisine": "粤菜", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "楼上菜馆(静安嘉里中心店)", "diamond": 1, "cuisine": "中餐", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "随堂里", "diamond": 1, "cuisine": "中餐", "district": "静安区",
     "address": "静安区石门一路366号镛舍2层", "source_url": "https://www.trip.com/moments/poi-sui-tang-li-56741907/"},
    {"name": "皖宴(苏河湾店)", "diamond": 1, "cuisine": "徽菜", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    {"name": "醉东 Oriental House(静安嘉里店)", "diamond": 1, "cuisine": "台州菜", "district": "静安区",
     "source_url": "https://www.jfdaily.com/sgh/detail?id=1701936"},
    # --- 徐汇 5 ---
    {"name": "Le Comptoir de Pierre Gagnaire", "diamond": 1, "cuisine": "法餐", "district": "徐汇区",
     "address": "徐汇区建国西路480号建业里", "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "Stone Sal 言盐西餐厅(东湖路店)", "diamond": 1, "cuisine": "牛排/西餐", "district": "徐汇区",
     "address": "徐汇区东湖路9号", "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "The Pine 松涧", "diamond": 1, "cuisine": "西餐", "district": "徐汇区",
     "address": "徐汇区长乐路333号", "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "大董(环贸iapm店)", "diamond": 1, "cuisine": "中餐/鲁菜创新", "district": "徐汇区",
     "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    {"name": "南兴园", "diamond": 1, "cuisine": "淮扬菜", "district": "徐汇区",
     "source_url": "https://www.shobserver.cn/sgh/detail?id=1706837"},
    # --- 浦东 5 ---
    {"name": "Maison Lameloise 莱美露滋(上海中心店)", "diamond": 1, "cuisine": "法餐", "district": "浦东新区",
     "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "南麓荟馆(国金中心店)", "diamond": 1, "cuisine": "浙菜", "district": "浦东新区",
     "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "悦轩(上海柏悦酒店)", "diamond": 1, "cuisine": "本帮菜", "district": "浦东新区",
     "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "徽季荣派徽菜", "diamond": 1, "cuisine": "徽菜", "district": "浦东新区",
     "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    {"name": "凪 Nagi", "diamond": 1, "cuisine": "日料", "district": "浦东新区",
     "source_url": "https://mobile.epaper.routeryun.com/index.php/home/article/index/appkey/41/date/2026-01-29/aid/9200346.html"},
    # --- enprimeurclub Shanghai 1-diamond ---
    {"name": "1929 by Guillaume Galliot", "diamond": 1, "cuisine": "法餐", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "成隆行·怡丰园(虹桥店)", "diamond": 1, "cuisine": "蟹宴/江浙", "district": "长宁区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Coquille 壳里", "diamond": 1, "cuisine": "法餐/海鲜", "district": "黄浦区",
     "source_url": "https://m.thepaper.cn/newsDetail_forward_32361879"},
    {"name": "Fu 1015 福1015", "diamond": 1, "cuisine": "本帮菜", "district": "长宁区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Fu 1088 福1088", "diamond": 1, "cuisine": "本帮菜", "district": "长宁区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "GRAND BOAT", "diamond": 1, "cuisine": "待确认", "district": "待确认",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "遇外滩(BFC外滩金融中心店)", "diamond": 1, "cuisine": "闽菜", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "泓0871臻选云南菜", "diamond": 1, "cuisine": "云南菜", "district": "虹口区",
     "source_url": "https://nw.eastday.com/self/citynews/20260129/e8b75c01a9a948b68d20380680d2d1ec.html"},
    {"name": "Jean Georges", "diamond": 1, "cuisine": "法餐", "district": "黄浦区",
     "source_url": "https://threeonthebund.com/zh/restaurant/102008183386"},
    {"name": "老兴鲜(黄浦)", "diamond": 1, "cuisine": "本帮菜", "district": "黄浦区",
     "source_url": "https://joinpearl.co/restaurants/shanghai/lao-xing-xian-huangpu"},
    {"name": "鲁采LU STYLE(环宇荟店)", "diamond": 1, "cuisine": "鲁菜", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Maggie 5 西郊5号", "diamond": 1, "cuisine": "中餐", "district": "长宁区",
     "source_url": "https://www.enprimeurclub.com/restaurants/maggie-5-shanghai"},
    {"name": "MIYAHATO", "diamond": 1, "cuisine": "日料", "district": "待确认",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "鹿园MOOSE(长宁店)", "diamond": 1, "cuisine": "本帮/江浙", "district": "长宁区",
     "source_url": "https://joinpearl.co/restaurants/shanghai/moose"},
    {"name": "Mr & Mrs Bund", "diamond": 1, "cuisine": "法餐", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "nabi", "diamond": 1, "cuisine": "韩食", "district": "静安区",
     "source_url": "https://nw.eastday.com/self/citynews/20260129/e8b75c01a9a948b68d20380680d2d1ec.html"},
    {"name": "食庐NOBLE(港汇恒隆店)", "diamond": 1, "cuisine": "淮扬菜", "district": "徐汇区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "逸道(北京东路)", "diamond": 1, "cuisine": "中餐", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "皇朝会(外滩店)", "diamond": 1, "cuisine": "粤菜", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "晟永兴(黄浦)", "diamond": 1, "cuisine": "烤鸭/京菜", "district": "黄浦区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Sushi Aoki", "diamond": 1, "cuisine": "日料/寿司", "district": "待确认",
     "source_url": "https://joinpearl.co/restaurants/shanghai/sushi-aoki"},
    {"name": "Taian Table", "diamond": 1, "cuisine": "现代欧陆", "district": "静安区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "Tie Wu", "diamond": 1, "cuisine": "待确认", "district": "待确认",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "upper club", "diamond": 1, "cuisine": "待确认", "district": "待确认",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "VALE RESTAURANT", "diamond": 1, "cuisine": "西餐", "district": "浦东新区",
     "source_url": "https://www.enprimeurclub.com/restaurants/vale-restaurant-shanghai-restaurant"},
    {"name": "Vivant by Johnny Pham", "diamond": 1, "cuisine": "中法融合", "district": "黄浦区",
     "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "WuXieJu 无邪居", "diamond": 1, "cuisine": "待确认", "district": "待确认",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
    {"name": "永·江臻", "diamond": 1, "cuisine": "江鲜/中餐", "district": "黄浦区",
     "address": "黄浦区思南路思南公馆", "source_url": "https://m.ctrip.com/webapp/you/community/detail?articleId=260981792"},
    {"name": "周舍海派菜", "diamond": 1, "cuisine": "本帮/海派", "district": "闵行区",
     "source_url": "https://www.enprimeurclub.com/lists/2026-black-pearl-1-diamond"},
]

ALL = THREE + TWO + ONE
print(f"Total compiled: {len(ALL)} (3-d={len(THREE)}, 2-d={len(TWO)}, 1-d={len(ONE)})")

# --- Alignment ---
def split_brand(name):
    m = re.search(r"[（(]([^（）()]+)[）)]", name)
    branch = None
    if m:
        branch = m.group(1)
    brand = re.sub(r"[（(].*?[）)]", "", name).strip()
    return brand, branch

DISTRICT_HINT = {"黄浦": "黄浦区", "徐汇": "徐汇区", "静安": "静安区", "长宁": "长宁区",
    "浦东": "浦东新区", "闵行": "闵行区", "虹口": "虹口区"}

results = {"matched": [], "alias_needed": [], "branch_missing": [], "unmatched": [], "review": []}

for rec in ALL:
    name = rec["name"]
    brand, branch = split_brand(name)
    cb = norm(brand)
    district = rec.get("district")

    chosen = None
    conf = None

    # Level 1: registry exact match
    if cb in reg:
        b = reg[cb]
        branches = b.get("branches", [])
        if len(branches) == 1 and branches[0]["id"] in by_id:
            chosen = by_id[branches[0]["id"]]
            conf = "high"
        elif len(branches) > 1:
            # try district match
            if district:
                cand = [by_id[br["id"]] for br in branches if br["id"] in by_id
                        and by_id[br["id"]].get("district") == district]
                if len(cand) == 1:
                    chosen = cand[0]
                    conf = "high"
                elif len(cand) > 1:
                    results["review"].append({**rec, "reason": "registry multi-branch district match",
                                              "candidates": [c["id"] for c in cand]})
                    continue
            if chosen is None and len(branches) == 1:
                chosen = by_id[branches[0]["id"]]
                conf = "high"

    # Level 2: prefix match
    if chosen is None and len(cb) >= 2:
        hits = []
        for r in db:
            cn = norm(r["name"])
            cen = norm(r.get("name_en") or "")
            if cn == cb or cn.startswith(cb) or (cen and (cen == cb or cen.startswith(cb))):
                if district and r.get("district") and r["district"] != district and district != "待确认":
                    continue
                hits.append(r)
        if len(hits) == 1:
            chosen = hits[0]
            conf = "medium"
        elif len(hits) > 1:
            results["review"].append({**rec, "reason": "prefix multi-candidate",
                                      "candidates": [h["id"] for h in hits]})
            continue

    if chosen:
        rec["matched_id"] = chosen["id"]
        rec["db_name"] = chosen["name"]
        rec["confidence"] = conf
        results["matched"].append(rec)
    else:
        rec["matched_id"] = None
        results["unmatched"].append(rec)

print(f"\n=== Alignment Results ===")
print(f"Matched: {len(results['matched'])}")
print(f"Review: {len(results['review'])}")
print(f"Unmatched (truly missing): {len(results['unmatched'])}")

print("\n--- Matched ---")
for r in results["matched"]:
    print(f"  [{r['diamond']}d] {r['name']} -> id={r['matched_id']} ({r['db_name']}) [{r['confidence']}]")

print("\n--- Need Review ---")
for r in results["review"]:
    print(f"  [{r['diamond']}d] {r['name']} -> {r['reason']} {r.get('candidates')}")

print("\n--- Unmatched (truly missing) ---")
for r in results["unmatched"]:
    print(f"  [{r['diamond']}d] {r['name']} ({r.get('cuisine','')}) {r.get('district','')}")

# Save full list
output = {
    "edition": "2026黑珍珠餐厅指南",
    "city": "上海",
    "total": len(ALL),
    "three_diamond": [{k:v for k,v in r.items() if k != 'matched_id'} for r in ALL if r["diamond"]==3],
    "two_diamond": [{k:v for k,v in r.items() if k != 'matched_id'} for r in ALL if r["diamond"]==2],
    "one_diamond": [{k:v for k,v in r.items() if k != 'matched_id'} for r in ALL if r["diamond"]==1],
}
(AUTH / "blackpearl_shanghai_full.json").write_text(
    json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved blackpearl_shanghai_full.json with {len(ALL)} entries")

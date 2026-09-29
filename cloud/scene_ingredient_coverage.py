#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scene_ingredient_coverage.py — W4b 确定性模块（场景茶饮归位 + 地域食材叶子 + 菜市场独立账本）

三块职责（配置驱动、默认 dry-run、--apply 才写库、写后回读断言）：

  J1 茶馆/茶饮语义纠错（归属叶子 82 / 324 / 352 / 353 / 354）
     - 裕莲茶楼 = 蛋挞 + 中式茶饮（乌龙奶茶），主营归「新中式茶饮 352 / 茶饮 324」，
       蛋挞/甜品出品由既有 302 甜品 / 317 蛋糕·法式甜品 / 67 / 68 体现；不得只挂「茶馆/茶室 82」。
     - 堂饮茶馆（普洱/岩茶/宋代点茶、包间、百元人均）按 category-bootstrap 附录C 边界，
       只留 82「茶馆/茶室」形式叶，移出 324 / 352（快取新中式茶饮 ≠ 堂饮茶馆）。
     - 配置 = CORRECTIONS 表；新增一家错链店只加配置，不改代码。

  J2 广西鱼生（横县鱼生）叶子幂等建设（归属 广西菜 21）
     - 按名查重，不存在才 POST 新叶（dimension=菜系, parent_category="21"），已存在则复用其 id。
     - 在库横县鱼生店（1993/1994/1995/1996）ensure 挂新叶（is_primary=True），父叶 21 保持 False
       （与 226 柳州螺蛳粉 / 256 桂林米粉 同款挂法）。
     - 661 禄记顺德鱼生 = 顺德菜 106，不碰（顺德鱼生 ≠ 横县鱼生）。
     - 免费通道（general_search + web.fetch）发现的候选店只登记进账本 frontier，
       不自动入库（宁空不假：候选需过 admission_gate 多声音）。

  J3 菜市场独立 POI 账本（非餐饮新品类，不写 restaurants 表）
     - 权威底册 = 上海市商务委《2025 年升级改造标准化菜市场名单》（93 家，名称+地址），
       脚本内确定性解析 MARKET_OFFICIAL_2025 表 → 写 research/category/菜市场/market_ledger.json。
     - 地图 POI 免费额度 / web 作为后续补坐标、补分区、补特色摊位的通道；本阶段不硬塞进餐饮库。

用法：
  FOOD_APP_DIR=$ROOT/app python3 scene_ingredient_coverage.py            # dry-run
  FOOD_APP_DIR=$ROOT/app python3 scene_ingredient_coverage.py --apply    # 幂等写库 + 写后回读断言
  FOOD_APP_DIR=$ROOT/app python3 scene_ingredient_coverage.py --gate      # 质量门只读模式（被 stage6/release_audit 调用）
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "pipeline"))
import common as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W4B_DIR = os.path.join(ROOT, "research", "mechanisms", "W4b")
MARKET_DIR = os.path.join(ROOT, "research", "category", "菜市场")

# ---------------------------------------------------------------- J1 配置：茶馆/茶饮纠错
# 归属叶子 id（与库对账后写死；脚本启动时再校验存在性）
T_TEAHOUSE_FORM = 82    # 茶馆/茶室（形式，饮料酒吧）
T_TEA_DRINK = 324       # 茶饮（菜系，非正餐）
T_NEW_CHINESE_TEA = 352 # 新中式茶饮
T_MILK_TEA = 353        # 奶茶专门店
T_HK_MILK_TEA = 354     # 港式奶茶·茶室

# 规则 A：裕莲茶楼模式 —— 名含「裕莲」→ ensure [352,324]；禁止 82
YULIAN_NAME_HINT = "裕莲"
YULIAN_ENSURE = [T_NEW_CHINESE_TEA, T_TEA_DRINK]
YULIAN_FORBID = [T_TEAHOUSE_FORM]
# 裕莲应体现的蛋挞/甜品出品（审计断言用，不在本模块改写）
YULIAN_DESSERT_PROOF = {302, 317, 67, 68}  # 甜品 / 蛋糕法式甜品 / 食材·甜点点心 / 食材·面包烘焙

# 规则 B：堂饮茶馆 —— 只留 82，移出 324/352（按店名+招牌+人均审定的确定性名单）
SITIN_TEAHOUSES = {
    1798: "湖心亭茶楼（豫园民俗茶楼·评弹茶席）",
    1989: "时相遇·1913百年茶馆（普洱/岩茶堂饮）",
    1990: "少山集（老白茶·冰泉煮茶）",
    1991: "隐溪茶馆（熟普/岩茶堂饮·包间）",
    1992: "黄庭茶馆（普洱老茶·宋代点茶）",
}
SITIN_ENSURE = [T_TEAHOUSE_FORM]
SITIN_REMOVE = [T_TEA_DRINK, T_NEW_CHINESE_TEA]

# 审计留档（不动作）：日式抹茶店 / 奶茶店现状，供账本记录，不在本模块改
AUDIT_ONLY = {
    "matcha_shops_keep_324_no_352": [1311, 1313, 1737, 1740],  # 辻利/九十葉/抹艾/西园
    "milk_tea_correct": [1574],                               # FIFTYLAN 在 324+353 正确
    "hk_milk_tea_empty": [],                                   # 354 港式奶茶·茶室 目前 0 家（缺口）
}

# ---------------------------------------------------------------- J2 配置：广西鱼生叶子
GUANGXI_ROOT = 21
YUSHENG_LEAF_NAME = "广西鱼生(横县鱼生)"
YUSHENG_SHOPS = [1993, 1994, 1995, 1996]   # 广记 / 渔八公 / 鱼城主 / 粤桂發（横县系）
YUSHENG_KEEP_OFF = {661}                    # 禄记顺德鱼生 → 顺德菜 106，不碰

# 免费通道发现的候选（frontier，不自动入库）
YUSHENG_FRONTIER = [
    {"name": "沪忆鲜（水产西路）", "district": "宝山区", "evidence": "横县鱼生·广西空运吊水皖鱼",
     "source_urls": ["https://www.iesdouyin.com/share/video/7524304213397048635",
                      "https://www.iesdouyin.com/share/video/7536040381306228002"]},
    {"name": "螺肥妹（宝山）", "district": "宝山区", "evidence": "广西特色·横县鱼生（赤眼鱼现切）",
     "source_urls": ["https://m.ctrip.com/webapp/you/community/detail?articleId=161638212"]},
]

# ---------------------------------------------------------------- J3 配置：菜市场权威底册
# 来源：上海市商务委《2025年上海市升级改造标准化菜市场名单》（2025-11-12 公示，93 家）
MARKET_OFFICIAL_URL = "https://sww.sh.gov.cn/zxxxgk/20251112/6c44d09d7e024d8bacde08e744a269ef.html"
MARKET_OFFICIAL_2025 = [
    "浦商菜市场沪东店|沪东路67号", "浦商邻里荟张桥店|永宁路150号", "浦商生鲜蔡路店|塘东街116弄6号A区",
    "浦商菜市场康花河店|康花路58号", "海鹏菜场|海鹏路138-160号", "鹏海市场|陈春东路120号",
    "公元集贸市场|德浦路17号", "周南集市|韵浦路259号", "平安里市场|周秀路99号", "周浦集贸市场|韵浦路58号",
    "周东市场|周东路391号-1", "富民邻里荟三桥店|金桥路2580号", "上钢菜场|上南路1500弄11-12号",
    "富民邻里荟昌莲店|昌里东路80弄1-6号A区", "浦商生鲜高青店|东书房路629弄23-24号一层A区",
    "兰陵集市|兰陵路48号", "临沂菜场|南码头路560号", "浦商菜市场江镇店|川南奉公路1915弄75号",
    "潼港市场|清溪路128号", "思集荟菜场|思学路277号", "秋岚市场|秋岚路271号", "成真农贸|柳埠路227号",
    "临书东生鲜农产品菜场|滨果公路2825号5室", "浦商生鲜冬融店|冬融路242-286号",
    "浦商菜市场航月店|鹤驰路198号", "万有菜市|浦三路4888弄5-7号", "吉家菜市场|晨晖路725号112、113室A、B区",
    "浦商菜市场福山店|福山路51号", "浦商菜市场瑞园店|瑞阳路331号", "万有全普育菜市场|普育东路109号",
    "古祥市集|罗香路174号一层", "嘉陵菜场|嘉陵路508号", "茶陵市集|零陵北路1号", "双峰菜场|双峰路300号",
    "跃康菜场|西康路770号", "黄山菜场|平型关路115号1-2层", "康定菜场|西康路520号", "兴泰菜场|大田路511号一楼",
    "芷江菜场|芷江西路50号", "大沽菜场|大沽路527号", "虹康菜场|仙霞西路299弄3号1楼",
    "新遵义菜场|遵义路760号", "华山菜场|华山路1623号", "诸安浜菜场|宣化路3号", "李园市场|真南路822弄536号",
    "泰山市场|泰山支路81号", "清涧市场|真光路2285号", "杏山市场|杏山路94号", "华丰市场|岚皋路251号",
    "上海中广食集|西江湾路122号", "三角地曲阳菜场|赤峰路319号", "三角地大连菜场|大连西路250弄30号",
    "星杨永吉菜场|双阳路419号6幢一层", "鞍山菜场|鞍山四村1-2号", "益理诚菜场|清流环三路99路",
    "平阳集市|平阳路458号", "永通菜场|龙吴路5530弄39号", "喜达多市集|华宁路2500号",
    "珲农菜场|闵瑞路910弄71号", "庙巷里市集|共康路654号", "润通菜场|水产西路938号", "盛桥菜场|古莲路328号",
    "清河菜场|梅园路75号", "马陆荣创市集|樱花街118号", "洪德集贸市场|洪德路135号",
    "惠嘉源集贸市场|春塔路837号", "菊胜集贸市场|平城路2000号1层", "绿晟农贸市场|新凤中路466号",
    "白鹤菜场|外青松公路2936号", "大盈菜场|襄臣街35号", "秀源路菜场|秀源路288号", "明珠路菜场|明珠路258号",
    "民惠菜场|久远路1449号", "菜花泾农贸市场|乐都路94号", "望塔集市|望塔路845弄1号1层",
    "富林市集|谷阳北路2760号", "洸星菜场|光星路1919号", "车墩中心菜场|车峰路300号", "如意市集|新塘路284号",
    "运河市集|运河北路468号", "鲜禾大嘴九华菜场|九华路1346号", "四团菜场|鹏贸街177号",
    "新美都菜场|运河北路199号", "胡桥菜场|胡桥新街240号", "优化菜场|优化路89号", "钱桥菜场|振钱路38号",
    "平安菜场|平福路1680号", "鲜禾大嘴江海花园菜场|人民南路2号", "鲜禾大嘴正阳菜场|育秀东路359号",
    "万安市场|公园路288号", "城河路市场|城河路175号", "边玛市集|新开河路877号1幢128室",
    "大新生态市集|富民路3号",
]


# ---------------------------------------------------------------- 基础读写（幂等 + 回读）
def fetch_links():
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id,is_primary",
                     order_col="restaurant_id")
    have = {}
    for x in rc:
        have.setdefault(x["restaurant_id"], {})[x["cuisine_id"]] = bool(x.get("is_primary"))
    return have


def ensure_link(have, rid, cid, is_primary=False, apply=False):
    """幂等：链接已存在且 is_primary 一致 → no-op；否则 POST。have=内存链接表（就地更新）。
    返回 (action, detail)。"""
    cur = have.get(rid, {}).get(cid)
    if cur is not None and bool(cur) == is_primary:
        return "noop", f"#{rid}-{cid} 已存在 is_primary={cur}"
    if apply:
        # 先删旧再写（统一 is_primary），复合键 upsert 语义
        if cur is not None:
            d = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
            assert d.status_code in (200, 204), f"删除旧链接失败 #{rid}-{cid}: {d.status_code} {d.text[:120]}"
        p = C.req("POST", "/restaurant_cuisines",
                  json={"restaurant_id": rid, "cuisine_id": cid, "is_primary": is_primary})
        assert p.status_code in (200, 201), f"写链接失败 #{rid}-{cid}: {p.status_code} {p.text[:120]}"
        # 回读断言
        back = C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
        rows = back.json()
        assert rows and bool(rows[0]["is_primary"]) == is_primary, f"回读断言失败 #{rid}-{cid}"
        have.setdefault(rid, {})[cid] = is_primary
        return "upsert", f"#{rid}-{cid} is_primary={is_primary}"
    return "plan_add", f"#{rid} +{cid} is_primary={is_primary}"


def remove_link(have, rid, cid, apply=False):
    if cid not in have.get(rid, {}):
        return "noop", f"#{rid}-{cid} 本就无链接"
    if apply:
        d = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
        assert d.status_code in (200, 204), f"删除失败 #{rid}-{cid}: {d.status_code} {d.text[:120]}"
        back = C.req("GET", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
        assert back.json() == [], f"回读断言失败：#{rid}-{cid} 仍在"
        have.get(rid, {}).pop(cid, None)
        return "deleted", f"#{rid}-{cid} 已删"
    return "plan_remove", f"#{rid} -{cid}"


# ---------------------------------------------------------------- J1 执行
def run_teahouse(apply, report):
    rests = C.fetch_all("restaurants", "id,name,status", order_col="id")
    by_id = {r["id"]: r for r in rests}
    have = fetch_links()

    # 规则 A：裕莲茶楼
    yulian_ids = [r["id"] for r in rests if YULIAN_NAME_HINT in (r.get("name") or "")
                  and r.get("status") != C.STATUS_CLOSED]
    report["yulian_matched_shops"] = [
        {"restaurant_id": i, "name": by_id[i]["name"]} for i in yulian_ids
    ]
    for rid in yulian_ids:
        for cid in YULIAN_ENSURE:
            act, msg = ensure_link(have, rid, cid, is_primary=False, apply=apply)
            report["teahouse_actions"].append({"rule": "yulian_ensure", "rid": rid, "cid": cid, "action": act, "msg": msg})
        for cid in YULIAN_FORBID:
            act, msg = remove_link(have, rid, cid, apply=apply)
            report["teahouse_actions"].append({"rule": "yulian_forbid", "rid": rid, "cid": cid, "action": act, "msg": msg})
        # 审计：蛋挞/甜品出品是否已体现（只断言，不改写）
        present = set(have.get(rid, {}).keys())
        dessert_ok = bool(present & YULIAN_DESSERT_PROOF)
        report["yulian_dessert_proof_present"].append(
            {"rid": rid, "dessert_links_present": sorted(present & YULIAN_DESSERT_PROOF), "ok": dessert_ok})

    # 规则 B：堂饮茶馆移出 324/352，ensure 82
    for rid, desc in SITIN_TEAHOUSES.items():
        if rid not in by_id:
            report["teahouse_actions"].append({"rule": "sitin_missing", "rid": rid, "action": "skip", "msg": desc})
            continue
        for cid in SITIN_ENSURE:
            act, msg = ensure_link(have, rid, cid, is_primary=False, apply=apply)
            report["teahouse_actions"].append({"rule": "sitin_ensure82", "rid": rid, "cid": cid, "action": act, "msg": msg})
        for cid in SITIN_REMOVE:
            act, msg = remove_link(have, rid, cid, apply=apply)
            report["teahouse_actions"].append({"rule": "sitin_remove", "rid": rid, "cid": cid, "action": act, "msg": msg})


# ---------------------------------------------------------------- J2 执行
def run_yusheng(apply, report):
    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    # 幂等查重
    leaf_id = None
    for c in cuis:
        if c["name"] == YUSHENG_LEAF_NAME or (
                YUSHENG_LEAF_NAME in (c["name"] or "") and c.get("dimension") == "菜系"):
            leaf_id = c["id"]
            break
    if leaf_id is None:
        if apply:
            body = {
                "name": YUSHENG_LEAF_NAME,
                "dimension": "菜系",
                "parent_category": str(GUANGXI_ROOT),
                "flavor_profile": "生鱼片薄切·花生油花生碎柠檬丝拌食·吊水皖鱼/赤眼鱼/真鲷·横县流派",
                "signature_dishes": json.dumps(
                    ["横县鱼生", "吊水皖鱼生", "赤眼鱼生", "真鲷鱼生", "鱼生配料十样"], ensure_ascii=False),
                "shanghai_format": "稀缺供给：广西空运活鱼现捞现切，多与椒盐牛蛙/凉菜套餐同售",
            }
            p = C.req("POST", "/cuisines", json=body)
            assert p.status_code in (200, 201), f"建叶失败: {p.status_code} {p.text[:200]}"
            # POST 可能返回空 body（无 Prefer 头），按名回查取 id
            back = C.req("GET", f"/cuisines?select=id,name,parent_category,dimension&name=eq.{YUSHENG_LEAF_NAME}")
            rows = back.json()
            assert rows, f"建叶后回查不到: {YUSHENG_LEAF_NAME}"
            leaf_id = rows[0]["id"]
            assert rows[0]["name"] == YUSHENG_LEAF_NAME and str(rows[0]["parent_category"]) == str(GUANGXI_ROOT), \
                f"回读断言失败：新叶 {rows[0]}"
        else:
            report["yusheng_leaf_plan"] = {"action": "plan_create", "name": YUSHENG_LEAF_NAME, "parent": str(GUANGXI_ROOT)}
            report["yusheng_leaf_id"] = None
            return
    report["yusheng_leaf_id"] = leaf_id

    have = fetch_links()
    for rid in YUSHENG_SHOPS:
        # 父叶 21 保持 False；新叶 True（对齐 226 模式）
        ensure_link(have, rid, GUANGXI_ROOT, is_primary=False, apply=apply)
        act, msg = ensure_link(have, rid, leaf_id, is_primary=True, apply=apply)
        report["yusheng_actions"].append({"rid": rid, "action": act, "msg": msg, "leaf_id": leaf_id})

    # 回读：统计新叶在库数
    back = C.req("GET", f"/restaurant_cuisines?select=restaurant_id&cuisine_id=eq.{leaf_id}")
    report["yusheng_shops_on_leaf"] = sorted(x["restaurant_id"] for x in back.json())


# ---------------------------------------------------------------- J3 执行
def run_market(report):
    markets = []
    for i, item in enumerate(MARKET_OFFICIAL_2025, 1):
        name, addr = item.split("|", 1)
        markets.append({
            "seq": i, "name": name, "address": addr,
            "district": None,           # 权威名单未带分区；待地图POI免费额度补
            "source_url": MARKET_OFFICIAL_URL,
            "source_kind": "official",
            "frame": "F2_authority_商务局",
            "coordinates": None,       # 宁空不假：待地图POI补
            "features": None,          # 特色摊位待 UGC/媒体补
            "status": "listed",
        })
    os.makedirs(MARKET_DIR, exist_ok=True)
    out = {
        "category": "菜市场（农贸市场/街市/市集）",
        "version": "2026-09-29",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "note": "独立 POI 账本，不写 restaurants 表；权威底册=上海市商务委2025升级改造标准化菜市场名单",
        "authority_url": MARKET_OFFICIAL_URL,
        "total": len(markets),
        "markets": markets,
    }
    path = os.path.join(MARKET_DIR, "market_ledger.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    report["market_ledger_path"] = path
    report["market_total"] = len(markets)


# ---------------------------------------------------------------- 质量门（只读）
def gate_check():
    """被 stage6_coverage / release_audit 调用：只读断言本模块归属叶子状态。"""
    problems = []
    have = fetch_links()
    # 1) 裕莲必须挂 352+324，不得挂 82
    rests = C.fetch_all("restaurants", "id,name", order_col="id")
    yulian = [r["id"] for r in rests if YULIAN_NAME_HINT in (r.get("name") or "")]
    for rid in yulian:
        ls = have.get(rid, {})
        if T_NEW_CHINESE_TEA not in ls or T_TEA_DRINK not in ls:
            problems.append(f"裕莲 #{rid} 缺 352/324")
        if T_TEAHOUSE_FORM in ls:
            problems.append(f"裕莲 #{rid} 误挂 82")
    # 2) 堂饮茶馆不得挂 324/352
    for rid in SITIN_TEAHOUSES:
        ls = have.get(rid, {})
        if T_TEAHOUSE_FORM not in ls:
            problems.append(f"堂饮茶馆 #{rid} 缺 82")
        if T_TEA_DRINK in ls or T_NEW_CHINESE_TEA in ls:
            problems.append(f"堂饮茶馆 #{rid} 误挂 324/352")
    # 3) 广西鱼生叶子存在且挂了 ≥2 家
    cuis = C.fetch_all("cuisines", "id,name", order_col="id")
    leaf = next((c["id"] for c in cuis if c["name"] == YUSHENG_LEAF_NAME), None)
    if leaf is None:
        problems.append("广西鱼生叶子未建")
    else:
        back = C.req("GET", f"/restaurant_cuisines?select=restaurant_id&cuisine_id=eq.{leaf_id if False else leaf}")
        n = len(back.json())
        if n < 2:
            problems.append(f"广西鱼生叶子在库仅 {n} 家 (<2)")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="幂等写库（默认 dry-run）")
    ap.add_argument("--gate", action="store_true", help="质量门只读模式")
    args = ap.parse_args()

    report = {
        "workflow": "W4b", "version": "2026-09-29",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if args.apply else ("gate" if args.gate else "dry-run"),
        "teahouse_actions": [], "yusheng_actions": [],
        "yulian_matched_shops": [], "yulian_dessert_proof_present": [],
        "audit_only": AUDIT_ONLY,
    }

    if args.gate:
        problems = gate_check()
        report["gate_problems"] = problems
        print(json.dumps({"gate": "scene_ingredient_coverage", "problems": problems,
                          "ok": not problems}, ensure_ascii=False, indent=2))
        sys.exit(1 if problems else 0)

    run_teahouse(args.apply, report)
    run_yusheng(args.apply, report)
    run_market(report)

    os.makedirs(W4B_DIR, exist_ok=True)
    ledger = os.path.join(W4B_DIR, "module_report.json")
    with open(ledger, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({"mode": report["mode"], "teahouse_actions": len(report["teahouse_actions"]),
                     "yusheng_actions": report.get("yusheng_actions"),
                     "yusheng_leaf_id": report.get("yusheng_leaf_id"),
                     "yusheng_shops_on_leaf": report.get("yusheng_shops_on_leaf"),
                     "market_total": report.get("market_total"),
                     "market_ledger": report.get("market_ledger_path"),
                     "report": ledger}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

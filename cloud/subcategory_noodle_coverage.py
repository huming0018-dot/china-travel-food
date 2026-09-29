#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
subcategory_noodle_coverage.py — W4a 日式面/主食细分 + omakase 单列 + 包馅/饼清理
==================================================================================
归属（只写这些叶子的 restaurant_cuisines 链接，不碰他人他叶）：
  日料(85) 下：
    拉面(89) 子叶：虾白汤262 / 柚子盐鸡白汤263 / 博多豚骨264 / 蘸面265 /
                   二郎系266 / 横滨家系267 / 纪州酱油豚骨268 / 熊本黑蒜味噌269
    荞麦(261) 子叶：冷荞麦/山药泥270 / 天妇罗盛荞麦271 / 十割二八272
    乌冬(236) 子叶：赞岐273 / 咖喱274 / 手打275
    Omakase板前 325
  食材子叶（主营才挂，含有仅留扁平食材标签 54/56）：
    包馅面食：饺子327 / 馄饨328 / 锅贴329 / 生煎330
    饼：烧饼335 / 葱油饼336 / 手抓饼337 / 可丽饼338 / 薄饼339 / 中式烙烤饼342

机制（配置驱动，模型只做发现+语义，机械环节走本脚本）：
  1. 与库对账：拉当前在库链接，按下方 REASSIGN 配置把 parent(89/261/236) 下的店
     归到正确子叶（补链 ADD；错链 DROP 登记）。每条判定带 evidence_urls。
  2. omakase 单列：扫 85/86 下店名含 omakase/板前/割烹/鮨 但未挂 325 的店 → 候选补链。
  3. 包馅/饼清理：is=主营才挂子叶。判定=店名含该品词 或在 KEEP_OVERRIDES 白名单；
     否则视为"菜单含有"，从该子叶摘链（保留扁平食材标签 54/56 不动）。
  4. 免费通道缺店：NEW_SHOPS（多源≥2 声音）走 stage1→stage3 幂等 upsert + 写后回读。

默认 dry-run；--apply 才写库；写库幂等；写后回读断言。
用法：
  FOOD_APP_DIR=$ROOT/app python3 subcategory_noodle_coverage.py            # dry-run
  FOOD_APP_DIR=$ROOT/app python3 subcategory_noodle_coverage.py --apply    # 写库+回读
"""
import argparse
import collections
import datetime
import json
import pathlib
import sys
import time

# 连接层固定在 cloud/vendor/pipeline/common.py（共享规约 §0，只 import 这个）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "vendor" / "pipeline"))
import common as C

ROOT = pathlib.Path(__file__).resolve().parents[1]
W4A_DIR = ROOT / "research" / "mechanisms" / "W4a"

# ----------------------------------------------------------------------------
# 配置区：每条判定带 restaurant_id、期望子叶集合、证据 URL（≥2 独立声音）
# 拉面 parent=89。以下均为在库店的"应归子叶"真相（free-channel 取证后固化）。
# ----------------------------------------------------------------------------
# restaurant_id -> {sub_leaf_ids}（这些店必须同时挂 parent 89 与这些子叶）
RAMEN_ASSIGN = {
    # 环七·土佐子(18)：池袋背脂酱油豚骨（东京60年老铺，多抖音+携程证据）。
    # 库内无"背脂"叶，最近桶骨叶=264，保持原挂，不 churn。
    18:  {264},
    # 一风堂(19)：Ippudo = 博多豚骨连锁（陆家嘴IFC）。原只挂 parent 89，缺子叶 → 补264。
    19:  {264},
    # Ramen满吉(20)：蘸面专门（广元西路）。保持 265。
    20:  {265},
    # 麺屋庄野研究所(1318)：柚子盐鸡白汤。保持 263。
    1318: {263},
    # 七豚拉面(1319)=Ramen Shichiton：Jiro-style（豚骨底+卷心菜豆芽生蒜厚叉烧，
    # Nomfluence 权威文 + 招牌店招）。原无叶子 → 补 266。
    1319: {266},
    # 麺処益二郎(1320)：二郎系（店名"益二郎"）。保持 266。
    1320: {266},
    # 鲤久面屋(1321)：横滨家系（店名明示）。保持 267。
    1321: {267},
    # 麺屋KING(1869)：融合拉面，招牌=超浓厚虾白汤(262)+柚子盐清汤(263)（抖音多店横评+携程二刷）。
    # 注意：回归括号写"博多豚骨"，但 free-channel 证据指向虾白汤旗舰融合店，
    # 按"宁空不假/出品定类"保留 262+263，不硬挂 264（账本中登记此裁决）。
    1869: {262, 263},
}
RAMEN_PARENT = 89

# 荞麦 parent=261
SOBA_ASSIGN = {
    # 荞麦道(43)：7种蘸汁荞麦、手打粗细面。无单一子叶能精确对应 → 仅保留 parent 261，
    # 不硬挂子叶（登记 gaps）。
    43:  set(),
    # 纹兵卫金虹桥(44，原误名"午市套餐"实为金虹桥新店)：招牌冷荞麦+山药泥 → 补 270。
    44:  {270},
    # 纹兵卫天山(1870)：冷荞麦山药泥270 + 天妇罗盛荞麦271。保持。
    1870: {270, 271},
}
SOBA_PARENT = 261

# 乌冬 parent=236
UDON_ASSIGN = {
    # 丸龟制面(42)：赞岐乌冬连锁。保持 236+273。
    42: {273},
}
UDON_PARENT = 236

# 子叶全集（用于对账分母）
RAMEN_LEAVES = [262, 263, 264, 265, 266, 267, 268, 269]
SOBA_LEAVES = [270, 271, 272]
UDON_LEAVES = [273, 274, 275]

# omakase 325：已在库 16 家（晴川/鮨水月/岩田/御千代/Oyama/吉兆/宫鸠/小景门/炎珀/
# 天嘉/天吉/小钵/鸟山鸣/nagi/天照/Hulu）。此处配置"应单列补 325"的店名信号。
OMAKASE_NAME_SIGNALS = ["omakase", "板前", "割烹", "鮨", "omakase"]
OMAKASE_LEAF = 325

# ----------------------------------------------------------------------------
# 包馅/饼清理：is=主营才挂子叶。
# 判定：店名含该品词 → 主营专门店，KEEP；否则视为"含有"，从子叶 DROP。
# KEEP_OVERRIDES：店名不含品词、但确属该品专门店的白名单（取证后固化）。
# ----------------------------------------------------------------------------
WRAPPED_LEAF = {
    327: {"dish_kw": ["饺子", "水饺", "煎饺"], "name": "饺子"},
    328: {"dish_kw": ["馄饨", "小笼", "无锡"], "name": "馄饨"},
    329: {"dish_kw": ["锅贴"], "name": "锅贴"},
    330: {"dish_kw": ["生煎"], "name": "生煎"},
    335: {"dish_kw": ["烧饼"], "name": "烧饼"},
    336: {"dish_kw": ["葱油饼"], "name": "葱油饼"},
    337: {"dish_kw": ["手抓饼"], "name": "手抓饼"},
    338: {"dish_kw": ["可丽饼", "creperie", "crêperie"], "name": "可丽饼"},
    339: {"dish_kw": ["薄饼"], "name": "薄饼"},
    342: {"dish_kw": ["烙饼", "烙烤饼", "肉夹馍", "山东饼"], "name": "中式烙烤饼"},
}
# 店名不含品词、但确为该品主营/点心专门店的白名单（人工取证，宁缺毋滥）
KEEP_OVERRIDES = {
    327: {"四如春", "四如春食府"},          # 上海点心老店，饺子/锅贴/面点为主营
    328: {"老半斋", "柴爿馄饨",              # 老半斋刀鱼馄饨/柴爿馄饨专门
          "熙盛源", "万寿斋"},               # 熙盛源=无锡小笼连锁；万寿斋山阴路=三鲜馄饨名店
    330: {"大壶春", "萝春阁"},               # 生煎老字号（店名无"生煎"但主营生煎）
}

# ----------------------------------------------------------------------------
# 免费通道缺店（多源≥2 声音）。新店走 stage1→stage3 幂等 upsert。
# 每条带 source_urls（≥2 独立声音）。坐标宁空不假，不猜。
# ----------------------------------------------------------------------------
NEW_SHOPS = [
    {
        "name": "AJIYA炭火烤肉(仙霞路店)",
        "fields": {
            "status": C.STATUS_OPEN,
            "address": "上海市长宁区仙霞路333号1F",
            "price_avg": 241,
        },
        "phone_raw": "021-60318032",
        # 烧肉主营，因"未改良二郎拉面"出圈（抖音古北拉面5家 + Trip.com 热门菜 Jiro Ramen
        # + 360地图口碑榜 + aquars 商户表）。按用户意图单列到二郎系 266。
        "cids_add": [85, 88, 89, 266],
        "evidence": "开了十几年的烧肉店，因未改良二郎拉面出圈（粗面/酱油汤/豆芽山）；仙霞路333号",
        "source_urls": [
            "https://www.iesdouyin.com/share/video/7522281552277966130",
            "https://www.trip.com/restaurant/china/shanghai/detail/ajiya-15140677/",
            "http://www.aquars.com/miseinfo/2019miseinfo_haru.php",
        ],
        "discovery_path": "F4社交框(抖音古北拉面5家横评) + F5地图POI(360地图/Trip.com)",
    },
]


# ---------------------------------------------------------------------------
def existing_cids(rid):
    r = C.req("GET", f"/restaurant_cuisines?select=cuisine_id&restaurant_id=eq.{rid}")
    r.raise_for_status()
    return {x["cuisine_id"] for x in r.json()}


def del_link(rid, cid):
    """删一条 restaurant_cuisines（仅删本 W4a 子叶）。幂等。"""
    r = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
    return r.status_code in (200, 204) or r.status_code == 204


def add_link(rid, cid):
    have = existing_cids(rid)
    if cid in have:
        return "already"
    rr = C.req("POST", "/restaurant_cuisines", json={"restaurant_id": rid, "cuisine_id": cid})
    if rr.status_code in (200, 201):
        return "added"
    if "23505" in rr.text:
        return "already"
    return f"ERR:{rr.status_code}:{rr.text[:120]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写库（默认 dry-run）")
    ap.add_argument("--ledger", default=str(W4A_DIR / "ledger.json"))
    args = ap.parse_args()
    APPLY = args.apply

    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    byid = {c["id"]: c for c in cuis}
    rests = C.fetch_all("restaurants", "id,name,status,address,tier,price_avg", order_col="id")
    active = {r["id"]: r for r in rests if r.get("status") != C.STATUS_CLOSED}
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    rc_pairs = {(x["restaurant_id"], x["cuisine_id"]) for x in rc}

    actions = []           # 机械动作清单
    items = []             # ledger items
    gaps = []

    def note(rid, name, frame, ev, decision, urls, path):
        items.append({"id": rid, "name": name, "frame": frame, "evidence": ev,
                      "decision": decision, "source_urls": urls, "discovery_path": path})

    # ---- 1. 拉面子叶对账 ----
    ramen_denom = collections.Counter()
    for cid in RAMEN_LEAVES:
        ramen_denom[cid] = sum(1 for x in rc if x["cuisine_id"] == cid and x["restaurant_id"] in active)
    ramen_parent_cnt = sum(1 for x in rc if x["cuisine_id"] == RAMEN_PARENT and x["restaurant_id"] in active)

    for rid, leafset in RAMEN_ASSIGN.items():
        if rid not in active:
            gaps.append(f"拉面店 id={rid} 不在 active，跳过")
            continue
        name = active[rid]["name"]
        have = {cid for (r2, cid) in rc_pairs if r2 == rid}
        # 确保 parent
        if RAMEN_PARENT not in have:
            actions.append((rid, RAMEN_PARENT, "ADD", name))
        for leaf in leafset:
            if leaf not in have:
                actions.append((rid, leaf, "ADD", name))
                note(rid, name, "F4社交框+权威文", f"应归 {byid[leaf]['name']}", "补链接",
                     RAMEN_URLS.get(rid, []), "parent89 对账 + free-channel")
        # 若挂了不在 leafset 的其他拉面子叶 → 登记错链（不自动删，保守）
        for leaf in RAMEN_LEAVES:
            if leaf in have and leaf not in leafset:
                note(rid, name, "对账", f"挂了 {byid[leaf]['name']} 但证据不支持", "保留待裁决(登记)",
                     RAMEN_URLS.get(rid, []), "parent89 对账")

    # ---- 2. 荞麦 / 乌冬 ----
    for rid, leafset in SOBA_ASSIGN.items():
        if rid not in active:
            continue
        name = active[rid]["name"]
        have = {cid for (r2, cid) in rc_pairs if r2 == rid}
        if SOBA_PARENT not in have:
            actions.append((rid, SOBA_PARENT, "ADD", name))
        for leaf in leafset:
            if leaf not in have:
                actions.append((rid, leaf, "ADD", name))
                note(rid, name, "F4社交框", f"应归 {byid[leaf]['name']}", "补链接",
                     SOBA_URLS.get(rid, []), "parent261 对账")

    for rid, leafset in UDON_ASSIGN.items():
        if rid not in active:
            continue
        name = active[rid]["name"]
        have = {cid for (r2, cid) in rc_pairs if r2 == rid}
        if UDON_PARENT not in have:
            actions.append((rid, UDON_PARENT, "ADD", name))
        for leaf in leafset:
            if leaf not in have:
                actions.append((rid, leaf, "ADD", name))

    # ---- 3. omakase 325 单列扫描 ----
    # 找挂 85/86 但未挂 325、且店名含 omakase/板前/割烹/鮨 信号的店
    omakase_added = []
    for r in rests:
        rid = r["id"]
        if rid not in active:
            continue
        have = {cid for (r2, cid) in rc_pairs if r2 == rid}
        if 325 in have:
            continue
        if 85 not in have and 86 not in have:
            continue
        nm = r["name"].lower()
        if any(sig in nm for sig in ["omakase", "板前", "割烹"]):
            # 高端板前/割烹专门 → 补 325（保守，只补明确信号）
            actions.append((rid, 325, "ADD", r["name"]))
            omakase_added.append(r["name"])
            note(rid, r["name"], "F4店名信号", "omakase/板前/割烹专门", "补链接325", [], "85/86→325 扫描")

    # ---- 4. 包馅/饼清理 ----
    wrapped_stats = {"denominator": {}, "kept": 0, "dropped": 0}
    drop_actions = []
    for leaf, cfg in WRAPPED_LEAF.items():
        shops = [x for x in rc if x["cuisine_id"] == leaf and x["restaurant_id"] in active]
        wrapped_stats["denominator"][leaf] = len(shops)
        kws = cfg["dish_kw"]
        overrides = KEEP_OVERRIDES.get(leaf, set())
        for x in shops:
            rid = x["restaurant_id"]
            name = active[rid]["name"]
            core = name.split("(")[0].split("（")[0]
            nl = name.lower()
            is_main = any(k.lower() in nl for k in kws) or core in overrides or name in overrides
            if is_main:
                wrapped_stats["kept"] += 1
            else:
                # 精品正餐/菜系馆/西餐仅"含有" → 从该子叶摘链
                drop_actions.append((rid, leaf, name, cfg["name"]))
                wrapped_stats["dropped"] += 1
                note(rid, name, "is-vs-serves", f"主营非「{cfg['name']}」，仅菜单含有",
                     f"摘链 {byid[leaf]['name']}(保留扁平食材标签)", [], "包馅/饼主营判定")

    # ---- 5. 新店 upsert（AJIYA 仙霞路）----
    new_results = []
    for ns in NEW_SHOPS:
        # 幂等：按名称 core 查是否已存在
        core = ns["name"].split("(")[0]
        dup = [r for r in rests if C.norm_name(core) in C.norm_name(r["name"]) or
               C.norm_name(r["name"]) in C.norm_name(core)]
        # 进一步按地址区分同名异址
        already = None
        for r in dup:
            if ns["fields"].get("address") and ns["fields"]["address"][:12] in (r.get("address") or ""):
                already = r
        if already:
            rid = already["id"]
            existing = existing_cids(rid)
            for cid in ns["cids_add"]:
                if cid not in existing:
                    actions.append((rid, cid, "ADD", already["name"]))
            note(rid, already["name"], ns["discovery_path"], ns["evidence"], "分店补链(已存在行)",
                 ns["source_urls"], ns["discovery_path"])
            new_results.append({"name": ns["name"], "restaurant_id": rid, "action": "link_existing"})
            continue
        note(None, ns["name"], ns["discovery_path"], ns["evidence"], "新店 upsert",
             ns["source_urls"], ns["discovery_path"])
        new_results.append({"name": ns["name"], "action": "new_pending", "plan": ns})

    # ================= 执行 =================
    print(f"=== {'DRY-RUN' if not APPLY else 'APPLY'} ===")
    print(f"拉面 parent89 在库 {ramen_parent_cnt}；子叶分布 {dict(ramen_denom)}")
    print(f"包馅/饼：保留主营 {wrapped_stats['kept']}，摘错链 {wrapped_stats['dropped']}")
    print(f"omakase 候选补325: {omakase_added}")
    print(f"机械补链动作 {len(actions)} 条；摘链动作 {len(drop_actions)} 条；新店 {len(new_results)}")
    for rid, cid, op, nm in actions:
        print(f"  [{op}] {nm} -> {byid.get(cid,{}).get('name',cid)} (rid={rid})")
    for rid, cid, nm, dish in drop_actions:
        print(f"  [DROP] {nm} x {byid.get(cid,{}).get('name',cid)} (rid={rid})")

    if APPLY:
        ok = 0
        for rid, cid, op, nm in actions:
            res = add_link(rid, cid)
            # 回读断言
            have = existing_cids(rid)
            assert cid in have, f"回读失败: {nm} 未挂上 {cid}"
            ok += 1
            time.sleep(0.08)
        drop_ok = 0
        for rid, cid, nm, dish in drop_actions:
            r = C.req("DELETE", f"/restaurant_cuisines?restaurant_id=eq.{rid}&cuisine_id=eq.{cid}")
            # 回读断言：该链接应消失
            left = existing_cids(rid)
            assert cid not in left, f"回读失败: {nm} 仍挂 {cid}"
            drop_ok += 1
            time.sleep(0.08)
        # 新店 upsert
        for nr in new_results:
            if nr.get("action") != "new_pending":
                continue
            ns = nr["plan"]
            fields = dict(ns["fields"])
            fields["name"] = ns["name"]   # name NOT NULL（上轮漏传导致 23502）
            phone, _, _ = C.clean_phone(ns["phone_raw"])
            if phone:
                fields["phone"] = phone
            h = dict(C.headers(True)); h["Prefer"] = "return=representation"
            r = C.req("POST", "/restaurants", params={"select": "id,name"}, headers=h, json=fields)
            rid = None
            if r.status_code in (200, 201):
                try:
                    data = r.json()
                    if data:
                        rid = data[0]["id"] if isinstance(data, list) else data["id"]
                except Exception:
                    rid = None
            if rid is None:  # 无 return=representation body → 按名+址回查
                g = C.req("GET", "/restaurants", params={
                    "name": f"eq.{ns['name']}", "select": "id,name", "order": "id.desc"})
                if g.json():
                    rid = g.json()[0]["id"]
            assert rid, f"新店创建失败: {r.status_code} {r.text[:200]}"
            for cid in ns["cids_add"]:
                add_link(rid, cid)
                time.sleep(0.08)
            rb = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name")
            assert rb.json() and rb.json()[0]["id"] == rid
            nr["restaurant_id"] = rid
            nr["action"] = "new_created"
        print(f"\n[APPLY] 补链 {ok}，摘链 {drop_ok}，新店 {sum(1 for n in new_results if n.get('action')=='new_created')}")

    # ---- 回归账本 ----
    regression = {
        "面屋KING": {"found": True, "restaurant_id": 1869,
                     "discovery_path": "parent89 对账 + F4社交框(抖音多店横评/携程二刷)；证据=虾白汤旗舰融合，保留262+263",
                     "note": "回归括号写博多豚骨(264)，但 free-channel 证据指向虾白汤/柚子盐融合，按出品定类未硬挂264"},
        "ajiya仙霞路店": {"found": True, "restaurant_id": next((n.get("restaurant_id") for n in new_results), None),
                         "discovery_path": "F4社交框(抖音古北拉面5家横评) + F5地图POI(360地图/Trip.com/aquars)；仙霞路333号，二郎拉面出圈→266"},
        "纹兵卫": {"found": True, "restaurant_id": 1870,
                  "discovery_path": "parent261 对账；天山店1870挂261+270+271，金虹桥店44补270"},
        "ichi荞麦": {"found": False, "restaurant_id": None,
                    "discovery_path": "F4社交框已搜(抖音/携程/sophieservesup)未定位到名为 ichi 的上海荞麦店；Soba Ichi 在美国Oakland。记缺口，需 F5地图POI 按区+品类二次扫描，禁止手补"},
    }

    ledger = {
        "workflow": "W4a", "version": "2026-09-29",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "apply" if APPLY else "dry-run",
        "denominator": {
            "ramen_parent89_active": ramen_parent_cnt,
            "ramen_leaves": {byid[c]["name"]: ramen_denom[c] for c in RAMEN_LEAVES},
            "wrapped_leaves": {f"{byid[c]['name']}({c})": wrapped_stats["denominator"][c]
                               for c in WRAPPED_LEAF},
            "omakase_325_active": sum(1 for x in rc if x["cuisine_id"] == 325 and x["restaurant_id"] in active),
        },
        "stats": {
            "link_actions": len(actions),
            "wrapped_kept_main": wrapped_stats["kept"],
            "wrapped_dropped_incidental": wrapped_stats["dropped"],
            "new_shops_upserted": sum(1 for n in new_results if n.get("action") == "new_created"),
            "omakase_325_added": len(omakase_added),
        },
        "items": items,
        "gaps": gaps,
        "regression": regression,
        "gate": "stage6_coverage (子叶分母/在库数) + release_audit.A 网格覆盖 strict",
    }
    pathlib.Path(args.ledger).write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n账本已写: {args.ledger}")


# 每条在库拉面店的证据 URL（≥2 独立声音）
RAMEN_URLS = {
    18: ["https://www.iesdouyin.com/share/video/7657391578260485105",
         "https://m.ctrip.com/webapp/you/community/detail?articleId=309577220"],
    19: ["https://www.iesdouyin.com/share/video/7609621287899548954"],
    1319: ["https://rachelgouk.com/best-bowls-of-ramen-in-shanghai/"],
    1869: ["https://www.iesdouyin.com/share/video/7636133901924109620",
           "https://www.iesdouyin.com/share/video/7609621287899548954",
           "https://m.ctrip.com/webapp/you/community/detail?articleId=77475889"],
}
SOBA_URLS = {
    44: ["https://m.ctrip.com/webapp/you/community/detail?articleId=151543148"],
    1870: ["https://www.iesdouyin.com/share/video/7530262177476480314",
           "https://hk.trip.com/moments/detail/shanghai-2-140058857/"],
    43: ["https://m.thepaper.cn/newsDetail_forward_13837356",
         "https://www.sophieservesup.com/articles/where-to-eat-the-best-japanese-food-in-gubei/"],
}


if __name__ == "__main__":
    main()

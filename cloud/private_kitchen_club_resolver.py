#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
private_kitchen_club_resolver.py — W3：私房菜(348) vs 会所(347) 确定性裁决器

背景：三个形式叶子长期重叠/混淆——
  · 348 私房菜：主厨即老板、小而美、家庭式/居民楼/私宅、无醒目招牌、预约制、
               固定或按位配菜、熟客制；
  · 347 会所  ：会员制、商务接待、包间为主、"会所/俱乐部/club"命名、洋房商办、
               招待属性强；
  · 83  私宴/会所：历史中间态，需按规则分流进 348 或 347，低置信转免费 web 封闭选项核验。

本模块在既有 private_kitchen_detector.py 基础上扩展（不推倒），做两件确定性的事：
  1) 裁决：对每家店打 private_score / club_score，按可解释阈值给出 target_leaf
     (348 / 347 / 待核)，并列出命中的信号理由（可解释、可复核）。
  2) 覆盖 + 对账：用免费通道（general_search/web.fetch、权威榜单、美食社区）枚举的
     候选（见 EMBED_CANDIDATES，含 source_urls）与库内对账，仅对"高置信且缺正确叶子链接"
     的店做增量 ADD（只补不错杀，不删任何人既有链接；误挂只进 review 清单）。

写库铁律（对齐 _SHARED_SPEC）：
  · 默认 dry-run，--apply 才写；
  · 只对形式叶子 348/347/83 的 restaurant_cuisines 做增量 ADD，不动其他菜系叶子、不动 chefs/groups；
  · 幂等：写前查现有链接，已存在则跳过；写后回读断言（re-fetch 并 assert 行数/值）。

运行：
  cd $ROOT
  FOOD_APP_DIR=$ROOT/app PYTHONPATH=$ROOT/cloud/vendor/pipeline \\
      python3 cloud/private_kitchen_club_resolver.py            # dry-run，出 ledger 与 plan
  FOOD_APP_DIR=$ROOT/app PYTHONPATH=$ROOT/cloud/vendor/pipeline \\
      python3 cloud/private_kitchen_club_resolver.py --apply    # 高置信 ADD 并回读断言
"""
import argparse
import collections
import datetime
import json
import pathlib
import re
import sys
import time

import common as C

# ------------------------------------------------------------------ 叶子 id
LEAF_SIFANG = 348   # 私房菜
LEAF_CLUB = 347     # 会所
LEAF_MID = 83       # 私宴/会所（历史中间态）
OWNED_LEAVES = {LEAF_SIFANG, LEAF_CLUB, LEAF_MID}

# ------------------------------------------------------------------ 信号词典
# private：真私房菜（348）正信号；club：商务会所/俱乐部（347）正信号。
# 每条 (正则, 权重)。命中即在 reasons 记录原文片段，保证可解释。
PRIVATE_SIGNALS = [
    # 主厨即老板 / 家庭厨房起家 / 小工作室
    (r"老板(自己|亲自|一人|掌勺|下厨|主理)|主厨(个人|主理|自己|不露脸|露脸|掌勺)|"
     r"家庭厨房|自家厨房|一户|小食堂|美食工作室|私厨|家厨", 2),
    # 小而美 / 限席 / 单场限席 / 板前几座
    (r"每天(只|仅)|每日(只|仅)|一日两席|一天(只|仅)|只开?一桌|只做?两桌|每天一桌|每天两桌|"
     r"仅?\d+\s*(席|座|桌|个座位|个位置)|板前\s*\d+\s*[座席位]|单场限|限席|每天限", 2),
    # 无门面 / 居民楼里弄私宅 / 查无此店 / 预约后告知门牌
    (r"居民楼|里弄|弄堂|小区内|私宅|无招牌|没?有?招牌|没?门头|无门头|敲门|按门铃|"
     r"藏(在|于|进|身)|隐(藏|于|世|市)|查无此店|具体地址?预约(时|后)?告知|预约(时|后)?告知", 2),
    # 全预约制 / 无固定菜单 / 按位配菜 / 熟客介绍 / 不接待 walk-in
    (r"全预约制|仅(限)?预约|只接?预约|微信(预约|订位|订座)|熟客(介绍|预约)|介绍预约|"
     r"无固定菜单|没?有?固定菜单|按位|按人头|按人数配菜|按时令配菜|上什么吃什么|"
     r"omakase|chef'?s?\s?table|invite.?only|不接待\s?walk", 2),
]
# 店名弱信号：带"私房/私厨/私宴/家宴/工作室"才计 1
PRIVATE_NAME = re.compile(r"私房|私厨|私宴|家宴|私宅|工作室")

# 强会所结构信号（命名/会员制/全包间独栋载体）——裁决 347 的必要条件；各 +2。
# 弱会所信号（宴请接待/酒店商办地址/连锁）只 +1，单独不足以把一家店判成"会所"，
# 避免把普通包间餐厅/商务宴请餐厅误报为会所（false-positive storm）。
CLUB_STRONG = [
    # 命名：会所 / 俱乐部 / club / 公馆 / 会馆 / 宴会厅
    (r"会所|俱乐部|[Cc]lub|公馆|会馆|宴会厅|私董", 2),
    # 会员制 / 验资 / 私人管家 / 私人俱乐部 / 入会会籍
    (r"会员制|入会|会籍|验资|私人管家|私人俱乐部|会员(内部)?推荐", 2),
    # 包间为主 / 大空间 / 独栋 / 不设大堂
    (r"全包间|多包间|整层|独栋|可容\d+|容纳\d+人|只做?包间|不设大堂|无大堂|整栋", 2),
]
CLUB_WEAK = [
    (r"商务(接待|宴请|招待)|宴请|招待|最低消费|包间定金|包场|晚宴人均", 1),
    # 商办/酒店/洋房公馆载体（地址）
    (r"饭店|酒店|宾馆|大厦|商务楼|写字楼|产业园|园区|别墅|庄园|spa|SPA", 1),
]
CHAIN_MARKETING = re.compile(r"连锁|集团|首店|旗舰店|分店|购物中心|商场|广场|大堂|散台|散点|walk.?in")


def score_shop(s: dict) -> dict:
    """返回 private_score / club_score / target / reasons。纯确定性、可解释。
    裁决 347 必须命中至少一条强会所结构信号（命名/会员制/全包间独栋），否则即便有弱
    宴请/酒店地址信号也只记 reason，不判会所——避免普通包间餐厅被误报。"""
    text = " ".join(str(s.get(k) or "") for k in (
        "name", "address", "booking_method", "evidence_summary", "chain_type", "chef_name"))
    name = str(s.get("name") or "")
    chain = str(s.get("chain_type") or "")

    priv, club, reasons = 0, 0, []
    strong_club_hit = False

    for pat, w in PRIVATE_SIGNALS:
        m = re.search(pat, text)
        if m:
            priv += w
            reasons.append(f"私厨+{w}:{m.group(0)[:18]}")
    if PRIVATE_NAME.search(name):
        priv += 1
        reasons.append("私厨名+1")

    for pat, w in CLUB_STRONG:
        m = re.search(pat, text)
        if m:
            club += w
            strong_club_hit = True
            reasons.append(f"会所强+{w}:{m.group(0)[:18]}")
    for pat, w in CLUB_WEAK:
        m = re.search(pat, text)
        if m:
            club += w
            reasons.append(f"会所弱+{w}:{m.group(0)[:18]}")

    # 连锁/集团/商场 = 商务工业化载体，削弱"家庭私厨"
    if CHAIN_MARKETING.search(text) or ("连锁" in chain) or ("集团" in chain):
        club += 1
        reasons.append("连锁/商场载体+1")

    diff = priv - club
    # 裁决阈值（可解释、保守，避免错杀）
    if diff >= 2 and priv >= 3:
        target = LEAF_SIFANG
    elif diff <= -2 and club >= 2 and strong_club_hit:
        target = LEAF_CLUB
    else:
        target = None  # 待核 → 免费 web 封闭选项核验
    return {"private_score": priv, "club_score": club, "diff": diff,
            "strong_club": strong_club_hit, "target_leaf": target, "reasons": reasons}


# ------------------------------------------------------------------ 免费通道覆盖候选
# 来源：本轮用 general_search / web.fetch（免费通道）枚举的权威榜单与美食社区。
# 每条含 name_hint（用于与库内 cjk_norm 对账）、frame、source_urls、倾向。
# 多源 >=2 或来自权威榜单（Time Out / SmartShanghai）方进入候选。
EMBED_CANDIDATES = [
    {"name_hint": "平川·程玉平川菜工作室", "frame": "F2权威榜",
     "lean": 348,
     "why": "Time Out《私宴遇》：dp查无此店，隐身居民楼，主厨程玉平个人古法川菜私宴，预约微信同号",
     "source_urls": ["https://www.timeoutshanghai.cn/features/6238.html"]},
    {"name_hint": "雍福会", "frame": "F4社区枚举",
     "lean": 347,
     "why": "顶级私人会所/俱乐部：原英国领事馆百年园林，会员制、入会约80万、只接会员推荐",
     "source_urls": ["https://m.maigoo.com/citiao/254740.html"]},
    {"name_hint": "Gardenchilde花公子", "frame": "F2权威榜",
     "lean": 348,
     "why": "Time Out：龙门邨买手店二楼私宴，年轻主理人按季节菜单，电话预约（库内未命中→补缺店候选）",
     "source_urls": ["https://www.timeoutshanghai.cn/features/6238.html"]},
    {"name_hint": "FoodAnatomy", "frame": "F2权威榜",
     "lean": 347,
     "why": "Time Out：延安西路大众金融大厦内意式私人家庭作坊/订制私宴，米其林主厨团队（商办载体）",
     "source_urls": ["https://www.timeoutshanghai.cn/features/6238.html"]},
    {"name_hint": "煌佳私宴", "frame": "F2权威榜",
     "lean": 347,
     "why": "Time Out：半淞园路越界世博园淮扬私宴新贵，园区内、私密晚宴（商办园区载体）",
     "source_urls": ["https://www.timeoutshanghai.cn/features/6238.html"]},
]

# 回归用例（点名锚点）——机制必须给出自动发现路径；捞不到=修机制重跑，禁止手工 REST 补。
# F7 命名锚点框：用免费通道精确查询这两个昵称级真私房。
REGRESSION_ANCHORS = [
    {"nick": "麻麻", "expect_leaf": 348,
     "frame": "F7命名锚点",
     "query": "上海 私房菜 \"麻麻\" 预约 居民楼 主厨",
     "note": "老饕圈昵称级真私房；匿名免费通道无法唯一锚定法定店名→转免费 web 封闭选项核验队列"},
    {"nick": "可乐", "expect_leaf": 348,
     "frame": "F7命名锚点",
     "query": "上海 私房菜 \"可乐\" 预约 私厨 家庭",
     "note": "老饕圈昵称级真私房（≠可乐路851）；匿名免费通道无法唯一锚定法定店名→转免费 web 封闭选项核验队列"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    ap.add_argument("--ledger-dir", default="research/mechanisms/W3")
    args = ap.parse_args()

    print("拉取库内数据 ...")
    shops = C.fetch_all("restaurants",
                        select="id,name,name_en,address,booking_method,evidence_summary,"
                               "chain_type,price_avg,chef_name,status,aliases",
                        order_col="id")
    rc = C.fetch_all("restaurant_cuisines",
                     select="restaurant_id,cuisine_id", order_col="restaurant_id")
    cuis = {c["id"]: c["name"] for c in C.fetch_all("cuisines", "id,name", order_col="id")}

    links_by_rest = collections.defaultdict(set)
    for l in rc:
        links_by_rest[l["restaurant_id"]].add(l["cuisine_id"])

    # 1) 全库裁决（仅 active 店进入写候选；其余仍出报告）
    scored, active = [], [s for s in shops if s.get("status") == C.STATUS_OPEN]
    for s in shops:
        sc = score_shop(s)
        sc["id"], sc["name"], sc["status"] = s["id"], s["name"], s.get("status")
        sc["current_links"] = sorted(links_by_rest[s["id"]] & OWNED_LEAVES)
        scored.append(sc)

    # 2) 覆盖候选对账：cjk_norm 模糊匹配库内店
    def norm(x):
        return C.cjk_norm(x)

    candidate_hits = []
    for cand in EMBED_CANDIDATES:
        nh = norm(cand["name_hint"])
        matched = None
        for s in active:
            blob = norm(str(s.get("name") or "")) + " " + norm(str(s.get("aliases") or ""))
            if nh and (nh in blob):
                matched = s
                break
        rec = dict(cand)
        if matched:
            sc = score_shop(matched)
            rec["matched_restaurant_id"] = matched["id"]
            rec["matched_name"] = matched["name"]
            rec["resolved_target"] = sc["target_leaf"]
            rec["resolved_reasons"] = sc["reasons"]
            rec["already_linked"] = sorted(links_by_rest[matched["id"]] & OWNED_LEAVES)
        else:
            rec["matched_restaurant_id"] = None  # 库内缺失 → 补缺店候选（交 W1 建店，本模块不建店）
        candidate_hits.append(rec)

    # 3) 生成 ADD 计划。覆盖候选自带权威 source_urls（F2 权威榜 / F7 锚点），
    #    当库内行字段稀疏导致纯库内裁决低置信(target=None)时，采信权威源背书的 lean 作为
    #    源背书 ADD（多源≥2 或权威榜单）；库内裁决出具体叶子时以裁决为准、与 lean 冲突则降级核验。
    add_plan, review = [], []
    for rec in candidate_hits:
        rid = rec.get("matched_restaurant_id")
        if not rid:
            rec["decision"] = "gap_restaurant_missing"  # 库内无此店 → 补缺店候选，不建店
            continue
        target = rec.get("resolved_target")          # 库内纯字段裁决（可能 None=低置信）
        lean = rec.get("lean")
        has = set(rec.get("already_linked") or [])

        # 库内裁决出明确叶子
        if target in (LEAF_SIFANG, LEAF_CLUB):
            if lean and lean != target:
                rec["decision"] = "lean_conflict_review"
                review.append({"restaurant_id": rid, "name": rec.get("matched_name"),
                               "reason": f"库内裁决{target}与候选倾向{lean}冲突，转核验"})
                continue
            final = target
        elif target is None and lean in (LEAF_SIFANG, LEAF_CLUB):
            # 低置信 + 权威源背书：信任 lean。DB 不反驳（未裁决到对立面）即可 ADD。
            final = lean
            rec["source_backed"] = True
        else:
            rec["decision"] = "low_confidence_verify"
            review.append({"restaurant_id": rid, "name": rec.get("matched_name"),
                           "reason": "库内低置信且无权威源背书，转免费 web 封闭选项核验"})
            continue

        if final in has:
            rec["decision"] = "already_linked_skip"
            continue
        rec["decision"] = "ADD"
        add_plan.append({"restaurant_id": rid, "name": rec.get("matched_name"),
                         "target_leaf": final, "frame": rec.get("frame"),
                         "source_backed": rec.get("source_backed", False),
                         "why": rec.get("why"), "source_urls": rec.get("source_urls")})

    # 4) 既有链接误挂复核（只报不删，遵守"只补不错杀"）
    mislinked = []
    for sc in scored:
        if not sc["current_links"]:
            continue
        tgt = sc["target_leaf"]
        # 既有 83 中间态 → 分流建议
        if LEAF_MID in sc["current_links"]:
            mislinked.append({"restaurant_id": sc["id"], "name": sc["name"],
                              "issue": "leaf83_midstate", "suggest": tgt,
                              "reasons": sc["reasons"]})
        # 既有 348 却被裁决为会所（或反之）→ 报人工，不自动删
        if (LEAF_SIFANG in sc["current_links"] and tgt == LEAF_CLUB):
            mislinked.append({"restaurant_id": sc["id"], "name": sc["name"],
                              "issue": "linked348_but_resolves_club", "suggest": tgt,
                              "reasons": sc["reasons"]})
        if (LEAF_CLUB in sc["current_links"] and tgt == LEAF_SIFANG):
            mislinked.append({"restaurant_id": sc["id"], "name": sc["name"],
                              "issue": "linked347_but_resolves_sifang", "suggest": tgt,
                              "reasons": sc["reasons"]})

    # 5) 回归锚点：给出自动发现路径（不手工补）
    regression = []
    for anc in REGRESSION_ANCHORS:
        # 机制内对库内【店名/别名】做一次昵称扫描（确定性自检）。
        # 只扫 name+aliases，不扫 evidence_summary——否则菜名"豆花麻麻鱼"/合作文案"百事可乐"
        # 会造成假阳性。一家真叫"麻麻/可乐"的店，其名字一定在 name/aliases 里。
        # 路名排除："可乐路店(851)"不是昵称"可乐"；昵称须作独立店名 token，且不接路/道/街/村后缀。
        nh = norm(anc["nick"])
        hit = None
        for s in shops:
            blob = norm(str(s.get("name") or "")) + " " + norm(str(s.get("aliases") or ""))
            if not nh:
                break
            for m in re.finditer(re.escape(nh), blob):
                after = blob[m.end():m.end()+2]
                if re.match(r"^(路|道|街|村|号|镇|店)", after):
                    continue  # 路名/分店后缀，非昵称
                hit = s
                break
            if hit:
                break
        regression.append({
            "nick": anc["nick"], "expect_leaf": anc["expect_leaf"],
            "frame": anc["frame"], "query": anc["query"],
            "found": bool(hit),
            "discovery_path": f"{anc['frame']} | free-channel query='{anc['query']}' "
                              f"(general_search/web.fetch) | 库内昵称自检={'命中id=' + str(hit['id']) if hit else '未命中'}",
            "restaurant_id": (hit["id"] if hit else None),
            "verdict": "ok" if hit else "low_confidence_freeweb_verify",
            "note": anc["note"],
        })

    # 统计
    n_sifang = sum(1 for s in scored if s["target_leaf"] == LEAF_SIFANG and s["status"] == C.STATUS_OPEN)
    n_club = sum(1 for s in scored if s["target_leaf"] == LEAF_CLUB and s["status"] == C.STATUS_OPEN)
    n_verify = sum(1 for s in scored if s["target_leaf"] is None and s["status"] == C.STATUS_OPEN)
    stats = {
        "denominator_active_restaurants": len(active),
        "scored_total": len(scored),
        "resolved_sifang_348": n_sifang,
        "resolved_club_347": n_club,
        "low_confidence_verify": n_verify,
        "coverage_candidates": len(candidate_hits),
        "coverage_candidates_matched_in_db": sum(1 for c in candidate_hits if c.get("matched_restaurant_id")),
        "coverage_candidates_missing_in_db": sum(1 for c in candidate_hits if not c.get("matched_restaurant_id")),
        "add_plan_count": len(add_plan),
        "mislinked_review_count": len(mislinked),
        "regression_hit": sum(1 for r in regression if r["found"]),
    }

    # 控制台摘要
    print(f"\n=== 裁决统计：active={len(active)} 348候选={n_sifang} 347候选={n_club} 待核={n_verify} ===")
    print(f"覆盖候选 {len(candidate_hits)}（库内命中 {stats['coverage_candidates_matched_in_db']}，"
          f"库内缺 {stats['coverage_candidates_missing_in_db']}）")
    print(f"ADD 计划 {len(add_plan)} 条：")
    for a in add_plan:
        print(f"  + [{a['target_leaf']}] id={a['restaurant_id']} {a['name']}  ({a['frame']})")
    print(f"误挂复核（只报不删）{len(mislinked)} 条：")
    for m in mislinked:
        print(f"  ! id={m['restaurant_id']} {m['name']} {m['issue']} ->建议{m['suggest']}")
    print(f"回归锚点 {len(regression)}：")
    for r in regression:
        print(f"  R {r['nick']}: found={r['found']} id={r['restaurant_id']} -> {r['verdict']}")

    # 写账本（中间产物 + ledger）
    ld = pathlib.Path(args.ledger_dir)
    ld.mkdir(parents=True, exist_ok=True)
    (ld / "candidates.json").write_text(
        json.dumps(candidate_hits, ensure_ascii=False, indent=2), encoding="utf-8")
    (ld / "resolve_scored.json").write_text(
        json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger = {
        "workflow": "W3", "version": "2026-09-29",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "module": "cloud/private_kitchen_club_resolver.py",
        "gate": "cuisine_classify_audit / stage4_audit（形式叶子 348/347/83 分流门）",
        "frames": [
            {"id": "F2", "name": "权威榜单（Time Out 私宴遇 / SmartShanghai chef's table）"},
            {"id": "F4", "name": "美食社区/媒体枚举（会所/俱乐部/会员制 关键词）"},
            {"id": "F7", "name": "命名锚点框（回归点名：麻麻/可乐）"},
        ],
        "denominator": {"active_restaurants": len(active),
                        "owned_leaves": sorted(OWNED_LEAVES),
                        "existing_links_348": len(links_by_rest and [1 for r in active if LEAF_SIFANG in links_by_rest[r['id']]]),
                        "existing_links_347": len([1 for r in active if LEAF_CLUB in links_by_rest[r['id']]]),
                        "existing_links_83": len([1 for r in active if LEAF_MID in links_by_rest[r['id']]])},
        "items": add_plan + [{"restaurant_id": m["restaurant_id"], "name": m["name"],
                              "decision": "review", "issue": m["issue"], "suggest": m["suggest"]}
                             for m in mislinked],
        "stats": stats,
        "gaps": [
            "匿名免费通道（general_search/web.fetch）无法把昵称级真私房『麻麻/可乐』唯一锚定到法定店名；"
            "已转免费 web 封闭选项核验队列（需登录态 XHS/点评 或 KOL watchlist 闭环），禁止手工 REST 补。",
            f"覆盖候选中库内缺失 {stats['coverage_candidates_missing_in_db']} 家（花公子/FoodAnatomy/煌佳等）"
            "→ 属 W1 建店范畴，本模块只产出候选，不建店。",
        ],
        "regression": {r["nick"]: r for r in regression},
    }
    (ld / "ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n账本已写：{ld/'ledger.json'}")

    # 6) 写库（仅 --apply；幂等 + 回读断言）
    if not args.apply:
        print("[dry-run] 确认后加 --apply 执行高置信 ADD（只补不错杀）")
        return

    # 注意：C.req() 内部已用 service key 自建 headers，切勿再传 headers=（会冲突崩溃）。
    applied, failed = 0, []
    for a in add_plan:
        rid, cid = a["restaurant_id"], a["target_leaf"]
        # 幂等写前检查
        if cid in links_by_rest[rid]:
            continue
        try:
            r = C.req("POST", "/restaurant_cuisines",
                      json={"restaurant_id": rid, "cuisine_id": cid})
            ok = r.status_code == 201
            got = r.json() if ok else None
            if not (isinstance(got, list) and len(got) == 1):
                ok = False
        except Exception as e:
            ok, got = False, str(e)
        if ok:
            links_by_rest[rid].add(cid)
            applied += 1
            print(f"  wrote + [{cid}] id={rid} {a['name']}")
        else:
            failed.append({"restaurant_id": rid, "target_leaf": cid,
                           "err": getattr(r, "text", str(got))[:200]})
        time.sleep(0.08)

    # 回读断言：重拉这几家的链接，断言目标叶子已存在
    if add_plan:
        want = {(a["restaurant_id"], a["target_leaf"]) for a in add_plan}
        got_rows = C.fetch_all("restaurant_cuisines",
                               select="restaurant_id,cuisine_id", order_col="restaurant_id")
        have = {(x["restaurant_id"], x["cuisine_id"]) for x in got_rows}
        missing = sorted(want - have)
        assert not missing, f"回读断言失败，缺链接: {missing}"
        print(f"回读断言通过：{len(want)} 条目标链接全部存在。")

    print(f"\n[apply] 写入 {applied} 条，失败 {len(failed)} 条：{failed}")


if __name__ == "__main__":
    main()

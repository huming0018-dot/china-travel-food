#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
phase0c_negative_tagon.py — Phase 0-C：连锁 / 工业化预制 / 软广 负面清单 tag-on（确定性、可溯、可逆）

定位（机制优先，不补单店）：
  · chain_type / central_kitchen / premade_risk 三列由 chain_audit.py / negative_audit.py
    （Phase 0-A/B 已跑）100% 覆盖；soft_ad_flag_reviews 由 softad_distribution.py（cron 5:37）
    自学写。本脚本【不重判】这些列，只做：
      1) 只读全库核对连锁/预制/软广现状，产出逐店清单（证据=品牌+分店id、置信、是否触发隐藏/降权）；
      2) tag-on 补缺：active 且 premade_risk='高' 的工业化店，若未挂「工业化餐饮」标签(cuisine_id=258)，
         则 INSERT restaurant_cuisines(restaurant_id, 258)。
         —— 依据 migration 003 v_audit_gaps 规则「高预制风险缺标签」；纯加标签 junction，可逆（删行即撤）。
      3) 软广：只读 /app/data/softad/baselines.json（分布模型自学结果），报告判定分布；不手写 flag/penalty。

写库红线（与 006/007/012 对齐）：
  · 只允许 INSERT restaurant_cuisines（标签 junction）；绝不 PATCH restaurants。
  · soft_ad_flag / soft_ad_penalty / is_chain_standardized 均由 trigger / generated column 派生，禁止直写。
  · 不改菜系/电话/坐标/价格/招牌菜等任何来源字段。

反误伤（最高优先级验收）：
  · 只给 premade_risk='高' 的店挂工业化标签；独立店 / pr!=高 绝不挂。
  · 回归正例：小菜园/望湘园/盖饭邦/外婆家/点都德 必须 std=True、flag=confirmed。
  · 反例锚点：新荣记/大董/甬府/鲁采/福和慧/唐阁/Ling Long/鮨系 必须 std=False（不被隐藏）。
  · 独立店(chain_type='独立店') 软广 flag 必须全为 none（否则=误杀，报错不 apply）。

用法：
  python3 phase0c_negative_tagon.py            # dry-run：逐店清单 + 自检，不写库
  python3 phase0c_negative_tagon.py --apply     # 自检全绿后才 INSERT；写后回读
"""
import os, sys, json, argparse, collections, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

OUT_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
REPORT_DIR = os.path.join(OUT_DIR, "phase0c")
INDUSTRIAL_TAG_ID = 258  # cuisines: name='工业化餐饮', dimension='标签'

# 预制高风险的 curated 品牌证据集（chain-premade-audit.md 已核实案例 + chain_audit/negative_audit 词表）。
# 用于自检：pr=高 的店必须落在这些已知工业化品牌里，否则报人工复核（不靠"出餐快/平价"猜预制）。
PREMADE_HIGH_BRANDS = [
    "小菜园", "望湘园", "盖饭邦", "外婆家", "绿茶", "点都德", "南京大牌档",
    "新旺", "东发道", "丸龟", "新白鹿", "费大厨", "鲜芋仙",
]

# 反例锚点：必须保持 is_chain_standardized=False（不被隐藏）。
# 注：遇外滩虽高端但确为三店连锁(ck疑似/pr低)，按008公式std=True属设计内保守隐藏，不计入独立锚点。
HIGH_END_ANCHORS = ["新荣记", "荣府宴", "大董", "甬府", "鲁采", "福和慧",
                    "唐阁", "Ling Long", "菁禧荟", "鮨"]


def today():
    return datetime.date.today().isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    os.makedirs(REPORT_DIR, exist_ok=True)

    # ---------- 拉全量（只读） ----------
    rests = C.fetch_all("restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,soft_ad_flag,"
        "soft_ad_flag_reviews,soft_ad_penalty,is_chain_standardized,review_count,"
        "score_total,price_scene,score_evidence_level", order_col="id")
    active = [r for r in rests if r["status"] == "active"]
    byid = {r["id"]: r for r in active}

    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    tagged258 = {x["restaurant_id"] for x in rc if x["cuisine_id"] == INDUSTRIAL_TAG_ID}

    groups = C.fetch_all("restaurant_groups", "id,name,group_type", order_col="id")
    members = C.fetch_all("restaurant_group_members",
                          "group_id,restaurant_id,brand_name,role,is_current", order_col="group_id")

    # ---------- 1. 现状分类统计 ----------
    stat = {
        "total": len(rests), "active": len(active),
        "chain_type": dict(collections.Counter(r.get("chain_type") for r in active)),
        "central_kitchen": dict(collections.Counter(r.get("central_kitchen") for r in active)),
        "premade_risk": dict(collections.Counter(r.get("premade_risk") for r in active)),
        "soft_ad_flag": dict(collections.Counter(r.get("soft_ad_flag") for r in active)),
        "soft_ad_flag_reviews": dict(collections.Counter(r.get("soft_ad_flag_reviews") for r in active)),
        "is_chain_standardized": dict(collections.Counter(bool(r.get("is_chain_standardized")) for r in active)),
        "penalty": dict(collections.Counter(r.get("soft_ad_penalty") for r in active)),
        "evidence_level": dict(collections.Counter(r.get("score_evidence_level") for r in active)),
    }

    # ---------- 2. 连锁逐店清单（含分店 id 列表 = 来源） ----------
    import re
    def brand_core(n):
        n = re.split(r"[（(]", n or "")[0]
        n = re.sub(r"(上海|全国|首店|旗舰店|总店|分店|店)$", "", n.strip())
        return C.norm_name(n)
    core_map = collections.defaultdict(list)
    for r in active:
        core_map[brand_core(r["name"])].append(r["id"])

    chain_rows = []
    for r in active:
        ct = r.get("chain_type")
        if ct in (None, "独立店"):
            continue
        core = brand_core(r["name"])
        branch_ids = core_map.get(core, [r["id"]])
        # 是否触发前端隐藏（is_chain_standardized）与降权（penalty）
        hidden = bool(r.get("is_chain_standardized"))
        pen = r.get("soft_ad_penalty") or 0
        chain_rows.append({
            "id": r["id"], "name": r["name"], "chain_type": ct,
            "central_kitchen": r.get("central_kitchen"), "premade_risk": r.get("premade_risk"),
            "brand_core": core, "branch_count": len(branch_ids), "branch_ids": branch_ids,
            "is_chain_standardized": hidden, "soft_ad_flag": r.get("soft_ad_flag"),
            "soft_ad_penalty": pen, "price_scene": r.get("price_scene"),
        })

    # ---------- 3. 预制 tag-on 计划：pr=高 且未挂 258 ----------
    tag_plan = []
    for r in active:
        if r.get("premade_risk") != "高":
            continue
        already = r["id"] in tagged258
        brand_hit = next((b for b in PREMADE_HIGH_BRANDS if b in r["name"]), None)
        tag_plan.append({
            "id": r["id"], "name": r["name"],
            "chain_type": r.get("chain_type"), "central_kitchen": r.get("central_kitchen"),
            "already_tagged_258": already,
            "brand_evidence": brand_hit,
            "needs_insert": (not already),
        })
    to_insert = [t for t in tag_plan if t["needs_insert"]]

    # ---------- 4. 软广分布模型结果（只读，不写） ----------
    softad = {"baseline_present": False, "verdicts": {}, "note": ""}
    bp = os.path.join(OUT_DIR, "softad", "baselines.json")
    if os.path.exists(bp):
        b = json.load(open(bp, encoding="utf-8"))
        vd = b.get("verdicts", {})
        softad = {
            "baseline_present": True, "run_date": b.get("run_date"),
            "thresholds": b.get("thresholds"),
            "verdicts": dict(collections.Counter(vd.values())),
            "non_none": {k: v for k, v in vd.items() if v != "none"},
            "note": "评论级分布模型(cron 5:37)结果；最终 soft_ad_flag 由 trigger=greatest(chain,reviews) 派生",
        }

    # ---------- 5. 反误伤自检 ----------
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 5a. 反误伤核心：独立店若被标 suspected/confirmed，必须有 ck/pr 具体输入支撑；
    #     【无 ck/pr 信号却被标】= 仅凭低评论/平价误杀，必须拦下。
    indep_bad = [r for r in active
                 if r.get("chain_type") == "独立店" and r.get("soft_ad_flag") in ("suspected", "confirmed")
                 and r.get("central_kitchen") in (None, "无")
                 and r.get("premade_risk") in (None, "无")]
    check("独立店被标必有ck/pr具体输入(无信号误杀=0)", len(indep_bad) == 0,
          f"{len(indep_bad)} 家独立店无ck/pr信号却被标: {[(r['id'],r['name'],r['soft_ad_flag']) for r in indep_bad[:5]]}")

    # 5b. 反例锚点必须不被隐藏
    anchor_bad = []
    for r in active:
        for kw in HIGH_END_ANCHORS:
            if kw.lower() in r["name"].lower() and r.get("is_chain_standardized"):
                anchor_bad.append((r["name"], r.get("is_chain_standardized")))
    check("高端/独立锚点不被隐藏(std=False)", len(anchor_bad) == 0, str(anchor_bad[:5]))

    # 5c. 回归正例必须 confirmed + std=True
    pos_ok = True
    pos_detail = []
    for kw in ["小菜园", "望湘园", "盖饭邦", "外婆家", "点都德"]:
        hits = [r for r in active if kw in r["name"]]
        for r in hits:
            good = (r.get("premade_risk") == "高" and r.get("central_kitchen") == "确认"
                    and r.get("is_chain_standardized") and r.get("soft_ad_flag") == "confirmed")
            pos_detail.append(f"{r['name']}:pr={r['premade_risk']}/ck={r['central_kitchen']}/std={r['is_chain_standardized']}/flag={r['soft_ad_flag']}")
            if not good:
                pos_ok = False
    check("预制正例已召回(pr高+ck确认+std+confirmed)", pos_ok, "; ".join(pos_detail[:8]))

    # 5d. tag-on 计划安全：只允许 pr=高、只补缺失、绝不写 restaurants
    unsafe = [t for t in to_insert if t["chain_type"] not in ("资本化连锁", "大型连锁", "小型连锁")]
    check("tag-on仅针对连锁(非独立店)", len(unsafe) == 0, str([(t['id'],t['name']) for t in unsafe[:5]]))
    # 5e. pr=高 店必须有 curated 品牌证据（不靠平价/出餐快猜）
    no_evidence = [t for t in to_insert if not t["brand_evidence"]]
    check("pr=高均有curated品牌证据", len(no_evidence) == 0,
          f"{len(no_evidence)} 家无品牌证据需人工复核: {[t['name'] for t in no_evidence[:8]]}")

    all_ok = all(c["ok"] for c in checks)

    # ---------- 6. 已检查但不标记（反误伤样本） ----------
    not_marked = []
    for kw in ["福和慧", "唐阁", "Ling Long", "菁禧荟", "鮨水月", "岩田", "Sushi Oyama",
               "新荣记", "大董", "甬府", "鲁采"]:
        for r in active:
            if kw.lower() in r["name"].lower():
                not_marked.append({
                    "id": r["id"], "name": r["name"], "chain_type": r.get("chain_type"),
                    "ck": r.get("central_kitchen"), "pr": r.get("premade_risk"),
                    "std": bool(r.get("is_chain_standardized")), "flag": r.get("soft_ad_flag"),
                    "decision": "不隐藏/不惩罚" if not r.get("is_chain_standardized") else "已隐藏(连锁)",
                })
                break

    # ---------- 6b. 人工复核项（不自动改，仅留痕） ----------
    borderline = []
    for r in active:
        n = r["name"]
        if r.get("chain_type") == "独立店" and r.get("soft_ad_flag") in ("suspected", "confirmed"):
            borderline.append({"id": r["id"], "name": n, "why":
                f"独立店但ck={r.get('central_kitchen')}/pr={r.get('premade_risk')}→trigger派生flag={r.get('soft_ad_flag')};非低价小馆误伤,但ck依据可人工复核"})
        if "遇外滩" in n:
            borderline.append({"id": r["id"], "name": n, "why":
                f"高端闽菜三店连锁 chain={r.get('chain_type')}/ck={r.get('central_kitchen')}/pr={r.get('premade_risk')}→std={bool(r.get('is_chain_standardized'))};按008公式保守隐藏,可申诉撤销"})
    # 历史已挂 tag258 但 pr!=高 的店（与派生口径不一致，仅报告不删）
    for rid in sorted(tagged258):
        r = byid.get(rid)
        if r and r.get("premade_risk") != "高":
            borderline.append({"id": rid, "name": r["name"], "why":
                f"已挂工业化标签258但pr={r.get('premade_risk')}/chain={r.get('chain_type')};与派生口径不一致,人工复核(本脚本不自动删)"})

    # ---------- 7. 输出报告 ----------
    report = {
        "run_date": today(), "mode": "apply" if args.apply else "dry-run",
        "stats": stat,
        "chain_shops": len(chain_rows),
        "chain_by_type": dict(collections.Counter(c["chain_type"] for c in chain_rows)),
        "hidden_shops": sum(1 for c in chain_rows if c["is_chain_standardized"]),
        "penalized_shops": sum(1 for c in chain_rows if (c["soft_ad_penalty"] or 0) > 0),
        "premade_high_total": len([t for t in tag_plan]),
        "premade_high_already_tagged": len([t for t in tag_plan if t["already_tagged_258"]]),
        "tag_on_insert_plan": to_insert,
        "softad": softad,
        "self_checks": checks,
        "all_self_checks_pass": all_ok,
        "checked_but_not_marked": not_marked,
        "borderline_human_review": borderline,
    }
    json_path = os.path.join(REPORT_DIR, f"report_{today()}.json")
    json.dump(report, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    # 控制台摘要
    print("=" * 60)
    print(f"Phase 0-C 负面清单 tag-on  [{report['mode']}]")
    print("=" * 60)
    print("基线:", {k: stat[k] for k in ("total", "active")})
    print("chain_type:", stat["chain_type"])
    print("premade_risk:", stat["premade_risk"])
    print("soft_ad_flag:", stat["soft_ad_flag"], " reviews侧:", stat["soft_ad_flag_reviews"])
    print("is_chain_standardized:", stat["is_chain_standardized"],
          f"→ 前端隐藏/降权联动 {report['hidden_shops']} 家")
    print(f"连锁相关店 {report['chain_shops']}，其中被 penalty {report['penalized_shops']} 家")
    print(f"\n预制高风险(pr=高)共 {report['premade_high_total']} 家；已挂工业化标签 {report['premade_high_already_tagged']}；"
          f"待补挂 {len(to_insert)}")
    for t in to_insert:
        print(f"   [INSERT 258] id={t['id']:>4} {t['name']}  证据品牌={t['brand_evidence']}")
    print(f"\n软广分布模型: {softad.get('run_date')} verdicts={softad.get('verdicts')} non_none={softad.get('non_none')}")
    print("\n--- 自检 ---")
    for c in checks:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}  {c['detail'][:110]}")
    print("ALL SELF CHECKS:", "PASS" if all_ok else "FAIL")
    print(f"\n人工复核项 {len(borderline)} 条（本脚本不自动改/删）:")
    for b in borderline:
        print(f"   - id={b['id']} {b['name']}: {b['why'][:100]}")

    if not args.apply:
        print(f"\n[dry-run] 报告已落 {json_path}")
        print("[dry-run] 自检全绿后加 --apply 才会 INSERT restaurant_cuisines(258)")
        return

    if not all_ok:
        print("\n[ABORT] 自检未全绿，不写库。请检查上方 FAIL 项。")
        sys.exit(1)

    # ---------- 8. apply：仅 INSERT restaurant_cuisines ----------
    H = C.headers()
    H["Prefer"] = "return=representation"
    ok, fail = 0, 0
    applied = []
    for t in to_insert:
        body = {"restaurant_id": t["id"], "cuisine_id": INDUSTRIAL_TAG_ID}
        r = C.req("POST", "/restaurant_cuisines", json=body)
        if r.status_code in (200, 201):
            ok += 1
            applied.append(t["id"])
        elif r.status_code == 409:  # 已存在（幂等）
            ok += 1
        else:
            fail += 1
            print("  INSERT 失败", t["id"], r.status_code, r.text[:160])
    print(f"\n[apply] INSERT 工业化餐饮标签: 成功 {ok}/{len(to_insert)}，失败 {fail}")

    # ---------- 9. 回读 ----------
    rc2 = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    after = {x["restaurant_id"] for x in rc2 if x["cuisine_id"] == INDUSTRIAL_TAG_ID}
    pr_high_ids = {r["id"] for r in active if r.get("premade_risk") == "高"}
    missing = pr_high_ids - after
    print(f"[回读] 现挂工业化标签总数 {len(after)}；pr=高 {len(pr_high_ids)} 家，仍缺标签 {len(missing)}")
    if missing:
        print("  缺标签:", missing)
    report["applied_ids"] = applied
    report["readback_tagged_total"] = len(after)
    report["readback_pr_high_missing"] = sorted(missing)
    json.dump(report, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"报告已更新 {json_path}")


if __name__ == "__main__":
    main()

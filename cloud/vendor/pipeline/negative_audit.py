#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
negative_audit.py — 负面清单与淘汰机制审计（软标记，禁物理删除）

在 chain_audit.py v2 基础上扩充：
  R1 小型连锁 ck/pr 补全（pr=低→ck=疑似, pr=无→ck=无, 现做多店保留）。
  R2 预制菜/中央厨房品牌名扩充词表（已知料理包/标准化连锁，未入 CAPITAL/LARGE 的）。
  R3 低质量无口碑店：score_total<55 且 review_count=0 的 active 店 → 软标记待出清。
     （soft_ad_flag=suspected, soft_ad_penalty≥20, is_chain_standardized=true）
  R4 资本化/大型连锁但 soft_ad_flag=none → 补 soft_ad_flag=suspected, penalty=10。
  R5 大型/资本化连锁且 is_chain_standardized=false 但 ck=确认 → 补 standardized=true。

值域硬约束（CHECK）：
  chain_type: 独立店/小型连锁/大型连锁/资本化连锁
  central_kitchen: 无/疑似/确认
  premade_risk: 无/低/疑似/高
  soft_ad_flag: none/suspected/confirmed

用法：
  python3 negative_audit.py            # dry-run，落 negative_plan.json
  python3 negative_audit.py --commit   # PATCH
"""
import argparse
import collections
import json
import pathlib
import re

import common as C

ROOT = pathlib.Path(C.DEFAULT_APP).parent

# R2: 预制菜/标准化连锁品牌扩充词表（未在 chain_audit.CAPITAL/LARGE 中的）
# (关键词, chain_type, central_kitchen, premade_risk)
PREMADE_EXTRA = [
    # 快餐/便当/盖饭类（强中央厨房、料理包）
    ("米村拌饭", "大型连锁", "确认", "高"),
    ("农耕记", "大型连锁", "确认", "高"),
    ("费大厨", "大型连锁", "确认", "高"),
    ("太二", "大型连锁", "确认", "高"),
    ("探鱼", "大型连锁", "确认", "高"),
    ("九毛九", "大型连锁", "确认", "高"),
    ("西贝", "大型连锁", "疑似", "高"),
    ("真功夫", "大型连锁", "确认", "高"),
    ("大米先生", "大型连锁", "确认", "高"),
    ("老乡鸡", "大型连锁", "确认", "高"),
    ("老娘舅", "大型连锁", "确认", "高"),
    ("阿香米线", "大型连锁", "确认", "高"),
    ("陈香贵", "大型连锁", "确认", "高"),
    ("马记永", "大型连锁", "确认", "高"),
    ("张拉拉", "大型连锁", "确认", "高"),
    ("霸蛮", "大型连锁", "确认", "高"),
    ("遇见小面", "大型连锁", "确认", "疑似"),
    ("永和大王", "大型连锁", "确认", "高"),
    ("吉祥馄饨", "大型连锁", "确认", "疑似"),
    ("巴比馒头", "大型连锁", "确认", "高"),
    # 茶饮/咖啡（强供应链）
    ("一点点", "资本化连锁", "确认", "疑似"),
    ("CoCo", "资本化连锁", "确认", "疑似"),
    ("coco都可", "资本化连锁", "确认", "疑似"),
    ("快乐柠檬", "资本化连锁", "确认", "疑似"),
    ("茶颜悦色", "资本化连锁", "确认", "疑似"),
    ("书亦烧仙草", "资本化连锁", "确认", "疑似"),
    ("塔斯汀", "资本化连锁", "确认", "高"),
    ("华莱士", "资本化连锁", "确认", "高"),
    ("德克士", "资本化连锁", "确认", "高"),
    ("M Stand", "资本化连锁", "确认", "疑似"),
    ("Seesaw", "资本化连锁", "确认", "疑似"),
    ("% Arabica", "资本化连锁", "疑似", "疑似"),
    ("%Arabica", "资本化连锁", "疑似", "疑似"),
    # 烘焙甜品（中央厨房配送为主）
    ("好利来", "大型连锁", "确认", "疑似"),
    ("味多美", "大型连锁", "确认", "疑似"),
    ("85度C", "大型连锁", "确认", "疑似"),
    ("85°C", "大型连锁", "确认", "疑似"),
    ("面包新语", "大型连锁", "确认", "疑似"),
    ("巴黎贝甜", "大型连锁", "确认", "疑似"),
    ("多乐之日", "大型连锁", "确认", "疑似"),
    ("原麦山丘", "大型连锁", "确认", "疑似"),
    ("满记甜品", "大型连锁", "确认", "高"),
    ("鲜芋仙", "大型连锁", "确认", "高"),
    ("乐乐茶", "资本化连锁", "确认", "疑似"),
    # 日式连锁
    ("丸龟", "大型连锁", "确认", "高"),
    ("花丸", "大型连锁", "确认", "高"),
    ("CoCo壱", "大型连锁", "确认", "高"),
    ("CoCo壱番屋", "大型连锁", "确认", "高"),
    ("食其家", "大型连锁", "确认", "高"),  # 已在 LARGE，幂等
    # 中式连锁正餐（疑似预制）
    ("外婆家", "大型连锁", "确认", "高"),  # 幂等
    ("绿茶", "大型连锁", "确认", "高"),
    ("新白鹿", "大型连锁", "确认", "高"),
    ("弄堂里", "大型连锁", "确认", "高"),
    ("桂满陇", "小型连锁", "疑似", "低"),  # REGIONAL_HINT 已有，升级
    # 火锅连锁
    ("呷哺", "大型连锁", "确认", "高"),
    ("呷哺呷哺", "大型连锁", "确认", "高"),
    ("凑凑", "大型连锁", "确认", "疑似"),
    ("左庭右院", "大型连锁", "疑似", "低"),  # 幂等
]

# R3: 低质量店分数阈值
LOW_SCORE_CUTOFF = 55.0


def match_premade_extra(name: str):
    low = name.lower()
    for kw, ct, ck, pr in PREMADE_EXTRA:
        if kw.lower() in low:
            return kw, ct, ck, pr
    return None


# 严重度排序（用于"只补更弱、不覆盖更强"）
CK_RANK = {"无": 0, "疑似": 1, "确认": 2}
PR_RANK = {"无": 0, "低": 1, "疑似": 2, "高": 3}


def evidenced_types(fact_claims):
    """已有带 source_url 证据的 claim type 集合（证据为准，规则不得覆盖）。"""
    return {c.get("type") for c in (fact_claims or [])
            if c.get("source_url") and c.get("type")}


def rule_candidate(ck, pr):
    """词表只产生候选：硬标签(确认/高)未经取证一律封顶为疑似；
    硬标签晋升必须经 claims_seed 带证据（fact_verify）。"""
    return ("疑似" if ck == "确认" else ck,
            "疑似" if pr == "高" else pr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all(
        "restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk,review_count,"
        "score_total,review_confidence,soft_ad_flag,soft_ad_penalty,"
        "is_chain_standardized,price_avg,investor_info,fact_claims",
        order_col="id",
    )
    active = [r for r in rests if r["status"] == "active"]

    plan = []          # 写库计划
    evidence = []      # 出清清单证据
    stats = collections.Counter()

    for r in active:
        rid, name = r["id"], r["name"]
        patch = {}
        reasons = []

        # ---- R2: 预制品牌扩充词表（只产生候选；硬标签需证据→走 claims_seed）----
        m = match_premade_extra(name)
        if m:
            kw, ct, ck, pr = m
            ck_c, pr_c = rule_candidate(ck, pr)
            ev = evidenced_types(r.get("fact_claims"))
            # 已有带 URL 证据的字段以证据为准，规则不覆盖；否则只在现状更弱时补候选
            if "central_kitchen" not in ev and CK_RANK.get(r.get("central_kitchen"), 0) < CK_RANK[ck_c]:
                patch["central_kitchen"] = ck_c
            if "premade_risk" not in ev and PR_RANK.get(r.get("premade_risk"), 0) < PR_RANK[pr_c]:
                patch["premade_risk"] = pr_c
            # chain_type 是规模轴，词表是合理信号：空或被误判为独立店时补
            if not r.get("chain_type"):
                patch["chain_type"] = ct
            elif r["chain_type"] == "独立店" and ct in ("大型连锁", "资本化连锁"):
                patch["chain_type"] = ct
            # is_chain_standardized 为 generated column，由 DB 据 chain_type/ck/pr/soft 推导，禁直写
            reasons.append(f"R2候选品牌[{kw}](未经取证,ck/pr封顶疑似)")
            stats["R2_premade_candidate"] += 1

        # ---- R1: 小型连锁 ck 补全 ----
        if r.get("chain_type") == "小型连锁" and not r.get("central_kitchen"):
            pr = r.get("premade_risk")
            if pr in ("高", "疑似"):
                patch["central_kitchen"] = "疑似"
                reasons.append(f"R1小型连锁pr={pr}→ck=疑似")
                stats["R1_small_ck_suspect"] += 1
            elif pr == "低":
                patch["central_kitchen"] = "疑似"
                reasons.append("R1小型连锁pr=低→ck=疑似")
                stats["R1_small_ck_suspect"] += 1
            elif pr == "无":
                patch["central_kitchen"] = "无"
                reasons.append("R1小型连锁pr=无→ck=无(现做多店保留)")
                stats["R1_small_ck_none"] += 1

        # ---- R4: 大型/资本化连锁但 soft_ad=none → 补 soft_ad 标记 ----
        if (r.get("chain_type") in ("大型连锁", "资本化连锁")
                and r.get("soft_ad_flag") == "none"):
            patch["soft_ad_flag"] = "suspected"
            cur_pen = r.get("soft_ad_penalty") or 0
            if cur_pen < 10:
                patch["soft_ad_penalty"] = 10
            reasons.append("R4连锁未标soft_ad→suspected+penalty10")
            stats["R4_chain_soft_ad"] += 1

        # ---- R5: 大型/资本化连锁且 ck=确认 → 由 generated column 自动推导 standardized，无需直写 ----
        # (is_chain_standardized 是 generated column)

        # ---- R3: 低质量无口碑店（score<55 且 review=0）→ 待出清软标记 ----
        rc = r.get("review_count") or 0
        st = r.get("score_total") or 0
        if rc == 0 and st < LOW_SCORE_CUTOFF:
            # 不降低已有 confirmed 标记；penalty 取 max
            if r.get("soft_ad_flag") != "confirmed":
                patch["soft_ad_flag"] = "suspected"
            cur_pen = r.get("soft_ad_penalty") or 0
            if cur_pen < 20:
                patch["soft_ad_penalty"] = 20
            reasons.append(f"R3低质量无口碑(score={st},review=0)→soft+sink")
            stats["R3_low_quality"] += 1

        if patch:
            plan.append({
                "id": rid, "name": name, "patch": patch,
                "reasons": reasons,
                "score_total": st, "review_count": rc,
                "chain_type": r.get("chain_type"),
                "premade_risk": r.get("premade_risk"),
                "central_kitchen": r.get("central_kitchen"),
            })
            evidence.append({
                "id": rid, "name": name, "reasons": reasons,
                "patch": patch,
                "score_total": st, "review_count": rc,
            })

    print(f"负面审计：{len(plan)} 家待更新")
    print("分类统计:", dict(stats))
    # 按 patch 字段汇总
    field_ct = collections.Counter()
    for p in plan:
        for k in p["patch"]:
            field_ct[k] += 1
    print("字段写入次数:", dict(field_ct))

    out = {
        "generated_at": C.today(),
        "summary": {
            "total_patch": len(plan),
            "by_rule": dict(stats),
            "by_field": dict(field_ct),
        },
        "plan": plan,
    }
    with open("negative_plan.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已落 negative_plan.json")

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
            print("  失败:", p["id"], p["name"], r.status_code, r.text[:200])
    print(f"commit 完成 {n}/{len(plan)}，失败 {fail}")


if __name__ == "__main__":
    main()

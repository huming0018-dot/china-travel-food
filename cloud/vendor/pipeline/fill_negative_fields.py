#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_negative_fields.py — P0-3 负面清单跑全：补全 chain_type/central_kitchen/premade_risk 三字段

值域（库 CHECK 约束，003/008）：
  chain_type:    独立店 / 小型连锁 / 大型连锁 / 资本化连锁
  central_kitchen: 无 / 疑似 / 确认
  premade_risk:    无 / 低 / 疑似 / 高

口径：
  A. 独立店 且 ck IS NULL 且 pr IS NULL → ck=无, pr=无（独立小店无中央厨房无预制）
  B. 人工判定表 MANUAL（21 个 chain_type NULL + 3 个 pr=低 的异常独立店）
只 PATCH 这三个字段，不动其他列；写前备份到 backups/。
用法：
  python3 fill_negative_fields.py            # dry-run，落 fill_plan.json
  python3 fill_negative_fields.py --commit   # 先备份再 PATCH
"""
import argparse
import collections
import datetime
import json
import pathlib
import time

import common as C

ROOT = pathlib.Path(C.DEFAULT_APP).parent
BACKUP_DIR = ROOT / "backups" / f"negative_fill_{C.today()}"

# ---- B: 人工判定（id -> patch）。证据见 HANDOFF / 本次扫描 ----
MANUAL = {
    # 关店 7
    905:  {"chain_type": "大型连锁", "central_kitchen": "无", "premade_risk": "无"},   # CHIC1699远洋私厨 黑珍珠闽菜品牌
    1139: {"chain_type": "大型连锁", "central_kitchen": "无", "premade_risk": "无"},   # Robuchon 国际fine dining品牌
    1262: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # EHB 单一北欧bistro项目
    1435: {"chain_type": "大型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 玉芝兰 兰桂均品牌
    1684: {"chain_type": "资本化连锁", "central_kitchen": "确认", "premade_risk": "疑似"},  # Seesaw 精品咖啡连锁
    1927: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 鮨心和 12座板前omakase
    1967: {"chain_type": "大型连锁", "central_kitchen": "无", "premade_risk": "无"},   # Nuits 植庭集团旗下bistro
    # 营业 14
    1989: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 时相遇 独栋老洋房茶馆
    1990: {"chain_type": "小型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 少山集 2店(创邑+陆家嘴)
    1991: {"chain_type": "大型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 隐溪茶馆 30余家连锁
    1992: {"chain_type": "小型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 黄庭茶馆 10余家连锁
    1993: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 广记鱼生 社区现切
    1994: {"chain_type": "小型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 渔八公 全国连锁上海店 现切
    1995: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 鱼城主 老板现切
    1996: {"chain_type": "小型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 粤桂發 全国连锁 现切
    1997: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 酥鱼坊 菜场档口现炸
    1998: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 阿模灵鸡粥 菜场档口
    1999: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 妃灵蛋糕 菜场甜品档
    2000: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # 潘记老面羌饼 菜场摊
    2001: {"chain_type": "小型连锁", "central_kitchen": "无", "premade_risk": "无"},   # 胡老头鱼丸 杨浦多分店手工
    2002: {"chain_type": "独立店",   "central_kitchen": "无", "premade_risk": "无"},   # Ministry of Crab 海外名店单店(对标Hakkasan/8½)
    # 3 个异常独立店（pr=低, ck=NULL）
    1982: {"chain_type": "小型连锁", "central_kitchen": "疑似"},   # 望庐·精细江西菜(外滩) 2店
    1983: {"chain_type": "小型连锁", "central_kitchen": "疑似"},   # 望庐·江西荟馆(前滩)
    1984: {"central_kitchen": "疑似"},                              # POP露台(外滩三号) 酒店餐厅 pr=低
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    rests = C.fetch_all(
        "restaurants",
        "id,name,status,chain_type,central_kitchen,premade_risk",
        order_col="id",
    )
    byid = {r["id"]: r for r in rests}

    # A. 批量：独立店 且 ck/pr 均 NULL
    bulk_ids = [r["id"] for r in rests
                if r.get("chain_type") == "独立店"
                and not r.get("central_kitchen")
                and not r.get("premade_risk")]
    # A2. 独立店 pr=低 ck=NULL（不在 bulk，交给 manual）
    for_manual_extra = [r["id"] for r in rests
                        if r.get("chain_type") == "独立店"
                        and not r.get("central_kitchen")
                        and r.get("premade_risk") == "低"]

    print(f"A. 批量独立店(ck/pr均NULL): {len(bulk_ids)} 家 -> ck=无, pr=无")
    print(f"A2. 独立店 pr=低 ck=NULL: {for_manual_extra}")

    # 校验 manual 里没有意外覆盖已有非空字段
    plan = []
    for rid, patch in MANUAL.items():
        cur = byid.get(rid)
        if not cur:
            print("  !! manual id 不在库:", rid); continue
        eff = {}
        for k, v in patch.items():
            old = cur.get(k)
            if old != v:
                eff[k] = v
        if eff:
            plan.append({"id": rid, "name": cur["name"], "patch": eff,
                         "before": {k: cur.get(k) for k in ("chain_type", "central_kitchen", "premade_risk")}})

    print(f"B. 人工判定: {len(plan)} 家有变更")
    for p in plan:
        print(f"   {p['id']:5d} {p['name'][:30]:30s}  {p['before']} -> {p['patch']}")

    # 统计写后分布
    post_ct, post_ck, post_pr = collections.Counter(), collections.Counter(), collections.Counter()
    for r in rests:
        rid = r["id"]
        ct = r.get("chain_type"); ck = r.get("central_kitchen"); pr = r.get("premade_risk")
        if rid in bulk_ids:
            ck, pr = "无", "无"
        if rid in MANUAL:
            for k, v in MANUAL[rid].items():
                if k == "chain_type": ct = v
                elif k == "central_kitchen": ck = v
                elif k == "premade_risk": pr = v
        post_ct[ct or "NULL"] += 1
        post_ck[ck or "NULL"] += 1
        post_pr[pr or "NULL"] += 1
    print("\n写后预测分布:")
    print("  chain_type:", dict(post_ct))
    print("  central_kitchen:", dict(post_ck))
    print("  premade_risk:", dict(post_pr))
    null_after = sum(1 for r in rests if (lambda rid, ct, ck, pr:
        (ck == "无" and pr == "无" and rid in bulk_ids) or
        (rid in MANUAL) or
        (ct and ck and pr))(r["id"], r.get("chain_type"), r.get("central_kitchen"), r.get("premade_risk")))
    # 计算剩余 NULL
    rem = 0
    for r in rests:
        rid = r["id"]
        ck = r.get("central_kitchen"); pr = r.get("premade_risk"); ct = r.get("chain_type")
        if rid in bulk_ids:
            ck, pr = "无", "无"
        if rid in MANUAL:
            m = MANUAL[rid]
            ct = m.get("chain_type", ct); ck = m.get("central_kitchen", ck); pr = m.get("premade_risk", pr)
        if not ct or not ck or not pr:
            rem += 1
    print(f"写后仍有任一字段为 NULL 的店: {rem}")

    out = {"bulk_ids": bulk_ids, "manual": plan,
           "post_dist": {"chain_type": dict(post_ct), "central_kitchen": dict(post_ck),
                         "premade_risk": dict(post_pr)}}
    pathlib.Path("fill_plan.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    print("\n已落 fill_plan.json")

    if not args.commit:
        print("[dry-run] 确认后加 --commit")
        return

    # ---- 备份 ----
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    snap = C.fetch_all("restaurants",
                       "id,name,status,chain_type,central_kitchen,premade_risk",
                       order_col="id")
    (BACKUP_DIR / "restaurants_3fields_before.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"备份已存: {BACKUP_DIR/'restaurants_3fields_before.json'} ({len(snap)} 行)")

    # ---- A. 批量 PATCH：用过滤器一次更新 ----
    r = C.req("PATCH",
              "/restaurants?chain_type=eq.独立店&central_kitchen=is.null&premade_risk=is.null",
              json={"central_kitchen": "无", "premade_risk": "无"})
    if r.status_code not in (200, 204):
        print("批量 PATCH 失败:", r.status_code, r.text[:300]); return
    cr = r.headers.get("content-range", "")
    print(f"A. 批量 PATCH 完成，返回 content-range={cr}")
    time.sleep(0.5)

    # ---- B. 人工逐条 PATCH ----
    n, fail = 0, 0
    for p in plan:
        rr = C.req("PATCH", f"/restaurants?id=eq.{p['id']}", json=p["patch"])
        if rr.status_code in (200, 204):
            n += 1
        else:
            fail += 1
            print("  失败:", p["id"], p["name"], rr.status_code, rr.text[:200])
    print(f"B. 人工 PATCH 完成 {n}/{len(plan)}，失败 {fail}")


if __name__ == "__main__":
    main()

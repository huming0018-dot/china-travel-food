#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""curate_gate.py — 标签驱动的「分级准入 + 徽章」唯一决策门（dev）。

为什么这样设计（校准结论）：
  现网 taste 聚合分与专家人工分层【不相关】（一般档中位77.6 ≥ 值得75.7/必吃77.3），
  原因是评论量少时菜系先验主导、压缩区分度。故采用两层决策：

  ① 专家层（权威种子，diner_seed_labels，labeler=expert）：
     must_eat→必吃、worth_eating→值得（入选）；average→移出。
     专家亲口体验高于推断类标签；但 status=closed 的客观状态仍对所有店生效。
  ② 证据层（无专家标签，临时档）：
     G1 复热/预制高 → 移出；
     强榜单背书 score_endorsement≥T_AWARD（米其林/黑珍珠/必吃榜）→ 精选；
     或强口味证据 score_taste≥T_TASTE 且独立食客 nind≥NIND → 精选（临时）；
     其余 → 不入选。
  徽章语义：必吃/值得＝专家认证；精选＝权威榜单/强证据（待专家复核）。

只 PATCH：is_curated / curate_badge / curate_reason（不碰触发器拥有的分数）。
用法：python3 curate_gate.py [--apply]
"""
import argparse
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core

DATA = pathlib.Path("/app/data")
LEDGER = DATA / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)

# 证据层阈值（0–100）
T_AWARD = 80.0    # 强榜单背书
T_TASTE = 78.0     # 无专家标签时的高口味线
NIND_TASTE = 4     # 且需 ≥4 独立食客
REHEAT = {"中央厨房·门店复热", "预制料理包·复热", "外购成品·无堂食厨房"}

EXPERT_BADGE = {"must_eat": "必吃", "worth_eating": "值得"}


def effective_diner_authors(revs):
    per = collections.defaultdict(set)
    for r in revs:
        if r.get("review_kind") != "diner":
            continue
        if r.get("is_fake_suspect") or r.get("is_hidden"):
            continue
        if r.get("trust_level") not in ("mid", "high"):
            continue
        if all(r.get(k) is None for k in ("aspect_taste", "rating_taste", "rating_total")):
            continue
        a = (r.get("author_name") or "").strip()
        if a:
            per[r["restaurant_id"]].add(a)
    return per


def latest_expert(labels):
    """rid -> 最新专家 tier（按 created_at 字符串排序）。"""
    best = {}
    for l in labels:
        rid = l["restaurant_id"]
        ca = l.get("created_at") or ""
        if rid not in best or ca > best[rid][1]:
            best[rid] = (l["tier"], ca)
    return {rid: v[0] for rid, v in best.items()}


def decide(r, nind, expert_tier):
    # G0 对所有店生效
    if r.get("status") != "active":
        return False, None, "G0 已关店"

    # ① 专家层
    if expert_tier is not None:
        if expert_tier in EXPERT_BADGE:
            badge = EXPERT_BADGE[expert_tier]
            reason = f"专家认证{badge}（独立食客{nind}、证据{r.get('score_evidence_level')}）"
            return True, badge, reason
        return False, None, "专家评为一般，移出精选"

    # ② 证据层
    if r.get("production_model") in REHEAT or r.get("premade_risk") == "高":
        return False, None, f"G1 出餐硬负面（{r.get('production_model') or r.get('premade_risk')}）"
    end = r.get("score_endorsement")
    taste = r.get("score_taste")
    if end is not None and end >= T_AWARD:
        return True, "精选", f"权威榜单背书{end}（口味待专家复核）"
    if taste is not None and taste >= T_TASTE and nind >= NIND_TASTE:
        return True, "精选", f"强口味证据{taste}、独立食客{nind}（待专家复核）"
    if r.get("soft_ad_flag") == "confirmed" and nind < 2:
        return False, None, "确认软广且无≥2独立食客真声"
    return False, None, "无专家标签且证据未达精选线，暂不入选"


def build():
    rs = core.fetch_all(
        "restaurants",
        "id,name,status,is_curated,curate_badge,curate_reason,chain_type,"
        "production_model,premade_risk,score_taste,score_endorsement,"
        "score_evidence_level,soft_ad_flag", order_col="id")
    revs = core.fetch_all(
        "reviews",
        "restaurant_id,author_name,review_kind,is_fake_suspect,is_hidden,"
        "trust_level,aspect_taste,rating_taste,rating_total", order_col="id")
    labels = core.fetch_all("diner_seed_labels",
                           "restaurant_id,tier,created_at,labeler", order_col="id")
    labels = [l for l in labels if l.get("labeler") == "expert"]
    expert = latest_expert(labels)
    authors = effective_diner_authors(revs)

    patches, audit = {}, []
    for r in rs:
        rid = r["id"]
        nind = len(authors.get(rid, set()))
        et = expert.get(rid)
        ok, badge, reason = decide(r, nind, et)
        cur_ok = bool(r.get("is_curated"))
        cur_badge = r.get("curate_badge")
        patch = {}
        if cur_ok != ok:
            patch["is_curated"] = ok
        want_badge = badge if ok else None
        if cur_badge != want_badge:
            patch["curate_badge"] = want_badge
        if ok and r.get("curate_reason") != reason:
            patch["curate_reason"] = reason
        if not ok and cur_ok and r.get("curate_reason") != reason:
            patch["curate_reason"] = reason
        if patch:
            patches[rid] = patch
        audit.append({"rid": rid, "name": r["name"], "nind": nind,
                      "expert": et, "decision": ok, "badge": want_badge,
                      "changed": bool(patch), "reason": reason})
    return rs, patches, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    rs, patches, audit = build()

    badge_dist = collections.Counter(x["badge"] for x in audit if x["decision"])
    turned_on = [x for x in audit if x["changed"] and x["decision"]]
    turned_off = [x for x in audit if x["changed"] and not x["decision"]]
    report = {
        "apply": a.apply, "total": len(rs),
        "curated_after": sum(1 for x in audit if x["decision"]),
        "badge_after": dict(badge_dist),
        "stores_to_patch": len(patches),
        "turned_on": len(turned_on), "turned_off": len(turned_off),
        "elapsed_s": round(time.time() - t0, 1),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    print("\n=== 移出精选（前25）===")
    for x in turned_off[:25]:
        print(f"  id{x['rid']:<6} {x['name'][:26]:<28} {('专家:'+str(x['expert'])) if x['expert'] else ''} | {x['reason']}")
    print("\n=== 新入选精选（前20）===")
    for x in turned_on[:20]:
        print(f"  id{x['rid']:<6} {x['name'][:26]:<28} {x['badge']} | {x['reason']}")

    if not a.apply:
        print("\n[dry-run] 未写库。加 --apply PATCH 决策字段。")
        return

    ts = time.strftime("%Y-%m-%dT%H-%M")
    decpath = LEDGER / f"curate_gate_{ts}.jsonl"
    n_ok = n_err = 0
    with decpath.open("w", encoding="utf-8") as fh:
        for rid, patch in patches.items():
            resp = core.req("PATCH", f"/restaurants?id=eq.{rid}", json=patch)
            okhttp = resp.status_code in (200, 204)
            n_ok += okhttp
            n_err += (not okhttp)
            fh.write(json.dumps({"rid": rid, "patch": patch, "http": resp.status_code},
                                ensure_ascii=False) + "\n")
    core.notify.info("curate_gate 已写库：" + json.dumps(report, ensure_ascii=False),
                     key="curate_gate")
    print(f"\n[apply] PATCH {n_ok} 店，错误 {n_err}；账本 {decpath}")


if __name__ == "__main__":
    main()

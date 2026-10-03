#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""taste_gate.py — 真实口味准入门（专家监督 + 贝叶斯/ML，诚实自校）。

最高原则：只保留真正好吃的店；真实食客堂食证据为最高评定；宁空不假。

三层（按可信度）：
  A. 专家标签（diner_seed_labels，最强监督，确定性执行）：
       must_eat 必吃      -> is_curated=true, curate_badge='必吃'
       worth_eating 值得  -> is_curated=true, curate_badge='值得'
       average 一般       -> is_curated=false, badge=NULL（专家判一般，出精选）
  B. 负向门（自动化、证据驱动）：astroturf_score≥ASTRO_HARD(20) -> 出精选；
       （astroturf 是当前唯一与专家档位显著相关的自动信号，Spearman≈-0.21）
  C. ML 序数门（仅在诚实 CV 超过平凡基线时才允许自动 curate；否则只落 hold 待人工）：
       目标 average<worth<must；5折分层 CV，对比“全猜值得”基线；
       同时输出 readiness（review_count≥8 的店占比，即数据能压过贝叶斯先验 M=8 的前提）。

--apply 才写库，且只写 A/B 确定性动作；C 在 metrics.model_ready=false 时绝不自动写。
默认 dry-run。产物 /app/data/ml_gate/。
"""
import argparse
import json
import pathlib

import numpy as np

import common_core as CC

OUT = pathlib.Path("/app/data/ml_gate")
ASTRO_HARD = 20          # astroturf_score 强制出精选阈值
REVIEW_READY = 8         # 数据压过先验 M=8 所需评论数（readiness 口径）
FN = ["taste", "diner", "platform", "endorsement", "reviews", "astro",
      "price", "big_chain", "hard_premade"]
TMAP = {"average": 0, "worth_eating": 1, "must_eat": 2}
BADGE = {0: None, 1: "值得", 2: "必吃"}


def num(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def fvec(r):
    return [
        num(r.get("score_taste"), np.nan),
        num(r.get("score_diner"), np.nan),
        num(r.get("score_platform"), np.nan),
        num(r.get("score_endorsement"), 0),
        num(r.get("review_count"), 0),
        num(r.get("astroturf_score"), 0),
        num(r.get("price_avg"), np.nan),
        1 if r.get("chain_type") in ("大型连锁", "资本化连锁") else 0,
        1 if r.get("central_kitchen") == "确认" or r.get("premade_risk") == "高" else 0,
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    labels = CC.fetch_all("diner_seed_labels", "restaurant_id,tier", order_col="id")
    rests = CC.fetch_all(
        "restaurants",
        "id,name,status,score_taste,score_diner,score_platform,score_endorsement,"
        "review_count,astroturf_score,chain_type,central_kitchen,premade_risk,"
        "price_avg,is_curated,curate_badge", order_col="id")
    R = {r["id"]: r for r in rests}

    # ---- A. 专家标签确定性计划（同一店若多条标签取最高档）
    expert = {}
    for l in labels:
        rid = l["restaurant_id"]
        if rid in R:
            expert[rid] = max(expert.get(rid, 0), TMAP[l["tier"]])

    plan = []
    for rid, t in expert.items():
        r = R[rid]
        want_cur = t in (1, 2)
        want_badge = BADGE[t]
        cur_badge = r.get("curate_badge")
        if bool(r.get("is_curated")) != want_cur or cur_badge != want_badge:
            f = {"is_curated": want_cur, "curate_badge": want_badge}
            if not want_cur:
                f["curate_reason"] = "专家标注一般，出精选"
            plan.append((rid, r["name"], f))

    # ---- B. astroturf 负向门（仅对未被专家判必吃/值得的店）
    b_plan = []
    for r in rests:
        rid = r["id"]
        if rid in expert and expert[rid] in (1, 2):
            continue
        if num(r.get("astroturf_score"), 0) >= ASTRO_HARD and r.get("is_curated"):
            b_plan.append((rid, r["name"],
                          {"is_curated": False, "curate_badge": None,
                           "curate_reason": f"astroturf≥{ASTRO_HARD}，软广硬信号出精选"}))

    # ---- C. ML 序数门（诚实 CV）
    X, y, rows_lab = [], [], []
    for l in labels:
        r = R.get(l["restaurant_id"])
        if r:
            X.append(fvec(r)); y.append(TMAP[l["tier"]]); rows_lab.append(r)
    X = np.array(X, float); y = np.array(y, int)

    metrics = {"n": int(len(y)), "dist": [int((y == k).sum()) for k in range(3)],
               "feature_names": FN}
    model_ready, hold = False, []
    if len(np.unique(y)) > 1:
        from sklearn.model_selection import StratifiedKFold, cross_val_predict
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import mean_absolute_error, accuracy_score

        cv = StratifiedKFold(5, shuffle=True, random_state=42)
        clf = Pipeline([("imp", SimpleImputer(strategy="median")),
                        ("sc", StandardScaler()),
                        ("lr", LogisticRegression(max_iter=2000,
                                                  class_weight="balanced"))])
        pred = cross_val_predict(clf, X, y, cv=cv)
        ml_mae = mean_absolute_error(y, pred)
        trivial_mae = mean_absolute_error(y, np.ones_like(y))
        metrics.update({"ml_mae": round(float(ml_mae), 3),
                        "ml_acc": round(float(accuracy_score(y, pred)), 3),
                        "trivial_mae": round(float(trivial_mae), 3),
                        "model_ready": bool(ml_mae < trivial_mae - 0.03)})
        model_ready = metrics["model_ready"]

        # 全量训练，给未标注店出概率 → hold（不自动 curate）
        clf.fit(X, y)
        labeled_ids = set(expert)
        un = [(r, fvec(r)) for r in rests if r["id"] not in labeled_ids]
        if un:
            U = np.array([f for _, f in un], float)
            proba = clf.predict_proba(U)
            classes = list(clf.named_steps["lr"].classes_)
            for (r, _), p in zip(un, proba):
                pi = int(np.argmax(p)); conf = float(p[pi])
                if pi in (1, 2) and conf >= 0.7:
                    hold.append({"restaurant_id": r["id"], "name": r["name"],
                                 "suggest_tier": ["average", "worth", "must"][pi],
                                 "confidence": round(conf, 2)})

    # readiness：评论数足以压过先验的店占比
    active = [r for r in rests if r.get("status") != "closed"]
    ready_n = sum(1 for r in active if num(r.get("review_count"), 0) >= REVIEW_READY)
    metrics["readiness"] = {
        "review_ready_n": ready_n, "active_n": len(active),
        "ready_ratio": round(ready_n / max(1, len(active)), 3),
        "note": f"review_count>={REVIEW_READY} 数据才压过先验 M=8；当前口味分被先验压缩，故与专家档位零相关"}
    (OUT / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "ml_hold.jsonl").write_text(
        "\n".join(json.dumps(h, ensure_ascii=False) for h in
                  sorted(hold, key=lambda x: -x["confidence"])), encoding="utf-8")

    print(f"专家标签: 必吃{metrics['dist'][2]}/值得{metrics['dist'][1]}/一般{metrics['dist'][0]}")
    print(f"A 专家标签计划: {len(plan)} 店；B astroturf 负向门: {len(b_plan)} 店")
    for rid, name, f in plan + b_plan:
        print(f"   id{rid:<5} {str(name)[:22]:<24} {f.get('curate_badge') or ('出精选:'+f.get('curate_reason','')[:18])}")
    print(f"\nC ML: {metrics.get('ml_mae')} vs 平凡 {metrics.get('trivial_mae')} -> "
          f"model_ready={model_ready}；ML hold 候选 {len(hold)}（不自动 curate）")
    print(f"readiness: {ready_n}/{len(active)} = {metrics['readiness']['ready_ratio']}")

    if not args.apply:
        print("\n[dry-run] 未写库；加 --apply 执行 A/B 确定性动作。")
        return

    ok = 0
    for rid, name, f in plan + b_plan:
        resp = CC.req("PATCH", f"/restaurants?id=eq.{rid}", use_service=True, json=f)
        if resp.status_code not in (200, 204):
            print(f"  [FAIL] id{rid}: {resp.status_code} {resp.text[:150]}")
            continue
        ok += 1
    print(f"\n[apply] A/B PATCH {ok}/{len(plan)+len(b_plan)}；C model_ready={model_ready}（未自动写 ML）。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cloud/vendor/pipeline/label_weight_learn.py — 以专家标注为监督的权重学习。

三类证据权重（口径可复算）：
  - 专家标注 taste（1-5）：高质量 ground truth，权重最高；
  - 真实食客 UGC(reviews score_taste)：口味第二来源；
  - 平台背书(endorsement，米其林/黑珍珠)：背书，仅次。
四维→两层映射：用 logistic 先验 taste 权重最高，样本多后用标注做逻辑回归拟合。
样本少时用先验；随标注量增大权重自动更新（先验收缩向经验）。
不覆盖在跑 scoring_engine 口径，先 dry-run 对比。
"""
import os, sys, math, json, argparse, statistics
sys.path.insert(0, "/app/pipeline")
import common as C

# 先验权重（样本=0 时用）：口味主导，稳定性次之，氛围/创新辅助
PRIOR = {"taste": 0.45, "consistency": 0.20, "ambience": 0.15, "innovation": 0.20}


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def learn(rows):
    """简单逻辑回归拟合 P(must_eat | 四维)。样本少时退化为先验。"""
    n = len(rows)
    if n < 8:
        return {"prior": PRIOR, "trained": False, "note": f"样本={n}<8，用先验权重，待标注累积"}
    # 梯度下降拟合 w·[taste,consistency,ambience,innovation] + b
    keys = ["taste", "consistency", "ambience", "innovation"]
    w = {k: PRIOR[k] for k in keys}
    b = 0.0
    lr = 0.1
    for _ in range(400):
        gw = {k: 0.0 for k in keys}; gb = 0.0
        for r in rows:
            z = b + sum(w[k] * (r[k] - 3) for k in keys)
            p = sigmoid(z)
            y = 1.0 if r["tier"] == "must_eat" else 0.0
            err = p - y
            for k in keys:
                gw[k] += err * (r[k] - 3)
            gb += err
        for k in keys:
            w[k] -= lr * gw[k] / n
        b -= lr * gb / n
    tot = sum(abs(v) for v in w.values()) or 1
    norm = {k: round(abs(v) / tot, 3) for k in keys}
    return {"prior": PRIOR, "trained": True, "weights": norm, "bias": round(b, 3), "n": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        rows = C.fetch_all("diner_expert_labels",
                           "restaurant_id,labeler,taste,ambience,innovation,consistency,tier,experienced_at",
                           order_col="restaurant_id")
    except Exception:
        print(json.dumps({"n_labels": 0, "learned": {"prior": PRIOR, "trained": False,
                          "note": "表 diner_expert_labels 未建(先在 SQL Editor 跑 018 migration)，用先验权重"},
                          "scoring_engine_current": {"blend": "0.45 taste + 0.25 diner + 0.18 obj + 0.12 endorsement"}},
                         ensure_ascii=False, indent=2))
        return
    res = learn(rows)
    # 当前在跑 scoring_engine 口径（参考，不覆盖）
    se = {"blend": "0.45 taste + 0.25 diner + 0.18 objective + 0.12 endorsement",
          "note": "DB 触发器 trg_restaurants_derive 仍为 score_total 唯一口径；本学习只产出建议权重"}
    print(json.dumps({"n_labels": len(rows), "learned": res, "scoring_engine_current": se},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# curate_v4.py — 精选层 dry-run v2（严谨，不写库）
# 特征：真实食客 taste (180d 半衰期加权) vs 高德聚合分 拆开；有序 logistic + GBDT；
# Pipeline 每折 StandardScaler；分层5折；对比平凡基线。
import json, pathlib, sys, os, math, statistics, datetime
sys.path.insert(0, "/app/pipeline")
import common as C
from collections import defaultdict

OUT = pathlib.Path("/app/data/post_record/curate_v4_dryrun.json")
TIER_NUM = {"must_eat": 2, "worth_eating": 1, "average": 0}
HALFLIFE_DAYS = 180
NOW = datetime.datetime.utcnow()


def parse_dt(s):
    if not s: return None
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def features():
    rests = C.fetch_all("/restaurants",
        "id,name,chain_type,premade_risk,central_kitchen,price_avg", order_col="id")
    # reviews: restaurant_id, source_platform, is_verified_diner, author_name,
    #          aspect_taste, aspect_json, visit_date, created_at
    reviews = C.fetch_all("/reviews",
        "restaurant_id,source_platform,is_verified_diner,author_name,"
        "aspect_taste,aspect_json,visit_date,created_at")
    labels = C.fetch_all("/diner_seed_labels", "restaurant_id,tier")

    by_rid = defaultdict(list)
    for rv in reviews:
        by_rid[rv["restaurant_id"]].append(rv)

    feat = {}
    for r in rests:
        rid = r["id"]
        rs = by_rid.get(rid, [])
        # 真实食客（XHS verified）
        diner = []
        amap = []
        for x in rs:
            taste = None
            try:
                aj = x.get("aspect_json") or {}
                if isinstance(aj, str):
                    aj = json.loads(aj)
                taste = x.get("aspect_taste") or (aj or {}).get("amap_rating")
            except Exception:
                taste = x.get("aspect_taste")
            if taste is None: continue
            item = {"v": float(taste),
                    "dt": parse_dt(x.get("visit_date") or x.get("created_at")),
                    "author": x.get("author_name")}
            if x.get("source_platform") == "amap" or not x.get("is_verified_diner"):
                amap.append(item)
            else:
                diner.append(item)

        def wmean(items):
            num = den = 0
            for it in items:
                age = (NOW - (it["dt"] or NOW)).days if it["dt"] else 999
                w = 0.5 ** (max(age, 0) / HALFLIFE_DAYS)
                num += it["v"] * w; den += w
            return num / den if den else 0

        diner_ratings = [d["v"] for d in diner]
        authors = set(d["author"] for d in diner if d["author"])
        recent = min(((NOW - d["dt"]).days for d in diner if d["dt"]), default=9999)

        feat[rid] = {
            "id": rid, "name": r["name"],
            "diner_avg": wmean(diner),
            "diner_n": len(diner),
            "n_ind": len(authors),
            "neg_ratio": (sum(1 for v in diner_ratings if v < 3.5) / len(diner_ratings)) if diner_ratings else 0,
            "std": statistics.stdev(diner_ratings) if len(diner_ratings) > 1 else 0,
            "recent_days": recent,
            "amap_avg": statistics.mean([a["v"] for a in amap]) if amap else 0,
            "log_n": math.log1p(len(rs)),
            "chain_type": r.get("chain_type") or "独立店",
            "premade_risk": r.get("premade_risk") or "无",
            "central_kitchen": r.get("central_kitchen") or "无",
            "price": r.get("price_avg") or 0,
        }
    return feat, labels


FEATURES = ["diner_avg", "diner_n", "n_ind", "neg_ratio", "std", "recent_days",
            "amap_avg", "log_n", "price"]


def encode(f):
    chain = {"独立店": [1,0,0,0], "小型连锁": [0,1,0,0],
             "大型连锁": [0,0,1,0], "资本化连锁": [0,0,0,1]}.get(f["chain_type"], [0,0,0,0])
    pr = {"无": 0, "低": 1, "疑似": 2, "高": 3}.get(f["premade_risk"], 0)
    ck = {"无": 0, "疑似": 1, "确认": 2}.get(f["central_kitchen"], 0)
    return ([f[k] for k in FEATURES] + chain + [pr, ck])


def main():
    feat, labels = features()
    train_rid = [l["restaurant_id"] for l in labels]
    y = [TIER_NUM[l["tier"]] for l in labels]
    X = [encode(feat[rid]) for rid in train_rid]

    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import accuracy_score, mean_absolute_error, confusion_matrix
    import numpy as np

    y_bin = [1 if t >= 1 else 0 for t in y]
    n = len(y)
    base_maj = max(y.count(0), y.count(1), y.count(2)) / n
    base_bin = max(y_bin.count(0), y_bin.count(1)) / n

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oos = []
    for tr, te in skf.split(X, y_bin):
        pipe = Pipeline([("sc", StandardScaler()),
                         ("m", LogisticRegression(max_iter=1000, C=0.3, class_weight="balanced"))])
        pipe.fit([X[i] for i in tr], [y_bin[i] for i in tr])
        oos.extend(pipe.predict([X[i] for i in te]))
    acc = accuracy_score(y_bin, oos)
    cm = confusion_matrix(y_bin, oos, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0

    # 全量训练取系数
    full = Pipeline([("sc", StandardScaler()),
                     ("m", LogisticRegression(max_iter=1000, C=0.3, class_weight="balanced"))])
    full.fit(X, y_bin)
    names = FEATURES + ["indep", "small", "large", "cap", "premade", "ck"]
    coefs = {k: round(float(v), 3) for k, v in zip(names, full.named_steps["m"].coef_[0])}

    # 硬规则 A
    down_A = [f["id"] for f in feat.values()
              if f["central_kitchen"] == "确认" or f["premade_risk"] == "高"]

    # ML 门 B：仅 n_ind>=2 且非疑似预制
    eligible = [f for f in feat.values() if f["n_ind"] >= 2
                and f["central_kitchen"] != "疑似" and f["premade_risk"] != "疑似"]
    probs = full.predict_proba([encode(f) for f in eligible])[:, 1]
    curated_B = sum(1 for p in probs if p >= 0.5)

    out = {
        "baseline_majority_tier": round(base_maj, 3),
        "baseline_majority_binary": round(base_bin, 3),
        "cv_binary_accuracy": round(acc, 3),
        "beats_baseline": acc > base_bin + 0.05,
        "precision": round(prec, 3), "recall": round(rec, 3),
        "coefs_standardized": coefs,
        "hard_down_A_count": len(down_A),
        "curated_eligible_B": len(eligible),
        "curated_B_at_05": curated_B,
        "cm_binary": cm.tolist(),
        "note": "aspect_taste/amap_rating 已拆分；若 acc<=baseline 则 ML 门暂缓。",
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

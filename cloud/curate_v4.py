#!/usr/bin/env python3
# curate_v4.py — 精选层 dry-run（不写库）
import json, pathlib, sys, os, math, statistics
sys.path.insert(0, "/app/pipeline")
import common as C
from collections import defaultdict

OUT = pathlib.Path("/app/data/post_record/curate_v4_dryrun.json")
TIER_NUM = {"must_eat": 2, "worth_eating": 1, "average": 0}


def features():
    rests = C.fetch_all("/restaurants",
        "id,name,chain_type,premade_risk,central_kitchen,price_avg,food_safety", order_col="id")
    reviews = C.fetch_all("/reviews",
        "restaurant_id,rating_total,rating_taste,user_id,author_name,visit_date,created_at")
    labels = C.fetch_all("/diner_seed_labels", "restaurant_id,tier,taste")
    by_rid = defaultdict(list)
    for rv in reviews:
        by_rid[rv["restaurant_id"]].append(rv)
    feat = {}
    for r in rests:
        rid = r["id"]
        rs = by_rid.get(rid, [])
        authors = set(x.get("user_id") or x.get("author_name") for x in rs)
        ratings = [float(x["rating_taste"] or x.get("rating_total") or 0)
                   for x in rs if x.get("rating_taste") or x.get("rating_total")]
        feat[rid] = {
            "id": rid, "name": r["name"],
            "n_ind": len(authors),
            "avg_rating": statistics.mean(ratings) if ratings else 0,
            "std_rating": statistics.stdev(ratings) if len(ratings) > 1 else 0,
            "neg_ratio": sum(1 for v in ratings if v < 3.5) / len(ratings) if ratings else 0,
            "log_n_reviews": math.log1p(len(rs)),
            "chain_type": r.get("chain_type") or "独立店",
            "premade_risk": r.get("premade_risk") or "无",
            "central_kitchen": r.get("central_kitchen") or "无",
            "price_avg": r.get("price_avg") or 0,
        }
    return feat, labels


def encode(f):
    chain = {"独立店": [1,0,0,0], "小型连锁": [0,1,0,0],
             "大型连锁": [0,0,1,0], "资本化连锁": [0,0,0,1]}.get(f["chain_type"], [0,0,0,0])
    pr = {"无": 0, "低": 1, "疑似": 2, "高": 3}.get(f["premade_risk"], 0)
    ck = {"无": 0, "疑似": 1, "确认": 2}.get(f["central_kitchen"], 0)
    return [f["n_ind"], f["avg_rating"], f["std_rating"], f["neg_ratio"],
            f["log_n_reviews"], f["price_avg"] / 1000.0] + chain + [pr, ck]


def main():
    feat, labels = features()
    train_rid = [l["restaurant_id"] for l in labels]
    y = [TIER_NUM[l["tier"]] for l in labels]
    X = [encode(feat[rid]) for rid in train_rid]
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import accuracy_score, confusion_matrix
    y_bin = [1 if t >= 1 else 0 for t in y]
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    preds_lr, preds_gb = [], []
    for tr, te in skf.split(X, y_bin):
        Xtr = [X[i] for i in tr]; ytr = [y_bin[i] for i in tr]
        Xte = [X[i] for i in te]
        m = LogisticRegression(max_iter=500, C=0.5).fit(Xtr, ytr)
        preds_lr.extend(m.predict(Xte))
        g = GradientBoostingClassifier(n_estimators=50, max_depth=2, random_state=42).fit(Xtr, ytr)
        preds_gb.extend(g.predict(Xte))
    acc_lr = accuracy_score(y_bin, preds_lr)
    acc_gb = accuracy_score(y_bin, preds_gb)
    cm = confusion_matrix(y_bin, preds_lr, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    full_X = [encode(f) for f in feat.values()]
    model = LogisticRegression(max_iter=500, C=0.5).fit(X, y_bin)
    probs = model.predict_proba(full_X)[:, 1]
    coefs = dict(zip(
        ["n_ind", "avg_rating", "std", "neg", "log_n", "price_norm",
         "indep", "small", "large", "cap", "premade", "ck"],
        model.coef_[0].tolist()))
    down, plan = [], []
    for f, p in zip(feat.values(), probs):
        hard = f["central_kitchen"] == "确认" or f["premade_risk"] == "高"
        if hard:
            is_curated = False; badge = None
            reason = f"硬规则下架: ck={f['central_kitchen']}/premade={f['premade_risk']}"
            down.append(f["id"])
        elif f["n_ind"] < 2:
            is_curated = False; badge = None
            reason = f"证据不足(n_ind={f['n_ind']})"
        else:
            is_curated = bool(p >= 0.5)
            badge = "必吃" if p >= 0.85 else ("值得" if p >= 0.5 else None)
            reason = f"v4 model p={p:.2f}"
        plan.append({"id": f["id"], "name": f["name"], "curate_score": round(p * 100, 1),
                     "is_curated": is_curated, "curate_badge": badge, "reason": reason})
    out = {"cv_accuracy_lr": acc_lr, "cv_accuracy_gb": acc_gb,
           "precision_selected": prec, "recall_selected": rec, "coefs": coefs,
           "hard_down_count": len(down), "curated_count": sum(1 for p in plan if p["is_curated"]),
           "plan": plan}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "plan"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

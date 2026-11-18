"""Food-project scoring calculation over supplied rows, without database access.

Inputs retain the existing restaurant/review/cuisine schemas. The caller supplies
its reference date, decay half-life and prior strength. Returns (predictions,
effective_review_count). Business formulas remain food-project policy, not a
general-purpose scoring library or a claim of SQL parity validation.
"""
import collections
import datetime


def taste_val(r):
    for k in ("aspect_taste", "rating_taste", "rating_total"):
        if r.get(k) is not None:
            return float(r[k])
    return None


def compute(revs, rs, rc, cu, *, reference_date, half_life, prior_strength):
    REF_DATE, HALF_LIFE, M = reference_date, half_life, prior_strength
    cu_by_id = {c["id"]: c for c in cu}
    cui_by_name = {c["name"]: c for c in cu if c["dimension"] == "菜系"}

    eff = []
    for r in revs:
        if r["review_kind"] != "diner":
            continue
        if r["is_fake_suspect"] or r["is_hidden"]:
            continue
        if r["trust_level"] not in ("mid", "high"):  # 红线：trust low 不作口味证据
            continue
        v = taste_val(r)
        if v is None:
            continue
        dt = r.get("visit_date") or (r.get("created_at") or "")[:10]
        try:
            d = datetime.date.fromisoformat(dt)
        except Exception:
            d = REF_DATE
        w = 0.5 ** ((REF_DATE - d).days / HALF_LIFE)
        eff.append({"rid": r["restaurant_id"], "author": r.get("author_name") or "",
                    "w": w, "q": (v - 1) / 4.0 * 100.0})

    per = collections.defaultdict(list)
    for e in eff:
        per[e["rid"]].append(e)

    res_cui = collections.defaultdict(list)
    for link in rc:
        c = cu_by_id.get(link["cuisine_id"])
        if c and c["dimension"] == "菜系":
            res_cui[link["restaurant_id"]].append((link["cuisine_id"],
                                                   bool(link.get("is_primary"))))

    tag_sum = collections.defaultdict(lambda: [0.0, 0.0])   # cuisine_id -> [Σwq, Σw]
    parent_sum = collections.defaultdict(lambda: [0.0, 0.0])  # parent_category lvl -> [Σwq, Σw]
    for e in eff:
        for (cid, _prim) in res_cui.get(e["rid"], []):
            tag_sum[cid][0] += e["w"] * e["q"]
            tag_sum[cid][1] += e["w"]
    for c in cu:
        if c["dimension"] == "菜系" and c["parent_category"]:
            t = tag_sum.get(c["id"])
            if t:
                parent_sum[c["parent_category"]][0] += t[0]
                parent_sum[c["parent_category"]][1] += t[1]

    def cuisine_prior(rid):
        tags = res_cui.get(rid)
        if not tags:
            return 70.0
        leaf = sorted(tags, key=lambda x: (not x[1], x[0]))[0][0]
        levels = []
        depth = 1
        cid, lvl, par = leaf, cu_by_id[leaf]["name"], cu_by_id[leaf]["parent_category"]
        while True:
            levels.append((cid, lvl, depth))
            if par is None:
                break
            prow = cui_by_name.get(par)
            npar = prow["parent_category"] if prow else None
            cid, lvl, par, depth = None, par, npar, depth + 1
        scored = []
        for (cid, lvl, depth) in levels:
            wq, w = (tag_sum.get(cid, [0.0, 0.0]) if cid is not None
                     else parent_sum.get(lvl, [0.0, 0.0]))
            scored.append((depth, (wq / w) if w > 0 else 70.0, w))
        # 先取 Σw>=20 的最浅层；否则最浅层
        scored.sort(key=lambda x: (1 if x[2] >= 20 else 0, -x[0]), reverse=True)
        return scored[0][1]

    clamp = lambda x: max(0.0, min(100.0, x))  # noqa: E731
    pred = {}
    for r in rs:
        rid = r["id"]
        ev = per.get(rid, [])
        sw = sum(e["w"] for e in ev)
        swq = sum(e["w"] * e["q"] for e in ev)
        nind = len(set(e["author"] for e in ev))
        if sw > 0:
            v_R = swq / sw
            v_C = cuisine_prior(rid)
            taste = round(sw / (sw + M) * v_R + M / (sw + M) * v_C, 2)
            diner = round(v_R, 2)
            conf = round(sw / (sw + M), 3)
            cnt = len(ev)
        else:
            taste = diner = None
            conf, cnt = 0, 0
        obj, end, pen = r["score_objective"], r["score_endorsement"], r["soft_ad_penalty"] or 0
        # 以下为 DB 触发器 derive_restaurant 的 blend 复算（仅用于 dry-run 预测与校验，不写库）
        if taste is not None and diner is not None:
            blend = (0.45 * taste + 0.25 * diner
                     + 0.18 * (obj if obj is not None else taste)
                     + 0.12 * (end if end is not None else 0))
            if nind >= 2:
                evl, tot = "verified", round(clamp(blend - pen), 1)
            else:
                evl, tot = "provisional", round(clamp(min(blend, 82) - pen), 1)
        elif (obj and obj > 0) or (end and end > 0):
            blend = 0.6 * (obj or 0) + 0.4 * (end or 0)
            evl, tot = "provisional", round(clamp(min(blend, 70) - pen), 1)
        else:
            evl, tot = "insufficient", None
        pred[rid] = {"taste": taste, "diner": diner, "count": cnt, "conf": conf,
                     "nind": nind, "evidence": evl, "total": tot}
    return pred, len(eff)

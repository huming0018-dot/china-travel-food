#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage4_audit.py — 全库只读质量门（可周期性运行，是数据保鲜/updating 机制的引擎）

用法：
  python3 stage4_audit.py                 # 拉生产库全量，打印 Markdown 报告
  python3 stage4_audit.py -o audit.md     # 同时落盘
退出码：发现 error（硬伤）=1；仅 warn/info =0。

检查：完整性/电话真假/分类悬挂游离/FineDining越档/重复/坐标覆盖/关店态与保鲜/认证标签覆盖/证据评分一致性。
"""
import argparse
import collections
import datetime
import sys

import common as C

SPECIAL = {159: "米其林星级", 160: "黑珍珠餐厅", 45: "素食/纯素", 46: "分子/先锋料理",
           165: "可预订", 166: "团购优惠", 167: "包间"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    rests = C.fetch_all("restaurants", order_col="id")
    cuis = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    cmap = {c["id"]: c for c in cuis}
    rmap = {r["id"]: r for r in rests}
    tags_by_rest = collections.defaultdict(set)
    for x in rc:
        tags_by_rest[x["restaurant_id"]].add(x["cuisine_id"])

    E, W, I = [], [], []  # error / warn / info
    def err(t): E.append(t)
    def warn(t): W.append(t)
    def info(t): I.append(t)

    # ---------- 悬挂 / 游离关联 ----------
    dangling = sorted({x["restaurant_id"] for x in rc if x["restaurant_id"] not in rmap})
    orphan_tags = sorted({x["cuisine_id"] for x in rc if x["cuisine_id"] not in cmap})
    if dangling:
        err(f"悬挂 RC（restaurant 不存在）{len(dangling)} 家: {dangling[:20]}")
    if orphan_tags:
        err(f"游离标签关联（cuisine_id 不在字典）{len(orphan_tags)} 个: {orphan_tags[:20]}")

    # ---------- 同名标签跨维度/重复（会导致筛选与统计分叉）----------
    name_rows = collections.defaultdict(list)
    for c in cuis:
        nm = str(c.get("name") or "").strip()
        if nm:
            name_rows[nm].append((c["id"], c.get("dimension"), c.get("parent_category")))
    for nm, rows in name_rows.items():
        dims = {d for _, d, _ in rows}
        # 仅跨 dimension 的同名才是真重复（会致筛选分叉）；同维度按风味细分（如面/饭分中式/日式）属合理
        if len(rows) > 1 and len(dims) > 1:
            warn(f"[同名标签跨维度重复] 『{nm}』有 {len(rows)} 个，应迁移 RC 后只保留一个: "
                 + "; ".join(f"id={i}[{d}]parent={p}" for i, d, p in rows))

    # ---------- 逐店检查 ----------
    name_idx, addr_idx = collections.defaultdict(list), collections.defaultdict(list)
    special_cnt = collections.Counter()
    score_mode = collections.Counter()
    score_partial, score_legacy, score_big = [], [], []
    score_recalc = collections.Counter()
    closed, stale = [], []
    today = datetime.date.today()

    for r in rests:
        rid, name = r["id"], r["name"]
        tags = tags_by_rest.get(rid, set())
        st_raw = str(r.get("status") or "").strip()
        norm = C.STATUS_ALIAS.get(st_raw, st_raw)
        for t in tags:
            if t in SPECIAL:
                special_cnt[t] += 1

        # 完整性（与数据库视图 v_audit_gaps 口径对齐：电话空也计入）
        for f in ["address", "phone", "district", "signature_dishes", "data_updated_at"]:
            v = r.get(f)
            empty = v is None or v == "" or v == [] or v == "[]"
            if empty:
                warn(f"[字段空] id={rid} {name} 缺 {f}")
        if not r.get("score_total"):
            warn(f"[无评分] id={rid} {name} 缺 score_total")
        ev = r.get("evidence_summary")
        if not ev or len(str(ev)) < 30:
            warn(f"[证据过短] id={rid} {name} evidence_summary<30字")

        # 电话
        phone = r.get("phone")
        if phone:
            clean, issues, _ = C.clean_phone(phone)
            if issues and not all(i == "phone_missing" for i in issues):
                err(f"[问题电话] id={rid} {name}: {phone!r} -> {issues}")
            elif clean and clean.replace(" / ", "").replace("/", "") != re_sub(phone):
                warn(f"[电话待规范] id={rid} {name}: {phone!r} -> {clean}")

        # tier 一致性
        price = C.to_int(r.get("price_avg"))
        want_tier = C.tier_from_price(price)
        if want_tier and r.get("tier") and r["tier"] != want_tier:
            err(f"[tier越档] id={rid} {name}: price={price} 应为{want_tier}，实挂{r['tier']}")

        # 分类完备性
        dims = collections.defaultdict(list)
        for t in tags:
            c = cmap.get(t)
            if c:
                dims[c["dimension"]].append(c["name"])
        if not dims.get("菜系"):
            warn(f"[缺菜系标签] id={rid} {name}")
        if not dims.get("形式"):
            warn(f"[缺形式标签] id={rid} {name}")
        if not ({162} & tags) and not ({163} & tags):
            warn(f"[缺午/晚餐时段] id={rid} {name}")
        if 71 in tags and (price is None or price < 250):
            err(f"[FineDining越档] id={rid} {name}: 挂71但人均={price}")

        # 评分一致性：百分制子分(现行) vs 旧加权/残缺；问题归类为可执行修复任务，不逐店刷噪音
        try:
            o = float(r.get("score_objective") or 0); d = float(r.get("score_diner") or 0)
            t = float(r.get("score_taste") or 0); e = float(r.get("score_endorsement") or 0)
            pen = float(r.get("soft_ad_penalty") or 0)
            pv = [r.get(k) for k in
                  ("score_objective", "score_diner", "score_taste", "score_endorsement")]
            if max(o, d, t, e) > 100 or min(o, d, t, e, pen) < 0:
                err(f"[评分越界] id={rid} {name}: 子分 o={o} d={d} t={t} e={e} pen={pen}")
            is_pct = o > 40 or d > 30 or t > 20 or e > 10
            incomplete = any(p is None for p in pv) or (o == 0 and d == 0 and t == 0 and e == 0)
            if is_pct and not incomplete:
                score_mode["百分制子分"] += 1
                if any(p is None for p in pv):
                    score_partial.append(f"{name}(id={rid})")
                if r.get("score_total") is not None:
                    tot = float(r["score_total"])
                    # v3 触发器权重（005）：taste0.35/objective0.25/diner0.25/endorsement0.15
                    s = 0.35 * t + 0.25 * o + 0.25 * d + 0.15 * e - pen
                    sn = 0.35 * t + 0.25 * o + 0.25 * d + 0.15 * e
                    if abs(tot - s) > 1.5:
                        if abs(tot - sn) <= 1.5:
                            score_recalc["total未减软广pen"] += 1
                        elif 0 < tot - s <= 6:
                            score_recalc["含小加分(bonus?)"] += 1
                        elif tot - s > 6:
                            score_recalc["total明显偏高"] += 1
                            score_big.append(f"{name}(id={rid}) tot={tot} 应={round(s,1)} pen={pen}")
                        else:
                            score_recalc["total偏低"] += 1
            else:
                score_mode["旧口径/残缺待迁移"] += 1
                score_legacy.append(f"{name}(id={rid})")
        except (TypeError, ValueError):
            pass

        # 坐标
        loc = C.parse_location(r.get("location"))
        if norm != C.STATUS_CLOSED:
            if not loc:
                warn(f"[无坐标] id={rid} {name}")
            elif not C.in_shanghai(*loc):
                err(f"[坐标越界] id={rid} {name}: {loc}")

        # 状态
        if norm not in C.VALID_STATUS:
            warn(f"[status枚举外] id={rid} {name}: {st_raw!r}")
        if norm == C.STATUS_CLOSED:
            closed.append(f"{name}(id={rid})")
        # 保鲜
        d = r.get("data_updated_at")
        if d:
            try:
                dd = datetime.date.fromisoformat(str(d)[:10])
                age = (today - dd).days
                limit = C.FRESH_DAYS_HIGH if want_tier in ("奢华", "高档") else C.FRESH_DAYS_MASS
                if age > limit:
                    stale.append(f"{name}(id={rid},{want_tier},{age}天)")
            except ValueError:
                warn(f"[日期格式] id={rid} {name}: {d}")

        name_idx[C.norm_name(name)].append(r)
        ac = C.addr_core(r.get("address") or "")
        if ac:
            addr_idx[ac].append(r)

    # ---------- 重复 ----------
    for nn, rs in name_idx.items():
        if len(rs) > 1:
            addrs = {C.addr_core(x.get("address") or "") for x in rs}
            if len(addrs) == 1:
                err(f"[同名同址重复] {rs[0]['name']} x{len(rs)} ids={[x['id'] for x in rs]}")
            else:
                info(f"同名异址(连锁分店,保留) {rs[0]['name']} x{len(rs)} ids={[x['id'] for x in rs]}")

    # 评分口径 / total 重算 / 旧数据迁移 —— 归类为可执行修复任务
    if score_legacy:
        warn(f"[评分待迁移] 旧加权口径或分项残缺 {len(score_legacy)} 家，需回填百分制子分后重算 total"
             f"（跑 stage5_recalc.py --report-only 查看）: {'、'.join(score_legacy[:15])}")
    for k, v in score_recalc.items():
        warn(f"[评分与触发器不符] {k} {v} 家：total 现由数据库触发器按 0.4o+0.3d+0.2t+0.1e−pen 计算，"
             f"不符说明触发器缺失/被绕过，跑 stage5_recalc.py 只读排查（stage5 不再写库）")
    for x in score_big[:20]:
        warn(f"[评分偏差大] {x}")
    if score_partial:
        warn(f"[评分分项缺失] {len(score_partial)} 家: {'、'.join(score_partial[:15])}")

    # ---------- 覆盖率 ----------
    n = len(rests)
    def rate(pred):
        return sum(1 for r in rests if pred(r))
    loc_n = rate(lambda r: C.parse_location(r.get("location")))
    phone_n = rate(lambda r: r.get("phone"))
    book_n = rate(lambda r: r.get("booking_method"))
    area_n = rate(lambda r: r.get("business_area"))

    # ---------- 报告 ----------
    L = []
    L.append(f"# 美食图鉴全库质量门审计 · {today}")
    L.append("")
    L.append(f"餐厅 **{n}** / 标签 **{len(cuis)}** / 关联 **{len(rc)}**")
    st_dist = collections.Counter(str(r.get('status')) for r in rests)
    tier_dist = collections.Counter(str(r.get('tier')) for r in rests)
    L.append(f"- status 分布: {dict(st_dist)}")
    L.append(f"- tier 分布: {dict(tier_dist)}")
    L.append("")
    L.append(f"## 覆盖率")
    L.append(f"- 坐标 location: **{loc_n}/{n} = {loc_n/n:.0%}**")
    L.append(f"- 电话: {phone_n/n:.0%}；预订方式: {book_n/n:.0%}；商圈: {area_n/n:.0%}")
    L.append(f"- 评分口径: {dict(score_mode)}")
    if score_recalc:
        L.append(f"- total 待重算分布: {dict(score_recalc)}（确定性修复跑 stage5_recalc.py）")
    L.append("")
    L.append("## 认证 / 特别标签挂店数（偏少提示补标）")
    for cid, nm in SPECIAL.items():
        L.append(f"- {nm}({cid}): **{special_cnt.get(cid,0)}**")
    L.append("")
    L.append(f"## 关店（{len(closed)}）")
    L.append("、".join(closed[:60]) or "无")
    L.append("")
    L.append(f"## 超过保鲜周期需复查（{len(stale)}，高端180天/大众90天）")
    L.append("、".join(stale[:60]) or "无")
    L.append("")
    def bucket(lines):
        c = collections.Counter()
        for x in lines:
            m = re.match(r"\[([^\]]+)\]", x)
            c[m.group(1) if m else "其他"] += 1
        return dict(c)

    import re
    L.append(f"## 🔴 ERROR {len(E)}（分类: {bucket(E)}）")
    L += [f"- {x}" for x in E] or ["- 无"]
    L.append("")
    L.append(f"## 🟡 WARN {len(W)}（分类: {bucket(W)}）")
    L += [f"- {x}" for x in W[:200]]
    if len(W) > 200:
        L.append(f"- …另有 {len(W)-200} 条，分类计数见标题")
    L.append("")
    L.append(f"## ℹ️ INFO {len(I)}")
    L += [f"- {x}" for x in I[:60]]
    report = "\n".join(L)
    print(report)
    if args.output:
        import pathlib
        pathlib.Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n已写入 {args.output}", file=sys.stderr)
    print(f"\n汇总: ERROR={len(E)} WARN={len(W)}", file=sys.stderr)
    sys.exit(1 if E else 0)


def re_sub(s):
    import re
    return re.sub(r"\D", "", str(s))


if __name__ == "__main__":
    main()

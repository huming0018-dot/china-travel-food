#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage1_validate.py — 入库前质量门（确定性，不调用模型）

输入：模型采集的原始证据 JSONL（每行一家店，符合 raw_place.schema.json）
输出：accepted.jsonl（清洗+归一后的可入库记录） / rejected.tsv（被打回及原因）
原则：不合格不入库；电话宁空不假；评分/档位由脚本按规则重算，不信模型手填。

用法：
  python3 stage1_validate.py -i raw.jsonl -o accepted.jsonl
"""
import argparse
import csv
import pathlib
import sys

import common as C

FORMS = {"Finedining", "Casual Dining", "Bistro", "快餐简餐", "Brunch",
         "下午茶", "私宴会所", "自助放题", "酒吧清吧", "夜宵", "快餐", " Casual"}


def validate(rec):
    errs, warns = [], []
    name = (rec.get("name") or "").strip()
    if not name:
        errs.append("name 为空")
        return errs, warns, None

    # ---- 地址 / 行政区 ----
    district = (rec.get("district") or "").strip()
    if district not in C.DISTRICTS and district not in ("多区连锁", "待确认"):
        errs.append(f"district 非标准行政区: {district!r}")
    address = (rec.get("address") or "").strip()
    if len(address) < 6:
        errs.append("address 过短或为空（渠道链补齐，不留空）")

    # ---- 人均 / 档位 ----
    price = C.to_int(rec.get("price_avg"))
    if price is None:
        if not rec.get("price_range"):
            errs.append("price_avg 与 price_range 均缺失")
    elif price <= 0 or price > 20000:
        errs.append(f"price_avg 异常: {price}")
    tier = C.tier_from_price(price)
    form = (rec.get("form") or "").strip()
    if form and form not in FORMS:
        warns.append(f"form 非标准枚举: {form!r}（请对照 runbook）")
    if form == "Finedining" and (price is not None and price < 250):
        errs.append(f"挂 Finedining 但人均 {price}<250")

    # ---- 招牌菜 ----
    dishes = C.dishes_list(rec.get("signature_dishes"))
    if len(dishes) < 2:
        errs.append("signature_dishes 少于 2 道")
    nn = C.norm_name(name)
    for d in dishes:
        if C.norm_name(d) == nn:
            errs.append(f"招牌菜出现店名本身（菜品名≠餐厅）: {d}")

    # ---- 分类路径 ----
    paths = rec.get("cuisine_paths") or []
    if not paths:
        errs.append("cuisine_paths 为空（至少 1 条 叶子+父链）")
    else:
        for p in paths:
            if not isinstance(p, list) or len(p) < 2:
                errs.append(f"cuisine_path 层级不足: {p}")

    # ---- 营业状态 / 关店三要素 ----
    status = rec.get("status")
    if status not in ("open", "closed"):
        errs.append(f"status 必须 open/closed: {status!r}")
    if status == "closed":
        if not rec.get("closed_date"):
            errs.append("关店缺 closed_date")
        if not rec.get("closed_source"):
            errs.append("关店缺 closed_source（关店信息 URL）")

    # ---- 证据（反软广核心）----
    ev = rec.get("evidence") or {}
    closed = (status == "closed")
    # evidence_summary 字数门：open 店硬门（媒体稿回答不了"为什么好吃"）；closed 店只记录关店、放宽为警告
    summary_text = (rec.get("evidence_summary") or "").strip()
    if len(summary_text) < 200:
        (warns if closed else errs).append(f"evidence_summary 不足200字（当前 {len(summary_text)}）")
    quotes = ev.get("diner_quotes") or []
    if len(quotes) < 2 and not closed:
        errs.append(f"堂食食客证据少于 2 条（当前 {len(quotes)}）")
    substance, ugc_diner = 0, 0
    for q in quotes:
        url = (q.get("url") or "").strip()
        quote = (q.get("quote") or "").strip()
        qkind = C.source_kind(q.get("source"), url)
        if not url:
            errs.append("存在无 URL 的食客证据（一手信源强制）")
        if not C.quote_has_substance(quote):
            warns.append(f"食客证据疑似空话/软广: {quote[:24]}…")
        else:
            substance += 1
        if qkind == "ugc" and C.quote_has_substance(quote):
            ugc_diner += 1
        elif qkind != "ugc":
            warns.append(f"非食客UGC来源({qkind})不计入堂食食客数: {q.get('source')}")
    if substance < 1 and not closed:
        errs.append("没有任何一条含具体菜品/体验的堂食证据（反软广不通过）")
    if ugc_diner < 2 and not closed:
        errs.append(f"真实食客UGC堂食原话少于2条（当前{ugc_diner}；媒体/官方/榜单/品牌稿不计入食客数）")

    pscores = ev.get("platform_scores") or []
    if len(pscores) < 1 and not closed:
        errs.append("缺 platform_scores")
    for ps in pscores:
        sc = ps.get("score")
        rc = ps.get("review_count")
        if sc is not None and rc is not None and rc < 50 and float(sc) >= 4.5:
            warns.append(f"{ps.get('platform')} 评论数<50 却高分，可信度系数应≤0.7")
    flags = ev.get("soft_ad_flags") or []
    if len(flags) >= 3:
        warns.append(f"命中 {len(flags)} 项软广信号，建议人工复核是否剔除")
    if not ev.get("negative_signals"):
        warns.append("无任何差评信号（全好评异常，需补负面交叉验证）")

    # ---- 来源独立性（按 URL 域名重判，不信模型自填 type）----
    sources = rec.get("sources") or []
    if len(sources) < 2:
        errs.append("sources 少于 2 个独立来源")
    src_kinds, norm_sources = {}, []
    for s in sources:
        if not s.get("url"):
            errs.append("存在无 URL 的 source")
        k = C.source_kind(s.get("title"), s.get("url"))
        s2 = dict(s); s2["kind"] = k
        norm_sources.append(s2)
        src_kinds[k] = src_kinds.get(k, 0) + 1
        mt = (s.get("type") or "").replace("news", "media")
        if mt and mt != k and not (mt == "overseas_media" and k == "media"):
            warns.append(f"source 自填类型 {s.get('type')} 与 URL 判定 {k} 不符: {str(s.get('title'))[:18]}")
    if "ugc" not in src_kinds and not closed:
        errs.append("sources 无任何食客 UGC 来源（媒体/榜单/品牌稿不能替代食客实测）")
    if len(src_kinds) < 2:
        (warns if closed else errs).append(f"来源类型少于2类（当前 {sorted(src_kinds)}；须 UGC + 官方指南/媒体/地图 至少两类）")
    sources = norm_sources

    # ---- 评分（脚本重算 total，防止模型算错）----
    sc_in = rec.get("scores") or {}
    try:
        obj = float(sc_in.get("objective", 0)); diner = float(sc_in.get("diner", 0))
        taste = float(sc_in.get("taste", 0)); endo = float(sc_in.get("endorsement", 0))
        pen = float(sc_in.get("soft_ad_penalty", 0))
        for k, v, hi in [("objective", obj, 100), ("diner", diner, 100),
                         ("taste", taste, 100), ("endorsement", endo, 100), ("penalty", pen, 30)]:
            if v < 0 or v > hi:
                errs.append(f"scores.{k} 越界: {v}")
        # 分项为百分制子分；total 按 v3 权重 taste0.35/objective0.25/diner0.25/endorsement0.15 加权后减软广扣分（与库触发器一致）
        total = round(max(0, 0.35 * taste + 0.25 * obj + 0.25 * diner + 0.15 * endo - pen), 1)
    except (TypeError, ValueError):
        errs.append("scores 不是数值"); total = None

    # ---- 品牌归属 ----
    if rec.get("brand_group") and not rec.get("brand_confirmed"):
        warns.append(f"brand_group={rec.get('brand_group')} 未经核实（brand_confirmed=false）")

    # ---- 电话（宁空不假）----
    phone, p_issues, p_note = C.clean_phone(rec.get("phone_raw"))
    for pi in p_issues:
        if pi == "phone_missing":
            if price is not None and price >= 200:
                warns.append("高端店缺电话，建议补预订方式")
        elif pi == "phone_switchboard":
            warns.append("电话为总机/分机（可拨但非直线，已在 booking_method 备注）")
        else:  # phone_unparseable：有数字却不合法，疑似编造
            errs.append(f"电话疑似编造/非法（{pi}）；查不到请留空，不要造假")

    # ---- 坐标（若给了必须在上海）----
    lat, lng = rec.get("lat"), rec.get("lng")
    if lat is not None and lng is not None:
        if not C.in_shanghai(lng, lat):
            errs.append(f"坐标不在上海范围: lng={lng} lat={lat}")

    if errs:
        return errs, warns, None

    # ---- 产出清洗后的规范记录 ----
    clean = {
        "name": name,
        "name_en": rec.get("name_en"),
        "match_restaurant_id": rec.get("match_restaurant_id"),
        "brand_group": rec.get("brand_group"),
        "brand_confirmed": bool(rec.get("brand_confirmed")),
        "scene": rec.get("scene"),
        "cuisine_paths": paths,
        "form": form,
        "meals": rec.get("meals") or ["午餐", "晚餐"],
        "ingredients": rec.get("ingredients") or [],
        "awards": rec.get("awards") or {},
        "special_tags": rec.get("special_tags") or [],
        "price_avg": price,
        "price_range": rec.get("price_range"),
        "tier": tier,
        "district": district,
        "address": address,
        "business_area": rec.get("business_area"),
        "lat": lat, "lng": lng, "coord_source": rec.get("coord_source"),
        "phone": phone,
        "booking_method": "；".join([x for x in [rec.get("booking_method"), p_note] if x]) or None,
        "signature_dishes": dishes,
        "status": C.STATUS_CLOSED if status == "closed" else C.STATUS_OPEN,
        "closed_date": rec.get("closed_date"), "closed_source": rec.get("closed_source"),
        "scores": {"objective": obj, "diner": diner, "taste": taste,
                   "endorsement": endo, "soft_ad_penalty": pen, "total": total},
        "evidence": ev,
        "sources": sources,
        "data_updated_at": rec.get("data_updated_at") or C.today(),
        "notes": rec.get("notes"),
        "evidence_summary": summary_text,
        "_warnings": warns,
    }
    return errs, warns, clean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("-o", "--output", default="accepted.jsonl")
    ap.add_argument("-r", "--rejected", default="rejected.tsv")
    args = ap.parse_args()

    raw = C.read_jsonl(args.input)
    accepted, rejected = [], []
    for rec in raw:
        errs, warns, clean = validate(rec)
        if clean is None:
            rejected.append(((rec.get("name") or "?").strip(), " | ".join(errs)))
        else:
            accepted.append(clean)

    C.write_jsonl(args.output, accepted)
    with open(args.rejected, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["name", "reasons"])
        w.writerows(rejected)

    print(f"原始 {len(raw)} 家 | 通过 {len(accepted)} | 打回 {len(rejected)}")
    warn_n = sum(1 for a in accepted if a["_warnings"])
    print(f"通过但带警告 {warn_n} 家（见 accepted.jsonl 的 _warnings，建议复核）")
    if rejected:
        print("\n=== 打回清单（修复后重跑）===")
        for n, reason in rejected[:50]:
            print(f"  ✗ {n}: {reason}")
    print(f"\n输出: {args.output} / {args.rejected}")
    sys.exit(2 if rejected else 0)


if __name__ == "__main__":
    main()

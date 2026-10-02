#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dianping_enrich.py — 大众点评富源采集器（独立小店覆盖 + 连锁/人均校准 + 平台评分落地）。

为什么存在（keyless 通用 SERP 能力边界已实测坐实）：
  - 通用搜索只覆盖有新闻/招股书的连锁，覆盖不到独立小店（老吴家川菜 srcs=0）；
  - 点评 cookie 有效、服务端搜索页直接带【星级/评价数/人均/菜系/商圈/分店数/关店】，
    独立小店也齐全。本模块用点评补齐这一缺口。

设计（只采集，不直接写库；复用既有单一写入门，保证联动、可审计）：
  1) chain_type / price_avg → 标准 findings，追加 post_record/findings.jsonl，
     由 `gate_apply.py --apply` 仲裁写库（硬标需≥2独立源，点评=branch 类）；
  2) 连锁硬主张 + 平台评分(platform_rating) → 生成 fact_verify claims seed，
     由 `fact_verify.py --apply`（FOOD_FACT_SEED 指向本种子）合并 fact_claims、回读；
  平台评分只作带出处主张落地，暂不直接改 score_*（后续 scoring_engine 统一读取）。

礼貌低频：每次搜索内部 sleep 2.5s；--max 控制每轮店数；按 rid 断点。
用法（容器内先 . /app/cloud/env.sh）：
  python3 dianping_enrich.py --max 30
  python3 dianping_enrich.py --max 30 --driver   # 采集后自动跑 gate_apply/fact_verify
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)

import dianping_branch_list as DBL  # noqa: E402

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
FINDINGS = LEDGER / "findings.jsonl"
CHECKPOINT = LEDGER / "dianping_enrich.done"
FACT_DIR = DATA / "fact_verify"
FACT_DIR.mkdir(parents=True, exist_ok=True)
DP_SEED = FACT_DIR / "dp_claims_seed.json"


def chain_value(n):
    if n <= 1:
        return "独立店"
    if n < 10:
        return "小型连锁"
    return "大型连锁"


def base_name(name):
    return re.split(r"[（(]", name or "")[0].strip()


def match_card(restaurant, cards):
    """把该餐厅匹配到唯一点评卡片；匹配不到返回 None（仅用品牌级数据）。"""
    name = restaurant.get("name", "")
    # 1) 全名精确
    for c in cards:
        if c.get("name") == name:
            return c
    # 2) 店名括号内分店标记
    m = re.search(r"[（(]([^）)]+)[）)]", name)
    tag = m.group(1) if m else ""
    if tag:
        for c in cards:
            if tag in (c.get("name") or ""):
                return c
    # 3) 商圈/区 与 地址
    addr = restaurant.get("address", "") or ""
    dist = restaurant.get("district", "") or ""
    for c in cards:
        reg = c.get("region") or ""
        if reg and (reg.split("/")[0] in addr or reg in addr or
                    (dist and dist in reg)):
            return c
    # 4) 仅一店
    return cards[0] if len(cards) == 1 else None


def load_done():
    if CHECKPOINT.exists():
        return {l.strip() for l in CHECKPOINT.read_text().splitlines() if l.strip()}
    return set()


def load_existing_findings():
    seen = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l)
                seen.add((d.get("restaurant_id"), d.get("field"), d.get("source_url")))
    return seen


def finding(rid, name, field, value, conf, source_url, source_title, reason):
    return {"restaurant_id": rid, "name": name, "field": field, "value": value,
            "confidence": conf, "source_url": source_url, "source_title": source_title,
            "reason": reason, "search_date": time.strftime("%Y-%m-%d"),
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def collect(rests, max_n):
    done = load_done()
    seen_f = load_existing_findings()
    new_findings = []
    brands = []
    processed = 0
    for r in rests:
        rid = r["id"]
        if str(rid) in done or processed >= max_n:
            continue
        name = r.get("name", "")
        all_cards = DBL.search_shops(name)
        # 只认店名包含品牌本名的卡片，排除点评关键词的模糊/相关推荐（防短名误判连锁）
        bn = base_name(name)
        cards = [c for c in all_cards if bn and bn in (c.get("name") or "")]
        if not cards and all_cards:
            # 无任何本名命中 → 视为未核实，不主张连锁/评分（宁空不假）
            cards = []
        n = len(cards)
        search_url = "https://www.dianping.com/search/keyword/1/0_" + name
        card = match_card(r, cards)
        claims = []

        # 连锁（品牌级，branch 类）
        cv = chain_value(n)
        if n >= 1:
            reason = f"点评分店列表 {n} 家异址门店连锁"
            key = (rid, "chain_type", search_url)
            if key not in seen_f:
                new_findings.append(finding(
                    rid, name, "chain_type", cv, 0.9, search_url,
                    f"点评分店列表 {n} 家", reason))
                seen_f.add(key)
            claims.append({"type": "chain_type", "value": cv,
                           "source_url": search_url,
                           "source_title": f"点评分店列表 {n} 家",
                           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # 人均（匹配卡片）
        if card and card.get("avg_price"):
            key = (rid, "price_avg", card.get("url"))
            if key not in seen_f:
                new_findings.append(finding(
                    rid, name, "price_avg", card["avg_price"], 0.85, card.get("url"),
                    f"点评人均 ￥{card['avg_price']}",
                    f"点评门店人均 ￥{card['avg_price']}"))
                seen_f.add(key)

        # 平台评分（带出处主张，不改 score_*）
        if card and card.get("stars") is not None:
            claims.append({"type": "platform_rating", "platform": "dianping",
                           "rating": card.get("stars"),
                           "review_count": card.get("review_count"),
                           "source_url": card.get("url"),
                           "source_title": card.get("name"),
                           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # 关店（仅主张，不自动 status；交通知/复查）
        if card and card.get("is_closed"):
            claims.append({"type": "closed_watch", "source_url": card.get("url"),
                           "source_title": card.get("name"),
                           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        if claims:
            brands.append({"brand": name, "match_contains": base_name(name),
                           "fields": {}, "claims": claims})

        with CHECKPOINT.open("a") as fh:
            fh.write(f"{rid}\n")
        processed += 1

    # 追加 findings
    if new_findings:
        with FINDINGS.open("a", encoding="utf-8") as fh:
            for f in new_findings:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    # 合并 claims seed（按 brand 名去重，claims 按 type+source_url 去重）
    existing = {"brands": []}
    if DP_SEED.exists():
        existing = json.loads(DP_SEED.read_text(encoding="utf-8"))
    by_brand = {b["brand"]: b for b in existing.get("brands", [])}
    for b in brands:
        cur = by_brand.get(b["brand"])
        if not cur:
            by_brand[b["brand"]] = b
        else:
            seen = {(c.get("type"), c.get("source_url")) for c in cur["claims"]}
            for c in b["claims"]:
                if (c.get("type"), c.get("source_url")) not in seen:
                    cur["claims"].append(c)
    DP_SEED.write_text(
        json.dumps({"brands": list(by_brand.values())}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return processed, len(new_findings), len(brands)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=30)
    ap.add_argument("--driver", action="store_true")
    ap.add_argument("--priority-empty", action="store_true",
                    help="优先处理无 score_taste/无证据的店（覆盖缺口）")
    args = ap.parse_args()

    import common as C
    rests = C.fetch_all(
        "restaurants",
        "id,name,status,district,address,chain_type,price_avg,score_taste,"
        "production_model,review_count", order_col="id")
    active = [r for r in rests if r.get("status") == "active"]
    if args.priority_empty:
        active.sort(key=lambda r: (r.get("score_taste") is not None,
                                   r.get("production_model") is not None))
    processed, nf, nb = collect(active, args.max)
    print(f"[dianping_enrich] processed={processed} new_findings={nf} brands_claims={nb}")
    print(f"  findings -> {FINDINGS}；claims seed -> {DP_SEED}")

    if args.driver and (nf or nb):
        import subprocess
        env = dict(os.environ)
        if nf:
            subprocess.run([sys.executable, "gate_apply.py", "--apply"],
                           cwd=str(HERE), env=env, check=False)
        if nb:
            env["FOOD_FACT_SEED"] = str(DP_SEED)
            subprocess.run([sys.executable, "fact_verify.py", "--apply"],
                           cwd=str(HERE), env=env, check=False)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_bridge.py — 建店桥接（deep_coverage admit 候选 → raw_place → stage1-4 建店）。

定位：deep_coverage 只【发现】，本模块负责把通过全文核验门的候选，补成可入库实体。
铁律：
  ① 只依据真实抓取的网页全文起草，地址/人均/电话/堂食原话拿不到一律留空，禁止编造；
  ② 确定性 stage1 质量门为准（≥2 条含菜名的真实食客 UGC 堂食原话 + 地址 + 平台分 + ≥2 类来源）；
  ③ 过门槛才建店；缺 UGC → need_ugc 队列（交 Apify），缺地址/坐标 → need_poi 队列（交地图）；
  ④ 幂等 + 断点（build_bridge_state.json），建过的不重建。

用法：
  python3 build_bridge.py                 # 补证据 + 过门，落 raw/队列（不写库）
  python3 build_bridge.py --apply         # 过门的走 stage1→2→3→4 正式建店
"""
import argparse
import glob
import json
import os
import pathlib
import re
import subprocess
import sys
import datetime

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")

import common_core as CC          # noqa: E402
import deep_coverage as D         # noqa: E402
from crowd_v4 import verified_pages

COVDIR = pathlib.Path("/app/data/coverage")
STATEP = COVDIR / "build_bridge_state.json"
TODAY = datetime.date.today().isoformat()


# ---------- 分类树：叶名 → [虚拟根, …, 叶]（确定性，不让模型编路径） ----------
def cuisine_path_of(leaf_name, byname, byid):
    """parent_category 库里两种存法混用（父名 / 数字 id），都兼容；链上统一存名。"""
    chain, cur, seen = [], leaf_name, set()
    while cur is not None and str(cur) not in seen:
        seen.add(str(cur))
        node = byname.get(cur)
        if node is None and str(cur).isdigit() and int(cur) in byid:
            node = byid[int(cur)]
        if not node:
            break
        chain.append(node["name"])
        cur = node.get("parent_category")
    chain.reverse()
    return [chain] if len(chain) >= 2 else None


def load_admits():
    """读全部 deep_candidates_*.jsonl，按 norm 名去重（strong 优先、菜多优先）。"""
    best = {}
    for f in sorted(glob.glob(str(COVDIR / "deep_candidates_*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("evidence_level") not in ("strong", "weak"):
                continue
            k = D.norm(r["name"])
            score = (2 if r["evidence_level"] == "strong" else 1,
                     len(r.get("dishes", [])))
            if k not in best or score > best[k][0]:
                best[k] = (score, r)
    return [v[1] for v in best.values()]


def gather_pages(rec):
    """候选已验证 URL + 最多2条点评/评价补充查询；抓含店名整页，合并。"""
    name = rec["name"]
    urls, u = [], set()
    for e in rec.get("evidence", []):
        if e.get("url") and e["url"] not in u:
            u.add(e["url"]); urls.append(e["url"])
    for q in (f"{name} 上海 评价", f"{name} 大众点评"):
        for h in D.searx(q)[:5]:
            if h.get("url") and h["url"] not in u \
                    and D.norm(name) in D.norm(h.get("title", "") + " " + h.get("snippet", "")):
                u.add(h["url"]); urls.append(h["url"])
    pages, used = verified_pages(name, os.environ.get('CROWD_V4_EVIDENCE_FILE', str(COVDIR / 'crowd_v4_verified.jsonl')))
    total = sum(map(len, pages))
    for url in urls[:6]:
        if url in used:
            continue
        ft = D.fetch_fulltext(url)
        if ft and D.norm(name) in D.norm(ft):
            pages.append(f"【来源{len(pages)+1} {url}】\n{ft}")
            used.append(url); total += len(ft)
            if total > 6200:
                break
    return pages, used


DRAFT_PROMPT = """你是严格的美食资料编辑。下面是关于上海候选餐厅「{name}」、品类「{leaf}」的网页全文。
请只依据这些全文抽取，禁止使用任何记忆，网页里没有的字段一律填 null，绝不编造地址/人均/电话/评价。输出 JSON：
{{"district":"上海XX区或null","address":"完整门牌地址或null","business_area":"商圈或null",
"price_avg":整数或null,"price_range":"如¥120-180或null","form":"Finedining/Bistro/Casual Dining",
"signature_dishes":["至少2道具体菜名"],
"diner_quotes":[{{"quote":"真实食客堂食原话(含菜名/体验,逐字)","dish":"相关菜名或null",
"source":"平台名","url":"原帖直链","date":"日期或null"}}],
"platform_scores":[{{"platform":"大众点评/高德等","score":数字,"review_count":整数或null,"url":"链接"}}],
"negative_signals":["差评/风险点"],"soft_ad_flags":["命中的软广信号"],
"evidence_summary":"≥200字、只基于全文的证据综述：它家风味/招牌/真实食客怎么评价/有何争议",
"sources":[{{"title":"标题","url":"链接","type":"ugc/map/news/brand_official"}}]}}
要求：diner_quotes 只收真实食客堂食内容（媒体/官方通稿不算），最多6条、宁少不假；
正常好店也应有 negative_signals，全文无差评就留空数组。

{pages}"""


def draft_raw(rec, pages, used_urls, cuisine_paths):
    name, leaf = rec["name"], rec["cuisine"]
    prompt = DRAFT_PROMPT.format(name=name, leaf=leaf, pages="\n\n".join(pages))
    d = None
    for p, m in D.pick_models():
        import model_providers as MP
        r = MP.chat(p, m, prompt, web_search=False, timeout=90)
        MP.log_usage("build_bridge", r)
        if not r.get("ok"):
            continue
        mobj = re.search(r"\{.*\}", r.get("text", ""), re.S)
        try:
            d = json.loads(mobj.group(0) if mobj else r["text"])
            break
        except Exception:
            continue
    if not d:
        return None
    # 合并 verify 已得的菜/好评（种子，降低漏抽）
    dishes = [x for x in (d.get("signature_dishes") or []) if x]
    for x in rec.get("dishes", []):
        if x and x not in dishes:
            dishes.append(x)
    quotes = d.get("diner_quotes") or []
    if rec.get("praise") and not any(rec["praise"][:12] in (q.get("quote") or "") for q in quotes):
        quotes.insert(0, {"quote": rec["praise"], "dish": (dishes[0] if dishes else None),
                          "source": "网页", "url": (used_urls[0] if used_urls else None),
                          "date": None})
    sources = d.get("sources") or []
    have = {s.get("url") for s in sources}
    for url in used_urls:
        if url not in have:
            sources.append({"title": url, "url": url, "type": "ugc"})
    form = d.get("form") or "Casual Dining"
    price = d.get("price_avg")
    if form == "Finedining" and (not price or price < 250):
        form = "Casual Dining"
    return {
        "name": name,
        "district": d.get("district") or "待确认",
        "address": d.get("address") or "",
        "business_area": d.get("business_area"),
        "price_avg": price, "price_range": d.get("price_range"),
        "cuisine_paths": cuisine_paths, "form": form,
        "signature_dishes": dishes,
        "status": "open",
        "evidence": {"diner_quotes": [q for q in quotes if q.get("url")],
                     "platform_scores": d.get("platform_scores") or [],
                     "negative_signals": d.get("negative_signals") or [],
                     "soft_ad_flags": d.get("soft_ad_flags") or []},
        "evidence_summary": d.get("evidence_summary") or "",
        "sources": sources, "data_updated_at": TODAY,
        "notes": d.get("notes")}


def classify_missing(errs):
    txt = " | ".join(errs)
    need = []
    if "address" in txt or "district" in txt:
        need.append("need_poi")
    if "UGC" in txt or "食客" in txt or "堂食" in txt:
        need.append("need_ugc")
    if "platform_scores" in txt or "招牌" in txt or "summary" in txt or "来源" in txt:
        need.append("need_ugc")
    return need or ["need_review"]


def run_stage(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    COVDIR.mkdir(parents=True, exist_ok=True)

    state = json.loads(STATEP.read_text()) if STATEP.exists() else {}
    cuis = CC.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    byname = {c["name"]: c for c in cuis}
    byid = {c["id"]: c for c in cuis}

    admits = load_admits()
    todo = [r for r in admits if state.get(D.norm(r["name"]), {}).get("status") != "built"]
    print(f"admit 候选 {len(admits)}；待处理 {len(todo)}；本轮最多 {args.limit}")

    raw_batch, hold = [], {"need_ugc": [], "need_poi": []}
    import stage1_validate as S1
    for rec in todo[:args.limit]:
        k = D.norm(rec["name"])
        cp = cuisine_path_of(rec["cuisine"], byname, byid)
        if not cp:
            state.setdefault(k, {}).update({"name": rec["name"], "status": "need_review",
                                            "reason": "cuisine path unresolved"})
            continue
        pages, used = gather_pages(rec)
        if not pages:
            state.setdefault(k, {}).update({"name": rec["name"], "status": "need_ugc",
                                            "reason": "no full page with name"})
            hold["need_ugc"].append(rec)
            continue
        raw = draft_raw(rec, pages, used, cp)
        if not raw:
            state.setdefault(k, {}).update({"name": rec["name"], "status": "error",
                                            "reason": "draft failed"})
            continue
        errs, warns, _clean = S1.validate(raw)
        if errs:
            needs = classify_missing(errs)
            state.setdefault(k, {}).update({"name": rec["name"], "status": needs[0],
                                            "reason": " | ".join(errs)[:300]})
            if "need_poi" in needs:
                hold["need_poi"].append({"name": rec["name"], "leaf": rec["cuisine"]})
            if "need_ugc" in needs:
                hold["need_ugc"].append({"name": rec["name"], "leaf": rec["cuisine"]})
            print(f"  HOLD {rec['name']} -> {needs}")
            continue
        raw_batch.append(raw)
        state.setdefault(k, {}).update({"name": rec["name"], "status": "ready"})
        print(f"  PASS {rec['name']}（warnings {len(warns)}）")

    # 落 raw + 队列
    rawp = COVDIR / f"raw_place_{TODAY}.jsonl"
    if raw_batch:
        with open(rawp, "a", encoding="utf-8") as f:
            for r in raw_batch:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for q, rows in hold.items():
        if not rows:
            continue
        p = COVDIR / f"{q}.jsonl"
        existing = {D.norm(json.loads(l)["name"]) for l in open(p) if l.strip()} if p.exists() else set()
        with open(p, "a", encoding="utf-8") as f:
            for r in rows:
                if D.norm(r["name"]) not in existing:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    STATEP.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(f"\n过门待建 {len(raw_batch)}；need_ugc {len(hold['need_ugc'])}；"
          f"need_poi {len(hold['need_poi'])}")

    if not args.apply or not raw_batch:
        if not args.apply:
            print("dry-run（加 --apply 走 stage1-4 建店）")
        return

    P = "/app/pipeline"
    accepted = COVDIR / f"accepted_{TODAY}.jsonl"
    rejected = COVDIR / f"rejected_{TODAY}.tsv"
    plan = COVDIR / f"plan_{TODAY}.json"
    rc, out = run_stage(["python3", f"{P}/stage1_validate.py", "-i", str(rawp),
                         "-o", str(accepted), "-r", str(rejected)])
    print(out[-600:])
    rc, out = run_stage(["python3", f"{P}/stage2_prepare.py", "-i", str(accepted),
                         "-o", str(plan), "--create-tags"])
    print(out[-800:])
    rc, out = run_stage(["python3", f"{P}/stage3_upsert.py", "-i", str(plan), "--commit"])
    print(out[-1200:])
    rc, out = run_stage(["python3", f"{P}/stage4_audit.py"])
    print(out[-500:])
    for r in raw_batch:
        state[D.norm(r["name"])].update(status="built", built_at=TODAY)
    STATEP.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print("建店完成，state 已置 built")


if __name__ == "__main__":
    main()

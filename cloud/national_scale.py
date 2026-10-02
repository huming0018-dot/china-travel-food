#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""national_scale.py — 对 scale_pending 店做【全国·分页】高德 POI 计数（客观规模）。

为什么：之前 map_scan 用 citylimit=true 只数上海，全国性连锁在上海仅数家会被误判规模待证。
全国（citylimit=false）分页（最多4页/100）数同品牌 POI 总数：
  ≥10 → 大型连锁；2-9 → 小型连锁。与点评主证据（不同域名）凑成 2 独立源 → gate 晋升。
仅 --apply 追加 findings 与 progress。
"""
import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import map_quota as MQ
import reverify_supply as R

LEDGER = pathlib.Path("/app/data/post_record")
SUPPLY_PROG = LEDGER / "reverify_supply_progress.json"
PROG = LEDGER / "national_scale_progress.json"
FINDINGS = LEDGER / "findings.jsonl"
MAX_PAGES = 4


def amap_page(kw, page):
    j, st = MQ.call("amap", "/v3/place/text",
                    {"keywords": kw, "citylimit": "false", "offset": 25, "page": page,
                     "extensions": "all"}, "search", "chain", timeout=18)
    if st != "ok":
        return [], st
    pois = []
    for p in (j or {}).get("pois", []):
        pois.append({"title": p.get("name", ""), "address": p.get("address", ""),
                     "city": p.get("cityname", ""), "loc": p.get("location", "")})
    return pois, "ok"


def search_url(kw):
    from urllib.parse import quote
    return "https://www.amap.com/search?query=" + quote(kw)


def done_set():
    if not PROG.exists():
        return set()
    data = json.loads(PROG.read_text(encoding="utf-8"))
    return set(data.get("done", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    scale = json.loads(SUPPLY_PROG.read_text(encoding="utf-8")).get("scale_pending", [])
    done = done_set()
    todo = [r for r in scale if r not in done]
    if a.limit:
        todo = todo[:a.limit]
    buckets = {"promote_large": [], "promote_small": [], "conflict": [], "blocked": []}
    for i, rid in enumerate(todo):
        st = core.fetch_all("restaurants", "id,name,chain_type", extra=f"id=eq.{rid}")
        if not st:
            continue
        name = st[0]["name"]
        brand = R.brand_of(name)
        cores = R.brand_cores(brand)
        union, seen, status = [], set(), "ok"
        for page in range(1, MAX_PAGES + 1):
            pois, stt = amap_page(brand, page)
            if stt != "ok":
                status = stt
                break
            added = 0
            for p in pois:
                if not R.same_brand(p["title"], cores):
                    continue
                k = p["loc"] or (p["city"] + p["title"])
                if k not in seen:
                    seen.add(k)
                    union.append(p)
                    added += 1
            if len(pois) < 25 or added == 0:
                break
            time.sleep(0.4)
        n = len(union)
        if status != "ok":
            buckets["blocked"].append(rid)
            print(f"[{i+1}] rid{rid} {brand} blocked({status})")
            continue
        if n >= 10:
            lvl = "大型连锁"
        elif n >= 2:
            lvl = "小型连锁"
        else:
            lvl = "独立店"
        cities = sorted({p["city"] for p in union if p["city"]})
        if a.apply:
            sample = "、".join(p["title"] for p in union[:8])
            reason = "全国地图POI同品牌共%d处、覆盖%s等；%s（地图核验·全国分页）" % (
                n, "、".join(cities[:6]), sample)
            rec = {"restaurant_id": rid, "field": "chain_type", "value": lvl,
                   "confidence": 0.85, "reason": reason, "source_url": search_url(brand),
                   "source_platform": "amap_national",
                   "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with FINDINGS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if lvl == "大型连锁":
                key = "promote_large"
            elif lvl == "小型连锁":
                key = "promote_small"
            else:
                key = "conflict"
            buckets[key].append(rid)
            print(f"[{i+1}] rid{rid} {brand[:16]} n={n} -> {lvl} (db {st[0]['chain_type']}) {key}")
            prog = {"done": sorted(done | {rid}),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            PROG.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")
        else:
            print(f"[{i+1}] rid{rid} {brand[:16]} dry n={n} -> {lvl}")
        time.sleep(0.5)
    print("\n=== 汇总 ===")
    for k, v in buckets.items():
        print(f"  {k}: {len(v)} {v[:20]}")
    print("NAT_SCALE_DONE apply=%s" % a.apply)


if __name__ == "__main__":
    main()

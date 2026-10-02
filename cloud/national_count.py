#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""national_count.py — 用高德全国检索的 count 字段客观判定品牌规模。

关键事实（实测）：高德 place/text 在 citylimit=false 且不指定 city 时，
  返回的 `count` = 全国同关键词 POI 总数（一风堂 count=72），
  但 pois 列表只回少量记录、page≥2 常为空。因此规模必须读 count，不能枚举 pois。
规模档：count≥10 大型连锁；2-9 小型连锁；<2 独立店。
样本 pois 用于品牌自验（至少一条命中品牌核心，否则不采信 count）。

用法：
  python3 national_count.py --source scale --apply     # scale_pending 组
  python3 national_count.py --source dispute --apply   # dispute_down 组（覆盖少计）
"""
import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import map_quota as MQ
import reverify_supply as R

LEDGER = pathlib.Path("/app/data/post_record")
SUPPLY_PROG = LEDGER / "reverify_supply_progress.json"
DISPUTE = LEDGER / "dispute_down.json"
FINDINGS = LEDGER / "findings.jsonl"


def amap_count(kw):
    j, st = MQ.call("amap", "/v3/place/text",
                    {"keywords": kw, "citylimit": "false", "offset": 25, "page": 1,
                     "extensions": "all"}, "search", "chain", timeout=18)
    if st != "ok":
        return None, [], st
    cnt = int((j or {}).get("count", 0))
    sample = [p.get("name", "") for p in (j or {}).get("pois", [])]
    return cnt, sample, "ok"


TENCENT_CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "重庆", "武汉",
                  "西安", "南京", "苏州", "长沙", "青岛", "郑州", "天津"]


def tencent_count(kw):
    # 先试 region(全国)
    j, st = MQ.call("tencent", "/ws/place/v1/search",
                    {"keyword": kw, "boundary": "region(全国,0)", "page_size": 20},
                    "search", "chain", timeout=18)
    if st == "ok" and isinstance(j, dict) and j.get("status") == 0:
        total = j.get("count")
        if total is None:
            total = (j.get("result") or {}).get("total")
        if total is not None:
            sample = [d.get("title", "") for d in j.get("data", [])]
            return int(total), sample, "ok"
    # 回退：多城市 region 计数（同品牌去重）
    seen, sample, status = set(), [], st
    for city in TENCENT_CITIES:
        j, st = MQ.call("tencent", "/ws/place/v1/search",
                        {"keyword": kw, "boundary": f"region({city},0)", "page_size": 20},
                        "search", "chain", timeout=18)
        if st != "ok":
            status = st
            continue
        for d in (j or {}).get("data", []):
            title = d.get("title", "")
            k = str(d.get("location", "")) or title
            if k not in seen:
                seen.add(k); sample.append(title)
        time.sleep(0.2)
    return len(seen), sample, "ok"


def level_for(n):
    if n >= 10:
        return "大型连锁"
    if n >= 2:
        return "小型连锁"
    return "独立店"


def search_url(kw):
    from urllib.parse import quote
    return "https://www.amap.com/search?query=" + quote(kw)


def rids_for(source):
    if source == "scale":
        return json.loads(SUPPLY_PROG.read_text(encoding="utf-8")).get("scale_pending", [])
    return json.loads(DISPUTE.read_text(encoding="utf-8")).get("rids", [])


def existing_platforms(rid):
    plats = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            d = json.loads(l)
            if d.get("restaurant_id") == rid and d.get("field") == "chain_type":
                plats.add(d.get("source_platform", ""))
    return plats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="scale", choices=["scale", "dispute"])
    ap.add_argument("--provider", default="amap", choices=["amap", "tencent"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    rids = rids_for(a.source)
    if a.limit:
        rids = rids[:a.limit]
    count_fn = amap_count if a.provider == "amap" else tencent_count
    platform = "amap_national_count" if a.provider == "amap" else "tencent_national_count"
    pname = "高德" if a.provider == "amap" else "腾讯"
    buckets = {"large": [], "small": [], "indep": [], "blocked": [], "skip": []}
    for i, rid in enumerate(rids):
        st = core.fetch_all("restaurants", "id,name,chain_type", extra=f"id=eq.{rid}")
        if not st:
            continue
        name = st[0]["name"]
        brand = R.brand_of(name)
        cores = R.brand_cores(brand)
        if platform in existing_platforms(rid):
            buckets["skip"].append(rid); continue
        cnt, sample, status = count_fn(brand)
        # 品牌自验：count>0 但样本无一命中品牌 → 换第一个变体再试
        if status == "ok" and cnt and not any(R.same_brand(s, cores) for s in sample):
            vs = [v for v in re.split(r"[·•丨]", re.sub(r"[（(].*?[)）]", "", name))
                  if len(v.strip()) >= 2]
            if vs:
                cnt2, sample2, st2 = count_fn(vs[0].strip())
                if st2 == "ok" and any(R.same_brand(s, cores) for s in sample2):
                    cnt, sample = cnt2, sample2
        if status != "ok":
            buckets["blocked"].append(rid)
            print(f"[{i+1}] rid{rid} {brand[:16]} blocked({status})")
            continue
        lvl = level_for(cnt)
        if a.apply:
            reason = "%s全国检索 count=%d（全国同品牌门店总数）；样本：%s（地图核验·count口径）" % (
                pname, cnt, "、".join(sample[:6]))
            rec = {"restaurant_id": rid, "field": "chain_type", "value": lvl,
                   "confidence": 0.85, "reason": reason, "source_url": search_url(brand),
                   "source_platform": platform,
                   "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            with FINDINGS.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        key = {"大型连锁": "large", "小型连锁": "small", "独立店": "indep"}[lvl]
        buckets[key].append(rid)
        print(f"[{i+1}] rid{rid} {brand[:16]} {pname}count={cnt} -> {lvl} (db {st[0]['chain_type']})")
        time.sleep(0.5)
    print("\n=== %s/%s 汇总（apply=%s）===" % (a.source, a.provider, a.apply))
    for k, v in buckets.items():
        print(f"  {k}: {len(v)} {v[:25]}")
    print("NAT_COUNT_DONE")


if __name__ == "__main__":
    main()

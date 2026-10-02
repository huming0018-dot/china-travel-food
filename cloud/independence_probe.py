#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""independence_probe.py — 对 dispute_down 店做【全国】双地图 POI 核验。

每供应商全国检索同品牌 POI：
  <2 处 → 追加 chain_type=独立店 澄清证据（conf .8）；
  ≥2 处 → 追加对应连锁档位硬证据（说明确为连锁）。
两个供应商（amap.com / qq.com 不同域名）均判独立 → gate 满足 2 独立源，下调为独立店。
幂等：同一供应商已出过该字段证据则跳过。断点：按 rid 落 progress。
"""
import argparse, json, pathlib, re, sys, time
sys.path.insert(0, "/app/cloud"); sys.path.insert(0, "/app/pipeline")
import common_core as core
import map_quota as MQ
import reverify_supply as R

LEDGER = pathlib.Path("/app/data/post_record")
DISPUTE = LEDGER / "dispute_down.json"
PROG = LEDGER / "independence_progress.json"
FINDINGS = LEDGER / "findings.jsonl"


def variants(name):
    b = re.sub(r"[（(].*?[)）]", "", name or "").strip()
    vs = [R.brand_of(name), b]
    lat = " ".join(re.findall(r"[A-Za-z][A-Za-z0-9'&+.\- ]+", b)).strip()
    if len(lat) >= 3:
        vs.append(lat)
    for seg in re.split(r"[·•丨]", b):
        if len(seg.strip()) >= 2:
            vs.append(seg.strip())
    out = []
    for v in vs:
        if v and v not in out:
            out.append(v)
    return out


def national_pois(family, kw):
    if family == "amap":
        j, st = MQ.call("amap", "/v3/place/text",
                        {"keywords": kw, "citylimit": "false", "offset": 25,
                         "extensions": "all"}, "search", "chain", timeout=18)
        if st != "ok":
            return [], st
        return [{"title": p.get("name", ""), "address": p.get("address", ""),
                 "loc": p.get("location", "")} for p in (j or {}).get("pois", [])], "ok"
    # tencent：region=全国（不传 region）
    j, st = MQ.call("tencent", "/ws/place/v1/search",
                    {"keyword": kw, "page_size": 20}, "search", "chain", timeout=18)
    if st != "ok":
        return [], st
    return [{"title": p.get("title", ""), "address": p.get("address", ""),
             "loc": str(p.get("location", {}))} for p in (j or {}).get("data", [])], "ok"


def search_url(family, kw):
    from urllib.parse import quote
    if family == "amap":
        return "https://www.amap.com/search?query=" + quote(kw)
    return "https://map.qq.com/?type=search&keyword=" + quote(kw)


def existing_domains(rid):
    doms = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            d = json.loads(l)
            if d.get("restaurant_id") == rid and d.get("field") == "chain_type":
                m = re.match(r"https?://([^/]+)", d.get("source_url", ""))
                if m:
                    doms.add(m.group(1))
    return doms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="amap,tencent")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    providers = a.providers.split(",")
    rids = json.loads(DISPUTE.read_text(encoding="utf-8"))["rids"]
    blocked = []
    for i, rid in enumerate(rids):
        st = core.fetch_all("restaurants", "id,name", extra=f"id=eq.{rid}")
        if not st:
            continue
        name = st[0]["name"]
        brand = R.brand_of(name)
        cores = R.brand_cores(brand)
        doms = existing_domains(rid)
        per = {}
        for fam in providers:
            dom = "www.amap.com" if fam == "amap" else "apis.map.qq.com"
            if dom in doms:
                per[fam] = "skip"; continue
            union, seen = [], set()
            for v in variants(name):
                pois, stt = national_pois(fam, v)
                if stt != "ok":
                    per[fam] = stt; break
                for p in pois:
                    if not R.same_brand(p["title"], cores):
                        continue
                    k = p["loc"] or (p["title"] + p["address"])
                    if k not in seen:
                        seen.add(k); union.append(p)
                time.sleep(0.4)
            n = len(union)
            if a.apply:
                if n < 2:
                    val = "独立店"
                    reason = "全国地图POI仅检索到本店1处、未见同品牌分店（地图核验，宁空不假）"
                else:
                    val = R.level_for(n, n >= 25)
                    reason = "全国地图POI同品牌%d处：%s（地图核验）" % (
                        n, "、".join(p["title"] for p in union[:8]))
                rec = {"restaurant_id": rid, "field": "chain_type", "value": val,
                       "confidence": 0.8, "reason": reason,
                       "source_url": search_url(fam, brand),
                       "source_platform": fam + "_national",
                       "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                with FINDINGS.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                per[fam] = val + "(n=%d)" % n
            else:
                per[fam] = "dry n=%d" % n
            time.sleep(0.6)
        tag = ",".join(f"{f}:{s}" for f, s in per.items())
        print(f"[{i+1}/{len(rids)}] rid{rid} {brand[:16]} {tag}")
        if any("quota" in str(s) or s in ("dead", "blocked") for s in per.values()):
            blocked.append(rid)
    print("\nblocked", len(blocked), blocked)
    print("INDEP_PROBE_DONE apply=%s" % a.apply)


if __name__ == "__main__":
    main()

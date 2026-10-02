#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reverify_supply.py — 为单源硬负面 chain hold 补「第 2 独立源」。

主通道（客观、配额化、可复跑）：地图 POI 检索
  - 以品牌（去掉分店括号与·后缀）在高德/腾讯 place search 检索上海在营 POI；
  - 数同品牌、不同地址的分店点数；地图 POI 是独立于点评/媒体的第三方 POI 库；
  - 档位只按客观计数给证据：≥10 家→大型连锁；2-9 家→小型连锁；不臆测资本；
  - 现有源家族与地图家族互不重叠时才采纳；再由 gate_apply 聚合晋升。
    · asserted 小型 + 地图 2-9 → 补小型，gate n_ind≥2 晋升；
    · asserted 大型 + 地图 ≥10 → 补大型，晋升；地图仅 2-9 → 只补小型，规模留待媒体；
    · asserted 资本化 → 地图无法证资本，留媒体通道（不在此处理）。
不修改除 chain_type 外字段；宁空不假；断点续跑。

用法：python3 reverify_supply.py [--providers amap,tencent] [--limit N] [--apply]
"""
import argparse, json, os, pathlib, re, sys, time

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import common as P
import map_quota as MQ
import gate_apply as G

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER = DATA / "post_record"
FINDINGS = LEDGER / "findings.jsonl"
WORKLIST = LEDGER / "reverify_worklist.json"
PROGRESS = LEDGER / "reverify_supply_progress.json"


# ───────── 品牌与同品牌判定 ─────────
def brand_of(name):
    """去分店括号 → 去 ·/•/丨 后缀，返回查询用品牌（汉字核心优先）。"""
    b = re.sub(r"[（(].*?[)）]", "", name or "").strip()
    first = re.split(r"[·•丨]", b)[0].strip()
    han = "".join(c for c in first if "一" <= c <= "鿿")
    query = han if len(han) >= 2 else (first or b)
    return query or first or b


def brand_cores(brand):
    cores = set()
    nb = P.cjk_norm(brand)
    if nb and len(nb) >= 2:
        cores.add(nb)
    for m in re.findall(r"[A-Za-z][A-Za-z0-9'&+.\- ]{2,}", brand):
        s = m.strip().lower()
        if len(s) >= 3:
            cores.add(s)
    return cores


def same_brand(title, cores):
    nt = P.cjk_norm(title)
    low = (title or "").lower()
    for c in cores:
        if c in nt:
            return True
        if re.fullmatch(r"[a-z0-9 &+.'\-]+", c) and c in low:
            return True
    return False


# ───────── 现有源家族 ─────────
def _family(host):
    h = (host or "").lower()
    if "dianping" in h or "meituan" in h:
        return "dianping_meituan"
    if "amap" in h or "gaode" in h:
        return "amap"
    if "map.qq" in h or "lbs.qq" in h:
        return "tencentmap"
    if "map.360" in h:
        return "360map"
    if "map.baidu" in h:
        return "baidumap"
    if "qcc" in h:
        return "qcc"
    if "shuidi" in h:
        return "shuidi"
    if "tianyancha" in h:
        return "tianyancha"
    return "media:" + h


def existing_families(rid):
    fams = set()
    if FINDINGS.exists():
        for line in FINDINGS.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            f = json.loads(line)
            if f.get("restaurant_id") == rid and f.get("field") == "chain_type":
                m = G.RE_DOM.match(f.get("source_url") or "")
                if m:
                    fams.add(_family(m.group(1)))
    return fams


# ───────── 地图 POI 扫描（经配额仲裁）─────────
def _amap_pois(brand):
    j, st = MQ.call("amap", "/v3/place/text", {
        "keywords": brand, "city": "上海", "citylimit": "true",
        "offset": 25, "extensions": "all",
    }, "search", "chain", timeout=18)
    if st != "ok":
        return [], st
    out = []
    for p in (j or {}).get("pois", []):
        out.append({"title": p.get("name", ""), "address": p.get("address", ""),
                    "loc": p.get("location", "")})
    return out, "ok"


def _tencent_pois(brand):
    j, st = MQ.call("tencent", "/ws/place/v1/search", {
        "keyword": brand, "boundary": "region(上海)", "page_size": 20,
    }, "search", "chain", timeout=18)
    if st != "ok":
        return [], st
    out = []
    for it in (j or {}).get("data", []):
        loc = it.get("location", {})
        out.append({"title": it.get("title", ""), "address": it.get("address", ""),
                    "loc": f"{loc.get('lng')},{loc.get('lat')}"})
    return out, "ok"


def _web_url(family, brand):
    from urllib.parse import quote
    q = quote(brand)
    if family == "amap":
        return f"https://www.amap.com/search?query={q}&city=310000"
    return f"https://map.qq.com/?q={q}"


def map_scan(brand, cores, families_have, providers):
    results = []
    cand = []
    if "amap" in providers:
        cand.append(("amap", _amap_pois))
    if "tencent" in providers:
        cand.append(("tencentmap", _tencent_pois))
    for family, fn in cand:
        if family in families_have:
            continue
        pois, st = fn(brand)
        if st != "ok":
            results.append({"family": family, "status": st, "branches": []})
            continue
        seen, branches = set(), []
        for p in pois:
            if not same_brand(p["title"], cores):
                continue
            key = p.get("loc") or (p["title"] + p["address"])
            if key in seen:
                continue
            seen.add(key)
            branches.append(p["title"])
        results.append({"family": family, "status": "ok",
                        "branches": branches, "n": len(branches),
                        "capped": len(pois) >= 25})
        time.sleep(0.6)
    return results


def level_for(n, capped):
    if capped or n >= 10:
        return "大型连锁"
    if n >= 2:
        return "小型连锁"
    return None


def append_finding(rid, name, value, scan):
    web = _web_url(scan["family"], brand_of(name))
    titles = "; ".join(scan["branches"][:10])
    reason = (f"地图POI上海检索'{brand_of(name)}'得{scan['n']}家门店：{titles}")[:200]
    row = {
        "restaurant_id": rid, "name": name, "field": "chain_type",
        "value": value, "confidence": 0.85, "source_url": web,
        "source_title": f"{brand_of(name)} 上海门店分布", "reason": reason,
        "search_date": time.strftime("%Y-%m-%d"),
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with FINDINGS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="amap,tencent")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    providers = [p.strip() for p in a.providers.split(",")]

    wl = json.loads(WORKLIST.read_text(encoding="utf-8"))
    holds = [x for x in wl.get("items", []) if x.get("field") == "chain_type"]
    prog = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    done = set(prog.get("promoted_evidence", [])) | set(prog.get("scale_pending", [])) \
        | set(prog.get("capital_pending", [])) | set(prog.get("none", []))
    todo = [x for x in holds if x["rid"] not in done]
    if a.limit:
        todo = todo[: a.limit]

    buckets = {k: list(prog.get(k, [])) for k in
               ("promoted_evidence", "scale_pending", "capital_pending", "none")}
    print(f"[reverify] chain holds={len(holds)} todo={len(todo)} providers={providers}")

    for i, item in enumerate(todo):
        rid, name, asserted = item["rid"], item["name"], item.get("hard_value")
        if asserted == "资本化连锁":
            buckets["capital_pending"].append(rid); tag = "capital_pending(需媒体)"
        else:
            brand = brand_of(name)
            cores = brand_cores(brand)
            have = existing_families(rid)
            scans = map_scan(brand, cores, have, providers)
            ok_scans = [s for s in scans if s["status"] == "ok"]
            tag = "none"
            for s in ok_scans:
                lvl = level_for(s["n"], s["capped"])
                if lvl is None:
                    continue
                if lvl == asserted:
                    if a.apply:
                        append_finding(rid, name, asserted, s)
                    buckets["promoted_evidence"].append(rid)
                    tag = f"promote({s['family']} n={s['n']} {asserted})"; break
                if asserted == "大型连锁" and lvl == "小型连锁":
                    if a.apply:
                        append_finding(rid, name, "小型连锁", s)
                    buckets["scale_pending"].append(rid)
                    tag = f"scale_pending({s['family']} n={s['n']})"; break
                if asserted == "小型连锁" and lvl == "大型连锁":
                    if a.apply:
                        append_finding(rid, name, "大型连锁", s)
                    buckets["scale_pending"].append(rid)
                    tag = f"upgrade_dispute({s['family']} n={s['n']})"; break
            if tag == "none" and not ok_scans:
                statuses = ",".join(f"{s['family']}:{s['status']}" for s in scans)
                tag = f"blocked({statuses})"  # 不落 progress，配额恢复后可重跑
            elif tag == "none":
                buckets["none"].append(rid)
        print(f"  [{i+1}/{len(todo)}] rid{rid} {brand_of(name)[:18]} -> {tag}")
        if a.apply:  # 仅 apply 才落进度；dry-run 不得标记完成（否则漏追加）
            prog.update({k: sorted(set(v)) for k, v in buckets.items()})
            prog["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            PROGRESS.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n=== 汇总 ===")
    for k in ("promoted_evidence", "scale_pending", "capital_pending", "none"):
        print(f"  {k}: {len(set(buckets[k]))}")
    print("(apply=%s)" % a.apply)


if __name__ == "__main__":
    main()

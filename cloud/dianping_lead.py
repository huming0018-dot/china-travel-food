#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dianping_lead.py — 「点评公开榜单 → 候选」合规引线器（不碰点评反爬）。

输入：dianping_seed.json（agent 从公开转载页 OCR/整理出的榜单店名 + source_url）。
处理（确定性）：
  1) 逐名高德 POI 验真（amap_search），只接受 typecode 以 05 开头的餐饮 POI、名称相似度≥0.7，
     分支名（人民广场店等）用于选对分店；
  2) 与现有 restaurants 比对：已在库 → 记录（榜单对账），全新 → 进候选；
  3) 按 poi_id / 品牌核心去重；产出 dianping_lead_fill.json（与 kol_lead_fill 同 schema），
     供 candidate_verify 做真实食客口味核验。
发现新转载页 → 整理店名补进 dianping_seed.json（信源沉淀，A4）。

用法（主机，先 set -a && . ./fill.env && set +a）：
  python3 dianping_lead.py --max-check 40            # 验真并落候选
  python3 dianping_lead.py                           # 离线看种子数
"""
import argparse
import difflib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), str(HERE / "vendor" / "pipeline"), "/app/pipeline"):
    if p not in sys.path:
        sys.path.insert(0, p)

import map_helpers as MH  # noqa: E402
import common as C       # noqa: E402

SEED_F = HERE / "dianping_seed.json"
OUT_F = HERE / "dianping_lead_fill.json"
STATE_F = HERE / "dianping_lead_state.json"

SIM_MIN = 0.70


def core_of(name):
    s = re.sub(r"[（(][^）)]*[）)]", "", name)
    s = re.sub(r"(总店|总店\s*)$", "", s)
    return s.strip(" ··-")


def branch_of(name):
    m = re.search(r"[（(]([^）)]+)[）)]", name)
    return m.group(1) if m else ""


def sim(a, b):
    na, nb = C.cjk_norm(a), C.cjk_norm(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return max(0.8, min(len(na), len(nb)) / max(len(na), len(nb)))
    return difflib.SequenceMatcher(None, na, nb).ratio()


def variants(nm, core):
    vs = [nm]
    if core and core != nm:
        vs.append(core)
    cjk = "".join(re.findall(r"[\u4e00-\u9fa5·]+", core)).strip("·")
    lat = " ".join(re.findall(r"[A-Za-z]+", core))
    if cjk and cjk != core:
        vs.append(cjk)
    if lat:
        first = lat.split()[0]
        vs.append(lat if lat != core else first)
        if len(lat.split()) > 1:
            vs.append(first)
    out, seen = [], set()
    for v in vs:
        v = v.strip()
        if v and v not in seen and len(v) >= 2:
            seen.add(v)
            out.append(v)
    return out


def best_poi(nm, core, branch, budget):
    """多查询变体取最佳餐饮 POI；budget 限制高德调用数。返回 (best,score,calls) 或 (None,0,calls)。"""
    pool, calls, seen_id = {}, 0, set()
    for q in variants(nm, core):
        if calls >= budget:
            break
        results = MH.amap_search(q)
        calls += 1
        if isinstance(results, str):
            return None, -1, calls, results
        for r in results or []:
            pid = r.get("id")
            if pid and pid not in seen_id:
                seen_id.add(pid)
                pool[pid] = r
    best, bs = None, 0.0
    for r in pool.values():
        if not str(r.get("typecode", "")).startswith("05"):
            continue
        s = max(sim(nm, r.get("title", "")), sim(core, r.get("title", "")))
        if branch:
            bt = C.cjk_norm(branch)
            if bt and (bt in C.cjk_norm(r.get("title", "")) or bt in C.cjk_norm(r.get("address", ""))):
                s += 0.15
        if s > bs:
            best, bs = r, s
    if best and bs >= SIM_MIN:
        return best, bs, calls, None
    return None, 0, calls, None


def district_of(addr):
    m = re.search(r"([\u4e00-\u9fa5]{2,4}区)", addr or "")
    return m.group(1) if m else ""


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"verified": {}, "checked": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-check", type=int, default=40)
    args = ap.parse_args()

    seed = json.loads(SEED_F.read_text(encoding="utf-8"))
    names = seed["shops"]
    st = load_state()
    if not sys.argv[1:]:
        print(f"种子 {len(names)} 家；--max-check 验真。source: {seed.get('source_url')}")
        return

    existing = C.fetch_all("restaurants", "id,name,address")
    ex_core = [(C.cjk_norm(core_of(r["name"])), C.addr_core(r.get("address") or ""), r["id"])
               for r in existing]

    out = []
    if OUT_F.exists():
        out = json.loads(OUT_F.read_text(encoding="utf-8"))
    seen_poi = {x.get("poi_id") for x in out}
    seen_core = {C.cjk_norm(x["core"]) for x in out}

    in_db, no_poi, added = [], [], []
    checks = 0
    for nm in names:
        core, branch = core_of(nm), branch_of(nm)
        cnorm = C.cjk_norm(core)
        # 已在库（按核心名）
        hit = next((e for e in ex_core if e[0] and (e[0] == cnorm or cnorm in e[0] or e[0] in cnorm)), None)
        if hit:
            in_db.append({"name": nm, "existing_id": hit[2]})
            continue
        if cnorm in seen_core:
            continue
        if checks >= args.max_check:
            break
        best, bs, used, err = best_poi(nm, core, branch, args.max_check - checks)
        checks += used
        st["checked"] = st["checked"] + used
        if err:  # QUOTA_EXCEEDED
            print("停止：", err)
            break
        if not best:
            no_poi.append(nm)
            continue
        if best.get("id") in seen_poi:
            continue
        rec = {
            "name": best.get("title"), "core": core, "raw_variants": [nm],
            "address": best.get("address", ""), "tel": best.get("tel", ""),
            "lng": best.get("lng"), "lat": best.get("lat"),
            "poi_id": best.get("id"), "grade": "必吃榜2026",
            "independent_kol_voices": 1, "source": "dianping_public_list",
            "signature_hints": [], "district": district_of(best.get("address", "")),
            "typecode": best.get("typecode"),
        }
        out.append(rec)
        seen_poi.add(best.get("id"))
        seen_core.add(cnorm)
        added.append(best.get("title"))
        st["verified"][nm] = {"poi_id": best.get("id"), "sim": round(bs, 2)}

    OUT_F.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"新增候选 {len(added)}；已在库 {len(in_db)}；无匹配 {len(no_poi)}；本轮高德查询 {checks}")
    print("新增：", json.dumps(added, ensure_ascii=False))
    if no_poi:
        print("无匹配：", json.dumps(no_poi, ensure_ascii=False))


if __name__ == "__main__":
    main()

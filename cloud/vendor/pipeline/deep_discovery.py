#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deep_discovery.py — 深覆盖执行器（消费 discovery_plan，多平台汇聚统一 frontier）。

架构：发现广撒网 → 统一 frontier 池 → 独立真实声音校验(admission_gate) → 收录。
本模块先落地最稳的「高德 map 地毯通道」：
  对每个缺口叶子的 map 查询跑高德 place/text（多 key 池），把 POI 归一并入 frontier，
  与在营店做名称/地址匹配，标注 matched / new / ambiguous 与连锁嫌疑。
  地图仅 1 个平台声音，**不直接收录**，只建池；社交/评论 collector（下一模块）进同一池
  补足独立声音后才会 admit（宁空不假）。

frontier: /app/data/coverage/frontier.json
  key=cjk_norm(name) -> {name, aliases, address, tel, lng, lat, sources, hits,
                         cuisines:[cid...], matched_rid, status, chain_suspect}

用法：
  python3 deep_discovery.py --batch 12                 # 处理前12个优先级叶子（map）
  python3 deep_discovery.py --batch 12 --apply         # 落盘 frontier
  python3 deep_discovery.py --leaf 264 --apply         # 只处理某叶子
"""
import argparse
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")

import common as C
import map_helpers as M

COVDIR = pathlib.Path("/app/data/coverage")
PLAN_F = COVDIR / "discovery_plan.json"
FRONT_F = COVDIR / "frontier.json"

# 连锁/工业化品牌启发（仅标注，不删除；最终以 softad 模块为准）
CHAIN_HINT = re.compile(
    r"(连锁|加盟|总店|分店|公司|集团|肯德基|麦当劳|星巴克|瑞幸|库迪|必胜客|华莱士|杨国福|"
    r"张亮|沙县|吉野家|食其家|松屋|汉堡王|德克士|小菜园|望湘园|绿茶|外婆家|西贝|海底捞)")
_RE_BRANCH = re.compile(r"[(（【][^)）]*?(店|分店|旗舰店|直营店)[)）]?$")


def strip_branch(name):
    return _RE_BRANCH.sub("", name).strip()


def load_frontier():
    if FRONT_F.exists():
        return json.loads(FRONT_F.read_text(encoding="utf-8"))
    return {}


def existing_index():
    rows = C.fetch_all("restaurants", select="id,name,address,status", order_col="id")
    by_name, by_base, by_addr = {}, {}, {}
    for r in rows:
        if r.get("status") != "active":
            continue
        nm, addr = r["name"], r.get("address") or ""
        by_name[C.cjk_norm(nm)] = r["id"]
        b = C.cjk_norm(strip_branch(nm))
        if b:
            by_base.setdefault(b, r["id"])
        ac = C.addr_core(addr)
        if ac:
            by_addr.setdefault(ac, r["id"])
    return by_name, by_base, by_addr


def match_poi(poi, idx):
    by_name, by_base, by_addr = idx
    k = C.cjk_norm(poi["title"])
    if k in by_name:
        return by_name[k], "matched"
    b = C.cjk_norm(strip_branch(poi["title"]))
    if b and b in by_base:
        return by_base[b], "matched"
    ac = C.addr_core(poi.get("address") or "")
    if ac and ac in by_addr:
        return by_addr[ac], "ambiguous"
    return None, "new"


# 日式拉面标记 vs 非日式 generic 面
JP_MARK = re.compile(r"(豚骨|酱油|味噌|二郎|家系|博多|熊本|纪州|横滨|蘸面|乌冬|荞麦|一幸舍|"
                     r"一风堂|面屋|屯京|大胜轩|鸣龙|日式|板前|居酒屋|日式拉面|tsukemen|ramen|udon|soba)")
NON_JP_NOODLE = re.compile(r"(兰州拉面|兰州牛肉面|牛肉拉面|河南.{0,3}拉面|清真|沙县|撒拉|青海)")


def relevant(poi, bundle):
    """菜系相关性：日料叶子排除 generic 非日式面（除非带日式标记）。"""
    root = bundle["lineage"][0] if bundle.get("lineage") else ""
    title = poi["title"]
    if ("日料" in root or "日本" in root) and NON_JP_NOODLE.search(title) \
            and not JP_MARK.search(title):
        return False
    return True


def collect_map(bundle):
    """高德地毯：返回去重后的 POI 列表。"""
    out, seen = [], set()
    for q in bundle["queries"]["map"]:
        r = M.amap_search(q, offset=15)
        if r == "QUOTA_EXCEEDED":
            print("  [map] 高德配额全部耗尽，停止")
            return out, True
        time.sleep(0.15)
        for p in r:
            key = (C.cjk_norm(p["title"]),
                   (round(p["lng"], 5) if p["lng"] else None,
                    round(p["lat"], 5) if p["lat"] else None))
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out, False


def upsert(frontier, poi, cid, idx):
    k = C.cjk_norm(poi["title"])
    rid, status = match_poi(poi, idx)
    chain = bool(CHAIN_HINT.search(poi["title"]))
    if k in frontier:
        e = frontier[k]
        e["hits"] += 1
        if cid not in e["cuisines"]:
            e["cuisines"].append(cid)
        if not e.get("matched_rid") and rid:
            e["matched_rid"] = rid; e["status"] = status
        if poi["title"] not in e["aliases"]:
            e["aliases"].append(poi["title"])
        return None
    frontier[k] = {
        "name": poi["title"], "aliases": [], "address": poi.get("address"),
        "tel": poi.get("tel"), "lng": poi.get("lng"), "lat": poi.get("lat"),
        "sources": ["amap"], "hits": 1, "cuisines": [cid],
        "matched_rid": rid, "status": status, "chain_suspect": chain,
    }
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--leaf", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
    if args.leaf:
        bundles = [b for b in bundles if b["id"] == args.leaf]
    else:
        bundles = bundles[:args.batch]

    idx = existing_index()
    frontier = load_frontier()
    quota_dead = False
    for b in bundles:
        pois, quota_dead = collect_map(b)
        cnt = collections_counter = {"new": 0, "matched": 0, "ambiguous": 0}
        skipped = 0
        for p in pois:
            if not relevant(p, b):
                skipped += 1
                continue
            st = upsert(frontier, p, b["id"], idx)
            if st:
                cnt[st] += 1
        print(f"  {b['id']:>3} {b['name']:<16} POI {len(pois):>2}  "
              f"new {cnt['new']} matched {cnt['matched']} ambig {cnt['ambiguous']} off {skipped}")
        if quota_dead:
            break

    new = [e for e in frontier.values() if e["status"] == "new"]
    new_ind = [e for e in new if not e["chain_suspect"]]
    print(f"\nfrontier 总数 {len(frontier)}；new {len(new)}（其中非连锁候选 {len(new_ind)}）；"
          f"matched {sum(1 for e in frontier.values() if e['status']=='matched')}")
    print("== 抽样：非连锁新候选（待社交声音校验）==")
    for e in new_ind[:15]:
        print(f"  {e['name']:<20} {e['address']}")

    if args.apply:
        COVDIR.mkdir(parents=True, exist_ok=True)
        FRONT_F.write_text(json.dumps(frontier, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print(f"\nsaved frontier -> {FRONT_F}")
    if quota_dead:
        print("\n[!] 高德配额耗尽，剩余叶子次日继续。")


if __name__ == "__main__":
    main()

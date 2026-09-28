#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_matrix.py — 上海「好吃店」目标全集 × 多独立抽样框 覆盖矩阵（P1，只读）。

北极星 P1：先定义目标全集（分母）与多个相互独立抽样框，缺口可计算、可复现，
不靠关键词碰运气。本脚本把已有账本/榜单/地图池/社交状态聚合成一张矩阵：

  F2 权威框   米其林(主列表153 + sitemap156对账) / 黑珍珠(待建)
  F5 地图框   高德 POI frontier（单平台声音，只建池不收录）
  F4 社交框   账本叶子 empty/shallow/thin/ok/rich + 账号健康
  F1 地理框   行政区在营店分布（稀疏区=地理漏采）
  F6 滚雪球   frontier 图遍历节点数

只读，不写库；--save 落 /app/data/coverage/coverage_matrix.json 供审计。
口径：米其林用 authority_sitemap.make_matcher 权威四态匹配（非粗糙子串），避免把
唐阁/甬府/福10xx/言盐这类命名漂移误报为缺失。
"""
import argparse
import collections
import json
import pathlib
import sys
import time

HERE = pathlib.Path("/app/cloud")
PIPE = "/app/pipeline"
DATA = pathlib.Path("/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C  # noqa: E402
import authority_sitemap as S  # noqa: E402


def frame_authority_michelin():
    """F2a 米其林权威框：主列表 153 与库内做权威四态对账。"""
    p = pathlib.Path(DATA) / "michelin_shanghai.json"
    if not p.exists():
        return {"frame": "F2a 米其林", "denominator": 0, "note": "michelin_shanghai.json 不存在"}
    mic = json.loads(p.read_text(encoding="utf-8"))
    rests = C.fetch_all("restaurants", "id,name,name_en,status", order_col="id")
    matcher = S.make_matcher(rests)
    rows = []
    for m in mic:
        name = m.get("name", "")
        aliases = [S.core(name)]
        if m.get("slug"):
            aliases += list(S.slug_brand_cores(m["slug"]))
        mm, conf = matcher(aliases)
        rows.append({"name": name, "conf": conf,
                     "matched_id": mm["id"] if mm else None})
    by = collections.Counter(r["conf"] for r in rows)
    in_db = by.get("exact", 0) + by.get("strong", 0)
    uncertain = by.get("weak", 0) + by.get("short", 0)
    missing = by.get("none", 0)
    return {
        "frame": "F2a 米其林主列表",
        "denominator": len(mic),
        "in_db_exact_strong": in_db,
        "uncertain_weak_short": uncertain,
        "true_missing_none": missing,
        "recall_pct": round(in_db * 100 / max(1, len(mic)), 1),
        "conf_dist": dict(by),
        "true_missing_names": [r["name"] for r in rows if r["conf"] == "none"],
        "note": "exact/strong=在库；weak/short=待人工(命名漂移)；none=真缺。官方口径156，sitemap对账见 authority_sitemap",
    }


def frame_blackpearl():
    """F2b 黑珍珠权威框：读 cloud_blackpearl_collect.py 产物（官方全量 + 四态对账）。"""
    p = pathlib.Path(DATA) / "blackpearl_reconcile.json"
    if not p.exists():
        return {"frame": "F2b 黑珍珠", "denominator": 0,
                "note": "blackpearl_reconcile.json 不存在；先跑 cloud_blackpearl_collect.py"}
    r = json.loads(p.read_text(encoding="utf-8"))
    cd = r.get("conf_dist", {})
    denom = r.get("official_totalCount") or r.get("collected") or 0
    in_db = r.get("in_db_exact_strong",
                  cd.get("exact", 0) + cd.get("strong", 0))
    missing = r.get("missing", [])
    return {
        "frame": "F2b 黑珍珠(上海)",
        "denominator": denom,
        "official_shopCount": r.get("official_shopCount"),
        "collected": r.get("collected"),
        "in_db_exact_strong": in_db,
        "conf_dist": cd,
        "true_missing_none": len(missing),
        "recall_pct": round(in_db * 100 / max(1, denom), 1),
        "tagged_total_after": r.get("tagged_total_after"),
        "tag_added_this_run": r.get("tag_added_this_run"),
        "true_missing_names": [m["name"] for m in missing],
        "note": "官方双口径对账(shopCount=totalCount=61)；exact/strong=在库已挂160；"
                "none=真缺(含同名异址分店错配排除)，交 admission_gate 补录；不 detag 历史宽口径",
    }


def frame_map_frontier():
    f = pathlib.Path(DATA) / "coverage" / "frontier.json"
    if not f.exists():
        return {"frame": "F5 地图POI", "denominator": 0}
    fr = json.loads(f.read_text(encoding="utf-8"))
    by = collections.Counter(e.get("status") for e in fr.values())
    nonchain_new = [e for e in fr.values()
                    if e.get("status") == "new" and not e.get("chain_suspect")]
    return {
        "frame": "F5 高德POI frontier",
        "pool_total": len(fr),
        "status_dist": dict(by),
        "new_single_voice_awaiting_second": len(nonchain_new),
        "note": "地图单平台声音只建池；需≥2 独立声音(社交/评论区)才进 admission_gate，当前 hits 多=1，正确地未收录",
    }


def frame_social_ledger():
    led = json.loads(pathlib.Path(DATA, "coverage", "ledger.json").read_text(encoding="utf-8"))
    leaves = [r for r in led if r.get("leaf")]
    by = collections.Counter(r.get("status") for r in leaves)
    target_sum = sum(r.get("target_n", 0) for r in leaves)
    active_sum = sum(r.get("n_active", 0) for r in leaves)  # 会重复，仅作规模感
    # 账号健康
    try:
        import xhs_cookie_pool as pool
        s = pool.summary() or {}
        accts = {k: v.get("status") for k, v in s.items() if isinstance(v, dict)}
    except Exception:
        accts = {}
    alive = [a for a, st in accts.items() if st == "ok"]
    return {
        "frame": "F4 社交发现（账本叶子）",
        "leaf_total": len(leaves),
        "leaf_status": dict(by),
        "gap_leaves_empty_shallow": by.get("empty", 0) + by.get("shallow", 0),
        "thin_leaves": by.get("thin", 0),
        "target_sum(叶级,会重复)": target_sum,
        "xhs_accounts": accts,
        "xhs_alive": alive,
        "note": "empty+shallow=地毯计划缺口叶(129 bundle)；账号全 -100 时 F4 停摆",
    }


def frame_geo():
    rows = C.fetch_all("restaurants", "id,district,status", order_col="id")
    act = [r for r in rows if r.get("status") == "active"]
    by = collections.Counter((r.get("district") or "(空)") for r in act)
    # 脏名：以"海市"开头=缺"上"
    dirty = {d: n for d, n in by.items() if d.startswith("海市")}
    clean = {d: n for d, n in by.items() if not d.startswith("海市")}
    sparse = sorted([(d, n) for d, n in clean.items() if n < 20], key=lambda x: x[1])
    return {
        "frame": "F1 行政区格网",
        "active_total": len(act),
        "district_dist": dict(sorted(clean.items(), key=lambda x: -x[1])),
        "sparse_districts_lt20": sparse,
        "dirty_district_names": dirty,
        "note": "稀疏区(宝山/松江/青浦/嘉定)是地理框漏采候选；'海市X区'为历史脏名(缺'上')，登记不修",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    frames = [
        frame_authority_michelin(),
        frame_blackpearl(),
        frame_map_frontier(),
        frame_social_ledger(),
        frame_geo(),
    ]
    print("=" * 90)
    print("上海「好吃店」多独立抽样框 覆盖矩阵（只读 / dry-run）")
    print("=" * 90)
    for fr in frames:
        print(f"\n■ {fr['frame']}")
        for k, v in fr.items():
            if k in ("frame", "true_missing_names"):
                continue
            s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            print(f"    {k:<28} {s[:120]}")
        if fr.get("true_missing_names"):
            print(f"    真缺(none) {len(fr['true_missing_names'])} 家: "
                  + "、".join(fr["true_missing_names"][:20]))

    if args.save:
        out = pathlib.Path(DATA) / "coverage" / "coverage_matrix.json"
        out.write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写 {out}")
    else:
        print("\n(dry-run；加 --save 写 coverage_matrix.json)")


if __name__ == "__main__":
    main()

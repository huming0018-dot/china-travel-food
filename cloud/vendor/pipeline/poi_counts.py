#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""poi_counts.py — 为每个菜系叶子采集「上海在营 POI 总数」（数据驱动覆盖分母）。

为什么存在：coverage_ledger 的 expected_supply 最初只能靠启发式；本模块对每个叶子用
高德 place/text（offset=1，只读返回的 count 总数，1 次调用/叶子），产出 leaf_id -> n_poi，
喂给 coverage_ledger --poi-counts，让分母从“拍脑袋”变为真实供给。

省配额：offset=1、extensions=base；多 key 池轮换；结果落盘即存（断点续跑）；
任一 key 日配额耗尽自动换，全耗尽则停止、次日续。
输出：/app/data/coverage/poi_counts.json
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")

import common as C          # noqa: E402
import map_helpers as M     # noqa: E402

COVDIR = pathlib.Path("/app/data/coverage")
OUT_F = COVDIR / "poi_counts.json"


def leaf_keyword(name):
    """把叶子名转成高德关键词：含「·」取末段（如 拉面·博多豚骨→博多豚骨）。"""
    t = str(name)
    if "·" in t:
        t = t.split("·")[-1]
    return t.strip()


def load_out():
    try:
        return {int(k): v for k, v in
                json.loads(OUT_F.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def save_out(d):
    COVDIR.mkdir(parents=True, exist_ok=True)
    OUT_F.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    cuisines = C.fetch_all("cuisines", order_col="id")
    by_id = {x["id"]: x for x in cuisines}
    import collections
    children = collections.defaultdict(list)
    for x in cuisines:
        p = x.get("parent_category")
        if isinstance(p, int) and p in by_id:
            children[p].append(x["id"])
        elif isinstance(p, str) and p.isdigit() and int(p) in by_id:
            children[int(p)].append(x["id"])
    leaves = sorted(x["id"] for x in cuisines if not children.get(x["id"]))

    out = load_out()
    todo = [c for c in leaves if c not in out]
    print(f"叶子 {len(leaves)}，已采集 {len(out)}，本轮待跑 {len(todo)}")

    quota_dead = False
    for n, cid in enumerate(todo, 1):
        kw = leaf_keyword(by_id[cid]["name"])
        j, st = M._amap_get("/v3/place/text", {
            "keywords": kw, "city": "上海", "citylimit": "true",
            "offset": 1, "extensions": "base"})
        if st == "quota":
            print("高德全部 key 配额耗尽，停止；次日续跑。")
            quota_dead = True
            break
        if st == "ok":
            try:
                out[cid] = int(j.get("count", "0"))
            except (TypeError, ValueError):
                out[cid] = 0
        else:
            out[cid] = 0
        if n % 20 == 0:
            save_out(out)
            print(f"  …{n}/{len(todo)}（已存 {len(out)}）")
        time.sleep(0.12)

    save_out(out)
    vals = list(out.values())
    print(f"\n完成：已采集 {len(out)}/{len(leaves)}；POI=0 的叶子 {sum(1 for v in vals if v==0)}；"
          f"中位数≈{sorted(vals)[len(vals)//2] if vals else 0}；quota_dead={quota_dead}")


if __name__ == "__main__":
    main()

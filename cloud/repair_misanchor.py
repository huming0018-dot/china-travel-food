#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repair_misanchor.py — 修复错挂：清错误 rid + 改挂正确 rid。dry 默认，--apply 写库。

错挂判定（人工据 evidence 核定，品牌关键词用于定位正确 rid）：
"""
import argparse, json, pathlib, sys
from collections import defaultdict
sys.path.insert(0, "/app/cloud")
import common_core as core

# (bad_rid, field, [正确品牌关键词...], 待改挂的值取自 findings 该(bad_rid,field))
SPEC = [
    (42,  "price_avg",    ["鮨一", "鮨 一"]),
    (489, "price_avg",    ["小杨生煎"]),
    (464, "investor_info", ["孔乙己"]),
    (495, "investor_info", ["德兴馆"]),
    (1116, "investor_info", ["克芮旺斯", "CRAZYONES"]),
    (1135, "investor_info", ["沃夫冈", "Wolfgang"]),
    (1136, "investor_info", ["皮氏", "Peet", "PEET"]),
    (1138, "investor_info", ["茵赫", "Manner", "MANNER"]),
    (1139, "investor_info", ["西舍", "Seesaw", "SEESAW"]),
    (1141, "investor_info", ["蓝瓶", "Blue Bottle", "BLUE"]),
    (1123, "investor_info", ["Da Vittorio", "哒伊沃", "Vittorio"]),
]
LED = pathlib.Path("/app/data/post_record")


def cjk(s):
    return core.pipeline_common().cjk_norm(s or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    findings = [json.loads(l) for l in (LED / "findings.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    def value_for(rid, fld):
        vals = [d for d in findings if d.get("restaurant_id") == rid and d.get("field") == fld]
        if not vals:
            return None
        if fld == "price_avg":
            v = max((d.get("value") for d in vals), key=lambda x: d_conf(vals, x))
            return int(round(v))
        return (sorted(vals, key=lambda d: -float(d.get("confidence") or 0))[0].get("value") or "")[:200]

    rests = core.fetch_all("restaurants", "id,name,price_avg,investor_info")
    name = {r["id"]: r["name"] for r in rests}

    plan_clear, plan_route, no_target = [], [], []
    for bad, fld, kws in SPEC:
        val = value_for(bad, fld)
        plan_clear.append((bad, fld, name.get(bad, "?")))
        # 定位正确 rid：店名含品牌关键词
        targets = []
        for r in rests:
            rn = r["name"]
            if any(k in rn for k in kws):
                targets.append(r["id"])
        if not targets:
            no_target.append((bad, fld, kws, val))
            continue
        for t in targets:
            cur_v = rget(rests, t, fld)
            if cur_v in (None, "", 0) or cur_v != val:
                plan_route.append((t, fld, val, name.get(t, "?"), cur_v))

    print("=== A. 清除错误 rid（字段回 null）===")
    for rid, fld, nm in plan_clear:
        print(f"  rid{rid}「{nm[:22]}」 {fld} -> null")
    print("\n=== B. 改挂到正确 rid ===")
    seen = set()
    for rid, fld, val, nm, cur in plan_route:
        k = (rid, fld)
        if k in seen:
            continue
        seen.add(k)
        print(f"  rid{rid}「{nm[:22]}」 {fld} = {str(val)[:55]} (现:{str(cur)[:20]})")
    print("\n=== C. 未找到正确 rid（值存 pending，不丢）===")
    for bad, fld, kws, val in no_target:
        print(f"  原rid{bad} {fld} 关键词{kws} 值:{str(val)[:50]}")

    if not args.apply:
        print("\n[DRY] 加 --apply 执行；price 清除项进补价清单")
        return

    done_clear = done_route = 0
    for rid, fld, nm in plan_clear:
        r = core.req("PATCH", f"/restaurants?id=eq.{rid}", json={fld: None})
        if r.status_code in (200, 204):
            done_clear += 1
        else:
            print("clear fail", rid, r.status_code, r.text[:120])
    for rid, fld, val, nm, cur in plan_route:
        r = core.req("PATCH", f"/restaurants?id=eq.{rid}", json={fld: val})
        if r.status_code in (200, 204):
            done_route += 1
        else:
            print("route fail", rid, r.status_code, r.text[:120])
    # 未定位的值落 pending
    pend_p = LED / "misanchor_pending_reroute.json"
    pend_p.write_text(json.dumps([{"from_rid": b, "field": f, "keywords": k, "value": v}
                                 for b, f, k, v in no_target], ensure_ascii=False, indent=1),
                      encoding="utf-8")
    # 被清空 price 的店进补价清单
    rp = LED / "reprice_worklist.json"
    rp.write_text(json.dumps([{"rid": b, "name": name.get(b)} for b, f, _ in plan_clear
                              if f == "price_avg"], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    print(f"\n[APPLY] 清除 {done_clear} 字段；改挂 {done_route}；pending {len(no_target)}")
    print("REPAIR_DONE")


def rget(rests, rid, fld):
    for r in rests:
        if r["id"] == rid:
            return r.get(fld)
    return None


def d_conf(vals, x):
    for d in vals:
        if d.get("value") == x:
            return float(d.get("confidence") or 0)
    return 0


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage3_upsert.py — 幂等写库（默认 dry-run，绝不默认改库）

用法：
  python3 stage3_upsert.py -i plan.json                 # 预演，只打印将执行的写操作
  python3 stage3_upsert.py -i plan.json --commit        # 真正写入 + 逐条回读
  python3 stage3_upsert.py -i plan.json --commit --force-conflicts   # 冲突也按 update 写（谨慎）

规则（见 supabase-write-runbook.md 与 db/migrations/002_harden.sql）：
- 新店 POST 不带 id，Prefer: return=representation 拿 id；老店逐行 PATCH（不用批量 upsert，避免 PGRST102）。
- restaurant_cuisines 先 GET 查重，再逐条补；默认只增不删，防止误摘标签。
- location 只写 EWKT 字符串 `SRID=4326;POINT(lng lat)`（实测 GeoJSON 对象会 500）；写后必须 GET 回读，return ok ≠ 结果正确。
- 派生列 tier / score_total / search_vector / updated_at 由数据库触发器计算，plan.fields 不应包含；
  非法 status / 评分 / 坐标 / 招牌菜会被 CHECK 约束直接拒绝（写失败回 stage1 修数据，不可绕过）。
"""
import argparse
import json
import pathlib
import re
import sys
import time

import common as C


def _core(s):
    """品牌核心名（去分店括号后缀），用于同店异写/分店锚定时的回读比对。"""
    return C.norm_name(re.split(r"[（(]", str(s))[0])


def existing_cids(rid):
    r = C.req("GET", f"/restaurant_cuisines?select=cuisine_id&restaurant_id=eq.{rid}")
    r.raise_for_status()
    return {x["cuisine_id"] for x in r.json()}


def write_one(p, force_conflicts):
    name, action, rid = p["name"], p["action"], p.get("restaurant_id")
    fields = dict(p["fields"])
    # 防御：location 若是 GeoJSON dict，统一转成本库可写的 EWKT（GeoJSON 对象直写会 500）
    _loc = fields.get("location")
    if isinstance(_loc, dict) and _loc.get("coordinates"):
        fields["location"] = C.point_ewkt(_loc["coordinates"][0], _loc["coordinates"][1])
    if action == "conflict" and not force_conflicts:
        return {"name": name, "action": "skipped_conflict", "ok": False}

    if action == "new":
        r = C.req("POST", "/restaurants",
                  params={"select": "id,name,status,location"},
                  json=fields)
        rid = None
        if r.status_code in (200, 201):
            try:
                data = r.json()
                if data:
                    rid = data[0]["id"] if isinstance(data, list) else data["id"]
            except ValueError:
                rid = None  # PostgREST 未返回 body（缺 Prefer），改为回查
        is_dup = r.status_code == 409 or "23505" in r.text
        if rid is None and (r.status_code in (200, 201) or is_dup):
            time.sleep(0.3)  # 按店名+地址回查新建行（同名异址连锁需带地址区分）
            q = {"name": f"eq.{fields['name']}", "select": "id,name,address",
                 "order": "id.desc", "limit": "1"}
            if fields.get("address"):
                q["address"] = f"eq.{fields['address']}"
            got = C.req("GET", "/restaurants", params=q).json()
            if got:
                rid = got[0]["id"]
        if rid is None:
            return {"name": name, "action": action, "ok": False,
                    "error": f"POST {r.status_code} 且回查无id: {r.text[:160]}"}
    else:  # update / conflict(force)
        r = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                  params={"select": "id,name,status,location"}, json=fields)
        if r.status_code not in (200, 201, 204):
            return {"name": name, "action": action, "rid": rid, "ok": False, "error": r.text[:200]}

    # RC 去重后逐条补
    have = existing_cids(rid)
    added = []
    for cid in p.get("cids_add", []):
        if cid in have:
            continue
        rr = C.req("POST", "/restaurant_cuisines", json={"restaurant_id": rid, "cuisine_id": cid})
        if rr.status_code in (200, 201):
            added.append(cid)
        elif "23505" in rr.text:  # 唯一冲突=已存在，忽略
            pass
        else:
            return {"name": name, "action": action, "rid": rid, "ok": False,
                    "error": f"RC {cid}: {rr.text[:160]}"}
        time.sleep(0.05)

    # 回读（含触发器派生列，验证数据库侧确实算好了 tier / score_total）
    rb = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name,status,location,phone,tier,price_avg,"
                      "score_total,score_objective,score_diner,score_taste,score_endorsement")
    rb_rows = rb.json() if rb.status_code == 200 else []
    rc_after = existing_cids(rid)
    derive_ok = True
    if rb_rows:
        row = rb_rows[0]
        if row.get("price_avg") and not row.get("tier"):
            derive_ok = False  # 触发器应按人均算出 tier
        subs = [row.get(k) for k in ("score_objective", "score_diner", "score_taste", "score_endorsement")]
        if all(v is not None for v in subs) and row.get("score_total") is None:
            derive_ok = False  # 四项齐全时触发器应算出 score_total
    ok = bool(rb_rows) and (
        C.norm_name(rb_rows[0]["name"]) == C.norm_name(name)
        or _core(rb_rows[0]["name"]) == _core(name)) and derive_ok
    return {"name": name, "action": action, "rid": rid, "rc_added": added,
            "rc_total": len(rc_after), "location_set": bool(rb_rows and rb_rows[0].get("location")),
            "derive_ok": derive_ok,
            "readback": rb_rows[0] if rb_rows else None, "ok": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", default="plan.json")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--force-conflicts", action="store_true")
    ap.add_argument("--report", default="write_report.json")
    args = ap.parse_args()

    plan = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    if not args.commit:
        n_new = sum(1 for p in plan if p["action"] == "new")
        n_upd = sum(1 for p in plan if p["action"] == "update")
        n_cf = sum(1 for p in plan if p["action"] == "conflict")
        n_amap = sum(1 for p in plan if p.get("needs_amap"))
        n_loc = sum(1 for p in plan if p["fields"].get("location"))
        print(f"【DRY-RUN】新增 {n_new} / 更新 {n_upd} / 冲突 {n_cf} / 待高德坐标 {n_amap}")
        print(f"本次将写坐标 {n_loc} 家。示例：")
        for p in plan[:15]:
            print(f"  [{p['action']}] {p['name']}  tags={p['cids_add']} "
                  f"loc={'Y' if p['fields'].get('location') else '-'} amap={'Y' if p.get('needs_amap') else '-'}")
        print("\n确认无误后加 --commit 写库。")
        return

    results = []
    for i, p in enumerate(plan, 1):
        res = write_one(p, args.force_conflicts)
        results.append(res)
        flag = "✓" if res.get("ok") else ("–" if res.get("action") == "skipped_conflict" else "✗")
        print(f"[{i}/{len(plan)}] {flag} {res['action']} {p['name']} "
              f"rid={res.get('rid')} rc+{len(res.get('rc_added', []))}"
              + (f" ERR={res.get('error')}" if not res.get('ok') and res.get('error') else ""))
        time.sleep(0.15)

    pathlib.Path(args.report).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in results if r.get("ok"))
    skip = sum(1 for r in results if r.get("action") == "skipped_conflict")
    fail = [r for r in results if not r.get("ok") and r.get("action") != "skipped_conflict"]
    print(f"\n写入成功 {ok} / 跳过冲突 {skip} / 失败 {len(fail)}；报告 {args.report}")
    if fail:
        sys.exit(1)


if __name__ == "__main__":
    main()

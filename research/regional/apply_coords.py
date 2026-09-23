#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_coords.py — 把腾讯拾取器采集的坐标（coord_final.json）幂等 PATCH 进 restaurants。

铁律：
- location 只写 EWKT `SRID=4326;POINT(lng lat)`（lng 在前；腾讯回填是 lat,lng，本脚本已分列）。
- 只写 location；phone 仅当库内为空且采集号码通过 clean_phone 合法性校验时补（防退化、防假号）。
- 不覆盖 address / 不写 coord_source（表无此列，来源只留本地 coord_final.json）。
- 写前 GET 全表核对 id->name（防 id 漂移）；写后 GET 回读坐标比对。
- 默认 dry-run；加 --commit 才真正写。

用法：
  FOOD_APP_DIR=<app目录> python3 apply_coords.py            # 预演
  FOOD_APP_DIR=<app目录> python3 apply_coords.py --commit   # 写库 + 回读
"""
import argparse
import json
import os
import pathlib
import sys
import time

SKILL_SCRIPTS = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL_SCRIPTS)
import common as C  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--final", default=str(HERE / "coord_final.json"))
    ap.add_argument("--report", default=str(HERE / "coord_apply_report.json"))
    args = ap.parse_args()

    coords = json.loads(pathlib.Path(args.final).read_text(encoding="utf-8"))
    rests = C.fetch_all("restaurants", "id,name,location,phone,status", order_col="id")
    rmap = {r["id"]: r for r in rests}

    plan, skipped = [], []
    for c in coords:
        rid = c["id"]
        db = rmap.get(rid)
        if not db:
            skipped.append((rid, c["name"], "库中无此 id"))
            continue
        # id 漂移/对错店防护：店名核心需一致（去分店后缀粗比）
        if C.norm_name(db["name"])[:6] != C.norm_name(c["name"])[:6]:
            skipped.append((rid, c["name"], f"库内店名不符: {db['name']}"))
            continue
        lng, lat = float(c["lng"]), float(c["lat"])
        if not C.in_shanghai(lng, lat):
            skipped.append((rid, c["name"], "坐标越界"))
            continue
        fields = {"location": C.point_ewkt(lng, lat)}
        # 电话：库空 + 采集号合法才补；格式对齐库内口径（021-XXXXXXXX / 手机纯11位）
        tel_note = ""
        if not db.get("phone") and c.get("tel"):
            clean, issues, note = C.clean_phone(c["tel"])
            if clean and not any(i == "phone_unparseable" for i in issues):
                def fmt(num):
                    if num.startswith("021") and len(num) == 11:
                        return "021-" + num[3:]
                    if len(num) == 11 and num.startswith("1"):
                        return num
                    return num
                clean = " / ".join(fmt(x) for x in clean.split(" / "))
                fields["phone"] = clean
                tel_note = f" 补电话 {clean}"
                if note:
                    fields["booking_method"] = note
        # 已有相同坐标则跳过
        cur = C.parse_location(db.get("location"))
        if cur and abs(cur[0] - lng) < 1e-6 and abs(cur[1] - lat) < 1e-6:
            continue
        plan.append((rid, c["name"], fields, tel_note))

    print(f"待写坐标 {len(plan)} 家；跳过 {len(skipped)} 家")
    for rid, nm, why in skipped:
        print("  跳过", rid, nm, why)
    if not args.commit:
        for rid, nm, f, note in plan[:15]:
            print("  [dry]", rid, nm, f["location"], note)
        print(f"\nDRY-RUN，共 {len(plan)} 家；确认后加 --commit")
        return

    results = []
    for i, (rid, nm, fields, note) in enumerate(plan, 1):
        r = C.req("PATCH", f"/restaurants?id=eq.{rid}",
                  params={"select": "id,name,location,phone"}, json=fields)
        ok = False
        rb = None
        if r.status_code in (200, 201, 204):
            time.sleep(0.15)
            got = C.req("GET", f"/restaurants?id=eq.{rid}&select=id,name,location,phone").json()
            if got:
                rb = got[0]
                p = C.parse_location(rb.get("location"))
                ok = bool(p) and abs(p[0] - float(fields["location"].split("(")[1].split()[0])) < 1e-5
        results.append({"id": rid, "name": nm, "ok": ok, "fields": list(fields),
                        "readback": (C.parse_location(rb["location"]) if rb else None)})
        print(f"[{i}/{len(plan)}]", "✓" if ok else "✗", rid, nm, note or "",
              "" if ok else f" ERR={r.status_code} {r.text[:120]}")
        time.sleep(0.12)

    pathlib.Path(args.report).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    nok = sum(1 for x in results if x["ok"])
    print(f"\n写入成功 {nok}/{len(plan)}；报告 {args.report}")
    if nok != len(plan):
        sys.exit(1)


if __name__ == "__main__":
    main()

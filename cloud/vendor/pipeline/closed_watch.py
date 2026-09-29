#!/usr/bin/env python3
"""Track 1B-2 关店/迁址周期扫描（只读、确定性、幂等）。

不写库、不改 status、不自动合并。只产出候选清单供人工/后续连接器核证。
按保鲜周期（新店30/高端180/平价连锁90）与 DB 内已有信号，把可疑店分桶：
  A. closed 行三要素审计（status+closed_date+closed_source URL 齐全？）
  B. active 行但 evidence/备注含"关店/停业/闭店/搬迁"信号 → 待核迁址/关店
  C. active 行超过保鲜周期（stale）→ 待复评
  D. active 行无电话且缺坐标 → 待补
证据不足一律转人工，宁空不假。
"""
import sys, os, json, datetime as dt, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/app/data"

# 保鲜周期（与 cloud_patrol.FRESH_SCENE 对齐；高端180，其余按场景）
FRESH_DAYS = {"快餐小吃": 30, "面包": 30, "咖啡茶饮": 30, "甜品": 30,
              "酒吧": 60, "正餐": 90}
HIGH_TIER = ("高档", "奢华")

# active 行 evidence/备注里出现这些词 = 可能关店/迁址信号
CLOSED_SIGNAL = re.compile(r"(关店|停业|闭店|歇业|搬迁|迁址|暂别|结业|撤店|不再营业|已关闭)")
URL_RE = re.compile(r"^https?://")


def _age_days(iso):
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).replace(tzinfo=None)
        return (dt.datetime.now() - t).days
    except Exception:
        return None


def scan(rests=None):
    """返回 dict 候选清单。只读。"""
    if rests is None:
        rests = C.fetch_all("restaurants", "*", order_col="id")

    closed_triple_missing = []   # A
    active_with_closed_signal = []  # B
    stale_active = []            # C
    no_phone_no_coord = []       # D

    for r in rests:
        rid = r["id"]
        status = r.get("status")
        if status == "closed":
            # A. 三要素
            if not (r.get("closed_date") and r.get("closed_source")):
                closed_triple_missing.append(
                    {"id": rid, "name": r.get("name"),
                     "missing": [k for k, v in
                                 [("closed_date", r.get("closed_date")),
                                  ("closed_source", r.get("closed_source"))] if not v]})
            elif not URL_RE.match(str(r.get("closed_source") or "")):
                closed_triple_missing.append(
                    {"id": rid, "name": r.get("name"),
                     "missing": ["closed_source非URL"]})
            continue

        # active 行
        # B. evidence/备注里有关店信号
        blob = " ".join(str(r.get(k) or "") for k in
                        ["evidence_summary", "semantic_description", "business_area", "notes"])
        if CLOSED_SIGNAL.search(blob):
            active_with_closed_signal.append(
                {"id": rid, "name": r.get("name"),
                 "signal": CLOSED_SIGNAL.search(blob).group(0),
                 "addr": r.get("address")})

        # C. stale（超过保鲜周期）
        scene = r.get("price_scene")
        days = FRESH_DAYS.get(scene, 90)
        if r.get("tier") in HIGH_TIER:
            days = 180
        age = _age_days(r.get("data_updated_at") or r.get("updated_at"))
        if age is not None and age > days:
            stale_active.append({"id": rid, "name": r.get("name"),
                                 "age": age, "cycle": days,
                                 "tier": r.get("tier"), "scene": scene})

        # D. 无电话且无坐标
        if not C.clean_phone(r.get("phone"))[0] and not C.parse_location(r.get("location")):
            no_phone_no_coord.append({"id": rid, "name": r.get("name"),
                                      "addr": r.get("address")})

    return {
        "closed_triple_missing": closed_triple_missing,
        "active_with_closed_signal": active_with_closed_signal,
        "stale_active": stale_active,
        "no_phone_no_coord": no_phone_no_coord,
        "totals": {
            "restaurants": len(rests),
            "closed": sum(1 for r in rests if r.get("status") == "closed"),
            "active": sum(1 for r in rests if r.get("status") == "active"),
        },
    }


def run():
    """patrol 调用入口：打印摘要并返回计数。"""
    res = scan()
    t = res["totals"]
    print(f"  关店扫描: closed={t['closed']} active={t['active']}")
    print(f"    closed三要素缺: {len(res['closed_triple_missing'])}")
    print(f"    active带关店信号(待核): {len(res['active_with_closed_signal'])}")
    print(f"    stale超保鲜周期: {len(res['stale_active'])}")
    print(f"    无电话无坐标: {len(res['no_phone_no_coord'])}")
    for x in res["active_with_closed_signal"][:10]:
        print(f"      [信号] id={x['id']} {x['name']!r} 词={x['signal']}")
    for x in res["closed_triple_missing"][:10]:
        print(f"      [三要素缺] id={x['id']} {x['name']!r} {x['missing']}")
    return res


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(DATA, "closed_watch_report.json"))
    args = ap.parse_args()
    print("==== 关店/迁址周期扫描（只读）====")
    res = run()
    json.dump(res, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(f"\n报告写 {args.out}（只读，未改库）")

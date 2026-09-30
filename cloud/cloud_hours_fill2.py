#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_hours_fill2.py — 营业时间/open_days 重补（批次7 增强版）。

设计原则（对齐 agent-hint）：
  * 仅 PATCH opening_hours / open_days 两字段；电话/坐标/评分/地址一律不动。
  * 宁空不假：day 证据不足时 open_days 留空，绝不臆造"周一至周日"。
  * 幂等可重跑：目标筛选本身就是"缺谁补谁"，重跑无副作用。
  * 每条带 source_url 持久账本（append-only jsonl）。

两个 Pass：
  Pass A (od_backfill)：opening_hours={"raw":...} 已有但 open_days 为空（828家）。
      不调外部 API，仅对既有 raw 做确定性解析，补 open_days；opening_hours 原样不动。
  Pass B (amap)      ：opening_hours 与 open_days 双空（547家）。
      高德 POI 查 business(opentime2)，命中后写 opening_hours={"raw":text}（与库内828家同形态）
      + 解析出的 open_days；source_url=https://www.amap.com/place/{poiid}。

用法（容器内）：
  python3 cloud_hours_fill2.py                # dry-run，只打印计划+账本，不写库
  python3 cloud_hours_fill2.py --apply        # 真实 PATCH 并逐行回读
  HOURS_SAMPLE_A=40 HOURS_SAMPLE_B=40 ...     # 有界样本；0=不限制
  HOURS_PASS=A|B                              # 只跑某个 pass
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C  # noqa: E402

LEDGER = pathlib.Path(DATA) / "hours_fill_ledger.jsonl"
DAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_DAY_IDX = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5,
            "周日": 6, "周天": 6}
ALL = {0, 1, 2, 3, 4, 5, 6}


def derive_open_days(raw):
    """严格从 raw 文本推导 open_days。无明确 day 证据 → None（宁空不假）。"""
    if not raw or not isinstance(raw, str):
        return None
    t = raw.strip()
    if ("全天" in t) or ("24小时" in t):
        return "周一至周日"
    # 明确定休日："周二休" / "每周二休息" / "周二店休"
    m = re.search(r"周([一二三四五六日天])\s*(休息|休业|定休|店休|闭店|休)", t)
    if m:
        return f"周{m.group(1).replace('天','日')}休"
    idx = set()
    # ① 区间：周X 至/到/—/–/~ 周?Y（Y 前的“周”常省略，如“周一至周五”）
    for rng in re.finditer(
            r"周([一二三四五六日天])\s*(?:至|到|—|–|~|～)\s*周?([一二三四五六日天])", t):
        a = _DAY_IDX["周" + rng.group(1).replace("天", "日")]
        b = _DAY_IDX["周" + rng.group(2).replace("天", "日")]
        lo, hi = sorted((a, b))
        idx.update(range(lo, hi + 1))
    # ② 单独出现的 周X（如“周一至周四,周日”里的 周日）
    for one in re.finditer(r"周([一二三四五六日天])", t):
        idx.add(_DAY_IDX["周" + one.group(1).replace("天", "日")])
    if not idx:
        return None  # 无任何星期证据
    if idx == ALL:
        return "周一至周日"
    if idx == {0, 1, 2, 3, 4}:
        return "周一至周五"
    if idx == {5, 6}:
        return "仅周末"
    mn, mx = min(idx), max(idx)
    if idx == set(range(mn, mx + 1)):  # 连续区间，如 周二至周六
        return f"{DAYS_CN[mn]}至{DAYS_CN[mx]}"
    return None  # 碎片（如仅周一/周四，或跳日）→ 不猜


def _ledger(row):
    row["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _patch_and_verify(rid, payload, apply):
    if not apply:
        return True
    pr = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=payload)
    if pr.status_code not in (200, 204):
        print(f"    PATCH FAIL {rid}: {pr.status_code} {pr.text[:120]}")
        return False
    time.sleep(0.12)
    g = C.req("GET", f"/restaurants?id=eq.{rid}&select=opening_hours,open_days")
    if g.status_code != 200:
        return True  # 回读失败不阻断，视为写入已发
    got = g.json()[0] if g.json() else {}
    for k, v in payload.items():
        if got.get(k) != v:
            print(f"    回读不一致 {rid}.{k}: want={v!r} got={got.get(k)!r}")
            return False
    return True


def _oh_filled(oh):
    if not isinstance(oh, dict):
        return False
    for v in oh.values():
        if isinstance(v, str) and v.strip():
            return True
        if v:
            return True
    return False


def _od_filled(od):
    return bool(od and isinstance(od, str) and od.strip())


def load_active():
    return C.fetch_all(
        "restaurants",
        "id,name,address,score_total,opening_hours,open_days",
        extra="status=eq.active",
    )


def run_pass_a(rows, sample, apply):
    targets = [r for r in rows
               if isinstance(r.get("opening_hours"), dict)
               and r["opening_hours"].get("raw")
               and not (r.get("open_days") or "").strip()]
    targets.sort(key=lambda r: (-(r.get("score_total") or 0), r["id"]))
    if sample:
        targets = targets[:sample]
    print(f"[PassA od_backfill] 计划处理 {len(targets)} 家（raw有、od空）")
    done = skip = 0
    for r in targets:
        rid, name = r["id"], r["name"]
        raw = r["opening_hours"]["raw"]
        od = derive_open_days(raw)
        if not od:
            skip += 1
            print(f"  [{rid}] {name} → 无明确day证据，留空")
            continue
        ok = _patch_and_verify(rid, {"open_days": od}, apply)
        if ok:
            done += 1
            print(f"  [{rid}] {name} → open_days={od}")
        else:
            skip += 1
        _ledger({"pass": "A_od_backfill", "rid": rid, "name": name,
                 "score": r.get("score_total"), "source": "derived_from_raw",
                 "source_url": "", "raw": raw[:200], "after_open_days": od,
                 "written": bool(ok and apply)})
        time.sleep(0.1)
    print(f"[PassA] 写入 {done} / 留空 {skip}")
    return done, skip


def run_pass_b(rows, sample, apply):
    from map_helpers import amap_search, pick_best
    targets = [r for r in rows
               if not _oh_filled(r.get("opening_hours"))
               and not _od_filled(r.get("open_days"))]
    targets.sort(key=lambda r: (-(r.get("score_total") or 0), r["id"]))
    if sample:
        targets = targets[:sample]
    print(f"[PassB amap] 计划处理 {len(targets)} 家（oh+od 双空）")
    done = skip = nohit = 0
    for r in targets:
        rid, name, addr = r["id"], r["name"], r.get("address", "")
        res = amap_search(name, offset=8)
        if res == "QUOTA_EXCEEDED":
            print(f"  [{rid}] {name} → 高德配额耗尽，停止本pass")
            break
        if not res:
            nohit += 1
            continue
        best, score = pick_best(res, name, addr, name_thresh=0.85)
        if not best or not (best.get("business") or "").strip():
            nohit += 1
            continue
        biz = best["business"].strip()
        od = derive_open_days(biz)
        payload = {"opening_hours": {"raw": biz}}
        if od:
            payload["open_days"] = od
        url = f"https://www.amap.com/place/{best.get('id','')}" if best.get("id") else ""
        ok = _patch_and_verify(rid, payload, apply)
        if ok:
            done += 1
            print(f"  [{rid}] {name} → oh(raw)+od={od}  src={url}")
        else:
            skip += 1
        _ledger({"pass": "B_amap", "rid": rid, "name": name,
                 "score": r.get("score_total"), "source": "amap",
                 "source_url": url, "raw": biz[:200],
                 "after_open_days": od, "match_score": round(score, 3),
                 "written": bool(ok and apply)})
        time.sleep(0.3)
    print(f"[PassB] 写入 {done} / 失败 {skip} / 无命中 {nohit}")
    return done, skip, nohit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真实写库（默认 dry-run）")
    ap.add_argument("--pass", dest="which", default="", choices=["", "A", "B"])
    args = ap.parse_args()
    sample_a = int(os.environ.get("HOURS_SAMPLE_A", "40"))
    sample_b = int(os.environ.get("HOURS_SAMPLE_B", "40"))

    rows = load_active()
    print(f"active={len(rows)}  mode={'APPLY' if args.apply else 'DRY-RUN'}  "
          f"sampleA={sample_a} sampleB={sample_b}")

    if args.which in ("", "A"):
        run_pass_a(rows, sample_a, args.apply)
    if args.which in ("", "B"):
        run_pass_b(rows, sample_b, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())

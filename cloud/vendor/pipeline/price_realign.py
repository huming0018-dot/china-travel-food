#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Align active restaurant prices to approved, fixed scene thresholds.

price_band_thresholds is the sole range authority (lo inclusive, hi exclusive).
price_position is the corresponding 经济/平价/中端/高端/奢华 label, NOT a
second percentile calculation. Recalibration must be separately reviewed and
applied atomically with affected rows; this script never writes configuration.

Default: read-only. --apply also requires FOOD_PRICE_ALIGNMENT_WRITES_ENABLED=1
after separate approval of the production data changes. It changes only price_band/price_position, guarded by
the original price inputs and values, and verifies every write. A failed or
uncertain write stops with exit 1; earlier verified rows may have committed.
Never automatically retry an uncertain PATCH. Database UPDATE triggers still
run (including updated_at); they are not disabled here.

REST cannot lock threshold reads and restaurant writes in one transaction.
Configuration MUST stay frozen while this runs. Before recalibrating, stop all
price writers and drain in-flight runs; keep them stopped through verification.
Per-row config checks detect drift but are not an atomic concurrency guarantee.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

# Offline plans and --help must not load credentials or HTTP dependencies.
C = None

SCENES = ["正餐", "快餐小吃", "咖啡茶饮", "面包", "甜品", "酒吧"]
POS_LABELS = ["经济", "平价", "中端", "高端", "奢华"]
FIELDS = "id,name,status,price_avg,price_scene,price_band,price_position"
GUARDS = ("id", "status", "price_avg", "price_scene", "price_band", "price_position")


class AlignmentError(ValueError):
    """A safe, contextual error suitable for the scheduler log."""


def validate_thresholds(rows):
    """Require all six scenes, five non-overlapping contiguous bands each."""
    by_scene = {scene: {} for scene in SCENES}
    for row in rows:
        scene, band = row.get("scene"), row.get("band")
        if scene not in by_scene or type(band) is not int or band not in range(1, 6):
            raise AlignmentError("thresholds: unknown scene or invalid band")
        if band in by_scene[scene]:
            raise AlignmentError(f"thresholds: duplicate {scene} band={band}")
        if "lo" not in row or "hi" not in row:
            raise AlignmentError(f"thresholds: missing bound {scene} band={band}")
        for key in ("lo", "hi"):
            value = row[key]
            if value is not None and (type(value) is not int or not 0 <= value <= 100000):
                raise AlignmentError(f"thresholds: invalid {key} {scene} band={band}")
        by_scene[scene][band] = {k: row[k] for k in ("scene", "band", "lo", "hi")}
    normalized = []
    for scene in SCENES:
        bands = by_scene[scene]
        if set(bands) != set(range(1, 6)):
            raise AlignmentError(f"thresholds: missing bands for {scene}")
        previous_hi = None
        for band in range(1, 6):
            row = bands[band]
            lo, hi = row["lo"], row["hi"]
            if lo != previous_hi or (band > 1 and lo is None):
                raise AlignmentError(f"thresholds: gap/overlap {scene} band={band}")
            if (band == 5) != (hi is None):
                raise AlignmentError(f"thresholds: invalid open bound {scene} band={band}")
            if hi is not None and hi <= (lo if lo is not None else 0):
                raise AlignmentError(f"thresholds: empty range {scene} band={band}")
            previous_hi = hi
            normalized.append(row)
    return normalized


def build(restaurants=None, thresholds=None):
    global C
    if C is None and (restaurants is None or thresholds is None):
        import common as C
    if restaurants is None:
        restaurants = C.fetch_all("restaurants", FIELDS, order_col="id")
    if thresholds is None:
        thresholds = C.fetch_all("price_band_thresholds", "scene,band,lo,hi", order_col="scene,band")
    thresholds = validate_thresholds(thresholds)
    changes, skipped, targets, seen = [], [], [], set()
    for row in restaurants:
        if any(key not in row for key in FIELDS.split(",")):
            raise AlignmentError("restaurants: missing required fields")
        rid = row["id"]
        if type(rid) is not int or rid <= 0 or rid in seen:
            raise AlignmentError("restaurants: invalid or duplicate id")
        seen.add(rid)
        if row["status"] != "active":
            continue
        price, scene = row["price_avg"], row["price_scene"]
        if price is None:
            skipped.append({"id": rid, "reason": "missing_price"})
            continue
        if type(price) is not int or not 0 <= price <= 99999:
            raise AlignmentError(f"restaurants: invalid price_avg id={rid}")
        if scene not in SCENES:
            skipped.append({"id": rid, "reason": "unknown_scene"})
            continue
        band = next(t["band"] for t in thresholds if t["scene"] == scene
                    and (t["lo"] is None or price >= t["lo"])
                    and (t["hi"] is None or price < t["hi"]))
        after = {"price_band": band, "price_position": POS_LABELS[band - 1]}
        targets.append({"id": rid, **after})
        if any(row[k] != v for k, v in after.items()):
            changes.append({"id": rid, "name": row["name"],
                            "before": {k: row[k] for k in GUARDS}, "after": after})
    return {"thresholds": thresholds, "changes": changes, "skipped": skipped, "targets": targets}


def check_response(response, stage, rid):
    if response.status_code not in (200, 204):
        code = "unknown"
        try:
            candidate = response.json().get("code", "")
            if isinstance(candidate, str) and re.fullmatch(r"[A-Z0-9]{5,10}", candidate):
                code = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        # Never echo raw response bodies or exception URLs (may contain secrets).
        raise AlignmentError(f"{stage} id={rid}: HTTP {response.status_code} code={code}")


def apply(plan):
    if os.environ.get("FOOD_PRICE_ALIGNMENT_WRITES_ENABLED") != "1":
        raise AlignmentError("WRITE BLOCKED: FOOD_PRICE_ALIGNMENT_WRITES_ENABLED must be explicitly enabled")
    checked = 0
    try:
        for change in plan["changes"]:
            current = C.fetch_all("price_band_thresholds", "scene,band,lo,hi", order_col="scene,band")
            if validate_thresholds(current) != plan["thresholds"]:
                raise AlignmentError("thresholds changed since planning; rerun dry-run")
            rid, before, after = change["id"], change["before"], change["after"]
            query = urlencode({k: "is.null" if v is None else f"eq.{v}" for k, v in before.items()})
            try:
                # common.req otherwise retries writes on 5xx or network failures.
                response = C.req("PATCH", "/restaurants?" + query, json=after, retries=1)
            except Exception as exc:
                raise AlignmentError(f"PATCH id={rid}: uncertain outcome ({type(exc).__name__}); read before retry") from None
            check_response(response, "PATCH", rid)
            response = C.req("GET", f"/restaurants?id=eq.{rid}&select={FIELDS}")
            check_response(response, "readback", rid)
            rows = response.json()
            expected = {**before, **after}
            if not isinstance(rows, list) or len(rows) != 1 or any(rows[0].get(k) != v for k, v in expected.items()):
                raise AlignmentError(f"readback id={rid}: mismatch/missing row; possible concurrent update")
            checked += 1
        verification = build()
        if verification["thresholds"] != plan["thresholds"]:
            raise AlignmentError("thresholds changed during apply; rerun dry-run before further writes")
        if verification["changes"]:
            raise AlignmentError(f"final readback: {len(verification['changes'])} mismatches remain")
    except Exception:
        print(f"[apply ERROR] verified={checked}/{len(plan['changes'])}; stopped, earlier rows may have committed")
        raise
    print(f"[apply OK] verified={checked}/{len(plan['changes'])}; thresholds unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--snapshot", type=Path, help="Offline JSON containing restaurants and thresholds; cannot apply")
    parser.add_argument("--report", type=Path, help="Write a reviewable JSON plan locally")
    args = parser.parse_args()
    if args.apply and args.snapshot:
        parser.error("--snapshot cannot be combined with --apply")
    if args.apply and os.environ.get("FOOD_PRICE_ALIGNMENT_WRITES_ENABLED") != "1":
        print("[WRITE BLOCKED] 价格写入默认关闭；确认数据变更范围后，才可单独启用 FOOD_PRICE_ALIGNMENT_WRITES_ENABLED=1。")
        return 2
    try:
        if args.snapshot:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            plan = build(snapshot["restaurants"], snapshot["thresholds"])
        else:
            plan = build()
        print(f"price alignment: eligible={len(plan['targets'])} changed={len(plan['changes'])} skipped={len(plan['skipped'])}")
        print("position after:", dict(collections.Counter(r["price_position"] for r in plan["targets"])))
        for change in plan["changes"][:25]:
            print(f"  id={change['id']} {change['name']}: {change['after']}")
        for row in plan["skipped"]:
            print(f"  [skip] id={row['id']} {row['reason']}")
        if args.report:
            args.report.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not args.apply:
            print("[dry-run] 未写库；阈值配置只读。--apply 仅对齐餐厅档位。")
            return 0
        print("[apply prerequisite] 阈值须冻结；禁止与阈值重标定并发运行。")
        apply(plan)
        return 0
    except AlignmentError as exc:
        print(f"[ERROR] {exc}")
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: failed; no success claimed (inspect sanitized service logs)")
    return 1


if __name__ == "__main__":
    sys.exit(main())

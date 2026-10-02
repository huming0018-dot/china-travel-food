#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""name_cuisine_link.py — 「店名 / 招牌 → 菜系叶」主身份回填引擎（确定性、幂等、保守）。

为什么存在（治通识问题，非补单店）：
  cuisine_plane_audit 的 W4 发现一批在营店只挂了食材/形式/标签、没有任何 dimension='菜系' 叶
  （如茶馆被挂"下午茶形式"却无菜系身份；港式火锅只挂"火锅食材"）。历史上靠人工逐店补，
  不可复用。本引擎用配置规则把"店名关键词 / 招牌菜证据 → 菜系叶"固化：
    - 只对【当前没有任何菜系叶】的在营店生效（补缺失主身份，绝不重分类已有身份，避免碰撞）；
    - 店名命中=高置信(0.95)；招牌菜命中需满足规则的独立信号数=中置信(0.85)；
    - 部分规则支持"店名含 X 且招牌含 Y"的组合判定；可顺带补形式/标签 tag；
    - 宁空不假：无明确证据不写。dry-run 默认，--apply 才写并回读断言。

用法：
  python3 name_cuisine_link.py
  python3 name_cuisine_link.py --apply
"""
import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", str(HERE / "vendor" / "pipeline"))
for _p in (HERE, PIPE, HERE / "vendor" / "pipeline"):
    if (pathlib.Path(_p) / "common.py").exists():
        sys.path.insert(0, str(_p))
        break
import common as C  # noqa: E402

RULES_PATH = HERE / "name_cuisine_rules.json"


def found(text, kws):
    return [k for k in kws if k in (text or "")]


def build_plan():
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))["rules"]
    cuis = C.fetch_all("cuisines", "id,name,dimension", order_col="id")
    dim_of = {c["id"]: c.get("dimension") for c in cuis}
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    links = {}
    for x in rc:
        links.setdefault(x["restaurant_id"], set()).add(x["cuisine_id"])
    rests = C.fetch_all("restaurants",
                        "id,name,signature_dishes,selling_points,status", order_col="id")

    plan = []  # {rid,name,leaf,conf,rule,extra_tags}
    for r in rests:
        if r.get("status") != "active":
            continue
        cur = links.get(r["id"], set())
        if any(dim_of.get(c) == "菜系" for c in cur):
            continue  # 已有菜系主身份，不动
        name = r["name"] or ""
        def as_str(x):
            if isinstance(x, str):
                return x
            if isinstance(x, dict):
                return " ".join(str(v) for k, v in x.items()
                                if k in ("name", "dish", "title", "text"))
            return str(x)

        sig = [as_str(x) for x in (r.get("signature_dishes") or [])]
        sp = r.get("selling_points")
        sp = [as_str(x) for x in sp] if isinstance(sp, list) else [as_str(sp or "")]
        dish_text = " ".join(sig + sp)
        for rule in rules:
            leaf = rule["leaf"]
            conf, why = 0, ""
            nh = found(name, rule.get("name_any", []))
            if nh:
                conf, why = rule.get("conf_name", 0.95), f"店名命中{nh[:2]}"
            else:
                dh = found(dish_text, rule.get("dish_any", []))
                need = rule.get("dish_min_distinct", 1)
                if len(set(dh)) >= need:
                    conf, why = rule.get("conf_dish", 0.85), f"招牌信号{dh[:3]}"
                else:
                    req = rule.get("dish_require_name_contains")
                    if req and any(q in name for q in req):
                        sh = found(dish_text, rule.get("dish_scoped_any", []))
                        if sh:
                            conf, why = rule.get("conf_dish", 0.85), \
                                f"店名含{req}且招牌{sh[:2]}"
            if not conf:
                continue
            extra = [t for t in rule.get("also_tags", []) if t not in cur]
            plan.append({"rid": r["id"], "name": name, "leaf": leaf, "conf": conf,
                         "rule": rule["id"], "why": why, "extra_tags": extra})
            break  # 一店只回填一个主身份
    return plan


def apply_plan(plan):
    rows = []
    for p in plan:
        rows.append({"restaurant_id": p["rid"], "cuisine_id": p["leaf"],
                     "is_primary": False})
        for t in p["extra_tags"]:
            rows.append({"restaurant_id": p["rid"], "cuisine_id": t,
                         "is_primary": False})
    if not rows:
        return 0
    r = C.req("POST", "/restaurant_cuisines", json=rows)
    if r.status_code not in (200, 201):
        print("[ERROR] POST", r.status_code, r.text[:300])
        return 0
    return len(plan)


def readback(plan):
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    links = {}
    for x in rc:
        links.setdefault(x["restaurant_id"], set()).add(x["cuisine_id"])
    ok = True
    for p in plan:
        if p["leaf"] not in links.get(p["rid"], set()):
            print(f"  [ASSERT FAIL] rid={p['rid']} leaf={p['leaf']}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    plan = build_plan()
    print(f"[{'APPLY' if a.apply else 'DRY-RUN'}] 待回填主身份店数={len(plan)}")
    for p in plan:
        print(f"  #{p['rid']} {p['name'][:26]:28s} ->叶{p['leaf']} conf={p['conf']} "
              f"[{p['rule']}] {p['why']} extra_tags={p['extra_tags']}")
    if not a.apply:
        print("\n[DRY-RUN] 加 --apply 才写库。")
        return
    n = apply_plan(plan)
    if n and readback(plan):
        print(f"\n[APPLIED] 回填 {n} 店主身份，回读断言 PASS")
    elif not n:
        print("\n无写入。")


if __name__ == "__main__":
    main()

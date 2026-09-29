#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signature_cuisine_link.py — W5: 招牌菜→菜系联动引擎（配置驱动）

目标：把"已抓到的招牌菜关键词"真正联动到 restaurant_cuisines，补完现有
signature_dish_classifier 只提词、不写库的缺口。

原则（与 cuisine-classification-engine.md 对齐）：
1. 出品定类，主营挂叶：is=主营(strong/具名裁决)才改/补 restaurant_cuisines；
   serves=含有(菜单里一道)只打标签，不挂菜系叶。
2. 店名/招牌词只作线索；地名/招牌陷阱词典(trap_rules)优先于泛化 dish_rules。
3. 配置驱动：加规则只改 signature_cuisine_rules.json，不改本文件。
4. 默认 dry-run；--apply 才写库；写库幂等；写后回读断言。
5. 只操作 W5 归属 cuisine 叶子集合(owned_cuisine_ids)；不删他类链接。
6. 宁空不假：低置信/冲突 → 列 ledger.gaps，不硬写。

用法：
  FOOD_APP_DIR=$ROOT/app python3 cloud/signature_cuisine_link.py            # dry-run
  FOOD_APP_DIR=$ROOT/app python3 cloud/signature_cuisine_link.py --apply    # 真写
  FOOD_APP_DIR=$ROOT/app python3 cloud/signature_cuisine_link.py --spot 967
"""
import sys, os, json, re, pathlib, argparse
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
# 运行时用 cloud/vendor/pipeline/common.py（共享连接层）；skill 沉淀副本旁有 common.py，作 fallback。
for _p in (HERE / "vendor" / "pipeline", HERE):
    if (_p / "common.py").exists():
        sys.path.insert(0, str(_p))
        break
import common as C  # noqa: E402

RULES_PATH = HERE / "signature_cuisine_rules.json"
LEDGER_DIR = HERE.parent / "research" / "mechanisms" / "W5"


def load_rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def dishes_of(shop):
    sig = shop.get("signature_dishes")
    return C.dishes_list(sig)


def build_plan(restaurants, links, id2c, rules):
    """返回 (actions, backfill_candidates, entity_edits, per_case)。
    actions: list of {rid, rname, cid, action: add|remove, rule, rationale, source_urls}
    """
    owned = set(rules["owned_cuisine_ids"])
    actions, backfill, entity_edits, per_case = [], [], [], []

    for shop in restaurants:
        rid = shop["id"]
        rname = str(shop.get("name") or "")
        name_en = str(shop.get("name_en") or "")
        full_name = (rname + " " + name_en)
        cur = set(links.get(rid, set()))
        sig = dishes_of(shop)
        sig_text = " ".join(sig)

        # ---- 1) 具名陷阱裁决（优先，可覆盖泛化词典）----
        for tr in rules.get("trap_rules", []):
            needles = tr.get("match_name_contains", [])
            if not any(n and n.lower() in full_name.lower() for n in needles):
                continue
            rec = {"rule": tr["id"], "rid": rid, "name": rname,
                   "before": sorted(cur), "ensure": [], "forbid": [],
                   "rationale": tr.get("forbid_rationale", ""),
                   "source_urls": tr.get("source_urls", [])}

            for cid in tr.get("ensure_cuisine_ids", []):
                if cid not in owned:
                    continue
                if cid not in cur:
                    actions.append({"rid": rid, "rname": rname, "cid": cid,
                                    "action": "add", "rule": tr["id"],
                                    "cuisine_name": id2c.get(cid, {}).get("name"),
                                    "rationale": tr.get("forbid_rationale", ""),
                                    "source_urls": tr.get("source_urls", [])})
                    rec["ensure"].append(cid)
            for cid in tr.get("forbid_cuisine_ids", []):
                if cid not in owned:
                    continue
                if cid in cur:
                    actions.append({"rid": rid, "rname": rname, "cid": cid,
                                    "action": "remove", "rule": tr["id"],
                                    "cuisine_name": id2c.get(cid, {}).get("name"),
                                    "rationale": tr.get("forbid_rationale", ""),
                                    "source_urls": tr.get("source_urls", [])})
                    rec["forbid"].append(cid)
            # entity 正名（T8）
            ent = tr.get("entity_name")
            if ent:
                cur_aliases = shop.get("aliases")
                entity_edits.append({"rid": rid, "rname": rname,
                                      "current_name": rname,
                                      "current_aliases": cur_aliases,
                                      "canonical_name": ent["canonical_name"],
                                      "rejected_aliases": ent["rejected_aliases"],
                                      "accept_aliases": ent["accept_aliases"],
                                      "do_not_rename_main": ent.get("do_not_rename_main", True),
                                      "rationale": ent.get("rationale", ""),
                                      "source_urls": ent.get("source_urls", [])})
            rec["after"] = sorted((cur - set(tr.get("forbid_cuisine_ids", []))) | set(tr.get("ensure_cuisine_ids", [])))
            per_case.append(rec)

        # ---- 2) 泛化招牌菜词典（出品向量→候选叶，仅高置信回填补链，报告态）----
        for dr in rules.get("dish_rules", []):
            pat = dr["pattern"]
            leaf = dr["leaf_cuisine_id"]
            if leaf not in owned:
                continue
            if not re.search(pat, sig_text):
                continue
            # name gate（如台湾牛肉面限定台系店名）
            gate = dr.get("applies_when_name_contains")
            if gate and not any(g.lower() in full_name.lower() for g in gate):
                continue
            hit = re.search(pat, sig_text).group(0)
            # 店型门：正餐里一道千层=serves 含有，不挂叶
            scene = str(shop.get("price_scene") or "")
            req_scene = dr.get("require_scene_contains")
            if req_scene and not any(s in scene for s in req_scene):
                continue
            if leaf not in cur:
                backfill.append({"rid": rid, "rname": rname, "leaf": leaf,
                                 "leaf_name": id2c.get(leaf, {}).get("name"),
                                 "hit": hit, "rule": dr["pattern"],
                                 "note": dr.get("note", "")})
    return actions, backfill, entity_edits, per_case


def apply_writes(actions, entity_edits):
    """幂等写：add → POST 缺失链接；remove → DELETE 具体链接。回读断言。"""
    # 预读现有链接集合
    existing = {(l["restaurant_id"], l["cuisine_id"])
                for l in C.fetch_all("restaurant_cuisines",
                                     select="restaurant_id,cuisine_id",
                                     order_col="restaurant_id")}
    added, removed = [], []
    adds = []
    for a in actions:
        key = (a["rid"], a["cid"])
        if a["action"] == "add":
            if key in existing:
                continue
            adds.append({"restaurant_id": a["rid"], "cuisine_id": a["cid"], "is_primary": False})
        elif a["action"] == "remove":
            if key not in existing:
                continue
            r = C.req("DELETE",
                      f"/restaurant_cuisines?restaurant_id=eq.{a['rid']}&cuisine_id=eq.{a['cid']}")
            if r.status_code in (200, 204):
                removed.append(a)
            else:
                print(f"  [WARN] DELETE {a['rid']}/{a['cid']} -> {r.status_code} {r.text[:120]}")
    if adds:
        h = C.headers(); h["Prefer"] = "return=representation"
        r = C.req("POST", "/restaurant_cuisines", headers=h, json=adds)
        if r.status_code in (200, 201):
            added = adds
        else:
            print(f"  [ERROR] POST adds -> {r.status_code} {r.text[:300]}")
    # entity aliases 写（T8：只补 aliases，不改正店主名）
    alias_writes = []
    for e in entity_edits:
        if e["do_not_rename_main"]:
            cur_al = e.get("current_aliases") or []
            merged = list(cur_al) + [a for a in e["accept_aliases"] if a not in cur_al]
            if merged != cur_al:
                r = C.req("PATCH", f"/restaurants?id=eq.{e['rid']}",
                          json={"aliases": merged})
                if r.status_code in (200, 204):
                    alias_writes.append({"rid": e["rid"], "aliases": merged})
                else:
                    print(f"  [WARN] PATCH aliases {e['rid']} -> {r.status_code} {r.text[:120]}")
    return added, removed, alias_writes


def readback_assert(added, removed, alias_writes):
    """写后回读：断言 remove 的链接已不存在、add 的链接已存在。"""
    live = {(l["restaurant_id"], l["cuisine_id"])
            for l in C.fetch_all("restaurant_cuisines",
                                 select="restaurant_id,cuisine_id",
                                 order_col="restaurant_id")}
    ok = True
    for a in removed:
        if (a["rid"], a["cid"]) in live:
            print(f"  [ASSERT FAIL] still linked {a['rid']}/{a['cid']}")
            ok = False
    for a in added:
        if (a["restaurant_id"], a["cuisine_id"]) not in live:
            print(f"  [ASSERT FAIL] not added {a['restaurant_id']}/{a['cuisine_id']}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spot", type=int)
    args = ap.parse_args()

    rules = load_rules()
    cuis = C.fetch_all("cuisines", select="id,name,parent_category,dimension", order_col="id")
    id2c = {c["id"]: c for c in cuis}
    rc = C.fetch_all("restaurant_cuisines", select="restaurant_id,cuisine_id", order_col="restaurant_id")
    rest = C.fetch_all("restaurants",
                       select="id,name,name_en,aliases,status,signature_dishes,price_avg,price_scene",
                       order_col="id")
    links = defaultdict(set)
    for l in rc:
        links[l["restaurant_id"]].add(l["cuisine_id"])

    actions, backfill, entity_edits, per_case = build_plan(rest, links, id2c, rules)

    if args.spot:
        print(f"=== spot {args.spot} ===")
        for p in per_case:
            if p["rid"] == args.spot:
                print(json.dumps(p, ensure_ascii=False, indent=2))
        return

    adds = [a for a in actions if a["action"] == "add"]
    removes = [a for a in actions if a["action"] == "remove"]
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] 扫描店数={len(rest)} (active={sum(1 for r in rest if r.get('status')=='active')})")
    print(f"  具名裁决命中店数={len(per_case)}  计划add={len(adds)} remove={len(removes)}  "
          f"泛化补链候选={len(backfill)}  实体正名={len(entity_edits)}")
    print("\n-- remove 计划 --")
    for a in removes:
        print(f"  #{a['rid']} {a['rname'][:24]:24s} -{a['cuisine_name']}({a['cid']})  [{a['rule']}]")
    print("-- add 计划 --")
    for a in adds:
        print(f"  #{a['rid']} {a['rname'][:24]:24s} +{a['cuisine_name']}({a['cid']})  [{a['rule']}]")
    print("-- 实体正名 --")
    for e in entity_edits:
        print(f"  #{e['rid']} {e['rname'][:24]:24s} canonical={e['canonical_name']} reject={e['rejected_aliases']} cur_aliases={e['current_aliases']}")
    print("-- 泛化补链候选(报告态,不自动写) top10 --")
    for b in backfill[:10]:
        print(f"  #{b['rid']} {b['rname'][:24]:24s} 缺[{b['leaf_name']}({b['leaf']})] hit={b['hit']}")

    if not args.apply:
        print("\n[DRY-RUN] 加 --apply 才写库。")
        return

    # ---- apply ----
    added, removed, alias_writes = apply_writes(actions, entity_edits)
    ok = readback_assert(added, removed, alias_writes)
    print(f"\n[APPLIED] added={len(added)} removed={len(removed)} alias_writes={len(alias_writes)} readback_assert={'PASS' if ok else 'FAIL'}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()

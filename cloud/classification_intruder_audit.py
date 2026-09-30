#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classification_intruder_audit.py — 出品定类入侵者 / 漏挂检测器（只读，机制层）

解决"把菜单单品当主营品类""因使用某食材而挂菜系"的复发。
原则（cuisine-classification-engine §0-1, north-star A1/A3）：
  - 一家店挂了某"产品叶"(如 拉面/鳗鱼饭/铁板烧/阿拉伯烧烤/美式牛排)，但
    signature_dishes 对该叶的 canonical 菜品正则 **零命中** → 该链接是
    "serves 含有"误挂（入侵者），列入删除建议（不自动删，等确认）。
  - signature_dishes 对某叶 canonical 菜品 **强命中**(≥2 个不重复词) 却未挂 →
    漏挂候选（加法性补链，可在确认后补）。
  - 根菜系叶(如 法餐26/甜品302/面包301/意餐27) 不做零命中判定：正餐 tasting menu
    店名菜名不一定含"法式"字样；根叶是容错误挂。只对"具体产品叶"判零命中。

用法（默认只读 dry-run）：
  python3 classification_intruder_audit.py            # 打印入侵者+漏挂，落 JSON
  python3 classification_intruder_audit.py --json OUT # 落指定 JSON
配置：同目录 intruder_audit_rules.json（加叶只改 JSON，不改 .py）。
"""
import argparse, json, pathlib, re, sys, collections

HERE = pathlib.Path(__file__).resolve().parent
for _p in (HERE / "vendor" / "pipeline", pathlib.Path("/app/pipeline")):
    if (_p / "common.py").exists():
        sys.path.insert(0, str(_p)); break
import common as C  # noqa: E402

RULES_PATH = HERE / "intruder_audit_rules.json"


def load_rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="intruder_audit_report.json")
    args = ap.parse_args()
    rules = load_rules()
    leaf_pat = {int(k): v for k, v in rules["leaf_canonical"].items()}
    leaf_names = {int(k): n for k, n in rules.get("leaf_names", {}).items()}

    cuis = C.fetch_all("cuisines", select="id,name,parent_category,dimension", order_col="id")
    id2c = {c["id"]: c for c in cuis}
    rc = C.fetch_all("restaurant_cuisines", select="restaurant_id,cuisine_id,is_primary", order_col="restaurant_id")
    rest = C.fetch_all("restaurants", select="id,name,status,signature_dishes,price_scene", order_col="id")
    rid2r = {r["id"]: r for r in rest}
    links = collections.defaultdict(set); prim = {}
    for l in rc:
        links[l["restaurant_id"]].add(l["cuisine_id"])
        if l.get("is_primary"):
            prim[l["restaurant_id"]] = l["cuisine_id"]

    intruders, missing = [], []
    for r in rest:
        if r.get("status") != "active":
            continue
        rid = r["id"]; nm = r.get("name")
        sig = C.dishes_list(r.get("signature_dishes"))
        sig_text = " ".join(str(x) for x in sig)
        cur = links.get(rid, set())
        for cid, pat in leaf_pat.items():
            leaf = id2c.get(cid, {})
            if leaf.get("dimension") != "菜系":
                continue
            if cid in cur:
                if not sig:
                    intruders.append({"rid": rid, "name": nm, "cid": cid,
                                      "leaf": leaf.get("name"), "is_primary": prim.get(rid) == cid,
                                      "reason": "无招牌菜证据，链接来源不明(legacy)"})
                    continue
                if not re.search(pat, sig_text, re.I):
                    intruders.append({"rid": rid, "name": nm, "cid": cid,
                                      "leaf": leaf.get("name"), "is_primary": prim.get(rid) == cid,
                                      "reason": "招牌菜零命中该叶 canonical 出品",
                                      "sig_sample": sig[:6]})
            else:
                hits = list(set(m.group(0) for m in re.finditer(pat, sig_text, re.I)))
                if len(hits) >= 2:
                    missing.append({"rid": rid, "name": nm, "cid": cid,
                                    "leaf": leaf.get("name"), "hits": hits[:5],
                                    "scene": r.get("price_scene"), "sig_sample": sig[:6]})

    report = {"intruders": intruders, "missing": missing,
              "counts": {"restaurants": len(rest), "active": sum(1 for r in rest if r.get("status") == "active"),
                         "intruders": len(intruders), "missing": len(missing)}}
    out = pathlib.Path(args.json)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[read-only] active={report['counts']['active']} 入侵者={len(intruders)} 漏挂={len(missing)}")
    print("\n-- 入侵者(挂叶但招牌零命中，建议删除，待确认) --")
    for x in sorted(intruders, key=lambda z: (not z["is_primary"], z["rid"])):
        star = "★PRIMARY" if x["is_primary"] else " secondary"
        print(f"  #{x['rid']:5d} [{star}] {str(x['name'])[:26]:26s} -{x['leaf']}({x['cid']})  {x['reason']}")
        if x.get("sig_sample"):
            print(f"           sig: {' | '.join(str(s) for s in x['sig_sample'])[:140]}")
    print("\n-- 漏挂(招牌强命中却未挂，加法性补链候选) --")
    for x in missing:
        print(f"  #{x['rid']:5d} {str(x['name'])[:26]:26s} +{x['leaf']}({x['cid']}) hits={x['hits']} scene={x['scene']}")
    print(f"\n报告 -> {out}")


if __name__ == "__main__":
    main()

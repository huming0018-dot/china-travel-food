#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 research/reevidence/raw_*_reev.jsonl → plan_reevidence.json（stage3 update 格式）+ 复核报告。
主代理独立复核，不盲信子代理 verdict：
- keep 门：≥2条实质堂食点评(quote≥10字/带菜名) 且 sources 类型≥2 且 四子分齐；来源单一降"存疑"。
- "建议下架"中理由为分类错误(实际是另一菜系) → reclassify 清单(成对改标签,非下架)。
- 查无此店/纯团购软广 → 保留在库,证据前缀+软广高扣分沉底,列报告待用户最终裁决(不擅删)。
- closed 三要素齐才关店。
"""
import glob
import json
import re
import sys

SKILL_SCRIPTS = "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"
sys.path.insert(0, SKILL_SCRIPTS)
import common as C  # noqa: E402

R = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/research"
RECLASS_HINT = re.compile(r"归类|实际为|误挂|误标|菜系.*错|其实是|实为")


def load_ev(s):
    if not s:
        return {"quotes": [], "negative": [], "soft_ad": []}
    try:
        d = json.loads(s)
        return {"quotes": d.get("quotes", []), "negative": d.get("negative", []),
                "soft_ad": d.get("soft_ad", [])}
    except (ValueError, TypeError):
        return {"quotes": [], "negative": [], "soft_ad": []}


def substance(q):
    t = str(q.get("quote") or "")
    return bool(q.get("url")) and (len(t) >= 10 or bool(q.get("dish")))


def main():
    recs = []
    files = sorted(glob.glob(f"{R}/reevidence/raw_*_reev.jsonl"))
    for f in files:
        for l in open(f, encoding="utf-8"):
            if l.strip():
                recs.append(json.loads(l))
    print(f"补强记录 {len(recs)} 条 / {len(files)} 片")

    allr = C.fetch_all("restaurants", "id,name,phone,status,evidence_summary", order_col="id")
    cur = {x["id"]: x for x in allr}

    plan = []
    report = {"keep": [], "存疑": [], "建议下架待裁": [], "分类纠错待改标签": [], "closed": [], "无锚点": []}
    for r in recs:
        rid = r.get("match_restaurant_id")
        if not rid or rid not in cur:
            report["无锚点"].append(r.get("name")); continue
        old = cur[rid]
        raw_v = r.get("verdict", "keep")
        qs = [q for q in (r.get("evidence", {}).get("diner_quotes") or []) if substance(q)]
        stypes = {s.get("type") for s in (r.get("sources") or []) if s.get("type")}
        sc = r.get("scores") or {}
        sc_ok = all(k in sc for k in ("objective", "diner", "taste", "endorsement", "soft_ad_penalty"))
        reason = r.get("verdict_reason") or ""

        # ---- 独立复核裁决 ----
        v = raw_v
        if raw_v == "建议下架" and RECLASS_HINT.search(reason):
            v = "分类纠错"
        elif raw_v == "keep" and not (len(qs) >= 2 and len(stypes) >= 2 and sc_ok):
            v = "存疑"
            if len(stypes) < 2:
                reason = (reason + "；主复核：来源类型单一(仅%s)，缺跨类型验证" % "/".join(sorted(stypes))).strip("；")
            elif len(qs) < 2:
                reason = (reason + "；主复核：实质堂食点评不足2条").strip("；")

        # ---- 合并证据（基于库内现状）----
        ev = load_ev(old.get("evidence_summary"))
        seen = {(q.get("url"), q.get("quote")) for q in ev["quotes"]}
        for q in (r.get("evidence", {}).get("diner_quotes") or []):
            key = (q.get("url"), q.get("quote"))
            if q.get("url") and q.get("quote") and key not in seen:
                ev["quotes"].append({"quote": q.get("quote"), "source": q.get("source"),
                                     "url": q.get("url"), "dish": q.get("dish"), "date": q.get("date")})
                seen.add(key)
        for k_src, k_dst in (("negative_signals", "negative"), ("soft_ad_flags", "soft_ad")):
            for x in (r.get("evidence", {}).get(k_src) or []):
                if x not in ev[k_dst]:
                    ev[k_dst].append(x)

        fields = {"data_updated_at": "2026-09-23"}
        # 建议下架但软广扣分不足的，强制沉底（证据为零/查无此店=30，纯软广=25），仍不擅删
        if v == "建议下架" and sc_ok:
            _floor = 30 if re.search(r"无法验证真实|查无|地址不明确|无法定位|不存在|信息不透明|证据为零", reason) else 25
            sc["soft_ad_penalty"] = max(sc["soft_ad_penalty"], _floor)
        elif v == "建议下架" and not sc_ok:
            print("⚠ 建议下架但评分不完整:", rid, old["name"], sc)
        if sc_ok:
            fields.update({"score_objective": sc["objective"], "score_diner": sc["diner"],
                           "score_taste": sc["taste"], "score_endorsement": sc["endorsement"],
                           "soft_ad_penalty": sc["soft_ad_penalty"]})
        if r.get("phone_raw") and not old.get("phone"):
            phone, issues, _ = C.clean_phone(r["phone_raw"])
            if phone and not any(i == "phone_unparseable" for i in issues):
                fields["phone"] = phone

        lead = None
        if v == "closed":
            if r.get("closed_date") and r.get("closed_source"):
                fields.update({"status": "closed", "closed_date": r["closed_date"],
                               "closed_source": r["closed_source"]})
                lead = f"【{r['closed_date']} 关店】来源:{r['closed_source']}"
            else:
                v = "存疑"; reason += "；关店三要素不全，未改状态"
        elif v == "分类纠错":
            lead = "【分类纠错·待改标签】" + reason
        elif v == "建议下架":
            lead = "【建议下架·待裁决】" + reason
        elif v == "存疑":
            lead = "【存疑·证据弱】" + reason
        body = json.dumps({"quotes": ev["quotes"], "negative": ev["negative"],
                           "soft_ad": ev["soft_ad"]}, ensure_ascii=False)
        fields["evidence_summary"] = (lead + " " + body) if lead else body

        plan.append({"action": "update", "restaurant_id": rid, "name": old["name"],
                     "fields": fields, "cids_add": [], "conflicts": [], "warnings": []})
        key = {"keep": "keep", "存疑": "存疑", "建议下架": "建议下架待裁",
               "分类纠错": "分类纠错待改标签", "closed": "closed"}.get(v, "存疑")
        report[key].append({"id": rid, "name": old["name"], "reason": reason,
                            "n_quotes": len(ev["quotes"]), "src_types": sorted(stypes),
                            "penalty": sc.get("soft_ad_penalty")})

    json.dump(plan, open(f"{R}/plan_reevidence.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(report, open(f"{R}/reevidence_report.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"plan {len(plan)} 条 update -> plan_reevidence.json")
    for k in ("keep", "存疑", "建议下架待裁", "分类纠错待改标签", "closed", "无锚点"):
        print(f"  {k}: {len(report[k])}")
    print("\n--- 分类纠错（成对改标签，不下架）---")
    for x in report["分类纠错待改标签"]:
        print(f"  id{x['id']} {x['name']} | {x['reason'][:80]}")
    print("\n--- 建议下架待裁决（保留+沉底）---")
    for x in report["建议下架待裁"]:
        print(f"  id{x['id']} {x['name']} | penalty={x['penalty']} | {x['reason'][:70]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
candidate_verify.py — 「候选人口味核验 runner」（账号无关，消费 kol_router 产出的全新餐饮候选）。

为什么需要它：
  kol_lead_fill.json 里是高德验真过、但库里还没有的新店（无 rid）。现有 review_apify_fill
  只能给【已在库】店补评价（select_targets 只遍历已有 rid）。本 runner 按【店名】routed 搜
  小红书（atomus-first→opspilot 兜底），把真实食客帖锚定到候选，做 admission：
    ≥2 独立食客 且 口味均分≥3.5 → admit（产 raw_place+reviews 包）
    均分<3.3 → reject；3.3–3.5 或仅 1 名食客 → hold；关店信号 → closed
  默认只核验/打包；--create 才真正建店（建店前再次查重，cuisine 留空待分类）。

复用 review_apify_fill（RF）：apify_search / normalize_note / note_author / is_brand_author /
current_used / remaining_credit / daily_allowance / PROVIDER_CHAIN，以及 common(C)、entity_match(EM)。

用法（主机，先 set -a && . ./fill.env && set +a）：
  python3 candidate_verify.py                 # 离线列出候选，不付费
  python3 candidate_verify.py --fetch         # 真实核验（不建店）
  python3 candidate_verify.py --fetch --apply # 核验并落 admit/hold/reject 包
  python3 candidate_verify.py --fetch --apply --create   # 核验并建店写评
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), str(HERE / "vendor" / "pipeline"), "/app/pipeline"):
    if p not in sys.path:
        sys.path.insert(0, p)

import review_apify_fill as RF  # noqa: E402

C = RF.C
EM = RF.EM
DATA = RF.DATA
CAND_F = DATA / "kol_lead_fill.json"
DIAN_F = DATA / "dianping_lead_fill.json"
STATE_F = DATA / "candidate_verify_state.json"
ADMIT_F = DATA / "candidate_admit_package.json"
HOLD_F = DATA / "candidate_hold.json"
REJECT_F = DATA / "candidate_reject.json"

ADMIT_MIN_VOICES = 2
ADMIT_MEAN = 3.5
REJECT_MEAN = 3.3
MAX_ACCEPT = 6
PER_NOTE_PAUSE = 4

CLOSURE_RE = re.compile(r"关门|倒闭|停业|关店|关了|已经关|搬走|搬迁|撤店|不开了")
# 工业/酒店/连锁反链过滤（用户硬要求）：这类即便好评也不自动收录进「真·本地好吃」图鉴。
INDUSTRIAL_RE = re.compile(
    r"自助餐|宜家|大酒店|机场|服务区|高铁站?|景区内|风景区|环球影城|迪士尼|乐园|影城|员工食堂|连锁")


def load_candidates():
    merged, seen_poi, seen_core = [], set(), set()

    def _add(rows, src):
        for c in rows or []:
            c = dict(c)
            c["_src"] = src
            poi = c.get("poi_id")
            core = C.cjk_norm(c.get("core") or c.get("name") or "")
            if poi and poi in seen_poi:
                continue
            if core and core in seen_core:
                continue
            if poi:
                seen_poi.add(poi)
            if core:
                seen_core.add(core)
            merged.append(c)

    if CAND_F.exists():
        _add(json.loads(CAND_F.read_text(encoding="utf-8")), "kol")
    if DIAN_F.exists():
        _add(json.loads(DIAN_F.read_text(encoding="utf-8")), "dianping")
    if not merged:
        sys.exit(f"找不到候选（{CAND_F.name} / {DIAN_F.name}）")
    return merged


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"items": {}, "cost_by_provider": {}, "calls_by_provider": {}, "last_run": ""}


def save_state(st):
    st["last_run"] = C.today()
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def district_of(cand):
    m = re.search(r"([\u4e00-\u9fa5]{2,4}区)", cand.get("address", ""))
    return m.group(1) if m else ""


def area_token(cand):
    blob = cand.get("name", "") + cand.get("address", "")
    for m in EM.MALLS:
        if m and m in blob:
            return m
    m = re.search(r"([\u4e00-\u9fa5]{2,6}[路街])", blob)
    return m.group(1) if m else ""


def keywords(cand):
    core = cand["core"]
    area = area_token(cand)
    q1 = f"{core} 上海"
    q2 = (f"{core} {area} 堂食 测评 上海" if area else f"{core} 堂食 测评 上海")
    return q1, q2


def note_text(note):
    return C.cjk_norm(note.get("title", "") + note.get("desc", ""))


def different_branch(note, area):
    """候选有明确商场/区域时，笔记提到【别的商场】= 其他分店，跳过。"""
    if not area:
        return False
    t = note_text(note)
    a = C.cjk_norm(area)
    for m in EM.MALLS:
        mn = C.cjk_norm(m)
        if mn and mn in t and mn != a:
            return True
    return False


def brand_hit(note, cand):
    t = note_text(note)
    names = [cand["core"]] + cand.get("raw_variants", [])
    for nm in names:
        n = C.cjk_norm(nm)
        if n and (n in t or t in n):
            return True
    return False


def evaluate_note(note, cand):
    """返回 (status, body, score, raw)。"""
    core_norm = C.cjk_norm(cand["core"])
    if RF.is_brand_author(note, core_norm):
        return "brand_author", None, None, None
    raw_text = (note.get("title", "") + "。" + note.get("desc", "")).strip("。")
    body = EM.clean_content(raw_text)
    if len(body) < 8 or not C.quote_has_substance(body):
        return "无实物/软广模板", None, None, None
    if EM.is_question(body):
        return "疑问/互动", None, None, None
    score, raw = EM.taste_sent(body)
    if score is None:
        return "无口味信号", None, None, None
    return "accept", body, score, raw


def process_candidate(cand, st, gates, args):
    poi = cand["poi_id"]
    item = st["items"].setdefault(poi, {"name": cand["name"], "status": "pending",
                                        "kws": [], "urls": []})
    if item["status"] in ("admit", "reject", "closed", "industrial") and not args.refetch:
        return item["status"], 0.0
    # 工业/酒店反链：不花钱，直接过滤
    if INDUSTRIAL_RE.search(cand.get("name", "") + cand.get("address", "")):
        item["status"] = "industrial"
        item["accepted_at"] = C.today()
        return "industrial", 0.0
    q1, q2 = keywords(cand)
    area = area_token(cand)
    accepted = {}   # url -> (author, score, body, raw, prov)
    reasons = {}
    closure_hits = 0
    spent = 0.0

    for kw in (q1, q2):
        if len(accepted) >= MAX_ACCEPT:
            break
        for prov in RF.PROVIDER_CHAIN:
            rem = RF.remaining_credit()
            if rem < RF.PER_RUN_FLOOR_USD:
                item["status"] = item.get("status", "pending")
                save_state(st)
                return "NO_CREDIT", spent
            if current_gate(gates, "day") or current_gate(gates, "round"):
                save_state(st)
                return "CAP", spent
            u0 = RF.current_used()
            raw_notes, err = RF.apify_search(prov, kw, max_items=6)
            du = max(0.0, round(RF.current_used() - u0, 4))
            spent += du
            cbp = st["cost_by_provider"]
            cbp[prov] = round(cbp.get(prov, 0.0) + du, 4)
            cap = st["calls_by_provider"]
            cap[prov] = cap.get(prov, 0) + 1
            item["kws"].append(f"{kw}@{prov}")
            if err:
                reasons[err] = reasons.get(err, 0) + 1
                continue
            for note in (RF.normalize_note(prov, x) for x in (raw_notes or [])):
                url = note.get("url")
                if url and (url in gates["existing_urls"] or url in item["urls"]):
                    continue
                if different_branch(note, area):
                    reasons["other_branch"] = reasons.get("other_branch", 0) + 1
                    continue
                if not brand_hit(note, cand):
                    reasons["no_brand"] = reasons.get("no_brand", 0) + 1
                    continue
                blob = note.get("title", "") + note.get("desc", "")
                if CLOSURE_RE.search(blob):
                    closure_hits += 1
                status, body, score, raw = evaluate_note(note, cand)
                if status == "accept":
                    if url:
                        item["urls"].append(url)
                    accepted[url or f"n{len(accepted)}"] = (
                        RF.note_author(note), score, body, raw, prov)
                else:
                    reasons[status] = reasons.get(status, 0) + 1
                if len(accepted) >= MAX_ACCEPT:
                    break
            time.sleep(PER_NOTE_PAUSE)
            if len(accepted) >= MAX_ACCEPT:
                break

    # ------------- admission 判定
    authors = {}
    scores = []
    for url, (au, sc, body, raw, prov) in accepted.items():
        authors.setdefault(C.cjk_norm(au), au)
        scores.append(sc)
    n_ind = len(authors)
    mean = round(sum(scores) / len(scores), 2) if scores else 0.0
    item.update({"n_diners": n_ind, "mean": mean, "n_reviews": len(accepted),
                 "reasons": reasons, "accepted_at": C.today()})

    if closure_hits >= 1 and n_ind == 0:
        verdict = "closed"
    elif n_ind >= ADMIT_MIN_VOICES and mean >= ADMIT_MEAN:
        verdict = "admit"
    elif n_ind >= 1 and mean < REJECT_MEAN:
        verdict = "reject"
    else:
        verdict = "hold"
    item["status"] = verdict

    if verdict == "admit":
        item["package"] = build_package(cand, accepted)
    return verdict, spent


def current_gate(gates, kind):
    if kind == "day":
        return (RF.current_used() - gates["day_start_used"]) >= gates["daily"]
    return (RF.current_used() - gates["round_start"]) >= RF.ROUND_CAP_USD


def build_package(cand, accepted):
    place = {
        "name": cand["name"], "address": cand.get("address", ""),
        "district": district_of(cand), "phone": cand.get("tel") or "",
        "lng": cand.get("lng"), "lat": cand.get("lat"),
        "poi_id": cand.get("poi_id"), "kol_grade": cand.get("grade"),
        "kol_voices": cand.get("independent_kol_voices"),
        "price_avg": None, "signature_dishes": [],
    }
    reviews = []
    for url, (au, sc, body, raw, prov) in accepted.items():
        reviews.append({
            "author_name": au[:20], "content": body, "source_platform": "小红书",
            "source_url": url or "", "review_kind": "diner",
            "is_verified_diner": True, "trust_level": "mid",
            "aspect_taste": sc, "aspect_json": {"via": f"apify-{prov}", "taste_raw": raw},
        })
    return {"place": place, "reviews": reviews}


def write_outputs(st):
    admits, holds, rejects = [], [], []
    for poi, item in st["items"].items():
        v = item["status"]
        if v == "admit":
            pkg = item.get("package")
            pkg["poi_id"] = poi
            admits.append(pkg)
        elif v in ("hold", "closed", "NO_CREDIT", "CAP", "pending"):
            holds.append({"poi_id": poi, "name": item.get("name"), "status": v,
                          "n_diners": item.get("n_diners", 0), "mean": item.get("mean", 0)})
        elif v in ("reject", "industrial"):
            rejects.append({"poi_id": poi, "name": item.get("name"), "status": v,
                            "n_diners": item.get("n_diners", 0), "mean": item.get("mean", 0)})
    ADMIT_F.write_text(json.dumps(admits, ensure_ascii=False, indent=1), encoding="utf-8")
    HOLD_F.write_text(json.dumps(holds, ensure_ascii=False, indent=1), encoding="utf-8")
    REJECT_F.write_text(json.dumps(rejects, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(admits), len(holds), len(rejects)


def create_restaurants(st, args):
    """对 admit 包：再次查重 → 建店 → 写评；cuisine 留空待分类。"""
    existing = C.fetch_all("restaurants", "id,name,address")
    created, skipped = [], []
    for poi, item in st["items"].items():
        if item["status"] != "admit":
            continue
        pkg = item["package"]
        pl = pkg["place"]
        dup = next((r for r in existing
                    if C.cjk_norm(pl["name"]) in C.cjk_norm(r["name"])
                    or (r.get("address") and C.addr_core(r["address"])
                        and C.addr_core(r["address"]) == C.addr_core(pl["address"]))), None)
        if dup:
            skipped.append({"poi_id": poi, "existing_id": dup["id"]})
            continue
        body = {"name": pl["name"], "status": "active", "address": pl["address"],
                "district": pl["district"], "phone": pl["phone"] or None}
        if pl.get("lng") and pl.get("lat"):
            body["location"] = C.point_ewkt(pl["lng"], pl["lat"])
        h = C.headers()
        h["Prefer"] = "return=representation"
        r = RF.requests.post(C.BASE + "/restaurants?select=id", headers=h, json=body, timeout=45)
        if r.status_code not in (200, 201):
            print("  create fail", r.status_code, r.text[:140])
            continue
        rid = r.json()[0]["id"]
        for rev in pkg["reviews"]:
            rev["restaurant_id"] = rid
            rr = C.req("POST", "/reviews", json=rev)
            if rr.status_code not in (200, 201):
                print("  review fail", rr.status_code, rr.text[:120])
        created.append({"poi_id": poi, "rid": rid, "name": pl["name"],
                        "reviews": len(pkg["reviews"]), "needs_cuisine": True})
    return created, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--limit", type=int, default=4)
    ap.add_argument("--refetch", action="store_true")
    args = ap.parse_args()

    cands = load_candidates()
    st = load_state()

    if not args.fetch:
        pending = [c for c in cands if st["items"].get(c["poi_id"], {}).get("status")
                   in (None, "pending", "NO_CREDIT", "CAP")]
        print(f"候选 {len(cands)}；待核验 {len(pending)}；剩余额度≈${RF.remaining_credit():.3f}")
        for c in pending[:args.limit]:
            print("  -", c["name"], f"[KOL声音{c.get('independent_kol_voices')}, grade{c.get('grade')}]")
        print("--fetch 核验；--apply 落包；--create 建店")
        return

    rem = RF.remaining_credit()
    gates = {"day_start_used": RF.current_used(),
             "daily": RF.daily_allowance(rem),
             "round_start": RF.current_used(),
             "existing_urls": set(x.get("source_url")
                                  for x in C.fetch_all("reviews", "source_url") if x.get("source_url"))}
    todo = [c for c in cands if st["items"].get(c["poi_id"], {}).get("status")
            in (None, "pending", "NO_CREDIT", "CAP")]
    counts = {}
    total_spent = 0.0
    for cand in todo[:args.limit]:
        verdict, spent = process_candidate(cand, st, gates, args)
        total_spent += spent
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"  {verdict:8} n={st['items'][cand['poi_id']].get('n_diners',0)} "
              f"mean={st['items'][cand['poi_id']].get('mean',0)}  {cand['name'][:26]}")
        if verdict in ("NO_CREDIT", "CAP"):
            break
    save_state(st)
    print(f"本轮判定 {counts}；实花≈${total_spent:.3f}")
    if args.apply:
        na, nh, nr = write_outputs(st)
        print(f"落包：admit {na} / hold+closed {nh} / reject {nr}")
    if args.create and args.apply:
        created, skipped = create_restaurants(st, args)
        print(f"建店 {len(created)}：", json.dumps(created, ensure_ascii=False))
        if skipped:
            print("已存在跳过：", json.dumps(skipped, ensure_ascii=False))


if __name__ == "__main__":
    main()

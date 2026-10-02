#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_apply.py — 统一「发现 → 交叉校验 → 挂标 → 精选重算」的唯一写入门（dev）。

为什么存在（修复反复出现的底层缺陷）：
  1) post_audit 旧逻辑对 chain/central_kitchen/premade 等【硬负面】标签，单条 conf≥0.8
     即挂，违反用户铁律「硬负面需 ≥2 独立可信源」；
  2) 没有按 (店,字段) 聚合证据、不做冲突仲裁，也不区分独立声音（同一域名多帖被当多源）；
  3) apply 路径分散（post_audit 与 reconcile.stage_curate 各写一遍），无单一闸门、无审计账本；
  4) 标签变化没有确定性地驱动精选重算，状态不联动。

本模块规则（全部确定性、可复跑、可审计）：
  - 读【全部】findings，按 (rid,field) 聚合；独立源 n_ind = max(不同域名数, 不同证据类数)。
    证据类：reg=注册主体/工商/企查查/天眼查/股权；branch=分店/分支/门店/加盟/官网；news=新闻/媒体。
    → 用户认可的「分店列表 + 注册主体互证」天然计为 2 个独立源。
  - 硬负面值（连锁非独立 / 中央厨房疑似·确认 / 预制疑似·高 / 食安疑似·问题）须 n_ind≥2 才挂新标；
    单源 → hold：不挂新硬标、不据此下架，进 reverify 取证窗口；DB 已有的硬标保留、不批量降级。
  - 澄清值（独立店/无）：conf≥0.8 且无 ≥2 源硬证据对冲时可挂。
  - 预制「低」为软标记，单高置信源即可；investor/price 为信息字段，conf≥0.8，price 过范围校验。
  - 精选硬下架：status=closed（平台状态直接采信）/ central_kitchen=确认 / premade=高。
    【连锁本身不下架】（好连锁可留）；大型/资本化连锁且独立食客口味声音<2 → chain_review 交 ML 门，不自动改。

用法：
  python3 gate_apply.py                 # dry run，出计划与 worklist，不写库
  python3 gate_apply.py --apply         # 单一 writer 写库 + 回读 + 决策账本
"""
import argparse
import datetime
import json
import pathlib
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import data_gate as gate

DATA = pathlib.Path("/app/data")
LEDGER = DATA / "post_record"
FINDINGS = LEDGER / "findings.jsonl"
LEDGER.mkdir(parents=True, exist_ok=True)

# 枚举（与 post_audit / DB 约束对齐）
ENUMS = {
    "chain_type": ["独立店", "小型连锁", "大型连锁", "资本化连锁"],
    "central_kitchen": ["无", "疑似", "确认"],
    "premade_risk": ["无", "低", "疑似", "高"],
    "food_safety": ["无", "疑似", "问题"],
}
HARD_VALUES = {
    "chain_type": {"小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"疑似", "确认"},
    "premade_risk": {"疑似", "高"},
    "food_safety": {"疑似", "问题"},
}
CLEAR_VALUE = {"chain_type": "独立店", "central_kitchen": "无",
               "premade_risk": "无", "food_safety": "无"}
# 硬值的严重度排序（仲裁时取更重者）
SEVERITY = {"资本化连锁": 3, "大型连锁": 2, "小型连锁": 1,
            "确认": 2, "高": 2, "疑似": 1, "问题": 2}
ENUM_FIELDS = set(ENUMS)
INFO_FIELDS = {"investor_info", "price_avg"}
# 客观事实字段（低主观性）：单一权威源（地图/官网）即可，但仍经 gate 校验、不直写
FACT_FIELDS = {"phone", "location", "opening_hours", "open_days"}
CONF_MIN = 0.8

RE_PHONE = re.compile(r"^(?:0\d{2,3}-?)?\d{7,8}$|^1[3-9]\d{9}$")
RE_LOC = re.compile(r"^SRID=4326;POINT\(-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\)$")


def valid_fact(field, value):
    """事实字段轻校验：宁空不假。"""
    if value is None or value == "":
        return False
    if field == "phone":
        return bool(RE_PHONE.match(str(value).replace(" ", "")))
    if field == "location":
        return bool(RELOC.match(str(value)))
    if field in ("opening_hours", "open_days"):
        return len(str(value)) >= 1
    return True

RE_REG = re.compile(r"注册|工商|企查查|天眼查|爱企查|股权|控股|法人|主体")
RE_BRANCH = re.compile(r"分店|分支|门店|加盟|官网|连锁|门店列表")
RE_NEWS = re.compile(r"新闻|报道|媒体|公众号|测评")
RE_DOM = re.compile(r"https?://([^/]+)")
# 集团关系连接词：出现即表明文本里点名的别家品牌与本店是母/子/姐妹/合作关系
RELATION_CUE = re.compile(
    r"旗下|隶属|所属|同集团|集团|姐妹|子品牌|高端品牌|高端版本|高端线|控股|联袂|联创|"
    r"品牌管理|运营主体|运营方|运营|团队|合作|联手|携手|背书")


def domain(url):
    m = RE_DOM.match(url or "")
    return m.group(1) if m else "?"


def ev_classes(reason):
    t = reason or ""
    out = set()
    if RE_REG.search(t):
        out.add("reg")
    if RE_BRANCH.search(t):
        out.add("branch")
    if RE_NEWS.search(t):
        out.add("news")
    return out


def n_independent(rows):
    """独立源数 = max(不同域名数, 不同证据类数)。"""
    doms, cls = set(), set()
    for r in rows:
        doms.add(domain(r.get("source_url")))
        cls |= ev_classes(r.get("reason"))
    return max(len(doms), len(cls))


def schema_for(field):
    """data_gate 校验 schema（枚举 / 数值范围）。"""
    if field in ENUMS:
        return {"fields": {field: {"type": "string", "enum": ENUMS[field]}}}
    if field == "price_avg":
        return {"fields": {field: {"type": "number", "min": 5, "max": 5000}}}
    if field == "investor_info":
        return {"fields": {field: {"type": "string", "max_length": 200}}}
    return {}


def resolve_enum(field, rows):
    """对一个枚举 (rid,field) 的全部证据做仲裁，返回 decision dict。"""
    buckets = defaultdict(list)
    for r in rows:
        v = r.get("value")
        if v in ENUMS[field]:
            buckets[v].append(r)
    hard = HARD_VALUES[field]
    # 硬值候选：按严重度排序，各自计独立源
    hard_cands = []
    for v, rs in buckets.items():
        if v in hard:
            cred = [r for r in rs if float(r.get("confidence", 0)) >= CONF_MIN]
            if cred:
                hard_cands.append((SEVERITY.get(v, 1), v, cred, n_independent(cred)))
    hard_cands.sort(reverse=True, key=lambda x: x[0])
    clear_rows = [r for r in buckets.get(CLEAR_VALUE[field], [])
                  if float(r.get("confidence", 0)) >= CONF_MIN]

    if hard_cands:
        sev, hv, cred, ni = hard_cands[0]
        if ni >= 2:
            return {"action": "apply_hard", "value": hv, "n_ind": ni,
                    "why": f"硬标 {hv} 有 {ni} 独立源"}
        # 硬标仅单源
        if clear_rows and n_independent(clear_rows) >= 2:
            return {"action": "apply_clear", "value": CLEAR_VALUE[field], "n_ind": n_independent(clear_rows),
                    "why": f"硬标 {hv} 仅单源，澄清值有 {n_independent(clear_rows)} 独立源，采澄清"}
        return {"action": "hold", "value": None, "n_ind": ni, "hard_value": hv,
                "why": f"硬标 {hv} 仅 {ni} 独立源，进取证窗口，不挂新标"}
    if clear_rows:
        return {"action": "apply_clear", "value": CLEAR_VALUE[field],
                "n_ind": n_independent(clear_rows), "why": "澄清值高置信，无硬证据对冲"}
    return {"action": "none", "value": None, "n_ind": 0, "why": "无有效枚举证据"}


def _is_num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def resolve_info(field, rows):
    """信息字段（investor/price）：取最高置信，price 做分歧与范围校验。"""
    cred = [r for r in rows if float(r.get("confidence", 0)) >= CONF_MIN
            and str(r.get("source_url", "")).startswith("http")]
    if not cred:
        return {"action": "none", "value": None, "why": "无高置信来源"}
    cred.sort(key=lambda r: float(r.get("confidence", 0)), reverse=True)
    if field == "price_avg":
        vals = []
        for r in cred:
            try:
                vals.append(float(r.get("value")))
            except Exception:
                pass
        vals = [v for v in vals if 5 <= v <= 5000]
        if not vals:
            return {"action": "none", "value": None, "why": "price 无合法值"}
        top = vals[0]
        # 多个高置信值分歧过大（>25%）→ hold，避免误改
        if vals and max(vals) / max(min(vals), 1) > 1.25:
            return {"action": "hold", "value": None, "why": f"price 来源分歧 {sorted(set(vals))[:4]}"}
        # price_avg 是 integer 列：浮点会被 PostgREST 拒（22P02），统一取整
        return {"action": "apply", "value": int(round(top)), "why": f"price={int(round(top))} 高置信"}
    txt = (cred[0].get("value") or "").strip()
    if not txt:
        return {"action": "none", "value": None, "why": "investor 空"}
    return {"action": "apply", "value": txt[:200], "why": "investor 高置信"}


def resolve_fact(field, rows):
    """客观事实字段：取通过校验的最高置信值；phone/location 须有来源。"""
    need_src = field in ("phone", "location")
    cand = []
    for r in rows:
        v = r.get("value")
        if not valid_fact(field, v):
            continue
        if need_src and not str(r.get("source_url", "")).startswith("http"):
            continue
        cand.append(r)
    if not cand:
        return {"action": "none", "value": None, "why": f"{field} 无合法证据"}
    cand.sort(key=lambda r: float(r.get("confidence", 0)), reverse=True)
    return {"action": "apply", "value": cand[0]["value"],
            "why": f"{field} 最高置信={cand[0].get('confidence')}"}


def _brand_core(name):
    """店名核心品牌：去括号分店后缀、去标点，保留中文/英文主干。"""
    s = re.split(r"[（(]", name or "")[0]
    s = re.sub(r"(总店|首店|旗舰店|专卖店|直营店)$", "", s)
    return s.strip(" ·・•&")


def build_brand_index(rests, P):
    """归一品牌名 -> rid 集合，用于识别 investor 文本里点名的“别家店”。"""
    idx = defaultdict(set)
    for r in rests:
        core_name = _brand_core(r["name"])
        for cand in {core_name, P.cjk_norm(core_name), core_name.split("·")[0]}:
            cand = P.cjk_norm(cand)
            if not cand:
                continue
            # 中文品牌 2 字即具区分度（鮨一/坛烧）；拉丁需 ≥3 避免噪声
            min_len = 2 if any("一" <= ch <= "鿿" for ch in cand) else 3
            if len(cand) >= min_len:
                idx[cand].add(r["id"])
    return idx


def self_tokens(store_name, P):
    """本店品牌的自证 token 集合（中文含首2字/分段/汉字+数字；拉丁含词与前两词拼接）。"""
    core_name = _brand_core(store_name)
    toks = set()
    # 中文：按非汉字切段，每段取归一全段 + 前 2 字（品牌前缀最具区分度）
    for seg in re.findall(r"[一-鿿]+", core_name):
        ns = P.cjk_norm(seg)
        if ns:
            toks.add(ns)
        if len(seg) >= 2:
            toks.add(P.cjk_norm(seg[:2]))
    # 汉字+数字品牌（福1039 / 福1088）：保留相邻数字
    for seg in re.findall(r"[一-鿿]+[0-9]+", core_name):
        ns = P.cjk_norm(seg)
        if ns and len(ns) >= 2:
            toks.add(ns)
    # 拉丁：小写词(≥3) + 前两词拼接
    words = re.findall(r"[A-Za-z]+", core_name.lower())
    for w in words:
        if len(w) >= 3:
            toks.add(w)
    if len(words) >= 2:
        toks.add("".join(words[:2]))
    return {t for t in toks if t and len(t) >= 2}


def self_present(store_name, text, P):
    """证据文本是否出现本店品牌任一 token。"""
    nt = P.cjk_norm(text or "")
    return any(t in nt for t in self_tokens(store_name, P))


def brand_contradiction(store_name, text, brand_index, self_rid, P):
    """文本点名了别家在库品牌、且没点到本店 → 返回别家品牌名，否则 None。"""
    nt = P.cjk_norm(text or "")
    if self_present(store_name, text, P):
        return None
    for bname, rids in brand_index.items():
        if bname in nt and self_rid not in rids:
            return bname
    return None


def named_other_brands(text, brand_index, self_rid, P):
    """文本中点名的、非本店的在库品牌集合。"""
    nt = P.cjk_norm(text or "")
    return {b for b, rids in brand_index.items()
            if b in nt and self_rid not in rids}


def build_relations(findings, brand_index, P):
    """rid -> 关联品牌集合：仅当 finding 带【关系连接词】且点名别家品牌时建立。"""
    rel = defaultdict(set)
    for d in findings:
        if d.get("field") != "investor_info":
            continue
        rid = d.get("restaurant_id")
        text = (d.get("reason") or "") + " " + str(d.get("value") or "")
        if not RELATION_CUE.search(text):
            continue
        for b in named_other_brands(text, brand_index, rid, P):
            rel[rid].add(b)
    return rel


def price_implausible(newv, oldv):
    """新价相对存量价极端偏离（>2.5x 或 <0.4x）→ 疑似错挂，hold。"""
    try:
        newv, oldv = float(newv), float(oldv)
    except (TypeError, ValueError):
        return False
    if oldv <= 0:
        return False
    return newv > oldv * 2.5 or newv < oldv * 0.4


def load_findings():
    if not FINDINGS.exists():
        return []
    return [json.loads(l) for l in FINDINGS.read_text(encoding="utf-8").splitlines() if l.strip()]


def build_plan():
    findings = load_findings()
    grouped = defaultdict(list)
    for d in findings:
        rid, fld = d.get("restaurant_id"), d.get("field")
        if rid and fld:
            grouped[(rid, fld)].append(d)

    rests = core.fetch_all("restaurants",
        "id,name,status,is_curated,chain_type,central_kitchen,premade_risk,price_avg,investor_info")
    cur = {r["id"]: r for r in rests}
    P = core.pipeline_common()
    brand_index = build_brand_index(rests, P)
    relations = build_relations(findings, brand_index, P)

    label_patches = defaultdict(dict)
    decisions = []
    reverify = []

    for (rid, fld), rows in sorted(grouped.items()):
        if fld in ENUM_FIELDS:
            dec = resolve_enum(fld, rows)
        elif fld in INFO_FIELDS:
            dec = resolve_info(fld, rows)
        elif fld in FACT_FIELDS:
            dec = resolve_fact(fld, rows)
        else:
            continue
        nowv = (cur.get(rid) or {}).get(fld)
        store_name = (cur.get(rid) or {}).get("name", "")
        evidence_text = " ".join((r.get("reason") or "") + " " + str(r.get("value") or "")
                                 for r in rows)

        # 可信候选值（conf≥0.8），用于防 flap（仅信息字段；枚举 hold 必须保留以补第2源）
        cred_rows = [r for r in rows if float(r.get("confidence") or 0) >= 0.8]
        if fld == "price_avg":
            credible_vals = {int(round(float(r["value"]))) for r in cred_rows
                             if _is_num(r.get("value"))}
        elif fld == "investor_info":
            credible_vals = {(r.get("value") or "").strip() for r in cred_rows}
        else:
            credible_vals = set()

        # 防 flap（仅信息字段）：现值已在可信候选中 → 保持，不在等信度值间来回改
        if fld in INFO_FIELDS and nowv is not None and nowv in credible_vals:
            dec = {"action": "none", "value": None, "why": "现值已在可信候选中，保持"}

        # 防错一：investor 点名【非关联】别家在库品牌（且无本店）= 错挂 → hold；
        # 点名母/子/姐妹/合作品牌（在 relations 内）或仅自证缺失 → 放行
        # （运营公司本名常与品牌不同，集团子品牌也只写母公司）。
        if fld == "investor_info" and dec.get("action") == "apply" and dec.get("value"):
            if not self_present(store_name, dec["value"], P):
                named = named_other_brands(dec["value"], brand_index, rid, P)
                unrelated = named - relations.get(rid, set())
                if unrelated:
                    dec = {"action": "hold", "value": None,
                           "why": f"investor 点名非关联别家「{sorted(unrelated)[0]}」、未出现本店，疑似错挂"}
        # 防错二：price 证据未出现本店品牌，或相对存量极端偏离 → hold
        if fld == "price_avg" and dec.get("action") == "apply":
            if not self_present(store_name, evidence_text, P):
                dec = {"action": "hold", "value": None,
                       "why": "price 证据未出现本店品牌，疑似错挂"}
            elif nowv is not None and price_implausible(dec["value"], nowv):
                dec = {"action": "hold", "value": None,
                       "why": f"price {dec['value']} 相对存量 {nowv} 极端偏离，疑似错挂"}

        rec = {"rid": rid, "field": fld, "decision": dec["action"],
               "value": dec.get("value"), "current": nowv, "why": dec.get("why"),
               "urls": sorted({r.get("source_url") for r in rows
                               if str(r.get("source_url", "")).startswith("http")})[:5]}
        decisions.append(rec)

        if dec["action"] in ("apply_hard", "apply_clear", "apply") and dec.get("value") is not None:
            # data_gate 校验该值
            issues = gate.validate({fld: dec["value"]}, schema_for(fld))
            if any(x["level"] == "error" for x in issues):
                rec["decision"] = "hold"
                rec["why"] += "；gate 校验失败：" + ",".join(x["detail"] for x in issues)
                reverify.append({"rid": rid, "name": (cur.get(rid) or {}).get("name"),
                                 "field": fld, "hard_value": dec.get("value"),
                                 "reason": rec["why"]})
                continue
            if nowv != dec["value"]:
                label_patches[rid][fld] = dec["value"]
        elif dec["action"] == "hold":
            hv = dec.get("hard_value") or dec.get("value")
            reverify.append({"rid": rid, "name": (cur.get(rid) or {}).get("name"),
                             "field": fld, "hard_value": hv, "reason": dec.get("why")})

    # 精选重算（硬规则）。closed 直接采信平台状态；确认/高 采信 DB 标签。
    curated_off = []
    for r in rests:
        if not r.get("is_curated"):
            continue
        rid = r["id"]
        if r.get("status") == "closed":
            curated_off.append((rid, "已关店，移出精选"))
        elif r.get("central_kitchen") == "确认":
            curated_off.append((rid, "中央厨房确认，移出精选"))
        elif r.get("premade_risk") == "高":
            curated_off.append((rid, "预制风险高，移出精选"))
    for rid, why in curated_off:
        label_patches[rid]["is_curated"] = False
        label_patches[rid]["curate_reason"] = why

    # chain_review：精选中的大型/资本化连锁，若独立食客口味声音 <2 → 交 ML 门，不自动改
    reviews = core.fetch_all("reviews",
        "restaurant_id,is_verified_diner,author_name,source_platform")
    diner_voices = defaultdict(set)
    for rv in reviews:
        if rv.get("is_verified_diner") and rv.get("author_name"):
            diner_voices[rv["restaurant_id"]].add(rv["author_name"])
    chain_review = []
    for r in rests:
        if r.get("is_curated") and r.get("chain_type") in ("大型连锁", "资本化连锁"):
            nv = len(diner_voices.get(r["id"], set()))
            if nv < 2:
                chain_review.append({"rid": r["id"], "name": r["name"],
                                     "chain_type": r.get("chain_type"),
                                     "independent_diner_voices": nv,
                                     "reason": "大型/资本化连锁且独立食客口味声音<2，交ML门复核"})

    plan = {
        "label_patches": {str(k): v for k, v in label_patches.items()},
        "curated_off": [{"rid": rid, "reason": w} for rid, w in curated_off],
        "reverify": reverify,
        "chain_review": chain_review,
        "decisions": decisions,
    }
    return plan


def apply_plan(plan):
    ts = time.strftime("%Y-%m-%dT%H:%M")
    n_patch = n_err = 0
    decpath = LEDGER / f"gate_decisions_{ts.replace(':', '-').replace('T', '_')}.jsonl"
    with decpath.open("w", encoding="utf-8") as fh:
        for rid_s, patch in plan["label_patches"].items():
            rid = int(rid_s)
            r = core.req("PATCH", f"/restaurants?id=eq.{rid}", json=patch)
            ok = r.status_code in (200, 204)
            n_patch += 1 if ok else 0
            n_err += 0 if ok else 1
            back = core.fetch_all("restaurants",
                "id," + ",".join(patch.keys()), extra=f"id=eq.{rid}")
            fh.write(json.dumps({"rid": rid, "patch": patch, "http": r.status_code,
                                 "readback": back[0] if back else None},
                                ensure_ascii=False) + "\n")
            if not ok:
                core.log("error", "gate patch failed", rid=rid, http=r.status_code)
    return n_patch, n_err, decpath


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    plan = build_plan()

    # 始终刷新 worklist（最新全量快照）
    (LEDGER / "reverify_worklist.json").write_text(
        json.dumps({"generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "items": plan["reverify"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    (LEDGER / "chain_review_worklist.json").write_text(
        json.dumps({"generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "items": plan["chain_review"]}, ensure_ascii=False, indent=1), encoding="utf-8")

    n_stores = len(plan["label_patches"])
    n_fields = sum(len(v) for v in plan["label_patches"].values())
    report = {
        "apply": a.apply,
        "stores_to_patch": n_stores, "fields_to_patch": n_fields,
        "curated_off": len(plan["curated_off"]),
        "reverify_holds": len(plan["reverify"]),
        "chain_review": len(plan["chain_review"]),
        "elapsed_s": round(time.time() - t0, 1),
    }
    if a.apply:
        n_patch, n_err, decpath = apply_plan(plan)
        report["patched_stores"] = n_patch
        report["patch_errors"] = n_err
        report["decision_ledger"] = str(decpath)
        core.notify.info("gate_apply 已写库：" + json.dumps(report, ensure_ascii=False),
                         key="gate_apply")
    else:
        core.notify.info("gate_apply dry：" + json.dumps(report, ensure_ascii=False),
                         key="gate_apply_dry")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n=== 抽样：待挂标签（前12店）===")
    for rid_s, patch in list(plan["label_patches"].items())[:12]:
        print(" ", rid_s, patch)
    print("\n=== 抽样：取证窗口 reverify（前10）===")
    for x in plan["reverify"][:10]:
        print(" ", x["rid"], x["field"], x.get("hard_value"), "|", x["reason"][:60])
    print("\n=== chain_review（交ML门，不自动改）===")
    for x in plan["chain_review"][:15]:
        print(" ", x["rid"], x["name"][:20], x["chain_type"], "独立食客声音", x["independent_diner_voices"])


if __name__ == "__main__":
    main()

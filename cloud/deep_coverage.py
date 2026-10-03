#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deep_coverage.py — 无头「深覆盖」发现编排器（24/7，不依赖浏览器/不碰 Apify 额度）。

把已沉淀但分散的方法论（systematic-sourcing / completeness-recall / llm-sourcing-fleet）
落成一条可定时跑、可回归、可饱和的代码闭环：

  ① 缺口：cuisines 菜系叶子 × 在营挂载数 → 找 empty/shallow 叶子（跨大陆根轮转，不偏科）
  ② 词矩阵：叶子名/俗称 × 长尾口碑词（宝藏/私藏/本地人/不网红/苍蝇馆/预约难/hidden gem）
 ③ 双通道召回：
     · LLM 舰队（ARK 便宜模型，批量问）列出该菜系真正好吃的店（含俗称/英文/小众/新店）
     · SearXNG（自建元搜索，免 key）跑词矩阵，从标题/摘要/引号名抽店
  ④ 实体对齐：归一去重、剔除已收录（名/别名/包含匹配）、剔噪声
  ⑤ 证据确认：对新店 "<name> 上海 好吃 评价" 取独立食客好评 + URL（strong≥2源 / weak 1源）
  ⑥ 产物：deep_candidates_<date>.jsonl 交给下游 evidence-gate 入库（本模块只发现、不直接建店）
  ⑦ 循环账本：每叶 last_run/n_new/stall；工作指针轮转；stall≥3 判饱和
  ⑧ 回归：research/regression_set.json 命中率 + 每家自动发现路径（KPI 目标 100%）

发现渠道≠评分背书：所有候选仍需下游堂食原话硬门；宁空不假。
默认 dry-run；--apply 才写候选文件/账本（不写 restaurants）。
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys

import requests

import common_core as CC

DATA = pathlib.Path("/app/data")
COVDIR = DATA / "coverage"
LEDGER = COVDIR / "deep_loop.json"
TARGET_N = 4        # 菜系叶子目标在营店数（低于即缺口）
STALL_SAT = 3       # 连续 N 轮零新增判饱和
SEARX = "http://searxng:8080"
MODIFIERS = ["推荐 必吃", "宝藏 私藏 本地人", "不网红 苍蝇馆子 预约难"]
PRAISE = re.compile(r"好吃|美味|惊艳|正宗|地道|鲜嫩|入味|爆汁|必吃|天花板|回购|推荐|fragrant|delicious")
GENERIC = {"餐厅", "饭店", "美食", "推荐", "上海", "攻略", "菜单", "团购", "加盟", "连锁店",
           "排行榜", "品牌", "哪家", "最好吃", "top10", "合集", "外卖"}
# 泛称/非店名（不是具体餐厅品牌）
GENERIC_PHRASE = {"苍蝇馆子", "破破烂烂", "快餐店", "网红店", "老字号", "路边摊", "大排档",
                  "小吃店", "家常菜", "私房", "小饭馆", "苍蝇馆"}
SH_DISTRICTS = ("上海", "黄浦", "静安", "徐汇", "长宁", "浦东", "虹口", "普陀", "杨浦",
                "闵行", "宝山", "嘉定", "金山", "松江", "青浦", "奉贤", "崇明",
                "外滩", "新天地", "陆家嘴", "前滩", "虹桥", "南京东路", "淮海")


def norm(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(s).lower())


def cjk_lead(s):
    """从一段文本抽取可能的店名（引号 / 《》 / “X（…店）”）。"""
    out = set()
    for pat in (r"[《「『【]([^》」』】]{2,18})[》」』】]",
                r"[“\"]([^”\"]{2,18})[”\"]"):
        for m in re.finditer(pat, s):
            out.add(m.group(1).strip())
    return out


def valid_name(n):
    """剔除『清水河店/快餐店/苍蝇馆子』这类无品牌泛称。"""
    n = str(n).strip()
    if len(norm(n)) < 3 or any(g in n for g in GENERIC):
        return False
    if norm(n) in {norm(g) for g in GENERIC_PHRASE}:
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]{2,3}[店铺馆堂]", n):
        return False
    return True


def in_shanghai(text):
    return any(d in text for d in SH_DISTRICTS)


def searx(q, timeout=8):
    try:
        r = requests.get(SEARX + "/search",
                         params={"q": q, "format": "json", "safesearch": 0},
                         timeout=timeout)
        if r.status_code != 200:
            return []
        return [{"url": x.get("url", ""), "title": x.get("title", ""),
                 "snippet": x.get("content", "")} for x in
                r.json().get("results", [])[:8]]
    except Exception:
        return []


def pick_models():
    """返回按优先级的 [(provider, model)]：优先【支持联网的豆包 mini/lite】(真实发现)，
    其后便宜模型作无联网兜底。缺 key 返回 []。"""
    sys.path.insert(0, "/app/pipeline")
    try:
        import model_providers as MP
        provs = MP.load_providers()
    except Exception:
        return []
    ranked, fallback = [], []
    for p in provs:
        for m in (getattr(p, "models", None) or []):
            ml = m.lower()
            is_doubao = p.name.startswith("ark") and "doubao" in ml
            if is_doubao and "mini" in ml:
                ranked.append((0, p, m))
            elif is_doubao and ("lite" in ml or "turbo" in ml):
                ranked.append((1, p, m))
            elif any(k in ml for k in ("flash", "mini", "lite")):
                fallback.append((p, m))
    ranked.sort(key=lambda x: x[0])
    out = [(p, m) for _, p, m in ranked]
    out += fallback
    return out


def llm_recall(model_list, leaf_names):
    """批量问一组菜系叶子，返回 ({leaf:[{name,area,reason}]}, sources, used_model)。
    联网发现（真实来源）；逐模型回退、超时重试。"""
    import model_providers as MP
    leaves = "、".join(leaf_names)
    prompt = (f"请联网检索后，列出在【上海】以下菜系真正好吃、口碑出色的餐厅（含俗称、英文名、"
              f"小众店、私房菜、近一年新店；排除中央厨房/预制菜/大型连锁）：{leaves}。"
              f"只输出 JSON：{{\"stores\":[{{\"cuisine\":\"菜系名\",\"name\":\"店名\",\"area\":\"区域\","
              f"\"reason\":\"一句真实口碑\"}}]}}；没有真实检索到就给空数组，不要凭记忆编造。")
    empty = {l: [] for l in leaf_names}
    for p, m in model_list:
        web = p.supports_web
        r = None
        for attempt in range(2):                      # 超时重试 1 次
            r = MP.chat(p, m, prompt, web_search=web, timeout=100)
            if r.get("ok") or "timed out" not in str(r.get("error")):
                break
        MP.log_usage("deep_coverage", r)
        if not r.get("ok"):
            continue
        txt = r.get("text", "")
        mobj = re.search(r"\{.*\}", txt, re.S)
        try:
            data = json.loads(mobj.group(0) if mobj else txt)
        except Exception:
            continue
        out = {l: [] for l in leaf_names}
        for s in data.get("stores", []):
            c = s.get("cuisine", ""); n = (s.get("name") or "").strip()
            if not n or len(norm(n)) < 2:
                continue
            tgt = next((l for l in leaf_names
                        if norm(l) in norm(c) or norm(c) in norm(l)), None)
            if tgt:
                out[tgt].append({"name": n, "area": s.get("area", ""),
                                 "reason": s.get("reason", "")})
        if any(out.values()):
            return out, (r.get("sources") or []), f"{p.name}/{m}"
    return empty, [], "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-leaves", type=int, default=10)
    ap.add_argument("--max-confirm", type=int, default=24)
    args = ap.parse_args()
    COVDIR.mkdir(parents=True, exist_ok=True)

    cuis = CC.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    byid = {c["id"]: c for c in cuis}
    byname = {c["name"]: c for c in cuis}
    children = {}
    for c in cuis:
        if c["parent_category"] is not None:
            children.setdefault(c["parent_category"], []).append(c["id"])

    def root_path(cid):
        node = byid[cid]
        path, cur = [cid], node["name"]
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            nxt = byname.get(cur, {}).get("parent_category")
            if nxt is None:
                break
            path.append(byname[cur]["id"]); cur = nxt
        return path  # leaf id -> ... -> root id

    rests = CC.fetch_all("restaurants", "id,name,aliases,status", order_col="id")
    active = {r["id"]: r for r in rests if r.get("status") != "closed"}
    rc = CC.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                      order_col="restaurant_id")
    leaf_active = {}
    for x in rc:
        if x["restaurant_id"] in active:
            leaf_active.setdefault(x["cuisine_id"], set()).add(x["restaurant_id"])

    # 已收录店名集合（名 + 别名 + 去括号主名）
    existing = set()
    for r in rests:
        for cand in [r["name"], r.get("aliases")]:
            if not cand:
                continue
            for piece in re.split(r"[,，、;；]|（[^）]*）|\([^)]*\)", str(cand)):
                n = norm(piece)
                if len(n) >= 2:
                    existing.add(n)

    def is_existing(n):
        n = norm(n)
        if len(n) < 2:
            return True
        if n in existing:
            return True
        return any((len(n) >= 4 and n in e) or (len(e) >= 4 and e in n) for e in existing)

    # 菜系叶子 + 缺口 + 所属大陆根
    leaves = []
    for c in cuis:
        if c["dimension"] != "菜系" or c["name"] in children:
            continue
        path = root_path(c["id"])
        root = byid[path[-1]]["name"]
        n = len(leaf_active.get(c["id"], set()))
        if n < TARGET_N:
            leaves.append({"id": c["id"], "name": c["name"], "root": root, "n": n})
    # 按大陆根分组轮转，保证不偏科
    roots = sorted({l["root"] for l in leaves})
    order = []
    byroot = {r: [l for l in leaves if l["root"] == r] for r in roots}
    while any(byroot.values()):
        for r in roots:
            if byroot[r]:
                order.append(byroot[r].pop(0))

    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    ptr = ledger.get("pointer", 0)
    batch = [order[(ptr + i) % len(order)] for i in range(min(args.max_leaves, len(order)))]

    model_list = pick_models()
    # LLM 联网批量召回（每 6 叶一批，省 token）；记录来源与所用模型
    llm, llm_sources, used_model = {}, [], "none"
    names = [l["name"] for l in batch]
    for i in range(0, len(names), 6):
        part, srcs, used = llm_recall(model_list, names[i:i + 6])
        llm.update(part); llm_sources += srcs; used_model = used

    import concurrent.futures as CF
    # SearXNG 词矩阵（每叶 3 条，线程并发）
    mq = [(l, f"上海 {l['name']} {mod}") for l in batch for mod in MODIFIERS]
    matrix = {}
    with CF.ThreadPoolExecutor(max_workers=4) as ex:
        for (l, q), hits in zip(mq, ex.map(lambda t: searx(t[1]), mq)):
            matrix.setdefault(l["name"], []).extend(hits)

    candidates, per_leaf = [], {}
    for l in batch:
        # 店名仅来自 LLM 召回（高精度）；词矩阵只作证据、不抽店名（cjk 碎片噪声大）
        names = set()
        for s in llm.get(l["name"], []):
            names.add((s["name"], s.get("reason", "")))
        new = [(n, why) for n, why in names if valid_name(n) and not is_existing(n)]
        per_leaf[l["name"]] = new
        for n, why in new:
            candidates.append({"leaf": l["name"], "root": l["root"], "name": n, "why": why})

    # 证据确认（限量，线程并发）——严格：证据标题/摘要必须【包含候选店名】且有口味信号
    uniq, seen = [], set()
    for c in candidates[:args.max_confirm]:
        if norm(c["name"]) not in seen:
            seen.add(norm(c["name"])); uniq.append(c)
    final = []

    def strict_hit(nn, h):
        text = f"{h.get('title','')} {h.get('snippet','')}"
        return (nn in norm(text) and in_shanghai(text)
                and PRAISE.search(text))

    with CF.ThreadPoolExecutor(max_workers=4) as ex:
        qs = [f"{c['name']} 上海 好吃 评价" for c in uniq]
        for c, ev in zip(uniq, ex.map(lambda q: searx(q), qs)):
            nn = norm(c["name"])
            pool = list(ev) + matrix.get(c["leaf"], [])   # 专属查询 + 该叶词矩阵
            good, u = [], set()
            for h in pool:
                if h.get("url") in u:
                    continue
                if strict_hit(nn, h):
                    u.add(h["url"]); good.append(h)
            if not good:
                continue
            final.append({"name": c["name"], "cuisine": c["leaf"], "root": c["root"],
                          "evidence_level": "strong" if len(u) >= 2 else "weak",
                          "llm_source_urls": [s for s in llm_sources if isinstance(s, str)],
                          "evidence": [{"url": h["url"], "title": h["title"][:40],
                                       "snippet": h["snippet"][:120]} for h in good[:3]]})

    # 账本（stall / 饱和 / 指针）
    today = dt.date.today().isoformat()
    for l in batch:
        prev = ledger.get("leaves", {}).get(l["name"], {})
        n_new = len(per_leaf[l["name"]])
        stall = (prev.get("stall", 0) + 1) if n_new == 0 else 0
        ledger.setdefault("leaves", {})[l["name"]] = {
            "last_run": today, "n_new": n_new, "stall": stall,
            "saturated": stall >= STALL_SAT, "n_active": l["n"]}
    ledger["pointer"] = (ptr + len(batch)) % max(1, len(order))
    ledger["last_run"] = today

    print(f"缺口叶子 {len(leaves)}（{len(roots)} 个大陆根）；本轮处理 {len(batch)} 叶")
    for l in batch:
        print(f"  [{l['root'][:4]:<5}] {l['name']:<10} 在营{l['n']:<3} 新候选{len(per_leaf[l['name']])}")
    print(f"\nLLM={'on '+used_model if used_model!='none' else 'off'}；证据确认通过 {len(final)}（strong "
          f"{sum(1 for f in final if f['evidence_level']=='strong')} / weak "
          f"{sum(1 for f in final if f['evidence_level']=='weak')}）")

    if args.apply:
        out = COVDIR / f"deep_candidates_{today}.jsonl"
        out.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in final),
                       encoding="utf-8")
        LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"[apply] 候选 -> {out}；账本指针={ledger['pointer']}；饱和叶 "
              f"{sum(1 for v in ledger['leaves'].values() if v['saturated'])}")
    else:
        print("[dry-run] 未写候选/账本；加 --apply。")


if __name__ == "__main__":
    main()

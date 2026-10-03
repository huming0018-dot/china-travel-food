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
import time

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


def _searx_once(q, timeout):
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


def searx(q, timeout=8, retries=1):
    """零结果（后端引擎瞬时抖动/请求失败）即时重试一次，短退避；仍空则如实返回 []。"""
    hits = _searx_once(q, timeout)
    attempt = 0
    while not hits and attempt < retries:
        attempt += 1
        time.sleep(2.5)
        hits = _searx_once(q, timeout)
    return hits


def fetch_fulltext(url, max_chars=4200, timeout=12):
    """抓整页正文（去 script/style），供全文核验。失败返回 ""。"""
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36")})
        if r.status_code != 200 or not r.text:
            return ""
        html = r.text
        try:
            html = html.encode(r.encoding or "utf-8", "ignore").decode("utf-8", "ignore")
        except Exception:
            pass
        html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
        try:
            from bs4 import BeautifulSoup
            txt = BeautifulSoup(html, "html.parser").get_text(" ")
        except Exception:
            txt = re.sub(r"(?s)<[^>]+>", " ", html)
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt[:max_chars]
    except Exception:
        return ""


# 易混/外来叶子的中文同义锚点（norm 口径）。只补"该品类真正的叫法"。
LEAF_ALIASES = {
    "fishchips": ["炸鱼薯条", "炸魚薯條", "英式炸鱼"],
    "diner美式简餐": ["美式简餐", "美式餐厅", "美式餐廳", "美式家常", "diner"],
    "couscous库斯库斯": ["库斯库斯", "庫斯庫斯", "古斯米", "蒸粗麦粉", "北非小米"],
    "bobotie马来风味派": ["波波提", "bobotie", "南非咖喱派", "马来风味派"],
    "empanada馅饼chimichurri": ["恩潘纳达", "empanada", "肉馅卷饼", "阿根廷馅饼", "chimichurri", "青酱"],
    "bbq烧烤": ["烧烤", "bbq", "烤肉"],
}


def leaf_anchors(name):
    """从叶子名拆出主题锚点（norm）：全名 + 中文段 + 英文段 + 同义映射。"""
    anchors = {norm(name)}
    cjk = re.findall(r"[\u4e00-\u9fff]+", str(name))
    lat = re.findall(r"[a-zA-Z][a-zA-Z0-9]+", str(name))
    for c in cjk:
        if len(c) >= 2:
            anchors.add(norm(c))
    for w in lat:
        if len(w) >= 4:
            anchors.add(w.lower())
    for extra in LEAF_ALIASES.get(norm(name), []):
        anchors.add(norm(extra))
    return {a for a in anchors if len(a) >= 2}


def on_topic(name, text):
    """命中页是否真的在讲该叶子（而非泛化"上海必吃"榜单）。"""
    t = norm(text)
    return any(a in t for a in leaf_anchors(name))


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


def llm_extract(model_list, leaf, hits):
    """有依据的店名抽取：把该叶 SearXNG 命中的标题/摘要喂给便宜模型，
    只抽取【真正出现在文本里、落在上海】的具体餐厅名。模型不做自由回忆 → 不幻觉。
    返回 ([{name,area,reason}], used_model)。"""
    import model_providers as MP
    lines, total = [], 0
    for i, h in enumerate(hits[:24]):
        t = (h.get("title", "") + " " + h.get("snippet", "")).strip().replace("\n", " ")
        if not t:
            continue
        t = t[:180]
        lines.append(f"{i+1}. {t}")
        total += len(t)
        if total > 5200:
            break
    blob = "\n".join(lines)
    if len(blob) < 20:
        return [], "none"
    prompt = (f"下面是关于【上海 {leaf}】的搜索结果原文（已编号，且均与该品类相关）。"
              f"请只依据这些文字，抽取其中【被明确当作{leaf}来介绍、位于上海】的具体餐厅/店铺专名"
              f"（含俗称、英文名、小众店、私房菜）。排除：只是同页顺带提到的其他菜系名店、"
              f"泛称（苍蝇馆子/老字号/网红店/小吃店等）、中央厨房/预制菜/大型连锁、非餐饮、外地店。"
              f"只输出 JSON：{{\"stores\":[{{\"name\":\"店名\",\"area\":\"区域或空\","
              f"\"dish\":\"文中它家的该品类代表菜或空\",\"is_match\":true}}]}}；"
              f"名字与该品类的关联必须能在原文找到，拿不准就不要列，禁止凭记忆补充。\n\n{blob}")
    for p, m in model_list:
        r = MP.chat(p, m, prompt, web_search=False, timeout=70)
        MP.log_usage("deep_coverage", r)
        if not r.get("ok"):
            continue
        mobj = re.search(r"\{.*\}", r.get("text", ""), re.S)
        try:
            data = json.loads(mobj.group(0) if mobj else r["text"])
        except Exception:
            continue
        out = []
        for s in data.get("stores", []):
            n = (s.get("name") or "").strip()
            if n and len(norm(n)) >= 2 and s.get("is_match", True):
                out.append({"name": n, "area": s.get("area", ""),
                            "reason": s.get("dish") or s.get("reason", "")})
        return out, f"{p.name}/{m}"
    return [], "none"


def verify_lead(model_list, name, leaf, urls):
    """全文核验门：抓候选 URL 整页，让便宜模型【只依据全文】判定——
    这是不是一家真实、在上海、被当作<leaf>经营、有具体菜名与真实食客好评的店。
    一次解决地名误抽/榜单误配/泛化好评等整类问题。
    返回 {verdict:admit/hold/reject, in_shanghai, is_category, dishes, praise,
          complaint, is_chain, is_place, n_urls}。"""
    pages, used_urls, total = [], [], 0
    for u in urls[:3]:
        ft = fetch_fulltext(u)
        if ft and norm(name) in norm(ft):
            pages.append(f"【来源{len(pages)+1}】{u}\n{ft}")
            used_urls.append(u)
            total += len(ft)
            if total > 4600:
                break
    base = {"verdict": "hold", "in_shanghai": False, "is_category": False,
            "dishes": [], "praise": "", "complaint": "", "is_chain": False,
            "is_place": False, "n_urls": len(used_urls), "urls": used_urls}
    if not pages:
        return base
    import model_providers as MP
    prompt = (f"你是严格的美食编辑。下面是关于候选名「{name}」、品类「上海 {leaf}」的网页全文。"
              f"请只依据全文判定，不要用任何外部记忆，输出 JSON：\n"
              f"{{\"is_place_or_person\":false,\"is_real_restaurant\":true,\"in_shanghai\":true,"
              f"\"is_category\":true,\"is_chain_or_premade\":false,\"dishes\":[\"具体菜名\"],\n"
              f"\"praise\":\"一句真实食客好评原话或空\",\"complaint\":\"一句真实食客差评原话或空\","
              f"\"verdict\":\"admit/hold/reject\"}}\n判定标准：①「{name}」若是地名/人名/节目名/"
              f"泛称→is_place_or_person=true 且 reject；②必须是当前在营、位于上海的餐厅；"
              f"③全文必须把它当作「{leaf}」介绍（is_category）；④至少1个具体菜名；"
              f"⑤有真实食客好评才可 admit；证据不足/疑似关店/连锁预制→hold 或 reject。\n\n"
              + "\n\n".join(pages))
    for p, m in model_list:
        r = MP.chat(p, m, prompt, web_search=False, timeout=80)
        MP.log_usage("deep_coverage_verify", r)
        if not r.get("ok"):
            continue
        mobj = re.search(r"\{.*\}", r.get("text", ""), re.S)
        try:
            d = json.loads(mobj.group(0) if mobj else r["text"])
        except Exception:
            continue
        return {
            "verdict": d.get("verdict", "hold"),
            "in_shanghai": bool(d.get("in_shanghai")),
            "is_category": bool(d.get("is_category")),
            "dishes": [x for x in (d.get("dishes") or []) if x][:5],
            "praise": d.get("praise", "") or "",
            "complaint": d.get("complaint", "") or "",
            "is_chain": bool(d.get("is_chain_or_premade")),
            "is_place": bool(d.get("is_place_or_person")),
            "n_urls": len(used_urls), "urls": used_urls}
    return base


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
    import concurrent.futures as CF
    # ① SearXNG 词矩阵（每叶 3 条，线程并发）——真实搜索结果，发现的事实底座
    mq = [(l, f"上海 {l['name']} {mod}") for l in batch for mod in MODIFIERS]
    raw_matrix = {}
    with CF.ThreadPoolExecutor(max_workers=4) as ex:
        for (l, q), hits in zip(mq, ex.map(lambda t: searx(t[1]), mq)):
            raw_matrix.setdefault(l["name"], []).extend(hits)
    # 只保留【主题相关】命中：剔除非该菜系的泛化"上海必吃"榜单（按 URL 去重）
    matrix = {}
    for l in batch:
        seen, rel = set(), []
        for h in raw_matrix.get(l["name"], []):
            u = h.get("url", "")
            if u in seen:
                continue
            seen.add(u)
            if on_topic(l["name"], h.get("title", "") + " " + h.get("snippet", "")):
                rel.append(h)
        matrix[l["name"]] = rel

    # ② 有依据抽取店名：LLM 从该叶命中原文抽取 + 确定性括号/引号抽取（双路）
    candidates, per_leaf, used_model = [], {}, "none"
    for l in batch:
        hits = matrix.get(l["name"], [])
        names = set()
        extracted, used_model = llm_extract(model_list, l["name"], hits)
        for s in extracted:
            names.add((s["name"], s.get("reason", "")))
        for h in hits:
            for n in cjk_lead(h.get("title", "") + " " + h.get("snippet", "")):
                names.add((n, ""))
        new = [(n, why) for n, why in names if valid_name(n) and not is_existing(n)]
        per_leaf[l["name"]] = new
        for n, why in new:
            candidates.append({"leaf": l["name"], "root": l["root"], "name": n, "why": why})

    # 证据确认（限量）——全页抓取 + LLM 全文核验门（替代 snippet 正则，整类解决误报）
    uniq, seen = [], set()
    for c in candidates[:args.max_confirm]:
        if norm(c["name"]) not in seen:
            seen.add(norm(c["name"])); uniq.append(c)

    def gather(c, ev):
        nn = norm(c["name"])
        # tie：主题相关矩阵中含店名的页；再补含店名的专属查询页
        tie = [h for h in matrix.get(c["leaf"], [])
               if nn in norm(h.get("title", "") + " " + h.get("snippet", ""))]
        extra = [h for h in ev
                 if nn in norm(h.get("title", "") + " " + h.get("snippet", ""))]
        urls, u = [], set()
        for h in tie + extra:
            if h.get("url") and h["url"] not in u:
                u.add(h["url"]); urls.append(h["url"])
        return tie, urls

    with CF.ThreadPoolExecutor(max_workers=3) as ex:
        qs = [f"{c['name']} 上海 好吃 评价" for c in uniq]
        evlist = list(ex.map(lambda q: searx(q), qs))
        tasks = []
        for c, ev in zip(uniq, evlist):
            tie, urls = gather(c, ev)
            if tie and urls:
                tasks.append((c, urls))
        verdicts = list(ex.map(lambda t: (t[0], verify_lead(model_list, t[0]["name"],
                                                            t[0]["leaf"], t[1])), tasks))

    final = []
    for c, v in verdicts:
        if v.get("is_place") or v.get("is_chain"):
            continue
        if not (v.get("verdict") == "admit" and v.get("in_shanghai")
                and v.get("is_category") and v.get("dishes") and v.get("praise")):
            continue
        strong = v.get("n_urls", 0) >= 2
        final.append({"name": c["name"], "cuisine": c["leaf"], "root": c["root"],
                      "evidence_level": "strong" if strong else "weak",
                      "dishes": v["dishes"], "praise": v["praise"],
                      "complaint": v["complaint"],
                      "evidence": [{"url": u} for u in v.get("urls", [])[:3]]})

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

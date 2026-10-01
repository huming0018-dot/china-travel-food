#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chef_snowball_run.py — HAE 主厨关系图「雪球辐射」搜索机（L0.5 假设层）。

与 fleet_grid_run（菜系叶子网格，按类目横扫）互补，构成第二个抽样框：
  从【锚点主厨/主理人】出发，沿固定关系边做图遍历 BFS——
    师徒(teacher) / 同门·直管副牌·长期合作(worked_at,career_period,related_to) /
    同榜单·同节目·同台(list_member,award,show_appearance) / 主理参与餐厅(founded)
  把【带证据/已确认】的新节点再入队，多轮自动辐射，直到边际增益收敛自动判停。

为什么需要它：网格/关键词按"类目"捞店，捞不到私房菜、主厨副牌、圈层口碑店；
  这些店在"主厨关系图"上是网络可达的（用户反复点名的漏店多属此类）。

防幻觉漂移（硬约束）：
  1. 只对 带来源URL 或 已确认 的节点继续扩散；纯模型无证据回忆只入假设、不入队。
  2. 实体按 cjk_norm 去重；同名异址分店保留为不同节点（用地址/来源区分）。
  3. 输出强制结构化 JSON + 显式 null + 来源；模型一致只抬先验，晋升走 hae_engine 闸门。
  4. L1–L4 是"锚点网络距离/出处"标签（proposed_by.anchor_tier），绝不进 score_taste。
  5. 五维 why 中：传承=可晋升事实；技法/食材/调味/创新=带源 profile，口味仍由真实食客定。

状态（断点幂等）：FOOD_DATA_DIR/hae/chef_snowball_state.json
用法：
  python3 chef_snowball_run.py --seed-json anchors.json --apply --rounds 3
  python3 chef_snowball_run.py --catchup --apply        # 跑到收敛
  python3 chef_snowball_run.py --status
无 key/无适配器：自动降级（打印、不中断），与 fleet_grid 一致。
"""
import argparse
import collections
import datetime
import json
import os
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402

DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
HAE_DIR = os.path.join(DATA, "hae")
RECALL_DIR = os.path.join(HAE_DIR, "chef_snowball_recall")
STATE_FILE = os.path.join(HAE_DIR, "chef_snowball_state.json")
PROBE_VERSION = "chefsnowball-v1"

# 收敛参数
PATIENCE = int(os.environ.get("HAE_SNOWBALL_PATIENCE", "2"))   # 连续 N 轮低增益则停
MIN_GAIN = int(os.environ.get("HAE_SNOWBALL_MIN_GAIN", "1"))   # 每轮新增证据节点下限
MAX_FRONTIER_PER_ROUND = int(os.environ.get("HAE_SNOWBALL_BREADTH", "6"))

# 雪球关系边 → hae VALID_RELATION
EDGE_HINT = ("teacher(师承:老师/徒弟), worked_at/career_period(同门/直管副牌/长期合作), "
             "list_member/award/show_appearance(同榜单/同节目/同台), founded(主理/参与的餐厅与新店)")

_PROBE_SCHEMA = {
    "anchor": "<锚点主厨名>",
    "neighbors": [
        {
            "subject_type": "chef / owner / restaurant / brand / group",
            "subject_name": "被辐射到的人名/店名/品牌（必须）",
            "relation": "teacher / worked_at / career_period / related_to / list_member / "
                        "award / show_appearance / founded / signature_dish",
            "object": "关系对象（餐厅名/品牌/老师名），没有则 null",
            "when": "时间（年/起止），没有则 null",
            "anchor_tier": "L1官方核心 / L2直属 / L3同榜圈层 / L4口碑",
            "why": {
                "technique": "技法功底，没有则 null",
                "ingredient": "食材逻辑，没有则 null",
                "flavor": "调味体系，没有则 null",
                "innovation": "创新表达，没有则 null",
                "lineage": "传承背书（师门/荣誉/品牌），没有则 null",
            },
            "address": "若是餐厅：地址（区分分店），否则 null",
            "status": "营业 / 迁址 / 关店 / 未知",
            "known": "知道 / 推断 / 不知道",
            "sources": ["来源 URL（有则必填）"],
        }
    ],
}


def probe_for_anchor(anchor):
    return (
        f"你是上海美食图鉴的【主厨圈层辐射引擎】。锚点主厨/主理人：「{anchor.get('name')}」"
        f"（已知 {json.dumps({k: anchor.get(k) for k in ('restaurant','tier','note') if anchor.get(k)}, ensure_ascii=False)}）。\n"
        f"沿这些关系边做圈层辐射：{EDGE_HINT}。\n"
        f"逐个 neighbor 输出：关系、对象、时间、anchor_tier(L1官方/L2直属/L3同榜/L4口碑)、"
        f"五维 why（技法/食材/调味/创新/传承，缺则 null）、餐厅地址（区分同名分店）、营业状态。\n"
        f"只输出你确实有把握或能由来源支撑的节点；没有线索就返回空数组并说明；"
        f"绝不虚构人名、店名、年份、师承。\n"
        f"【只输出如下 JSON，不要客套、不要 Markdown 代码块】：\n"
        f"{json.dumps(_PROBE_SCHEMA, ensure_ascii=False)}"
    )


# ---------------------------------------------------------------------------
def api_tasks():
    try:
        import model_providers as MP
    except Exception as e:
        return None, [f"model_providers import skip: {e}"]
    provs = MP.load_providers()
    if not provs:
        return None, ["无可用 API 适配器（缺 key），降级占位"]
    tasks = [(p, m) for p in provs for m in getattr(p, "models", [])]
    return (MP, tasks), []


def call_one(MP, p, m, prompt):
    try:
        r = MP.chat(p, m, prompt)
        r["identity"] = f"{p.name}/{m}"
        return r
    except Exception as e:
        return {"ok": False, "text": "", "sources": [], "identity": f"{p.name}/{m}",
                "error": f"{type(e).__name__}: {e}"}


def recall_anchor(anchor):
    info, msg = api_tasks()
    if info is None:
        return [], msg, {"anchor": anchor.get("name"), "results": []}
    MP, tasks = info
    prompt = probe_for_anchor(anchor)
    with ThreadPoolExecutor(max_workers=min(6, len(tasks))) as ex:
        futs = [ex.submit(call_one, MP, p, m, prompt) for (p, m) in tasks]
        results = [f.result() for f in futs]
    used = [r.get("identity") + ("" if r.get("ok") else " SKIP") for r in results] + msg
    raw = {"anchor": anchor.get("name"), "probe_version": PROBE_VERSION,
           "date": datetime.date.today().isoformat(),
           "results": [{"identity": r.get("identity"), "ok": r.get("ok"),
                        "web": r.get("web"), "text": r.get("text"),
                        "sources": r.get("sources"), "error": r.get("error")} for r in results]}
    return results, used, raw


def _extract_json(text):
    if not text:
        return None
    t = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    t = t.replace("```json", "").replace("```", "")
    a, b = t.find("{"), t.rfind("}")
    cand = t[a:b + 1] if a >= 0 and b > a else t
    for c in (cand, t):
        try:
            return json.loads(c)
        except Exception:
            try:
                return json.loads(re.sub(r",(\s*[}\]])", r"\1", c))
            except Exception:
                continue
    return None


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _clean(v):
    if isinstance(v, str):
        s = v.strip()
        if s and s not in ("null", "未知", "无", "None"):
            return s
    return None


def parse_neighbors(results):
    """聚合多模型返回 → {ekey: agg}。"""
    aggs = {}
    for r in results:
        if not r.get("ok"):
            continue
        data = _extract_json(r.get("text", ""))
        items = data.get("neighbors") or data.get("items") or [] if isinstance(data, dict) else (
            data if isinstance(data, list) else [])
        for it in items:
            if not isinstance(it, dict):
                continue
            name = _clean(it.get("subject_name"))
            if not name:
                continue
            ekey = C.cjk_norm(name)
            if not ekey:
                continue
            urls = [u for u in _as_list(it.get("sources")) if u.startswith("http")]
            urls += [u for u in (r.get("sources") or []) if isinstance(u, str) and u.startswith("http")]
            urls = list(dict.fromkeys(urls))
            agg = aggs.setdefault(ekey, {"names": [], "items": [], "models": [], "urls": []})
            if name not in agg["names"]:
                agg["names"].append(name)
            agg["items"].append(it)
            if r.get("identity"):
                agg["models"].append(r["identity"])
            for u in urls:
                if u not in agg["urls"]:
                    agg["urls"].append(u)
    return aggs


def _first(items, key):
    for it in items:
        c = _clean(it.get(key))
        if c:
            return c
    return None


def build_rows(aggs, anchor):
    today = datetime.date.today().isoformat()
    rows, enqueue = [], []
    for ekey, agg in aggs.items():
        name = _first(agg["items"], "subject_name") or agg["names"][0]
        stype = _first(agg["items"], "subject_type") or "chef"
        if stype not in ("chef", "owner", "restaurant", "brand", "group", "blogger", "list"):
            stype = "chef"
        rel = _first(agg["items"], "relation") or "related_to"
        obj = _first(agg["items"], "object")
        when = _first(agg["items"], "when")
        tier = _first(agg["items"], "anchor_tier") or "L3同榜圈层"
        tier = tier if tier.startswith("L") else "L3同榜圈层"
        addr = _first(agg["items"], "address")
        status_v = _first(agg["items"], "status") or "未知"
        why = next((it.get("why") for it in agg["items"]
                    if isinstance(it.get("why"), dict)), {})
        urls = agg["urls"]
        n_models = len(set(agg["models"]))

        whybits = [f"{k}={why[k]}" for k in ("technique", "ingredient", "flavor",
                                            "innovation", "lineage")
                   if isinstance(why.get(k), str) and _clean(why.get(k))]
        bits = [f"主厨雪球(锚点「{anchor.get('name')}」)", f"关系={rel}"]
        if obj: bits.append(f"对象={obj}")
        if when: bits.append(f"时间={when}")
        if addr: bits.append(f"地址={addr}")
        if status_v != "营业": bits.append(f"状态={status_v}")
        if whybits: bits.append("五维:" + "；".join(whybits))
        if not urls: bits.append("暂无来源URL，待取证")
        claim_text = "；".join(bits)

        conf = 0.30 + 0.06 * min(max(n_models - 1, 0), 2)
        if urls: conf += 0.10
        cap = 0.65 if (urls and any(
            (lambda u: C.source_kind(url=u) in ("official_guide", "media", "brand"))(u)
            for u in urls)) else 0.55
        conf = min(round(conf, 2), cap)

        row = {
            "subject_type": stype, "subject_name": name, "relation": rel,
            "object": obj, "when": when, "claim_text": claim_text,
            "confidence": conf,
            "known_vs_inferred": "知道" if (n_models >= 2 and (obj or addr or whybits)) else "推断",
            "status": "hypothesized", "evidence": urls,
            "confirmed_source_urls": urls, "confirm_voices": 1 if urls else 0,
            "model_consensus": "consensus" if n_models >= 2 else "single",
            "confirm_queries": [f"{name} 上海 主厨 餐厅 地址 荣誉",
                                f"{name} 师承 同门 招牌菜"],
            "falsify_queries": [f"{name} 关店 离职 辟谣",
                                f"{name} 预制 中央厨房 差评"],
            "is_seed": False,
            "proposed_by": {"channel": "api/chef-snowball", "anchor": anchor.get("name"),
                            "anchor_tier": tier,
                            "why": {k: why.get(k) for k in ("technique", "ingredient",
                                                            "flavor", "innovation", "lineage")},
                            "address": addr, "models": sorted(set(agg["models"])),
                            "prompt_hash": PROBE_VERSION, "date": today},
        }
        rows.append(row)
        # 只让「带证据 且 是 chef/owner」的节点继续扩散（防漂移）；餐厅/品牌只记录不再 BFS
        if urls and stype in ("chef", "owner"):
            enqueue.append({"name": name, "restaurant": obj or addr, "tier": tier,
                            "ekey": ekey})
    return rows, enqueue


# ---------------------------------------------------------------------------
def load_state():
    os.makedirs(HAE_DIR, exist_ok=True)
    if os.path.exists(STATE_FILE):
        st = json.load(open(STATE_FILE))
    else:
        st = {}
    st.setdefault("frontier", [])
    st.setdefault("expanded", [])
    st.setdefault("discovered", [])
    st.setdefault("gains", [])
    st.setdefault("rounds", 0)
    st.setdefault("converged", False)
    return st


def save_state(st):
    json.dump(st, open(STATE_FILE, "w"), ensure_ascii=False, indent=2)


def seed_frontier(st, seeds):
    have = {C.cjk_norm(s["name"]) for s in st["frontier"]} | set(st["expanded"])
    n = 0
    for s in seeds:
        k = C.cjk_norm(s["name"])
        if k and k not in have:
            s.setdefault("ekey", k)
            st["frontier"].append(s)
            n += 1
    return n


def run_round(st, args):
    batch = st["frontier"][: args.breadth]
    if not batch:
        return 0
    print(f"[snowball] round={st['rounds']+1} frontier={len(st['frontier'])} batch={[b['name'] for b in batch]}")
    all_rows, used_all, raws = [], [], []
    new_evidenced = []
    for anchor in batch:
        results, used, raw = recall_anchor(anchor)
        used_all += used
        raws.append(raw)
        aggs = parse_neighbors(results)
        rows, enq = build_rows(aggs, anchor)
        all_rows += rows
        new_evidenced += enq
        print(f"  · {anchor['name']}: 模型={len(results)} 假设={len(rows)} 可扩散新节点={len(enq)}")

    os.makedirs(RECALL_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    json.dump({"probe_version": PROBE_VERSION, "date": datetime.date.today().isoformat(),
               "anchors": raws}, open(os.path.join(RECALL_DIR, f"snowball_{ts}.json"), "w"),
              ensure_ascii=False, indent=1)

    # 从 frontier 移除本批，记入 expanded
    bkeys = {C.cjk_norm(b["name"]) for b in batch}
    st["frontier"] = [f for f in st["frontier"] if C.cjk_norm(f["name"]) not in bkeys]
    st["expanded"] = list(dict.fromkeys(st["expanded"] + list(bkeys)))

    # 新证据节点入队（去重、排除已展开/已在队）
    blocked = set(st["expanded"]) | {C.cjk_norm(f["name"]) for f in st["frontier"]} \
        | set(st["discovered"])
    added = 0
    for q in new_evidenced:
        if q["ekey"] not in blocked:
            st["frontier"].append({"name": q["name"], "restaurant": q.get("restaurant"),
                                   "tier": q.get("tier"), "ekey": q["ekey"]})
            st["discovered"].append(q["ekey"])
            added += 1

    st["gains"].append(added)
    st["rounds"] += 1
    print(f"[snowball] providers={used_all or ['全部跳过(无key)']}")
    print(f"[snowball] 本轮新增可扩散证据节点={added}；frontier 余={len(st['frontier'])}")

    if args.apply:
        import hae_engine as H
        normed = []
        for r in all_rows:
            try:
                normed.append(H.norm_row(dict(r)))
            except Exception as e:
                print("  [norm skip]", r.get("subject_name"), repr(e)[:90])
        res = H.upsert_rows(normed, apply=True)
        print("[snowball] upsert:", res)

    # 收敛判停：连续 PATIENCE 轮增益 < MIN_GAIN
    recent = st["gains"][-PATIENCE:]
    if len(recent) >= PATIENCE and all(g < MIN_GAIN for g in recent) and not st["frontier"]:
        st["converged"] = True
        print("[snowball] 边际增益收敛且 frontier 清空，自动判停。")
    save_state(st)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-json", default="")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--catchup", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--breadth", type=int, default=MAX_FRONTIER_PER_ROUND)
    args = ap.parse_args()

    st = load_state()
    if args.status:
        print(json.dumps({"rounds": st["rounds"], "frontier": len(st["frontier"]),
                          "expanded": len(st["expanded"]),
                          "discovered": len(set(st["discovered"])),
                          "gains": st["gains"], "converged": st["converged"]},
                         ensure_ascii=False))
        return

    if args.seed_json:
        seeds = json.loads(pathlib.Path(args.seed_json).read_text(encoding="utf-8"))
        if isinstance(seeds, dict):
            seeds = seeds.get("anchors") or seeds.get("chefs") or []
        n = seed_frontier(st, seeds)
        print(f"[snowball] 载入新种子 {n} 个")
        save_state(st)

    if args.catchup:
        guard = 0
        while (st["frontier"] and not st["converged"]) or guard < 0:
            run_round(st, args)
            guard += 1
            if guard > 40:
                break
        print(f"[snowball] catchup 结束 rounds={st['rounds']} converged={st['converged']}")
    else:
        for _ in range(max(args.rounds, 1)):
            run_round(st, args)


if __name__ == "__main__":
    main()

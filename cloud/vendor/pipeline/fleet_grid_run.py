#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAE 四轴网格轮转搜索机 v2（L0.5 假设层）。

以「菜系叶子」为稳定枚举轴（菜系×场景×食材×口碑四轴中，菜系叶子最稳定，
从 cuisines 表 dimension=菜系、parent_category 非虚拟根枚举，不临时点名）。
维护轮转游标（checkpoint 落 /app/data/hae/fleet_grid_state.json）：
  取切片（SLICE 个叶子）→ 对每叶拼【多维结构化探针】→ 并行问 API 舰队 →
  解析舰队返回的餐厅实体（聚合多模型、来源入库、原文按叶落盘）→ upsert lead_hypotheses。

v2 修复（v1 的两处致命缺陷）：
  1. v1 探针只有一句泛问；v2 改为覆盖 主厨/师承、集团品牌、菜系定位、招牌菜、
     开关迁址、同名分店、米其林黑珍珠/节目成员、本地老饕口碑 vs 连锁预制 的多维探针，
     强制只输出结构化 JSON、显式"不知道"、附来源 URL。
  2. v1 recall_rows_for_leaf 把舰队实际返回文本【整体丢弃】、只写一条占位假设；
     v2 真正解析文本 → 每家被回忆起的餐厅一条假设，携带多模型共识、来源与证据，
     原始回答按叶落盘 /app/data/hae/recall/ 供审计与重解析。

认识论红线（与 source-classes-and-calibration / north-star 一致，硬约束）：
  - 模型/舰队输出【只 upsert lead_hypotheses】，绝不直写事实表；
  - 多模型一致只抬高【先验】（语料同源，非独立证实），置信保守封顶；
    晋升仍走 hae_engine 闸门：权威 source_url 或 ≥2 独立声音；
  - 每条假设必带 confirm_queries + falsify_queries；
  - 无 key/缺适配器自动跳过、降级占位（不报错中断）；断点幂等，重跑从游标继续。

用法：
  python3 fleet_grid_run.py --once --apply          # 跑一个切片并写假设
  python3 fleet_grid_run.py --catchup --apply       # 连续切片直到扫完（或 --max-leaves）
  python3 fleet_grid_run.py --status                # 只看游标进度
"""
import os, sys, json, argparse, datetime, hashlib, re
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
HAE_DIR = os.path.join(DATA, "hae")
RECALL_DIR = os.path.join(HAE_DIR, "recall")
STATE_FILE = os.path.join(HAE_DIR, "fleet_grid_state.json")
VIRTUAL_ROOTS = {"中餐", "亚洲菜", "西餐", "其他"}
SLICE = int(os.environ.get("HAE_GRID_SLICE", "8"))
PROBE_VERSION = "fleetgrid-v2"  # 稳定 prompt_hash：同店重跑 hid 幂等

# ---------------------------------------------------------------------------
# 叶子枚举 / 游标
# ---------------------------------------------------------------------------
def enum_leaves():
    rows = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    leaves = [r["name"] for r in rows
              if r["dimension"] == "菜系" and (r.get("parent_category") or "") not in VIRTUAL_ROOTS]
    return sorted(set(leaves))


def load_state(total):
    os.makedirs(HAE_DIR, exist_ok=True)
    if os.path.exists(STATE_FILE):
        st = json.load(open(STATE_FILE))
    else:
        st = {"cursor": 0, "done": []}
    st.setdefault("cursor", 0)
    st.setdefault("done", [])
    if st.get("total") != total:  # 网格重建则游标重置
        st = {"cursor": 0, "done": [], "total": total}
    return st


def save_state(st):
    json.dump(st, open(STATE_FILE, "w"), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 多维结构化探针
# ---------------------------------------------------------------------------
_PROBE_SCHEMA = {
    "leaf": "<菜系叶子名>",
    "city": "上海",
    "restaurants": [
        {
            "name": "规范中文店名（必须）",
            "name_en": "外文名/别名，没有则 null",
            "chef": "主厨/主理人，没有则 null",
            "chef_lineage": "主厨师承/出身，没有则 null",
            "group": "所属餐饮集团/品牌，没有则 null",
            "positioning": "该店真实菜系/品类定位",
            "signature_dishes": ["招牌/代表菜"],
            "awards": ["米其林星级/黑珍珠钻级/美食节目成员等，没有则 []"],
            "branches": ["同名分店及其地址，没有则 []"],
            "status": "营业 / 迁址 / 关店 / 未知",
            "status_note": "迁址新店址或关店说明，没有则 null",
            "local_repute": "本地老饕/食客的真实口碑（区别于营销），没有则 null",
            "chain_premade": "独立现做 / 小型连锁现做 / 连锁预制 / 中央厨房 / 未知",
            "sources": ["支撑信息的来源 URL（联网搜索时必填）"],
            "known": "知道 / 推断 / 不知道",
        }
    ],
}


def probe_for_leaf(leaf):
    return (
        f"你是上海城市美食图鉴的【事实线索引擎】。请就上海的「{leaf}」这一菜系/品类，"
        f"做一次多维度联网回忆，找出真正值得收录、口味出色的餐厅与主厨。\n"
        f"必须逐维度核查（缺一维度也要显式标注 null，禁止编造）：\n"
        f"1) 主厨/主理人及其师承出身；2) 所属餐饮集团/品牌；3) 该店真实菜系与品类定位；"
        f"4) 招牌菜/代表菜；5) 开店/迁址/关店状态与时间；6) 同名分店及各自地址（不同分店要分别列出）；"
        f"7) 米其林星级、黑珍珠钻级、美食节目（如一饭封神/黑白厨房）成员等荣誉；"
        f"8) 本地老饕真实口碑 vs 连锁/预制/中央厨房（明显连锁预制、非本地化的店要在 chain_premade 标明，不要推荐）。\n"
        f"只输出你确实有记忆或能由来源支撑的店；完全没有线索就返回空数组并在 leaf 里说明，"
        f"绝不虚构店名、人名、年份。\n"
        f"【只输出如下 JSON，不要任何客套或解释，不要 Markdown 代码块】：\n"
        f"{json.dumps(_PROBE_SCHEMA, ensure_ascii=False)}"
    )


# ---------------------------------------------------------------------------
# 舰队调用（API 并行；无 key 自动跳过）
# ---------------------------------------------------------------------------
def api_tasks():
    """构造 [(provider, model)] 任务；无 key 返回 []。"""
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


def recall_leaf(leaf):
    """对一个叶子跑舰队，返回 (results[dict], used[list], raw)。"""
    info, msg = api_tasks()
    if info is None:
        return [], msg, {"leaf": leaf, "results": []}
    MP, tasks = info
    prompt = probe_for_leaf(leaf)
    results = []
    if tasks:
        workers = min(6, len(tasks))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(call_one, MP, p, m, prompt) for (p, m) in tasks]
            results = [f.result() for f in futs]
    used = [r.get("identity") + ("" if r.get("ok") else " SKIP") for r in results]
    used += msg
    raw = {"leaf": leaf, "probe_version": PROBE_VERSION,
           "date": datetime.date.today().isoformat(),
           "results": [{"identity": r.get("identity"), "ok": r.get("ok"),
                        "web": r.get("web"), "text": r.get("text"),
                        "sources": r.get("sources"), "error": r.get("error")}
                       for r in results]}
    return results, used, raw


# ---------------------------------------------------------------------------
# 解析舰队文本 → 餐厅实体
# ---------------------------------------------------------------------------
def _extract_json(text):
    """从模型文本中鲁棒抽取 JSON（去代码块、截取首尾大括号、容忍尾逗号）。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(json)?|```$", "", t, flags=re.M).strip()
    # 去掉跨行代码围栏
    t = t.replace("```json", "").replace("```", "")
    a, b = t.find("{"), t.rfind("}")
    candidate = t[a:b + 1] if a >= 0 and b > a else t
    for cand in (candidate, t):
        try:
            return json.loads(cand)
        except Exception:
            try:  # 容忍对象/数组尾逗号
                fixed = re.sub(r",(\s*[}\]])", r"\1", cand)
                return json.loads(fixed)
            except Exception:
                continue
    return None


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def parse_restaurants(results):
    """把多模型返回解析并按规范店名聚合 → {ekey: agg}。"""
    aggs = {}
    for r in results:
        if not r.get("ok"):
            continue
        data = _extract_json(r.get("text", ""))
        items = []
        if isinstance(data, dict):
            items = data.get("restaurants") or data.get("items") or []
        elif isinstance(data, list):
            items = data
        for it in items:
            if not isinstance(it, dict):
                continue
            name = (it.get("name") or "").strip()
            if not name or name in ("null", "未知", "无"):
                continue
            ekey = C.cjk_norm(name)
            if not ekey:
                continue
            urls, src0 = [], r.get("sources") or []
            urls += [u for u in _as_list(it.get("sources")) if u.startswith("http")]
            urls += [u for u in src0 if isinstance(u, str) and u.startswith("http")]
            # 去重保序
            urls = list(dict.fromkeys(urls))
            agg = aggs.setdefault(ekey, {
                "names": [], "items": [], "models": [], "urls": []})
            if name not in agg["names"]:
                agg["names"].append(name)
            agg["items"].append(it)
            if r.get("identity") and r["identity"] not in agg["models"]:
                agg["models"].append(r["identity"])
            for u in urls:
                if u not in agg["urls"]:
                    agg["urls"].append(u)
    return aggs


def _authoritative(urls):
    for u in urls:
        try:
            if C.source_kind(url=u) in ("official_guide", "media", "brand"):
                return True
        except Exception:
            continue
    return False


def _display_name(agg):
    """选择最规范的展示名：优先多模型共识，其次信息最全，其次最长。"""
    names = agg["names"]
    if len(names) == 1:
        return names[0]
    # 出现频次（按 items 中重复）
    from collections import Counter
    freq = Counter()
    for it in agg["items"]:
        nm = (it.get("name") or "").strip()
        if nm:
            freq[nm] += 1
    top = freq.most_common()
    best = top[0][0]
    if top[0][1] >= 2 and (len(top) == 1 or top[1][1] < top[0][1]):
        return best
    # 信息最全 / 最长
    return sorted(names, key=lambda n: (len(C.cjk_norm(n)), len(n)), reverse=True)[0]


def _first_nonempty(items, key):
    for it in items:
        v = it.get(key)
        if isinstance(v, str) and v.strip() and v.strip() not in ("null", "未知", "无"):
            return v.strip()
    return None


def build_rows_for_leaf(leaf, results):
    """聚合 → 每店一条规范假设行（不做 hid，交 hae_engine.norm_row）。"""
    aggs = parse_restaurants(results)
    today = datetime.date.today().isoformat()
    rows = []
    for ekey, agg in aggs.items():
        name = _display_name(agg)
        items = agg["items"]
        n_models = len(set(agg["models"]))
        urls = agg["urls"]
        chef = _first_nonempty(items, "chef")
        group = _first_nonempty(items, "group")
        positioning = _first_nonempty(items, "positioning")
        status = _first_nonempty(items, "status") or "未知"
        status_note = _first_nonempty(items, "status_note")
        local_repute = _first_nonempty(items, "local_repute")
        chain_premade = _first_nonempty(items, "chain_premade")
        chef_lineage = _first_nonempty(items, "chef_lineage")
        dishes, awards = [], []
        for it in items:
            dishes += _as_list(it.get("signature_dishes"))
            awards += _as_list(it.get("awards"))
        dishes = list(dict.fromkeys(dishes))[:8]
        awards = list(dict.fromkeys(awards))[:6]

        bits = [f"网格召回(菜系叶子「{leaf}」)"]
        if positioning: bits.append(f"定位={positioning}")
        if chef: bits.append(f"主厨={chef}" + (f"（{chef_lineage}）" if chef_lineage else ""))
        if group: bits.append(f"集团={group}")
        if dishes: bits.append("招牌=" + "、".join(dishes))
        if awards: bits.append("荣誉=" + "、".join(awards))
        if status and status != "营业": bits.append(f"状态={status}" + (f"（{status_note}）" if status_note else ""))
        if chain_premade: bits.append(f"连锁/预制判定={chain_premade}")
        if local_repute: bits.append(f"本地口碑={local_repute}")
        if not urls: bits.append("暂无来源URL，待取证")
        claim_text = "；".join(bits)

        # 置信：模型先验，保守封顶（语料同源，非独立证实）
        conf = 0.30
        conf += 0.06 * min(max(n_models - 1, 0), 2)   # 多模型共识 +0.06/个，最多 +0.12
        if urls: conf += 0.10
        cap = 0.65 if _authoritative(urls) else 0.55
        conf = min(round(conf, 2), cap)

        # known_vs_inferred：>=2 模型且有具体细节 → 知道，否则推断
        concrete = any([chef, dishes, group])
        known = "知道" if (n_models >= 2 and concrete) else "推断"

        row = {
            "subject_type": "restaurant",
            "subject_name": name,
            "relation": "related_to",
            "object": "上海值得收录店",
            "claim_text": claim_text,
            "confidence": conf,
            "known_vs_inferred": known,
            "status": "hypothesized",
            "evidence": urls,
            "confirmed_source_urls": urls,
            "confirm_voices": 1 if urls else 0,
            "model_consensus": "consensus" if n_models >= 2 else "single",
            "confirm_queries": [f"{name} 上海 地址 电话 预订",
                                f"{name} 主厨 招牌菜 米其林 黑珍珠"],
            "falsify_queries": [f"{name} 上海 关店 停业 搬迁",
                                f"{name} 预制菜 中央厨房 连锁 差评"],
            "proposed_by": {"channel": "api/fleet-grid", "models": sorted(set(agg["models"])),
                            "leaves": [leaf], "prompt_hash": PROBE_VERSION, "date": today},
        }
        rows.append(row)
    return rows


def placeholder_for_leaf(leaf, used):
    """零实体时的占位（保证有迹、游标照常推进）。"""
    today = datetime.date.today().isoformat()
    return [{
        "subject_type": "restaurant",
        "subject_name": f"{leaf}(网格种子)",
        "relation": "related_to",
        "object": "上海值得收录店",
        "claim_text": f"四轴网格轮转种子=菜系叶子[{leaf}]；本轮无 API 模型/未解析出实体，待取证。",
        "confidence": 0.30,
        "known_vs_inferred": "推断",
        "status": "hypothesized",
        "evidence": [],
        "confirmed_source_urls": [],
        "confirm_voices": 0,
        "confirm_queries": [f"上海 {leaf} 米其林 黑珍珠", f"上海 {leaf} 必吃 主厨"],
        "falsify_queries": [f"上海 {leaf} 关店 停业 预制"],
        "proposed_by": {"channel": "api/fleet-grid", "models": used[:3],
                        "leaves": [leaf], "prompt_hash": PROBE_VERSION, "date": today},
    }]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _norm_all(rows):
    import hae_engine as H
    out = []
    for r in rows:
        try:
            out.append(H.norm_row(dict(r)))
        except Exception as e:
            print("  [norm skip]", r.get("subject_name"), repr(e)[:100])
    return out


def run_slice(st, leaves, args):
    i0 = st["cursor"]
    i1 = min(i0 + args.slice, len(leaves))
    batch = leaves[i0:i1]
    print(f"[grid] leaves={len(leaves)} slice={args.slice} batch[{i0}:{i1}]={batch}")

    all_rows, used_all, raw_pack = [], [], {"probe_version": PROBE_VERSION,
                                            "date": datetime.date.today().isoformat(),
                                            "leaves": []}
    for leaf in batch:
        results, used, raw = recall_leaf(leaf)
        used_all += used
        raw_pack["leaves"].append(raw)
        rows = build_rows_for_leaf(leaf, results)
        if not rows:
            rows = placeholder_for_leaf(leaf, used)
        all_rows += rows
        print(f"  · {leaf}: 模型={len(results)} 假设实体={len(rows)}")

    # 原文按 run 落盘（审计 / 重解析）
    os.makedirs(RECALL_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    rp = os.path.join(RECALL_DIR, f"fleet_recall_{ts}.json")
    json.dump(raw_pack, open(rp, "w"), ensure_ascii=False, indent=1)

    normed = _norm_all(all_rows)
    print("[grid] providers:", used_all or ["全部跳过(无key)"])
    print(f"[grid] recall entities={len(normed)}; raw saved {rp}")

    if args.apply:
        import hae_engine as H
        res = H.upsert_rows(normed, apply=True)
        print("[grid] upsert:", res)
        st["cursor"] = i1
        st["done"] = st.get("done", []) + [b for b in batch if b not in st.get("done", [])]
        st["last_advanced"] = datetime.date.today().isoformat()
        save_state(st)
        print("[grid] cursor ->", st["cursor"], "/", len(leaves))
    else:
        print("[grid] dry-run（加 --apply 才写 lead_hypotheses 并推进游标）")
    return len(normed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--catchup", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--slice", type=int, default=SLICE)
    ap.add_argument("--max-leaves", type=int, default=10 ** 9)
    args = ap.parse_args()

    leaves = enum_leaves()
    st = load_state(len(leaves))
    if args.status:
        print(json.dumps({"total_leaves": len(leaves), "cursor": st["cursor"],
                          "done": len(st.get("done", [])), "slice": args.slice,
                          "remaining": len(leaves) - st["cursor"],
                          "last_advanced": st.get("last_advanced")}, ensure_ascii=False))
        return

    if not (args.once or args.catchup):
        args.once = True

    processed = 0
    if args.catchup:
        while st["cursor"] < len(leaves) and processed < args.max_leaves:
            processed += run_slice(st, leaves, args)
        print(f"[grid] catchup done; cursor={st['cursor']}/{len(leaves)} entities_this_run={processed}")
    else:
        run_slice(st, leaves, args)


if __name__ == "__main__":
    main()

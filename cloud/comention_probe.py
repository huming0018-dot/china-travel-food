#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""comention_probe.py — 模块C·联想词探针。

机制（source-classes §1 硬边界：探针只进 gap/候选，绝不直写事实表）：
  1. 种子 = 在库高评分/认证店（米其林/黑珍珠/高分 active），取一批；
  2. 联想路径：从既有 raw_discovery.jsonl 每篇笔记里挖「同篇共现」的店名锚点，
     形成 种子--未知店 共现边；同时为每种子生成联想 query（平替/还有/类似/合集）入 frontier；
  3. 建 co-mention 图：节点=店（已知 rid / 未知候选），边记 共现次数+共同来源URL+强度分；
  4. 未知店只写 /app/data/discovery/lead_coention.jsonl（候选池），交既有 admission_gate，
     由 gap_pool 后续取证；绝不 POST restaurants。
  5. 幂等：processed seeds/edges 记 ledger，重复跑 0 新增边。

只读 DB（fetch_all）；只写 /app/data/discovery/。
用法：
  python3 comention_probe.py            # dry-run，打印图统计
  python3 comention_probe.py --enqueue  # 把未知候选写进 lead_coention.jsonl
"""
import argparse, json, pathlib, re, sys, collections, time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = "/app/pipeline"
DATA = pathlib.Path("/app/data")
DISC = pathlib.Path(DATA, "discovery")
GRAPH_F = pathlib.Path(DATA, "comention_graph.json")
EDGES_F = pathlib.Path(DISC, "comention_edges.jsonl")
LEADS_F = pathlib.Path(DISC, "lead_coention.jsonl")
LEDGER_F = pathlib.Path(DATA, "comention_probe_ledger.json")

# 评论区/正文「另一家」口述店名（与 discovery_engine.RE_REC 同义，独立正则以免耦合）
RE_REC = [
    re.compile(r"真正好?吃的?(?:还得是|是|得去)?\s*([一-龥A-Za-z][一-龥A-Za-z·&']{1,13})"),
    re.compile(r"(?:推荐|安利|种草)(?:大家)?(?:一家|个|去)?\s*([一-龥A-Za-z][一-龥A-Za-z·&']{1,13})"),
    re.compile(r"另(?:一家|外一家|家)\s*([一-龥A-Za-z][一-龥A-Za-z·&']{1,13})"),
]
STOP = set("这那个一好吃买的我你他她它啥很真最还在和跟是也就了啦啊吧呢嘛超很挺")
# 种子联想 query 模板（确定性、可配置）
ASSOC_TEMPLATES = ["{seed} 平替", "{seed} 还有 类似 上海", "{seed} 推荐 上海",
                   "{cuisine} 合集 上海", "{cuisine} 私藏 老饕"]


def _norm(s):
    return re.sub(r"[\s·,，。！!？?、（）()]", "", (s or "")).lower()


def pick_seeds(limit=40):
    """在库高评分/认证 active 店作种子。只读。"""
    sys.path.insert(0, PIPE)
    import common as C
    rows = C.fetch_all("restaurants", "id,name,status,score_total", order_col="id")
    seeds = [x for x in rows if x.get("status") == "active" and (x.get("score_total") or 0) >= 70]
    seeds.sort(key=lambda x: -(x.get("score_total") or 0))
    return seeds[:limit]


def anchors_in_text(text):
    out = []
    for rx in RE_REC:
        for m in rx.findall(text or ""):
            m = m.strip()
            if len(m) >= 2 and not m[-1] in STOP:
                out.append(m)
    return out


def mine_raw(seed_list):
    """扫 raw_discovery.jsonl，挖同篇共现。seed_list=种子店名 list。返回 edges[(a,b)]。"""
    edges = collections.defaultdict(lambda: {"urls": [], "count": 0})
    seed_norm = {_norm(sn): sn for sn in seed_list}
    notes = 0
    if not pathlib.Path(DISC, "raw_discovery.jsonl").exists():
        return edges, 0
    for line in pathlib.Path(DISC, "raw_discovery.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for n in rec.get("notes", []):
            notes += 1
            text = (n.get("title", "") or "") + " " + (n.get("desc", "") or "") + " " + \
                   " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in (n.get("comments") or []))
            if not isinstance(text, str):
                text = str(text)
            url = n.get("url") or n.get("bvid") or ""
            found = set()
            for sn in seed_list:
                if _norm(sn) and _norm(sn) in _norm(text):
                    found.add(sn)
            for a in anchors_in_text(text):
                an = _norm(a)
                if an in seed_norm:
                    found.add(seed_norm[an])
                else:
                    found.add(a)
            found = list(found)
            for i in range(len(found)):
                for j in range(i + 1, len(found)):
                    a, b = sorted([found[i], found[j]])
                    key = (a, b)
                    edges[key]["count"] += 1
                    if url and url not in edges[key]["urls"]:
                        edges[key]["urls"].append(url)
    return edges, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enqueue", action="store_true")
    ap.add_argument("--seeds", type=int, default=40)
    args = ap.parse_args()

    seeds = pick_seeds(args.seeds)
    seed_names = {s["name"]: s for s in seeds}
    print(f"种子数(高分active>={70}): {len(seeds)}")

    edges, notes = mine_raw([s["name"] for s in seeds])
    print(f"扫描 raw_discovery 笔记: {notes}; 共现边: {len(edges)}")

    # 强度分 = 共现次数 * (1 + url数)
    nodes = {}
    seed_ids = {_norm(s["name"]): s["id"] for s in seeds}
    rows = []
    for (a, b), e in sorted(edges.items(), key=lambda kv: -len(kv[1]["urls"])):
        strength = e["count"] + len(e["urls"])
        rows.append({"a": a, "b": b, "count": e["count"],
                      "n_urls": len(e["urls"]), "strength": strength, "urls": e["urls"][:5]})
        for n in (a, b):
            nodes[n] = {"in_db": _norm(n) in seed_ids, "rid": seed_ids.get(_norm(n))}

    # 未知节点（共现到但不在库）
    unknown = [n for n, v in nodes.items() if not v["in_db"]]
    print(f"图节点: {len(nodes)} (已知种子 {len(seeds)}); 未知共现店: {len(unknown)}")
    print("强度 top5 边:")
    for r in rows[:5]:
        print(f"  {r['a']} -- {r['b']}  count={r['count']} urls={r['n_urls']} strength={r['strength']}")

    # 联想 query（每种子）
    assoc_q = []
    cuisine_root = "上海"
    for s in seeds[:20]:
        for t in ASSOC_TEMPLATES:
            assoc_q.append(t.format(seed=s["name"], cuisine=cuisine_root))
    print(f"联想 query 数: {len(assoc_q)} (样本: {assoc_q[:3]})")

    # 持久化（幂等：合并 ledger 已见边）
    ledger = {}
    if LEDGER_F.exists():
        ledger = json.loads(LEDGER_F.read_text(encoding="utf-8"))
    seen_edges = set(tuple(x) for x in ledger.get("edges", []))
    new_edges = [r for r in rows if (r["a"], r["b"]) not in seen_edges]

    GRAPH_F.write_text(json.dumps({
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "n_seeds": len(seeds), "n_notes": notes,
        "n_nodes": len(nodes), "n_edges": len(rows),
        "unknown_candidates": unknown[:50],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.enqueue and new_edges:
        with EDGES_F.open("a", encoding="utf-8") as f:
            for r in new_edges:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        # 未知店写候选池（不写事实表）
        existing = set()
        if LEADS_F.exists():
            for line in LEADS_F.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.add(json.loads(line).get("name"))
        with LEADS_F.open("a", encoding="utf-8") as f:
            for n in unknown:
                if n not in existing:
                    f.write(json.dumps({"name": n, "source": "comention_probe",
                                        "ts": time.strftime("%Y-%m-%d %H:%M"),
                                        "note": "种子共现发现，待 admission_gate 取证"},
                                       ensure_ascii=False) + "\n")
        ledger["edges"] = [list(e) for e in seen_edges] + [(r["a"], r["b"]) for r in new_edges]
        LEDGER_F.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        print(f"写入新边 {len(new_edges)}; 未知候选入 lead_coention {len([n for n in unknown if n not in existing])}")
    else:
        print("dry-run（--enqueue 才写候选池/边账本）")


if __name__ == "__main__":
    main()

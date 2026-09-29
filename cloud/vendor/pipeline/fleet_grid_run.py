#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAE 四轴网格轮转搜索机（L0.5 假设层）。

以「菜系叶子」为种子（菜系×场景×食材×口碑四轴中，菜系叶子是最稳定的枚举轴，
从 cuisines 表 dimension=菜系、parent_category 非虚拟根枚举，不临时点名）。
维护轮转游标（checkpoint 落 /app/data/hae/fleet_grid_state.json）：
  每次取一个切片（SLICE 个叶子）→ 对每个叶子拼舰队探针 → fleet-recall → prove → promote。

认识论（与 source-classes-and-calibration.md 一致，硬约束）：
  - 模型/舰队输出【只 upsert lead_hypotheses】，绝不直写事实表；
  - 多模型一致只作先验，晋升仍需权威 source_url 或 >=2 独立声音；
  - 无 key/缺适配器自动跳过、降级 agent 推理，不报错中断；
  - 每条假设必带 confirm_queries + falsify_queries；断点幂等，重跑从游标继续。

用法：
  python3 fleet_grid_run.py --once            # 跑一个切片（默认 dry-run 只打印计划）
  python3 fleet_grid_run.py --once --apply    # 真写 lead_hypotheses（晋升仍走 hae_engine --promote --apply）
  python3 fleet_grid_run.py --status          # 只看游标进度
"""
import os, sys, json, argparse, datetime, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

STATE_DIR = os.environ.get("FOOD_DATA_DIR", "/app/data")
STATE_DIR = os.path.join(STATE_DIR, "hae")
STATE_FILE = os.path.join(STATE_DIR, "fleet_grid_state.json")
VIRTUAL_ROOTS = {"中餐", "亚洲菜", "西餐", "其他"}
SLICE = int(os.environ.get("HAE_GRID_SLICE", "8"))


def enum_leaves():
    rows = C.fetch_all("cuisines", "id,name,dimension,parent_category", order_col="id")
    leaves = [r["name"] for r in rows
              if r["dimension"] == "菜系" and (r.get("parent_category") or "") not in VIRTUAL_ROOTS]
    # 稳定排序，保证切片可复现
    return sorted(set(leaves))


def load_state(total):
    os.makedirs(STATE_DIR, exist_ok=True)
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


def probe_for_leaf(leaf):
    return (
        f"联网回忆：上海有哪些值得收录的「{leaf}」餐厅与主厨？"
        f"列出店名、主厨/主理人、招牌菜、是否米其林/黑珍珠。"
        f"不知道就显式说不知道，禁止编造；最后列参考来源URL。"
    )


def try_providers(prompt):
    """有 key 就并行问 API 舰队；无 key/限流自动跳过。返回 (rows, used)。"""
    try:
        import model_providers as MP
    except Exception as e:
        return [], [f"model_providers import skip: {e}"]
    provs = MP.load_providers()
    if not provs:
        return [], ["无可用 API 适配器（缺 key），降级 agent/网页"]
    out, used = [], []
    for p in provs:
        for m in getattr(p, "models", []):
            try:
                r = MP.chat(p, m, prompt)
                used.append(f"{p.kind}/{m}")
                out.append(r)
            except Exception as e:
                used.append(f"{p.kind}/{m} SKIP({type(e).__name__})")
    return out, used


def recall_rows_for_leaf(leaf, provider_texts, used):
    """把舰队/agent 文本归一为假设行（hid 幂等）。"""
    today = datetime.date.today().isoformat()
    ph = hashlib.md5(leaf.encode()).hexdigest()[:8]
    return [{
        "hid": f"grid-{ph}-{leaf}",
        "subject_type": "restaurant",
        "subject_name": f"{leaf}(网格种子)",
        "relation": "related_to",
        "object": "上海值得收录店",
        "claim_text": f"四轴网格轮转种子=菜系叶子[{leaf}]；舰队/agent 回忆待取证。",
        "confidence": 0.3,
        "known_vs_inferred": "推断",
        "proposed_by": "web/agent+fleet-grid " + ",".join(used[:3]) + " " + today,
        "status": "hypothesized",
        "evidence": [],
        "confirm_queries": [f"上海 {leaf} 米其林 黑珍珠", f"上海 {leaf} 必吃 主厨"],
        "falsify_queries": [f"上海 {leaf} 关店 停业 预制"],
    }]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--slice", type=int, default=SLICE)
    args = ap.parse_args()

    leaves = enum_leaves()
    st = load_state(len(leaves))
    if args.status:
        print(json.dumps({"total_leaves": len(leaves), "cursor": st["cursor"],
                          "done": len(st["done"]), "slice": args.slice,
                          "remaining": len(leaves) - st["cursor"]}, ensure_ascii=False))
        return

    i0 = st["cursor"]
    i1 = min(i0 + args.slice, len(leaves))
    batch = leaves[i0:i1]
    print(f"[grid] leaves={len(leaves)} slice={args.slice} batch[{i0}:{i1}]={batch}")

    all_rows, used_all = [], []
    for leaf in batch:
        prompt = probe_for_leaf(leaf)
        texts, used = try_providers(prompt)
        used_all += used
        all_rows += recall_rows_for_leaf(leaf, texts, used)

    print("[grid] providers:", used_all or ["全部跳过(无key)"])
    print("[grid] recall rows:", len(all_rows))

    if args.apply:
        import hae_engine as H
        res = H.upsert_rows(all_rows, apply=True)
        print("[grid] upsert:", res)
        st["cursor"] = i1
        st["done"] = st.get("done", []) + batch
        save_state(st)
        print("[grid] cursor ->", st["cursor"], "/", len(leaves))
    else:
        print("[grid] dry-run（加 --apply 才写 lead_hypotheses 并推进游标）")


if __name__ == "__main__":
    main()

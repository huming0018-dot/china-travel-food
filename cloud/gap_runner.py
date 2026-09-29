#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gap_runner.py — 用「覆盖账本 + 地毯计划器」驱动 DiscoveryEngine（签名 HTTP，全程不开浏览器）。

采集单元 = category（粗品类，约 40 个），不是 discovery_plan 的细叶（129 个）：
  - 同一 category 的多个细叶（拉面·博多豚骨 / 拉面·蘸面 …）聚合为一个工作单元，
    共享一个引擎、并集种子，避免每个细叶各跑一遍全品类的冗余采集；
  - DiscoveryEngine / admission_gate / candidate_apply 本就以 category 为路由，
    candidate_apply 把新店挂到 category 的菜系【根节点】。

完成判据（category 粒度，2026-09-28 粒度对齐）：
  n_active = 菜系根节点【聚合】在营店数（账本父节点 = 根直挂 + 各叶后代去重）；
  target   = 根下叶子 target_n 之和（子类型网格填满所需）；
  n_active ≥ target 即该 category 发现完成。细叶 n_active 不作判据——把根下餐厅
  分发到细叶是下游「招牌菜联动归类」步骤，不阻塞发现。

假饱和重开：一轮 run 标 saturated 但 category 未达标 → reseed_deep（评论区/长尾/
主厨/排名词根，排除已访问）再跑，最多 MAX_DEEP_ROUNDS 轮；仍不足标 gap_remaining，
claim 按 engine mtime GAP_REVISIT_SEC 后才重开。

用法：
  并行池 worker（gap_pool 每个健康账号拉起一个）：
    python3 gap_runner.py --pool --account account_b --queries 6
  单跑兜底：
    python3 gap_runner.py --next --queries 8
    python3 gap_runner.py --category ramen --queries 6
"""
import argparse
import collections
import fcntl
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path("/app/pipeline")
DATA = pathlib.Path("/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import xhs_api  # noqa: E402
import discovery_engine as _DE  # noqa: E402
import discovery_keywords as K  # noqa: E402
from discovery_engine import DiscoveryEngine  # noqa: E402
import category_resolver as resolver  # noqa: E402

# 评论/正文口述抽取里常见的"非店名"片段：图遍历只追真实店名，这些一律拦截。
_DE.GENERIC_WORDS |= {
    "地址", "适合", "推荐", "位置", "地方", "环境", "服务", "味道", "口感", "时候",
    "现在", "已经", "觉得", "个人", "比较", "非常", "特别", "可以", "真的", "这家",
    "那家", "性价比", "体验", "感觉", "招牌", "特色", "人均", "排队", "预约", "营业",
    "时间", "电话", "路线", "交通", "停车", "地铁", "公交", "商圈", "商场", "楼层",
    "门口", "附近", "旁边", "对面", "隔壁", "朋友", "同事", "家人", "老板", "店员",
    "服务员", "厨师", "主厨", "菜品", "菜式", "口味", "分量", "价格", "不贵", "便宜",
    "地点", "店名", "名字", "名称", "规则", "吐槽", "总吐槽", "评论", "笔记", "帖子",
}

COVDIR = DATA / "coverage"
PLAN_F = COVDIR / "discovery_plan.json"
FRONT_F = COVDIR / "frontier.json"
LEDGER_F = COVDIR / "ledger.json"
DISC = DATA / "discovery"
CLAIM_F = COVDIR / "claims.json"
CLAIM_LOCK = COVDIR / "claims.lock"
PROXY_F = DATA / "account_proxies.json"  # {account: "http://user:pass@host:port"}

# 假饱和重开参数
MAX_DEEP_ROUNDS = 2          # 每个 category 最多加深重开次数
GAP_REVISIT_SEC = 6 * 3600   # gap_remaining 冷却多久后允许再次认领


def proxies_for(account):
    """每账号独立出口代理；未配置则返回 None（走服务器默认 IP）。"""
    if not account or not PROXY_F.exists():
        return None
    try:
        url = json.loads(PROXY_F.read_text(encoding="utf-8")).get(account)
    except Exception:
        return None
    return {"http": url, "https": url} if url else None


def map_category(lineage, leaf_id=None):
    """数据驱动路由：返回 category slug 或 ''。"""
    slug, _why = resolver.resolve(lineage, leaf_id)
    return slug or ""


# ------------------------------------------------------------ 工作单元聚合
def category_worklist():
    """把 plan bundles 解析后按 category 聚合。

    返回 {cat: {leaves:[id...], names:[...], seeds:[并集 xhs 词]}}，
    resolver 无法映射（标签/特殊节点）的细叶被排除。
    """
    bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
    out = collections.OrderedDict()
    for b in bundles:
        cat = map_category(b["lineage"], b["id"])
        if not cat:
            continue
        e = out.setdefault(cat, {"leaves": [], "names": [], "seeds": []})
        e["leaves"].append(b["id"])
        e["names"].append(b["name"])
        for q in b.get("queries", {}).get("xhs", []):
            if q not in e["seeds"]:
                e["seeds"].append(q)
    return out


def _frontier_names(leaves):
    """地图 frontier 中、关联到本 category 任一细叶且 status=new 的店名。"""
    out = []
    if FRONT_F.exists():
        try:
            fr = json.loads(FRONT_F.read_text(encoding="utf-8"))
        except Exception:
            return out
        for e in fr.values():
            if e.get("status") == "new" and any(
                    lf in e.get("cuisines", []) for lf in leaves):
                if e.get("name") and e["name"] not in out:
                    out.append(e["name"])
    return out


# ------------------------------------------------------------ category 供给
def _ancestor_chain(leaf_id, byid, byname):
    """叶子→根的祖先 id 链（含叶子）；父为虚拟根/不存则止。"""
    chain, seen, cur = [], set(), byid.get(int(leaf_id))
    while cur is not None:
        cid = cur["id"]
        if cid in seen:
            break
        seen.add(cid)
        chain.append(cid)
        p = resolver._parent(cur, byid, byname)
        cur = byid.get(p["id"]) if p else None
    return chain


def category_supply(cat, worklist=None):
    """category 粒度供给。返回 dict 或 None。

      root     = 本 category 细叶在 cuisines 父链上的【最近公共祖先 LCA】（不依赖
                 CUISINE_ROOT 的显示名，避免「越南菜 vs 越餐」这类名字漂移）；
      n_active = root 聚合在营店数（账本父节点 = 根直挂 + 各叶后代去重；根本身是叶
                 则取该叶 n_active）；
      target   = 本 category 计划细叶 target_n 之和。
    """
    if not LEDGER_F.exists():
        return None
    resolver.load_cuisines()
    byid = resolver._CACHE["by_id"]
    byname = resolver._CACHE["by_name"]
    wl = worklist or category_worklist()
    e = wl.get(cat)
    rows = json.loads(LEDGER_F.read_text(encoding="utf-8"))
    by = {r["id"]: r for r in rows}
    leaves = e["leaves"] if e else []

    # 1) LCA：各细叶祖先链的交集里，最深的那个
    root_id = None
    valid = [lf for lf in leaves if int(lf) in byid]
    if valid:
        chains = [_ancestor_chain(lf, byid, byname) for lf in valid]
        common = set(chains[0])
        for ch in chains[1:]:
            common &= set(ch)
        for cid in chains[0]:          # 链为 叶→根，首个命中即最深公共祖先
            if cid in common:
                root_id = cid
                break

    # 2) 兜底：按 CUISINE_ROOT 显示名精确找根
    if root_id is None:
        root_name = K.CUISINE_ROOT.get(cat)
        cands = [r for r in rows if r.get("name") == root_name]
        root = next((r for r in cands if not r.get("leaf")),
                    cands[0] if cands else None)
        if not root:
            return None
        root_id = root["id"]

    root = by.get(root_id)
    if root is None:
        return None

    # target：本 category 计划细叶 target_n 之和；计划无叶则取根下全部叶
    plan_leaves = [int(lf) for lf in leaves
                   if int(lf) in by and by[int(lf)].get("leaf")]
    if plan_leaves:
        target = sum(by[lf].get("target_n", 3) for lf in plan_leaves)
    else:
        children = collections.defaultdict(list)
        for cid, row in byid.items():
            p = resolver._parent(row, byid, byname)
            if p is not None:
                children[p["id"]].append(cid)
        desc, stack = [], [root_id]
        while stack:
            c = stack.pop()
            for ch in children.get(c, []):
                desc.append(ch)
                stack.append(ch)
        leaf_desc = [d for d in desc if d in by and by[d].get("leaf")]
        target = (sum(by[d].get("target_n", 3) for d in leaf_desc)
                  if leaf_desc else root.get("target_n", 3))

    n = root.get("n_active", 0)
    return {"root_id": root_id, "root_name": root.get("name"),
            "n_active": n, "target": target, "met": n >= target}


# ---------------------------------------------------------------- 认领（整 category）
def _read_claims():
    if CLAIM_F.exists():
        try:
            return json.loads(CLAIM_F.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_claims(c):
    CLAIM_F.write_text(json.dumps(c, ensure_ascii=False, indent=1),
                       encoding="utf-8")


def _claimed_categories(claims):
    return {v.get("category") for v in claims.values() if v.get("category")}


def claim_next_category(account):
    """跨进程原子认领下一个「未达标」category；认领即占用该 category 全部细叶。

    跳过：整类已达标（category_supply.met）；gap_remaining 且 engine mtime 冷却未过；
    已被其他 worker 认领。
    """
    CLAIM_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIM_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        work = category_worklist()
        claims = _read_claims()
        busy = _claimed_categories(claims)
        now = time.time()
        for cat, e in work.items():
            if cat in busy:
                continue
            cs = category_supply(cat)
            if cs and cs["met"]:
                continue
            stf = DISC / f"cat_{cat}" / f"engine_{cat}.json"
            if stf.exists():
                try:
                    s = json.loads(stf.read_text(encoding="utf-8"))
                    if s.get("status") == "gap_remaining" and now - stf.stat().st_mtime < GAP_REVISIT_SEC:
                        continue  # 冷却中，防热循环
                except Exception:
                    pass
            for lid in e["leaves"]:
                claims[str(lid)] = {"account": account, "category": cat,
                                    "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            _write_claims(claims)
            return cat, e
        return None, None


def release_category(cat):
    CLAIM_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIM_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        claims = _read_claims()
        for k in [k for k, v in claims.items() if v.get("category") == cat]:
            claims.pop(k)
        _write_claims(claims)


# ---------------------------------------------------------------- gate + apply
def auto_gate_apply(work, cat):
    raw = work / "raw_discovery.jsonl"
    cout = DISC / f"candidates_{cat}.jsonl"
    g = subprocess.run(
        [sys.executable, str(PIPE / "admission_gate.py"), "--raw", str(raw),
         "--category", cat, "--out", str(cout)],
        capture_output=True, text=True)
    gtail = (g.stdout or "").strip().splitlines()
    admit = next((ln for ln in gtail if "裁决统计" in ln), "")
    a = subprocess.run(
        [sys.executable, str(HERE / "candidate_apply.py"),
         "--category", cat, "--commit"],
        capture_output=True, text=True)
    atail = [ln for ln in (a.stdout or "").strip().splitlines() if ln][-6:]
    return admit, gtail[-3:], atail


def refresh_supply(cat):
    """重跑 coverage_ledger 写盘，返回 category_supply。"""
    r = subprocess.run(
        [sys.executable, str(PIPE / "coverage_ledger.py"),
         "--save", str(LEDGER_F)],
        capture_output=True, text=True)
    for ln in [ln for ln in (r.stdout or "").strip().splitlines() if ln][-2:]:
        print("  ledger:", ln)
    return category_supply(cat)


def _probe_account(api, account):
    """GET user/me 权威判据：登录有效(guest=false)返回 0；登录过期返回 -100（worker 应退出）；
    其余风控码原样返回（搜索软限流会自恢复，不当死）。不再用搜索 POST / get_search_id。
    【质量监管】首次 -100 时等待 30s 重试一次，避免临时性风控误判为登录过期。"""
    acc = next((a for a in api.accounts if a["name"] == account), None)
    if acc is None:
        return -100
    for attempt in range(2):
        j = api._send("GET", "/api/sns/web/v2/user/me")
        code = j.get("code", -1)
        me = j.get("data", {}) or {}
        if code == 0 and not me.get("guest", True):
            return 0
        if code in (-100, -101) or me.get("guest", True):
            if attempt == 0:
                print(f"[{account}] probe首次返回-100，等待30s后重试...")
                time.sleep(30)
                continue
            return -100
        return code
    return -100


# ---------------------------------------------------------------- 跑一个 category
def run_category(cat, e, queries, account=None):
    """返回 'saturated' / 'gap_remaining' / 'stalled' / 'dead' / 'continue'。"""
    gap = 3.2 if account else 2.2
    api = xhs_api.XhsApi(min_gap=gap, pin=account,
                         proxies=proxies_for(account))
    if not api.accounts:
        print("无带登录态的小红书账号，本轮跳过。")
        return "dead"
    if account and _probe_account(api, account) == -100:
        print(f"[{account}] 登录已过期(-100)，需重新扫码登录；worker 退出。")
        return "dead"
    _DE.D._gather_one_query = (
        lambda bu, q, npq, city: api.gather_query(q, npq, city=city or None))
    print(f"category={cat}（{len(e['leaves'])}细叶：{','.join(e['names'][:3])}"
          f"{'…' if len(e['names'])>3 else ''}）；账号={account or '池轮换'} 限速{gap}s")

    work = DISC / f"cat_{cat}"
    work.mkdir(parents=True, exist_ok=True)
    eng = DiscoveryEngine(None, cat, work, notes_per_query=3,
                          max_per_run=queries)
    cn = _DE.C.cjk_norm
    eng.state["brands"] = {
        k: v for k, v in eng.state["brands"].items()
        if cn(v.get("name", "")) not in _DE.GENERIC_WORDS}
    eng.state["oral"] = {
        k: v for k, v in eng.state["oral"].items() if k not in _DE.GENERIC_WORDS}

    # 仅在全新 category 引擎（无 visited、frontier 空）时注入并集种子
    if not eng.state.get("visited") and not eng.state["frontier_high"]:
        seeds = _frontier_names(e["leaves"]) + list(e["seeds"])
        eng.state["frontier_high"] = list(dict.fromkeys(seeds))
        eng.state["frontier_low"] = []
    eng.save()

    iters, guard = 0, 8
    while iters < guard:
        rep = eng.run(max_queries=queries)
        print("== 报告 ==", json.dumps(rep, ensure_ascii=False))
        iters += 1

        if rep["status"] == "stalled":
            return _handle_stalled(cat, e, account, api, rep)

        if rep["status"] == "saturated":
            print("== category 饱和，自动 gate + apply ==")
            admit, gtail, atail = auto_gate_apply(work, cat)
            print(" ", admit)
            for ln in gtail:
                print("  gate:", ln)
            for ln in atail:
                print("  apply:", ln)
            cs = refresh_supply(cat)
            if cs and cs["met"]:
                print(f"== category 达标：n_active={cs['n_active']} ≥ "
                      f"target={cs['target']}，完成 ==")
                return "saturated"
            deep = eng.state.get("deep_round", 0)
            if deep < MAX_DEEP_ROUNDS:
                n = eng.reseed_deep(deep + 1)
                print(f"!! 假饱和：n_active={cs['n_active'] if cs else '?'}/"
                      f"target={cs['target'] if cs else '?'}，加深第{deep+1}轮，"
                      f"新frontier={n}")
                continue
            eng.state["status"] = "gap_remaining"
            eng.save()
            print(f"!! 加深{MAX_DEEP_ROUNDS}轮后仍不足，gap_remaining，"
                  f"{GAP_REVISIT_SEC//3600}h 后重开。")
            return "gap_remaining"

        # running：frontier 未干但本轮 query 用满 → 继续
        if rep["frontier_remaining"] > 0:
            print(f"frontier 剩 {rep['frontier_remaining']}，继续。")
            continue
        continue

    print("达到单 category 最大迭代，释放稍后继续。")
    return "continue"


def _handle_stalled(cat, e, account, api, rep):
    """空转（搜索限流/登录失效）：不入库，释放冷却，并告警。"""
    reason = rep.get("stall_reason", "未知原因")
    throttled = getattr(api, "search_throttled", False)
    print(f"!! 空转检测：{reason}")
    print(f"   search_throttled={throttled}，consecutive_empty="
          f"{getattr(api, 'consecutive_empty', 0)}；不 gate+apply。")
    try:
        import notifier
        notifier.warn(
            f"采集空转：category={cat}（{','.join(e['names'][:3])}）\n"
            f"原因：{reason}\n账号：{account or '池轮换'}，"
            f"search_throttled={throttled}\n已暂停入库，等待恢复。",
            key=f"stalled:cat:{cat}", cooldown=1800)
    except Exception:
        pass
    return "stalled"


# ---------------------------------------------------------------- worker loop
def worker_loop(account, queries):
    """一个账号一个 worker：认领 category → 跑到饱和/gap/失效 → 释放 → 再认领。"""
    finished = 0
    while True:
        cat, e = claim_next_category(account)
        if cat is None:
            print(f"[{account}] 没有可认领的 category，worker 结束。")
            return finished
        st = "continue"
        while st == "continue":
            st = run_category(cat, e, queries, account=account)
        release_category(cat)
        if st == "saturated":
            finished += 1
        elif st == "gap_remaining":
            print(f"[{account}] category gap_remaining，claim 6h 后重开。")
        elif st == "stalled":
            print(f"[{account}] 空转冷却 180s 后继续…")
            time.sleep(180)
        elif st == "dead":
            return finished


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--pool", action="store_true")
    ap.add_argument("--account", default=None)
    ap.add_argument("--queries", type=int, default=8)
    args = ap.parse_args()

    if args.pool:
        if not args.account:
            sys.exit("--pool 需配合 --account <name>")
        return worker_loop(args.account, args.queries)

    work = category_worklist()
    if args.category:
        e = work.get(args.category)
        if not e:
            sys.exit(f"category {args.category} 无法从计划解析")
        run_category(args.category, e, args.queries)
        return 0

    # --next / 默认：找第一个未达标的 category
    for cat, e in work.items():
        cs = category_supply(cat)
        if not (cs and cs["met"]):
            run_category(cat, e, args.queries)
            return 0
    print("所有 category 均已达标。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

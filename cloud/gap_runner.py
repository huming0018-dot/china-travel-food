#!/usr/bin/env python3
# -*- coding: utf-8">
"""gap_runner.py — 用「覆盖账本 + 地毯计划器」驱动 DiscoveryEngine（签名 HTTP，全程不开浏览器）。

两种用法：
  单跑（兼容/兜底）：
    python3 gap_runner.py --next --queries 8
    python3 gap_runner.py --leaf 264 --queries 6
  并行池 worker（由 gap_pool.py 每个健康账号拉起一个）：
    python3 gap_runner.py --pool --account account_b --queries 6

并行协调：claims.json + fcntl 跨进程原子认领，保证每个缺口叶子同时只被一个 worker 处理；
worker 认领后一直跑到该叶子 saturated（自动 gate+apply）或账号失效才释放，再认领下一叶。
"""
import argparse
import json
import pathlib
import subprocess
import sys
import time
import fcntl

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path("/app/pipeline")
DATA = pathlib.Path("/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import xhs_api  # noqa
import discovery_engine as _DE  # noqa
from discovery_engine import DiscoveryEngine  # noqa

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
DISC = DATA / "discovery"
CLAIM_F = COVDIR / "claims.json"
CLAIM_LOCK = COVDIR / "claims.lock"
PROXY_F = DATA / "account_proxies.json"  # {account: "http://user:pass@host:port"}


def proxies_for(account):
    """每账号独立出口代理；未配置则返回 None（走服务器默认 IP）。"""
    if not account or not PROXY_F.exists():
        return None
    try:
        url = json.loads(PROXY_F.read_text(encoding="utf-8")).get(account)
    except Exception:
        return None
    return {"http": url, "https": url} if url else None


def map_category(lineage):
    j = " ".join(lineage)
    table = [("拉面", "ramen"), ("乌冬", "udon"), ("荞麦", "soba"),
             ("寿司", "sushi"), ("烧鸟", "yakitori"), ("烧肉", "yakiniku"),
             ("居酒屋", "izakuya"), ("天妇罗", "tempura"),
             ("川", "sichuan"), ("粤", "cantonese"), ("苏", "jiangsu"),
             ("鲁", "shandong"), ("浙", "zhejiang"), ("闽", "fujian"),
             ("湘", "hunan"), ("徽", "anhui"), ("本帮", "shanghainese"),
             ("北京", "beijing"), ("泰", "thai"), ("越南", "vietnamese"),
             ("韩", "korean"), ("法", "french"), ("意", "italian"),
             ("面包", "bread"), ("咖啡", "coffee"), ("甜品", "dessert"),
             ("茶", "tea_house"), ("酒吧", "bar")]
    for k, v in table:
        if k in j:
            return v
    return ""


# ---------------------------------------------------------------- 叶子认领
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


def claim_next_leaf(account):
    """跨进程原子认领下一个未饱和、可映射 category 的缺口叶子。"""
    CLAIM_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIM_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
        claims = _read_claims()
        for b in bundles:
            cat = map_category(b["lineage"])
            if not cat:
                continue
            lid = str(b["id"])
            if lid in claims:
                continue
            st = DISC / f"gap{b['id']}" / f"engine_{cat}.json"
            if st.exists():
                try:
                    if json.loads(st.read_text(encoding="utf-8")).get(
                            "status") == "saturated":
                        continue
                except Exception:
                    pass
            claims[lid] = {"account": account,
                           "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            _write_claims(claims)
            return b["id"], cat
        return None, None


def release_leaf(leaf):
    CLAIM_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIM_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        claims = _read_claims()
        claims.pop(str(leaf), None)
        _write_claims(claims)


def auto_gate_apply(leaf, cat):
    work = DISC / f"gap{leaf}"
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


def _probe_account(api, account):
    """一次最小签名搜索，返回 code；-100 表示该账号登录过期（worker 应退出）。"""
    acc = next((a for a in api.accounts if a["name"] == account), None)
    if acc is None:
        return -100
    uri = "/api/sns/web/v1/search/notes"
    p = {"keyword": "拉面", "page": 1, "page_size": 5,
         "search_id": api.sign.get_search_id(), "sort": "general", "note_type": 0}
    j = api._send("POST", uri, payload=p)
    return j.get("code", -1)


def run_leaf(leaf, category, queries, account=None):
    """返回 'saturated' / 'continue' / 'dead'。"""
    bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
    b = next((x for x in bundles if x["id"] == leaf), None)
    if not b:
        sys.exit(f"leaf {leaf} 不在缺口计划中")

    # 并行时绑定账号、抬高限速；单跑时用轮换池。
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
    print(f"leaf {leaf} {b['name']} → category={category}；"
          f"账号={account or '池轮换'} 限速{gap}s")

    map_names = []
    if FRONT_F.exists():
        fr = json.loads(FRONT_F.read_text(encoding="utf-8"))
        for e in fr.values():
            if leaf in e.get("cuisines", []) and e.get("status") == "new":
                map_names.append(e["name"])
    seeds = map_names + list(b["queries"]["xhs"])
    seeds = list(dict.fromkeys(seeds))

    work = DISC / f"gap{leaf}"
    eng = DiscoveryEngine(None, category, work, notes_per_query=3,
                          max_per_run=queries)
    eng.state["frontier_high"] = seeds
    eng.state["frontier_low"] = []
    cn = _DE.C.cjk_norm
    eng.state["brands"] = {
        k: v for k, v in eng.state["brands"].items()
        if cn(v.get("name", "")) not in _DE.GENERIC_WORDS}
    eng.state["oral"] = {
        k: v for k, v in eng.state["oral"].items() if k not in _DE.GENERIC_WORDS}
    eng.save()

    rep = eng.run(max_queries=queries)
    print("== 报告 ==", json.dumps(rep, ensure_ascii=False))

    if rep["status"] == "saturated":
        print("== 叶子饱和，自动 gate + apply ==")
        admit, gtail, atail = auto_gate_apply(leaf, category)
        print(" ", admit)
        for ln in gtail:
            print("  gate:", ln)
        for ln in atail:
            print("  apply:", ln)
        return "saturated"
    print(f"未饱和（frontier 剩 {rep['frontier_remaining']}），继续本叶子。")
    return "continue"


def worker_loop(account, queries):
    """一个账号一个 worker：认领→跑到饱和/失效→释放→再认领。"""
    finished = 0
    while True:
        leaf, cat = claim_next_leaf(account)
        if leaf is None:
            print(f"[{account}] 没有可认领的缺口叶子，worker 结束。")
            return finished
        st = "continue"
        while st == "continue":
            st = run_leaf(leaf, cat, queries, account=account)
        release_leaf(leaf)
        if st == "saturated":
            finished += 1
        elif st == "dead":
            return finished


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaf", type=int, default=None)
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--pool", action="store_true")
    ap.add_argument("--account", default=None)
    ap.add_argument("--queries", type=int, default=8)
    args = ap.parse_args()

    if args.pool:
        if not args.account:
            sys.exit("--pool 需配合 --account <name>")
        worker_loop(args.account, args.queries)
        return 0

    bundles = json.loads(PLAN_F.read_text(encoding="utf-8"))
    if args.next or args.leaf is None:
        leaf, cat = None, None
        for b in bundles:
            c = map_category(b["lineage"])
            st = DISC / f"gap{b['id']}" / f"engine_{c}.json" if c else None
            if c and not (st and st.exists() and
                          json.loads(st.read_text()).get("status") == "saturated"):
                leaf, cat = b["id"], c
                break
        if leaf is None:
            print("所有可映射缺口叶子均已饱和。")
            return 0
    else:
        leaf = args.leaf
        b = next((x for x in bundles if x["id"] == leaf), None)
        cat = map_category(b["lineage"]) if b else ""
        if not cat:
            sys.exit(f"leaf {leaf} 暂无法映射 category")
    run_leaf(leaf, cat, args.queries)
    return 0


if __name__ == "__main__":
    sys.exit(main())

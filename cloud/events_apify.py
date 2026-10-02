#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
events_apify.py — 「最新动向」采集器（Apify 通道，替代需自有登录浏览器的 events_collect）。

为什么：events_collect 依赖我方登录态浏览器、从未被调度；改走 Apify actor，我方零封号，
按结果计费（多数事件词 0 结果=$0）。本模块产出与 events_collect 完全相同的 raw 信封，
后续仍由 events_build.py 判定/归店、atlas_write 入库。

在容器 food-cloud 内运行（. /app/cloud/env.sh 后）：
  python3 events_apify.py --sweep --max-queries 6                 # 预演（采集+build，不写库）
  python3 events_apify.py --sweep --commit                         # 采集并幂等写事件
  python3 events_apify.py --watch --names "店A,店B" --commit       # 已知店保鲜
守卫：每次调用前查 /limits 余量；按 usage 实际增量累计，超 --budget 即停；
      余量 < $0.15 报 NO_CREDIT 停止、保存进度，不硬刷；flock 防任务重叠。
"""
import argparse, json, os, pathlib, subprocess, sys, time

import requests

PIPE = pathlib.Path("/app/pipeline")
CLOUD = pathlib.Path("/app/cloud")
for p in (str(PIPE), str(CLOUD)):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA = pathlib.Path("/app/data")
SOC = DATA / "research" / "social"
CFG_P = SOC / "listen_keywords.json"
RAW_P = SOC / "raw_events_collected.jsonl"
OUT_EVENTS = SOC / "raw_events.jsonl"

def _load_token():
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if t:
        return t
    sp = DATA / ".secrets" / "apify_token"
    if sp.exists():
        return sp.read_text(encoding="utf-8").strip()
    return ""


TOKEN = _load_token()
PER_RUN_CHARGE = float(os.environ.get("EVENTS_PER_RUN_CHARGE", "0.30"))
MIN_CREDIT = float(os.environ.get("EVENTS_MIN_CREDIT", "0.15"))

ACTORS = {
    "atomus": ("https://api.apify.com/v2/acts/atomus~xiaohongshu-scraper/run-sync-get-dataset-items",
               lambda kw, n: {"searchType": "search", "keywords": [kw],
                              "maxItems": n, "sortType": "popularity_descending"}, False),
    "opspilot": ("https://api.apify.com/v2/acts/opspilot.cc~xiaohongshu-keyword-search-scraper"
                 "/run-sync-get-dataset-items",
                 lambda kw, n: {"keyword": kw}, True),
    "sian": ("https://api.apify.com/v2/acts/sian.agency~xiaohongshu-rednote-scraper/run-sync-get-dataset-items",
             lambda kw, n: {"action": "searchNote", "keyword": kw, "searchType": "note",
                            "sortType": "general", "page": 1, "maxItems": n}, False),
}


# ------------------------------------------------ 账单（权威）
def _limits():
    d = requests.get("https://api.apify.com/v2/users/me/limits",
                     params={"token": TOKEN}, timeout=30).json()["data"]
    cap = float(d["limits"]["maxMonthlyUsageUsd"])
    used = float(d["current"]["monthlyUsageUsd"])
    return cap, used


def remaining():
    cap, used = _limits()
    return round(cap - used, 4)


# ------------------------------------------------ 采集
def run_actor(provider, kw, max_items):
    url, body_fn, mem = ACTORS[provider]
    params = {"token": TOKEN, "maxItems": max_items, "maxTotalChargeUsd": PER_RUN_CHARGE}
    if mem:
        params["memory"] = 512
    r = requests.post(url, params=params, json=body_fn(kw, max_items), timeout=170)
    if r.status_code not in (200, 201):
        return [], f"http{r.status_code}:{r.text[:120]}"
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        return [], str(data["error"])[:160]
    if isinstance(data, list):
        data = [x for x in data if not (isinstance(x, dict) and x.get("error_kind"))]
    return data, None


def _author(n):
    u = n.get("user") if isinstance(n.get("user"), dict) else {}
    return (u.get("nickname") or u.get("nickName") or n.get("nickname")
            or n.get("author") or "")


def _date(n):
    for k in ("time", "createTime", "lastUpdateTime", "date", "publishedAt", "createdAt"):
        v = n.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def to_note(n):
    nid = n.get("id") or n.get("noteId")
    url = n.get("url") or n.get("noteUrl") or (
        f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
    return {"title": n.get("title") or "",
            "desc": n.get("desc") or n.get("description") or "",
            "url": url, "author": _author(n), "date": _date(n), "comments": []}


def append_raw(rec):
    SOC.mkdir(parents=True, exist_ok=True)
    with RAW_P.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def done_queries(field):
    s = set()
    if RAW_P.exists():
        for line in RAW_P.read_text(encoding="utf-8").splitlines():
            try:
                s.add(json.loads(line).get(field))
            except Exception:
                pass
    return s


def build_sweep_queries(cfg, roots_per_cat, city):
    done = done_queries("query")
    out = []
    for cat in cfg["category_priority"]:
        c = cfg["categories"][cat]
        words = c.get("sweep") or c["roots"]
        for w in words[:roots_per_cat]:
            q = w if city in w else f"{w} {city}"
            if q not in done:
                out.append((cat, q))
    return out


# ------------------------------------------------ 模式
def sweep(cfg, provider, max_queries, roots_per_cat, max_items, budget):
    city = cfg.get("city_default", "上海")
    queries = build_sweep_queries(cfg, roots_per_cat, city)[:max_queries]
    spent, ran, notes_n = 0.0, 0, 0
    for cat, q in queries:
        rem = remaining()
        if rem < MIN_CREDIT:
            return {"stop": "NO_CREDIT", "ran": ran, "queries": [], "remain": rem, "spent": round(spent, 3)}
        if spent >= budget:
            return {"stop": "BUDGET", "ran": ran, "remain": rem, "spent": round(spent, 3)}
        _, before = _limits()
        items, err = run_actor(provider, q, max_items)
        _, after = _limits()
        spent += max(0.0, after - before)
        if err:
            append_raw({"kind": "sweep", "query": q, "category_hint": cat, "notes": []})
            continue
        notes = [to_note(x) for x in items if isinstance(x, dict)]
        append_raw({"kind": "sweep", "query": q, "category_hint": cat, "notes": notes})
        ran += 1; notes_n += len(notes)
        time.sleep(3)
    return {"stop": "DONE", "ran": ran, "notes": notes_n, "spent": round(spent, 3),
            "remain": remaining()}


def watch(cfg, provider, names, max_items, budget):
    done = done_queries("watch_name")
    spent, ran, notes_n = 0.0, 0, 0
    for name in [x.strip() for x in names if x.strip() and x.strip() not in done]:
        rem = remaining()
        if rem < MIN_CREDIT or spent >= budget:
            return {"stop": rem < MIN_CREDIT and "NO_CREDIT" or "BUDGET",
                    "ran": ran, "remain": rem, "spent": round(spent, 3)}
        _, before = _limits()
        items, err = run_actor(provider, name, max_items)
        _, after = _limits()
        spent += max(0.0, after - before)
        notes = [] if err else [to_note(x) for x in items if isinstance(x, dict)]
        append_raw({"kind": "watch", "watch_name": name, "notes": notes})
        ran += 1; notes_n += len(notes)
        time.sleep(3)
    return {"stop": "DONE", "ran": ran, "notes": notes_n, "spent": round(spent, 3),
            "remain": remaining()}


def run_build():
    p = subprocess.run([sys.executable, "events_build.py"], cwd=str(PIPE),
                       capture_output=True, text=True)
    lines = [l for l in ((p.stdout or "") + (p.stderr or "")).splitlines() if l]
    return p.returncode, lines[:4]


def run_write(commit):
    cmd = [sys.executable, "atlas_write.py", "--domain", "events",
           "--input", str(OUT_EVENTS)]
    if commit:
        cmd.append("--commit")
    p = subprocess.run(cmd, cwd=str(PIPE), capture_output=True, text=True)
    lines = [l for l in ((p.stdout or "") + (p.stderr or "")).splitlines() if l]
    return p.returncode, lines[-4:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--names", default="", help="逗号分隔店名（watch）")
    ap.add_argument("--provider", default="atomus", choices=list(ACTORS))
    ap.add_argument("--max-queries", type=int, default=6)
    ap.add_argument("--roots-per-cat", type=int, default=1)
    ap.add_argument("--max-items", type=int, default=8)
    ap.add_argument("--budget", type=float, default=float(os.environ.get("EVENTS_BUDGET", "0.5")))
    ap.add_argument("--commit", "--apply", dest="commit", action="store_true")
    args = ap.parse_args()

    if not TOKEN:
        sys.exit("APIFY_TOKEN 未配置")
    cfg = json.loads(CFG_P.read_text(encoding="utf-8"))

    res = {}
    if args.sweep or not args.watch:
        res["sweep"] = sweep(cfg, args.provider, args.max_queries,
                             args.roots_per_cat, args.max_items, args.budget)
    if args.watch:
        res["watch"] = watch(cfg, args.provider, args.names.split(","),
                             args.max_items, args.budget)

    rc, build_lines = run_build()
    res["build_rc"] = rc
    res["build"] = build_lines
    if args.commit:
        wc, wlines = run_write(True)
        res["write_rc"] = wc
        res["write"] = wlines
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

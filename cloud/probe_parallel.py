#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_parallel.py — 出餐方式探针的【多模型分片并发】runner。

相对 production_model_probe.run()（单 provider 串行、品牌间隔 sleep）的升级：
  · 品牌进共享队列；每个【便宜模型】一个 worker 线程并行首判（worker 绑定模型），
    把各模型独立的免费配额同时用起来 → 吞吐 ≈ 可用便宜模型数 × 单模型吞吐；
  · 证据按品牌持久缓存（/app/data/probe/evidence_cache），多 worker / 复跑不重复搜，
    证据检索限并发，避免打爆 searxng；
  · 便宜模型首判；仅严判(复热)/低置信才升级强模型对抗复核（confirm_if_severe）；
  · 某模型 429 SetLimitExceeded → mark dead、品牌回队交其余 worker；
    便宜模型全死时，按 --allow-strong-fallback（默认开）用强模型继续。
  · 只在 --ingest 时 write_findings；其余字段不动；宁空不假。

用法：
  python3 probe_parallel.py --all --ingest
  python3 probe_parallel.py --limit 200 --workers 6
  python3 probe_parallel.py --brands 外婆家,绿波廊
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import pathlib
import queue
import sys
import threading
import time
import urllib.error

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core
import model_providers as MP
import production_model_probe as P

CACHE_DIR = pathlib.Path("/app/data/probe/evidence_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = pathlib.Path("/app/data/research/atlas")
_search_sem = threading.Semaphore(4)   # 证据检索并发上限
_cache_lock = threading.Lock()

# 死号状态持久化到数据卷（默认在镜像层 /app/cloud，重建即丢）；重定向后重新加载
P._POOL_STATE_PATH = "/app/data/probe/model_pool_state.json"
try:
    P._POOL["dead"] = set(P._load_pool_state().get("dead", []))
except Exception:
    pass


class RateGate:
    """账号级自适应节流：所有 worker 共享最小请求间隔；遇普通 429(非配额) 全局退避，
    避免在单账号低 RPM 下空转。429 越多间隔自动拉长，连续成功后缓慢回落。"""
    def __init__(self, spacing=2.5):
        self.lock = threading.Lock()
        self.next_ts = 0.0
        self.spacing = spacing
        self.backoffs = 0

    def acquire(self):
        while True:
            with self.lock:
                now = time.time()
                if now >= self.next_ts:
                    self.next_ts = now + self.spacing
                    return
                wait = self.next_ts - now
            time.sleep(min(wait, 1.0))

    def backoff(self, seconds):
        with self.lock:
            self.backoffs += 1
            # 每次普通429：全局冷却，并把稳态间隔小幅拉长（上限 12s）
            self.spacing = min(12.0, self.spacing + 0.8)
            self.next_ts = max(self.next_ts, time.time() + seconds)

    def relax(self):
        with self.lock:
            # 成功后缓慢回落间隔（下限 2s）
            self.spacing = max(2.0, self.spacing - 0.15)


RATE = RateGate()
STRONG_MARK = ("pro", "glm-5-2", "turbo")


def is_strong(m):
    ml = m.lower()
    return any(k in ml for k in STRONG_MARK)


def cache_path(brand):
    h = hashlib.sha1(brand.encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def gather_cached(brand, n_queries=3):
    """证据按品牌缓存：命中文件直接读；否则限并发检索后落盘。"""
    cp = cache_path(brand)
    with _cache_lock:
        if cp.exists():
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                pass
    with _search_sem:
        # 双检（可能在等信号量期间已被其他线程取到）
        if cp.exists():
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                pass
        ev = P.gather_evidence(brand, n_queries=n_queries)
        try:
            cp.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return ev


def build_brands(args):
    rests = core.fetch_all("restaurants",
                           "id,name,status,chain_type,review_count,production_model",
                           order_col="id")
    brands = {}
    for r in rests:
        if r.get("status") == "closed":
            continue
        brands.setdefault(P.brand_core(r["name"]), []).append(r)
    if args.brands:
        out = []
        for key in [x.strip() for x in args.brands.split(",") if x.strip()]:
            hit = next((b for b in brands if key in b), None)
            if hit:
                out.append(hit)
        return brands, out

    def resolved(rows):
        # 品牌下所有分店都已有出餐方式结论 → 视为已处理（pending-only 跳过）
        return all(r.get("production_model") for r in rows)

    if args.all:
        names = [b for b in brands
                 if args.reprocess_all or not resolved(brands[b])]
    else:
        def rank(b):
            rs = brands[b]
            chain = 0 if all(r.get("chain_type") == "独立店" for r in rs) else 1
            return (chain, max(r.get("review_count") or 0 for r in rs))
        pool = [b for b in brands
                if args.reprocess_all or not resolved(brands[b])]
        names = sorted(pool, key=rank, reverse=True)[:args.limit]
    return brands, names


def worker(provider, model, q, done_flag, allow_strong, stats, lock):
    """绑定一个模型，循环从队列取品牌首判。模型额度死 → 退出（品牌已回队）。"""
    while True:
        try:
            bname = q.get_nowait()
        except queue.Empty:
            return
        try:
            rows = done_flag["brands"].get(bname)
            if not rows:
                continue
            rids = [r["id"] for r in rows]
            locs = "; ".join(r["name"] for r in rows[:6])
            evidence = gather_cached(bname)
            RATE.acquire()
            try:
                sig = P.extract_signals_once(provider, model, bname, locs, evidence)
            except urllib.error.HTTPError as e:
                body_txt = ""
                try:
                    body_txt = e.read().decode("utf-8", "ignore")
                except Exception:
                    pass
                if e.code == 429 and "SetLimitExceeded" in body_txt:
                    P.mark_model_dead(model)
                    q.put(bname)   # 回队交其他模型
                    with lock:
                        stats["dead"].append(model)
                    return
                if e.code == 429:
                    RATE.backoff(15)   # 账号级 RPM：全局退避，再回队
                q.put(bname)
                continue
            except TimeoutError:
                RATE.backoff(8)
                q.put(bname)  # 服务挂起，回队重试
                continue
            if not sig:
                with lock:
                    stats["no_signal"].append(bname)
                continue
            RATE.relax()
            sig = P.filter_signals_by_evidence(sig, evidence)
            verdict = P.adjudicate(sig)
            verdict = P.confirm_if_severe(provider, bname, locs, evidence, verdict)
            n_add = 0
            if done_flag["ingest"]:
                n_add = P.write_findings(bname, rids, verdict)
            with lock:
                stats["done"].append(bname)
                stats["findings"] += n_add
            done_flag["results"].append({"brand": bname, "rids": rids,
                                        "verdict": verdict, "model": model})
        finally:
            q.task_done()


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--brands", default="")
    ap.add_argument("--ingest", action="store_true")
    ap.add_argument("--workers", type=int, default=0, help="0=按便宜模型数")
    ap.add_argument("--allow-strong-fallback", action="store_true", default=True)
    ap.add_argument("--reprocess-all", action="store_true",
                    help="含已有 production_model 结论的品牌（默认 pending-only 推进尾部）")
    args = ap.parse_args()

    P.ensure_search_ready()
    ps = MP.load_providers()
    if not ps:
        print("未配置 LLM provider，退出。")
        return
    provider = ps[0]
    brands, names = build_brands(args)
    if not names:
        print("无目标品牌。")
        return

    live = [m for m in provider.models if m not in P._POOL["dead"]]
    cheap = [m for m in live if not is_strong(m)]
    first_pool = cheap or live
    n_workers = args.workers or min(len(first_pool), max(1, len(names)))

    q = queue.Queue()
    for b in names:
        q.put(b)
    stats = {"done": [], "no_signal": [], "dead": [], "findings": 0}
    done_flag = {"brands": brands, "ingest": args.ingest, "results": []}
    lock = threading.Lock()

    print(f"provider={provider.name} 目标品牌{len(names)} workers={n_workers} "
          f"首判模型={first_pool} ingest={args.ingest}\n")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = []
        for i in range(n_workers):
            model = first_pool[i % len(first_pool)]
            futs.append(ex.submit(worker, provider, model, q, done_flag,
                                  args.allow_strong_fallback, stats, lock))
        # 便宜模型全死且仍有积压 → 用强模型补 worker
        while True:
            time.sleep(5)
            remaining = q.qsize()
            alive = sum(1 for f in futs if f.running())
            if remaining == 0:
                break
            strong_live = [m for m in live if is_strong(m) and m not in stats["dead"]]
            if alive == 0 and strong_live and args.allow_strong_fallback:
                print(f"  [fallback] 便宜模型耗尽，强模型 {strong_live} 接续 {remaining} 品牌")
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(strong_live)) as ex2:
                    for m in strong_live:
                        ex2.submit(worker, provider, m, q, done_flag,
                                   args.allow_strong_fallback, stats, lock)
                break
            if alive == 0 and not strong_live:
                print(f"  [stop] 所有模型配额耗尽，剩余 {remaining} 品牌待下次")
                break
        for f in concurrent.futures.as_completed(futs):
            f.result()

    elapsed = round(time.time() - t0, 1)
    rp = REPORT_DIR / f"production_probe_parallel_{datetime.date.today()}.json"
    rp.write_text(json.dumps(done_flag["results"], ensure_ascii=False, indent=1),
                  encoding="utf-8")
    summary = {
        "targets": len(names), "processed": len(stats["done"]),
        "no_signal": len(stats["no_signal"]), "remaining": q.qsize(),
        "dead_models": sorted(set(stats["dead"])),
        "new_findings": stats["findings"], "elapsed_s": elapsed,
        "throughput_brand_per_min": round(len(stats["done"]) / (elapsed / 60), 1) if elapsed else 0,
    }
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"报告：{rp}")
    core.notify.info("probe_parallel：" + json.dumps(summary, ensure_ascii=False),
                     key="probe_parallel")


if __name__ == "__main__":
    run()

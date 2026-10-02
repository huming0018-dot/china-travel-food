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

# 默认只跑「协作奖励计划」已授权模型（调用按日返免费包），避免并行探针遍历全模型付费；
# --full-models 才放开全量（可能付费）。与 fleet_grid_run.AUTHORIZED_MODELS 保持一致。
AUTHORIZED_MODELS = {"deepseek-v4-flash-ga-260731", "glm-5-2-260617"}

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


_ZERO_TTL = 6 * 3600   # 空取证缓存复用窗口：过期重搜，恢复中毒/瞬时空结果


def _ev_hits(ev):
    return sum(len(e.get("results", [])) for e in ev)


def _ev_raw(ev):
    return sum(e.get("raw", 0) for e in ev)


def _cache_fresh(cp):
    """非空缓存长期复用；空缓存仅在 TTL 内复用（过期视为 miss 重搜）。"""
    try:
        cached = json.loads(cp.read_text(encoding="utf-8"))
    except Exception:
        return None
    if _ev_hits(cached) > 0:
        return cached
    try:
        if time.time() - cp.stat().st_mtime < _ZERO_TTL:
            return cached
    except Exception:
        return None
    return None


def gather_cached(brand, n_queries=3):
    """证据按品牌缓存：命中（非空，或空且在 TTL 内）直接读；否则限并发检索后落盘。"""
    cp = cache_path(brand)
    cached = _cache_fresh(cp)
    if cached is not None:
        return cached
    with _search_sem:
        cached = _cache_fresh(cp)   # 双检（等信号量期间可能已被他线程取到）
        if cached is not None:
            return cached
        ev = P.gather_evidence(brand, n_queries=n_queries)
        # 全部搜索失败(raw=0，基础设施瞬态)：不写缓存、下次重试；raw>0（真搜过）才落盘
        if _ev_raw(ev) > 0:
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
            provider._llm_sem.acquire()   # 占该账号一个在飞 LLM 名额
            try:
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
                        dk = f"{provider.name}/{model}"
                        P.mark_model_dead(dk)
                        q.put(bname)   # 回队交其他模型
                        with lock:
                            stats["dead"].append(dk)
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
            finally:
                provider._llm_sem.release()
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
    ap.add_argument("--full-models", action="store_true",
                    help="放开全部模型（默认仅授权免费模型；全量可能付费）")
    args = ap.parse_args()

    P.ensure_search_ready()
    ps = MP.load_providers()
    if not ps:
        print("未配置 LLM provider，退出。")
        return
    # 每账号在飞 LLM 并发硬上限：免费/单账号并发低，worker 数（按便宜模型）会远超账号
    # 实际并发，不限就会在服务端排队→非流式尾部超时→回队再挤的活锁。等待信号量的线程
    # 不发请求，故不占服务端队列。多账号（ARK_API_KEYS）自动线性放大总并发。
    _per_acct = max(1, int(os.environ.get("LLM_CONCURRENCY_PER_ACCOUNT", "3")))
    for _prov in ps:
        _prov._llm_sem = threading.BoundedSemaphore(_per_acct)
    brands, names = build_brands(args)
    if not names:
        print("无目标品牌。")
        return

    # 跨所有 provider(账号) 收集 (provider, model) 槽位；每账号独立 RPM/配额 → 真并行
    # 默认仅授权（免费）模型；--full-models 才纳入全量。
    cheap_slots, strong_slots = [], []
    for prov in ps:
        for m in prov.models:
            if not args.full_models and m not in AUTHORIZED_MODELS:
                continue
            if f"{prov.name}/{m}" in P._POOL["dead"]:
                continue
            (strong_slots if is_strong(m) else cheap_slots).append((prov, m))
    first_pool = cheap_slots or strong_slots
    n_workers = args.workers or min(len(first_pool), max(1, len(names)))

    q = queue.Queue()
    for b in names:
        q.put(b)
    stats = {"done": [], "no_signal": [], "dead": [], "findings": 0}
    done_flag = {"brands": brands, "ingest": args.ingest, "results": []}
    lock = threading.Lock()

    slot_lbl = [f"{p.name}/{m}" for p, m in first_pool]
    print(f"账号数={len(ps)} 目标品牌{len(names)} workers={n_workers} "
          f"槽位={slot_lbl} ingest={args.ingest}\n")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
        futs = []
        for i in range(n_workers):
            prov, model = first_pool[i % len(first_pool)]
            futs.append(ex.submit(worker, prov, model, q, done_flag,
                                  args.allow_strong_fallback, stats, lock))
        # 便宜槽全死且仍有积压 → 用强模型槽补 worker
        while True:
            time.sleep(5)
            remaining = q.qsize()
            alive = sum(1 for f in futs if f.running())
            if remaining == 0:
                break
            strong_live = [(p, m) for (p, m) in strong_slots
                          if f"{p.name}/{m}" not in stats["dead"]]
            if alive == 0 and strong_live and args.allow_strong_fallback:
                print(f"  [fallback] 便宜模型耗尽，强槽 {[p.name+'/'+m for p,m in strong_live]} "
                      f"接续 {remaining} 品牌")
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=len(strong_live)) as ex2:
                    for p, m in strong_live:
                        ex2.submit(worker, p, m, q, done_flag,
                                   args.allow_strong_fallback, stats, lock)
                break
            if alive == 0 and not strong_live:
                print(f"  [stop] 所有账号模型配额耗尽，剩余 {remaining} 品牌待下次")
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""production_runner.py — 出餐方式（production_model）配额感知调度器。

设计目标：在 LLM 配额有限、会被限流的现实下，无人值守地完成
  ① 首次全量覆盖 → ② 日常增量（新店 / 仍无标签店）→ ③ 每周全量复校。
断点续跑：状态落 production_runner_state.json；遇账号级限流（配额耗尽）立即暂停，
下一班自动从断点继续，不空转、不硬刷。

调用：
  python3 production_runner.py                 # 自动：全量未完成跑全量，完成后跑增量
  FORCE=full python3 production_runner.py      # 开启一轮全量复校（由每周 cron 触发）
环境：BATCH（每轮品牌数，默认 5）；BRAND_GAP 由探针内部读取。
只写 findings；gate 写库由 cron 链 gate_apply.py --apply 完成。
"""
import json
import os
import pathlib
import sys
import time
import datetime
import threading
import urllib.error

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core  # noqa: E402
import production_model_probe as PMP  # noqa: E402

STATE = pathlib.Path("/app/data/post_record/production_runner_state.json")
MAX_NULL_ATTEMPTS = 2


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"done": {}, "reverify": 0, "reverify_cursor": [], "last_run": None}


def save_state(st):
    st["last_run"] = now()
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def hard_watch(fn, deadline):
    """单品牌顶层硬墙钟：守护线程跑整个 probe，到点未返回即强弃，
    保证调度器不会因任一搜索/LLM/代理挂起而永久卡死。"""
    box = {}

    def work():
        try:
            box["r"] = fn()
        except Exception as e:  # noqa: BLE001
            box["e"] = e

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(deadline)
    if th.is_alive():
        return None, True
    if "e" in box:
        raise box["e"]
    return box.get("r"), False


def build_brands():
    rests = core.fetch_all(
        "restaurants", "id,name,status,chain_type,review_count,production_model",
        order_col="id")
    brands = {}
    for r in rests:
        if r.get("status") == "closed":
            continue
        key = PMP.brand_core(r["name"])
        brands.setdefault(key, []).append(r)
    return brands


def rank_full(rs):
    is_chain = 0 if all(r.get("chain_type") == "独立店" for r in rs) else 1
    return (is_chain, max(r.get("review_count") or 0 for r in rs))


def select_targets(brands, st, batch):
    """返回 (mode, [(brand, rs)])。"""
    # 每周复校进行中（或被 FORCE 开启）
    if os.environ.get("FORCE") == "full":
        st["reverify"] = 1
        st["reverify_cursor"] = []
    if st.get("reverify"):
        cursor = set(st.get("reverify_cursor") or [])
        ordered = sorted(brands, key=lambda b: rank_full(brands[b]), reverse=True)
        names = [b for b in ordered if b not in cursor][:batch]
        return "reverify", [(b, brands[b]) for b in names]
    # 首次全量：仍有从未处理的品牌
    not_done = [b for b in brands if b not in st["done"]]
    if not_done:
        ordered = sorted(not_done, key=lambda b: rank_full(brands[b]), reverse=True)
        names = ordered[:batch]
        return "full", [(b, brands[b]) for b in names]
    # 增量：仍无标签且尝试次数未超上限
    inc = []
    for b, rs in brands.items():
        rec = st["done"].get(b) or {}
        no_label = all(not r.get("production_model") for r in rs)
        if no_label and rec.get("attempts", 0) < MAX_NULL_ATTEMPTS:
            inc.append(b)
    ordered = sorted(inc, key=lambda b: rank_full(brands[b]), reverse=True)
    names = ordered[:batch]
    return "incremental", [(b, brands[b]) for b in names]


def main():
    batch = int(os.environ.get("RUN_BATCH", os.environ.get("BATCH", "5")))
    st = load_state()
    brands = build_brands()
    mode, targets = select_targets(brands, st, batch)

    p, _model = PMP.pick_provider_model()
    if not p:
        print("未配置 LLM provider（ARK），退出。")
        return
    print(f"[runner] mode={mode}；品牌总数 {len(brands)}；本轮 {len(targets)}；"
          f"已完成 {len(st['done'])}；reverify={st.get('reverify')}\n")

    # 轻量 LLM 预检：限流/不可用班次立即暂停，避免对每个品牌空跑数分钟搜索
    pf_model = PMP.candidate_models(p)[0]

    def _pf():
        return PMP.chat_raw(
            p, pf_model, [{"role": "user", "content": "ping，回复 ok"}],
            timeout=15, retries=1, hard_cap=30)

    llm_ok = False
    try:
        r, to = hard_watch(_pf, 45)
        llm_ok = (not to) and bool(r)
    except urllib.error.HTTPError as e:
        print(f"[preflight] LLM HTTP {e.code}")
        llm_ok = e.code not in (429, 503)
    except Exception:
        llm_ok = False
    if not llm_ok:
        print("⏸ LLM 预检未通过（账号限流/服务不可用），本轮不跑搜索，下一班再试。")
        save_state(st)
        return

    processed, paused = 0, None
    timeouts = 0
    brand_hard = int(os.environ.get("BRAND_HARD", "240"))
    for bname, rs in targets:
        rids = [r["id"] for r in rs]
        locs = "; ".join(r["name"] for r in rs[:6])
        print(f"● {bname} | 分店 {rids}")
        res, timed_out = hard_watch(
            lambda: PMP.probe_brand(p, PMP.candidate_models(p), bname, locs),
            brand_hard)
        if timed_out:
            timeouts += 1
            sig, status = None, "brand_timeout"
            print("    ⏱ 单品牌硬墙钟到点，强弃该品牌")
        else:
            sig, _ev, status = res
        if status == "llm_ratelimit":
            paused = "账号级 LLM 配额/限流，本轮提前暂停，下一班续跑"
            print("    ⏸", paused)
            break
        if timeouts >= 2:
            paused = "连续品牌搜索/代理超时，本轮提前暂停，下一班续跑"
            print("    ⏸", paused)
            break
        if status == "ok" and sig:
            verdict = PMP.adjudicate(sig)
            verdict = PMP.confirm_if_severe(p, bname, locs, _ev, verdict)
            n_add = PMP.write_findings(bname, rids, verdict)
            label = verdict["production_model"]
            n_dom = len(verdict.get("sources") or [])
            st["done"][bname] = {"label": label, "n_dom": n_dom, "ts": now(),
                                 "attempts": 0}
            print(f"    => {label} | 源{n_dom} | findings+{n_add}")
        else:
            rec = st["done"].get(bname) or {"attempts": 0}
            rec["attempts"] = rec.get("attempts", 0) + 1
            rec["ts"] = now()
            rec.setdefault("label", None)
            st["done"][bname] = rec
            print(f"    ~ 暂无可采信号（{status}），attempts={rec['attempts']}")
        if mode == "reverify":
            st["reverify_cursor"].append(bname)
        processed += 1
        gap = int(os.environ.get("BRAND_GAP", "12"))
        if gap:
            time.sleep(gap)

    # 复校走完一圈 → 清标志
    if st.get("reverify") and not paused:
        if len(set(st["reverify_cursor"])) >= len(brands):
            st["reverify"] = 0
            st["reverify_cursor"] = []
            print("\n[runner] 全量复校完成，恢复增量模式。")
    save_state(st)

    labeled = sum(1 for rec in st["done"].values() if rec.get("label"))
    print(f"\n[runner] 本轮处理 {processed}；累计有标签品牌 {labeled}/{len(brands)}；"
          f"{'暂停：' + paused if paused else '正常结束'}")


if __name__ == "__main__":
    main()

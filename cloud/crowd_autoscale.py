#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_autoscale.py — 众包采集器「去重扩容」自动看护（定时任务，直接服务 public.crowd_tasks）。

为什么需要它：
  crowd_scale.py 的发布通道经 crowd_pack→crowd_v4_admin，实际写进的是【移动端】
  crowd_v4.tasks（一店一任务、无 pack 列）；而 Chrome 扩展采集器 crowd_fetch_tasks
  读的是 public.crowd_tasks（6 店 pack 数组）。本脚本复刻生产现存包的形状，
  直接 POST /crowd_tasks 发布扩展采集器能领取的任务包，避免发错表。

做什么（每轮）：
  1. 统计 open 任务包数（=可派库存）；
  2. 仅当 open 包数低于 MIN_OPEN_PACKS 才补，补到 TARGET_OPEN_PACKS，
     且单次新增不超过 MAX_NEW_PACKS_PER_RUN（护栏，防失控/防压垮设备）；
  3. 严格去重：已有 accepted 证据的店 + 所有任务包（任何状态，含 fulfilled/closed）
     里的店，一律不重发；
  4. 候选优先「口味分缺口」（active 且 score_taste 为空），按 score_total 降序，
     只发上海范围、店名合法、非测试脏数据的店；
  5. 每 6 家店切一个 pack，直接 POST /crowd_tasks（store / both / kpi5 / quota50）。

宁空不假：候选不足就少发、没有合规候选就不发；水位够就什么都不做。

用法：
  python3 cloud/crowd_autoscale.py            # dry-run，只打印计划，不写
  python3 cloud/crowd_autoscale.py --apply    # 实际发布
环境变量（均有默认值）：
  SUPABASE_SERVICE_ROLE_KEY / NEXT_PUBLIC_SUPABASE_URL
  CROWD_AUTO_MIN_OPEN(20) CROWD_AUTO_TARGET_OPEN(30)
  CROWD_AUTO_MAX_NEW_PACKS(10) CROWD_AUTO_PACK_SIZE(6) CROWD_AUTO_QUOTA(50)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

BASE = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
        .rstrip("/") or "https://bdwrhshgdeghgyzwpxnl.supabase.co")
REST = BASE + "/rest/v1"
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

PACK_SIZE = int(os.environ.get("CROWD_AUTO_PACK_SIZE", "6"))
MIN_OPEN_PACKS = int(os.environ.get("CROWD_AUTO_MIN_OPEN", "20"))
TARGET_OPEN_PACKS = int(os.environ.get("CROWD_AUTO_TARGET_OPEN", "30"))
MAX_NEW_PACKS_PER_RUN = int(os.environ.get("CROWD_AUTO_MAX_NEW_PACKS", "10"))
QUOTA = int(os.environ.get("CROWD_AUTO_QUOTA", "50"))
KPI = 5
SOURCE = "autoscale"

# 仅认上海行政区（restaurants 无 city 列，用 district 兜底防脏数据）
SH_DISTRICTS = {
    "黄浦区", "徐汇区", "静安区", "长宁区", "浦东新区", "闵行区", "杨浦区",
    "虹口区", "普陀区", "嘉定区", "宝山区", "松江区", "青浦区", "奉贤区",
    "金山区", "崇明区",
}
# 回归测试/脏数据特征
BAD_NAME = re.compile(r"TEST|zzz|__|测试任务|回归测试|example|dummy", re.I)


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def headers():
    if not KEY:
        sys.exit("缺少 SUPABASE_SERVICE_ROLE_KEY（source deploy.env 后运行）")
    return {"apikey": KEY, "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json"}


def request(method, path, body=None, retries=4):
    url = REST + path
    data = json.dumps(body).encode() if body is not None else None
    h = headers()
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode()
                return r.status, (json.loads(raw) if raw else None), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last = f"HTTP {e.code} {e.read().decode()[:200]}"
                time.sleep(min(2 ** i, 15))
                continue
            return e.code, e.read().decode(), {}
        except Exception as e:  # 网络抖动
            last = repr(e)
            time.sleep(min(2 ** i, 15))
    raise RuntimeError(f"{method} {path} 连续失败: {last}")


def fetch_all(path, page=1000):
    """分页拉全（PostgREST 单页上限 1000）。"""
    out, off = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        st, body, _ = request("GET", f"{path}{sep}limit={page}&offset={off}")
        if st != 200:
            raise RuntimeError(f"fetch_all {path} -> {st} {str(body)[:200]}")
        if not body:
            break
        out.extend(body)
        if len(body) < page:
            break
        off += page
        time.sleep(0.1)
    return out


def norm(name):
    """保守归一：去空白/标点/括号差异 + 小写，用于跨繁简/异写去重。"""
    s = str(name or "").strip().lower()
    return re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]+&、,，.。/／]+", "", s)


def valid_store(r):
    name = (r.get("name") or "").strip()
    if len(name) < 2 or len(name) > 100:
        return False
    if BAD_NAME.search(name):
        return False
    if r.get("district") and r["district"] not in SH_DISTRICTS:
        return False
    return True


def load_covered():
    """返回 (归一店名集合, open 包数)。
    覆盖 = ①已 accepted 证据的 matched_store ②所有任务包（任意状态）里的店。"""
    covered = set()

    # ① 已 accepted 笔记证据锚定的店
    proofs = fetch_all(
        "/crowd_proofs?select=matched_store&gate_status=eq.accepted&kind=eq.note")
    for p in proofs:
        ms = p.get("matched_store")
        if ms:
            covered.add(norm(ms))

    # ② 所有任务包（含 open/in_progress/fulfilled/closed）
    tasks = fetch_all("/crowd_tasks?select=task_id,status,pack")
    open_packs = 0
    for t in tasks:
        if t.get("status") == "open":
            open_packs += 1
        pack = t.get("pack")
        if isinstance(pack, list):
            for s in pack:
                if s:
                    covered.add(norm(s))
    return covered, open_packs


def load_candidates(need):
    """fill 优先：active 且 score_taste 空，按 score_total 降序多拉一些供去重后取用。"""
    fetch_n = min(need + 200, 800)
    rows = fetch_all(
        "/restaurants?status=eq.active&score_taste=is.null"
        "&select=name,district,tier,score_total"
        "&order=score_total.desc.nullslast"
        f"&limit={fetch_n}")
    return rows


def main():
    ap = argparse.ArgumentParser(description="众包去重扩容自动看护")
    ap.add_argument("--apply", action="store_true", help="实际发布（默认 dry-run）")
    args = ap.parse_args()

    log("═══ crowd_autoscale 开始（{}）═══".format("APPLY" if args.apply else "dry-run"))

    covered, open_packs = load_covered()
    log(f"当前水位：open 包 {open_packs} 个；已覆盖店名集合 {len(covered)} 个")
    log(f"护栏：MIN_OPEN={MIN_OPEN_PACKS} TARGET_OPEN={TARGET_OPEN_PACKS} "
        f"单次最多新增 {MAX_NEW_PACKS_PER_RUN} 包 / 每包 {PACK_SIZE} 店 / quota={QUOTA}")

    if open_packs >= MIN_OPEN_PACKS:
        log(f"库存充足（open {open_packs} >= {MIN_OPEN_PACKS}），本轮不发新包。")
        return

    gap_packs = TARGET_OPEN_PACKS - open_packs
    new_packs = min(gap_packs, MAX_NEW_PACKS_PER_RUN)
    need_stores = new_packs * PACK_SIZE
    log(f"缺口 {gap_packs} 包，本轮计划新增 {new_packs} 包，需要约 {need_stores} 家未覆盖店")

    candidates = load_candidates(need_stores)
    fresh, seen = [], set()
    for r in candidates:
        if not valid_store(r):
            continue
        key = norm(r.get("name"))
        if not key or key in covered or key in seen:
            continue
        seen.add(key)
        fresh.append(r["name"].strip())
        if len(fresh) >= need_stores:
            break

    log(f"候选 {len(candidates)} 家，去重后可用 {len(fresh)} 家")
    if not fresh:
        log("没有合规的未覆盖候选（宁空不假），本轮不发任何包。")
        return

    # 切包（末包可不足 PACK_SIZE）
    packs = [fresh[i:i + PACK_SIZE] for i in range(0, len(fresh), PACK_SIZE)]
    packs = packs[:new_packs]
    log(f"实际切出 {len(packs)} 个包（共 {sum(len(p) for p in packs)} 家店）")

    created = 0
    for idx, pack in enumerate(packs, 1):
        body = {
            "pack_type": "store",
            "pack": pack,
            "target": "both",
            "kpi_min": KPI,
            "quota_day": QUOTA,
            "status": "open",
            "source": SOURCE,
        }
        if not args.apply:
            log(f"[dry-run] 包{idx}（{len(pack)}店）：{pack}")
            continue
        st, resp, _ = request("POST", "/crowd_tasks", body)
        if st in (200, 201):
            tid = resp[0].get("task_id") if isinstance(resp, list) and resp else "?"
            created += 1
            log(f"✅ 包{idx} 已发 task_id={tid}（{len(pack)}店）：{pack}")
        else:
            log(f"❌ 包{idx} 发布失败 HTTP {st} {str(resp)[:200]}")
        time.sleep(0.3)

    if args.apply:
        log(f"完成：本轮新增 {created} 个任务包。")
    else:
        log(f"dry-run 完成：计划 {len(packs)} 个包；加 --apply 实际发布。")


if __name__ == "__main__":
    main()

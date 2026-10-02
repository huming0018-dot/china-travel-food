#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_apify_fill.py — 账号无关的真实食客评价兜底回填（v4：每店封顶 + 查询阶梯 + 持久熔断 + 日预算）。

v4 根修复（方案见 cloud/APIFY_OPTIMAL_PLAN.md；针对 $44.93 被烧、"笔记20 采信0"、失控重跑）：
  1. 每店尝试台账 attempts，每周期最多 MAX_SHOP_ATTEMPTS(2) 次；超限转 deferred，治失控重跑
     （10-01 旧循环 344 runs 仅完成 37 店）。
  2. 查询阶梯：q1=品牌 分店 上海；0 采信则 q2=品牌 分店 招牌菜 堂食 上海，绕开名店裸搜 19/20 合集。
  3. 持久全局熔断 circuit（指数退避 3→6→12→24h），跨脚本调用；熔断前区分「查询问题
     (合集/有锚定)」与「actor 问题(纯跑题 0 锚定)」，治外层重启重置 preflight。
  4. 日预算闸门 daily allowance，把月度上限摊平，根治月初一天烧光。
  5. 合集写入 roundup_queue.jsonl 供覆盖扩容挖掘（不计口味证据）。
  6. 主机安全 _notify：容器内走 notifier，主机落 alert_queue.jsonl，由控制器 docker-exec 排空转发。
  7. 默认离线（不付费）；--fetch 才调用付费 actor，--apply 才写库；控制器用 --fetch --apply --guard。

实体锚定统一复用 entity_match（anchor_note 返回 (rid, reason)）；账单 API 为权威门。
用法：
  python3 review_apify_fill.py                       # 离线计划，不付费
  python3 review_apify_fill.py --fetch               # 真实抓取（不写库）
  python3 review_apify_fill.py --fetch --apply       # 抓取并写库
  python3 review_apify_fill.py --fetch --apply --guard  # 自治模式，输出 @@STATUS
"""
import argparse
import calendar as _calendar
import datetime
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR") or (HERE / "vendor" / "pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR") or HERE)
for p in (str(HERE), str(PIPE), str(HERE / "vendor" / "pipeline"), "/app/pipeline"):
    if p and p not in sys.path:
        sys.path.insert(0, p)

import requests  # noqa: E402
import common as C  # noqa: E402
import entity_match as EM  # noqa: E402


def _load_token():
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if t:
        return t
    fp = DATA / ".secrets" / "apify_token"
    if fp.exists():
        return fp.read_text(encoding="utf-8").strip()
    return ""


TOKEN = _load_token()
STATE_F = DATA / "apify_fill_state.json"
ROUNDUP_QUEUE = DATA / "roundup_queue.jsonl"
BIG_HOLD = DATA / "big_brand_hold.json"
ALERT_QUEUE = HERE / "alert_queue.jsonl"

PROVIDERS = {
    "opspilot": {
        "run": ("https://api.apify.com/v2/acts/opspilot.cc~xiaohongshu-keyword-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.10},
    "zenstudio": {
        "run": ("https://api.apify.com/v2/acts/zen-studio~rednote-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.17},
    "toolzerhub": {
        "run": ("https://api.apify.com/v2/acts/toolzerhub~rednote-xiaohongshu-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.021},
    "atomus": {
        "run": ("https://api.apify.com/v2/acts/atomus~xiaohongshu-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.17},
}
DEFAULT_PROVIDER = os.environ.get("APIFY_PROVIDER", "routed")
# 成本路由：atomus 按结果计费（0结果=$0）先探，不足再 opspilot；可用 APIFY_PROVIDER_CHAIN 覆盖。
_prov_chain = os.environ.get("APIFY_PROVIDER_CHAIN", "atomus,opspilot")
PROVIDER_CHAIN = [p.strip() for p in _prov_chain.split(",") if p.strip() in PROVIDERS] \
    or ["atomus", "opspilot"]

PER_NOTE_PAUSE = float(os.environ.get("APIFY_NOTE_PAUSE", "4.0"))
PER_RUN_FLOOR_USD = float(os.environ.get("APIFY_PER_RUN_FLOOR_USD", "0.15"))
ROUND_CAP_USD = float(os.environ.get("APIFY_ROUND_USD", "2.0"))
MAX_CHARGE_USD = float(os.environ.get("APIFY_MAX_CHARGE_USD", "0.30"))
MAX_SHOP_ATTEMPTS = int(os.environ.get("APIFY_MAX_SHOP_ATTEMPTS", "2"))
PREFLIGHT_CONFIRM = int(os.environ.get("APIFY_PREFLIGHT_CONFIRM", "2"))
CIRCUIT_COOLDOWN_0 = int(os.environ.get("APIFY_CIRCUIT_COOLDOWN_0", str(3 * 3600)))
CIRCUIT_COOLDOWN_MAX = int(os.environ.get("APIFY_CIRCUIT_COOLDOWN_MAX", str(24 * 3600)))
CREDIT_WAIT = int(os.environ.get("APIFY_CREDIT_WAIT", str(4 * 3600)))
DEFER_NAME = re.compile(r"私房|私厨|会所|俱乐部|会馆")


# ---------------------------------------------------------------- 账单（权威门）
def remaining_credit():
    if not TOKEN:
        return 0.0
    try:
        d = requests.get("https://api.apify.com/v2/users/me/usage/monthly",
                         params={"token": TOKEN}, timeout=30).json()["data"]
        used = float(d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0)
        # 权威硬上限优先取自定义 limits（REST /v2/users/me/limits 可调，如 $50），
        # 再回退 plan 基准（STARTER base，不含自定义提额）。
        cap = 0.0
        try:
            lj = requests.get("https://api.apify.com/v2/users/me/limits",
                              params={"token": TOKEN}, timeout=30).json()["data"]
            cap = float((lj.get("limits") or {}).get("maxMonthlyUsageUsd") or 0)
        except Exception:
            cap = 0.0
        if not cap:
            me = requests.get("https://api.apify.com/v2/users/me",
                              params={"token": TOKEN}, timeout=30).json()["data"]
            cap = float((me.get("plan") or {}).get("maxMonthlyUsageUsd") or 0)
        return max(0.0, cap - used)
    except Exception:
        return 0.0


def current_used():
    if not TOKEN:
        return 0.0
    try:
        d = requests.get("https://api.apify.com/v2/users/me/usage/monthly",
                         params={"token": TOKEN}, timeout=30).json()["data"]
        return float(d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0.0)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- 主机安全告警
def _notify(level, key, body, **kw):
    try:
        import notifier  # type: ignore
        getattr(notifier, level)(body, key=key, **kw)
        return True
    except Exception:
        try:
            with ALERT_QUEUE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"level": level, "key": key, "body": body,
                                    "ts": C.today()}, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return False


# ---------------------------------------------------------------- Apify 调用
class TokenBad(Exception):
    pass


def apify_search(provider, keyword, max_items=6, timeout=160):
    if not TOKEN:
        raise TokenBad("APIFY_TOKEN 未配置")
    if provider == "toolzerhub":
        body = {"query": keyword, "sort": "popular", "maxItems": max_items}
    elif provider == "atomus":
        body = {"searchType": "search", "keywords": [keyword],
                "maxItems": max_items, "sortType": "popularity_descending"}
    elif provider == "opspilot":
        # 正确字段 keyword（单数）。keywords 复数数组会被静默忽略、回退默认泛搜“美食推荐”。
        body = {"keyword": keyword}
    else:  # zenstudio
        body = {"keyword": keyword, "maxItems": max_items}
    endpoint = PROVIDERS[provider]["run"]
    run_params = {"token": TOKEN, "maxItems": max_items,
                  "maxTotalChargeUsd": MAX_CHARGE_USD}
    if provider == "opspilot":
        run_params["memory"] = 512
    r = requests.post(endpoint, params=run_params, json=body, timeout=timeout)
    if r.status_code == 401:
        raise TokenBad(r.text[:200])
    if r.status_code not in (200, 201):
        return None, f"http{r.status_code}:{r.text[:120]}"
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        return None, str(data["error"])[:160]
    if isinstance(data, list):
        errs = [x for x in data if isinstance(x, dict) and x.get("error_kind")]
        good = [x for x in data if not (isinstance(x, dict) and x.get("error_kind"))]
        if not good and errs:
            return None, f"actor:{str(errs[0].get('reason'))[:140]}"
        data = good
    return data, None


def normalize_note(provider, n):
    if provider == "opspilot":
        nid = n.get("noteId")
        url = n.get("noteUrl") or (
            f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
        return {"id": nid, "title": n.get("title") or "",
                "desc": n.get("description") or "", "url": url,
                "author": n.get("nickname") or "",
                "liked_count": n.get("likedCount"), "provider": provider}
    if provider == "zenstudio":
        nid = n.get("id")
        eng = n.get("engagement") if isinstance(n.get("engagement"), dict) else {}
        au = n.get("author") if isinstance(n.get("author"), dict) else {}
        return {"id": nid, "title": n.get("title") or "",
                "desc": n.get("desc") or "", "url": n.get("url") or "",
                "author": au.get("nickname") or "",
                "liked_count": eng.get("liked_count"), "provider": provider}
    nid = n.get("id")
    url = n.get("url") or (f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
    u = n.get("user")
    author = ""
    if isinstance(u, dict):
        author = u.get("nickname") or u.get("nickName") or ""
    author = author or n.get("author") or n.get("nickname") or ""
    return {"id": nid, "title": n.get("title") or "", "desc": n.get("desc") or "",
            "url": url, "author": author, "liked_count": n.get("liked_count"),
            "provider": provider}


def note_author(note):
    if note.get("author"):
        return note["author"]
    return note.get("nickname") or "小红书用户"


def is_brand_author(note, base_core):
    return bool(base_core) and base_core in C.cjk_norm(note_author(note))


# ---------------------------------------------------------------- 状态 / 周期
def _cycle_tag():
    d = datetime.date.today()
    return f"{d.year}-{d.month:02d}"


def load_state():
    st = {}
    if STATE_F.exists():
        try:
            st = json.loads(STATE_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            st = {}
    st.setdefault("billable_notes", 0)
    st.setdefault("billable_cost_usd", 0.0)
    st.setdefault("shops_done", [])
    st.setdefault("skipped", {})
    st.setdefault("last_run", "")
    st.setdefault("token_bad", False)
    st.setdefault("attempts", {})
    st.setdefault("deferred", [])
    st.setdefault("circuit", {})
    st.setdefault("last_credit_alert", "")
    st.setdefault("cycle", _cycle_tag())
    return st


def save_state(st):
    st["last_run"] = C.today()
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def reset_for_new_cycle(st):
    if st.get("cycle") != _cycle_tag():
        st["cycle"] = _cycle_tag()
        st["attempts"] = {}
        st["deferred"] = []
        st["circuit"] = {}


def worth_order():
    """gate brief（worth_fill.json，已按 P0→P1→P2 排序）-> {rid: (position, label)}。"""
    for p in (DATA / "worth_fill.json", HERE / "worth_fill.json"):
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            out = {}
            for i, x in enumerate(d):
                if isinstance(x, dict) and x.get("id") is not None:
                    out[x["id"]] = (i, x.get("label", "P9"))
            return out
    return None


# ---------------------------------------------------------------- 查询阶梯
def branch_hint(name):
    for p in re.findall(r"[（(]([^）)]+)[）)]", name):
        for m in EM.MALLS:
            if m in p:
                return m
        m = re.search(r"([一-龥]{2,6}[路街])", p)
        if m:
            return m.group(1)
    return ""


def first_dish(rec):
    sd = rec.get("signature_dishes")
    vals = []
    if isinstance(sd, list):
        vals = [str(x) for x in sd]
    elif isinstance(sd, str):
        vals = re.split(r"[、,，;/\n]", sd)
    for v in vals:
        v = v.strip(" ·.、,，")
        if 1 < len(v) <= 8:
            return v
    return ""


def keywords_for(rec):
    name = rec["name"]
    base = EM.strip_branch(name)
    hint = branch_hint(name)
    q1 = re.sub(r"\s+", " ", f"{base} {hint} 上海").strip()
    dish = first_dish(rec)
    mid = " ".join(x for x in (hint, dish or "测评", "堂食") if x)
    q2 = re.sub(r"\s+", " ", f"{base} {mid} 上海").strip()
    return q1, q2


# ---------------------------------------------------------------- 目标选择
# 连锁规模 -> opspilot 搜索级通道优先级（A/B 实测 2026-10-02）
# 独立/名字独特的店，品牌词能出单店食客帖（Tacolicious 9采信/4口味）；
# 大型/资本化多分店品牌（新荣记/遇外滩）品牌词甚至招牌菜词都被合集淹没、0采信，
# 不应在 opspilot 通道白烧——摘出记 big_brand_hold，后续走 sian 全文/评论路由。
CHAIN_TIER = {"独立店": 0, "小型连锁": 1}
BIG_CHAIN = {"大型连锁", "资本化连锁"}


def select_targets(idx, need, st):
    revs = C.fetch_all("reviews", "restaurant_id,trust_level,is_verified_diner")
    have = {}
    for r in revs:
        if r.get("is_verified_diner") and r.get("trust_level") in ("mid", "high"):
            have[r["restaurant_id"]] = have.get(r["restaurant_id"], 0) + 1
    info = {r["id"]: r for r in C.fetch_all(
        "restaurants",
        "id,is_chain_standardized,chain_type,price_avg,signature_dishes,status")}
    order = worth_order()
    allow = set(order) if order else None
    cap_ids = {int(rid) for rid, a in st.get("attempts", {}).items()
               if a.get("n", 0) >= MAX_SHOP_ATTEMPTS}
    deferred_ids = {d["id"] for d in st.get("deferred", [])}
    targets, big_hold = [], []
    for d in idx.RMD:
        rid = d["id"]
        r = info.get(rid)
        if not r or r.get("status") != "active":
            continue
        if r.get("is_chain_standardized") is True:
            continue
        if have.get(rid, 0) >= need:
            continue
        if allow is not None and rid not in allow:
            continue
        if rid in cap_ids or rid in deferred_ids:
            continue
        chain = r.get("chain_type") or "独立店"
        if chain in BIG_CHAIN:
            big_hold.append({"id": rid, "name": d["name"], "chain_type": chain,
                             "brief_label": order[rid][1] if order else "P9"})
            continue
        targets.append({"id": rid, "name": d["name"],
                        "tier": CHAIN_TIER.get(chain, 1),
                        "price_avg": C.to_int(r.get("price_avg")) or 0,
                        "signature_dishes": r.get("signature_dishes"),
                        "brief_pos": order[rid][0] if order else 10 ** 9,
                        "brief_label": order[rid][1] if order else "P9"})
    # 第一排序=gate brief 位置（P0 捍卫精选 → P1 榜单核实 → P2 苗头）；
    # 其余仅作并列兜底：独立/小型连锁、本地平价、有招牌菜(q2 可续)略优先。
    targets.sort(key=lambda x: (x["brief_pos"], x["tier"],
                               1 if DEFER_NAME.search(x["name"]) else 0,
                               0 if x["signature_dishes"] else 1,
                               x["price_avg"], x["id"]))
    if big_hold:
        BIG_HOLD.write_text(json.dumps(
            {"note": "大型/资本化多分店品牌，opspilot 搜索级0采信，留待 sian 全文/评论路由",
             "count": len(big_hold), "shops": big_hold},
            ensure_ascii=False, indent=2), encoding="utf-8")
    return targets


def accepted_note(idx, note, target_rid, rec_name):
    """返回 (status, payload, anchored, is_roundup)。payload=(body,score,raw)。"""
    rid, reason = idx.anchor_note(note, rec_name)
    if rid != target_rid:
        return reason or "未锚", None, False, reason == "合集"
    body = EM.clean_content(note.get("desc", ""))
    if len(body) < 8 or not C.quote_has_substance(body):
        return "无实物/软广模板", None, True, False
    if EM.is_question(body):
        return "疑问/互动", None, True, False
    score, raw = EM.taste_sent(body)
    if score is None:
        return "无口味信号", None, True, False
    return "accept", (body, score, raw), True, False


# ---------------------------------------------------------------- 合集捕获
def capture_roundups(flagged):
    """flagged: [(note, kw)]；合集写入 roundup_queue，url 去重。"""
    seen = set()
    if ROUNDUP_QUEUE.exists():
        for line in ROUNDUP_QUEUE.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line).get("url"))
            except Exception:
                pass
    n = 0
    with ROUNDUP_QUEUE.open("a", encoding="utf-8") as f:
        for note, kw in flagged:
            url = note.get("url")
            if not url or url in seen:
                continue
            content = (note.get("title", "") + "\n" + note.get("desc", "")).strip()
            f.write(json.dumps({"url": url, "content": content[:1500],
                                "source": "apify", "kw": kw,
                                "ts": C.today()}, ensure_ascii=False) + "\n")
            seen.add(url); n += 1
    return n


# ---------------------------------------------------------------- 熔断 / 日预算
def circuit_open_seconds(st):
    until = (st.get("circuit") or {}).get("cooldown_until")
    return max(int(until - time.time()), 0) if until else 0


def trip_circuit(st, reason):
    c = st.get("circuit") or {}
    level = c.get("level", 0) + 1
    cooldown = min(CIRCUIT_COOLDOWN_0 * (2 ** (level - 1)), CIRCUIT_COOLDOWN_MAX)
    st["circuit"] = {"open_at": int(time.time()), "level": level, "reason": reason,
                     "cooldown_until": int(time.time()) + cooldown}
    return cooldown


def clear_circuit(st):
    if st.get("circuit"):
        st["circuit"] = {}


def _days_left():
    today = datetime.date.today()
    last = _calendar.monthrange(today.year, today.month)[1]
    return max((datetime.date(today.year, today.month, last) - today).days, 0) + 1


def daily_allowance(rem):
    # 显式覆盖（滚动测试）：APIFY_DAILY_CAP=10 → 当天最多烧 $10（"$10 一轮"），
    # 烧到该额度睡到次日；剩余额度近 0 时 guard 先返 NO_CREDIT。
    _env_cap = os.environ.get("APIFY_DAILY_CAP", "").strip()
    if _env_cap:
        try:
            return max(float(_env_cap), 0.0)
        except ValueError:
            pass
    return max(rem, 0.0) / _days_left()


def _secs_to_tomorrow():
    now = datetime.datetime.now()
    tom = (now + datetime.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return max(int((tom - now).total_seconds()), 60)


# ---------------------------------------------------------------- 单店处理
def process_shop(rec, idx, st, args, gates):
    rid, name = rec["id"], rec["name"]
    q1, q2 = keywords_for(rec)
    att = st["attempts"].setdefault(str(rid), {"n": 0, "kws": [], "last": ""})
    base_core = C.cjk_norm(EM.strip_branch(name))
    got, blocked = 0, 0
    reason_ct = {}
    n_roundup, n_anchor = 0, 0
    flagged_roundups = []
    chain = PROVIDER_CHAIN if args.provider == "routed" else [args.provider]
    while att["n"] < MAX_SHOP_ATTEMPTS and got < args.need:
        kw = q1 if att["n"] == 0 else q2
        for prov in chain:
            rem = remaining_credit()
            if rem < PER_RUN_FLOOR_USD:
                att["last"] = "额度地板"
                return {"code": "NO_CREDIT", "got": got}
            used_today = current_used() - gates["day_start_used"]
            if used_today >= gates["daily"] or gates["daily"] < PER_RUN_FLOOR_USD:
                att["last"] = "日预算"
                return {"code": "DAILY_CAP", "got": got}
            if current_used() - gates["round_start"] >= ROUND_CAP_USD:
                att["last"] = "轮次上限"
                return {"code": "ROUND_CAP", "got": got}
            u0 = current_used()
            try:
                raw_notes, err = apify_search(prov, kw, max_items=6)
            except TokenBad as e:
                st["token_bad"] = True
                save_state(st)
                _notify("action", "apify_token_bad",
                        "Apify token 无效（401），账号无关回填暂停。请到 console.apify.com 确认账号/"
                        "重新生成 token 并更新凭据。", action_text="去处理", nudge_schedule=(6,))
                return {"code": "TOKEN_BAD", "got": got}
            du = max(0.0, round(current_used() - u0, 4))
            att["kws"].append(f"{kw}@{prov}")
            cbp = st.setdefault("cost_by_provider", {})
            cbp[prov] = round(cbp.get(prov, 0.0) + du, 4)
            cap = st.setdefault("calls_by_provider", {})
            cap[prov] = cap.get(prov, 0) + 1
            st["billable_notes"] += len(raw_notes) if raw_notes else 0
            st["billable_cost_usd"] = round(st.get("billable_cost_usd", 0.0) + du, 4)
            if err:
                att["last"] = err
                st["skipped"][str(rid)] = err
                continue
            for note in [normalize_note(prov, x) for x in raw_notes]:
                url = note.get("url")
                if url and url in gates["existing_urls"]:
                    continue
                if is_brand_author(note, base_core):
                    blocked += 1
                    continue
                status, payload, anchored, rp = accepted_note(idx, note, rid, name)
                if anchored:
                    n_anchor += 1
                if rp:
                    n_roundup += 1
                    flagged_roundups.append((note, kw))
                if status == "accept":
                    body, score, raw = payload
                    rev = {"restaurant_id": rid, "author_name": note_author(note)[:20],
                           "source_platform": "小红书", "source_url": url, "content": body,
                           "review_kind": "diner", "is_verified_diner": True,
                           "trust_level": "mid", "aspect_taste": score,
                           "aspect_json": {"via": f"apify-{prov}",
                                           "taste_raw": raw, "liked": note.get("liked_count")}}
                    if args.apply:
                        rr = C.req("POST", "/reviews", json=rev)
                        if rr.status_code in (200, 201):
                            got += 1
                            if url:
                                gates["existing_urls"].add(url)
                        else:
                            print("   insert fail", rr.status_code, rr.text[:120])
                    else:
                        got += 1
                else:
                    reason_ct[status] = reason_ct.get(status, 0) + 1
                    if status == "无实物/软广模板":
                        blocked += 1
            time.sleep(PER_NOTE_PAUSE)
            if got >= args.need:
                break
        att["n"] += 1
        if got >= args.need:
            break
    capture_roundups(flagged_roundups)
    if got >= args.need:
        if rid not in st["shops_done"]:
            st["shops_done"].append(rid)
        att["last"] = "达标"
        return {"code": "DONE", "got": got, "blocked": blocked}
    if n_roundup >= 5:
        why = "合集主导，无单店食客帖"
    elif n_anchor > 0:
        why = "有锚定但无可用口味信号"
    else:
        why = "搜索跑题/无公开食客帖"
    att["last"] = why
    st["deferred"] = [d for d in st["deferred"] if d["id"] != rid]
    st["deferred"].append({"id": rid, "name": name, "reason": why})
    pure_offtarget = (n_roundup < 5 and n_anchor == 0)
    return {"code": "DEFER", "got": got, "blocked": blocked,
            "reason_ct": reason_ct, "pure_offtarget": pure_offtarget, "why": why}


# ---------------------------------------------------------------- 离线计划
def offline_plan(idx, st, args):
    rem = remaining_credit()
    targets = select_targets(idx, args.need, st)
    print("=== 离线计划（不付费）===")
    print(f"剩余额度≈${rem:.3f}；本月剩余 {_days_left()} 天，日预算≈${daily_allowance(rem):.3f}")
    csecs = circuit_open_seconds(st)
    print(f"熔断：{'开启，冷却剩 %ds' % csecs if csecs else '无'}；attempts 店 {len(st['attempts'])}；"
          f"deferred {len(st['deferred'])}；shops_done {len(st['shops_done'])}")
    print(f"待补目标 {len(targets)}（显示 {min(len(targets), args.limit)}）：")
    for rec in targets[:args.limit]:
        q1, q2 = keywords_for(rec)
        a = st["attempts"].get(str(rec["id"]), {})
        print(f"  [{rec['id']}] {rec['name'][:28]} att={a.get('n',0)}")
        print(f"      q1: {q1}\n      q2: {q2}")


# ---------------------------------------------------------------- 主流程
def run(args):
    if os.environ.get("APIFY_DISABLED", ""):
        print("[已停用] APIFY_DISABLED 已设置；额度重置/充值后取消该变量。")
        return
    st = load_state()
    reset_for_new_cycle(st)
    idx = EM.get_index()

    if not args.fetch:
        offline_plan(idx, st, args)
        return

    rem = remaining_credit()
    if rem < PER_RUN_FLOOR_USD:
        if st.get("last_credit_alert") != C.today():
            _notify("action", "fill_credit",
                    f"Apify 本月额度仅剩 ${rem:.3f}（地板 ${PER_RUN_FLOOR_USD}），worth_fill 暂停。"
                    "到 console.apify.com/billing 充值；额度恢复/下月重置后本服务自动续跑。",
                    action_text="去充值", nudge_schedule=(9, 21))
            st["last_credit_alert"] = C.today()
            save_state(st)
        if args.guard:
            print(f"@@STATUS NO_CREDIT {CREDIT_WAIT} remaining=${rem:.3f}")
        else:
            print(f"额度不足（剩余 ${rem:.3f}），停止。")
        return

    csecs = circuit_open_seconds(st)
    if csecs > 0:
        if args.guard:
            print(f"@@STATUS CIRCUIT_WAIT {csecs} {st['circuit'].get('reason','')}")
        else:
            print(f"熔断冷却中，剩 {csecs}s。")
        return

    targets = select_targets(idx, args.need, st)
    if not targets:
        save_state(st)
        if args.guard:
            print("@@STATUS DONE 0 worth_fill 已全部达标")
        else:
            print("worth_fill 已全部达标。")
        return

    gates = {"day_start_used": current_used(), "daily": daily_allowance(rem),
             "round_start": current_used(),
             "existing_urls": set(x.get("source_url")
                                  for x in C.fetch_all("reviews", "source_url")
                                  if x.get("source_url"))}
    if args.provider == "routed":
        prov_desc = "routed(链:" + ">".join(PROVIDER_CHAIN) + ")"
    else:
        prov_desc = f"{args.provider}(${PROVIDERS[args.provider]['price_per_run']:.2f}/次)"
    print(f"待补 {len(targets)}；本轮处理 {min(len(targets),args.limit)}；"
          f"provider={prov_desc}；日预算≈${gates['daily']:.2f}")

    done_n, defer_n, applied, blocked_n = 0, 0, 0, 0
    preflight_n = 0
    for rec in targets[:args.limit]:
        res = process_shop(rec, idx, st, args, gates)
        code = res["code"]
        if code in ("NO_CREDIT", "TOKEN_BAD"):
            save_state(st)
            if args.guard:
                print(f"@@STATUS {code} {CREDIT_WAIT} {res}")
            return
        if code in ("DAILY_CAP", "ROUND_CAP"):
            save_state(st)
            wait = _secs_to_tomorrow() if code == "DAILY_CAP" else 1800
            if args.guard:
                print(f"@@STATUS {code} {wait}")
            return
        save_state(st)
        if code == "DONE":
            clear_circuit(st)
            done_n += 1
            applied += res["got"]
            blocked_n += res.get("blocked", 0)
            print(f"  [{rec['id']}] {rec['name'][:24]} ← 采信{res['got']}")
        else:
            defer_n += 1
            blocked_n += res.get("blocked", 0)
            if res.get("pure_offtarget"):
                preflight_n += 1
            print(f"  [{rec['id']}] {rec['name'][:24]} ← 0采信（{res['why']}）")

    # 熔断只在「整轮无一家达标 + 多家纯跑题(非合集)」时判定 actor 系统性失效；
    # 只要本轮有达标店即说明 actor 正常，冷门无帖店仅 defer、不全局停。
    if done_n == 0 and preflight_n >= PREFLIGHT_CONFIRM:
        cooldown = trip_circuit(st, "整轮纯跑题0锚定0达标")
        _notify("action", "fill_preflight",
                f"[PREFLIGHT 熔断] 本轮 0 达标、{preflight_n} 家纯跑题 0 锚定（非合集），"
                f"判定 actor 系统性失效，冷却 {cooldown//3600}h，以免继续烧钱。")
        save_state(st)
        if args.guard:
            print(f"@@STATUS CIRCUIT_WAIT {cooldown} preflight")
        return

    st["token_bad"] = False
    save_state(st)
    remain_targets = len(select_targets(idx, args.need, st))
    if args.guard:
        print(f"@@STATUS OK 30 done={done_n} deferred={defer_n} applied={applied} "
              f"blocked={blocked_n} remain_targets={remain_targets} "
              f"remain_credit=${remaining_credit():.2f}")
    else:
        print(f"本批：达标 {done_n}，deferred {defer_n}，采信 {applied}，拦截 {blocked_n}；"
              f"剩余目标 {remain_targets}，剩余额度 ${remaining_credit():.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--guard", action="store_true")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--need", type=int, default=2)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER,
                    choices=["routed"] + list(PROVIDERS))
    run(ap.parse_args())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_apify_fill.py — 账号无关的真实食客评价兜底回填（v3：统一实体匹配 + 熔断 + 硬 bound）。

v3 根修复（针对 Starter $19 被烧、"笔记20 采信0"）：
  1. 实体锚定统一复用 entity_match（品牌多形态 + 前缀/二元索引 + 分店消歧 + 证据化合集），
     不再用本脚本旧的"完整长店名子串"粗糙匹配（曾 78% 真实食客笔记被误判"正文无目标店"）。
  2. opspilot 输入字段修正为 keywords（复数数组）；旧 keyword（单数）必 http400。
  3. 每次运行带 maxTotalChargeUsd 硬上限 + memory=512，杜绝单次运行超收。
  4. 首店即 preflight：第一家"正常返回但 0 采信"即熔断本轮并告警，不为系统性错配持续烧钱。

成本口径（2026-10-01 真实账单）：Apify 按「每次运行启动 + 内存×时长」计费，非按条。
  余额门 / 轮次门一律用账单 API 真实值，不用内部估算。

用法（容器内，cd /app/cloud && . ./env.sh）：
  python3 review_apify_fill.py            # dry-run
  python3 review_apify_fill.py --apply    # 写入
  --limit N   本轮最多处理几家（默认 12）
  --need N    每店目标独立口味证据数（默认 2）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

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

PROVIDERS = {
    "opspilot": {
        "run": ("https://api.apify.com/v2/acts/opspilot.cc~xiaohongshu-keyword-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.0},
    "zenstudio": {
        "run": ("https://api.apify.com/v2/acts/zen-studio~rednote-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.0},
    "toolzerhub": {
        "run": ("https://api.apify.com/v2/acts/toolzerhub~rednote-xiaohongshu-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.10},
    "atomus": {
        "run": ("https://api.apify.com/v2/acts/atomus~xiaohongshu-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.17},
}
DEFAULT_PROVIDER = os.environ.get("APIFY_PROVIDER", "opspilot")

FREE_COST_CAP = float(os.environ.get("APIFY_FREE_COST_USD", "0.50"))
FREE_NOTE_CAP = int(os.environ.get("APIFY_FREE_NOTE_CAP", "100"))
PER_NOTE_PAUSE = float(os.environ.get("APIFY_NOTE_PAUSE", "4.0"))
MIN_REMAINING_USD = float(os.environ.get("APIFY_MIN_REMAINING_USD", "1.00"))
PER_RUN_FLOOR_USD = float(os.environ.get("APIFY_PER_RUN_FLOOR_USD", "0.15"))
ROUND_CAP_USD = float(os.environ.get("APIFY_ROUND_USD", "2.0"))
# 单次运行计费硬上限（Apify run option maxTotalChargeUsd），超过即中止该 run、不超收。
MAX_CHARGE_USD = float(os.environ.get("APIFY_MAX_CHARGE_USD", "0.30"))
# preflight：第一家正常返回但采信数 < 此值 → 熔断本轮（防系统性错配烧钱）。
PREFLIGHT_MIN = int(os.environ.get("APIFY_PREFLIGHT_MIN", "1"))


def remaining_credit():
    if not TOKEN:
        return 0.0
    try:
        me = requests.get("https://api.apify.com/v2/users/me",
                          params={"token": TOKEN}, timeout=30).json()["data"]
        cap = (me.get("plan") or {}).get("maxMonthlyUsageUsd") or 0
        d = requests.get("https://api.apify.com/v2/users/me/usage/monthly",
                         params={"token": TOKEN}, timeout=30).json()["data"]
        used = d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0
        return max(0.0, float(cap) - float(used))
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
        # 正确字段是 keywords（复数数组）；单数 keyword 必 http400 invalid-input。
        body = {"keywords": [keyword], "maxItems": max_items}
    else:  # zenstudio
        body = {"keyword": keyword, "maxItems": max_items}
    endpoint = PROVIDERS[provider]["run"]
    run_params = {"token": TOKEN,
                  "maxItems": max_items,
                  "maxTotalChargeUsd": MAX_CHARGE_USD}
    if provider == "opspilot":
        run_params["memory"] = 512   # 默认 4GB 太贵；关键词搜索 512MB 足够
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
                "liked_count": n.get("likedCount"),
                "timestamp": None, "provider": provider}
    if provider == "zenstudio":
        nid = n.get("id")
        eng = n.get("engagement") if isinstance(n.get("engagement"), dict) else {}
        au = n.get("author") if isinstance(n.get("author"), dict) else {}
        return {"id": nid, "title": n.get("title") or "",
                "desc": n.get("desc") or "", "url": n.get("url") or "",
                "author": au.get("nickname") or "",
                "liked_count": eng.get("liked_count"),
                "timestamp": n.get("timestamp"), "provider": provider}
    nid = n.get("id")
    url = n.get("url") or (f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
    u = n.get("user")
    author = ""
    if isinstance(u, dict):
        author = u.get("nickname") or u.get("nickName") or ""
    author = author or n.get("author") or n.get("nickname") or ""
    return {"id": nid, "title": n.get("title") or "", "desc": n.get("desc") or "",
            "url": url, "author": author, "liked_count": n.get("liked_count"),
            "timestamp": n.get("timestamp"), "provider": provider}


def note_author(note):
    if note.get("author"):
        return note["author"]
    u = note.get("user")
    if isinstance(u, dict):
        return u.get("nickname") or u.get("nickName") or ""
    return note.get("nickname") or "小红书用户"


def is_brand_author(note, base_core):
    if not base_core:
        return False
    return base_core in C.cjk_norm(note_author(note))


# ---------------------------------------------------------------- 状态 / 队列
def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"billable_notes": 0, "billable_cost_usd": 0.0, "shops_done": [],
            "skipped": {}, "last_run": "", "token_bad": False}


def save_state(st):
    st["last_run"] = C.today()
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def worth_ids():
    cands = [pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/home/ubuntu/food-apify-fill"))
             / "worth_fill.json",
             pathlib.Path(__file__).parent / "worth_fill.json"]
    for p in cands:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return {x["id"] for x in d if isinstance(x, dict) and x.get("id") is not None}
    return None


def select_targets(idx, need):
    revs = C.fetch_all("reviews", "restaurant_id,trust_level,is_verified_diner")
    have = {}
    for r in revs:
        if r.get("is_verified_diner") and r.get("trust_level") in ("mid", "high"):
            have[r["restaurant_id"]] = have.get(r["restaurant_id"], 0) + 1
    info = {r["id"]: r for r in C.fetch_all(
        "restaurants", "id,is_chain_standardized,price_avg")}
    allow = worth_ids()
    targets = []
    for d in idx.RMD:
        if d["status"] != "active":
            continue
        rid = d["id"]
        r = info.get(rid)
        if not r:
            continue
        if r.get("is_chain_standardized") is True:
            continue
        if have.get(rid, 0) >= need:
            continue
        if allow is not None and rid not in allow:
            continue
        targets.append({"id": rid, "name": d["name"],
                        "price_avg": C.to_int(r.get("price_avg")) or 0})
    targets.sort(key=lambda r: (-r["price_avg"], r["id"]))
    return targets


def branch_hint(name):
    """从括号分店名取 mall / XX路 短提示，让搜索更贴分店。"""
    for p in re.findall(r"[（(]([^）)]+)[）)]", name):
        for m in EM.MALLS:
            if m in p:
                return m
        m = re.search(r"([一-龥]{2,6}[路街])", p)
        if m:
            return m.group(1)
    return ""


def accepted_note(idx, note, target_rid, rec_name):
    """返回 (status, payload)。status: accept / official / blocked / <reason>。"""
    rid, reason = idx.anchor_note(note, rec_name)
    if rid != target_rid:
        return reason or "未锚", None
    body = EM.clean_content(note.get("desc", ""))
    if len(body) < 8 or not C.quote_has_substance(body):
        return "无实物/软广模板", None
    if EM.is_question(body):
        return "疑问/互动", None
    score, raw = EM.taste_sent(body)
    if score is None:
        return "无口味信号", None
    return "accept", (body, score, raw)


# ---------------------------------------------------------------- 主流程
def run(apply, limit, need, provider=DEFAULT_PROVIDER):
    if os.environ.get("APIFY_DISABLED", ""):
        print("[已停用] APIFY_DISABLED 已设置，Apify 采集暂停；额度重置/充值后取消该变量。")
        return
    if provider not in PROVIDERS:
        print(f"未知 provider {provider}；可选 {list(PROVIDERS)}")
        return
    if not TOKEN:
        print("APIFY_TOKEN 未配置；写入 deploy.env 或持久卷 .secrets/apify_token 后再跑。")
        return

    st = load_state()
    idx = EM.get_index()
    targets = select_targets(idx, need)
    round_start_used = current_used()
    print(f"缺<{need}条真实口味证据的 active 店：{len(targets)}；本轮处理 {limit} 家；"
          f"provider={provider}(${PROVIDERS[provider]['price_per_run']:.2f}/次)")
    print(f"内部累计 ${st.get('billable_cost_usd',0):.3f}/{FREE_COST_CAP}；"
          f"笔记 {st['billable_notes']}/{FREE_NOTE_CAP}")

    existing_urls = set(
        x.get("source_url") for x in C.fetch_all("reviews", "source_url")
        if x.get("source_url"))

    batch = targets[:limit]
    written, blocked, empty = 0, 0, 0
    preflight_done = False
    for i, rest in enumerate(batch):
        rid, name = rest["id"], rest["name"]
        base = EM.strip_branch(name)
        base_core = C.cjk_norm(base)
        hint = branch_hint(name)
        keyword = f"{base} {hint} 上海".replace("  上海", " 上海")
        rem = remaining_credit()
        if rem < PER_RUN_FLOOR_USD:
            print(f"[额度门] 剩余 ${rem:.3f} < 地板 ${PER_RUN_FLOOR_USD:.2f}，本轮停止；"
                  "充值或额度重置后常驻服务自动续跑。")
            break
        if current_used() - round_start_used >= ROUND_CAP_USD:
            print(f"[轮次门] 本轮真实花费达 ${ROUND_CAP_USD:.2f}，暂停。")
            break
        try:
            raw_notes, err = apify_search(provider, keyword, max_items=6)
        except TokenBad as e:
            st["token_bad"] = True
            save_state(st)
            print(f"[TOKEN-BAD] {e}")
            _alert_token()
            return
        if err:
            print(f"  [skip] {name}: {err}")
            st["skipped"][str(rid)] = err
            continue
        if raw_notes is None:
            continue
        if PROVIDERS[provider]["price_per_run"] > 0:
            st["billable_notes"] += len(raw_notes)
            st["billable_cost_usd"] = round(
                st.get("billable_cost_usd", 0.0)
                + PROVIDERS[provider]["price_per_run"], 4)
        notes = [normalize_note(provider, x) for x in raw_notes]
        got = 0
        reason_ct = {}
        for note in notes:
            url = note.get("url")
            if url and url in existing_urls:
                continue
            if is_brand_author(note, base_core):
                blocked += 1
                continue
            status, payload = accepted_note(idx, note, rid, name)
            if status == "accept":
                body, score, raw = payload
                rev = {"restaurant_id": rid,
                       "author_name": note_author(note)[:20],
                       "source_platform": "小红书", "source_url": url, "content": body,
                       "review_kind": "diner", "is_verified_diner": True,
                       "trust_level": "mid", "aspect_taste": score,
                       "aspect_json": {"via": f"apify-{provider}",
                                       "taste_raw": raw,
                                       "liked": note.get("liked_count")}}
                if apply:
                    rr = C.req("POST", "/reviews", json=rev)
                    if rr.status_code in (200, 201):
                        got += 1
                        if url:
                            existing_urls.add(url)
                    else:
                        print("   insert fail", rr.status_code, rr.text[:140])
                else:
                    got += 1
            else:
                reason_ct[status] = reason_ct.get(status, 0) + 1
                if status == "无实物/软广模板":
                    blocked += 1
        if got:
            written += got
            if rid not in st["shops_done"]:
                st["shops_done"].append(rid)
        else:
            empty += 1
        print(f"  [{rid}] {name[:22]} ← 笔记{len(notes)} 采信{got} {reason_ct if reason_ct else ''}")

        # preflight 熔断：第一家“正常跑完但 0 采信”→ 系统性错配/失效，停止本轮并告警。
        if not preflight_done:
            preflight_done = True
            if got < PREFLIGHT_MIN:
                print(f"[PREFLIGHT 熔断] 首店正常返回但采信 {got} < {PREFLIGHT_MIN}，"
                      "判定 actor/查询系统性失效，本轮停止以免继续烧钱；已告警。")
                _alert_preflight(provider, name, reason_ct)
                break
        if current_used() - round_start_used >= ROUND_CAP_USD:
            print(f"[轮次门] 本轮真实花费达 ${ROUND_CAP_USD:.2f}，暂停。")
            break
        time.sleep(PER_NOTE_PAUSE)

    st["token_bad"] = False
    save_state(st)
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n[{mode}] 采信评论 {written} | 软广/无实物拦截 {blocked} | 0证据店 {empty}")
    print(f"内部累计 ${st.get('billable_cost_usd',0):.3f}/{FREE_COST_CAP}；"
          f"笔记 {st['billable_notes']}/{FREE_NOTE_CAP}")


def _alert_token():
    try:
        import notifier
        notifier.action(
            "Apify token 无效（401），账号无关回填暂停。请到 console.apify.com 确认账号/"
            "重新生成 token 并更新 deploy.env。",
            key="apify_token_bad", action_text="去处理", nudge_schedule="6h")
    except Exception as e:
        print("notifier fail:", repr(e)[:100])


def _alert_preflight(provider, name, reason_ct):
    try:
        import notifier
        notifier.warn(
            f"Apify preflight 熔断：首店「{name}」正常返回但 0 采信（{reason_ct}）。"
            f"provider={provider} 可能已失效或相关度异常，本轮未继续烧钱；请人工确认或换 actor。",
            key="apify_preflight", cooldown="6h")
    except Exception as e:
        print("notifier fail:", repr(e)[:100])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--need", type=int, default=2)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER, choices=list(PROVIDERS))
    a = ap.parse_args()
    run(a.apply, a.limit, a.need, a.provider)

#!/usr/bin/env python3
# serp_producer.py — 模块B·容器内全自动 SERP producer
# 引擎：360(www.so.com) 主力；sogou 第二；bing 加引号备用。验证码/拦截退避切引擎。
# 模式：--full 全量；--incremental 增量。账本 /app/data/post_record/scan_ledger.json。
# 抽取交 findings_extractor.validate()；findings 落 findings.jsonl 后由 post_audit --apply 入库。
# 红线：只写 chain_type/central_kitchen/premade_risk/investor_info/price_avg/food_safety。
import argparse, json, pathlib, os, re, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "/app/pipeline")
import common as C

sys.path.insert(0, "/app/cloud")
import findings_extractor as FX

LEDGER = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data")) / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
SCAN_LEDGER = LEDGER / "scan_ledger.json"

UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
]


def _load_proxy():
    """SERP 默认【直连】：住宅代理（account_b 广州）经实测对 360/搜狗/bing 等搜索引擎
    全超时（见 HANDOFF 已验证死路），每次 12s 超时才回落直连、严重拖慢采集。
    仅当显式设置 SERP_PROXY=1 时，才读 /app/data/account_proxies.json 走代理。
    （account_proxies 仅供小红书浏览器账号使用，与 SERP 无关。）"""
    if os.environ.get("SERP_PROXY", "0").strip() not in ("1", "true", "True"):
        return None
    import json
    p = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data")) / "account_proxies.json"
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
        v = m.get("account_b") or m.get("account_a")
        if isinstance(v, dict):
            url = v.get("http") or v.get("https") or v.get("url")
            if url:
                return {"http": url, "https": url}
        if isinstance(v, str):
            return {"http": v, "https": v}
    except Exception:
        pass
    return None


PROXIES = _load_proxy()
print(f"[serp] proxy={'on' if PROXIES else 'off'}", file=sys.stderr)

# 全局出站引擎并发上限：并发取证（多品牌 × 每品牌多查询）会瞬时打出大量请求、触发搜索
# 引擎限流/验证码；用信号量把同时在飞的引擎 HTTP 调用压到安全范围（env SERP_OUTBOUND 可调）。
_OUTBOUND = threading.BoundedSemaphore(max(1, int(os.environ.get("SERP_OUTBOUND", "6"))))


def _get(url, timeout=12):
    import requests
    kw = {"headers": {"User-Agent": random.choice(UAS),
                      "Accept-Language": "zh-CN,zh;q=0.9"},
          "timeout": timeout, "allow_redirects": True}
    if PROXIES:
        try:
            return requests.get(url, proxies=PROXIES, **kw)
        except Exception:
            pass  # 代理失败回落直连
    return requests.get(url, **kw)


def search_360(q):
    import requests
    from bs4 import BeautifulSoup
    try:
        r = _get("https://www.so.com/s?q=" + requests.utils.quote(q))
        if r.status_code != 200 or len(r.text) < 5000:
            return None, f"360 http {r.status_code}"
        s = BeautifulSoup(r.text, "html.parser")
        items = s.select("li.res-list")
        out = []
        for it in items:
            a = it.find("a")
            if not a: continue
            href = a.get("href", "")
            txt = it.get_text(" ", strip=True)
            # follow so.com redirect to get real target URL
            real = href
            try:
                rr = requests.head(href, headers={"User-Agent": random.choice(UAS)},
                                   timeout=5, allow_redirects=True)
                real = rr.url
            except Exception:
                pass
            host = real.split("://", 1)[-1].split("/", 1)[0]
            if real.startswith("http") and txt:
                out.append({"source_url": real, "source_title": txt[:120],
                            "snippet": txt[:400], "source_host": host})
        return out[:8], None
    except Exception as e:
        return None, f"360 err {type(e).__name__}"


def search_sogou(q):
    import requests
    from bs4 import BeautifulSoup
    try:
        r = _get("https://www.sogou.com/web?query=" + requests.utils.quote(q))
        if r.status_code != 200:
            return None, f"sogou http {r.status_code}"
        s = BeautifulSoup(r.text, "html.parser")
        items = s.select("div.vrwrap") or s.select("div.rb")
        out = []
        for it in items:
            a = it.find("a")
            if not a: continue
            href = a.get("href", "")
            txt = it.get_text(" ", strip=True)
            out.append({"source_url": href if href.startswith("http") else "https://www.sogou.com" + href,
                        "source_title": txt[:120], "snippet": txt[:400], "source_host": "sogou.com"})
        return out[:8], None
    except Exception as e:
        return None, f"sogou err {type(e).__name__}"


def search_bing(q):
    import requests
    from bs4 import BeautifulSoup
    try:
        url = ("https://www.bing.com/search?q=" + requests.utils.quote(q)
               + "&setlang=zh-CN&cc=CN&ensearch=0")
        r = _get(url)
        if r.status_code != 200:
            return None, f"bing http {r.status_code}"
        s = BeautifulSoup(r.text, "html.parser")
        out = []
        for it in s.select("li.b_algo"):
            a = it.select_one("h2 a")
            if not a:
                continue
            href = a.get("href", "")
            if not href.startswith("http"):
                continue
            title = a.get_text(" ", strip=True)
            cap = it.select_one(".b_caption p") or it.select_one("p")
            snippet = cap.get_text(" ", strip=True) if cap else title
            host = href.split("://", 1)[-1].split("/", 1)[0]
            out.append({"source_url": href, "source_title": title[:120],
                        "snippet": snippet[:400], "source_host": host})
        return out[:8], None
    except Exception as e:
        return None, f"bing err {type(e).__name__}"


def search_baidu(q):
    import requests
    from bs4 import BeautifulSoup
    try:
        r = _get("https://www.baidu.com/s?wd=" + requests.utils.quote(q))
        if r.status_code != 200 or len(r.text) < 5000:
            return None, f"baidu http {r.status_code}"
        if _is_blocked(r.url, r.text):
            return None, "baidu blocked"
        s = BeautifulSoup(r.text, "html.parser")
        out, seen = [], set()
        for h3 in s.select("h3"):
            a = h3.find("a")
            if not a:
                continue
            href = a.get("href", "")
            if not href.startswith("http"):
                continue
            box = a
            for _ in range(5):
                box = box.parent
                if box is not None and box.name == "div" and "c-container" in (box.get("class") or []):
                    break
            txt = (box.get_text(" ", strip=True) if box is not None else a.get_text(" ", strip=True))
            real = href
            try:
                rr = requests.head(href, headers={"User-Agent": random.choice(UAS)},
                                   timeout=5, allow_redirects=True)
                real = rr.url
            except Exception:
                pass
            if any(x in real for x in ("image.baidu", "tieba.baidu", "baike.baidu",
                                       "video.baidu", "wenku.baidu", "pan.baidu",
                                       "pic.baidu", "haokan.baidu")):
                continue
            if "百度图片" in txt:
                continue
            host = real.split("://", 1)[-1].split("/", 1)[0]
            if host in seen:
                continue
            seen.add(host)
            out.append({"source_url": real, "source_title": txt[:120],
                        "snippet": txt[:400], "source_host": host})
        return out[:8], None
    except Exception as e:
        return None, f"baidu err {type(e).__name__}"


def search_ddg(q):
    import requests
    from bs4 import BeautifulSoup
    import urllib.parse as up
    try:
        r = _get("https://html.duckduckgo.com/html/?q=" + requests.utils.quote(q))
        if r.status_code != 200:
            return None, f"ddg http {r.status_code}"
        s = BeautifulSoup(r.text, "html.parser")
        out = []
        for it in s.select("div.result"):
            a = it.select_one("a.result__a")
            if not a:
                continue
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            if m:
                href = up.unquote(m.group(1))
            if not href.startswith("http"):
                continue
            sn = it.select_one(".result__snippet")
            title = a.get_text(" ", strip=True)
            snippet = sn.get_text(" ", strip=True) if sn else title
            host = href.split("://", 1)[-1].split("/", 1)[0]
            out.append({"source_url": href, "source_title": title[:120],
                        "snippet": snippet[:400], "source_host": host})
        return out[:8], None
    except Exception as e:
        return None, f"ddg err {type(e).__name__}"


SEARX_URL = os.environ.get("SEARX_URL", "http://searxng:8080")


def search_searxng(q):
    """自建 SearXNG 元搜索：服务端聚合 bing/mojeek/startpage/yandex 等，返回去重 JSON。"""
    import requests
    for attempt in range(2):
        try:
            r = requests.get(SEARX_URL + "/search",
                             params={"q": q, "format": "json", "safesearch": 0},
                             timeout=12)
            if r.status_code != 200:
                if attempt == 0:
                    time.sleep(2)
                    continue
                return [], f"searxng http {r.status_code}"
            d = r.json()
            out = []
            for x in d.get("results", []):
                pu = x.get("parsed_url") or []
                host = pu[1] if len(pu) > 1 else ""
                out.append({
                    "source_url": x.get("url", ""),
                    "source_title": (x.get("title") or "").strip(),
                    "source_host": host,
                    "snippet": (x.get("content") or "").strip()})
            if out or attempt == 1:
                return out, ("searxng" if out else "empty")
            time.sleep(2)
        except Exception as e:
            if attempt == 1:
                return [], f"searxng {type(e).__name__}"
            time.sleep(2)
    return [], "searxng empty"


ENGINES = [("searxng", search_searxng), ("ddg", search_ddg), ("baidu", search_baidu),
           ("sogou", search_sogou), ("360", search_360), ("bing", search_bing)]
# 首选固定引擎（始终先试），其余按计数器轮换作为回退
PINNED = ["searxng"]
BLOCK_MARKERS = ["qcaptcha.so.com", "antispider", "captcha", "verify", "安全验证", "百度安全验证"]


def _is_blocked(url, html):
    return any(m in (url or "") for m in BLOCK_MARKERS) or any(m in (html or "")[:3000] for m in BLOCK_MARKERS)


def _qterms(q):
    """查询的显著词：CJK 整段+二元组，拉丁整词。用于相关性过滤首页垃圾。"""
    terms = set()
    for raw in re.split(r"\s+", q):
        raw = raw.strip('"\'')
        if not raw:
            continue
        if re.fullmatch(r"[A-Za-z0-9.&+\-]+", raw):
            if len(raw) >= 3:
                terms.add(raw.lower())
            continue
        for run in re.findall(r"[\u4e00-\u9fa5]+", raw):
            if len(run) >= 2:
                terms.add(run)
            for i in range(len(run) - 1):
                terms.add(run[i:i + 2])
    return terms


def _rel(terms, doc):
    blob = (doc.get("source_title", "") + " " + doc.get("snippet", "") + " " + doc.get("source_url", ""))
    blob_l = blob.lower()
    return sum(1 for t in terms if t in (blob_l if t.isascii() else blob))


_ROT = {"i": 0}


def _hard_call(fn, q, deadline):
    """独立于 HTTP 库内部超时的硬墙钟：守护线程跑一次引擎，到点未返回即强弃，
    杜绝 SearXNG/上游挂起导致的整轮卡死。"""
    box = {}

    def work():
        with _OUTBOUND:
            try:
                box["r"] = fn(q)
            except Exception as e:
                box["r"] = [], f"err {type(e).__name__}"

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(deadline)
    if th.is_alive():
        return [], "hard_deadline"
    return box.get("r", ([], "nores"))


def search_with_failover(q, want=8, time_cap=18, max_fallback=1):
    terms = _qterms(q)
    fallback = [e for e in ENGINES if e[0] not in PINNED]
    k = _ROT["i"] % len(fallback)
    _ROT["i"] += 1
    pinned = [e for e in ENGINES if e[0] in PINNED]
    order = pinned + fallback[k:] + fallback[:k]
    best = None
    t0 = time.time()
    fb_tried = 0
    for name, fn in order:
        if name not in PINNED:
            if fb_tried >= max_fallback:
                break
            fb_tried += 1
        if time.time() - t0 > time_cap:
            break
        res, err = _hard_call(fn, q, min(14, max(4, time_cap - (time.time() - t0))))
        if res:
            kept = [d for d in res if _rel(terms, d) >= 1]
            kept.sort(key=lambda d: -_rel(terms, d))
            if kept:
                score = sum(_rel(terms, d) for d in kept)
                if best is None or score > best[0]:
                    best = (score, name, kept[:want])
                if score >= 6:
                    break
        time.sleep(0.6)
    if best:
        return best[2], best[1]
    return [], "all_blocked"


# 简单 claim 抽取（确定性关键词规则，非 LLM）
# 目的：把 SERP snippets 转成 candidate claims 喂给 findings_extractor 硬门槛。
RULES = [
    ("chain_type", "小型连锁",
     [r"(\d+)\s*家门店", r"连锁", r"分店", r"多家门店"]),
    ("premade_risk", "高",
     [r"预制菜", r"料理包", r"中央厨房"]),
    ("central_kitchen", "确认",
     [r"中央厨房"]),
    ("food_safety", "问题",
     [r"食安", r"拉肚子", r"卫生问题"]),
]


def extract_claims(name, results):
    claims = []
    for doc in results:
        snip = (doc.get("snippet") or "") + " " + (doc.get("source_title") or "")
        for field, val, pats in RULES:
            for p in pats:
                if re.search(p, snip):
                    claims.append({
                        "field": field, "value": val,
                        "claim_text": snip[:160],
                        "confidence": 0.85,
                        "source_url": doc["source_url"],
                        "source_title": doc.get("source_title", ""),
                        "source_host": doc.get("source_host", ""),
                    })
                    break
        # 价格：人均 N 元
        m = re.search(r"人均\s*(\d{2,4})\s*元", snip)
        if m:
            claims.append({
                "field": "price_avg", "value": float(m.group(1)),
                "claim_text": snip[:160], "confidence": 0.8,
                "source_url": doc["source_url"],
                "source_title": doc.get("source_title", ""),
                "source_host": doc.get("source_host", ""),
            })
    return claims


def scan_one(restaurant, do_apply=False):
    rid = restaurant["id"]; name = restaurant["name"]
    q1 = f"{name} 上海 连锁 加盟 分店 预制菜 料理包 中央厨房"
    q2 = f"{name} 人均 价格 老板 集团 投资方"
    results = []
    used = []
    for q in (q1, q2):
        res, engine = search_with_failover(q)
        used.append(engine)
        results.extend(res)
        time.sleep(random.uniform(3.0, 5.0))
    claims = extract_claims(name, results)
    payload = {"restaurant_id": rid, "name": name, "claims": claims}
    kept = FX.validate(payload, apply=do_apply)
    return rid, len(results), used, kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    res = C.fetch_all("/restaurants", "id,name,status,data_updated_at", order_col="id")
    act = [r for r in res if r.get("status") == "active"]
    ledger = json.loads(SCAN_LEDGER.read_text(encoding="utf-8")) if SCAN_LEDGER.exists() else {}
    if a.full:
        todo = act
    elif a.incremental:
        last = ledger.get("last_full_date", "")
        todo = [r for r in act
                if str(r.get("data_updated_at") or "")[:10] >= last
                or str(r["id"]) not in ledger.get("rids", {})]
    else:
        todo = act[:30]  # dry-run 默认 30
    if a.limit:
        todo = todo[: a.limit]

    print(f"[producer] mode={'full' if a.full else 'inc' if a.incremental else 'dry30'} "
          f"todo={len(todo)} apply={a.apply}")
    total_kept = 0; engine_stats = {}
    findings_path = LEDGER / "findings.jsonl"
    n_before = (sum(1 for _ in findings_path.open(encoding="utf-8"))
                if findings_path.exists() else 0)

    def save_ledger():
        # 增量落盘：中断/超时也不丢已扫进度
        SCAN_LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    with ThreadPoolExecutor(max_workers=1) as ex:
        futs = {ex.submit(scan_one, r, a.apply): r for r in todo}
        for i, fut in enumerate(as_completed(futs)):
            rid, nres, used, kept = fut.result()
            for e in used:
                engine_stats[e] = engine_stats.get(e, 0) + 1
            total_kept += len(kept)
            # checkpoint
            ledger.setdefault("rids", {})[str(rid)] = {
                "date": time.strftime("%Y-%m-%d"), "n_results": nres,
                "n_kept": len(kept)}
            if (i + 1) % 10 == 0:
                print(f"  progress {i+1}/{len(todo)} kept_so_far={total_kept}")
                save_ledger()
    if a.full:
        ledger["last_full_date"] = time.strftime("%Y-%m-%d")
    save_ledger()
    print(f"[producer] done. total_kept={total_kept} engine_stats={engine_stats}")

    if a.apply and total_kept > 0:
        # 只把【本轮新增】findings 经唯一入库门 post_audit 写库，避免每批重 PATCH 全量
        all_lines = findings_path.read_text(encoding="utf-8").splitlines()
        new_lines = all_lines[n_before:]
        new_path = LEDGER / f"findings_new_{time.strftime('%Y-%m-%d_%H%M')}.jsonl"
        new_path.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"[producer] new findings={len(new_lines)} -> {new_path}")
        sys.path.insert(0, "/app/cloud")
        import post_audit as PA
        PA.apply_findings(str(new_path), apply=True)
    elif a.apply:
        print("[producer] no kept findings; post_audit skipped")


if __name__ == "__main__":
    main()

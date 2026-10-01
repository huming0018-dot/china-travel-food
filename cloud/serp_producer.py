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
    """从 /app/data/account_proxies.json 读 account_b 的代理（广州）。"""
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
    # 加引号消歧
    qq = f'"{q.split()[0]}" ' + " ".join(q.split()[1:])
    try:
        r = _get("https://cn.bing.com/search?q=" + requests.utils.quote(qq))
        if r.status_code != 200:
            return None, f"bing http {r.status_code}"
        s = BeautifulSoup(r.text, "html.parser")
        items = s.select("li.b_algo")
        out = []
        for it in items:
            a = it.find("a")
            if not a: continue
            txt = it.get_text(" ", strip=True)
            out.append({"source_url": a.get("href", ""), "source_title": txt[:120],
                        "snippet": txt[:400], "source_host": "bing.com"})
        return out[:8], None
    except Exception as e:
        return None, f"bing err {type(e).__name__}"


ENGINES = [("360", search_360), ("sogou", search_sogou), ("bing", search_bing)]
BLOCK_MARKERS = ["qcaptcha.so.com", "antispider", "captcha", "verify", "安全验证"]


def _is_blocked(url, html):
    return any(m in (url or "") for m in BLOCK_MARKERS) or any(m in (html or "")[:3000] for m in BLOCK_MARKERS)


def search_with_failover(q):
    for name, fn in ENGINES:
        res, err = fn(q)
        if res:
            return res, name
        time.sleep(3)
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


def scan_one(restaurant):
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
    kept = FX.validate(payload, apply=False)
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
          f"todo={len(todo)}")
    total_kept = 0; engine_stats = {}
    with ThreadPoolExecutor(max_workers=1) as ex:
        futs = {ex.submit(scan_one, r): r for r in todo}
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
    if a.full:
        ledger["last_full_date"] = time.strftime("%Y-%m-%d")
    SCAN_LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[producer] done. total_kept={total_kept} engine_stats={engine_stats}")


if __name__ == "__main__":
    main()

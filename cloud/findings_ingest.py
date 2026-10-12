#!/usr/bin/env python3
# findings_ingest.py — 模块B·findings 归一/校验/落盘器
# 输入：agent 经 general_search 拿到的原始结果（JSON 数组，见 --sample 字段约定）
# 输出：追加到 /app/data/post_record/findings.jsonl，字段口径与 post_audit.apply_findings 完全对齐：
#   {restaurant_id, name, field, value, confidence, source_url, source_title, reason,
#    search_date, captured_at}
# 硬规则：
#   - 必须 source_url 以 http 开头，否则丢弃；
#   - field 必须在 post_audit.ALLOWED 内；
#   - value 必须落在 field 的枚举内（investor_info/price_avg 例外）；
#   - confidence < 0.8 不进 post_audit（标记 dropped_low_conf，不写 findings）；
#   - 可信源分级白名单（NOISY 先判硬杀，再判 TRUSTED 放行）；
#   - 硬负面（央厨确认/预制高/食安问题）必须命中官方监管源，或同一 rid+field 有
#     ≥2 个相互独立的可信域名互证，否则丢弃（单篇市场化媒体不足以下硬结论）；
#   - 按 restaurant_id+field+source_url 去重；
#   - 默认 dry-run 打印不写；--apply 才 append。
import argparse, json, pathlib, os, sys, time
from urllib.parse import urlparse

LEDGER = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data")) / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
FINDINGS = LEDGER / "findings.jsonl"

# 与 cloud/post_audit.py ALLOWED 保持一致
ALLOWED = {
    "chain_type": {"独立店", "小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"无", "疑似", "确认"},
    "premade_risk": {"无", "低", "疑似", "高"},
    "investor_info": None,
    "price_avg": None,
    "food_safety": {"无", "疑似", "问题"},
}

# 明显营销/SEO/UGC 聚合/招聘/加盟/OTA —— 一律不支撑 chain/price/央厨/食安 等硬事实。
# 先于 TRUSTED 判定（命中即杀），避免其标题里夹带 "official/36kr" 等词蒙混。
NOISY = [
    "sohu.com/a", "163.com/dy", "baijiahao", "zhihu.com/question",
    "xiaohongshu.com/search", "xiaohongshu.com/explore",
    "toutiao.com/group", "m.toutiao.com", "douyin.com", "iesdouyin",
    "ctrip", "jobui", "jiameng", "zhipin", "shuidi.cn",
    "china.com/", "jianlimo", "1637.com", "21food",
]

# 可信源分级白名单（域名片段，小写子串匹配）。
TRUSTED = [
    # —— 官方榜单 / 平台 / 点评 / 官网 ——
    "meituan.com", "dianping.com", "michelin.", "blackpearl", "timeout",
    "smartshanghai", "official", "weixin", "mp.weixin",
    # —— 政府 / 监管 / 司法（商务部特许经营备案、市场监管、地方政府站）——
    ".gov.cn", ".gov.",
    # —— 工商注册 / 知识产权档（注册主体、分支机构、商标、对外投资）——
    "qcc.com", "qixin.com", "tianyancha.com", "aiqicha.com",
    # —— 通讯社 / 央媒 / 权威媒体 ——
    "news.cn", "xinhuanet", "xinhua", "people.com", "chinanews.com", "gmw.cn",
    "cnr.cn", "jjckb.cn", "ce.cn", "zgswcn.com", "bjd.com.cn", "bjnews.com.cn",
    "xinmin.cn", "xinminweekly.com.cn", "yunnan.cn", "tmtpost.com",
    # —— 财经 / 市场化可信媒体 ——
    "thepaper", "jiemian", "36kr", "yicai", "stcn",
]

# 官方/监管/通讯社源：硬负面命中其一时，单源即可成立（监管通报/政府公示本身即权威）。
OFFICIAL = [
    ".gov.cn", ".gov.", "news.cn", "xinhuanet", "xinhua", "people.com",
    "chinanews.com", "gmw.cn", "cnr.cn", "jjckb.cn", "ce.cn", "samr",
]

# 硬负面取值：必须官方源 或 ≥2 独立可信域名互证。
HARD_NEG = {("central_kitchen", "确认"), ("premade_risk", "高"), ("food_safety", "问题")}


def _domain(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else (h[2:] if h.startswith("m.") else h)


def is_trusted(url: str, title: str) -> bool:
    u = (url or "").lower(); t = (title or "").lower()
    if any(n in u for n in NOISY):
        return False
    return any(k in u or k in t for k in TRUSTED)


def is_official(url: str) -> bool:
    u = (url or "").lower()
    return any(k in u for k in OFFICIAL)


def norm(rows, apply=False):
    today = time.strftime("%Y-%m-%d")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    # 已落盘 findings：用于去重 + 硬负面的互证域名计数。
    seen = set()
    evidence = {}   # (rid, field) -> set(domains)；含已落盘可信源
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            f = json.loads(l)
            seen.add((f.get("restaurant_id"), f.get("field"), f.get("source_url")))
            if is_trusted(f.get("source_url", ""), ""):
                evidence.setdefault((f.get("restaurant_id"), f.get("field")), set()).add(
                    _domain(f.get("source_url", "")))

    # 第一遍：基础硬过滤，累计本批可信域名。
    staged = []
    dropped = []
    for r in rows:
        rid = r.get("restaurant_id")
        field = r.get("field")
        val = r.get("value")
        url = (r.get("source_url") or "").strip()
        title = r.get("source_title") or ""
        conf = float(r.get("confidence", 0))
        if not rid or field not in ALLOWED:
            dropped.append((rid, field, "bad_field")); continue
        if not url.startswith("http"):
            dropped.append((rid, field, "no_url")); continue
        enum = ALLOWED[field]
        if enum and val not in enum:
            dropped.append((rid, field, f"bad_enum:{val}")); continue
        if field == "price_avg":
            try:
                val = float(val)
            except Exception:
                dropped.append((rid, field, "bad_price")); continue
        if not is_trusted(url, title):
            dropped.append((rid, field, "noisy_source")); continue
        if conf < 0.8:
            dropped.append((rid, field, "low_conf")); continue
        key = (rid, field, url)
        if key in seen:
            dropped.append((rid, field, "dup")); continue
        staged.append({"rid": rid, "field": field, "val": val, "url": url,
                       "title": title, "conf": conf, "r": r, "dom": _domain(url)})
        evidence.setdefault((rid, field), set()).add(_domain(url))

    # 第二遍：硬负面双源/官方源仲裁 + 去重落盘。
    out = []
    for s in staged:
        rid, field, val, url = s["rid"], s["field"], s["val"], s["url"]
        if (field, val) in HARD_NEG:
            doms = {d for d in evidence.get((rid, field), set()) if d}
            if not is_official(url) and len(doms) < 2:
                dropped.append((rid, field, f"hardneg_single_source:{s['dom']}")); continue
        key = (rid, field, url)
        if key in seen:
            dropped.append((rid, field, "dup")); continue
        seen.add(key)
        out.append({
            "restaurant_id": rid, "name": s["r"].get("name", ""), "field": field,
            "value": val, "confidence": s["conf"], "source_url": url,
            "source_title": s["title"], "reason": s["r"].get("reason", ""),
            "search_date": today, "captured_at": now,
        })

    print(f"归一 {len(rows)} 条 -> 可入 findings {len(out)} 条；丢弃 {len(dropped)} 条")
    for d in dropped[:20]:
        print("  DROP", d)
    for o in out:
        print("  KEEP", o["restaurant_id"], o["field"], "->", o["value"],
              "| conf", o["confidence"], "|", o["source_url"][:60])
    if apply and out:
        with FINDINGS.open("a", encoding="utf-8") as fh:
            for o in out:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"已 append {len(out)} 条到 {FINDINGS}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="归一候选 JSON 文件")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    rows = json.loads(pathlib.Path(a.input).read_text(encoding="utf-8"))
    norm(rows, a.apply)


if __name__ == "__main__":
    main()

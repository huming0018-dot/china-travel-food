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
#   - 按 restaurant_id+field+source_url 去重；
#   - 默认 dry-run 打印不写；--apply 才 append。
import argparse, json, pathlib, os, sys, time

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

# 可信源白名单关键词（域名片段）；营销聚合/SEO 站不计
TRUSTED = ["meituan.com", "dianping.com", "michelin.", "blackpearl", "time out",
           "smartshanghai", "official", "weixin", "mp.weixin", "news.cn", "xinhua",
           "thepaper", "jiemian", "36kr", "yicai", "stcn", "official website"]
# 明显营销/聚合 SEO 站
NOISY = ["sohu.com/a", "163.com/dy", "baijiahao", "zhihu.com/question", "xiaohongshu.com/search"]


def is_trusted(url: str, title: str) -> bool:
    u = (url or "").lower(); t = (title or "").lower()
    if any(n in u for n in NOISY):
        return False
    return any(k in u or k in t for k in TRUSTED)


def norm(rows, apply=False):
    out, dropped = [], []
    seen = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if l.strip():
                f = json.loads(l)
                seen.add((f.get("restaurant_id"), f.get("field"), f.get("source_url")))
    today = time.strftime("%Y-%m-%d")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for r in rows:
        rid = r.get("restaurant_id")
        field = r.get("field")
        val = r.get("value")
        url = (r.get("source_url") or "").strip()
        title = r.get("source_title") or ""
        conf = float(r.get("confidence", 0))
        # 硬过滤
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
        seen.add(key)
        out.append({
            "restaurant_id": rid, "name": r.get("name", ""), "field": field,
            "value": val, "confidence": conf, "source_url": url,
            "source_title": title, "reason": r.get("reason", ""),
            "search_date": today, "captured_at": now,
        })

    print(f"归一 {len(rows)} 条 -> 可入 findings {len(out)} 条；丢弃 {len(dropped)} 条")
    for d in dropped[:10]:
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

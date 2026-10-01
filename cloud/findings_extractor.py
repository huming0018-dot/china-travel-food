#!/usr/bin/env python3
# findings_extractor.py — 模块B 标准件（全并行分片统一调用）
# 单一职责：
#   - 输入：agent 经 general_search 拿到的原始结果（restaurant_id, name, raw_docs[]），
#           LLM 已从 snippets 抽出 candidate claims（见 INPUT_SCHEMA）；
#   - 本模块【只做确定性校验】：源白/黑名单、枚举、confidence 口径、≥2 独立源、去重、落盘。
#   - 不联网、不调 LLM。
# 硬约束：只 PATCH chain/central_kitchen/premade_risk/investor_info/price_avg/food_safety；
#   电话/坐标/营业时间/精选层字段一律不动。宁空不假：无 source_url / conf<0.8 / 单一营销源 → 丢。
#
# 输入 JSON  schema（stdout 或 --input 文件）：
# {
#   "restaurant_id": int, "name": str,
#   "claims": [
#     {"field": "chain_type|central_kitchen|premade_risk|investor_info|price_avg|food_safety",
#      "value": str|number,
#      "claim_text": str,           # LLM 从 snippets 摘的原句
#      "confidence": float 0..1,    # LLM 自评
#      "source_url": str, "source_title": str, "source_host": str}
#   ]
# }
#
# 输出（dry-run 打印；--apply 时 append 到 findings.jsonl）：
#   findings 行：{restaurant_id, name, field, value, confidence, source_url,
#                 source_title, reason, search_date, captured_at}
import argparse, json, pathlib, os, sys, time

LEDGER = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data")) / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
FINDINGS = LEDGER / "findings.jsonl"

# 与 cloud/post_audit.py ALLOWED 严格对齐
ALLOWED = {
    "chain_type": {"独立店", "小型连锁", "大型连锁", "资本化连锁"},
    "central_kitchen": {"无", "疑似", "确认"},
    "premade_risk": {"无", "低", "疑似", "高"},
    "investor_info": None,
    "price_avg": None,
    "food_safety": {"无", "疑似", "问题"},
}

# 硬负面字段（chain/premade/food_safety/central_kitchen=确认）要求 ≥2 独立可信源
HARD_NEG_FIELDS = {"chain_type", "premade_risk", "central_kitchen", "food_safety"}

# 可信源 host 片段（官方/权威/主流媒体/点评）
TRUSTED_HOSTS = [
    "dianping.com", "meituan.com", "michelin", "blackpearl", "thebeijinger",
    "smartshanghai", "timeouts", "timeout.com", "webstar.tv",
    "mp.weixin.qq.com", "weixin.qq.com", "official", ".com.cn",
    "news.cn", "xinhuanet", "thepaper.cn", "jiemian.com", "36kr.com",
    "yicai.com", "stcn.com", "jfdaily.com", "shobserver.com", "eastday.com",
    "qcc.com", "tianyancha.com", "shuidi.cn", "meituan.net",
]
# chain_type 专用 TRUSTED：点评分店列表页（由 dianping_branch_list.py 产出）
# 与通用 TRUSTED 不同：同一品牌在点评出 ≥2 个不同地址分店，本身就构成 chain 证据。
CHAIN_TRUSTED_HOSTS = {"dianping.com", "meituan.com"}
# 噪声/营销/UGC 聚合 host（单一此类源不算数，至少要 1 个 TRUSTED 背书）
NOISY_HOSTS = [
    "sohu.com", "163.com", "baijiahao.baidu", "zhihu.com", "xiaohongshu.com",
    "douyin.com", "iesdouyin.com", "kuaishou", "bilibili.com", "ctrip.com",
    "m.ctrip.com", "dianping.com/xing", "toutiao.com", "eastday.com/sh",
]

MIN_CONF = 0.8


def host_of(url: str) -> str:
    u = (url or "").lower()
    if "://" in u:
        u = u.split("://", 1)[1]
    return u.split("/", 1)[0]


def is_trusted(url: str) -> bool:
    h = host_of(url)
    return any(k in h for k in TRUSTED_HOSTS)


def is_noisy(url: str) -> bool:
    h = host_of(url)
    return any(k in h for k in NOISY_HOSTS)


def _core(s):
    import re
    if not s: return ""
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"(店|分店|上海|路|号|区).*$", "", s)
    return s.strip()


def validate(payload: dict, apply: bool = False, db_names: dict = None):
    rid = payload.get("restaurant_id")
    name = payload.get("name", "")
    # name 核心一致性闸门：finding name 必须与 DB 该 rid 的 name 核心重叠
    if db_names and rid in db_names:
        dbn = db_names[rid]
        nc, dbc = _core(name), _core(dbn)
        if nc and dbc and nc != dbc and nc not in dbc and dbc not in nc:
            print(f"  REJECT name_mismatch rid={rid} finding={name} db={dbn}", file=sys.stderr)
            return []
    claims = payload.get("claims", [])

    # 加载已有（去重）
    seen = set()
    if FINDINGS.exists():
        for l in FINDINGS.read_text(encoding="utf-8").splitlines():
            if l.strip():
                f = json.loads(l)
                seen.add((f.get("restaurant_id"), f.get("field"), f.get("source_url")))

    # 按 field 分组，统计可信源数（用于硬负面 ≥2 规则）
    by_field = {}
    for c in claims:
        by_field.setdefault(c.get("field"), []).append(c)

    kept, dropped = [], []
    today = time.strftime("%Y-%m-%d")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    for c in claims:
        field = c.get("field"); val = c.get("value")
        url = (c.get("source_url") or "").strip()
        host = c.get("source_host") or host_of(url)
        conf = float(c.get("confidence", 0))
        reason = c.get("claim_text", "")[:200]

        if not rid or field not in ALLOWED:
            dropped.append((rid, field, "bad_field")); continue
        if not url.startswith("http"):
            dropped.append((rid, field, "no_url")); continue
        enum = ALLOWED[field]
        if enum and val not in enum:
            dropped.append((rid, field, f"bad_enum:{val}")); continue
        if field == "price_avg":
            try: val = float(val)
            except Exception:
                dropped.append((rid, field, "bad_price")); continue
        if conf < MIN_CONF:
            dropped.append((rid, field, f"low_conf:{conf}")); continue

        # 硬负面字段：该 field 下必须 ≥2 独立源；若全是 noisy 则丢
        if field in HARD_NEG_FIELDS:
            same = by_field[field]
            trusted = [x for x in same if (x.get("source_url") or "").startswith("http")
                       and is_trusted(x["source_url"])]
            # chain_type 特殊：点评/美团分店列表页（dianping_branch_list.py 产出）单独计数
            if field == "chain_type":
                chain_trusted = [x for x in same if (x.get("source_url") or "").startswith("http")
                                 and host_of(x["source_url"]) in CHAIN_TRUSTED_HOSTS]
                # 通用 TRUSTED + 点评分店列表 任一类凑齐 ≥2 独立 URL 即过
                if len({x["source_url"] for x in trusted + chain_trusted}) < 2:
                    dropped.append((rid, field, f"need_2_indep_trusted:{len(trusted)}+chain:{len(chain_trusted)}")); continue
            else:
                if len(trusted) < 2:
                    dropped.append((rid, field, f"need_2_indep_trusted:{len(trusted)}")); continue
        else:
            # 非硬负面（价格/集团）：至少 1 个 trusted，否则丢
            if not is_trusted(url):
                dropped.append((rid, field, "need_trusted_source")); continue

        key = (rid, field, url)
        if key in seen:
            dropped.append((rid, field, "dup")); continue
        seen.add(key)
        kept.append({
            "restaurant_id": rid, "name": name, "field": field, "value": val,
            "confidence": conf, "source_url": url, "source_title": c.get("source_title", ""),
            "reason": reason, "search_date": today, "captured_at": now,
        })

    print(f"[extract] rid={rid} {name} claims={len(claims)} kept={len(kept)} dropped={len(dropped)}")
    for d in dropped[:10]:
        print("  DROP", d)
    for k in kept:
        print("  KEEP", k["field"], "->", k["value"], "| conf", k["confidence"],
              "|", host_of(k["source_url"]))

    if apply and kept:
        with FINDINGS.open("a", encoding="utf-8") as fh:
            for k in kept:
                fh.write(json.dumps(k, ensure_ascii=False) + "\n")
        print(f"[apply] appended {len(kept)} -> {FINDINGS}")
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    payload = json.loads(pathlib.Path(a.input).read_text(encoding="utf-8"))
    validate(payload, a.apply)


if __name__ == "__main__":
    main()

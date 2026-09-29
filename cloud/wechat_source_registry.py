#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat_source_registry.py — P5 信源注册表 + 微信公众号/媒体源定时采集连接器（W2）。

定位（北极星：事实与评价分离、A2 宁空不假、P5 源当长期资产）：
  模型只做「发现 + 语义判断」：用免费 web 搜索（general_search / web.fetch，含
  site:mp.weixin.qq.com）发现可溯源的探店/事实文章，产出 discovered_seed.jsonl。
  本脚本做「机械环节」：
    1) 一次发现 -> 长期注册：源 upsert food_kol_watchlist，P5 扩展字段落
       research/mechanisms/W2/source_registry_ledger.json（按业务键幂等维护）；
    2) 按 refresh_cadence 定时 poll：到期源把新文章归档 food_kol_posts，并按在库
       店名抽取提及写 food_kol_mentions（提及=线索，绝不计口味）；
    3) 来源定性直接调 common.source_kind(text,url)：mp.weixin 个人探店=ugc，
       机构/集团/品牌/传媒号=brand/media；官方/媒体绝不冒充 UGC（确定性白名单兜底）；
    4) 事实与评价分离：探店口味只进 posts/mentions；仅可溯源「事实型」信号（集团隶属/
       搬迁原址）形成 fact_claim 候选，且只有命中在库餐厅才幂等 PATCH restaurants.fact_claims
       （合并键 type+source_url、写后回读断言），未命中=线索留痕、绝不臆造匹配（宁空不假）；
    5) 源质量评分 + 淘汰：按产出/实质度/营销占比/reliability 衰减，低质或停更源降级、
       连续失活淘汰并留痕。

用法（容器外先 cd $ROOT，FOOD_APP_DIR=$ROOT/app）：
  python3 wechat_source_registry.py --seed discovered_seed.jsonl            # dry-run
  python3 wechat_source_registry.py --seed discovered_seed.jsonl --apply     # 注册+poll+写库+回读
  python3 wechat_source_registry.py --audit                                  # P5 只读质量门
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from urllib.parse import quote

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT / "cloud" / "vendor" / "pipeline")):
    if p not in sys.path:
        sys.path.insert(0, p)

import common as C  # noqa: E402
import kol_post_ingest as KPI  # noqa: E402 （复用店名索引/提及抽取，机械环节）

W2_DIR = ROOT / "research" / "mechanisms" / "W2"
LEDGER = W2_DIR / "source_registry_ledger.json"

# ---- P5 常量 ----
KIND_INIT_REL = {"ugc": 0.60, "official_guide": 0.70, "media": 0.80,
                 "brand": 0.65, "map": 0.70, "other": 0.40}
CADENCE_DAYS = {"ugc": 7, "media": 7, "official_guide": 14, "brand": 30,
                "map": 30, "other": 30}
FLOOR_RELIABILITY = 0.30     # 低于此值 → 淘汰
STALE_HEALTH = 0.50          # 低于此值 → stale
MAX_STALE_STREAK = 3         # 连续 N 个 poll 无新文 → 淘汰
# 确定性官方/媒体/机构号白名单：这些 mp.weixin 号绝不许被 source_kind 误判为 ugc。
OFFICIAL_ACCOUNTS = {
    "跃动金海": "official_guide",          # 奉贤金海街道党群宣传
    "澎湃新闻·美食": "media",
    "上海发布": "official_guide",
    "乐游上海": "official_guide",
}
MIRROR_ACCOUNTS = {"奉贤政务公开·小商铺大流量转载": "other"}  # 聚合转载，不新增独立声音


def today() -> str:
    return dt.date.today().isoformat()


def bkey(platform: str, account: str) -> str:
    return f"{platform}::{account}"


# ---------------------------------------------------------------- 账本
def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {"workflow": "W2", "generated_at": dt.datetime.now().isoformat(),
            "sources": {}, "audit_log": []}


def save_ledger(led: dict):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    led["generated_at"] = dt.datetime.now().isoformat()
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 定性
def classify(account: str, account_url: str, hint: str) -> str:
    """来源定性：先调 common.source_kind，再用确定性白名单/镜像规则兜底，官方不得冒充 UGC。"""
    if account in OFFICIAL_ACCOUNTS:
        return OFFICIAL_ACCOUNTS[account]
    if account in MIRROR_ACCOUNTS:
        return MIRROR_ACCOUNTS[account]
    if hint in ("official_guide", "media", "brand", "ugc", "map"):
        return hint
    return C.source_kind(account, account_url)


def trust_of(rel: float) -> str:
    return "high" if rel >= 0.7 else ("mid" if rel >= 0.5 else "low")


# ---------------------------------------------------------------- watchlist
def upsert_watchlist(rec: dict, apply: bool) -> int | None:
    """按 (name, platform) 幂等 upsert food_kol_watchlist，返回 kol_id。"""
    account, platform = rec["name"], rec["platform"]
    r = C.req("GET", f"/food_kol_watchlist?select=id,name,platform,status&"
                     f"name=eq.{quote(account, safe='')}&platform=eq.{quote(platform, safe='')}")
    rows = r.json()
    body = {
        "name": account, "platform": platform, "region": "上海",
        "kol_type": "博主",  # watchlist CHECK 约束仅允许存量枚举（博主/官方号等）；角色见 kind
        "specialty_tags": rec.get("covers", []), "trust": trust_of(rec["reliability"]),
        # watchlist.status 有枚举约束（仅 active 等）；淘汰状态以 P5 账本 health=dead 为准，
        # 不把 DB.status 改成 inactive（避免 CHECK 400）。trust=low 标记低质。
        "status": "active",
        "profile_url": rec.get("profile_url") or None, "last_seen": today(),
    }
    if rows:
        kol_id = rows[0]["id"]
        if apply:
            rb = {k: body[k] for k in ("trust", "status", "specialty_tags", "last_seen", "profile_url")}
            try:
                rr = C.req("PATCH", f"/food_kol_watchlist?id=eq.{kol_id}", json=rb)
                rr.raise_for_status()
            except Exception as e:  # 健康同步非关键路径：不中断 posts/mentions/fact 主写
                print(f"  [WARN] watchlist PATCH id={kol_id} 跳过: {e} | body={rb}")
        return kol_id
    if not apply:
        return None
    body["first_seen"] = today()
    h = C.headers(); h["Prefer"] = "return=representation"
    import requests
    resp = requests.post(C.BASE + "/food_kol_watchlist", headers=h, json=body, timeout=45)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"watchlist insert {resp.status_code}: {resp.text[:200]}")
    return resp.json()[0]["id"]


# ---------------------------------------------------------------- 文章/提及
def upsert_post(kol_id: int | None, art: dict, kind: str, apply: bool) -> int | None:
    import requests
    post = {"kol_id": kol_id, "platform": "wechat" if "mp.weixin" in art["post_url"] else "web_media",
            "post_url": art["post_url"], "title": art.get("title") or "",
            "summary": art.get("summary") or "", "published_at": art.get("published_at")}
    if not apply:
        return None
    h = C.headers(); h["Prefer"] = "resolution=merge-duplicates,return=representation"
    resp = requests.post(C.BASE + "/food_kol_posts?on_conflict=post_url",
                         headers=h, json=post, timeout=45)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"post upsert {resp.status_code}: {resp.text[:200]}")
    rep = resp.json()
    if isinstance(rep, list) and rep:
        return rep[0]["id"]
    got = requests.get(C.BASE + f"/food_kol_posts?post_url=eq.{quote(art['post_url'], safe='')}&select=id",
                        headers=C.headers(), timeout=30).json()
    return got[0]["id"]


def write_mentions(post_id: int, mentions: list, apply: bool):
    import requests
    if not mentions:
        return 0
    rows = [{"post_id": post_id, "restaurant_id": m["rid"],
             "mentioned_raw": m["name"], "match_status": "matched",
             "polarity": m["polarity"]} for m in mentions]
    if not apply:
        return len(rows)
    h = C.headers(); h["Prefer"] = "resolution=merge-duplicates"
    rr = requests.post(C.BASE + "/food_kol_mentions?on_conflict=post_id,mentioned_raw",
                       headers=h, json=rows, timeout=45)
    if rr.status_code not in (200, 201):
        raise RuntimeError(f"mention upsert {rr.status_code}: {rr.text[:200]}")
    return len(rows)


# ---------------------------------------------------------------- 事实主张
FACT_PATTERNS = [
    ("group_relation", r"([一-鿿]{2,10}集团)旗下", "{}旗下品牌（机构号自述）", "low"),
    ("relocation", r"原([一-鿿]{2,10}店)", "原址 {}（现址见正文，需二次核址）", "low"),
]


def extract_fact_claims(art: dict, kind: str) -> list:
    """事实与评价分离：只抽可溯源『事实型』信号，不抽口味评价。返回 claim 候选。"""
    out = []
    blob = (art.get("summary") or "") + " " + (art.get("text") or "")
    for ctype, pat, tpl, conf in FACT_PATTERNS:
        import re
        m = re.search(pat, blob)
        if not m:
            continue
        out.append({"type": ctype, "value": tpl.format(m.group(1)),
                    "confidence": conf, "date": art.get("published_at") or today(),
                    "source_url": art["post_url"],
                    "quote": blob[max(0, m.start() - 12):m.end() + 12].strip()})
    return out


def match_restaurants(rests: list, claim_text: str):
    """事实主张按店名子串命中在库餐厅；只对命中者写 fact_claims，未命中=线索。"""
    hits = []
    for r in rests:
        names = [r.get("name") or ""] + list(r.get("aliases") or [])
        for n in names:
            if n and len(n) >= 2 and n in claim_text:
                hits.append(r)
                break
    return hits


def apply_fact_claims(claim: dict, rests: list, apply: bool) -> dict:
    hits = match_restaurants(rests, claim["value"] + claim["quote"])
    res = {"claim": claim, "matched_ids": [h["id"] for h in hits],
           "matched_names": [h["name"] for h in hits], "applied": False}
    if not hits or not apply:
        return res
    import requests
    for r in hits:
        existing = r.get("fact_claims") or []
        if any(c.get("type") == claim["type"] and c.get("source_url") == claim["source_url"]
               for c in existing):
            continue  # 幂等：同主张已存在
        merged = existing + [claim]
        body = {"fact_claims": merged}
        pr = C.req("PATCH", f"/restaurants?id=eq.{r['id']}", json=body)
        pr.raise_for_status()
        # 写后回读断言
        got = C.fetch_all("restaurants", "id,fact_claims", extra=f"id=eq.{r['id']}")
        assert got and len(got[0].get("fact_claims") or []) == len(merged), \
            f"id={r['id']} fact_claims 回读数量不符"
        res["applied"] = True
    return res


# ---------------------------------------------------------------- poll
def due_now(last_polled: str | None, cadence_days: int) -> bool:
    if not last_polled:
        return True  # 新注册源：本轮即首次 poll
    try:
        d = dt.date.fromisoformat(last_polled)
    except Exception:
        return True
    return (dt.date.today() - d).days >= cadence_days


def run(seed_path: pathlib.Path, apply: bool):
    led = load_ledger()
    # 1) 读发现种子，按源聚合
    seed_rows = [json.loads(l) for l in seed_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_src = {}
    for row in seed_rows:
        k = bkey(row["platform"], row["account"])
        by_src.setdefault(k, {"meta": row, "articles": []})
        if row.get("article", {}).get("post_url"):
            by_src[k]["articles"].append(row["article"])

    rests = C.fetch_all("restaurants", "id,name,aliases,status")
    name_idx = KPI.build_name_index(rests)

    stats = {"registered_new": 0, "registered_existing": 0, "polled": 0,
             "posts_archived": 0, "mentions": 0, "fact_claim_candidates": 0,
             "fact_claims_applied": 0, "leads_unmatched": 0, "degraded": 0, "eliminated": 0}

    for k, bucket in by_src.items():
        meta, arts = bucket["meta"], bucket["articles"]
        kind = classify(meta["account"], meta.get("account_url", ""), meta.get("account_kind_hint", ""))
        rec = led["sources"].get(k)
        is_new = rec is None
        if is_new:
            rec = {"business_key": k, "name": meta["account"], "platform": meta["platform"],
                   "kind": kind, "auth_level": "L0", "covers": meta.get("covers", []),
                   "reliability": KIND_INIT_REL.get(kind, 0.5),
                   "refresh_cadence_days": CADENCE_DAYS.get(kind, 14),
                   "last_polled": None, "health": "active", "stale_streak": 0,
                   "connector_module": "cloud/wechat_source_registry.py",
                   "profile_url": meta.get("account_url", ""), "history": []}
            led["sources"][k] = rec
            stats["registered_new"] += 1
        else:
            stats["registered_existing"] += 1
            rec["kind"] = kind  # 每次复核定性（不被源自填带偏）

        # 2) 到节奏才 poll
        if not due_now(rec["last_polled"], rec["refresh_cadence_days"]):
            rec["history"].append({"at": today(), "event": "skipped_not_due"})
            continue
        stats["polled"] += 1

        n_new_articles = 0
        n_mentions = 0
        substance = 0
        promo = 0
        kol_id = upsert_watchlist(rec, apply=apply)
        for art in arts:
            pid = upsert_post(kol_id, art, kind, apply=apply)
            n_new_articles += 1
            stats["posts_archived"] += 1
            blob = (art.get("title", "") + " " + art.get("summary", "") + " " + art.get("text", ""))
            mentions = KPI.find_mentions(blob, name_idx)
            if pid is not None:
                n_mentions += write_mentions(pid, mentions, apply=apply)
            else:
                n_mentions += len(mentions)
            stats["mentions"] += len(mentions)
            if C.quote_has_substance(blob):
                substance += 1
            # 官方/机构号的宣传稿不算堂食口味证据（事实与评价分离）
            if kind in ("official_guide", "brand", "other"):
                promo += 1
            # 事实主张候选
            for claim in extract_fact_claims(art, kind):
                stats["fact_claim_candidates"] += 1
                res = apply_fact_claims(claim, rests, apply=apply)
                if res["applied"]:
                    stats["fact_claims_applied"] += 1
                if not res["matched_ids"]:
                    stats["leads_unmatched"] += 1
                rec["history"].append({"at": today(), "event": "fact_claim",
                                       "type": claim["type"], "value": claim["value"],
                                       "matched": res["matched_names"], "applied": res["applied"]})

        # 3) reliability 评分
        if n_new_articles > 0:
            sub_ratio = substance / n_new_articles
            promo_ratio = promo / n_new_articles
            rec["reliability"] = round(min(1.0, max(0.0, rec["reliability"]
                                                    + 0.04 * sub_ratio - 0.08 * promo_ratio)), 3)
            rec["stale_streak"] = 0
        else:
            rec["reliability"] = round(max(0.0, rec["reliability"] - 0.15), 3)  # 停更衰减
            rec["stale_streak"] += 1
            stats["degraded"] += 1

        # 4) health / 淘汰
        prev = rec["health"]
        if rec["reliability"] < FLOOR_RELIABILITY or rec["stale_streak"] >= MAX_STALE_STREAK:
            rec["health"] = "dead"
        elif rec["reliability"] < STALE_HEALTH:
            rec["health"] = "stale"
        else:
            rec["health"] = "active"
        if rec["health"] == "dead" and prev != "dead":
            stats["eliminated"] += 1
            rec["history"].append({"at": today(), "event": "eliminated",
                                   "reason": f"reliability={rec['reliability']}<{FLOOR_RELIABILITY} "
                                             f"或 stale_streak={rec['stale_streak']}>={MAX_STALE_STREAK}，"
                                             f"停止独立采集，仅留痕"})
        elif rec["health"] != prev:
            stats["degraded"] += 1
            rec["history"].append({"at": today(), "event": f"health:{prev}->{rec['health']}",
                                    "reliability": rec["reliability"]})

        rec["last_polled"] = today()
        # watchlist 健康同步回写
        upsert_watchlist(rec, apply=apply)

    if apply:
        save_ledger(led)
    return led, stats


# ---------------------------------------------------------------- P5 门
def audit() -> int:
    """P5 质量门（只读）：在用源必须注册且有 connector+cadence+last_polled；
    不得有一次性源（无 connector_module）；reliability 不得低于淘汰线却仍 active。"""
    led = load_ledger()
    srcs = led.get("sources", {})
    errs, warns = [], []
    for k, s in srcs.items():
        if not s.get("connector_module"):
            errs.append(f"{k}: 无 connector_module（一次性源，违反 P5）")
        if s.get("health") == "active":
            if not s.get("last_polled"):
                errs.append(f"{k}: active 但从未 poll（缺 last_polled）")
            if s.get("reliability", 1) < FLOOR_RELIABILITY:
                errs.append(f"{k}: reliability={s.get('reliability')} 已低于淘汰线却仍 active")
        for f in ("platform", "kind", "refresh_cadence_days", "reliability"):
            if f not in s:
                errs.append(f"{k}: 缺字段 {f}")
    n_active = sum(1 for s in srcs.values() if s.get("health") == "active")
    n_dead = sum(1 for s in srcs.values() if s.get("health") == "dead")
    print(f"[P5 source_registry] 注册源={len(srcs)} active={n_active} stale="
          f"{sum(1 for s in srcs.values() if s.get('health')=='stale')} dead={n_dead}")
    for w in warns:
        print("  WARN", w)
    for e in errs:
        print("  ERROR", e)
    print(f"P5_GATE_ERRORS={len(errs)}")
    return 1 if errs else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--audit", action="store_true")
    args = ap.parse_args()
    if args.audit:
        sys.exit(audit())
    if not args.seed:
        raise SystemExit("用法: --seed <discovered.jsonl> [--apply] | --audit")
    led, stats = run(pathlib.Path(args.seed), apply=args.apply)
    print(f"=== wechat_source_registry {'APPLY' if args.apply else 'DRY-RUN'} ===")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    for k, s in led["sources"].items():
        print(f"  [{s['health']:6}] {s['kind']:14} rel={s['reliability']:.2f} "
              f"cad={s['refresh_cadence_days']}d last={s['last_polled']} <- {s['name']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""blackpearl_reconcile.py — 黑珍珠「全量召回 + 官方总数对账 + 缺店闭环」（确定性、可复跑）。

对齐 authority-recall 三件套与米其林处理口径：
  1) 全量底册 = blackpearl_shanghai_full.json（官方 61 家，3/2/1 钻）。
  2) 与官方总数对账：底册枚举 61 == 官方 total 61；再对【当前库】重新四态匹配，
     刷新 matched_id / gap_status（旧文件状态可能已被后续深覆盖改变）。
  3) 缺店闭环：仍不在库的店不强行收录（北极星：权威背书≠真实口味证据）——
     分类为 ready_raw（已有地址/raw，待口味证据）与 hold_evidence（证据不足），
     统一写入口味证据填充队列，交 Apify/XHS 真实食客采集，达到 admission 门槛才入库。

用法（deuce，纯 python 无需浏览器）：
  python blackpearl_reconcile.py            # 对账，落 blackpearl_reconcile.json
  python blackpearl_reconcile.py --queue    # 额外落 blackpearl_fill_queue.json
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (str(HERE), "/app/pipeline", "/app/cloud"):
    if p not in sys.path:
        sys.path.insert(0, p)
import common as C            # noqa: E402
import authority_sitemap as S  # noqa: E402

AUTH = S.AUTH
FULL = AUTH / "blackpearl_shanghai_full.json"
DIAMOND_KEYS = ("three_diamond", "two_diamond", "one_diamond")


def entry_name(it):
    return it.get("raw_name") or it.get("name") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", action="store_true")
    args = ap.parse_args()

    book = json.loads(FULL.read_text(encoding="utf-8"))
    official_total = book.get("total")
    items = []
    for dk in DIAMOND_KEYS:
        for it in book.get(dk, []):
            it = dict(it); it["_diamond_key"] = dk; items.append(it)

    print(f"底册枚举 {len(items)} / 官方 total {official_total}")
    if len(items) != official_total:
        print(f"⚠ 底册与官方总数差 {official_total-len(items)}：官方完整名单需登录点评黑珍珠频道补全")

    rests = C.fetch_all("restaurants", "id,name,name_en,aliases,status,district")
    # 把 aliases 纳入匹配索引：复用 matcher 前扩展 name/name_en 不便，改为构造"虚拟行"
    virt = []
    for r in rests:
        virt.append(r)
        for al in (r.get("aliases") or []):
            if al:
                rr = dict(r); rr["name"] = al; rr["name_en"] = None; virt.append(rr)
    matcher = S.make_matcher(virt)

    in_db, ready_raw, hold = [], [], []
    for it in items:
        nm = entry_name(it)
        cores = [S.core(nm)]
        m, conf = matcher(cores)
        rec = {"name": nm, "diamond": it.get("diamond"),
               "cuisine": it.get("cuisine"), "district": it.get("district"),
               "address": it.get("address"), "source_url": it.get("source_url"),
               "match_conf": conf,
               "matched_id": m["id"] if m else None,
               "prev_status": it.get("gap_status")}
        if conf in ("exact", "strong") and m:
            rec["gap_status"] = "in_db"; in_db.append(rec)
        else:
            # 仍不在库：权威在册但缺真实口味证据 →进填充/取证闭环
            if it.get("gap_status") == "gap_suspect":
                rec["gap_status"] = "hold_evidence"
                rec["reason"] = it.get("suspect_reason"); hold.append(rec)
            else:
                rec["gap_status"] = "ready_raw"; ready_raw.append(rec)

    out = {"official_total": official_total, "listed": len(items),
           "counts": {"in_db": len(in_db), "ready_raw": len(ready_raw),
                      "hold_evidence": len(hold)},
           "in_db": in_db, "ready_raw": ready_raw, "hold_evidence": hold}
    (AUTH / "blackpearl_reconcile.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== 黑珍珠实时对账（当前库）===")
    print(f"在库 {len(in_db)}；已产raw待口味证据 {len(ready_raw)}；证据不足hold {len(hold)}")
    for r in ready_raw:
        print(f"  ready_raw：{r['name']}（{r.get('cuisine')}）")
    for r in hold:
        print(f"  hold：{r['name']}：{(r.get('reason') or '')[:46]}")
    print("\n已落 blackpearl_reconcile.json")

    if args.queue:
        q = [{"name": r["name"], "diamond": r["diamond"],
              "cuisine": r.get("cuisine"), "district": r.get("district"),
              "address": r.get("address"), "source_url": r.get("source_url"),
              "need": "taste_evidence"}
             for r in (ready_raw + hold)]
        (AUTH / "blackpearl_fill_queue.json").write_text(
            json.dumps({"n": len(q), "queue": q}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print(f"已落 blackpearl_fill_queue.json（{len(q)} 家待真实食客口味证据）")


if __name__ == "__main__":
    main()

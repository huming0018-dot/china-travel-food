#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ab_compare.py — sian / atomus / opspilot 三家小红书采集器 A/B 对照（#44）
=================================================================================
目的：同一批店、同一级查询（搜索级），实测每家 actor 的
  · 每店真实成本（以月度账单 usage 差值为权威口径）
  · 采信率（anchor_note 判定为目标店的笔记占比）
  · 每采信 1 条口味证据的成本（cost / taste）
据此把"成本路由"从标价推断升级为实测结论，再固化进 v4 控制器。

口径：
  · 三家搜索级结果均已带正文（opspilot=description / atomus=desc / sian=noteDesc），
    故只做"搜索级"对照即公平且最省；不自动追全文（全文另计费）。
  · 成本 = 运行前后 current_used()（totalUsageCreditsUsdAfterVolumeDiscount）差值；
    run-sync 同步阻塞，返回后轮询账单至稳定。
  · 全局预算 AB_BUDGET_USD（默认 $3）；逐 run 前查剩余额度，不足即 NO_CREDIT 退出。
  · 断点续跑：账本 ab_result.json，cell key="rid:actor"，已完成不重跑。

用法：
  python3 ab_compare.py            # 仅打印计划（不付费）
  python3 ab_compare.py --run      # 强制执行（付费，受预算闸门保护）
  python3 ab_compare.py --auto     # 控制器调用：结果缺失且剩余额度≥$5 才跑，否则立即退出
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import review_apify_fill as F   # 复用 keywords_for / apify_search / normalize_note / 账单 / TOKEN
import entity_match as EM

C = F.C

RESULT_F = HERE / "ab_result.json"
MD_F = HERE / "AB_RESULT.md"
AB_BUDGET = float(os.environ.get("AB_BUDGET_USD", "3.0"))
MAX_CHARGE = float(os.environ.get("AB_MAX_CHARGE_USD", "0.30"))
SEARCH_ITEMS = int(os.environ.get("AB_SEARCH_ITEMS", "12"))
AUTO_MIN_REMAIN = float(os.environ.get("AB_AUTO_MIN_REMAIN", "5.0"))

# 三个代表性场景（覆盖三种典型查询，路由结论才有区分度）
TARGETS = [
    {"rid": 871,  "name": "新荣记(南京西路店)", "tag": "名品牌·合集压力"},
    {"rid": None, "name": "望庐",               "tag": "米其林单菜系·深度测评"},
    {"rid": 1865, "name": "Tacolicious(同乐坊店)", "tag": "外文名·相关性压力"},
]
ACTORS = ["opspilot", "atomus", "sian"]

SIAN_RUN = ("https://api.apify.com/v2/acts/sian.agency~xiaohongshu-rednote-scraper"
            "/run-sync-get-dataset-items")


# ───────────────────────────── 目标解析 ─────────────────────────────
def resolve_targets():
    rows = C.fetch_all("restaurants", "id,name,signature_dishes,status,address,district")
    byid = {r["id"]: r for r in rows}
    out = []
    for t in TARGETS:
        rec = byid.get(t["rid"]) if t["rid"] else None
        if rec is None:
            core = t["name"].split("(")[0]
            cand = [r for r in rows if r.get("status") != C.STATUS_CLOSED
                    and core in (r.get("name") or "")]
            if not cand:
                print("  ! 未定位到:", t["name"]); continue
            # 望庐：优先“外滩”，否则取首条
            wai = [r for r in cand if "外滩" in (r.get("name") or "")]
            rec = (wai or cand)[0]
        out.append(rec)
    return out


# ───────────────────────────── sian 适配器 ─────────────────────────────
def sian_run(keyword, max_items):
    if not F.TOKEN:
        return None, "APIFY_TOKEN 未配置"
    body = {"action": "searchNote", "keyword": keyword, "searchType": "note",
            "sortType": "general", "page": 1, "maxItems": max_items}
    params = {"token": F.TOKEN, "maxItems": max_items,
              "maxTotalChargeUsd": MAX_CHARGE}
    try:
        r = requests.post(SIAN_RUN, params=params, json=body, timeout=220)
    except Exception as e:
        return None, "exc:%s" % e
    if r.status_code not in (200, 201):
        return None, "http%s:%s" % (r.status_code, r.text[:120])
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        return None, str(data["error"])[:160]
    if isinstance(data, list):
        good = [x for x in data
                if not (isinstance(x, dict) and x.get("error_kind"))]
        return good, None
    return data, None


def norm_sian(n):
    nid = n.get("noteId") or n.get("id")
    title = n.get("noteTitle") or n.get("title") or ""
    desc = n.get("noteDesc") or n.get("desc") or ""
    url = n.get("notePageUrl") or n.get("url") or (
        f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
    author = n.get("userName") or ""
    if not author and isinstance(n.get("user"), dict):
        author = n["user"].get("nickname") or n["user"].get("nickName") or ""
    liked = n.get("likedCount") or n.get("liked_count")
    return {"id": nid, "title": title, "desc": desc, "url": url,
            "author": author, "liked_count": liked, "provider": "sian"}


def norm_for(actor, n):
    if actor == "sian":
        return norm_sian(n)
    return F.normalize_note(actor, n)


# ───────────────────────── 成本测量（账单差值，权威） ─────────────────────────
def cost_around(run_fn):
    before = F.current_used()
    items, err = run_fn()
    after = before
    for _ in range(8):
        time.sleep(3)
        cur = F.current_used()
        if cur > after:
            after = cur
            time.sleep(2)
            after = max(after, F.current_used())
            break
    return items, err, round(max(0.0, after - before), 4)


# ───────────────────────── 采信/口味统计 ─────────────────────────
def evaluate(notes, idx, rec):
    reasons = {}
    n_anchor = 0
    n_taste = 0
    rows = []
    for note in notes:
        rid, reason = idx.anchor_note(note, rec["name"])
        reasons[reason] = reasons.get(reason, 0) + 1
        text = note.get("title", "") + "\n" + note.get("desc", "")
        tv, _ = EM.taste_sent(text)
        question = EM.is_question(text)
        anchored = (rid == rec["id"])
        taste = (tv is not None and not question)
        if anchored:
            n_anchor += 1
        if anchored and taste:
            n_taste += 1
        rows.append({"title": note.get("title", "")[:60], "rid": rid,
                     "reason": reason, "taste": tv, "anchored": anchored,
                     "url": note.get("url", "")})
    return {"n": len(notes), "anchor": n_anchor, "taste": n_taste,
            "reasons": reasons, "rows": rows}


# ───────────────────────── 账本 ─────────────────────────
def load_ledger():
    if RESULT_F.exists():
        try:
            return json.loads(RESULT_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"started_at": C.today(), "budget": AB_BUDGET,
            "cells": {}, "done": False, "stop": None}


def save_ledger(led):
    RESULT_F.write_text(json.dumps(led, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def spent_total(led):
    return round(sum(c["cost"] for c in led["cells"].values()), 4)


# ───────────────────────── 主执行 ─────────────────────────
def run_all(force=False):
    led = load_ledger()
    if led.get("done") and not force:
        print("A/B 已完成，见", MD_F); return
    idx = EM.get_index()
    targets = resolve_targets()
    print("目标店 %d 家；预算 $%.2f；已完成 cell %d" %
          (len(targets), AB_BUDGET, len(led["cells"])))
    stop = None
    for rec in targets:
        q1, _q2 = F.keywords_for(rec)
        for actor in ACTORS:
            key = "%s:%s" % (rec["id"], actor)
            if key in led["cells"]:
                continue
            spent = spent_total(led)
            if spent >= AB_BUDGET:
                stop = "BUDGET"; break
            if F.remaining_credit() <= 0.01:
                stop = "NO_CREDIT"; break
            print("  >> %s [%s] q1=%s" % (rec["name"], actor, q1))
            if actor == "sian":
                fn = lambda: sian_run(q1, SEARCH_ITEMS)
            else:
                fn = lambda actor=actor: F.apify_search(actor, q1,
                                                        max_items=SEARCH_ITEMS)
            items, err, cost = cost_around(fn)
            raw = items or []
            if not isinstance(raw, list):
                raw = []
            notes = [norm_for(actor, n) for n in raw if isinstance(n, dict)]
            metrics = evaluate(notes, idx, rec)
            led["cells"][key] = {
                "rid": rec["id"], "name": rec["name"], "actor": actor,
                "q1": q1, "cost": cost, "err": err,
                "n_raw": len(raw), "metrics": metrics}
            save_ledger(led)
            print("     cost=$%.3f raw=%d anchor=%d taste=%d err=%s" %
                  (cost, len(raw), metrics["anchor"], metrics["taste"], err))
        if stop:
            break
    if stop:
        led["stop"] = stop
        save_ledger(led)
        print("@@STATUS %s 已完成 cell=%d spent=$%.3f（断点保留，下次续跑）" %
              (stop, len(led["cells"]), spent_total(led)))
        if stop == "NO_CREDIT":
            deliver("action", "ab_nocredit",
                    "A/B 对照跑到一半额度不足，已保存进度；充值后下一周期自动续跑。")
        return
    if len(led["cells"]) >= len(targets) * len(ACTORS):
        led["done"] = True
        save_ledger(led)
        finalize(led)


# ───────────────────────── 汇总 + 报告 ─────────────────────────
def aggregate(led, n_shops):
    per = {a: {"cost": 0.0, "notes": 0, "anchor": 0, "taste": 0}
           for a in ACTORS}
    for c in led["cells"].values():
        a = c["actor"]; m = c["metrics"]
        per[a]["cost"] += c["cost"]
        per[a]["notes"] += m["n"]
        per[a]["anchor"] += m["anchor"]
        per[a]["taste"] += m["taste"]
    for a, d in per.items():
        d["cost_per_shop"] = round(d["cost"] / n_shops, 3) if n_shops else None
        d["anchor_rate"] = round(d["anchor"] / d["notes"], 3) if d["notes"] else None
        d["cost_per_taste"] = round(d["cost"] / d["taste"], 3) if d["taste"] else None
    return per


def finalize(led):
    n_shops = len(TARGETS)
    per = aggregate(led, n_shops)
    # 路由结论
    def best(metric, reverse=False):
        vals = [(a, d[metric]) for a, d in per.items()
                if d[metric] is not None]
        if not vals:
            return None
        return (min(vals, key=lambda x: x[1]) if not reverse
                else max(vals, key=lambda x: x[1]))
    cheap_taste = best("cost_per_taste")
    high_anchor = best("anchor_rate", reverse=True)
    # 名品牌(合集压力)场景下最便宜且有采信者 → 探测通道
    probe_cell = [(c["actor"], c["cost"], c["metrics"]["anchor"])
                  for c in led["cells"].values() if c["rid"] == 871]
    probe = sorted([x for x in probe_cell if x[2] > 0], key=lambda x: x[1])
    probe = probe[0] if probe else (probe_cell[0] if probe_cell else None)

    lines = []
    lines.append("# 小红书采集器 A/B 实测报告（%s）\n" % C.today())
    lines.append("> 同 %d 家店 × 3 actor 搜索级对照；成本=月度账单 usage 差值。\n" % n_shops)
    head = "| actor | 总成本 | 每店成本 | 笔记数 | 采信数 | 采信率 | 口味证据 | 每条口味成本 |"
    sep = "|---|---|---|---|---|---|---|---|"
    lines.append(head); lines.append(sep)
    name_zh = {"opspilot": "opspilot", "atomus": "atomus", "sian": "sian"}
    for a in ACTORS:
        d = per[a]
        lines.append("| %s | $%.3f | $%.3f | %s | %s | %s | %s | %s |" % (
            name_zh[a], d["cost"], d["cost_per_shop"] or 0, d["notes"],
            d["anchor"], d["anchor_rate"] if d["anchor_rate"] is not None else "-",
            d["taste"], ("$%.3f" % d["cost_per_taste"])
            if d["cost_per_taste"] is not None else "-"))
    lines.append("")
    lines.append("## 逐 cell 明细\n")
    lines.append("| 店 | actor | 成本 | raw | 采信 | 口味 | 拒绝原因分布 |")
    lines.append("|---|---|---|---|---|---|---|")
    for c in led["cells"].values():
        m = c["metrics"]
        rs = ", ".join("%s×%d" % (k, v) for k, v in
                       sorted(m["reasons"].items(), key=lambda x: -x[1]))
        lines.append("| %s | %s | $%.3f | %d | %d | %d | %s |" % (
            c["name"], c["actor"], c["cost"], c["n_raw"],
            m["anchor"], m["taste"], rs))
    lines.append("")
    lines.append("## 自动路由建议\n")
    if cheap_taste:
        lines.append("- **精准查询默认通道**：%s（每条口味证据 $%.3f，最低）。"
                     % (cheap_taste[0], cheap_taste[1]))
    if high_anchor:
        lines.append("- **采信率最高**：%s（%.0f%%）。"
                     % (high_anchor[0], (high_anchor[1] or 0) * 100))
    if probe:
        lines.append("- **名品牌/合集压力场景先探测**：%s（该场景成本 $%.3f、采信 %d），"
                     "避免固定价通道为合集付费。" % (probe[0], probe[1], probe[2]))
    lines.append("\n> 注：搜索级未含全文/视频（sian 全文 .05、atomus .04）；"
                 "若搜索级正文被截断，应在控制器按 anchored 笔记再追全文，另测。")
    MD_F.write_text("\n".join(lines), encoding="utf-8")

    body = "A/B 实测完成（%d店×3）：\n" % n_shops
    for a in ACTORS:
        d = per[a]
        body += ("· %s 每店$%.3f 采信率%s 每条口味%s\n" % (
            a, d["cost_per_shop"] or 0,
            ("%.0f%%" % (d["anchor_rate"] * 100)) if d["anchor_rate"] is not None else "-",
            ("$%.3f" % d["cost_per_taste"]) if d["cost_per_taste"] is not None else "无"))
    if cheap_taste:
        body += "建议精准通道=%s；详见 AB_RESULT.md" % cheap_taste[0]
    deliver("info", "ab_done", body)
    print(body)
    print("报告:", MD_F)
    print("@@STATUS AB_DONE")


# ───────────────────────── 经容器投递（best effort） ─────────────────────────
def deliver(level, key, body):
    try:
        p = subprocess.run(
            ["sudo", "docker", "exec", "-i", "food-cloud", "bash", "-c",
             ". /app/cloud/env.sh; python3 /app/cloud/notify_cli.py \"$@\"",
             "_", level, key],
            input=body, text=True, capture_output=True, timeout=40)
        ok = p.returncode == 0
        if not ok:
            print("  (notify failed:", (p.stdout + p.stderr)[:120], ")")
        return ok
    except Exception as e:
        print("  (notify exc:", e, ")")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="强制执行（付费）")
    ap.add_argument("--auto", action="store_true",
                    help="结果缺失且剩余额度≥$5 才跑")
    ap.add_argument("--force-redo", action="store_true")
    args = ap.parse_args()

    if args.auto:
        if RESULT_F.exists():
            print("@@STATUS AB_SKIP done"); return
        rem = F.remaining_credit()
        if rem < AUTO_MIN_REMAIN:
            print("@@STATUS AB_SKIP remain=$%.2f" % rem); return
        run_all(force=args.force_redo)
    elif args.run:
        run_all(force=args.force_redo)
    else:
        led = load_ledger()
        print("A/B 计划：%d 店 × %s，预算 $%.2f；已完成 cell=%d/%d" % (
            len(TARGETS), ACTORS, AB_BUDGET, len(led["cells"]),
            len(TARGETS) * len(ACTORS)))
        print("剩余额度: $%.2f；加 --run 执行，--auto 由控制器按额度自动执行。"
              % F.remaining_credit())


if __name__ == "__main__":
    main()

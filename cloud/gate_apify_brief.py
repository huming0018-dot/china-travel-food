#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_apify_brief.py — gate 产出的 Apify 采证 brief（决定真实食客评价预算花给谁）。

为什么存在：此前 review_apify_fill 按"高价优先"在 ~986 家上撒网，钱没有集中在
"捍卫精选 / 核实榜单店"上；也不排除 gate 已判定的中央厨房/高预制店。
本脚本把 gate 的结论转成明确、分层、带理由的采证名单：
  P0：精选店但独立食客声音 <2 —— 优先采证以捍卫/确认精选；
  P1：非精选但当前在榜（米其林星/必比登/黑珍珠）且声音 <2 —— 采证以定晋升；
  P2：其他榜单(other_list)或聚合口味≥4 且声音 <2 —— 有苗头，补证；
  其余 0 声音、无榜单、非精选店：不进付费名单（不撒胡椒面）。
硬排除（写负面清单，不采证、不精选）：关店 / central_kitchen=确认 / premade_risk=高。

产出（容器 /app/data/research/atlas/）：
  apify_brief.json 机器名单；apify_brief.md 人工 brief；worth_fill.json 控制器队列；
  负面清单 /app/data/post_record/negative_list.json。
worth_fill.json 需再 docker cp 到主机 /home/ubuntu/food-apify-fill/ 供控制器读取。
"""
import argparse
import json
import os
import pathlib
import sys
import time
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C   # noqa: E402

ATLAS = DATA / "research" / "atlas"
POST = DATA / "post_record"
MIN_VOICES = 2          # 达此独立食客声音即不再付费采
TARGET_VOICES = 3
HEADLINE = {"michelin_star", "bib_gourmand", "black_pearl"}


def voices_by_rid():
    V = C.fetch_all("reviews",
                    "restaurant_id,is_verified_diner,author_name,trust_level")
    voices = defaultdict(set)
    for v in V:
        if (v.get("is_verified_diner") and v.get("author_name")
                and v.get("trust_level") in ("mid", "high")):
            voices[v["restaurant_id"]].add(v["author_name"])
    return voices


def awards_by_rid():
    A = C.fetch_all("restaurant_awards",
                    "restaurant_id,award_type,is_current")
    m = defaultdict(set)
    for a in A:
        if a.get("is_current", True):
            m[a["restaurant_id"]].add(a["award_type"])
    return m


def build():
    R = C.fetch_all(
        "restaurants",
        "id,name,status,is_curated,chain_type,central_kitchen,premade_risk,"
        "price_avg,score_taste")
    voices, awards = voices_by_rid(), awards_by_rid()
    brief, negative, backlog = [], [], 0
    for d in R:
        rid = d["id"]
        nv = len(voices.get(rid, set()))
        if d["status"] != "active":
            continue
        if d.get("central_kitchen") == "确认" or d.get("premade_risk") == "高":
            negative.append({
                "id": rid, "name": d["name"], "chain_type": d.get("chain_type"),
                "central_kitchen": d.get("central_kitchen"),
                "premade_risk": d.get("premade_risk"),
                "reason": "中央厨房确认/预制高风险：不采证、不进精选"})
            continue
        aw = awards.get(rid, set())
        if nv >= MIN_VOICES:
            continue
        if d.get("is_curated"):
            tier, why = "P0", f"精选店仅 {nv} 独立食客声音，需采证捍卫精选"
        elif aw & HEADLINE:
            tier, why = "P1", f"在榜 {sorted(aw & HEADLINE)} 仅 {nv} 声音，采证定晋升"
        elif "other_list" in aw or (d.get("score_taste") or 0) >= 4:
            tier, why = "P2", f"有榜单/聚合口碑仅 {nv} 声音，补证"
        else:
            backlog += 1
            continue
        brief.append({"id": rid, "name": d["name"], "tier": tier,
                      "curated": bool(d.get("is_curated")),
                      "chain_type": d.get("chain_type"), "awards": sorted(aw),
                      "voices": nv, "target": TARGET_VOICES,
                      "price_avg": d.get("price_avg"), "reason": why})
    order = {"P0": 0, "P1": 1, "P2": 2}
    brief.sort(key=lambda b: (order[b["tier"]], b["voices"],
                              -(b["price_avg"] or 0), b["id"]))
    return brief, negative, backlog


def write_outputs(brief, negative, backlog):
    ATLAS.mkdir(parents=True, exist_ok=True)
    POST.mkdir(parents=True, exist_ok=True)
    (ATLAS / "apify_brief.json").write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "min_voices": MIN_VOICES, "target_voices": TARGET_VOICES,
                    "brief": brief}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    worth = [{"id": b["id"], "name": b["name"],
              "taste_evidence": b["voices"], "label": b["tier"]} for b in brief]
    (ATLAS / "worth_fill.json").write_text(
        json.dumps(worth, ensure_ascii=False, indent=1), encoding="utf-8")
    (POST / "negative_list.json").write_text(
        json.dumps({"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "negative": negative}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    cnt = Counter(b["tier"] for b in brief)
    lines = ["# Apify 采证 brief（gate 产出）",
             f"> 生成 {time.strftime('%Y-%m-%d %H:%M')}｜独立食客声音口径："
             f"verified diner 且 trust mid/high",
             f"- 付费目标 **{len(brief)}**：P0 {cnt['P0']}（捍卫精选）／"
             f"P1 {cnt['P1']}（榜单定晋升）／P2 {cnt['P2']}（苗头补证）",
             f"- 硬负面出清 **{len(negative)}**（中央厨房确认/高预制，不采证）",
             f"- 不付费 backlog {backlog}（0 声音、无榜单、非精选）",
             "", "## P0 精选捍卫名单",
             "| rid | 店名 | 现声音 | 连锁 | 理由 |", "|---|---|---|---|---|"]
    for b in brief:
        if b["tier"] == "P0":
            lines.append(f"| {b['id']} | {b['name']} | {b['voices']} | "
                         f"{b['chain_type']} | {b['reason']} |")
    lines += ["", "## P1 榜单核实名单",
              "| rid | 店名 | 现声音 | 榜单 |", "|---|---|---|---|"]
    for b in brief:
        if b["tier"] == "P1":
            lines.append(f"| {b['id']} | {b['name']} | {b['voices']} | "
                         f"{','.join(b['awards'])} |")
    lines += ["", "## 硬负面清单（出清）",
              "| rid | 店名 | 中央厨房 | 预制 |", "|---|---|---|---|"]
    for n in negative:
        lines.append(f"| {n['id']} | {n['name']} | {n['central_kitchen']} | "
                     f"{n['premade_risk']} |")
    (ATLAS / "apify_brief.md").write_text(
        "\n".join(lines), encoding="utf-8")
    return cnt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    brief, negative, backlog = build()
    cnt = write_outputs(brief, negative, backlog)
    print(f"付费目标 {len(brief)}：P0={cnt['P0']} P1={cnt['P1']} P2={cnt['P2']}")
    print(f"硬负面 {len(negative)}；不付费 backlog {backlog}")
    print("已写 apify_brief.json/md、worth_fill.json、negative_list.json")
    print("下一步：docker cp worth_fill.json 到主机 /home/ubuntu/food-apify-fill/")


if __name__ == "__main__":
    main()

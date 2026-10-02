#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest.py — 统一取证入口（采集器 → findings 的唯一通道）。

原则：
- 所有采集器只调用 append_finding() 把证据追加进 findings.jsonl，
  绝不再直接 PATCH/POST restaurants 事实列；
- 事实列由 gate_apply.py 统一仲裁后写库（采集→证据→门→库）。
- 同 (rid, field, 归一value) 幂等去重，重复证据不重复落盘。
"""
import json
import os
import pathlib
import re
import time

LEDGER = pathlib.Path(os.environ.get(
    "FINDINGS_LEDGER", "/app/data/post_record/findings.jsonl"))

_RE_URL = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.I)


def valid_source_url(u):
    """来源 URL 必须真实可定位（scheme+点分主机，无省略号/空白/截断）；
    空串允许（表示无来源），但给了就必须合法——宁空不假。"""
    if not u:
        return True
    if not isinstance(u, str) or not _RE_URL.match(u.strip()):
        return False
    if "..." in u or "…" in u or " " in u:
        return False
    host = u.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return ("." in host) and host[-1].isalnum()


def _key(rid, field, value, source_url=""):
    # 幂等粒度 = 一条证据 = 同一来源(source)对同一(rid,field)提出同一 value；
    # 必须含 source_url，否则同一结论的【第二条独立来源】会被误判重复丢弃，
    # 使硬结论永远凑不齐 n_ind≥2（曾导致新 claim 永久卡 reverify）。
    return json.dumps([rid, field, value, (source_url or "").strip()],
                      ensure_ascii=False, sort_keys=True)


def append_finding(rid, field, value, confidence, reason,
                   source_url="", source_platform="", ledger=None):
    """追加一条证据；已存在同 rid+field+value 返回 False，否则写入返回 True。
    来源 URL 非法（杜撰/残缺）一律拒收。"""
    if not valid_source_url(source_url):
        return False
    lp = pathlib.Path(ledger) if ledger else LEDGER
    rec = {"restaurant_id": int(rid), "field": field, "value": value,
           "confidence": float(confidence), "reason": reason,
           "source_url": source_url or "", "source_platform": source_platform or "",
           "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    key = _key(rec["restaurant_id"], rec["field"], rec["value"],
               rec.get("source_url"))
    if lp.exists():
        for line in lp.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if _key(d.get("restaurant_id"), d.get("field"), d.get("value"),
                    d.get("source_url")) == key:
                return False
    lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def supersede(rid, fields, platform="production_probe", ledger=None):
    """用更新一轮的取证【取代】该 rid 在指定 fields 上、来自 platform 的旧证据：
    从账本物理移除匹配行（新证据更强/可溯源，旧弱证据不应再参与裁决）。
    platform=None 表示不限来源。返回移除行数。"""
    lp = pathlib.Path(ledger) if ledger else LEDGER
    if not lp.exists():
        return 0
    kept, dropped = [], 0
    for line in lp.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            kept.append(line)
            continue
        if d.get("restaurant_id") == int(rid) and d.get("field") in fields and \
           (platform is None or d.get("source_platform") == platform):
            dropped += 1
            continue
        kept.append(line)
    tmp = lp.with_name(lp.name + ".tmp")
    body = "\n".join(kept)
    tmp.write_text(body + ("\n" if body else ""), encoding="utf-8")
    os.replace(tmp, lp)
    return dropped


def append_many(rows, ledger=None):
    """批量 append；rows 为 dict 列表（含 rid/field/value/confidence/reason/source_*）。"""
    n = 0
    for r in rows:
        if append_finding(
                r["rid"], r["field"], r["value"], r.get("confidence", 0.8),
                r.get("reason", ""), r.get("source_url", ""),
                r.get("source_platform", ""), ledger=ledger):
            n += 1
    return n

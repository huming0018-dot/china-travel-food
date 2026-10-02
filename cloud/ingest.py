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
import time

LEDGER = pathlib.Path(os.environ.get(
    "FINDINGS_LEDGER", "/app/data/post_record/findings.jsonl"))


def _key(rid, field, value, source_url=""):
    # 幂等粒度 = 一条证据 = 同一来源(source)对同一(rid,field)提出同一 value；
    # 必须含 source_url，否则同一结论的【第二条独立来源】会被误判重复丢弃，
    # 使硬结论永远凑不齐 n_ind≥2（曾导致新 claim 永久卡 reverify）。
    return json.dumps([rid, field, value, (source_url or "").strip()],
                      ensure_ascii=False, sort_keys=True)


def append_finding(rid, field, value, confidence, reason,
                   source_url="", source_platform="", ledger=None):
    """追加一条证据；已存在同 rid+field+value 返回 False，否则写入返回 True。"""
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

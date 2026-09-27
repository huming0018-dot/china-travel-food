#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""unmatched_bridge.py — 把 run_batch 阶段「锚不入库」的小红书笔记回收进开放式发现管线。

补齐的断点：
  xhs_to_reviews.py 对「锚不到单一库内店」的笔记写 unmatched_shops.jsonl 后，原本没有任何
 下游。本桥把这些笔记（库内无此店 / 合集）按 admission_gate 可消费的 raw_discovery 格式
 重新喂回发现池：

    unmatched_shops.jsonl（xhs_to_reviews 产出）
      → 从 raw_xhs.jsonl 按 note_url 找回完整笔记（正文+评论）
      → 推断品类（优先按 search_name 在库菜系反查 CUISINE_ROOT；兜底按正文品类词）
      → 去重（note_url 状态文件）后追加进 /app/data/discovery/raw_discovery.jsonl
      → 对有新证据的品类：admission_gate 离线裁决 → candidate_apply 自动收录

为什么「合集」也要回收：xhs_to_reviews 因合集多店不锚单一店而丢弃，但 admission_gate
的结构化锚点解析（- 店名：/ 📍 / 店名丨 / 编号 店名）正是为合集设计的，合集是新店信号富矿。
「分店冲突」(mall 冲突) 歧义太大，不回收。

幂等：按 note_url 去重（unmatched_ingested.json）；gate 重算聚合、apply 按 name+address 回查。
容器内：cloud=/app/cloud，pipeline=/app/pipeline，data=/app/data。
"""
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C            # noqa: E402
import discovery_keywords as K  # noqa: E402

XHS_DIR = pathlib.Path(DATA) / "research/atlas/xhs"
UNMATCHED = XHS_DIR / "unmatched_shops.jsonl"
RAW_XHS = XHS_DIR / "raw_xhs.jsonl"
DISC_DIR = pathlib.Path(DATA) / "discovery"
RAW_DISC = DISC_DIR / "raw_discovery.jsonl"
INGESTED = DISC_DIR / "unmatched_ingested.json"

# 回收哪些 reason：库内无此店（单店笔记讲的是未知店）+ 合集（多店锚点富矿）。
# 排除 分店冲突:*（商场歧义，锁错店风险高）。
def _want_reason(reason):
    r = reason or ""
    return r == "库内无此店" or r == "合集"


def load_note_index():
    """note_url -> 完整 note 对象（含 desc/comments）。"""
    idx = {}
    if not RAW_XHS.exists():
        return idx
    for line in RAW_XHS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        for n in rec.get("notes", []):
            u = n.get("url")
            if u:
                idx[u] = n
    return idx


def build_name_to_categories():
    """search_name(库内店) → 它归属的品类 key 集合（反查 CUISINE_ROOT）。"""
    rests = C.fetch_all("restaurants", "id,name", order_col="id")
    cuis = C.fetch_all("cuisines", "id,name,parent_category", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id",
                     order_col="restaurant_id")
    by_id = {c["id"]: c for c in cuis}
    root2cat = {v: k for k, v in K.CUISINE_ROOT.items()}

    def root_of(cid):
        seen = set()
        while cid and cid not in seen:
            seen.add(cid)
            c = by_id.get(cid)
            if not c:
                return None
            if c.get("parent_category") is None:
                return c.get("name")
            cid = c["parent_category"]
        return None

    rid_cats = defaultdict(set)
    for x in rc:
        rn = root_of(x["cuisine_id"])
        if rn in root2cat:
            rid_cats[x["restaurant_id"]].add(root2cat[rn])
    # 归一店名 → 品类集合（含去分店主干）
    name2cats = {}
    for r in rests:
        cats = rid_cats.get(r["id"], set())
        if not cats:
            continue
        for form in (r["name"], re.split(r"[（(]", r["name"])[0].strip()):
            na = C.cjk_norm(form)
            if na:
                name2cats.setdefault(na, set()).update(cats)
    return name2cats


# 兜底：正文品类词命中 → 品类 key
def guess_category_from_text(text):
    t = text or ""
    best, best_n = None, 0
    for cat, spec in K.CATEGORY_SPEC.items():
        n = 0
        for w in (spec.get("names", []) + spec.get("subs", [])):
            if len(w) >= 2 and w in t:
                n += 1
        if n > best_n:
            best, best_n = cat, n
    return best if best_n >= 1 else None


def infer_category(search_name, note, name2cats):
    # 1) 按 search_name 在库菜系
    na = C.cjk_norm(search_name)
    if na in name2cats:
        cats = name2cats[na]
        if cats:
            return sorted(cats)[0]
    # 2) 去分店主干再试
    stem = C.cjk_norm(re.split(r"[（(]", search_name or "")[0])
    if stem in name2cats and name2cats[stem]:
        return sorted(name2cats[stem])[0]
    # 3) 正文品类词
    blob = (note.get("title", "") or "") + " " + (note.get("desc", "") or "")
    return guess_category_from_text(blob)


def load_ingested():
    if INGESTED.exists():
        try:
            return set(json.loads(INGESTED.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return set()
    return set()


def save_ingested(s):
    DISC_DIR.mkdir(parents=True, exist_ok=True)
    INGESTED.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")


def main():
    if not UNMATCHED.exists():
        print(f"无 {UNMATCHED}，跳过。")
        return 0

    entries = []
    for line in UNMATCHED.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _want_reason(e.get("reason", "")):
            entries.append(e)
    print(f"unmatched 共 {len(entries)} 条待回收（库内无此店/合集）。")

    notes_idx = load_note_index()
    name2cats = build_name_to_categories()
    ingested = load_ingested()

    by_cat = defaultdict(list)   # category -> list of note objects
    recovered, missing, skipped_no_evidence, already = 0, 0, 0, 0
    for e in entries:
        url = e.get("note_url")
        if not url:
            continue
        if url in ingested:
            already += 1
            continue
        note = notes_idx.get(url)
        if not note:
            missing += 1
            continue
        # 无正文无评论 = 无证据，gate 也提不出锚点
        if not (note.get("desc") or "").strip() and not note.get("comments"):
            skipped_no_evidence += 1
            ingested.add(url)   # 标记掉，不再重试
            continue
        cat = infer_category(e.get("search_name", ""), note, name2cats)
        if not cat:
            ingested.add(url)   # 推断不出品类，不强喂（宁空不假）
            continue
        by_cat[cat].append(note)
        ingested.add(url)
        recovered += 1

    # 追加进共享 raw_discovery.jsonl（与 cloud_discover 证据池合并）
    new_records = 0
    if by_cat:
        DISC_DIR.mkdir(parents=True, exist_ok=True)
        with RAW_DISC.open("a", encoding="utf-8") as f:
            for cat, notes in by_cat.items():
                # 按 search_name 归并成一次 discover 记录；note 原样保留
                f.write(json.dumps({"kind": "discover", "category": cat,
                                    "query": "unmatched-bridge", "city": "上海",
                                    "notes": notes}, ensure_ascii=False) + "\n")
                new_records += 1
                print(f"  喂入 {cat}: {len(notes)} 篇笔记")

    save_ingested(ingested)
    print(f"回收 {recovered} 篇（missing={missing} 无正文={skipped_no_evidence} 已处理={already}）；"
          f"新增 {new_records} 条品类记录。")

    # 对有新证据的品类跑 gate → apply（失败不阻断整体）
    for cat in sorted(by_cat):
        print(f"\n=== admission_gate: {cat} ===")
        r = subprocess.run([sys.executable, f"{PIPE}/admission_gate.py",
                            "--raw", str(RAW_DISC), "--category", cat])
        if r.returncode != 0:
            print(f"  gate {cat} 失败 rc={r.returncode}")
            continue
        print(f"=== candidate_apply: {cat} ===")
        subprocess.run([sys.executable, str(HERE / "candidate_apply.py"),
                        "--category", cat, "--commit"])

    return 0


if __name__ == "__main__":
    sys.exit(main())

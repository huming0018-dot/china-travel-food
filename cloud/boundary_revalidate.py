#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boundary_revalidate.py — 跑题/边界笔记的再验证与线索回收（#38）

输入：DATA/boundary_notes.jsonl（review_apify_fill 在搜索返回"非目标店但有食物实质"笔记时落盘）
处理（用户指示：不直接淘汰，进候选池再验证）：
  ① 确定性他店改投：anchor_note 已识别"唯一主角"为库内他店 other_rid，且正文有口味信号
     → 直接作为该他店的真实食客评价入库（不经过 LLM、不张冠李戴给搜索目标）。
  ② LLM 新店线索：未匹配到库内任何店的边界笔记，批量交【已授权免费】模型判定
     recover（实为目标店异名）/ lead（某家不在库的上海餐厅，给店名+区域）/ drop（无具体店）。
     lead 按店名聚合：≥2 次、或 1 次且带可定位区域 → boundary_leads.jsonl，交 discovery/frontier。
  ③ 幂等：processed url 记 boundary_state.json，重复跑不重复写。

用法：python3 boundary_revalidate.py [--apply]（默认 dry-run 只统计）
"""
import collections
import json
import os
import pathlib
import re
import sys
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR") or (HERE / "vendor" / "pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR") or HERE)
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import common as C          # noqa: E402
import entity_match as EM   # noqa: E402

BOUNDARY = DATA / "boundary_notes.jsonl"
LEADS = DATA / "boundary_leads.jsonl"
RECOVER = DATA / "boundary_recover.jsonl"
STATE_F = DATA / "boundary_state.json"

# 已授权（协作奖励计划、返免费包）模型，优先 glm-5.2；故障回落 flash
LLM_MODELS = ["glm-5-2-260617", "deepseek-v4-flash-ga-260731"]
BATCH_N = 8


def _load_state():
    if STATE_F.exists():
        st = json.loads(STATE_F.read_text(encoding="utf-8"))
    else:
        st = {}
    st.setdefault("processed", [])
    return st


def _read_jsonl(p):
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ---------------------------------------------------------------- LLM
def ark_chat(messages):
    base = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    key = os.environ.get("ARK_API_KEY")
    if not key:
        raise RuntimeError("ARK_API_KEY 未配置")
    last = None
    for model in LLM_MODELS:
        try:
            r = requests.post(base.rstrip("/") + "/chat/completions",
                              headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json"},
                              json={"model": model, "messages": messages,
                                    "temperature": 0.1, "max_tokens": 1400},
                              timeout=90)
            if r.status_code != 200:
                last = f"{model}: HTTP {r.status_code} {r.text[:120]}"
                continue
            return r.json()["choices"][0]["message"].get("content") or ""
        except requests.RequestException as e:
            last = f"{model}: {e}"
    raise RuntimeError("LLM 全部失败: " + str(last))


def classify_batch(entries):
    lines = []
    for i, e in enumerate(entries):
        txt = (e.get("title", "") + "。" + e.get("desc", "")).replace("\n", " ")[:260]
        lines.append(f"[{i}] 搜索目标《{e.get('target_name')}》 笔记：{txt}")
    prompt = (
        "你是上海美食图鉴的去软广审核员。下面是按某餐厅搜索、却没匹配到该餐厅的小红书笔记。"
        "逐条判断它真正在讲哪家【上海】餐厅，只输出 JSON 数组，不要解释：\n"
        '[{"i":序号,"v":"recover|lead|drop","shop":"店名(无则空)","area":"商圈/路(无则空)"}]\n'
        "- recover：其实在讲搜索目标《该条标注的目标名》，只是别称/写法不同。\n"
        "- lead：在讲某家具体的、与搜索目标不同的上海餐厅，shop 填它的准确店名。\n"
        "- drop：没有具体餐厅、纯打卡/提问/非餐饮/通稿。\n"
        "宁空不假，看不出具体店名就 drop。\n\n" + "\n".join(lines))
    content = ark_chat([{"role": "user", "content": prompt}])
    m = re.search(r"\[.*\]", content, re.S)
    if not m:
        return {}
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return {}
    return {int(a["i"]): a for a in arr if "i" in a and "v" in a}


# ---------------------------------------------------------------- 他店改投
def reroute_to_other(e, apply):
    rid = e.get("other_rid")
    body = EM.clean_content(e.get("desc", ""))
    if len(body) < 8 or not C.quote_has_substance(body):
        return None, "无实物"
    score, raw = EM.taste_sent(body)
    if score is None:
        return None, "无口味"
    url = e.get("url")
    rev = {"restaurant_id": rid, "author_name": "",
           "source_platform": "小红书", "source_url": url, "content": body,
           "review_kind": "diner", "is_verified_diner": True,
           "trust_level": "mid", "aspect_taste": score,
           "aspect_json": {"via": "boundary-reroute", "taste_raw": raw,
                           "from_search": e.get("target_name")}}
    if apply:
        r = C.req("POST", "/reviews", json=rev)
        if r.status_code not in (200, 201):
            return None, f"HTTP {r.status_code}"
    return ("reroute:" + str(rid)), None


def append_jsonl(p, rec):
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- main
def main():
    apply = "--apply" in sys.argv
    entries = _read_jsonl(BOUNDARY)
    st = _load_state()
    done = set(st["processed"])
    todo = [e for e in entries if e.get("url") and e["url"] not in done]

    n_reroute, n_llm = 0, 0
    llm_entries = []
    for e in todo:
        if e.get("other_rid"):
            tag, err = reroute_to_other(e, apply)
            if tag:
                n_reroute += 1
                print(f"  改投 {e['url']} → {tag}")
            done.add(e["url"])
        else:
            llm_entries.append(e)

    # LLM 批量
    verdicts = {}
    for k in range(0, len(llm_entries), BATCH_N):
        batch = llm_entries[k:k + BATCH_N]
        try:
            res = classify_batch(batch)
        except RuntimeError as ex:
            print("  [LLM 暂停]", ex)
            break
        for i, a in res.items():
            verdicts[batch[i]["url"]] = (batch[i], a)
        time.sleep(1.0)

    # 聚合 lead
    lead_acc = collections.defaultdict(lambda: {"areas": set(), "n": 0, "urls": []})
    n_recover, n_drop = 0, 0
    for url, (e, a) in verdicts.items():
        v = a.get("v")
        if v == "recover":
            n_recover += 1
            if apply:
                append_jsonl(RECOVER, {"target_rid": e.get("target_rid"),
                                       "target_name": e.get("target_name"),
                                       "url": url, "desc": e.get("desc", "")[:800]})
        elif v == "lead" and a.get("shop"):
            key = C.cjk_norm(a["shop"])
            if key:
                acc = lead_acc[key]
                acc["n"] += 1
                acc["name"] = a["shop"]
                if a.get("area"):
                    acc["areas"].add(a["area"])
                acc["urls"].append(url)
        else:
            n_drop += 1
        done.add(url)
    # 未被 LLM 处理（中断）的 url 不标 done，下次续跑
    for e in llm_entries:
        if e["url"] not in verdicts and e.get("other_rid") is None:
            done.discard(e["url"])

    n_new_leads = 0
    existing = {C.cjk_norm(x.get("name", "")) for x in _read_jsonl(LEADS)}
    for key, acc in lead_acc.items():
        strong = acc["n"] >= 2 or bool(acc["areas"])
        if not strong:
            continue
        if key in existing:
            continue
        n_new_leads += 1
        if apply:
            append_jsonl(LEADS, {"name": acc["name"], "area": sorted(acc["areas"]),
                                 "count": acc["n"], "sample_urls": acc["urls"][:3],
                                 "source": "boundary", "ts": C.today()})

    if apply:
        st["processed"] = sorted(done)
        STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n=== boundary 再验证（{'APPLY' if apply else 'DRY-RUN'}）===")
    print(f"  待处理 {len(todo)}；他店改投 {n_reroute}；recover {n_recover}；"
          f"drop {n_drop}；新增 lead 候选 {n_new_leads}")
    print(f"  LLM 批次覆盖 {len(verdicts)}/{len(llm_entries)}"
          + ("" if apply else "（dry-run 不落盘）"))


if __name__ == "__main__":
    main()

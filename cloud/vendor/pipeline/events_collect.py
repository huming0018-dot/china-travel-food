#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""events_collect.py — 「最新动向」Social Listening 采集器（小红书登录态，真实坐标点击，单浏览器串行，断点续跑）。

在 mac_computer_use_tool(plane="bu") 的 cell 内调用：
    import sys; sys.path.insert(0, PIPE)
    import events_collect as E
    E.run_sweep(bu, CONFIG, RAW, roots_per_cat=2, notes_per_query=4, max_queries=12)   # 发现未知
    E.run_watch(bu, RAW, names=[...], notes_per_name=3)                                # 已知店保鲜

两种模式：
  sweep —— 按「{事件词根} 上海」搜索，发现【未知】的新店/首店/快闪/联名/飞行/搬迁/闭店。
  watch —— 按店名搜索，对【已知重点店】做状态保鲜（是否搬迁/闭店/换主厨由转换器按词根判定）。

铁律（同 xhs，教训 #54）：必须真实坐标点击让 URL 带 xsec_token，禁 JS click；单浏览器串行、不开并行。
本模块只做机械采集，"是否为实质事件 / 归到哪家 / 置信度"交给 events_build.py。
"""
import json
import pathlib
import sys

try:
    import xhs_collect as X
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import xhs_collect as X


def load_config(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _append(path, rec):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def done_keys(path, field):
    """已采集 query / watch_name 集合（断点续跑）。"""
    s = set()
    p = pathlib.Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                s.add(json.loads(line).get(field))
            except Exception:
                pass
    return s


def _gather(bu, keyword, max_notes, city="上海"):
    """搜一个关键词（xhs_collect.search 会自动拼 city），打开前 max_notes 篇。"""
    X.search(bu, keyword, city)
    positions = X.note_positions(bu, limit=max_notes + 3)
    out = []
    for p in positions:
        if len(out) >= max_notes:
            break
        info = X.open_note(bu, p["x"], p["y"])
        if not info.get("ok"):
            continue
        comments = X.scroll_and_get_comments(bu)
        X.close_note(bu)
        out.append({"title": info["title"], "author": info["author"], "date": info["date"],
                    "desc": info["desc"], "url": info["url"], "comments": comments})
    return out


def run_sweep(bu, config_path, raw_path, roots_per_cat=2, notes_per_query=4,
              max_queries=12, categories=None, city="上海"):
    """模式 B：按事件词根地毯搜索，发现未知新动向。返回实际跑的 query。"""
    cfg = load_config(config_path)
    cats = set(categories or cfg["categories"].keys())
    done = done_keys(raw_path, "query")
    queries = []
    for cat in cfg["category_priority"]:
        if cat not in cats:
            continue
        cobj = cfg["categories"][cat]
        words = cobj.get("sweep") or cobj["roots"]  # sweep 词已含餐饮语境，优先
        for sw in words[:roots_per_cat]:
            q = f"{sw} {city}"
            if q not in done:
                queries.append((cat, sw, q))
    queries = queries[:max_queries]
    ran = []
    for cat, sw, q in queries:
        notes = _gather(bu, sw, notes_per_query, city)
        _append(raw_path, {"kind": "sweep", "query": q, "category_hint": cat, "notes": notes})
        ran.append(q)
    return {"ran": len(ran), "queries": ran}


def run_watch(bu, raw_path, names, notes_per_name=3, city="上海"):
    """模式 A：按店名巡检已知重点店（状态保鲜）。"""
    done = done_keys(raw_path, "watch_name")
    todo = [n for n in names if n and n not in done]
    ran = []
    for name in todo:
        notes = _gather(bu, name, notes_per_name, city)
        _append(raw_path, {"kind": "watch", "watch_name": name, "notes": notes})
        ran.append(name)
    return {"ran": len(ran), "names": ran}


def run_batch(bu, config_path, raw_path, max_queries=8, roots_per_cat=1,
              notes_per_query=3, commit=False, categories=None, city="上海"):
    """定时任务单批一键编排：sweep 采集一批 → events_build 转换 → atlas_write 入库。
    在 plane=bu cell 内调用（采集需浏览器）；build/write 为纯 python，subprocess 串行。
    commit=False 仅预演；True 则幂等写库（rumor/verified 都写，feed_view 只显示 verified）。"""
    import subprocess
    pipe_dir = str(pathlib.Path(__file__).parent)
    sweep_res = run_sweep(bu, config_path, raw_path, roots_per_cat=roots_per_cat,
                          notes_per_query=notes_per_query, max_queries=max_queries,
                          categories=categories, city=city)
    b = subprocess.run([sys.executable, "events_build.py"], cwd=pipe_dir,
                       capture_output=True, text=True)
    out_events = str(pathlib.Path(raw_path).with_name("raw_events.jsonl"))
    cmd = [sys.executable, "atlas_write.py", "--domain", "events", "--input", out_events]
    if commit:
        cmd.append("--commit")
    w = subprocess.run(cmd, cwd=pipe_dir, capture_output=True, text=True)
    return {"sweep": sweep_res,
            "build": [l for l in (b.stdout or b.stderr).splitlines() if l][:2],
            "write": [l for l in (w.stdout or w.stderr).splitlines() if l][-2:]}


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""work_progress.py — 开发侧「工作进度」状态（agent 维护，progress_broadcast 读取并播报）。

为什么存在：服务器 cron 的播报只能读管线状态，看不到 agent 当前在做什么、完成了哪些里程碑。
本模块把开发进度落到 /app/data/work_progress.json，agent 每完成/接手一项就更新，
播报据此展示「阶段 / 最新提交 / 最近完成 / 正在做 / 下一步」。

CLI（容器内，env 已加载）：
  python work_progress.py --phase "P1 覆盖分母"
  python work_progress.py --doing "跑地图 POI 计数"
  python work_progress.py --done "账本引入 target_n"
  python work_progress.py --next "POI计数|集团主厨树"
  python work_progress.py --commit   # 自动回填最新 git 提交（若容器无 .git 则跳过）
"""
import argparse
import datetime
import json
import os
import pathlib
import subprocess

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
F = DATA / "work_progress.json"
KEEP_DONE = 8


def now():
    return datetime.datetime.now().strftime("%m-%d %H:%M")


def blank():
    return {"phase": "", "goal": "", "updated_at": "", "latest_commit": "",
            "in_progress": "", "next": [], "done": []}


def load():
    try:
        st = json.loads(F.read_text(encoding="utf-8"))
        return {**blank(), **st}
    except Exception:
        return blank()


def save(st):
    st["updated_at"] = now()
    F.parent.mkdir(parents=True, exist_ok=True)
    F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def add_done(st, item):
    st["done"].insert(0, {"ts": now(), "item": item})
    st["done"] = st["done"][:KEEP_DONE]
    st["in_progress"] = ""


def detect_commit(st):
    """容器若挂了源码 .git 则取最新提交，否则保留原值。"""
    for repo in ("/app", "/app/cloud"):
        try:
            h = subprocess.run(["git", "-C", repo, "log", "-1",
                                "--pretty=%h %s"], capture_output=True, text=True, timeout=8)
            if h.returncode == 0 and h.stdout.strip():
                st["latest_commit"] = h.stdout.strip()[:80]
                return
        except Exception:
            continue


def render_text():
    st = load()
    lines = ["— 开发进度 —", f"阶段：{st['phase'] or '—'}"]
    if st.get("latest_commit"):
        lines.append(f"最新提交：{st['latest_commit']}")
    if st.get("done"):
        lines.append("最近完成：")
        for d in st["done"][:4]:
            lines.append(f"  · {d['item']}（{d['ts']}）")
    if st.get("in_progress"):
        lines.append(f"正在做：{st['in_progress']}")
    if st.get("next"):
        lines.append("下一步：" + "；".join(st["next"]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="")
    ap.add_argument("--goal", default="")
    ap.add_argument("--doing", default="")
    ap.add_argument("--done", default="")
    ap.add_argument("--next", default="")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    st = load()
    if args.phase:
        st["phase"] = args.phase
    if args.goal:
        st["goal"] = args.goal
    if args.doing:
        st["in_progress"] = args.doing
    if args.done:
        add_done(st, args.done)
    if args.next:
        st["next"] = [s for s in args.next.split("|") if s]
    if args.commit:
        detect_commit(st)
    save(st)
    print(render_text())


if __name__ == "__main__":
    main()

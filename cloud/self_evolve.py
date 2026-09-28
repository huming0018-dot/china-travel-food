#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_evolve.py — 每日 01:00 自我进化（只读复盘，绝不自动改数据）。

铁律（无人值守任务）：
  - 只报告、不自动改：不发任何 PATCH/POST/DELETE，不跑 --commit；只读 GET 与只读扫描。
  - 确定性、可复跑：同日重复跑只覆盖当天报告，不产生副作用。
  - 产出：/app/data/self_evolve/YYYY-MM-DD.md；经 notifier 推一条精简结论
    （常态 INFO；出现 ERROR/需人工处理才 ACTION）到 Telegram+飞书。

复盘内容（对齐北极星宪法 A6 闭环自检 与 release-regression-loop A–H）：
  1. 当日代码改动概览（/app/cloud 下今日 mtime 的 .py，按修改时间列）；
  2. 当日数据概览（Supabase 只读计数：库总量/营业/已补电话/已补坐标/评价数）；
  3. 通识 A–G 只读扫描（release_audit.py，绝不 --commit）；
  4. 结论汇总：PASS / CHECK / ERROR 计数与需人工关注的要点。
"""
import datetime
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path("/app/pipeline")
DATA = pathlib.Path("/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import common as C          # noqa: E402
import notifier             # noqa: E402
import requests             # noqa: E402

REPORT_DIR = DATA / "self_evolve"
PY = sys.executable


def today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _get_count(path):
    """只读 GET 取总数（Prefer count=exact + Range 0-0，不拉全表）。
    直接用 requests 合并 C.headers()，避免 C.req 自带 headers 冲突。"""
    try:
        h = {**C.headers(), "Prefer": "count=exact", "Range": "0-0"}
        r = requests.get(C.BASE + path, headers=h, timeout=30)
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            return int(cr.split("/")[-1])
        j = r.json()
        return len(j) if isinstance(j, list) else None
    except Exception as e:
        return f"err:{e}"


def section_code_changes():
    """当日 /app/cloud 下被修改的 .py（按 mtime）。"""
    today = datetime.datetime.now().date()
    rows = []
    for p in sorted(HERE.glob("*.py"), key=lambda x: x.stat().st_mtime):
        try:
            mt = datetime.datetime.fromtimestamp(p.stat().st_mtime)
        except Exception:
            continue
        if mt.date() == today:
            rows.append(f"  {mt.strftime('%H:%M')}  {p.name}")
    if not rows:
        return "  （今日 /app/cloud 无 .py 改动）"
    return "\n".join(rows)


def section_data():
    q = {
        "库总量": "/restaurants?select=id",
        "营业中": "/restaurants?select=id&status=eq.active",
        "已补电话": "/restaurants?select=id&status=eq.active&phone=not.is.null",
        "已补坐标": "/restaurants?select=id&status=eq.active&location=not.is.null",
        "待补电话": "/restaurants?select=id&status=eq.active&phone=is.null",
        "评价数": "/reviews?select=id",
    }
    lines = []
    for label, path in q.items():
        lines.append(f"  {label}: {_get_count(path)}")
    return "\n".join(lines)


def section_release_audit():
    """跑 release_audit.py（只读），返回 (状态表文本, 有无线程错误)。"""
    audit = PIPE / "release_audit.py"
    if not audit.exists():
        return "  SKIP：release_audit.py 不存在", False
    try:
        p = subprocess.run([PY, str(audit)], capture_output=True, text=True,
                           timeout=900, cwd=str(PIPE))
    except subprocess.TimeoutExpired:
        return "  ERROR：release_audit 超时(>900s)", True
    out = (p.stdout or "") + (p.stderr or "")
    low = out.lower()
    has_err = ("traceback" in low) or ("exception" in low)
    tail = "\n".join(out.strip().splitlines()[-25:])
    return tail or "  (无输出)", has_err


def main():
    d = today_str()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"{d}.md"

    code = section_code_changes()
    data = section_data()
    audit_tail, audit_err = section_release_audit()

    n_err = audit_tail.count("ERROR") if isinstance(audit_tail, str) else 0
    body = f"""# 自我进化日报 {d}

## 1) 当日代码改动（/app/cloud/*.py）
{code}

## 2) 当日数据概览（Supabase 只读计数）
{data}

## 3) 通识 A–G 只读扫描（release_audit，未 --commit）
{audit_tail}

## 4) 结论
  - 只读扫描异常：{'有，需人工看' if audit_err else '无 traceback/exception'}
  - 本报告由 cron 01:00 自动生成，仅复盘、未改动任何数据。
"""
    report.write_text(body, encoding="utf-8")

    # 精简结论推送到 TG+飞书
    head = f"自我进化日报 {d}"
    if audit_err:
        msg = (f"{head}\n只读扫描出现异常/堆栈，需人工查看：\n"
               f"{audit_tail[-400:]}")
        notifier.action(msg, key=f"self_evolve:{d}",
                        action_text="打开 /app/data/self_evolve/"
                                    f"{d}.md 定位 ERROR，按 A–H 闭环修复机制")
    else:
        msg = (f"{head}\n只读扫描无异常；数据概览已落盘 "
               f"/app/data/self_evolve/{d}.md。")
        notifier.info(msg, key=f"self_evolve:{d}", cadence=0)
    print(f"[self_evolve] 报告已写: {report}")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())

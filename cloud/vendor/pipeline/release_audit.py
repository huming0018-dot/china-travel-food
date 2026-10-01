#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release_audit.py — 版本发布前的通识问题总扫描器（只读，绝不 --commit）。

依次运行各只读质量门（对应 release-regression-loop.md 的 A–G 类别），
捕获返回码与输出摘要，汇总成 research/release_audit_<date>.md。
前端 H 类需浏览器，不在本脚本内，按文档第二步单独回归。

用法：python3 release_audit.py
"""
import datetime
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _proj_root():
    """项目根（可移植，禁止硬编码单机路径）：FOOD_PROJECT 优先，其次按 repo 布局反推，再次 cwd。"""
    env = os.environ.get("FOOD_PROJECT")
    if env and pathlib.Path(env).exists():
        return pathlib.Path(env)
    for cand in (list(HERE.parents) + [pathlib.Path.cwd()]):
        if (cand / "research").exists() or (cand / "cloud").exists():
            return cand
    return HERE


PROJ = _proj_root()


def _auth_dir():
    env = os.environ.get("FOOD_AUTHORITY_DIR")
    if env:
        return pathlib.Path(env)
    for cand in (PROJ / "data" / "authority", PROJ / "research" / "authority"):
        if cand.exists():
            return cand
    return PROJ / "research" / "authority"


AUTH = _auth_dir()
PY = sys.executable

# (类别, 脚本, 参数, 说明)
CHECKS = [
    ("R 名称回归集", "regression_check.py", [], "点名店回归断言，必须 100% 命中，有 miss 返回1"),
    ("D 同址真重复", "duplicate_audit.py", [], "同址多店=真重复应合并，异址分店保留，有真重复返回1"),
    ("D/G 单店字段/硬伤", "stage4_audit.py", [], "全库只读体检，ERROR 应为 0"),
    ("A 网格覆盖", "stage6_coverage.py", ["--strict"], "空格/薄格/薄证据，strict 不达标返回1"),
    ("C 事实硬标签证据", "fact_evidence_gap.py", ["--strict"], "硬标签必须带同type带URL证据，缺口>0返回1"),
    ("E 跨菜系根", "cross_cuisine_audit.py", [], "dry-run，误挂根检查"),
    ("C 连锁/预制", "chain_audit.py", [], "dry-run，连锁/中央厨房/预制标注"),
    ("E 分类引擎", "cuisine_classify_audit.py", [], "dry-run，主营/地名陷阱/冲突"),
    ("D 实体对齐", "entity_align.py", [], "权威名单 high/medium/unmatched/need_review"),
    ("A 权威名单比对", "authority_compare.py", [], "米其林全量与库 hit/missing"),
    ("B 总分漂移", "stage5_recalc.py", [], "score_total 只读漂移检测"),
]


def child_env():
    env = dict(os.environ)
    env.setdefault("FOOD_PROJECT", str(PROJ))
    env.setdefault("FOOD_AUTHORITY_DIR", str(AUTH))
    return env


def run_one(script, args):
    path = HERE / script
    if not path.exists():
        return "SKIP", -1, "脚本不存在: " + script
    try:
        p = subprocess.run([PY, str(path)] + args, capture_output=True,
                           text=True, timeout=600, cwd=str(HERE), env=child_env())
    except subprocess.TimeoutExpired:
        return "ERROR", -2, "超时(>600s)"
    out = (p.stdout or "") + ("\n[stderr]\n" + p.stderr if p.stderr else "")
    tail = "\n".join(out.strip().splitlines()[-22:])
    low = out.lower()
    # traceback / exception = 真错误；"ERROR=0" 不算失败（解析计数，>0 才降级）；
    # WARN（如电话缺口）不算失败。
    if "traceback" in low or "exception" in low:
        status = "ERROR"
    else:
        err_nums = [int(m) for m in re.findall(r"error\s*[=:]\s*(\d+)", low)]
        if err_nums and max(err_nums) > 0:
            status = "CHECK"
        elif p.returncode == 0:
            status = "PASS"
        else:
            status = "CHECK"
    return status, p.returncode, tail


def main():
    today = datetime.date.today().isoformat()
    sections, counts = [], {"PASS": 0, "CHECK": 0, "ERROR": 0, "SKIP": 0}
    for label, script, args, note in CHECKS:
        status, code, tail = run_one(script, args)
        counts[status] += 1
        sections.append(
            f"### [{status}] {label} — `{script}` (return={code})\n"
            f"> {note}\n\n```\n{tail}\n```\n")
        print(f"{status:5} {label} ({script} return={code})")

    overall = "全绿，可进入前端回归 / 写库" if counts["ERROR"] == 0 and counts["CHECK"] == 0 \
        else "存在待查/错误，按 release-regression-loop 修复机制后重扫"
    md = (f"# 版本回归扫描报告 {today}\n\n"
          f"汇总：PASS={counts['PASS']} CHECK={counts['CHECK']} "
          f"ERROR={counts['ERROR']} SKIP={counts['SKIP']}\n\n"
          f"**结论：{overall}**\n\n"
          f"前端 H 类（导航/筛选/排序/详情地图/打卡）需 browser-use 单独回归。\n\n"
          + "\n".join(sections))

    out_dir = AUTH if (AUTH.exists() and "data" in AUTH.parts) else PROJ / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"release_audit_{today}.md"
    out_path.write_text(md, encoding="utf-8")
    print("\n", overall)
    print("报告:", out_path)


if __name__ == "__main__":
    main()

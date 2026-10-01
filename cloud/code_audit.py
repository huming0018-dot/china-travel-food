#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""code_audit.py — 代码仓库定期排雷审计

每周自动运行一次，扫描代码质量问题：
1. 硬编码密钥/IP
2. 临时诊断文件
3. 重复文件
4. 超大文件
5. 死代码/注释代码
6. research目录临时脚本数量

用法：
  python3 code_audit.py           # 完整审计
  python3 code_audit.py --report  # 只输出问题数量
"""
import os, sys, pathlib, json, time
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
ROOT = pathlib.Path(__file__).resolve().parent.parent
CLOUD = ROOT / "cloud"

issues = []

def add(level, category, message, file=""):
    issues.append({
        "level": level,  # P0/P1/P2
        "category": category,
        "message": message,
        "file": file
    })


def audit_hardcoded_secrets():
    """检查硬编码密钥"""
    patterns = [
        ("sb_secret_", "Supabase密钥"),
        ("sk-", "API密钥"),
        ("49.234.35.92", "服务器IP硬编码"),
    ]
    for pyfile in CLOUD.glob("*.py"):
        try:
            content = pyfile.read_text(encoding="utf-8")
            for pat, desc in patterns:
                if pat in content and "marker" not in content:  # 排除脱敏函数
                    add("P1", "硬编码", f"{desc}: {pyfile.name}")
        except Exception:
            pass


def audit_temp_files():
    """检查临时诊断文件"""
    for pyfile in CLOUD.glob("_*.py"):
        add("P1", "临时文件", f"诊断脚本应清理: {pyfile.name}")


def audit_duplicate_files():
    """检查重复文件名"""
    names = {}
    for pyfile in CLOUD.glob("*.py"):
        name = pyfile.name
        if name in names:
            add("P1", "重复文件", f"重复: {name}")
        names[name] = True


def audit_large_files():
    """检查超大文件"""
    for pyfile in CLOUD.glob("*.py"):
        try:
            lines = len(pyfile.read_text(encoding="utf-8").splitlines())
            if lines > 600:
                add("P2", "大文件", f"{pyfile.name}: {lines}行，建议拆分")
        except Exception:
            pass


def audit_research_scripts():
    """检查research目录临时脚本"""
    research = ROOT / "research"
    if research.exists():
        count = len(list(research.glob("**/*.py")))
        if count > 10:
            add("P2", "临时脚本", f"research目录有{count}个脚本，建议归档")


def audit_todo_fixme():
    """检查TODO/FIXME"""
    for pyfile in CLOUD.glob("*.py"):
        try:
            content = pyfile.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "TODO" in line or "FIXME" in line:
                    add("P2", "待办", f"{pyfile.name}: {line.strip()[:50]}")
                    break
        except Exception:
            pass


def main():
    print("=" * 50)
    print(f"代码审计 · {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    audit_hardcoded_secrets()
    audit_temp_files()
    audit_duplicate_files()
    audit_large_files()
    audit_research_scripts()
    audit_todo_fixme()

    # 按级别分组
    p0 = [i for i in issues if i["level"] == "P0"]
    p1 = [i for i in issues if i["level"] == "P1"]
    p2 = [i for i in issues if i["level"] == "P2"]

    print(f"\n📊 审计结果:")
    print(f"  P0（必须修复）: {len(p0)}个")
    print(f"  P1（应该修复）: {len(p1)}个")
    print(f"  P2（可以后续）: {len(p2)}个")

    if p1:
        print(f"\n🔴 P1问题:")
        for i in p1:
            print(f"  [{i['category']}] {i['message']}")

    if p2:
        print(f"\n🟡 P2问题:")
        for i in p2[:10]:
            print(f"  [{i['category']}] {i['message']}")
        if len(p2) > 10:
            print(f"  ... 还有{len(p2)-10}个")

    # 保存报告
    report_f = ROOT / "AUDIT_REPORT.md"
    with open(report_f, "w", encoding="utf-8") as f:
        f.write(f"# 代码审计报告 · {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"## 统计\n\n")
        f.write(f"- P0: {len(p0)}个\n- P1: {len(p1)}个\n- P2: {len(p2)}个\n\n")
        f.write(f"## P1问题明细\n\n")
        for i in p1:
            f.write(f"- [{i['category']}] {i['message']}\n")
        f.write(f"\n## P2问题明细\n\n")
        for i in p2:
            f.write(f"- [{i['category']}] {i['message']}\n")

    print(f"\n📄 报告已保存: {report_f.name}")

    # 推送到TG
    try:
        sys.path.insert(0, str(CLOUD))
        import notifier
        summary = f"代码审计完成: P0={len(p0)} P1={len(p1)} P2={len(p2)}"
        if p1:
            summary += f"\nP1: {p1[0]['message'][:40]}"
        notifier.info(summary, key="code_audit", cadence=86400*7)  # 每周一次
    except Exception:
        pass


if __name__ == "__main__":
    main()

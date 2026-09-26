#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_paths.py — 构建镜像时，把管线脚本里写死的本机绝对路径替换为容器路径。

管线脚本是在本机开发的，里面硬编码了项目根与管线目录的绝对路径。
云端不保留 /Users/hubowen 目录结构，故在镜像构建阶段做一次性、确定性的文本替换，
避免手工逐个改脚本，也不污染源码（替换只发生在容器内的副本上）。
"""
import pathlib

# 顺序：先替换更长、更具体的管线目录，再替换项目根，避免子串误伤
REPLACEMENTS = [
    ("/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/"
     "agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline",
     "/app/pipeline"),
    ("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food",
     "/app/data"),
]


def fix(root="/app/pipeline"):
    root = pathlib.Path(root)
    n = 0
    for f in root.rglob("*.py"):
        if f.name.startswith("._"):  # macOS AppleDouble 残留，不是源码
            continue
        try:
            s = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # 非 UTF-8 文本不做路径替换
            continue
        o = s
        for a, b in REPLACEMENTS:
            s = s.replace(a, b)
        if s != o:
            f.write_text(s, encoding="utf-8")
            print("patched:", f.relative_to(root))
            n += 1
    print(f"fix_paths 完成，修改 {n} 个文件")


if __name__ == "__main__":
    import sys
    fix(sys.argv[1] if len(sys.argv) > 1 else "/app/pipeline")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify_cli.py — 通用 stdin→notifier 分发器（让主机/控制器可经容器发送双通道通知）。

notifier.py 只暴露 Python 函数、没有命令行；本脚本补上 CLI：
  echo "正文" | python3 notify_cli.py <level> <key> [action_text]
    level: info / warn / action / resolve
    key:   去重/折叠键
    action_text: 仅 level=action 时使用（默认"去处理"）
正文从标准输入读取（可含换行/引号），避免命令行转义问题。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifier as N  # noqa: E402


def main():
    if len(sys.argv) < 3:
        print("usage: notify_cli.py <info|warn|action|resolve> <key> [action_text]",
              file=sys.stderr)
        return 2
    level, key = sys.argv[1], sys.argv[2]
    body = sys.stdin.read().strip()
    if not body:
        print("empty body", file=sys.stderr)
        return 2
    if level == "info":
        ok = N.info(body, key=key, cadence=0)          # 立即推
    elif level == "warn":
        ok = N.warn(body, key=key)
    elif level == "action":
        ok = N.action(body, key=key,
                      action_text=sys.argv[3] if len(sys.argv) > 3 else "去处理")
    elif level == "resolve":
        ok = N.resolve(body, key=key)
    else:
        print(f"unknown level {level}", file=sys.stderr)
        return 2
    print("delivered" if ok else "suppressed/failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

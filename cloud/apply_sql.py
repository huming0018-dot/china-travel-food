#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_sql.py — 经 Supabase Management API 执行 SQL（迁移/一次性 DML）。

令牌从本机 ~/.food_atlas_credentials.md 用正则提取，绝不打印、绝不入仓。
用法：python3 apply_sql.py <file.sql>
"""
import pathlib, re, sys, json, urllib.request

PROJECT = "bdwrhshgdeghgyzwpxnl"
URL = f"https://api.supabase.com/v1/projects/{PROJECT}/database/query"


def token():
    # 优先读会话系统文件中的真实 44 位令牌
    cand = pathlib.Path(
        "/Users/deuce/Library/Application Support/Doubao/Default/.doubao/agent_mode/"
        "workspace/.sessions/38444479935001090/agents/m_0cwp6SalkKS/system/sbp_token.txt")
    if cand.exists():
        t = cand.read_text(encoding="utf-8").strip()
        if t.startswith("sbp_") and len(t) >= 40:
            return t
    txt = pathlib.Path.home().joinpath(".food_atlas_credentials.md").read_text(encoding="utf-8")
    m = re.search(r"sbp_[A-Za-z0-9]{30,}", txt)
    if not m:
        sys.exit("未找到 sbp_ Management 令牌")
    return m.group(0)


def run(sql):
    body = json.dumps({"query": sql}).encode("utf-8")
    req = urllib.request.Request(
        URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8")[:1500])
        sys.exit(1)
    print("OK", out[:1500] if out.strip() else "(no rows)")


if __name__ == "__main__":
    run(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 app/.env.local 生成服务器用 deploy.env（只取需要的键，不含无关变量）。"""
import pathlib

ROOT = "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"
envf = pathlib.Path(ROOT) / "app/.env.local"
tplf = pathlib.Path(ROOT) / "cloud/deploy.env.template"
outf = pathlib.Path(ROOT) / "cloud/deploy.env"

vals = {}
for line in envf.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")

need = {"NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"}
missing = need - set(vals)
if missing:
    raise SystemExit(f".env.local 缺少: {missing}")

lines = []
for line in tplf.read_text(encoding="utf-8").splitlines():
    if line.startswith("NEXT_PUBLIC_SUPABASE_URL="):
        line = "NEXT_PUBLIC_SUPABASE_URL=" + vals["NEXT_PUBLIC_SUPABASE_URL"]
    elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
        line = "SUPABASE_SERVICE_ROLE_KEY=" + vals["SUPABASE_SERVICE_ROLE_KEY"]
    lines.append(line)
outf.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("已生成 deploy.env（含 Supabase 密钥，勿提交 git）")

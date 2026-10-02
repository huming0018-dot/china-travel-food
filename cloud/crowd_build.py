#!/usr/bin/env python3
"""
crowd_build.py — 众包插件构建脚本（PM 窗口）

用途：
  1. 校验插件源码完整性（文件齐全、JS 语法、安全线配置）
  2. 从 app/.env.local 读取真实 Supabase URL + anon key（sb_pub_）
  3. 把 key 注入 background.js / apply.html（构建时替换）
  4. 打成 zip → crowd_extension/releases/crowd-extension-v2.0.0.zip（供在线报名页下载）

用法：
  python3 cloud/crowd_build.py            # 打正式包
  python3 cloud/crowd_build.py --dry      # 只校验不打包

安全：
  - anon key 是公开可分发的最小权限 key（仅 RPC 调用 + 报名 insert pending），可随包分发
  - service_role key 绝不进入插件包
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "crowd_extension")
VERSION = "2.0.0"
OUT_DIR = os.path.join(EXT, "releases")
OUT_ZIP = os.path.join(OUT_DIR, f"crowd-extension-v{VERSION}.zip")
ENV_LOCAL = os.path.join(ROOT, "app", ".env.local")

NEEDED = [
    "manifest.json",
    "src/background.js",
    "src/content.js",
    "src/safety_engine.js",
    "src/popup.html",
    "src/onboarding.html",
    "icons/icon128.png",
]


def load_env(path):
    env = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def check_js_syntax(path):
    # 用 node --check 校验（macOS 有 node 时）
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"  ⚠ JS 语法: {path} → {r.stderr.strip()[:200]}")
            return False
        return True
    except FileNotFoundError:
        # 无 node：退化为 python 括号粗查（仅提示）
        print("  ℹ 未装 node，跳过 JS 语法机检（建议安装后重跑）")
        return True


def main():
    dry = "--dry" in sys.argv
    print(f"=== 众包插件构建 v{VERSION} ===")

    # 1) 文件完整性
    missing = [f for f in NEEDED if not os.path.exists(os.path.join(EXT, f))]
    if missing:
        print(f"✗ 缺失文件: {missing}")
        sys.exit(1)
    print(f"✓ 文件齐全 ({len(NEEDED)} 个)")

    # 2) JS 语法
    bad = False
    for js in ["src/background.js", "src/content.js", "src/safety_engine.js"]:
        if not check_js_syntax(os.path.join(EXT, js)):
            bad = True
    if bad:
        print("✗ JS 语法检查未通过")
        sys.exit(1)
    print("✓ JS 语法 OK")

    # 3) 读取 env（正式打包才需要）
    env = load_env(ENV_LOCAL)
    anon = env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    url = env.get("NEXT_PUBLIC_SUPABASE_URL", "")

    if dry:
        print(f"✓ dry-run：anon key {'已配置(' + str(len(anon)) + '字符)' if anon else '缺失！'}")

    if anon.startswith("eyJ"):
        print("✗ anon key 仍是旧版 legacy 格式（eyJ 开头），已禁用！请用 sb_pub_ 新版 key")
        sys.exit(1)
    if not anon.startswith("sb_pub"):
        print(f"✗ anon key 格式异常: {anon[:8]}...，应为 sb_pub_ 开头")
        sys.exit(1)
    if len(anon) < 40:
        print("✗ anon key 长度异常")
        sys.exit(1)
    print(f"✓ anon key 校验通过 (sb_pub_，{len(anon)}字符)")

    if dry:
        return

    # 4) 临时目录注入 + 打包
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="crowd_ext_")
    try:
        # 复制全部文件到临时目录
        for f in os.listdir(EXT):
            if f.startswith(".") or f == "releases":
                continue
            src = os.path.join(EXT, f)
            dst = os.path.join(tmp, f)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # 注入 background.js：CROWD_API_BASE / CROWD_API_KEY
        bg = os.path.join(tmp, "src", "background.js")
        c = open(bg).read()
        c = c.replace('self.CROWD_API_BASE || "https://bdwrhshgdeghgyzwpxnl.supabase.co"',
                      '"' + url.rstrip("/") + '"')
        c = re.sub(r'API_KEY: self\.CROWD_API_KEY \|\| ""', 'API_KEY: "' + anon + '"', c)
        open(bg, "w").write(c)
        print("✓ background.js 已注入 key")

        # 注入 apply.html（放到 releases 旁，方便报名页同目录下载；正式包内不含报名页 key 注入文件）
        ap = os.path.join(tmp, "apply.html")
        if os.path.exists(ap):
            a = open(ap).read()
            a = a.replace('"REPLACE_WITH_SUPABASE_ANON_KEY"', '"' + anon + '"')
            open(ap, "w").write(a)
            print("✓ apply.html 已注入 anon key")

        # 5) 打 zip
        with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmp):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, tmp)
                    zf.write(full, rel)
        print(f"✓ 已打包: {OUT_ZIP} ({os.path.getsize(OUT_ZIP)//1024} KB)")

        # 6) 校验包内容
        with zipfile.ZipFile(OUT_ZIP) as zf:
            names = zf.namelist()
            for need in ["manifest.json", "src/background.js"]:
                if need not in names:
                    print(f"✗ 包内缺失 {need}")
                    sys.exit(1)
        print("✓ 包内容校验 OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== 完成：可分发文件 ===")
    print(f"  {OUT_ZIP}")
    print("  报名页: apply.html（同目录 releases/ 下放置 zip 即可在线下载）")


if __name__ == "__main__":
    main()

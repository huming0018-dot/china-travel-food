#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_pages_deploy.py — 众包美食家扩展「云端发布」脚本（不依赖 Mac / Chrome / 签名 key）。

为什么有它：
  旧 publish.sh 只能在 Mac 跑：① crx 打包要本机 Chrome + key.pem；② Pages 同步依赖 `gh auth token`
  （GitHub Contents API）；③ Pages 只同步 updates.xml/crx/latest.zip，**漏了顶层 crowd-install-mac.command**
  （导致从 Pages 重装的设备拿到旧安装器、缺 Chrome 常驻看护）；④ zip 用 rsync 黑名单打包，混入 .bak 脏备份。

本脚本在云端宿主机即可完成 OTA 主通道发布（实际 OTA 走未签名 latest.zip，由 LaunchAgent 下载 rsync，
**不需要 crx/key**）：
  1. 从 crowd_extension 源码用「白名单」打 crowd-extension-latest.zip（含单形态 manifest，排除文档/脚本/脏文件/密钥）；
  2. 生成 updates.xml（codebase 指向 Pages crx；updater 只取版本号，crx 仅 Chrome 原生更新备用通道）；
  3. 上传 Supabase bucket 兜底通道（latest.zip / 版本 zip / updates.xml / 安装器 / 页面 / 图标）；
  4. 用 git + 单仓库 deploy key 把完整硬发布物同步到 crowd-pages（含安装器，修复遗漏）；
  5. 全程校验：版本一致、安装器含常驻看护、zip 可解、git 工作区干净。

crx 处理：无 key 不构建；若 dist-release 或 crowd_extension 已存在对应版本 .crx 则一并同步（通常由 Mac 补）。
  crx 缺失只影响「Chrome 原生自动更新」这条对解包加载扩展实际不生效的备用通道，不影响 LaunchAgent + zip 的 OTA。

用法：
  python3 crowd_pages_deploy.py            # dry-run：只构建+校验+打印将要做的事，不写任何远端
  python3 crowd_pages_deploy.py --apply    # 真正上传 bucket + push Pages
  --skip-bucket / --skip-pages            # 只走其中一条通道
  --pages-dir PATH                        # crowd-pages 工作副本（默认 ~/crowd-pages）

凭据：service_role 从环境变量 SUPABASE_SERVICE_ROLE_KEY 或 deploy.env 读取（机密，绝不入库）。
"""
import argparse
import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------- 常量
EXT_ID = "licijehcpohikchlnkbpjdjdfkcocndg"
PAGES_BASE = "https://huming0018-dot.github.io/crowd-pages"
SUPA_BASE = "https://bdwrhshgdeghgyzwpxnl.supabase.co"
BUCKET_PUBLIC = f"{SUPA_BASE}/storage/v1/object/public/crowd"
BUCKET_UPLOAD = f"{SUPA_BASE}/storage/v1/object/crowd"

# 脚本在 <repo>/cloud/ 下，扩展源在 <repo>/crowd_extension/
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "crowd_extension"
PAGES_DEFAULT = Path.home() / "crowd-pages"

# latest.zip 白名单（运行时 + 安装/页面所需）。文档/脚本/密钥/构建产物/脏备份一律不进。
ZIP_ROOT_FILES = [
    "manifest.json",
    "crowd-updater.sh",
    "crowd-updater.ps1",
    "crowd-updater-launchagent.plist",
    "crowd-install-mac.command",
    "crowd-install-win.bat",
    "apply.html",
    "install.html",
    "install-mobile.html",
    "owner-rate.html",
    "status.html",
    "submit.html",
    "sw.js",
    "app-manifest.json",
]
ZIP_DIRS = ["src", "icons"]
# 上传到 bucket 的页面/静态资源（与旧 publish.sh 对齐）
BUCKET_STATIC = [
    "apply.html", "install.html", "install-mobile.html", "submit.html",
    "owner-rate.html", "status.html", "sw.js", "app-manifest.json",
    "icons/icon192.png", "icons/icon512.png",
    "crowd-install-mac.command", "crowd-install-win.bat",
]
# 同步到 Pages 的「版本绑定硬发布物」（页面 html 在 Pages 网站侧独立维护、反而更新，不自动覆盖）
PAGES_SYNC = ["crowd-extension-latest.zip", "updates.xml",
              "crowd-install-mac.command", "crowd-install-win.bat"]

GIT_NAME = "crowd-deploy"
GIT_EMAIL = "1791357984-85e3ce0f@users.noreply.github.com"


def log(msg):
    print(msg, flush=True)


def fail(msg):
    log(f"❌ {msg}")
    sys.exit(1)


# ---------------------------------------------------------------- 凭据
def load_service_key():
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if key:
        return key
    for cand in [Path.home() / "food-cloud" / "deploy.env",
                 REPO / "cloud" / "deploy.env",
                 REPO.parent / "food-cloud" / "deploy.env"]:
        if cand.exists():
            for line in cand.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------- 构建 zip
def chrome_manifest_bytes():
    """zip 内用单形态 manifest（删 background.scripts，兼容 Chrome <121）；源文件不改动。"""
    m = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    bg = m.get("background")
    if isinstance(bg, dict) and "scripts" in bg:
        del bg["scripts"]
    return (json.dumps(m, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_latest_zip(ver):
    """白名单打包，返回 (zip_bytes, [(size, arcname)...])。"""
    entries = []
    for d in ZIP_DIRS:
        base = SRC / d
        if not base.is_dir():
            fail(f"缺少目录 {d}")
        for p in sorted(base.rglob("*")):
            if p.is_file() and ".DS_Store" not in p.name and ".bak" not in p.name:
                entries.append(p)
    for f in ZIP_ROOT_FILES:
        p = SRC / f
        if not p.is_file():
            fail(f"白名单文件缺失: {f}")
        entries.append(p)

    buf = io.BytesIO()
    manifest_added = False
    listed = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(entries, key=lambda x: str(x.relative_to(SRC))):
            arc = str(p.relative_to(SRC))
            if arc == "manifest.json":
                data = chrome_manifest_bytes()
                zi = zipfile.ZipInfo("manifest.json")
                zi.external_attr = 0o644 << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, data)
                manifest_added = True
                listed.append((len(data), "manifest.json"))
            else:
                zf.write(p, arc)
                listed.append((p.stat().st_size, arc))
        if not manifest_added:
            fail("manifest.json 未入包")
    data = buf.getvalue()
    return data, listed


def build_updates_xml(ver):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">\n'
        f'  <app appid="{EXT_ID}">\n'
        f'    <updatecheck codebase="{PAGES_BASE}/crowd-extension-v{ver}.crx" version="{ver}" />\n'
        '  </app>\n'
        '</gupdate>\n'
    ).encode("utf-8")


def find_crx(ver):
    for cand in [SRC / "dist-release" / f"crowd-extension-v{ver}.crx",
                 SRC / f"crowd-extension-v{ver}.crx"]:
        if cand.is_file():
            return cand
    return None


# ---------------------------------------------------------------- 校验
def verify(ver, zip_bytes):
    # zip 可解且 manifest 版本正确
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        bad = zf.testzip()
        if bad:
            fail(f"zip 损坏: {bad}")
        m = json.loads(zf.read("manifest.json").decode("utf-8"))
        if m.get("version") != ver:
            fail(f"zip 内 manifest 版本 {m.get('version')} != 源版本 {ver}")
        if "scripts" in (m.get("background") or {}):
            fail("zip 内 manifest 仍是双形态（background.scripts 未删）")
        names = set(zf.namelist())
    # 脏文件不得入包
    for n in names:
        if n.endswith(".pem") or ".bak" in n or n in ("publish.sh", "write-crowd-policy.sh",
                                                      "README.md", "DEPLOY.md", "CROWD_CONTRACT.md"):
            fail(f"zip 混入不该打包的文件: {n}")
    # 安装器常驻看护（v3.5.2+ 必须含 ensure_chrome_running）
    inst = (SRC / "crowd-install-mac.command").read_text(encoding="utf-8", errors="ignore")
    if "ensure_chrome_running" not in inst:
        fail("crowd-install-mac.command 缺少 ensure_chrome_running（常驻看护），拒绝发布旧安装器")
    log("✅ 校验通过：zip 可解 / 单形态 manifest / 无脏文件 / 安装器含常驻看护")


# ---------------------------------------------------------------- bucket
def upload_bucket(key, name, data, ctype):
    req = urllib.request.Request(
        f"{BUCKET_UPLOAD}/{name}", data=data, method="PUT",
        headers={"Authorization": f"Bearer {key}", "apikey": key,
                 "x-upsert": "true", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status in (200, 201)


def do_bucket(key, ver, zip_bytes, xml_bytes, crx):
    jobs = [
        ("crowd-extension-latest.zip", zip_bytes, "application/zip"),
        (f"crowd-extension-v{ver}.zip", zip_bytes, "application/zip"),
        ("updates.xml", xml_bytes, "text/xml"),
    ]
    for f in BUCKET_STATIC:
        jobs.append((f, (SRC / f).read_bytes(),
                     "application/octet-stream" if f.endswith((".command", ".bat")) else
                     "image/png" if f.endswith(".png") else
                     "application/json" if f.endswith(".json") else
                     "text/html" if f.endswith(".html") else "text/javascript"))
    if crx:
        jobs.append((f"crowd-extension-v{ver}.crx", crx.read_bytes(), "application/octet-stream"))
    fail_n = 0
    for name, data, ctype in jobs:
        try:
            ok = upload_bucket(key, name, data, ctype)
            log(("   ✅ " if ok else "   ❌ ") + f"bucket {name}")
            fail_n += 0 if ok else 1
        except Exception as e:  # noqa
            fail_n += 1
            log(f"   ❌ bucket {name} -> {e}")
    if fail_n:
        fail(f"bucket 上传 {fail_n} 个失败")


# ---------------------------------------------------------------- Pages (git)
def git(pages_dir, *args):
    return subprocess.run(["git", "-C", str(pages_dir), *args],
                          capture_output=True, text=True)


def do_pages(pages_dir, ver, zip_bytes, xml_bytes, crx, apply):
    if not pages_dir.is_dir():
        fail(f"crowd-pages 工作副本不存在: {pages_dir}（先 git clone git@github-crowd-pages:huming0018-dot/crowd-pages.git）")

    # 产物（内存），dry-run 时只比对、不落盘，避免污染工作区
    artifacts = {
        "crowd-extension-latest.zip": (zip_bytes, None),
        "updates.xml": (xml_bytes, None),
        "crowd-install-mac.command": ((SRC / "crowd-install-mac.command").read_bytes(), 0o755),
        "crowd-install-win.bat": ((SRC / "crowd-install-win.bat").read_bytes(), None),
    }
    if crx:
        artifacts[f"crowd-extension-v{ver}.crx"] = (crx.read_bytes(), None)

    changed = []
    for name, (data, mode) in artifacts.items():
        p = pages_dir / name
        if not p.exists():
            changed.append((name, "新增", data, mode))
        elif p.read_bytes() != data:
            changed.append((name, "更新", data, mode))
    if not changed:
        log("✅ Pages 已是最新，无需提交（幂等）")
        return
    log("Pages 将变更:")
    for name, kind, _, _ in changed:
        log(f"   {kind} {name}")
    if not apply:
        log("[dry-run] 未 commit/push（加 --apply 才写）")
        return

    r = git(pages_dir, "pull", "--ff-only", "origin", "main")
    if r.returncode != 0:
        fail(f"pages pull 失败（有本地改动/分叉）: {r.stderr.strip()}")
    names = []
    for name, kind, data, mode in changed:
        p = pages_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        if mode:
            os.chmod(p, mode)
        names.append(name)
    r = git(pages_dir, "add", "--", *names)
    if r.returncode != 0:
        fail("pages git add 失败: " + r.stderr.strip())
    msg = f"Pages 发布 v{ver}（latest.zip + 安装器 + updates.xml，云端自动）"
    r = git(pages_dir, "-c", f"user.name={GIT_NAME}", "-c", f"user.email={GIT_EMAIL}",
            "commit", "-m", msg)
    if r.returncode != 0:
        fail("pages commit 失败: " + r.stderr.strip())
    r = git(pages_dir, "push", "origin", "main")
    if r.returncode != 0:
        fail("pages push 失败: " + r.stderr.strip())
    log(f"✅ Pages 已 push: {msg}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正上传+push（默认 dry-run）")
    ap.add_argument("--skip-bucket", action="store_true")
    ap.add_argument("--skip-pages", action="store_true")
    ap.add_argument("--pages-dir", default=str(PAGES_DEFAULT))
    args = ap.parse_args()

    if not SRC.is_dir():
        fail(f"找不到扩展源目录 {SRC}")
    ver = json.loads((SRC / "manifest.json").read_text(encoding="utf-8")).get("version", "")
    if not ver:
        fail("读不到 manifest version")
    log(f"== 众包美食家发布 v{ver}（apply={args.apply}）源={SRC}")

    zip_bytes, listed = build_latest_zip(ver)
    xml_bytes = build_updates_xml(ver)
    crx = find_crx(ver)
    verify(ver, zip_bytes)
    log(f"== latest.zip {len(zip_bytes)} 字节，{len(listed)} 个文件；updates.xml 就绪；"
        + (f"crx 存在 {crx.name}" if crx else "无 crx（云端无 key，跳过；不影响 zip OTA）"))

    key = ""
    if args.apply and not args.skip_bucket:
        key = load_service_key()
        if not key:
            fail("缺 SUPABASE_SERVICE_ROLE_KEY（env 或 deploy.env）")

    if not args.skip_bucket:
        if args.apply:
            do_bucket(key, ver, zip_bytes, xml_bytes, crx)
        else:
            log("[dry-run] 将上传 bucket: latest.zip / 版本 zip / updates.xml / 安装器 / 页面 / 图标"
                + (" / crx" if crx else ""))
    if not args.skip_pages:
        do_pages(Path(args.pages_dir), ver, zip_bytes, xml_bytes, crx, args.apply)

    log("== 完成" + ("（已发布）" if args.apply else "（dry-run，未写远端）"))


if __name__ == "__main__":
    main()

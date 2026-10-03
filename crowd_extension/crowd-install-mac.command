#!/bin/bash
# ============================================================
# 美食图鉴·众包采集插件 — macOS 一键安装器
# 无需 Python / 无任何开发环境。双击即可。
# 自动完成：解压插件 → 打开扩展页 → 复制插件路径到剪贴板
# ============================================================
set -e

echo "=============================================="
echo "  美食图鉴 · 众包采集插件 一键安装 (macOS)"
echo "=============================================="
echo ""

# 0) 脚本所在目录（下载文件通常在 ~/Downloads 或当前目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORK_DIR="${HOME}/.food-crowd"
EXT_DIR="${WORK_DIR}/crowd-extension-v3.2.0"

# 1) 找 zip：优先脚本同目录，其次 Downloads
ZIP_SRC=""
for cand in "${SCRIPT_DIR}/crowd-extension-v3.2.0.zip" "${HOME}/Downloads/crowd-extension-v3.2.0.zip"; do
  if [ -f "$cand" ]; then ZIP_SRC="$cand"; break; fi
done

if [ -z "$ZIP_SRC" ]; then
  echo "❌ 没找到 crowd-extension-v3.2.0.zip"
  echo "   请先回到报名/安装页下载插件 zip（与安装器放同一文件夹即可）。"
  echo ""
  read -p "按回车退出…" _
  exit 1
fi
echo "✓ 找到插件包: ${ZIP_SRC}"

# 2) 解压到固定目录
mkdir -p "$WORK_DIR"
rm -rf "$EXT_DIR"
echo "✓ 解压中…"
cd "$WORK_DIR"
unzip -oq "$ZIP_SRC" -d "$EXT_DIR"
echo "✓ 插件已解压到: ${EXT_DIR}"

# 3) 自动探测 Chrome 系浏览器
BROWSER_APP=""
for app in "/Applications/Google Chrome.app" "/Applications/Microsoft Edge.app" "/Applications/Brave Browser.app" "/Applications/Chromium.app" "/Applications/Arc.app"; do
  if [ -d "$app" ]; then BROWSER_APP="$app"; break; fi
done

if [ -z "$BROWSER_APP" ]; then
  echo "❌ 未检测到 Chrome / Edge / Brave。请先安装任一 Chrome 系浏览器后重试。"
  read -p "按回车退出…" _
  exit 1
fi
echo "✓ 检测到浏览器: $(basename "$BROWSER_APP" | sed 's/\.app//')"

# 4) 复制插件路径到剪贴板
echo -n "$EXT_DIR" | pbcopy
echo "✓ 插件文件夹路径已复制到剪贴板"

# 5) 打开扩展管理页
if [[ "$BROWSER_APP" == *"Google Chrome"* ]]; then
  EXT_URL="chrome://extensions"
elif [[ "$BROWSER_APP" == *"Microsoft Edge"* ]]; then
  EXT_URL="edge://extensions"
else
  EXT_URL="chrome://extensions"
fi
open -a "$BROWSER_APP" "$EXT_URL"
echo "✓ 已打开扩展管理页（${EXT_URL}）"

echo ""
echo "=============================================="
echo "  最后一步（30 秒完成）："
echo "  1. 在扩展页右上角 开启「开发者模式」"
echo "  2. 点「加载已解压的扩展程序」"
echo "  3. 在弹窗里按 ⌘V 粘贴路径 → 回车"
echo "=============================================="
echo ""
echo "安装完成后：点浏览器右上角 🧩 → 插件「选项」→"
echo "填写参与编号（P-XXXXXX）并同意协议 → 回到小红书页面启动采集。"
echo ""
read -p "按回车关闭…" _

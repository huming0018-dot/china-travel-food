#!/bin/bash
# 众包美食家 · Mac 一键安装（双击运行，无需 Python/任何开发环境）
#
# 原理：写入 Chrome 企业策略 ExtensionInstallForcelist —— Chrome 会自己从项目更新服务器
# 下载、安装插件，并在以后每次发布新版本时自动升级，无需再装。
# 需要：管理员密码一次（写策略用）；本机装有 Chrome。
set -e
EXT_ID="licijehcpohikchlnkbpjdjdfkcocndg"
UPDATE_URL="https://huming0018-dot.github.io/crowd-pages/updates.xml"
ENTRY="$EXT_ID;$UPDATE_URL"
PLIST="/Library/Managed Preferences/com.google.Chrome"

clear
echo "==============================================="
echo "  众包美食家 · 一键安装（Mac）"
echo "==============================================="
echo
echo "这一步会把插件登记进 Chrome 的企业策略，之后 Chrome"
echo "自动完成安装，并且以后每次升级都会自动更新，无需重装。"
echo

# 0. 前置检查
if [ ! -d "/Applications/Google Chrome.app" ]; then
  echo "❌ 未检测到 Chrome，请先安装 Chrome 浏览器后再运行本脚本。"
  read -r -p "按回车退出..."
  exit 1
fi

# 1. 写入策略（需要一次管理员密码）
echo "请输入开机密码（输入时不显示，输完回车）："
if sudo -v; then :; else echo "❌ 需要管理员权限才能写入 Chrome 策略。"; read -r -p "按回车退出..."; exit 1; fi

if sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" >/dev/null 2>&1; then
  if sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" | grep -q "$EXT_ID;$UPDATE_URL"; then
    echo "✅ 安装策略已存在且为最新（之前装过），跳过登记。"
  elif sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" | grep -q "$EXT_ID"; then
    # v3.4.8 通道迁移：条目在但更新地址是旧的（bucket 已废）→ 原地替换
    IDX=$(sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" | grep -n "$EXT_ID" | cut -d: -f1)
    IDX=$((IDX-1))
    sudo /usr/libexec/PlistBuddy -c "Delete :ExtensionInstallForcelist:$IDX" "$PLIST.plist"
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$IDX string $ENTRY" "$PLIST.plist"
    echo "✅ 安装策略的更新地址已迁移到国内可达通道。"
  else
    IDX=$(sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" | grep -cE "^    " || true)
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$IDX string $ENTRY" "$PLIST.plist"
    echo "✅ 已登记到 Chrome 策略（追加）。"
  fi
else
  sudo defaults write "$PLIST" ExtensionInstallForcelist -array "$ENTRY"
  echo "✅ 已登记到 Chrome 策略（新建）。"
fi

# 1.5 刷新 macOS 偏好缓存（cfprefsd 会缓存 plist，不刷 Chrome 可能读到旧的空策略）
sudo killall cfprefsd 2>/dev/null || true

# 2. 重启 Chrome 让策略生效（CROWD_NO_RESTART=1 时跳过：策略会在 Chrome 下次自然重启时生效）
if [ "${CROWD_NO_RESTART:-0}" = "1" ]; then
  echo "（按约定不重启 Chrome；策略已生效，插件会在 Chrome 下次启动时自动安装/升级）"
else
echo
echo "即将重启 Chrome 让插件自动安装（请先保存浏览器里未提交的页面）。"
read -r -p "按回车重启 Chrome，或 Ctrl+C 取消..."
osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true
sleep 2
open -a "Google Chrome"
fi

echo
echo "==============================================="
echo "  完成！接下来："
echo "  1. Chrome 重启后会自动装好「众包美食家」插件"
echo "     （约 1 分钟内；插件图标出现在右上角拼图里）"
echo "  2. 首次安装会自动打开「参与协议」页："
echo "     点【我要加入】自动获得参与编号 → 点【同意并开始使用】"
echo "  3. 如果之前手动装过旧版本（开发者模式装的），"
echo "     请到 chrome://extensions 把旧的移除，避免重复"
echo
echo "  以后插件升级全自动，不需要再运行本脚本。"
echo "==============================================="
read -r -p "按回车关闭窗口..."

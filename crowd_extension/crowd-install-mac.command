#!/bin/bash
# Internal Mac acceptance only. The bundle supplies both verified architectures.
set -euo pipefail
umask 077
finish() {
  result=$?
  [ -z "${staging:-}" ] || rm -rf "$staging"
  if [ "$result" -ne 0 ]; then echo '安装未完成。请保留这段提示，交给 Codex 检查。'; fi
  echo '按回车关闭此窗口。'
  read -r _ || true
}
trap finish EXIT
cd "$(dirname "$0")"
echo '正在准备 Mac 内测客户端。无需管理员权限。'
[ "$(uname -s)" = Darwin ] || { echo '请在 Mac 上双击运行。'; exit 1; }
case "$(uname -m)" in
  arm64) arch=arm64 ;;
  x86_64) arch=x64 ;;
  *) echo '此 Mac 的处理器暂不支持。'; exit 1 ;;
esac
major=$(sw_vers -productVersion | cut -d. -f1)
[ "$major" -ge 13 ] || { echo '需要 macOS 13 或更新系统。'; exit 1; }
for tool in unzip shasum plutil codesign open; do
  command -v "$tool" >/dev/null || { echo "缺少系统工具：$tool"; exit 1; }
done
echo '正在校验安装文件……'
shasum -a 256 -c SHA256SUMS.txt
destination="$HOME/Applications/众包采集内测.app"
[ ! -e "$destination" ] || { echo '内测客户端已安装，正在打开。'; open "$destination"; exit 0; }
mkdir -p "$HOME/Applications"
staging=$(mktemp -d "$HOME/Applications/.crowd-install.XXXXXX")
unzip -q "electron-v44.5.1-darwin-$arch.zip" -d "$staging"
app="$staging/众包采集内测.app"
mv "$staging/Electron.app" "$app"
plist="$app/Contents/Info.plist"
plutil -replace CFBundleName -string '众包采集内测' "$plist"
plutil -replace CFBundleDisplayName -string '众包采集内测' "$plist"
plutil -replace CFBundleIdentifier -string org.foodresearch.crowd "$plist"
plutil -replace CFBundleShortVersionString -string 4.0.0 "$plist"
plutil -replace CFBundleVersion -string 40000 "$plist"
plutil -insert CFBundleURLTypes -json '[{"CFBundleURLSchemes":["foodcrowd"],"CFBundleURLName":"org.foodresearch.crowd.join"}]' "$plist"
mkdir -p "$app/Contents/Resources/app"
unzip -q crowd-desktop-sources-v4.0.0.zip -d "$app/Contents/Resources/app"
echo '正在生成本机内测签名……'
codesign --force --deep --preserve-metadata=entitlements,requirements,flags --sign - "$app"
codesign --verify --deep --strict "$app"
mv "$app" "$destination"
echo '客户端已安装到你的「应用程序」文件夹，正在打开。'
open "$destination"
echo '等待客户端打开后，再打开同目录的「开始Mac内测.html」。'

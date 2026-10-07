#!/bin/bash
# Internal extension setup helper. Browser installation stays user-confirmed.
set -euo pipefail
umask 077
trap 'result=$?; if [ "$result" -ne 0 ]; then echo "准备未完成。请保留以上提示，交给 Codex 检查。"; fi' EXIT
[ "$(uname -s)" = Darwin ] || { echo '请在 Mac 上双击运行。'; exit 1; }
kit_dir=$(cd "$(dirname "$0")" && pwd)
cd "$kit_dir"
echo '正在校验并准备轻量插件。无需管理员密码。'
shasum -a 256 -c SHA256SUMS.txt >/dev/null
extension_id=licijehcpohikchlnkbpjdjdfkcocndg
expected_key=$(plutil -extract key raw -o - "$kit_dir/插件/manifest.json")
browser_app=''; browser_url=''; installed_path=''; installed_profile=''
# Read only this extension's source path; never edit browser profile or policy.
for browser in 'Google Chrome' 'Microsoft Edge'; do
  candidate_app=''
  for app_path in "$HOME/Applications/$browser.app" "/Applications/$browser.app"; do
    if [ -d "$app_path" ]; then candidate_app=$app_path; break; fi
  done
  [ -n "$candidate_app" ] || continue
  if [ "$browser" = 'Google Chrome' ]; then profile_root="$HOME/Library/Application Support/Google/Chrome"; candidate_url='chrome://extensions/'
  else profile_root="$HOME/Library/Application Support/Microsoft Edge"; candidate_url='edge://extensions/'; fi
  if [ -z "$browser_app" ]; then browser_app=$candidate_app; browser_url=$candidate_url; fi
  for profile in "$profile_root/Default" "$profile_root"/Profile\ *; do
    for preferences in "$profile/Preferences" "$profile/Secure Preferences"; do
      [ -f "$preferences" ] || continue
      path=$(plutil -extract "extensions.settings.$extension_id.path" raw -o - "$preferences" 2>/dev/null) || continue
      case "$path" in /*) ;; *) continue ;; esac
      [ ! -L "$path" ] || continue
      if [ -f "$path/manifest.json" ]; then
        key=$(plutil -extract key raw -o - "$path/manifest.json" 2>/dev/null) || continue
        version=$(plutil -extract version raw -o - "$path/manifest.json" 2>/dev/null) || continue
      else
        # Restore a removed source folder only when the browser remembers our key.
        case "$path" in "$HOME"/*) ;; *) continue ;; esac
        key=$(plutil -extract "extensions.settings.$extension_id.manifest.key" raw -o - "$preferences" 2>/dev/null) || continue
        version=$(plutil -extract "extensions.settings.$extension_id.manifest.version" raw -o - "$preferences" 2>/dev/null) || continue
      fi
      [ "$key" = "$expected_key" ] || continue
      # Legacy v3 uses the same public key; it is a separate runtime.
      case "$version" in 4.*) ;; *) continue ;; esac
      if [ -n "$installed_path" ] && { [ "$installed_path" != "$path" ] || [ "$browser_app" != "$candidate_app" ] || [ "$installed_profile" != "${profile##*/}" ]; }; then
        echo '检测到多个浏览器或个人资料中的安装。请在之前成功接入的个人资料窗口更新并刷新，不要卸载或重新报名。'; exit 1
      fi
      installed_path=$path; installed_profile=${profile##*/}; browser_app=$candidate_app; browser_url=$candidate_url
    done
  done
done
[ -n "$browser_app" ] || { echo '未找到 Chrome 或 Edge。请先安装其中一个浏览器，再双击本文件。'; exit 1; }
destination=${installed_path:-"$HOME/Library/Application Support/众包采集轻量/插件"}
[ ! -L "$destination" ] || { echo '安装目录是链接，请联系 Codex 检查。'; exit 1; }
if [ -e "$destination" ]; then
  key=$(plutil -extract key raw -o - "$destination/manifest.json" 2>/dev/null) || { echo '安装目录异常，未覆盖。'; exit 1; }
  [ "$key" = "$expected_key" ] || { echo '安装目录不是本插件，未覆盖。'; exit 1; }
  version=$(plutil -extract version raw -o - "$destination/manifest.json" 2>/dev/null) || { echo '无法核对原版本，未覆盖。'; exit 1; }
  case "$version" in 4.*) ;; *) echo '目标目录是旧版采集器，未覆盖。请在现有 v4 参与身份的浏览器中更新。'; exit 1 ;; esac
  [ -z "$(find "$destination" -type l -print -quit)" ] || { echo '插件目录含链接，未覆盖。'; exit 1; }
fi
mkdir -p "$destination"
cp -R "$kit_dir/插件/." "$destination/"
printf '%s' "$destination" | pbcopy
open -R "$destination/manifest.json"
open "$kit_dir/先打开安装说明.html"
if [ -n "$installed_path" ]; then
  # Select the existing research profile, even when another profile is active.
  open -n -a "$browser_app" --args "--profile-directory=$installed_profile" "$browser_url"
  echo '已更新原插件文件，本机参与身份未删除。请在扩展管理页点击本插件的刷新图标。'
  echo "已打开原浏览器个人资料：$installed_profile。请在此窗口继续，不要重新报名。"
else
  open -a "$browser_app" "$browser_url"
  echo '文件已准备好，尚未安装到浏览器。安装路径已复制。'
  echo '在扩展页开启「开发者模式」→「加载已解压的扩展程序」。'
  echo '选文件夹时按 Command+Shift+G，再按 Command+V、回车，点击「选择」。'
fi
echo '加载后勾选自愿参与并开始，按提示登录小红书。遇到管理策略拦截请保留提示。'

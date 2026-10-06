#!/bin/bash
# 众包美食家 · Mac 一键安装（v3 遥测版，2026-10-07）
# 每一步自动上报到服务端日志——装不上时不用截图接力，PM 直接看到卡在哪。
# 主通道：Chrome 企业策略（自动安装+自动升级）；兜底：无管理员自动降级手动挂载。
EXT_ID="licijehcpohikchlnkbpjdjdfkcocndg"
UPDATE_URL="https://huming0018-dot.github.io/crowd-pages/updates.xml"
ENTRY="$EXT_ID;$UPDATE_URL"
PLIST="${CROWD_PLIST_OVERRIDE:-/Library/Managed Preferences/com.google.Chrome}"
EXT_DIR="$HOME/crowd-ext"
ZIP_URL="https://huming0018-dot.github.io/crowd-pages/crowd-extension-latest.zip"
ZIP_URL_BAK="https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v3.4.10.zip"
API_KEY="sb_publishable_c93XenGzZsoa308e3bTg6A__lfaqQ-B"
RPC="https://bdwrhshgdeghgyzwpxnl.supabase.co/rest/v1/rpc/crowd_install_report"
RID="$(date +%s)-$(od -An -tx1 -N4 /dev/urandom 2>/dev/null | tr -d ' ' || echo R$RANDOM)"

report() { # report <step> <msg> —— 静默、5 秒封顶、永不阻塞安装
  local msg
  msg=$(printf '%s' "$2" | tr '"\\' "'/" | head -c 380)
  curl -s --max-time 5 -X POST "$RPC" -H "apikey: $API_KEY" -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"p_run_id\":\"$RID\",\"p_step\":\"$1\",\"p_msg\":\"$msg\"}" >/dev/null 2>&1 || true
}

clear
echo "================================================"
echo "  众包美食家 · 一键安装（Mac）"
echo "  安装编号：$RID（出问题报这串就行）"
echo "================================================"
report start "$(uname -m) macOS $(sw_vers -productVersion 2>/dev/null)"

step() { echo; echo "—— $1"; report "step" "$1"; }
fail() { echo; echo "❌ $1"; echo "👉 $2"; echo; report "FAIL" "$1"; exit 1; }

# ---------- 第 1 步：Chrome ----------
step "第 1 步：检查 Chrome"
[ -d "/Applications/Google Chrome.app" ] || fail "没检测到 Chrome" "先装 Chrome：https://www.google.cn/chrome/ ，装完重跑"
CHROME_VER=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null | grep -oE '[0-9]+' | head -1)
[ -n "$CHROME_VER" ] || fail "Chrome 版本读不到" "重装 Chrome 后重跑"
if [ "$CHROME_VER" -lt 96 ] 2>/dev/null; then
  fail "Chrome 版本太老（$CHROME_VER）" "升级 Chrome 后重跑"
fi
echo "✅ Chrome 已安装（版本 $CHROME_VER）"
report chrome_ok "chrome $CHROME_VER"

# ---------- 第 2 步：网络 ----------
step "第 2 步：检查网络（插件更新通道）"
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 12 "$UPDATE_URL" || echo 000)
[ "$CODE" = "200" ] || fail "连不上插件更新服务器（HTTP $CODE）" "检查网络/代理/VPN 后重跑；或换个网络"
echo "✅ 更新通道正常"
report net_ok "updates.xml $CODE"

# ---------- 第 3 步：写策略 ----------
step "第 3 步：登记插件到 Chrome（需要一次管理员密码）"
echo "接下来会要开机密码（输入时屏幕不显示，输完回车）。"
if sudo -v; then
  ADMIN_OK=1
  report admin_ok ""
else
  ADMIN_OK=0
  echo "⚠️  管理员校验没过（密码错误或账户不是管理员）——自动改走免管理员模式。"
  report admin_fail "sudo -v failed"
fi

write_entry() {
  local cur
  cur=$(sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" 2>/dev/null)
  if [ $? -ne 0 ] || ! echo "$cur" | grep -q .; then
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist array" "$PLIST.plist" 2>/dev/null
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:0 string $ENTRY" "$PLIST.plist" 2>/dev/null
    return
  fi
  echo "$cur" | grep -q "$ENTRY" && return 0
  local idx
  idx=$(echo "$cur" | awk -v ext="$EXT_ID" '
    /Array \{/ {inarr=1; idx=0; next}
    inarr && /^[[:space:]]*\}/ {inarr=0}
    inarr { if (index($0, ext)) { print idx; exit } idx++ }')
  if [ -n "$idx" ]; then
    sudo /usr/libexec/PlistBuddy -c "Delete :ExtensionInstallForcelist:$idx" "$PLIST.plist" 2>/dev/null || true
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$idx string $ENTRY" "$PLIST.plist" 2>/dev/null
  else
    local cnt
    cnt=$(echo "$cur" | awk '/Array \{/{f=1;c=0;next} f&&/^[[:space:]]*\}/{f=0} f{c++} END{print c+0}')
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$cnt string $ENTRY" "$PLIST.plist" 2>/dev/null
  fi
}

if [ "$ADMIN_OK" = "1" ]; then
  write_entry
  sudo killall cfprefsd 2>/dev/null || true
  if sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" 2>/dev/null | grep -q "$ENTRY"; then
    echo "✅ 策略已登记并读回验证通过（自动升级通道已开）"
    report policy_ok ""
    MODE="policy"
  else
    echo "⚠️  策略写入后读回验证失败，自动改走免管理员模式。"
    report policy_writeback_fail ""
    MODE="sideload"
  fi
else
  MODE="sideload"
fi

# ---------- 兜底：手动挂载 ----------
if [ "$MODE" = "sideload" ]; then
  step "第 3b 步：下载插件包并挂载（免管理员）"
  rm -rf "$EXT_DIR" && mkdir -p "$EXT_DIR"
  curl -sL --max-time 90 -o /tmp/crowd-ext.zip "$ZIP_URL" || curl -sL --max-time 90 -o /tmp/crowd-ext.zip "$ZIP_URL_BAK" \
    || fail "插件包下载失败" "检查网络后重跑"
  [ -s /tmp/crowd-ext.zip ] || fail "插件包是空文件" "检查网络后重跑"
  unzip -qo /tmp/crowd-ext.zip -d "$EXT_DIR" || fail "解压失败" "重跑本脚本"
  [ -f "$EXT_DIR/manifest.json" ] || fail "解压内容不对" "重跑；不行就联系管理员"
  echo "✅ 插件包已就位"
  report sideload_ready "$EXT_DIR"
fi

# ---------- 第 4 步：重启 Chrome ----------
step "第 4 步：重启 Chrome 让插件生效"
if [ "${CROWD_NO_RESTART:-0}" = "1" ]; then
  echo "（按约定不重启 Chrome；下次启动时生效）"
  report no_restart ""
else
  echo "即将重启 Chrome（先保存浏览器里没提交的页面）。"
  read -r -p "按回车重启 Chrome，或 Ctrl+C 取消..."
  osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true
  sleep 2
  if [ "$MODE" = "sideload" ]; then
    open -a "Google Chrome" --args --load-extension="$EXT_DIR"
  else
    open -a "Google Chrome"
  fi
  report chrome_restarted "$MODE"
fi

# ---------- 第 5 步：验证插件真的落地 ----------
if [ "${CROWD_NO_RESTART:-0}" != "1" ]; then
  step "第 5 步：验证安装结果（最多等 2 分钟）"
  OK=0
  for i in $(seq 1 24); do
    sleep 5
    if [ -d "$HOME/Library/Application Support/Google/Chrome/Default/Extensions/$EXT_ID" ] \
       || [ -d "$HOME/Library/Application Support/Google/Chrome/Default/Local Extension Settings/$EXT_ID" ]; then
      OK=1; break
    fi
  done
  if [ "$OK" = "1" ]; then
    echo "✅✅ 插件已装好并验证落地！"
    report install_verified "$MODE"
  else
    echo "⚠️  2 分钟内没检测到插件落地。"
    echo "    打开 Chrome 访问 chrome://extensions 看看有没有「众包美食家」。"
    echo "    没有的话：chrome://policy 点「重新加载政策」，再重启一次 Chrome。"
    report install_unverified "$MODE"
  fi
fi

echo
echo "================================================"
echo "  下一步（只此一次）：Chrome 会自动弹出「参与协议」页："
echo "  点【我要加入】自动领编号 → 点【同意并开始使用】"
echo "  之后采集全自动，不用人管。"
[ "$MODE" = "sideload" ] && echo "  （本机为免管理员挂载模式：扩展页显示开发者模式属正常；升级插件重跑本脚本即可）"
echo "================================================"

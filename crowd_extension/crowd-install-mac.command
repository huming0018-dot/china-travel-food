#!/bin/bash
# 众包美食家 · Mac 一键安装（v2 加固版，2026-10-06 重写）
#
# 设计原则：每一步自检，失败明说原因+怎么办，装完验证插件真的落地。
# 主通道：Chrome 企业策略 ExtensionInstallForcelist（自动安装+自动升级）。
# 兜底通道：无管理员权限时自动降级为手动挂载（--load-extension，功能相同，升级需重跑本脚本）。
EXT_ID="licijehcpohikchlnkbpjdjdfkcocndg"
UPDATE_URL="https://huming0018-dot.github.io/crowd-pages/updates.xml"
ENTRY="$EXT_ID;$UPDATE_URL"
PLIST="${CROWD_PLIST_OVERRIDE:-/Library/Managed Preferences/com.google.Chrome}"
ZIP_URL="https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-latest.zip"
EXT_DIR="$HOME/crowd-ext"

clear
echo "================================================"
echo "  众包美食家 · 一键安装（Mac）"
echo "================================================"
echo

step() { echo; echo "—— $1"; }
fail() { echo; echo "❌ $1"; echo "👉 $2"; echo; exit 1; }

# ---------- 第 1 步：Chrome ----------
step "第 1 步：检查 Chrome"
if [ ! -d "/Applications/Google Chrome.app" ]; then
  fail "这台机器还没装 Chrome" "先去装 Chrome 浏览器：https://www.google.cn/chrome/ ，装完再跑我"
fi
CHROME_VER=$("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null | grep -oE '[0-9]+' | head -1)
echo "✅ Chrome 已安装（版本号 $CHROME_VER）"
if [ -n "$CHROME_VER" ] && [ "$CHROME_VER" -lt 96 ] 2>/dev/null; then
  fail "Chrome 版本太老（$CHROME_VER）" "把 Chrome 升级到最新版再跑"
fi

# ---------- 第 2 步：网络 ----------
step "第 2 步：检查网络（插件更新通道）"
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 12 "$UPDATE_URL" || echo 000)
[ "$CODE" = "200" ] || fail "连不上插件更新服务器（HTTP $CODE）" "检查网络/代理/VPN 后重跑；或换个网络环境"
echo "✅ 更新通道正常"

# ---------- 第 3 步：写策略 ----------
step "第 3 步：登记插件到 Chrome（需要一次管理员密码）"
echo "接下来会要开机密码（输入时屏幕不显示，输完回车）。"
if ! sudo -v; then
  ADMIN_OK=0
  echo "⚠️  管理员校验没过（密码错误或账户不是管理员）。"
else
  ADMIN_OK=1
fi

write_entry() {
  # 用 awk 精确算数组下标（PlistBuddy 打印子键时是裸数组，第一行是 'Array {'）
  local cur
  cur=$(sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" 2>/dev/null)
  if [ $? -ne 0 ]; then
    # 整个 plist 还没有这个键：新建数组
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist array" "$PLIST.plist" 2>/dev/null || \
      sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist array" "$PLIST.plist"
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:0 string $ENTRY" "$PLIST.plist"
    return
  fi
  if echo "$cur" | grep -q "$ENTRY"; then
    return  # 已是新地址，无需动
  fi
  # 已有条目：换掉同 ID 的旧地址，或追加
  local idx
  idx=$(echo "$cur" | awk -v ext="$EXT_ID" '
    /Array \{/ {inarr=1; idx=0; next}
    inarr && /^[[:space:]]*\}/ {inarr=0}
    inarr { if (index($0, ext)) { print idx; exit } idx++ }')
  if [ -n "$idx" ]; then
    sudo /usr/libexec/PlistBuddy -c "Delete :ExtensionInstallForcelist:$idx" "$PLIST.plist" || true
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$idx string $ENTRY" "$PLIST.plist"
  else
    local cnt
    cnt=$(echo "$cur" | awk '/Array \{/{f=1;c=0;next} f&&/^[[:space:]]*\}/{f=0} f{c++} END{print c+0}')
    sudo /usr/libexec/PlistBuddy -c "Add :ExtensionInstallForcelist:$cnt string $ENTRY" "$PLIST.plist"
  fi
}

if [ "$ADMIN_OK" = "1" ]; then
  write_entry
  sudo killall cfprefsd 2>/dev/null || true   # 刷新策略缓存，否则 Chrome 可能读到旧的
  # 读回验证——写了不算数，读得到才算数
  if sudo /usr/libexec/PlistBuddy -c "Print :ExtensionInstallForcelist" "$PLIST.plist" 2>/dev/null | grep -q "$ENTRY"; then
    echo "✅ 策略已登记并读回验证通过（自动升级通道已开）"
    MODE="policy"
  else
    echo "⚠️  策略写入后读回验证失败。降级为手动挂载模式。"
    MODE="sideload"
  fi
else
  echo "改走手动挂载模式（不需要管理员权限，功能完全一样）。"
  MODE="sideload"
fi

# ---------- 兜底：手动挂载 ----------
if [ "$MODE" = "sideload" ]; then
  step "第 3b 步：直接下载插件包挂载"
  mkdir -p "$EXT_DIR"
  curl -sL --max-time 60 -o /tmp/crowd-ext.zip "https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v3.4.10.zip" \
    || fail "插件包下载失败" "检查网络后重跑"
  [ -s /tmp/crowd-ext.zip ] || fail "插件包下载是空文件" "检查网络后重跑"
  rm -rf "$EXT_DIR"
  mkdir -p "$EXT_DIR"
  unzip -qo /tmp/crowd-ext.zip -d "$EXT_DIR" || fail "插件包解压失败" "重跑本脚本"
  [ -f "$EXT_DIR/manifest.json" ] || fail "解压出来的东西不对" "重跑本脚本；还不行找管理员"
  echo "✅ 插件包已就位：$EXT_DIR"
fi

# ---------- 第 4 步：重启 Chrome ----------
step "第 4 步：重启 Chrome 让插件生效"
if [ "${CROWD_NO_RESTART:-0}" = "1" ]; then
  echo "（按约定不重启 Chrome；下次 Chrome 启动时生效）"
else
  echo "即将重启 Chrome（请先保存浏览器里没提交的页面）。"
  read -r -p "按回车重启 Chrome，或 Ctrl+C 取消..."
  osascript -e 'tell application "Google Chrome" to quit' 2>/dev/null || true
  sleep 2
  if [ "$MODE" = "sideload" ]; then
    open -a "Google Chrome" --args --load-extension="$EXT_DIR"
  else
    open -a "Google Chrome"
  fi
fi

# ---------- 第 5 步：验证插件真的装上了 ----------
if [ "${CROWD_NO_RESTART:-0}" != "1" ]; then
  step "第 5 步：验证安装结果"
  echo "等 Chrome 装好插件（最多 2 分钟）……"
  OK=0
  for i in $(seq 1 24); do
    sleep 5
    if [ "$MODE" = "sideload" ]; then
      # 手动挂载：看扩展进程有没有起来（检查 Service Worker 注册）
      if ls "$HOME/Library/Application Support/Google/Chrome/Default/Service Worker/ScriptCache" >/dev/null 2>&1 \
         && ls "$HOME/Library/Application Support/Google/Chrome/Default/Local Extension Settings/$EXT_ID" >/dev/null 2>&1; then
        OK=1; break
      fi
    else
      if ls "$HOME/Library/Application Support/Google/Chrome/Default/Extensions/$EXT_ID"/*/manifest.json >/dev/null 2>&1; then
        OK=1; break
      fi
    fi
  done
  if [ "$OK" = "1" ]; then
    echo "✅✅ 插件已装好并验证落地！"
  else
    echo "⚠️  2 分钟内没检测到插件落地。"
    echo "    请打开 Chrome 访问 chrome://extensions 看有没有「众包美食家」。"
    echo "    没有的话：chrome://policy 里点「重新加载政策」，再重启 Chrome。"
  fi
fi

echo
echo "================================================"
echo "  下一步（只此一次）："
echo "  Chrome 里会自动弹出「参与协议」页："
echo "  点【我要加入】自动领编号 → 点【同意并开始使用】"
echo "  之后采集全自动，不用人管。"
if [ "$MODE" = "sideload" ]; then
  echo
  echo "  注意：本机是手动挂载模式（扩展页显示开发者模式属正常）；"
  echo "  以后升级插件：重跑本脚本即可。"
fi
echo "================================================"

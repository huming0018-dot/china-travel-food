#!/usr/bin/env bash
# food-radar 环境自检
# 用法：bash scripts/preflight.sh
# 退出码：0=就绪；1=有阻塞项
# 最后实测：2026-10-17

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MC="$SKILL_DIR/tools/media-crawler"
export PATH="/Users/deuce/.local/bin:$PATH"

fail=0
ok()   { printf '  [ OK ] %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }

# 检查某平台登录态：cookie 的 value 或 encrypted_value 必须非空
check_login() {
  local plat="$1" cookie="$2"
  local db="$MC/browser_data/${plat}_user_data_dir/Default/Cookies"
  [ -f "$db" ] || { warn "$plat 无登录态目录（需首次扫码）"; return; }
  local tmp n
  tmp=$(mktemp /tmp/ck.XXXXXX.db)
  cp "$db" "$tmp" 2>/dev/null || { warn "$plat cookie库不可读"; return; }
  n=$(sqlite3 "$tmp" "SELECT COUNT(*) FROM cookies WHERE name='$cookie' AND (length(value)>0 OR length(encrypted_value)>0);" 2>/dev/null)
  rm -f "$tmp"
  if [ "${n:-0}" -gt 0 ]; then
    ok "$plat 登录态有效（$cookie）"
  else
    warn "$plat 登录态无效/为空（$cookie）→ 需重新扫码"
  fi
}

echo "=============================================="
echo " food-radar 环境自检  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

echo "[1] 运行时"
command -v uv >/dev/null 2>&1 && ok "uv $(uv --version 2>/dev/null | awk '{print $2}')" || bad "uv 未安装"
[ -x /Users/deuce/.local/bin/python3.12 ] && ok "python3.12 $(/Users/deuce/.local/bin/python3.12 -V 2>&1 | awk '{print $2}')" || bad "python3.12 缺失（MediaCrawler 需 >=3.11）"
command -v node >/dev/null 2>&1 && ok "node $(node -v) → 抖音签名可用" || bad "node 未装 → 抖音签名将失败（execjs 需 Nashorn，JDK15+ 已移除，装 Java 无效）"

echo "[2] MediaCrawler 运行环境"
if [ -x "$MC/.venv/bin/python" ]; then
  ok "venv 已建"
  "$MC/.venv/bin/python" -c "import playwright,httpx,requests" 2>/dev/null \
    && ok "依赖完整" || bad "依赖缺失 → uv pip install --python .venv/bin/python -r requirements.txt"
  [ -d "$HOME/Library/Caches/ms-playwright/chromium-1248" ] \
    && ok "chromium 已安装" || bad "chromium 缺失 → $MC/.venv/bin/playwright install chromium"
else
  bad "venv 缺失 → cd tools/media-crawler && uv venv --python 3.12 .venv"
fi
grep -q '^ENABLE_CDP_MODE = False' "$MC/config/base_config.py" 2>/dev/null \
  && ok "CDP 模式已停用（本机不可用，见 environment.md 3.2）" \
  || warn "ENABLE_CDP_MODE 非 False → CDP 在本机会失败并浪费时间"

echo "[3] 平台登录态（扫码持久化，免重复扫码）"
check_login xhs web_session
check_login dy sessionid

echo "[4] Agent-Reach"
if command -v agent-reach >/dev/null 2>&1; then
  ok "已安装（$(agent-reach --version 2>/dev/null || echo v?)）"
  n=$(agent-reach doctor 2>/dev/null | grep -oE '[0-9]+/16' | head -1)
  ok "通路 $n（不含抖音）"
else
  warn "未安装 → cd tools/agent-reach && uv tool install ."
fi

echo "[5] 大众点评"
DP="$SKILL_DIR/browser_data/dianping_user_data_dir"
if [ -f "$DP/Default/Cookies" ]; then
  tmp=$(mktemp /tmp/dp.XXXXXX.db); cp "$DP/Default/Cookies" "$tmp" 2>/dev/null
  n=$(sqlite3 "$tmp" "SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%dianping%' AND (length(value)>0 OR length(encrypted_value)>0);" 2>/dev/null)
  rm -f "$tmp"
  if [ "${n:-0}" -gt 0 ]; then ok "点评登录态有效（非空 cookie ${n}）"; else warn "点评登录态为空 → 需重新登录"; fi
else
  warn "点评无登录态目录 → 首次需人工登录一次（手机号+验证码）"
fi
if [ -f "$SKILL_DIR/scripts/dianping_fetch.py" ]; then ok "点评采集器就位"; else bad "缺少 scripts/dianping_fetch.py"; fi
warn "注意：必须 headful + 持久化登录；选择器用 a[href*='/shop/']（div.shop-wrap 已失效）"

echo "[6] Java 工具链（备用）"
T="/Users/deuce/CodeBuddy/Claw/toolchain"
if [ -d "$T/jdk-21.0.12.1+1" ]; then ok "JDK 21 已装"; else warn "JDK 未装（当前无 Java 工具必需）"; fi
if [ -d "$T/apache-maven-3.9.16" ]; then ok "Maven 3.9.16 已装"; else warn "Maven 未装"; fi

echo "=============================================="
if [ "$fail" -eq 0 ]; then
  echo " 结果：无阻塞项，可执行检索"
else
  echo " 结果：存在阻塞项，请按上方提示补齐"
fi
echo "=============================================="
exit "$fail"
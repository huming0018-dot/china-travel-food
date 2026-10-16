#!/usr/bin/env bash
# food-radar 环境自检
# 用法：bash scripts/preflight.sh
# 退出码：0=全部就绪；1=有阻塞项（详见输出）

set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$SKILL_DIR/tools"
export PATH="/Users/deuce/.local/bin:$PATH"

fail=0
ok()   { printf '  [ OK ] %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1"; }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=1; }

echo "=============================================="
echo " food-radar 环境自检  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

echo "[1] 运行时"
if command -v uv >/dev/null 2>&1; then ok "uv: $(uv --version 2>/dev/null)"; else bad "uv 未安装（brew install uv）"; fi
if [ -x /Users/deuce/.local/bin/python3.12 ]; then
  ok "python3.12: $(/Users/deuce/.local/bin/python3.12 -V 2>&1)"
else
  bad "python3.12 缺失（MediaCrawler 需 >=3.11，系统 python3.9 不可用）"
fi
if command -v node >/dev/null 2>&1; then
  ok "node: $(node -v)"
else
  warn "node 未安装 → wechat-article-search 通路不可用"
fi

echo "[2] MediaCrawler"
if [ -x "$TOOLS/media-crawler/.venv/bin/python" ]; then
  ok "venv 已建"
  if "$TOOLS/media-crawler/.venv/bin/python" -c "import playwright,httpx,requests" 2>/dev/null; then
    ok "依赖完整"
  else
    bad "依赖缺失 → cd tools/media-crawler && uv pip install --python .venv/bin/python -r requirements.txt"
  fi
  if "$TOOLS/media-crawler/.venv/bin/python" -c "import playwright;playwright.sync_api" 2>/dev/null; then
    if [ -d "$HOME/Library/Caches/ms-playwright/chromium-1248" ]; then
      ok "chromium 已安装"
    else
      bad "chromium 缺失 → $TOOLS/media-crawler/.venv/bin/playwright install chromium"
    fi
  fi
  if [ -d "$TOOLS/media-crawler/browser_data" ]; then
    ok "登录态目录存在（请确认 cookie 未过期）"
  else
    warn "尚无登录态 → 首次使用需扫码登录保存 cookie"
  fi
else
  bad "venv 缺失 → cd tools/media-crawler && uv venv --python 3.12 .venv"
fi

echo "[3] Agent-Reach"
if command -v agent-reach >/dev/null 2>&1; then
  ok "agent-reach: $(agent-reach --version 2>/dev/null || echo installed)"
  echo "  ---- 通路明细 ----"
  agent-reach doctor 2>/dev/null | sed 's/^/  /' | tail -n 20
else
  bad "agent-reach 未安装 → cd tools/agent-reach && uv tool install ."
fi

echo "[4] 大众点评"
if [ -d "$TOOLS/dianping-crawler" ]; then
  # 注意：macOS 的 /usr/bin/java 存根在无 JRE 时也返回 0，必须匹配版本号才算可用
  if java -version 2>&1 | head -1 | grep -qE 'version "[0-9]'; then
    ok "java: $(java -version 2>&1 | head -1)"
  else
    warn "无 Java 运行时 → dianping-crawler 不可构建，点评走 agent-browser 降级"
  fi
  if command -v mvn >/dev/null 2>&1; then ok "maven 可用"; else warn "无 Maven → dianping-crawler 不可构建"; fi
else
  warn "未克隆 → git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler"
fi

echo "[5] 浏览器自动化"
for b in agent-browser playwright-cli; do
  if ls "${HOME}/.codebuddy/skills/$b/SKILL.md" >/dev/null 2>&1; then ok "$b skill 已安装"; else warn "$b 未安装（点评/小红书详情页兜底方案）"; fi
done

echo "=============================================="
if [ "$fail" -eq 0 ]; then
  echo " 结果：就绪，可执行标准检索"
else
  echo " 结果：存在阻塞项，请按上方提示补齐后再开工"
fi
echo "=============================================="
exit "$fail"
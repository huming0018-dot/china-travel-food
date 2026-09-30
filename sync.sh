#!/bin/bash
# sync.sh — 跨窗口自动同步（v2）
#
# 用法：
#   开始工作:  bash sync.sh <角色>
#   结束工作:  bash sync.sh push "提交说明"
#
# 角色注册在 ROLES.md，新增窗口直接添加即可。
# 运行前自动校验：git对齐、环境配置、角色边界。

set -e
cd "$(dirname "$0")"

ROLE="${1:-}"

# ────────────────────── push模式 ──────────────────────
if [ "$ROLE" = "push" ]; then
  MSG="${2:-更新状态 $(date '+%H:%M')}"
  git add -A
  git commit -m "$MSG" --allow-empty
  git push
  echo "✅ 已push: $MSG"
  exit 0
fi

# ────────────────────── 校验：角色名 ──────────────────────
if [ -z "$ROLE" ]; then
  echo "❌ 用法: bash sync.sh <角色名>"
  echo ""
  echo "已注册角色（见 ROLES.md）:"
  grep "^### " ROLES.md 2>/dev/null | sed 's/### /  - /' || echo "  (ROLES.md不存在)"
  exit 1
fi

# ────────────────────── 运行前校验 ──────────────────────
echo "════════════════════════════════════════"
echo "  CTFS 同步 · $ROLE 窗口"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

CHECKS_PASS=0
CHECKS_FAIL=0

check() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  ✅ $desc"
    CHECKS_PASS=$((CHECKS_PASS+1))
  else
    echo "  ❌ $desc"
    CHECKS_FAIL=$((CHECKS_FAIL+1))
  fi
}

echo ""
echo "🔍 运行前校验:"
check "Git仓库已初始化" "git rev-parse --git-dir"
check "项目根目录正确" "test -f cloud/public_status.py"
check "ROLES.md存在（角色边界）" "test -f ROLES.md"
check "STATUS.md存在（状态快照）" "test -f STATUS.md"
check "task_helper.py存在（任务队列）" "test -f cloud/task_helper.py"

# git对齐检查
echo "  📥 拉取最新代码..."
git pull --rebase 2>/dev/null || git pull 2>/dev/null || echo "  ⚠️  pull失败，请手动解决"

# 未commit更改
if git diff --quiet && git diff --cached --quiet; then
  echo "  ✅ 工作区干净"
  CHECKS_PASS=$((CHECKS_PASS+1))
else
  UNCOMMITTED=$(git status --short | wc -l | tr -d ' ')
  echo "  ⚠️  有${UNCOMMITTED}个未commit文件"
fi

echo ""
echo "  校验结果: ${CHECKS_PASS}通过 / ${CHECKS_FAIL}失败"
if [ $CHECKS_FAIL -gt 0 ]; then
  echo "  ⚠️  有校验未通过，请先修复再工作"
fi

# ────────────────────── 角色边界提示 ──────────────────────
echo ""
echo "📋 角色边界（$ROLE）:"
if [ -f ROLES.md ]; then
  awk "/^### $ROLE/,/^### |^## /" ROLES.md 2>/dev/null | head -8 || echo "  (未在ROLES.md注册)"
fi

# ────────────────────── 公共状态快照 ──────────────────────
echo ""
echo "📊 公共状态:"
if command -v python3 &>/dev/null; then
  python3 cloud/public_status.py 2>/dev/null || echo "  (公共状态获取失败)"
else
  echo "  (python3不可用)"
fi

# ────────────────────── 任务队列 ──────────────────────
echo ""
echo "📌 我的任务（$ROLE）:"
python3 cloud/task_helper.py list "$ROLE" 2>/dev/null || echo "  (任务队列不可用)"

# ────────────────────── 最近commit ──────────────────────
echo ""
echo "📝 最近5条commit:"
git log --oneline -5 2>/dev/null || echo "  (无)"

# ────────────────────── 结束提示 ──────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  完成后: bash sync.sh push \"说明\""
echo "  任务: python3 cloud/task_helper.py list"
echo "════════════════════════════════════════"

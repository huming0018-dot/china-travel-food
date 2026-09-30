#!/bin/bash
# sync.sh — 跨窗口自动同步脚本
# 用法：
#   开发窗口:   bash sync.sh dev
#   采集窗口:   bash sync.sh collector
#   QA窗口:     bash sync.sh qa
#
# 每个窗口开始工作时运行此脚本，结束工作时运行:
#   bash sync.sh push "commit message"

set -e
cd "$(dirname "$0")"

ROLE="${1:-qa}"
ROLE_CN="QA监管官"
case "$ROLE" in
  dev) ROLE_CN="开发" ;;
  collector) ROLE_CN="采集" ;;
esac

if [ "$2" = "push" ]; then
  MSG="${3:-更新状态 $(date '+%H:%M')}"
  git add -A
  git commit -m "$MSG" --allow-empty
  git push
  echo "✅ 已push: $MSG"
  exit 0
fi

echo "════════════════════════════════════════"
echo "  CTFS 同步 · $ROLE_CN 窗口"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

# 1. 拉取最新代码
echo ""
echo "📥 拉取最新代码..."
git pull --rebase 2>/dev/null || git pull 2>/dev/null || echo "  (pull跳过)"

# 2. 显示状态快照
echo ""
echo "📋 当前状态（STATUS.md）:"
echo "────────────────────────────────────────"
if [ -f STATUS.md ]; then
  head -40 STATUS.md
else
  echo "  (STATUS.md不存在)"
fi

# 3. 显示P0问题
echo ""
echo "🔴 P0问题（QUALITY_ISSUES.md）:"
echo "────────────────────────────────────────"
if [ -f QUALITY_ISSUES.md ]; then
  grep -A2 "P0.*open\|P0.*verifying" QUALITY_ISSUES.md | head -15 || echo "  无P0 open问题"
else
  echo "  (QUALITY_ISSUES.md不存在)"
fi

# 4. 显示任务队列
echo ""
echo "📌 任务队列（task_queue）:"
echo "────────────────────────────────────────"
if command -v python3 &>/dev/null; then
  python3 cloud/task_helper.py list "$ROLE" 2>/dev/null || echo "  (任务表可能还没建，需执行017_task_queue.sql)"
else
  echo "  (python3不可用)"
fi

# 5. 显示最近commit
echo ""
echo "📝 最近5条commit:"
echo "────────────────────────────────────────"
git log --oneline -5 2>/dev/null || echo "  (无)"

echo ""
echo "════════════════════════════════════════"
echo "  工作完成后运行: bash sync.sh push \"提交说明\""
echo "════════════════════════════════════════"

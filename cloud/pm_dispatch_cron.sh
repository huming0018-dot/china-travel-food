#!/bin/bash
# pm_dispatch_cron.sh — PM调度器 cron 包装（每15分钟跑一次）
# 负责:载入项目环境变量+代理 → 跑 pm_dispatch.py --once → 记日志
# 部署: crontab 加一行  */15 * * * * <本项目>/cloud/pm_dispatch_cron.sh >> <日志> 2>&1
set -euo pipefail

PROJ="/Users/deuce/Doubao/chats/2026-09-29/new-chat/china-travel-food"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7897}"
export FOOD_APP_DIR="$PROJ/app"
export FOOD_DATA_DIR="$PROJ/.pm_dispatch_data"
export PM_DISPATCH_LOG="$PROJ/.pm_dispatch_data/dispatch.log"

# Python: 优先用沙箱runtime(含requests等依赖); 否则回退系统python3
PYBIN="/Users/deuce/Library/Application Support/Doubao/sandbox_runtime/bases/98670218a5f0d8bc9b9ebf3f70881304/bin/python3"
if [ ! -x "$PYBIN" ]; then
  PYBIN="/usr/bin/python3"
fi

mkdir -p "$FOOD_DATA_DIR"

# 载入通知凭据（deploy.env 为 gitignored 本机文件）
if [ -f "$PROJ/cloud/deploy.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$PROJ/cloud/deploy.env"
  set +a
fi

cd "$PROJ"
exec "$PYBIN" cloud/pm_dispatch.py --once

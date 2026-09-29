#!/usr/bin/env bash
# build_sync.sh — 构建前把持久仓库（origin/main）的最新 cloud/*.py 与 pipeline/*.py
# 同步到服务器构建上下文（~/food-cloud），根治「docker cp 补脚本、重建后丢失」。
#
# 用法：在服务器 ~/food-cloud 里执行：
#   bash cloud/build_sync.sh          # 同步并重新 build + compose up
#   bash cloud/build_sync.sh --no-build # 只同步不 build
#
# 设计：
#   - 不直接覆盖构建目录为 git worktree，避免碰 deploy.env / xhs_accounts（gitignored/本地凭据）；
#     只 rsync 脚本文件，保留构建目录里的凭据与 cookie。
#   - 以 origin/main 为唯一真相；构建上下文是从仓库生成的快照。
set -euo pipefail

REPO_URL="${FOOD_REPO_URL:-https://github.com/hung0018-dot/china-travel-food.git}"
SRC_DIR="${FOOD_SRC_CACHE:-$HOME/food-src}"
BUILD_DIR="${FOOD_BUILD_DIR:-$HOME/food-cloud}"

echo "==> [1/4] 同步 origin/main 到缓存 $SRC_DIR"
if [ -d "$SRC_DIR/.git" ]; then
  git -C "$SRC_DIR" fetch --depth=1 origin main
  git -C "$SRC_DIR" reset --hard origin/main
else
  git clone --depth=1 --branch main "$REPO_URL" "$SRC_DIR"
fi

echo "==> [2/4] rsync cloud/*.py -> $BUILD_DIR/"
mkdir -p "$BUILD_DIR"
rsync -a --include='*.py' --exclude='*' "$SRC_DIR/cloud/" "$BUILD_DIR/"

echo "==> [3/4] rsync pipeline/*.py -> $BUILD_DIR/vendor/pipeline/"
mkdir -p "$BUILD_DIR/vendor/pipeline"
rsync -a --include='*.py' --exclude='*' "$SRC_DIR/pipeline/" "$BUILD_DIR/vendor/pipeline/"
# 同步构建所需非 .py 资产（Dockerfile/crontab/entrypoint/requirements）
for f in Dockerfile crontab.txt entrypoint.sh requirements.txt docker-compose.yml; do
  [ -f "$SRC_DIR/cloud/$f" ] && cp -f "$SRC_DIR/cloud/$f" "$BUILD_DIR/$f"
done

echo "==> 同步完成。构建上下文 cloud/*.py 数：$(ls "$BUILD_DIR"/*.py | wc -l)，pipeline/*.py 数：$(ls "$BUILD_DIR"/vendor/pipeline/*.py | wc -l)"

if [ "${1:-}" != "--no-build" ]; then
  echo "==> [4/4] docker build + compose up"
  cd "$BUILD_DIR"
  docker build -t food-cloud:local .
  docker compose up -d
  sleep 3
  docker compose ps
  echo "BUILD_SYNC_DONE"
fi

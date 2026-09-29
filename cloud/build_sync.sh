#!/usr/bin/env bash
# build_sync.sh — 构建前把 origin/main 最新代码同步到服务器构建上下文（~/food-cloud），
# 根治「docker cp 补脚本、重建后丢失」。服务器经 SSH deploy key 拉取 GitHub。
#
# 用法：在服务器执行 `bash ~/food-cloud/build_sync.sh`（同步+build+compose up）
#       `bash ~/food-cloud/build_sync.sh --no-build`（只同步）
#
# 设计：
#   - 服务器已有 SSH 浅克隆 ~/china-travel-food（git@github.com），build 前 fetch+reset --hard origin/main；
#   - rsync cloud/*.py、pipeline/*.py 到构建上下文；不碰 deploy.env / xhs_accounts（本地凭据）。
set -euo pipefail

REPO_URL="${FOOD_REPO_URL:-git@github.com:huming0018-dot/china-travel-food.git}"
SRC_DIR="${FOOD_SRC_CACHE:-$HOME/china-travel-food}"
BUILD_DIR="${FOOD_BUILD_DIR:-$HOME/food-cloud}"

echo "==> [1/4] 拉取 origin/main -> $SRC_DIR"
if [ -d "$SRC_DIR/.git" ]; then
  git -C "$SRC_DIR" fetch --depth=1 origin main
  git -C "$SRC_DIR" reset --hard origin/main
else
  git clone --depth=1 --branch main "$REPO_URL" "$SRC_DIR"
fi
HEAD=$(git -C "$SRC_DIR" rev-parse --short HEAD)
echo "    build 基于 commit: $HEAD"

echo "==> [2/4] rsync cloud/*.py -> $BUILD_DIR/"
mkdir -p "$BUILD_DIR"
rsync -a --include='*.py' --exclude='*' "$SRC_DIR/cloud/" "$BUILD_DIR/"

echo "==> [3/4] rsync pipeline/*.py -> $BUILD_DIR/vendor/pipeline/"
mkdir -p "$BUILD_DIR/vendor/pipeline"
rsync -a --include='*.py' --exclude='*' "$SRC_DIR/pipeline/" "$BUILD_DIR/vendor/pipeline/" 2>/dev/null || true
for f in Dockerfile crontab.txt entrypoint.sh requirements.txt docker-compose.yml; do
  [ -f "$SRC_DIR/cloud/$f" ] && cp -f "$SRC_DIR/cloud/$f" "$BUILD_DIR/$f"
done
echo "    cloud/*.py=$(ls "$BUILD_DIR"/*.py | wc -l)  pipeline/*.py=$(ls "$BUILD_DIR"/vendor/pipeline/*.py | wc -l)"

if [ "${1:-}" != "--no-build" ]; then
  echo "==> [4/4] docker build + compose up"
  cd "$BUILD_DIR"
  sudo docker build -t food-cloud:local .
  sudo docker compose up -d
  sleep 3
  sudo docker compose ps
  echo "BUILD_SYNC_DONE based on $HEAD"
fi

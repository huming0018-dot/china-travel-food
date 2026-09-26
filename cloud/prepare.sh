#!/bin/bash
# prepare.sh — 构建镜像前，在本机把当前管线快照复制到构建上下文 cloud/vendor/pipeline
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline"

if [ ! -d "$SRC" ]; then
  echo "找不到管线目录: $SRC"
  exit 1
fi
rm -rf "$HERE/vendor/pipeline"
mkdir -p "$HERE/vendor"
cp -R "$SRC" "$HERE/vendor/pipeline"
find "$HERE/vendor/pipeline" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$HERE/vendor/pipeline" -name '*.pyc' -delete 2>/dev/null || true
echo "管线快照已复制到 cloud/vendor/pipeline（构建时将被打进镜像）"

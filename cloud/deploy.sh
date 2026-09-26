#!/usr/bin/env bash
# deploy.sh — 服务器端一键部署（Ubuntu/Debian，幂等，可重复执行）
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/5] 检查 Docker"
if ! command -v docker >/dev/null 2>&1; then
  echo "未检测到 Docker，使用国内镜像源安装..."
  curl -fsSL https://get.docker.com | sh -s -- --mirror Aliyun
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "安装 compose 插件..."
  (apt-get update && apt-get install -y docker-compose-plugin) || \
  curl -fsSL https://get.docker.com | sh -s -- --mirror Aliyun
fi

echo "==> [2/5] 加载镜像"
if [ -f food-cloud-image.tgz ]; then
  docker load -i food-cloud-image.tgz
elif ! docker image inspect food-cloud:local >/dev/null 2>&1; then
  echo "无镜像包且本机无镜像，现场构建（服务器需能拉取基础镜像）..."
  docker build -t food-cloud:local .
fi

echo "==> [3/5] 准备配置"
[ -f deploy.env ] || cp deploy.env.template deploy.env
[ -f xhs_cookies.json ] || { echo "缺少 xhs_cookies.json"; exit 1; }

echo "==> [4/5] 启动常驻服务"
docker compose up -d

echo "==> [5/5] 状态"
sleep 3
docker compose ps
echo "DEPLOY_DONE — 查看实时日志: docker compose logs -f"

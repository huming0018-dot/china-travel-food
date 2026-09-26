#!/usr/bin/env bash
# build_on_server.sh — 在服务器（amd64）原生构建，全国内源；省掉跨架构编译与 974MB 镜像上传。可重复执行。
set -uo pipefail
export COPYFILE_DISABLE=1   # macOS tar 不生成 ._ AppleDouble（否则在 Linux 上变成非 UTF-8 的 ._*.py）
cd "$(dirname "$0")"
KEY="$HOME/.ssh/food_cloud_deploy"
HOST=ubuntu@49.234.35.92
RDIR=/home/ubuntu/food-cloud
SSH(){ ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$HOST" "$@"; }
SCP(){ scp -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$@"; }

echo "==> [1/6] 配置 Docker Hub 腾讯云内网 mirror"
SSH "echo '{\"registry-mirrors\":[\"https://mirror.ccs.tencentyun.com\"]}' | sudo tee /etc/docker/daemon.json >/dev/null && sudo systemctl restart docker && echo MIRROR_OK"

echo "==> [2/6] 打包构建上下文（不含大镜像/分片）"
tar czf server-context.tgz \
  Dockerfile requirements.txt fix_paths.py cloud_bu.py health.py run_batch.py \
  crontab.txt entrypoint.sh map_helpers.py cloud_phone_fill.py cloud_coord_fill.py cloud_hours_fill.py cloud_review_fill.py vendor
ls -lh server-context.tgz | awk '{print "context 大小:",$5}'

echo "==> [3/6] 上传上下文与运行配置"
SSH "mkdir -p $RDIR"
for f in server-context.tgz docker-compose.yml deploy.env xhs_cookies.json; do
  ok=0
  for a in 1 2 3 4; do SCP "$f" "$HOST:$RDIR/$f" >/dev/null 2>&1 && { echo "$f OK"; ok=1; break; }; sleep 1; done
  [ "$ok" = 1 ] || { echo "$f FAILED"; exit 1; }
done

echo "==> [4/6] 清理旧 arm64 镜像/大文件并解压"
SSH "cd $RDIR && sudo docker compose down 2>/dev/null; sudo docker image rm -f food-cloud:local 2>/dev/null; rm -rf vendor chunks food-cloud-image.tgz server-context; tar xzf server-context.tgz; find . -name '._*' -delete; echo EXTRACT_OK"

echo "==> [5/6] 服务器原生构建 amd64 镜像"
SSH "cd $RDIR && sudo docker build -t food-cloud:local ."

echo "==> [6/6] 启动并验证"
SSH "cd $RDIR && sudo docker compose up -d && sleep 8 && sudo docker compose ps"
echo "BUILD_ON_SERVER_DONE"

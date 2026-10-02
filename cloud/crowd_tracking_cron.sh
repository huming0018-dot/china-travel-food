#!/bin/bash
# crowd_tracking_cron.sh — 众包回流 tracking 报告（每小时）
# 部署: crontab 加一行  7 * * * * /home/ubuntu/china-travel-food/cloud/crowd_tracking_cron.sh >> /home/ubuntu/china-travel-food/.data/crowd_tracking.log 2>&1
# 注意: 服务器直连 Supabase（无本地代理 127.0.0.1:7897，那是 mac 本机端口）
set -uo pipefail
PROJ="/home/ubuntu/china-travel-food"
unset HTTPS_PROXY http_proxy https_proxy HTTP_PROXY
export FOOD_APP_DIR="$PROJ/app"
export FOOD_DATA_DIR="$PROJ/.data"
mkdir -p "$PROJ/.data"
if [ -f /home/ubuntu/food-cloud/deploy.env ]; then
  set -a; source /home/ubuntu/food-cloud/deploy.env; set +a
fi
cd "$PROJ"
exec /usr/bin/python3 cloud/crowd_tracking.py >> "$PROJ/.data/crowd_tracking.log" 2>&1

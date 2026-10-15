#!/bin/bash
# crowd_autoscale_cron.sh — 众包去重扩容自动看护（每 6 小时，与 crowd_tracking 错峰）
# 部署: crontab 加一行
#   23 */6 * * * /home/ubuntu/china-travel-food/cloud/crowd_autoscale_cron.sh >> /home/ubuntu/china-travel-food/.data/crowd_autoscale.log 2>&1
# 逻辑：open 包低于 MIN_OPEN 才补到 TARGET_OPEN，单次最多 MAX_NEW_PACKS 包；
#       严格去重（已 accepted 的店 + 所有任务包店），候选优先口味分缺口店；
#       水位够则什么都不发。直连 Supabase（无本地代理）。
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
exec /usr/bin/python3 cloud/crowd_autoscale.py --apply

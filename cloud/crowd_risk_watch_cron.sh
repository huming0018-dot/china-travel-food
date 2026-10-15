#!/bin/bash
# crowd_risk_watch_cron.sh — 众包采集器风控信号自动看护（v3.5.3，每 10 分钟）
# 部署（crontab）：
#   */10 * * * * /home/ubuntu/china-travel-food/cloud/crowd_risk_watch_cron.sh \
#       >> /home/ubuntu/china-travel-food/.data/crowd_risk_watch.log 2>&1
# 逻辑：读 crowd_risk_log 新信号 → 账号处罚/登录失效置 quota_day=0 并推 TG；
#       验证码/频繁密集出现告警；每天北京 18:00 后做一次日产量骤降检查。
#       直连 Supabase（无本地代理），TG 走 Edge tg-relay。
set -uo pipefail
PROJ="/home/ubuntu/china-travel-food"
unset HTTPS_PROXY http_proxy https_proxy HTTP_PROXY
export FOOD_DATA_DIR="$PROJ/.data"
mkdir -p "$PROJ/.data"
if [ -f /home/ubuntu/food-cloud/deploy.env ]; then
  set -a; source /home/ubuntu/food-cloud/deploy.env; set +a
fi
cd "$PROJ"
exec /usr/bin/python3 cloud/crowd_risk_watch.py

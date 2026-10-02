#!/bin/bash
# 出餐方式（production_model）云端采集 wrapper：runner 写 findings，gate 写库。
# 用法：food_production.sh [auto|full]
set -u
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MODE="${1:-auto}"
if [ "$MODE" = "full" ]; then
  /usr/bin/sudo docker exec -e FORCE=full -e RUN_BATCH=8 food-cloud sh -c \
    'cd /app/cloud && . /app/cloud/env.sh && python3 -u production_runner.py'
else
  /usr/bin/sudo docker exec -e RUN_BATCH=6 food-cloud sh -c \
    'cd /app/cloud && . /app/cloud/env.sh && python3 -u production_runner.py'
fi
/usr/bin/sudo docker exec food-cloud sh -c \
  'cd /app/cloud && . /app/cloud/env.sh && python3 -u gate_apply.py --apply'

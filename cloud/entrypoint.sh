#!/bin/bash
# entrypoint.sh — 容器入口：固化环境变量供 cron 使用、安装并启动 cron、可选立即跑一轮
set -e

ENVF=/app/cloud/env.sh
: > "$ENVF"
# cron 不继承 `docker run -e` 传入的变量，这里把需要的变量安全写入文件供每轮 source
for v in FOOD_PIPELINE_DIR FOOD_DATA_DIR \
         NEXT_PUBLIC_SUPABASE_URL SUPABASE_SERVICE_ROLE_KEY NEXT_PUBLIC_SUPABASE_ANON_KEY \
         XHS_COOKIE XHS_COOKIE_FILE ALERT_WEBHOOK BATCH TZ \
         TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID TELEGRAM_API_BASE \
         FEISHU_WEBHOOK FEISHU_SECRET FEISHU_APP_ID FEISHU_APP_SECRET FEISHU_CHAT_ID FEISHU_API_BASE \
         TENCENT_MAP_KEY TENCENT_MAP_SK AMAP_KEY AMAP_SK \
         PHONE_FILL_BATCH HOURS_FILL_BATCH COORD_FILL_ENABLED HOURS_FILL_ENABLED \
         ALERT_COOLDOWN_SEC; do
  val=$(printenv "$v" 2>/dev/null || true)
  if [ -n "$val" ]; then
    printf 'export %s=%q\n' "$v" "$val" >> "$ENVF"
  fi
done

crontab /app/cloud/crontab.txt
cron
echo "=== 云端采集服务已启动：cron 每 20 分钟一轮，数据写 /app/data ==="

# RUN_ON_START=1 时容器一起就先跑一轮
if [ "$RUN_ON_START" = "1" ]; then
  . "$ENVF"
  cd /app/cloud
  flock -n /tmp/xhs.lock /usr/local/bin/python run_batch.py || true
fi

# 容器常驻
exec tail -f /dev/null

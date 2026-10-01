#!/bin/bash
# 上海美食图鉴 · worth_fill Apify 自动填充常驻控制器（v3，2026-10-02）
#  - 调度智能全部在 review_apify_fill.py（v4）：每店 attempts 封顶、q1/q2 查询阶梯、
#    持久熔断、日预算闸门；本脚本只负责循环、解析 @@STATUS、排空告警。
#  - 脚本默认离线不付费；这里显式 --fetch --apply --guard。
#  - 主机无 notifier：脚本把告警落 alert_queue.jsonl，本控制器聚合为【一条】经容器转发后清空，
#    额度耗尽只在状态变化/每日首条时提醒，随后长睡，不再每 20 分钟刷屏。
set -u
DIR=/home/ubuntu/food-apify-fill
BATCH=12

# 经容器 notifier 投递：level/key 为固定枚举，正文走 stdin（可含换行/引号）
# 容器内 notifier.py 无 CLI，统一由 notify_cli.py 分发（需已 docker cp 进 /app/cloud）。
deliver() {
  sudo docker exec -i food-cloud bash -c \
    '. /app/cloud/env.sh; python3 /app/cloud/notify_cli.py "$@"' _ "$1" "$2"
}

# 排空 alert_queue.jsonl：多条合并成一条，按最高级别投递，然后清空
drain_alerts() {
  local AQ="$DIR/alert_queue.jsonl"
  [ -s "$AQ" ] || return 0
  local lvl=info
  grep -q '"level": "action"' "$AQ" && lvl=action
  [ "$lvl" = info ] && grep -q '"level": "warn"' "$AQ" && lvl=warn
  python3 -c "import json,sys;print('\n'.join(json.loads(l)['body'] for l in open(sys.argv[1])))" "$AQ" \
    | deliver "$lvl" guard_batch
  : > "$AQ"
}

while true; do
  OUT=$(cd "$DIR" && set -a && . ./fill.env && set +a && \
        python3 review_apify_fill.py --fetch --apply --guard --limit "$BATCH" 2>&1)
  echo "$OUT"
  LINE=$(echo "$OUT" | grep '@@STATUS' | tail -1)
  drain_alerts
  CODE=$(echo "$LINE" | awk '{print $2}')
  SL=$(echo "$LINE" | awk '{print $3}')
  case "$CODE" in
    DONE)
      echo "worth_fill 全部达标，控制器退出。"
      printf '%s' "worth_fill 已全部达到目标，Apify 自动填充完成。" | deliver info guard_done
      exit 0
      ;;
    NO_CREDIT|TOKEN_BAD|CIRCUIT_WAIT|DAILY_CAP|ROUND_CAP)
      echo "[$CODE] 睡 ${SL:-1800}s"
      sleep "${SL:-1800}"
      ;;
    *)
      sleep "${SL:-30}"
      ;;
  esac
done

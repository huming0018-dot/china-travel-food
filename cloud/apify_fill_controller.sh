#!/bin/bash
# 上海美食图鉴 · worth_fill Apify 自动填充常驻控制器（v2，2026-10-02）
#  - 质量优先：opspilot($0.10/次,固定~20条,已验证19/20相关) 为主；zenstudio 备用；
#    toolzerhub 早前烧钱且质量差，移出默认顺序。
#  - 单次脚本调用由 review_apify_fill.ROUND_CAP_USD=2.0 封顶（约20 runs/调用）。
#  - 额度低于 FLOOR 自动等待，充值/月度重置后续跑；全程云端 systemd，不依赖 deuce/MacBook。
cd /home/ubuntu/food-apify-fill || exit 1
set -a; . ./fill.env; set +a
export FOOD_DATA_DIR=/home/ubuntu/food-apify-fill
export FOOD_PIPELINE_DIR=/home/ubuntu/food-apify-fill

NOTIFY(){ # level key body
  body="$3"
  sudo docker exec -i food-cloud bash -lc ". /app/cloud/env.sh; cd /app/cloud; python3 -c \"import notifier,sys; getattr(notifier,sys.argv[1])(sys.argv[2], key=sys.argv[3])\" \"$1\" \"$body\" \"$2\"" >/dev/null 2>&1 || true
}

ORDER="opspilot"
FLOOR=0.25
WAIT=1200

state_vals(){
  eval "$(python3 - <<'PY'
try:
    import review_apify_fill as F
    import entity_match as EM
    try:
        rem = F.remaining_credit()
    except Exception:
        rem = 0.0
    idx = EM.get_index()
    targ = len(F.select_targets(idx, 2))
    print('REM=%.4f' % rem)
    print('TARG=%d' % targ)
except Exception as e:
    # 关键：导入/查询异常用 -1 错误哨兵，绝不能被当成“全部完成(0)”
    print('REM=0.0')
    print('TARG=-1')
    print('ERR=%s' % str(e)[:120])
PY
)"
}

while true; do
  state_vals
  echo "[$(date '+%F %T')] remaining=\$$REM targets=$TARG ${ERR:+err=$ERR}"
  if [ "${TARG:-0}" = "-1" ]; then
    echo "STATE ERROR, retry in 120s"; sleep 120; continue
  fi
  if [ "${TARG:-0}" = "0" ]; then
    NOTIFY info fill_done "worth_fill 队列已全部补齐真实食客口味证据，可停用本填充服务。"
    echo "ALL DONE"; sleep 86400; continue
  fi
  if python3 -c "import sys;sys.exit(0 if float('${REM:-0}')>=$FLOOR else 1)"; then
    :
  else
    NOTIFY warn fill_credit "Apify 本月额度仅剩 $REM 美元（运行地板 $FLOOR），worth_fill 暂停。到 console.apify.com/billing 充值；下月额度重置后本服务自动续跑，无需重启。"
    sleep $WAIT; continue
  fi
  for prov in $ORDER; do
    echo "=== pass provider=$prov $(date '+%T') ==="
    python3 review_apify_fill.py --provider "$prov" --apply --limit 30
    state_vals
    [ "${TARG:-0}" = "-1" ] && { sleep 60; break; }
    [ "${TARG:-0}" = "0" ] && break
    python3 -c "import sys;sys.exit(0 if float('${REM:-0}')>=$FLOOR else 1)" || break
    sleep 5
  done
  NOTIFY info fill_round "Apify 填充一轮结束：剩余待补 $TARG 家，本月剩余额度约 $REM 美元。"
  sleep 30
done

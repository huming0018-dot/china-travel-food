#!/usr/bin/env bash
# llm_apply.sh — 把 LLM 舰队凭据安全注入云端（绝不回显密钥），并立即对运行容器生效 + 验证真实 chat。
#
# 凭据经环境变量传入（deuce 端从 gitignored 文件经 ctfs-run stdin 注入；不落任何产物）：
#   ARK_API_KEY=xxx  HAE_MODELS_ARK="ep-aaa,ep-bbb"   （火山方舟，豆包可联网、DeepSeek 便宜）
#   可选：KIMI_API_KEY/HAE_MODELS_KIMI、QWEN_API_KEY/HAE_MODELS_QWEN、GLM_API_KEY/HAE_MODELS_GLM、
#         MINIMAX_API_KEY/HAE_MODELS_MINIMAX、HUNYUAN_API_KEY/HAE_MODELS_HUNYUAN
#   HAE_WEB_SEARCH=1   （允许联网，召回带来源 URL）
#
# 幂等：同名变量先删后写；容器 env.sh 的 LLM 段整体重建。只动 LLM 相关变量，不碰其它配置。
set -euo pipefail
BUILD_DIR="${FOOD_BUILD_DIR:-$HOME/food-cloud}"
ENVF="$BUILD_DIR/deploy.env"
CN=$(sudo docker ps --format '{{.Names}}' | grep -i food | head -1)
[ -n "$CN" ] || { echo "未找到 food 容器"; exit 1; }

KEYS=(ARK_BASE_URL ARK_API_KEY HAE_MODELS_ARK \
 KIMI_BASE_URL KIMI_API_KEY HAE_MODELS_KIMI \
 QWEN_BASE_URL QWEN_API_KEY HAE_MODELS_QWEN \
 GLM_BASE_URL GLM_API_KEY HAE_MODELS_GLM \
 MINIMAX_BASE_URL MINIMAX_API_KEY HAE_MODELS_MINIMAX \
 HUNYUAN_BASE_URL HUNYUAN_API_KEY HAE_MODELS_HUNYUAN \
 HAE_WEB_SEARCH HAE_GRID_SLICE)

# 1) 合并进宿主 deploy.env（compose env_file；不打印值）
touch "$ENVF"; chmod 600 "$ENVF"
for k in "${KEYS[@]}"; do
  grep -v "^$k=" "$ENVF" > "$ENVF.tmp" || true
  mv "$ENVF.tmp" "$ENVF"
  val="${!k:-}"
  [ -n "$val" ] && printf '%s=%s\n' "$k" "$val" >> "$ENVF"
done
echo "[1/3] deploy.env 已合并（密钥未显示）"

# 2) 重建运行容器 /app/cloud/env.sh 的 LLM 段（立即对 cron 生效，免重建）
sudo docker exec "$CN" bash -c 'grep -vE "^export (ARK|KIMI|QWEN|GLM|MINIMAX|HUNYUAN|HAE_)" /app/cloud/env.sh > /app/cloud/env.sh.new || true; mv /app/cloud/env.sh.new /app/cloud/env.sh'
{
  for k in "${KEYS[@]}"; do
    val="${!k:-}"
    [ -n "$val" ] && printf 'export %s=%q\n' "$k" "$val"
  done
} | sudo docker exec -i "$CN" bash -c 'cat >> /app/cloud/env.sh'
echo "[2/3] 容器 env.sh 的 LLM 段已更新（cron 立即生效）"

# 3) 验证真实 chat（只打印 ok/长度/来源，不打印 key 与正文）
echo "[3/3] 验证 API 连通..."
sudo docker exec "$CN" bash -c '. /app/cloud/env.sh; python - <<"PY"
import sys; sys.path.insert(0,"/app/pipeline")
import model_providers as MP
provs=MP.load_providers()
print("  providers:", [(p.name, list(p.models)) for p in provs])
if not provs:
    print("  WARN: 无可用 provider（检查 key / HAE_MODELS_* 是否非空）"); sys.exit(2)
for p in provs:
    m=list(p.models)[0]
    try:
        r=MP.chat(p,m,"只回两个字：你好", web_search=False, timeout=40)
        print(f"  {p.name}/{m}: ok={r.get('ok')} len={len(r.get('text') or '')} err={r.get('error')}")
    except Exception as e:
        print(f"  {p.name}/{m}: EXC {type(e).__name__}: {e}")
PY'
echo "LLM_APPLY_DONE"
#!/usr/bin/env bash
# =====================================================================
# release.sh — 发布前非阻断检查 + 发布清单/打 tag 骨架（Standard 3 配套）
# ---------------------------------------------------------------------
# 设计铁律：
#   * 默认【只检查、绝不部署】。脚本里没有任何一条会真正 SSH / docker / git push
#     生产的命令；部署指令一律只 echo 给 release owner 看，由人手动执行。
#   * 非阻断：任何单项失败只记 FAIL/WARN 并继续跑完，除非 --strict 才以非零退出。
#   * 不碰 live crontab、不动 /app/data 卷、不碰凭据、不触发部署。
#
# 用法：
#   bash cloud/release.sh                 # 跑全部非阻断检查（默认）
#   bash cloud/release.sh --frontend-build # 额外跑 app/ 的 next build（较慢）
#   bash cloud/release.sh --make-manifest v0.24.0   # 从模板建 docs/releases/ 清单
#   bash cloud/release.sh --tag-dry-run v0.24.0      # 只打印打 tag 命令，不执行
#   bash cloud/release.sh --strict        # 有 FAIL 时退出码非零（供 CI/owner 把关）
#
# 配套规范：docs/standards/standard3_release_sync.md
# =====================================================================
set -u   # 注意：故意不用 set -e —— 非阻断，单项失败不中断后续检查

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

STRICT=0
FRONTEND_BUILD=0
MAKE_MANIFEST=""
TAG_DRY_RUN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --strict) STRICT=1; shift ;;
    --frontend-build) FRONTEND_BUILD=1; shift ;;
    --make-manifest) MAKE_MANIFEST="${2:-}"; shift 2 ;;
    --tag-dry-run) TAG_DRY_RUN="${2:-}"; shift 2 ;;
    *) echo "未知参数: $1"; shift ;;
  esac
done

PASS=0; WARN=0; FAIL=0
ok()  { echo "  ✅ PASS  $1"; PASS=$((PASS+1)); }
warn(){ echo "  🟡 WARN  $1"; WARN=$((WARN+1)); }
bad() { echo "  ❌ FAIL  $1"; FAIL=$((FAIL+1)); }
have(){ [ -e "$1" ]; }

line(){ echo "──────────────────────────────────────────────────────────"; }

echo "CTFS release 检查（非阻断，不部署）· $(date '+%Y-%m-%d %H:%M')"
echo "repo: $ROOT"
line

# ── 0. 只做清单/打 tag 打印的快路径 ──────────────────────────────
if [ -n "$MAKE_MANIFEST" ]; then
  out="docs/releases/$MAKE_MANIFEST.md"
  mkdir -p docs/releases
  if [ -e "$out" ]; then echo "已存在，不覆盖: $out"; else
    cp docs/standards/release_manifest.template.md "$out"
    echo "已生成发布清单: $out （请逐项填写）"
  fi
fi
if [ -n "$TAG_DRY_RUN" ]; then
  echo "  打 tag 命令（回读验证通过后由 owner 手动执行，本脚本不代跑）："
  echo "    git tag -a $TAG_DRY_RUN -m \"release: $TAG_DRY_RUN\""
  echo "    git push origin $TAG_DRY_RUN"
fi

# ── 1. 仓库卫生 ──────────────────────────────────────────────────
echo "[1] 仓库卫生"
if [ "$(git branch --show-current 2>/dev/null)" = "main" ]; then ok "当前在 main"; else warn "当前不在 main（$(git branch --show-current 2>/dev/null)）——发布 owner 注意"; fi
if git diff --quiet && git diff --cached --quiet; then ok "工作区干净"; else warn "有未提交改动：$(git status --short | wc -l | tr -d ' ') 个文件"; fi
git fetch --dry-run origin main >/dev/null 2>&1 && true
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
[ "$BEHIND" = "0" ] && ok "HEAD 对齐 origin/main" || warn "落后 origin/main $BEHIND（先 git pull --rebase）"

# ── 2. 明文密钥扫描（tracked 文件）──────────────────────────────
echo "[2] 明文密钥扫描（tracked, 保守匹配）"
LEAK=$(git grep -nI -E '(service_role|SUPABASE_SERVICE_ROLE_KEY)\s*=\s*"eyJ' -- '*.py' '*.sh' '*.env*' 2>/dev/null | wc -l | tr -d ' ')
[ "$LEAK" = "0" ] && ok "未见硬编码 service_role JWT" || bad "tracked 文件疑似硬编码密钥: $LEAK 处"

# ── 3. 迁移 / schema 物 ──────────────────────────────────────────
echo "[3] 迁移与 schema 物"
LATEST_MIG=$(ls db/migrations/*.sql 2>/dev/null | sort | tail -1)
[ -n "$LATEST_MIG" ] && ok "最新迁移: $(basename "$LATEST_MIG")" || bad "db/migrations 为空"
have db/migrations/024_prior_evidence_separation.sql && ok "024 先验证据分离迁移在库" || bad "缺 024 迁移"

# ── 4. 发布回归 loop / 硬门脚本就位 ─────────────────────────────
echo "[4] 回归 loop / 质量门脚本就位（只读 A–G 在 cloud/vendor/pipeline）"
for f in cloud/vendor/pipeline/release_audit.py cloud/vendor/pipeline/regression_check.py \
         cloud/vendor/pipeline/duplicate_audit.py cloud/vendor/pipeline/fact_evidence_gap.py \
         cloud/reconcile.py cloud/prior_separate.py cloud/apify_ingest.py cloud/code_audit.py; do
  have "$f" && ok "$f" || bad "缺 $f"
done
echo "  ℹ release_audit A–G 的真跑需在容器内（有 Supabase env）执行："
echo "    python3 /app/pipeline/release_audit.py  （本脚本不代跑，避免本机无 env 误报）"

# ── G1 权威计数 ─────────────────────────────────────────────────
echo "[G1] 权威计数 / reconcile 桥接"
have cloud/reconcile.py && ok "cloud/reconcile.py 编排链在库" || bad "缺 reconcile.py"
if grep -q "reconcile.py" cloud/crontab.txt; then
  ok "crontab 已接 reconcile 编排"
else
  warn "crontab.txt 07:47 仍直跑 post_audit.py，未切到 reconcile.py（真漂移；本轮按要求不改 crontab，由 owner 确认）"
fi

# ── G2 先验证据分离 ─────────────────────────────────────────────
echo "[G2] 先验 vs 证据列分离（硬门不得读 *_prior）"
PRIOR_LEAK=$(grep -lE '_prior' cloud/reconcile.py cloud/vendor/pipeline/curate_score.py 2>/dev/null | wc -l | tr -d ' ')
[ "$PRIOR_LEAK" = "0" ] && ok "硬门脚本未消费 *_prior 列" || bad "硬门脚本疑似读了 *_prior: $(grep -lE '_prior' cloud/reconcile.py cloud/vendor/pipeline/curate_score.py 2>/dev/null | tr '\n' ' ')"
have cloud/prior_separate.py && ok "cloud/prior_separate.py 在库" || bad "缺 prior_separate.py"

# ── G3 前端接线 ────────────────────────────────────────────────
echo "[G3] 前端接线（精选层/连锁列）"
for p in app/pages/index.tsx app/pages/restaurants/index.tsx "app/pages/restaurants/[id].tsx"; do
  have "$p" && ok "$p 存在" || bad "缺 $p"
done
WIRED=$(grep -lE 'curate|chain_type|premade|central_kitchen' app/pages/index.tsx app/pages/restaurants/index.tsx "app/pages/restaurants/[id].tsx" 2>/dev/null | wc -l | tr -d ' ')
[ "$WIRED" -ge 1 ] && ok "$WIRED 个页面引用接线列" || bad "前端页面未见 curate/chain 列引用"
if [ "$FRONTEND_BUILD" = "1" ]; then
  echo "  ▶ 跑 next build（app/）..."
  (cd app && npm run build) && ok "next build 通过" || bad "next build 失败"
else
  warn "跳过 next build（加 --frontend-build 才跑；发布前建议真跑一次）"
fi

# ── G4 孤立清理 ─────────────────────────────────────────────────
echo "[G4] 孤立清理 / 仓库排雷"
STRAY=$(ls cloud/_*.py cloud/vendor/pipeline/_*.py 2>/dev/null | wc -l | tr -d ' ')
[ "$STRAY" = "0" ] && ok "构建上下文无游离 _*.py 过程稿" || warn "发现游离过程稿 $STRAY 个：$(ls cloud/_*.py cloud/vendor/pipeline/_*.py 2>/dev/null | tr '\n' ' ')"
if command -v python3 >/dev/null 2>&1; then
  REPORT=$(python3 cloud/code_audit.py --report 2>/dev/null | tail -1) && ok "code_audit 已跑（见 AUDIT_REPORT.md）：$REPORT" || warn "code_audit 退出非零，人工看 AUDIT_REPORT.md"
else
  warn "本机无 python3，跳过 code_audit"
fi

# ── G5 Apify 核验 ─────────────────────────────────────────────
echo "[G5] Apify 采集链路"
have cloud/apify_ingest.py && ok "cloud/apify_ingest.py 在库" || bad "缺 apify_ingest.py"
if [ -n "${APIFY_TOKEN:-}" ]; then ok "APIFY_TOKEN 已注入"; else warn "本机未见 APIFY_TOKEN（容器/服务器 env 内是否已配需 owner 确认；不代跑扣费小样）"; fi

# ── 5. 部署指引（只打印，绝不执行）─────────────────────────────
line
echo "部署指引（以下命令仅打印，由 release owner 手动执行；本脚本不代跑）："
echo "  前端:  push origin main → Vercel(Root=app/) 自动构建"
echo "  容器:  ssh -i ~/.ssh/food_cloud_deploy ubuntu@49.234.35.92"
echo "         bash ~/food-cloud/build_sync.sh   # fetch+reset origin/main → rsync → docker build → compose up"
echo "  回读:  docker compose ps ; python3 /app/pipeline/release_audit.py"
echo "  播报:  python3 -c 'import notifier; notifier.info(\"release vX.Y.Z deployed\")'  # 容器内"
line
echo "汇总: PASS=$PASS  WARN=$WARN  FAIL=$FAIL"
if [ "$FAIL" -gt 0 ] && [ "$STRICT" = "1" ]; then
  echo "存在未解释 FAIL（--strict）——不要在解释清楚前开发布。"
  exit 1
fi
echo "检查完成（非阻断，退出 0）。ERROR=0 且无未解释 FAIL 才进入合并/部署。"
exit 0

#!/bin/bash
# sync.sh — 跨窗口自动同步（v2）
#
# 用法：
#   开始工作:  bash sync.sh <角色>
#   结束工作:  bash sync.sh push "提交说明"
#
# 角色注册在 ROLES.md，新增窗口直接添加即可。
# 运行前自动校验：git对齐、环境配置、角色边界。

set -e
cd "$(dirname "$0")"

ROLE="${1:-}"

# ────────────────────── push模式 ──────────────────────
if [ "$ROLE" = "push" ]; then
  MSG="${2:-更新状态 $(date '+%H:%M')}"
  git add -A
  git commit -m "$MSG" --allow-empty
  git push
  echo "✅ 已push: $MSG"
  exit 0
fi

# ────────────────────── 校验：角色名 ──────────────────────
if [ -z "$ROLE" ]; then
  echo "❌ 用法: bash sync.sh <角色名>"
  echo ""
  echo "已注册角色（见 ROLES.md）:"
  grep "^### " ROLES.md 2>/dev/null | sed 's/### /  - /' || echo "  (ROLES.md不存在)"
  exit 1
fi

# ────────────────────── 运行前校验 ──────────────────────
echo "════════════════════════════════════════"
echo "  CTFS 同步 · $ROLE 窗口"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

CHECKS_PASS=0
CHECKS_FAIL=0

check() {
  local desc="$1"
  local cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  ✅ $desc"
    CHECKS_PASS=$((CHECKS_PASS+1))
  else
    echo "  ❌ $desc"
    CHECKS_FAIL=$((CHECKS_FAIL+1))
  fi
}

echo ""
echo "🔍 运行前校验:"
check "Git仓库已初始化" "git rev-parse --git-dir"
check "项目根目录正确" "test -f cloud/public_status.py"
check "ROLES.md存在（角色边界）" "test -f ROLES.md"
check "STATUS.md存在（状态快照）" "test -f STATUS.md"
check "task_helper.py存在（任务队列）" "test -f cloud/task_helper.py"

# git对齐检查
echo "  📥 拉取最新代码..."
git pull --rebase 2>/dev/null || git pull 2>/dev/null || echo "  ⚠️  pull失败，请手动解决"

# 未commit更改
if git diff --quiet && git diff --cached --quiet; then
  echo "  ✅ 工作区干净"
  CHECKS_PASS=$((CHECKS_PASS+1))
else
  UNCOMMITTED=$(git status --short | wc -l | tr -d ' ')
  echo "  ⚠️  有${UNCOMMITTED}个未commit文件"
fi

echo ""
echo "  校验结果: ${CHECKS_PASS}通过 / ${CHECKS_FAIL}失败"
if [ $CHECKS_FAIL -gt 0 ]; then
  echo "  ⚠️  有校验未通过，请先修复再工作"
fi

# ────────────────────── 角色边界提示 ──────────────────────
echo ""
echo "📋 角色边界（$ROLE）:"
if [ -f ROLES.md ]; then
  awk "/^### $ROLE/,/^### |^## /" ROLES.md 2>/dev/null | head -8 || echo "  (未在ROLES.md注册)"
fi

# ────────────────────── 角色边界提示 ──────────────────────
echo ""
echo "📋 角色边界（$ROLE）:"
if [ -f ROLES.md ]; then
  awk "/^### $ROLE/,/^### |^## /" ROLES.md 2>/dev/null | head -8 || echo "  (未在ROLES.md注册)"
fi

# ────────────────────── 职责通知（必读） ──────────────────────
if [ -f NOTICE_ROLES.md ]; then
  echo ""
  echo "📢 职责通知（NOTICE_ROLES.md，QA发布）:"
  echo "────────────────────────────────────────"
  awk "/^## 致 $ROLE 窗口/,/^---/" NOTICE_ROLES.md 2>/dev/null | head -30 || echo "  (本窗口暂无专项通知)"
fi

# ────────────────────── 信箱（其他窗口留言） ──────────────────────
echo ""
echo "📬 信箱（其他窗口留言）:"
python3 cloud/inbox.py read "$ROLE" 2>/dev/null | head -25 || echo "  (信箱不可用)"
echo "  回复: python3 cloud/inbox.py post <收件人> \"内容\""

# ────────────────────── 公共状态快照 ──────────────────────
echo ""
echo "📊 公共状态:"
if command -v python3 &>/dev/null; then
  python3 cloud/public_status.py 2>/dev/null || echo "  (公共状态获取失败)"
else
  echo "  (python3不可用)"
fi

# ────────────────────── 最近状态事件 ──────────────────────
echo ""
echo "📡 最近状态事件（其他窗口的动态）:"
python3 cloud/status_events.py list 10 2>/dev/null | head -10 || echo "  (无新事件)"

# ────────────────────── 自动解锁检查 ──────────────────────
echo ""
echo "🔓 自动解锁检查:"
python3 cloud/task_helper.py unblock 2>/dev/null || echo "  (无阻塞任务)"

# ────────────────────── 任务队列 ──────────────────────
echo ""
echo "📌 我的任务（$ROLE）:"
python3 cloud/task_helper.py list "$ROLE" 2>/dev/null || echo "  (任务队列不可用)"

# ────────────────────── 待认领强制提示 ──────────────────────
TASKS_PY=$(mktemp)
python3 - "$ROLE" > "$TASKS_PY" <<'EOF'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('cloud').resolve()))
import os
os.environ.setdefault('FOOD_APP_DIR', str(pathlib.Path('app').resolve()))
try:
    import task_helper
    role = sys.argv[1]
    tasks = task_helper.list_tasks(role) or []
    todo = [t for t in tasks if t.get('status') == 'todo']
    if todo:
        print("HAS_TODO")
        for t in todo[:5]:
            print(f"  #{t.get('id','?')} [{t.get('priority','?')}] {t.get('title','')[:40]}")
except Exception as e:
    print(f"ERR {e}")
EOF
if grep -q "HAS_TODO" "$TASKS_PY" 2>/dev/null; then
  echo ""
  echo "🔴🔴 你有 $ROLE 待认领任务！未认领将上报PM："
  grep -v "HAS_TODO" "$TASKS_PY" | head -6
  echo "  认领: python3 cloud/task_helper.py claim <id>"
else
  echo ""
  echo "✅ 无待认领任务"
fi
rm -f "$TASKS_PY"

# ────────────────────── 过时事实自动校验（PM 2026-10-01） ──────────────────────
# 防止窗口读到旧状态事实（如"Apify需充值"）而误导工作。
# 规则：key=<正则> 若匹配到任何工作文档，则判定为过时事实，强制提示。
echo ""
echo "🔍 过时事实校验（防止旧状态误导）:"
STALE_FOUND=0
check_stale() {
  local desc="$1" pattern="$2"
  local hits
  hits=$(grep -rn "$pattern" HANDOFF.md STATUS.md PM_START_HERE.md ROLE_STANDARD.md 2>/dev/null | grep -v "^Binary" | head -3)
  if [ -n "$hits" ]; then
    echo "  ❌ 发现过时事实 [$desc]:"
    echo "$hits" | sed 's/^/     /'
    STALE_FOUND=1
  fi
}
# 当前已确认的过时事实（随状态变更维护）：
# Apify已充值Starter(2026-10-01 PM确认)，"首轮$10封顶/等10-28重置"为旧事实
check_stale "Apify充值已完成,但文档仍写'首轮\$10封顶/等10-28重置'" '首轮 \$10 封顶\|等 10-28 月度重置\|需你本人在 https://console.apify.com/billing 加支付方式'
if [ $STALE_FOUND -eq 0 ]; then
  echo "  ✅ 无过时事实"
else
  echo "  ⚠️ 存在过时事实！请先修正文档再继续工作（或确认该行是历史日志段，非当前待办）"
fi

# ────────────────────── 统一状态卡（PM 2026-10-01·方案B） ──────────────────────
# 三窗口开工强制渲染同一张卡：数据/账号/配额/费用/最新事件。
# 来源：task_queue（真源）+ status_events + Supabase 计数。看卡才允许干活。
echo ""
echo "📊 统一状态卡（三窗口共享，PM维护）:"
STATUS_CARD=$(mktemp)
python3 - > "$STATUS_CARD" <<'EOF'
import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path('cloud').resolve()))
os_env = pathlib.Path('app/.env.local')
import os
os.environ.setdefault('FOOD_APP_DIR', str(pathlib.Path('app').resolve()))
os.environ.setdefault('HTTPS_PROXY', 'http://127.0.0.1:7897')
os.environ.setdefault('HTTP_PROXY', 'http://127.0.0.1:7897')
try:
    import cloud.vendor.pipeline.common as C
    # 数据基线
    try:
        rest = C.fetch_all('restaurants', select='id,status', page=1000)
        active = sum(1 for r in rest if r.get('status')=='active')
        print(f"  餐厅: {len(rest)} 在营: {active}")
    except Exception as e:
        print(f"  餐厅: (查询失败 {str(e)[:40]})")
    try:
        cmt = C.fetch_all('reviews', select='id', page=1000)
        print(f"  评论: {len(cmt)}")
    except Exception:
        print("  评论: (查询失败)")
    # 任务概览
    try:
        tq = C.fetch_all('task_queue', select='id,status,priority', page=1000)
        todo_n = sum(1 for t in tq if t.get('status')=='todo')
        prog_n = sum(1 for t in tq if t.get('status')=='in_progress')
        done_n = sum(1 for t in tq if t.get('status')=='done')
        print(f"  任务: todo={todo_n} 进行中={prog_n} done={done_n}")
    except Exception as e:
        print(f"  任务: (查询失败 {str(e)[:40]})")
except Exception as e:
    print(f"  (状态卡获取失败: {str(e)[:60]})")
EOF
head -8 "$STATUS_CARD"
rm -f "$STATUS_CARD"

# ────────────────────── 最近commit ──────────────────────
echo ""
echo "📝 最近5条commit:"
git log --oneline -5 2>/dev/null || echo "  (无)"

# ────────────────────── 结束提示 ──────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  完成后: bash sync.sh push \"说明\""
echo "  任务: python3 cloud/task_helper.py list"
echo "════════════════════════════════════════"

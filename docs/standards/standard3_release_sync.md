# 规范 3 · 发布规则与全窗口同步（Standard 3：Release & Multi-Window Sync）

> 版本：v0.1（2026-10-01 订立） ｜ 维护者：release owner（当前 = PM 窗口）
> 本规范**只立标准 + 提供非阻断检查骨架**。本轮不做任何破坏性变更、不触发部署、不改 live crontab。
> 配套物：
> - 非阻断检查脚本：`cloud/release.sh`（默认只跑检查、绝不部署）
> - 发布清单模板：`docs/standards/release_manifest.template.md`
>
> 凡是仓库里没有现成命令、需人工在 Supabase/Vercel/服务器上操作的步骤，下文均标 **【人工】**；
> 凡是我无法在本仓库 100% 证实的，标 **【待确认】**，不臆造。

---

## 0. 基础设施事实（本仓库实测，2026-10-01）

| 项 | 真实值 | 证据 / 路径 |
|---|---|---|
| 主仓库 origin | `git@github.com:huming0018-dot/china-travel-food.git`（SSH） | `git remote -v` |
| 主分支 | `main` | `git branch --show-current` |
| 前端 | Next.js 14，**Root Directory = `app/`**，Vercel 托管 | `app/package.json`、`app/vercel.json`、`DEPLOY.md` |
| 前端定时 | Vercel Cron `/api/sync` 每日 03:00 | `app/vercel.json` |
| 后端采集容器 | 容器名 **`food-cloud`**，镜像 `food-cloud:local` | `cloud/docker-compose.yml` |
| 服务器 | `ubuntu@49.234.35.92`，deploy key `~/.ssh/food_cloud_deploy` | `cloud/build_on_server.sh` |
| 服务器路径（git 缓存） | `/home/ubuntu/china-travel-food`（`build_sync.sh` 的 `SRC_DIR`，浅克隆 + `reset --hard origin/main`） | `cloud/build_sync.sh` |
| 服务器路径（构建上下文） | `/home/ubuntu/food-cloud`（`build_sync.sh` 的 `BUILD_DIR`；`build_on_server.sh` 的 `RDIR`） | `cloud/build_sync.sh` / `cloud/build_on_server.sh` |
| 数据库 | Supabase（`restaurants`/`reviews`/…），迁移**人工在 SQL Editor 逐条执行**，仓库无 migration runner | `db/migrations/`、`DEPLOY.md` |
| 通知出口 | `cloud/notifier.py`（唯一外发口），通道 TG + 飞书自建应用，开关 `/app/data/notify_channels.json` | `cloud/notifier.py`、`cloud/entrypoint.sh` |
| 自进化对账 | 容器 cron **每天 01:00** 跑 `cloud/self_evolve.py`（只读复盘 + release_audit A–G） | `cloud/crontab.txt` 第 12 条 |
| 跨窗口锚点 | `HANDOFF.md`（顶部=最新）、`STATUS.md`、`task_queue` 表、`cloud/inbox.py` 信箱 | `HANDOFF.md`、`STATUS.md`、`ROLE_SYNC.md` |

> **【待确认】通道现状**：`cloud/entrypoint.sh` 首次起卷默认 TG+飞书自建应用(`feishu_app`)开；
> 但 `ROLE_SYNC.md` 写「仅 Telegram，飞书已关闭」。以运行时 `/app/data/notify_channels.json` 为准——
> 发布播报前用 `cloud/notifier` 实际投递一条 `INFO` 验证，别假设双通道都通。

> **【待确认】Vercel 项目名/生产域名**：仓库内无 Vercel 项目名或域名记录（`DEPLOY.md` 仅教程）。
> 发布回读验证的具体 URL 由 release owner 补进发布清单，本规范不臆造。

---

## 1. 版本号与发布物清单

### 1.1 版本号约定
仓库当前 **无任何 git tag**（`git tag` 为空），因此本规范首次引入约定：

- 格式：`vMAJOR.MINOR.PATCH`（语义化）。
- 初始锚点建议 `v0.24.0` —— 对齐最新迁移号 `db/migrations/024_prior_evidence_separation.sql`。
  【待确认】是否从 0.24.0 起跳由 release owner 拍板；之前的历史发布不强行补 tag。
- 打在 **main 合并后的 merge commit** 上；annotated tag：`git tag -a vX.Y.Z -m "release: ..."`。
- PATCH = 纯数据/热修；MINOR = 新迁移或新前端页面；MAJOR = 不兼容的 schema/口径变更（需在清单里列回滚）。

### 1.2 发布物清单（一次发布必须逐项勾稽，缺项不开发布）

| # | 类别 | 具体物 | 本仓库路径 / 落点 | 落地方式 |
|---|---|---|---|---|
| 1 | **迁移 (DB)** | 新 SQL 迁移（本轮最新 024） | `db/migrations/*.sql` | **【人工】** Supabase SQL Editor 逐条 Run；回读 `information_schema.columns` 验证 |
| 2 | **后端 / 容器** | `cloud/*.py`、`cloud/vendor/pipeline/*.py`、Dockerfile/compose/crontab | `cloud/` 全量 | 服务器 `build_sync.sh` 烤进镜像，容器 `food-cloud` 重建 |
| 3 | **数据** | 可重跑的 `--apply` 脚本与账本（非手工库改） | `cloud/reconcile.py`、`cloud/prior_separate.py`、`cloud/post_audit.py`、`/app/data/**` | 容器内幂等 `--apply`；数据不进 git（卷持久化） |
| 4 | **前端** | Next.js 页面/组件/lib | `app/pages/`、`app/components/`、`app/lib/` | push main → Vercel 自动构建（Root=`app/`） |
| 5 | **配置** | 环境变量 / 通道开关 / cookie 池 | `cloud/deploy.env.template`、`app/.env.local.example`、`/app/data/notify_channels.json` | **【人工】** 不进 git；新增变量必须同时登记 template |

> 铁律：**密钥/凭据永不入库**（`deploy.env`、`xhs_cookies.json`、`xhs_accounts/` 均 gitignored）。
> 新增环境变量时，必须同步：`cloud/entrypoint.sh` 的 env 白名单 + `cloud/deploy.env.template` + `app/.env.local.example`。

### 1.3 Changelog / 发布 manifest 字段
每次发布新建 `docs/releases/vX.Y.Z.md`（从 `release_manifest.template.md` 复制），必填字段：

- `version`、`date`、`release_owner`（单一责任人）、`commit`（main 合并后 SHA）、`tag`
- `migration_applied`：本次执行的迁移编号列表 + 是否人工回读验证
- `artifact_scope`：本次实际改了哪几类（上表 1–5 勾选）
- `checklist_results`：发布前必过检查项（§4）的 PASS/WARN/FAIL 记录，附 `release_audit_<date>.md` 路径
- `deploy_steps_taken`：Vercel 自动部署 / 容器重建 实际做了什么
- `readback_verification`：部署后回读证据（见 §2.5）
- `rollback`：回滚路径（迁移回滚 SQL / 上一镜像 tag / Vercel 上一 deployment）
- `notify`：TG/飞书播报已发否

---

## 2. 标准发布流（文字版流程图）

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  分支开发  feature/<topic>   (各窗口在自己任务上，不直接推 main)              │
 └───────────────┬─────────────────────────────────────────────────────────┘
                 │ 推分支 + 开 PR
                 ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  发布前检查（cloud/release.sh，非阻断；全 PASS/WARN 才可进下一步）          │
 │   ① 仓库卫生：工作区干净、HEAD 对齐 origin/main、无明文密钥                │
 │   ② schema 校验：新迁移列出 + 【人工】Supabase 回读新列就位                │
 │   ③ 发布回归 loop：cloud/vendor/pipeline/release_audit.py（只读 A–G）      │
 │   ④ 硬规则断言：本轮 5 项修复门（见 §4）                                  │
 │   ⑤ 覆盖计数：release_audit 汇总 PASS/CHECK/ERROR/SKIP；数据计数 best-effort│
 │   ⑥ 前端契约：app/ 依赖/列名接线核对（next build 默认不跑，--frontend-build 才跑）│
 └───────────────┬─────────────────────────────────────────────────────────┘
                 │ 检查全绿（ERROR=0），QA 复核
                 ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  合并到 main（PR squash/merge）→ git push origin main                    │
 └───────────────┬─────────────────────────────────────────────────────────┘
                 │ push main 触发两路部署（异步）
       ┌─────────┴───────────┐
       ▼ 前端                  ▼ 后端/容器
 ┌──────────────┐      ┌──────────────────────────────────────────┐
 │ Vercel 自动  │      │ 服务器：                                  │
 │ 构建(Root=app)│      │ SSH 到 ubuntu@49.234.35.92               │
 │  Next.js 部署 │      │ bash ~/food-cloud/build_sync.sh           │
 │              │      │  (= fetch+reset origin/main → rsync      │
 │              │      │   *.py → docker build → compose up)      │
 │              │      │ 容器名 food-cloud 重建                    │
 └──────┬───────┘      └───────────────────┬──────────────────────┘
        └──────────────┬────────────────────┘
                       ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  部署后回读验证（readback）                                                │
 │   前端：生产 URL 首页/地图/详情 200，精选层/连锁列已渲染（H 类人工浏览器回归）│
 │   容器：docker compose ps=Up；最近 cron 日志无 traceback；notifier 心跳正常 │
 │   数据：release_audit 复跑 ERROR=0；stage5 总分漂移在阈值内               │
 └───────────────┬─────────────────────────────────────────────────────────┘
                 │ 回读通过
                 ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  打 tag：git tag -a vX.Y.Z && git push origin vX.Y.Z                      │
 │  写 docs/releases/vX.Y.Z.md 清单 → commit/push → notifier 播报发布完成     │
 └─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 分支 → PR
- 任务在 `feature/` 分支上做；窗口结束用 `bash sync.sh push "说明"`（见 §3），但**直推 main 仅限发布 owner**。
- PR 描述里粘 `docs/releases/` 清单草稿 + release.sh 的检查输出。

### 2.2 检查（本地/开发机，全部只读、非阻断）
统一入口 `cloud/release.sh`（默认只检查）。覆盖：测试/回归 loop/硬断言/覆盖计数/前端契约，详见 §4。

### 2.3 合并
- main 是唯一发布源。合并后 `git rev-parse HEAD` 记录进清单。

### 2.4 部署（push main 后；以下命令由 release owner 在服务器/本机手动执行，**release.sh 不代跑**）
- **前端（Vercel）**：push main 即自动触发，无需命令。【待确认】是否绑定了自动部署分支，以 Vercel 项目设置为准。
- **后端容器**（SSH 到服务器后执行；首选 git 缓存重建，根治「docker cp 补脚本、重建后丢失」）：
  ```bash
  # 在服务器上（经代理/可达 49.234.35.92 的通道）：
  bash ~/food-cloud/build_sync.sh          # fetch+reset origin/main → rsync → docker build → compose up
  ```
  - 备选上传式构建（本机打包上传，少用）：`bash cloud/build_on_server.sh`（见该脚本头注释）。
  - 重建前确认：新迁移已在 Supabase 执行（否则容器代码先于 schema 上线）。
  - **不得**用 `docker cp` 临时补脚本后不入库（HANDOFF 2026-09-29 lean 清理已教训）。

### 2.5 部署后回读验证
- 容器：`docker compose ps`（food-cloud=Up）、`tail /app/data/*.log` 无 traceback、`progress_broadcast` 心跳仍在。
- 数据：容器内复跑 `python3 /app/pipeline/release_audit.py`，ERROR=0。
- 前端：浏览器人工走 H 类（导航/筛选/排序/详情/地图/打卡），确认接线列渲染、无 hydration 报错。

### 2.6 打 tag
- 回读通过后才打 annotated tag 并推送，清单 commit 一并 push。

---

## 3. 多窗口同步规则（HANDOFF 为锚）

### 3.1 锚点文件
- **`HANDOFF.md` 是全窗口唯一交接锚点**，最新条目在文件**顶部**。
- 辅以 `STATUS.md`（实时状态快照）、`QUALITY_ISSUES.md`（问题台账）、`task_queue`（真源任务表）、`cloud/inbox.py`（窗口信箱）。

### 3.2 每个窗口开工前必做（顺序固定）
```bash
bash sync.sh <role>        # = git pull --rebase → 读 STATUS → 任务队列 → 最近 commit → 信箱
# 然后人工读 HANDOFF.md 顶部最新段落 + STATUS.md
```
- **禁止基于过期 schema 开工**：开工前确认最新迁移号（`db/migrations/` 最大值）与自己要用的表结构一致；
  若 HANDOFF 顶部提到「新迁移待执行」，先等迁移落地再写消费该列的代码。

### 3.3 发布/状态播报
- 所有窗口间「对话」靠 git 异步：信箱 `python3 cloud/inbox.py post <人> "内容"` + task_queue + 直读会话（见 `WINDOWS.md`）；平台无主动跨窗口发消息工具。
- 发布事件（开始/成功/回滚）经 `cloud/notifier.py` 推 TG（+飞书若通道开），格式 `format(level, body)`。

### 3.4 单一发布 owner
- 任一时刻只有 **一名 release owner**（当前 = PM 窗口）有权：合并 main、触发容器重建、打 tag、发发布播报。
- 其他窗口可以准备分支和检查，但不越权部署。owner 身份写进当次发布清单。

### 3.5 回滚与 hotfix
- **数据/迁移回滚**：每个迁移文件底部自带【回滚语句】（如 024），按它在 SQL Editor 逐条执行。
- **容器回滚**：保留上一个可工作镜像；重建失败则 `docker compose down` + 回退上一镜像 tag 重新 up（【待确认】当前是否保留多镜像 tag——未 tag 前是 `food-cloud:local` 单标签，建议发布后给镜像也打版本注记）。
- **前端回滚**：Vercel 控制台一键回退上一 deployment（【人工】）。
- **hotfix 流程**：P0 不过夜（`ROLE_SYNC.md` 铁律）。hotfix 走最小分支 → 同样过 §4 检查 → 由 owner 合并部署 → 在 HANDOFF 顶部追加一条 hotfix 记录。hotfix 也必须打 tag（PATCH 位）。

### 3.6 与 01:00 自进化对齐
- 容器 cron **每天 01:00** 跑 `cloud/self_evolve.py`：只读复盘当日改动 + 跑 release_audit A–G，报告落 `/app/data/self_evolve/YYYY-MM-DD.md` 并播报。
- 发布窗口尽量**避开 01:00**（及它前后约 15 分钟），避免发布验证与自进化复盘同时跑、数字互相污染。
- 发布后第一天的 01:00 报告即「发布后自动回归对账」：若它报 ERROR，按 §3.5 回滚。

---

## 4. 发布前必过检查项（本轮 5 项修复硬门）

> 这些同时被 `cloud/release.sh` 非阻断地自动检查；任何一项 FAIL 都不阻断脚本退出（仍返回 0），
> 但**发布 owner 不得在存在未解释 FAIL 时开发布**。

| 门 | 修复 | 必须成立的事实 | 自动检查位置（release.sh） | 人工/只读复核 |
|---|---|---|---|---|
| **G1 权威计数** | 权威列桥接与计数 | `cloud/reconcile.py` 编排链就位；findings→字段→curate 单 cron（07:47）已接线；applied 计数与账本一致 | 脚本存在性 + `crontab.txt` 含 `reconcile`/07:47 | 容器内 reconcile dry-run 计数，与 HANDOFF 记录（本轮 183 字段）对账 |
| **G2 先验证据分离** | 启发式先验与证据列物理分离 | `db/migrations/024_prior_evidence_separation.sql` + `cloud/prior_separate.py` 就位；**硬门只读证据列、绝不读 `*_prior`** | 文件存在性 + grep 硬门脚本未消费 `_prior` | Supabase 回读 4 新列；确认/高证据行未被搬动 |
| **G3 前端接线** | 精选层/连锁/预制列接线（不改视觉） | `app/pages/index.tsx`、`restaurants/index.tsx`、`restaurants/[id].tsx` 引用 curate/chain 列；`next build` 通过 | 页面文件存在且含相关列名；build 默认不跑 | `--frontend-build` 后浏览器 H 类回归 |
| **G4 孤立清理** | 热补丁归位 + 一次性过程稿清除 | `cloud/code_audit.py` 可跑；构建上下文无游离 `_*.py` 过程稿；在跑脚本都已入库 | best-effort 跑 `code_audit.py --report`；扫描构建目录游离文件 | 对照容器 `/app/cloud` ↔ git HEAD 三方一致性 |
| **G5 Apify 核验** | Apify 采集链路打通 | `cloud/apify_ingest.py` 就位、`APIFY_TOKEN` 已配（Starter 已充值）；小样跑通无 http402、成本在 `APIFY_COST_CAP_USD` 内 | 文件存在 + 环境变量存在性（不实际扣费跑） | 【人工】跑一次限量小样，核对 JSONL 解析与成本账本 |

---

## 5. 非阻断约定（本轮）
- `cloud/release.sh` **只检查、不部署**：脚本内不含任何会真正 ssh/docker/push 的未注释命令；部署指令一律以 `echo` 打印给人看。
- 不改 live crontab、不动 `/app/data` 卷、不碰凭据。
- 检查失败 = 记 WARN/FAIL 并继续跑完所有项，最终给一份汇总，退出码恒为 0（除非 `--strict`）。

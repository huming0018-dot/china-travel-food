# 发布清单 · vX.Y.Z（TEMPLATE）

> 用法：发布前 `cp docs/standards/release_manifest.template.md docs/releases/vX.Y.Z.md`，再逐项填。
> 带 ☐ 的是勾选框；【人工】= 需人在 Supabase/Vercel/服务器操作；【待确认】= 信息不全需 owner 补。
> 本文件提交进 git；不写任何明文密钥。

---

## 元信息
- version: `vX.Y.Z`
- date: `YYYY-MM-DD`
- release_owner: `<单一发布责任人窗口/人>`
- commit (main merge SHA): `<git rev-parse HEAD>`
- tag: `vX.Y.Z`（回读通过后才打）
- 上一版本: `<none 或 vX.Y.Z-1>`

## 本次发布物范围（勾选实际改动的类别）
- ☐ 1 迁移 (DB)：`db/migrations/` 编号 __________
- ☐ 2 后端/容器：`cloud/` 改动文件列表 __________
- ☐ 3 数据：可重跑脚本 + 账本 __________
- ☐ 4 前端：`app/` 页面/组件 __________
- ☐ 5 配置：新增/变更环境变量 __________（须已同步 entrypoint 白名单 + template）

## 迁移（人工）
- ☐ 新迁移已在 Supabase SQL Editor 逐条执行：`__________.sql`
- ☐ 回读验证（information_schema 新列就位）：PASS / FAIL 截图/输出路径 __________
- ☐ 已记录回滚 SQL（迁移文件底部）：是 / 否

## 发布前必过检查（cloud/release.sh 输出粘贴）
- 运行命令：`bash cloud/release.sh`（必要时 `bash cloud/release.sh --frontend-build`）
- 汇总：PASS=__  WARN=__  FAIL=__ （ERROR 必须为 0 才可发）
- release_audit 报告路径：`research/release_audit_<date>.md` 或 `/app/data/authority/release_audit_<date>.md`

五项硬门（G1–G5）：
- ☐ G1 权威计数（reconcile 链 / 07:47 / 计数对账）：PASS / WARN / FAIL 说明 ____
- ☐ G2 先验证据分离（024 + prior_separate；硬门不读 *_prior）：PASS / WARN / FAIL ____
- ☐ G3 前端接线（index/restaurants 页列渲染、next build）：PASS / WARN / FAIL ____
- ☐ G4 孤立清理（code_audit、无游离过程稿）：PASS / WARN / FAIL ____
- ☐ G5 Apify 核验（token 就位、小样无 http402、成本在 cap 内）：PASS / WARN / FAIL ____

## 部署（release owner 手动执行）
- 前端：push main → Vercel 自动构建；生产 URL `__________`【待确认】
- 后端容器：`bash ~/food-cloud/build_sync.sh`（服务器 ubuntu@49.234.35.92）：已跑 / 未跑
- 容器名：`food-cloud`；重建时间 `__________`

## 部署后回读验证（readback）
- ☐ 容器 `docker compose ps` = Up，日志无 traceback
- ☐ 复跑 `python3 /app/pipeline/release_audit.py` ERROR=0
- ☐ 前端生产 URL 首页/地图/详情 200，接线列已渲染（H 类浏览器回归）
- ☐ notifier 心跳/发布播报正常

## 回滚预案
- 数据迁移回滚：见 `db/migrations/0XX_*.sql` 底部【回滚语句】
- 容器回滚：上一可工作镜像 `__________`
- 前端回滚：Vercel 上一 deployment 一键回退
- hotfix 触发条件（什么情况下回滚）：__________

## 通知
- ☐ TG 播报已发（notifier INFO/RESOLVED）：是 / 否
- ☐ 飞书（若通道开）：是 / 否 / 通道关
- HANDOFF.md 顶部已追加本次发布条目：是 / 否

## 打 tag
- ☐ `git tag -a vX.Y.Z -m "release: ..."` 已打
- ☐ `git push origin vX.Y.Z` 已推

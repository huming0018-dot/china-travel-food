# 举报安全闭环交接（2026-10-11）

基于 main `7b3226b594956c40fc88600630502dc47d05b7ea`。

## 生产事实与实现
- 已核对生产项目 `bdwrhshgdeghgyzwpxnl`：原先无 increment_report；reviews 开启 RLS，仅本人评价可 UPDATE。不能据此声称匿名用户可修改任意评价。
- 已部署迁移 `20261011141634_secure_review_reporting.sql` 和 `20261011141825_report_count_skip_taste_recalc.sql`；文件版本与生产 schema_migrations 对齐。
- public.increment_report(uuid) 为 invoker 包装；私有 schema 的 definer 实现检查 auth.uid()，拒绝匿名登录，固定空 search_path。仅 authenticated 可调用。
- 私有举报记录唯一键 (review_id, reporter_id)；账号事务 advisory lock 和评价行锁串行化去重、限流与原子加一；每账号每小时最多20条新举报，重复重试不占额度。
- report_count 的 INSERT/UPDATE 对 public/anon/authenticated 撤回；普通 authenticated 其他列写入仍由既有 RLS 限定。service_role 等可信后端权限保持。
- 不重算、不回填历史举报数。历史用户是否已经举报无法从旧聚合数判断；去重仅从部署后的举报记录开始。账户限流无法阻止多账户滥用，若出现证据再接风控。
- 举报数更新不触发口味评分重算；其他评价变更保留原评分触发器行为。
- 前端移除浏览器直接写回退；检查 RPC 错误和返回合同；采用服务器计数。同步 in-flight guard 防重复点击，逐条显示失败/成功/已举报。

## 已执行验证
- 19项 PGlite 隔离检查通过：历史数不变、原子计数、重复、权限不足、匿名/匿名登录拒绝、直接 INSERT/UPDATE 计数拒绝、私有记录拒绝、不存在/隐藏评价、20/小时限流、重复在限流后重试、数据库异常回滚、评分触发器兼容、RPC 缺失 PGRST202/数据库/网络错误与无效响应。
- `npm ci --ignore-scripts`、`npm run build` 成功，包含 Next.js 类型检查、生产编译和14页生成。
- 生产事务隔离 SQL 验证：仅创建临时测试评价，首次举报返回 count=1/accepted=true，重复返回 count=1/accepted=false；匿名 RPC 与直接计数 UPDATE 被拒绝。整事务回滚，无测试评价/举报记录保留。
- 首次生产事务验证发现评分触发器的非限定函数名与空 search_path 冲突；补充第二迁移后复测通过。失败事务未保留计数或举报记录。
- 真实生产 REST 匿名 RPC：HTTP 401 / SQLSTATE 42501，函数权限拒绝，已排除 PGRST202 函数缺失。
- 迁移前后 reviews=2643，举报合计=0，按 id 排序的计数指纹 `f0f28ffaa801c5deecd0a337c7f3b684` 一致；举报记录0条。
- 已跑 Supabase security advisors：新私有表 RLS 无 policy 属有意拒绝直接访问，且撤回普通角色表权限；既有其他告警不作为本次新发现的可利用漏洞。参考 https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy 。

## 尚未验收
- 真正多连接并发：脚本 `cloud/tests/review-reporting-concurrency.mjs` 已发布，覆盖32不同用户、32同用户重试、25跨评价并发限流；当前无可用隔离 PostgreSQL，尚未执行。PGlite单会话通过不代表多会话并发通过。
- 当前 Vercel 团队接口返回403，现有连接不能直接发布/读取该团队部署。GitHub main 已有 Vercel自动构建状态，可以通过提交状态跟踪自动发布；不能把本地build当作生产部署成功。
- 真实登录用户浏览器端举报/网络失败视觉验收未完成，生产SQL模拟身份与匿名REST不等于该验收。

## 复跑
Node 24+：
```bash
CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/review-reporting.mjs
```
tools需安装 @electric-sql/pglite 0.5.8。

并发脚本仅可在**可销毁的独立数据库**运行，脚本会重建 public.reviews/auth/report_private，不可使用生产连接：
```bash
REPORT_TEST_DISPOSABLE=yes REPORT_TEST_DATABASE_URL=... CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/review-reporting-concurrency.mjs
```
tools需安装 pg 8.16.3。

不要在回退前端时恢复浏览器直接计数写入权限；数据库迁移已部署，不可用撤回权限来掩盖前端旧版本问题。

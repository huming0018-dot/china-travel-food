# 2026-10-07 远程诊断和入库修复

线上证据查询时间：北京时间 14:00–14:55。未创建测试参与者或向生产回传模拟笔记。

## 已修复并部署

- 旧版 `public.crowd_ingest_stores(false)` 持续 HTTP 500。数据库日志确认 SQLSTATE `21000`：同一店名归一化后关联多个 `restaurants`，导致一次 `ON CONFLICT` 重复更新同一主键。
- 按归一化名称先聚合餐厅匹配，只有恰好一个匹配时设置餐厅 ID。重名匹配保留为候选，不能随意取一个 ID 或回写评分。
- 补上 `PUBLIC` 的 EXECUTE 撤销；原 SQL 仅撤销 anon/authenticated，仍通过 PUBLIC 继承执行权限。
- 聚合表与候选表启用 RLS，撤销 PUBLIC/anon/authenticated 直接访问，保留 service_role 后台管理权限。这些表没有浏览器直接访问调用方，`crowd_store_ingest.py` 默认使用 service_role。
- 实际迁移版本：`20261007065208_crowd_ingest_unique_store_match`、`20261007065442_crowd_store_tables_service_only`。已通过 Supabase Management API 应用；不需要 Vercel 重部署或重装客户端。

## 实际数据回验

两次执行真实入库 RPC 均成功：`ok=true, evidence_count=31, candidates=26, updated_restaurants=0`。

- `public.crowd_store_evidence`：31 个店铺，5 个唯一匹配主库。
- `public.crowd_store_candidates`：26 个 open 候选，包含 2 个重名匹配和 24 个无匹配。
- accepted 评分数量为 0，因此没有改动餐厅评分。`candidates` 是本次 upsert 影响行数，不能解释成每次新增 26 家。
- 匿名/普通登录身份不能执行入库 RPC 或直接读取/改写这两张表，service_role 权限保留。
- Supabase security advisor 中这两张表的 RLS-disabled 错误已消失。无客户端策略是后台专用表的有意设置；其他历史表的告警不在本次修复范围。

权限说明：[API grants/RLS](https://supabase.com/docs/guides/api/securing-your-api)。Advisor 说明：[RLS disabled](https://supabase.com/docs/guides/database/database-linter?lint=0013_rls_disabled_in_public)、[RLS enabled without policies](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)。

## Mac 内测接入状态

- 原安装身份保持 suspended，换浏览器后的 macos 身份已于北京时间 14:51:04 完成接入，之后领取任务成功。当前一名 approved 参与者，日配额两条，另一个旧身份暂停。
- 新版 `crowd_v4.proofs` 和 `crowd_v4.diagnostics` 仍为 0；不能声明页面采集成功，也无法确定 `page_timeout` 的客户端原因。
- 同时有 Mac 请求调用旧版 v3 接口。北京时间 13:00 起旧版 accepted 笔记共 33 条，正文摘要均不足 8 字；这些回传不能算作新版完整笔记证据，也不能仅凭 Mac 请求就认定属于本次参与者。
- 定位实际网页超时仍需当前客户端勾选「发送运行诊断」。诊断默认关闭，仅发送运行阶段等有限状态，不含登录凭据、正文、截图，也没有远程执行命令能力。
- v4 正式安装渠道及 Docker 导出调度没有在本次操作中开放。此次 v3 入库修复不能替代 v4 的实机采集验收。

## 最小回归检查

使用已有 PGlite 安装运行，不新增项目运行依赖：

```sh
CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/crowd-store-ingest.mjs
```

覆盖唯一/重名/无匹配、三条评分门槛、拒收不参与聚合、空店名、dry-run、重复执行和权限。原函数已在隔离数据库复现相同 `21000`，修复版检查通过。迁移文件时间戳与线上 migration history 一致。

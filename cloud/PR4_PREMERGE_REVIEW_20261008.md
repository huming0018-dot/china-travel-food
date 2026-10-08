# PR #4 合并前审查（2026-10-08）

结论：原 head 存在评分保护阻断缺陷。已提供最小后续迁移和回归测试，生产未执行任何迁移或入库 RPC。PR 保持 open；不能宣称 main 与线上迁移历史已一致。

## 审查基线

- main：`8eac200616291d7043c92232d31f9bee21766971`。
- 原 PR head：`d5b84116c360f4432627f7bcaea4539f30fd4085`。检查时 open、非 draft、mergeable，无正式评审。
- 与 main 试合并无冲突，试合并状态下运行扩展回归通过，随后撤销本地试合并。
- 生产项目：`bdwrhshgdeghgyzwpxnl`。只读核对 schema_migrations、函数定义、ACL、RLS 和聚合计数。

## 阻断问题与最小修复

1. **撤回证据仍可改评分。** 原函数更新评分读取整个 `crowd_store_evidence`。某店所有 accepted 证据撤回后，该店不在新聚合中，旧聚合却保留并继续回写。隔离复现：预先将评分改为 2，再撤回该店所有证据，原函数仍返回 `updated_restaurants=1`。新增回归要求为 0。
2. **多个原始店名映射同一餐厅。** 按原始店名聚合的多个来源可归一到同一餐厅，`UPDATE ... FROM` 没有确定评分来源。隔离复现：两个别名各有三条评分，均值分别 3 和 5，原函数仍更新一家餐厅。新增回归要求暂缓更新，直到建立明确的别名合并政策。

后续迁移 `20261008134109_crowd_ingest_current_safe_scores.sql` 只替换函数并重申执行权限，不主动调用入库或修改业务行。评分更新直接使用本次 accepted 聚合，重新检查主库唯一匹配，排除空归一化名称；每个餐厅恰好只有一个聚合来源且评分数至少 3、均值大于 0 才写入。保留历史聚合记录供审计，不自动恢复曾写过的旧评分。同步更新全新安装 SQL。已部署的两项 20261007 迁移保持原文不变。

## 幂等性和部署顺序

- 前置依赖：restaurants、crowd_proofs、v3.2.5 聚合/候选表、名称归一函数和候选 identity sequence 已存在。两项 20261007 文件不是完整建库迁移。
- 顺序：旧 v3.2.5 schema → 20261007065208 函数修复 → 20261007065442 表权限 → 新的评分保护迁移。
- 隔离测试重复应用每项修复迁移，通过；CREATE OR REPLACE、ENABLE RLS、REVOKE/GRANT 不依赖首次运行。
- 生产已经应用的两项迁移禁止重放或修改。新增迁移尚未部署，不能把本地测试称为生产 SQL 验收。
- 新建环境使用更新后的 v3.2.5 SQL，随后按顺序回放修复迁移；不要在已部署环境重新执行旧安装 SQL。
- candidates 返回的是 upsert 影响行数，不是每次新增数。业务 RPC 重跑可更新同步时间及消耗 identity 序列值，不能称为全库逐字节不变。

## 重名与权限边界

- 原 PR 按主库归一化名称计数，只允许 count=1，重名不猜测 ID，保留候选。修复仍保留这个行为。
- 生产函数 ACL 为 `{postgres=X/postgres,service_role=X/postgres}`；anon/authenticated 无执行权限。
- 两张后台表 RLS 已开启，anon/authenticated 无直接读取证据或写入候选权限，service_role 权限保留；两角色均无 public schema CREATE 权限。
- 后续函数使用空 search_path，访问业务对象均明确指定 public schema。匿名/登录调用失败和 service_role 成功由隔离测试验证。

## 测试结果

已有 PGlite 回归在原 PR 下通过。补充评分撤回测试在已部署定义下失败：期望 0，实际 1；单独别名冲突测试同样失败：期望 0，实际 1。

修复后，以下三种路径通过：旧 main schema 升级、更新后全新 schema、最新 main 试合并。覆盖唯一/重名/无匹配、评分门槛、拒收/空店名、dry-run、业务重复执行、迁移重复执行、匿名/登录权限、service_role、证据撤回、过期匹配、别名冲突、零评分和空归一化评分来源。

```sh
CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/crowd-store-ingest.mjs
# 已部署定义的负向复现，应在撤回证据断言处失败：
CROWD_TEST_DEPLOYED_ONLY=1 CROWD_TEST_TOOLS=/path/to/tools node cloud/tests/crowd-store-ingest.mjs
# 可使用 CROWD_TEST_SCHEMA=/path/to/old-main-schema.sql 验证旧版升级路径。
```

测试工具临时安装于独立目录：PGlite 0.5.8；未新增项目运行依赖。PGlite 验证不等于完整 Supabase/PostgREST 生产集成验收。

## 三种状态必须分开

| 层次 | 核查结果 |
| --- | --- |
| 已部署数据库修复 | 两项 20261007 迁移存在；线上函数正文 MD5 `286d623781b9f4ecb06e016c0fdf5bf3` 与原 PR 迁移一致；当前权限边界符合原 PR。 |
| 源码合并 | 尚未合并。main 缺少两项历史迁移；补充修复仅在 PR 分支，新增迁移未在生产应用。 |
| 后续业务验收 | 未完成。10 月 7 日两次 31/26/0 是历史真实入库验收。此次只读看到 52 条聚合、41 条 open 候选、accepted 评分 0、过期聚合 0；未执行入库，未验收完整客户端采集。 |

生产迁移历史还存在多项 v4 后续版本，main 当前 migrations 目录仅有两项 20261006 版本；不能将 PR #4 两项迁移核对外推成整个项目迁移历史一致。后续版本归档属于另外的源码同步工作。

下一步门槛：审阅新增评分保护 SQL，按独立部署流程安排这项尚未应用的迁移及只读定义/权限回验，再重新核对最新 PR head/main 并完成合并。此审查没有授权或执行生产重放、数据清理、评分恢复或真实入库。

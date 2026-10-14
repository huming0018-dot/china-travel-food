# 众包评分保护生产验收（2026-10-14，北京时间）

## 结论与范围

代码已合入 main；本次新增评分保护已部署生产；真实业务评分回写尚未验收。生产项目 `bdwrhshgdeghgyzwpxnl`。只部署 `20261008134109_crowd_ingest_current_safe_scores.sql`，源码 blob `54280f23edee66a8a84b87b7f1071b4f6beffc7b`，未改原文件。两项 20261007 历史迁移保留，未重放。未调用生产 `crowd_ingest_stores(false)`，未重算、清理或恢复历史评分。

## 部署前取证与兼容性

生产函数仍使用历史 crowd_store_evidence 写分，正文 MD5 `286d623781b9f4ecb06e016c0fdf5bf3`，search_path=public；历史中不存在 20261008134109。20261007065208、20261007065442 已存在。函数 owner=postgres，ACL 仅 postgres/service_role；后台两表 RLS 已开启。

已检查当前列类型、约束、候选唯一索引 (store_name,status)、名称归一函数、restaurants 更新触发器与 crowd_submit_proof(text,jsonb) 定义。当前 v3.5.1 写入协议仍为 kind=note/rating、gate_status=accepted，rating 为 numeric，已收录 accepted rating 无 null；参数与返回 JSON 兼容。本函数只聚合 public.crowd_proofs，不消费 crowd_v4.proofs，不能将本次验收外推为 v4 数据桥已完成。

部署前 accepted note=702、accepted rating=1、rejected note=9。餐厅1523家，score_diner 摘要 MD5 `a39ec8ee038678b8ee38536bd7fd28b1`。

## 发布执行与迁移记录

通过已授权 Supabase SQL 管理入口执行单一有界事务：repeatable read、lock_timeout=5s、statement_timeout=20s；锁定迁移历史，断言目标版本不存在、历史两项存在、函数仍为核验的旧正文。原文执行 CREATE OR REPLACE 与 REVOKE/GRANT，并在同一事务向 schema_migrations 登记原版本、名称及完整原文 statements。不使用全量 db push，避免补跑其他未部署迁移。事务内餐厅全行摘要前后相同后提交。

生产记录：version=20261008134109，name=crowd_ingest_current_safe_scores；statements 与 main 原文件精确一致。部署后正文与源码精确一致，MD5 `120e486d665b0a53ce57d0105c61b030`，search_path为空，ACL仍仅 postgres/service_role。原两项记录仍在。

## 有界验收

- 部署前以该迁移定义、部署后以生产 pg_get_functiondef 回读定义分别执行临时表回归；均通过。
- 临时副本仅将函数名和四张业务表引用改为 pg_temp；沿用生产 norm_store_name，并复制生产聚合/候选表列、CHECK 与索引。候选使用临时 identity，未消耗生产序列；无真实餐厅触发器或前端集成测试。
- 覆盖唯一匹配（3条4分更新为4）、主库重名（不更新）、两个原始别名3/5分映射同店（不更新）、两条评分（不更新）、rejected评分（不计）、所有证据撤回后历史聚合仍存在（不回写）、业务重复执行（第二次评分改动0）、dry-run（不写聚合），以及定义重复安装。全部临时对象和数据事务回滚。
- 生产角色实测：anon/authenticated 调用 dry-run 均触发 insufficient_privilege；service_role dry-run 返回 ok=true、evidence_count=90、updated_restaurants=0、candidates=0；随后回滚。
- 正式函数未重复部署；幂等定义重放在临时副本验证。真实函数权限采用生产角色直接验证。
- 部署后餐厅1523家，score_diner 摘要仍为 `a39ec8ee038678b8ee38536bd7fd28b1`。部署事务内全行摘要也未改变，部署本身没有触发评分或派生字段更新。

## 尚未部署与业务限制

main 另有 `20261008183356_crowd_ingest_refresh_old_aggregates.sql`，生产历史中仍不存在。本次没有部署它；原有综合 crowd-store-ingest.mjs 已包含该后续迁移的旧聚合失效/候选清理断言，因此不能称该完整测试在仅本次迁移状态通过。本次评分保护阻止旧聚合回写，但不会失效旧聚合、刷新 first_seen 或清理旧 open 候选。后续迁移需单独核验与部署。

当前只有1条 accepted rating，尚无3条门槛的真实评分回写样本；临时表回归和生产 dry-run 不等于客户端→评分写入→正式入库→餐厅触发器的真实业务验收。不自动产生评分样本或调用正式入库来填补这一缺口。

# CROWD MIGRATION v3.2 — 服务端迁移总纲

> 依据：外部 bot《审阅报告.md》（2026-10-03）14 项高优先级问题 + 交付缺口表。
> 本总纲覆盖 **服务端 SQL 侧**修复；插件端修复见 `crowd_extension/src/*`（v3.2.1）与《审阅修复报告》。

## ✅ 部署状态（2026-10-03 已执行）

| 序号 | 状态 | 执行时间 |
|---|---|---|
| 01 证据真实性 | ✅ 已部署（备份 `*_bak_20261003` 三表） | 2026-10-03 |
| 02 身份绑定 | ✅ 已部署（Auth 已启用，apply.html 改走 crowd_register RPC） | 2026-10-03 |
| 03 任务租约 | ✅ 已部署（crowd_tasks 含 claimed_by/lease_until 列） | 2026-10-03 |
| 04 结算闭环 | ✅ 已部署（crowd_settle RPC + 状态列 + 每周一 09:00 服务器 cron） | 2026-10-03 |

## 迁移顺序（必须按序执行，每步备份）

| 序号 | 文件 | 覆盖审阅项 | 可否独立上线 | 前提 |
|---|---|---|---|---|
| 01 | `crowd_migration_v3.2_01_evidence.sql` | #7 URL-ID一致性 / #8 note_id去重 / #9 拒收落库 / #5 per-kw完成判定 | ✅ 已上线（插件 v3.2 已对齐） | 备份 crowd_proofs / crowd_tasks |
| 02 | `crowd_migration_v3.2_02_identity.sql` | #6 身份绑定 / #61 管理字段收紧 | ✅ 已上线（Auth 已启用 + 报名页走 RPC） | 产品决策（已同意） |
| 03 | `crowd_migration_v3.2_03_lease.sql` | #14 任务租约与名额预留 | ✅ 已上线（提交函数含租约校验） | 备份 crowd_tasks |
| 04 | `crowd_migration_v3.2_04_settlement.sql` | #13 结算闭环 | ✅ 已上线（crowd_settle RPC + 结算工具） | 备份 crowd_settlements |
| 05 | `crowd_migration_v3.2_05_store_ingest.sql` | #13 入库链路 | ✅ 已上线（crowd_store_evidence + 候选 + score_diner 回写） | 备份 crowd_proofs / restaurants |

## 执行前备份（Supabase SQL Editor）

```sql
create table public.crowd_proofs_bak_20261003 as select * from public.crowd_proofs;
create table public.crowd_tasks_bak_20261003 as select * from public.crowd_tasks;
create table public.crowd_participants_bak_20261003 as select * from public.crowd_participants;
```

## 迁移 01（证据真实性）——建议立即执行

- 每个文件 **整体单次提交**（plpgsql 按 \n 拆分会 FAIL）
- 执行后立即验证（文件末尾"验证"段）：
  1. URL 内 note_id 与字段不一致 → results 含 `gate=invalid` 且库内落 invalid 行
  2. 同 note_id 改标题再提交 → 第二条 `duplicate_skipped`（去重基于 note_id）
  3. 拒收率：`select participant_id, gate_status, count(*) from crowd_proofs group by 1,2;` 能看到 rejected/invalid 行
  4. keyword 包每词达 kpi_min 才 fulfilled

## 迁移 02（身份绑定）——产品决策后启用

启用前需：
1. Supabase Dashboard → Authentication → 启用（Provider 按招募渠道：邮箱+密码 / Google / 微信等）
2. `apply.html` 增加登录（登录后再报名 → `crowd_register` 自动绑定）
3. 存量参与者：登录后调 `crowd_bind_participant('P-XXXX')` 绑定
4. 上线后：未绑定参与者提交 → 迁移01函数返回 `auth_identity_mismatch`（自动拦截冒名）

**影响提示**：引入登录门槛会改变"报名即用"体验，需用户（老板）拍板。若暂不启用，迁移 02 **不执行**即可，插件 v3.2 与迁移 01 完全兼容。

## 迁移 03（任务租约）——并发防超发

- 领取改走 `crowd_fetch_tasks`（原子 UPDATE ... FOR UPDATE SKIP LOCKED）
- 提交校验：`task_claimed_by_other`（见迁移01函数内）
- 租约默认 24h（`lease_duration_min` 可调），过期释放
- 与插件 v3.2 兼容（插件仍调用同名 RPC，参数不变）

## 验收用例（对照审阅报告 §应交付的验收用例）

| # | 用例 | 涉及 |
|---|---|---|
| 1 | 同 note_id 改标题仍去重；不同 note_id 同标题可保留 | 迁移01 |
| 2 | URL 与 ID 不一致拒收 | 迁移01 |
| 3 | 实际拒收/重复/系统故障进入正确统计；75% 拒收率显示 75% | 迁移01 + crowd_tracking 修复 |
| 4 | 未认证者、他人身份、未领取任务不能绕过授权 | 迁移02/03 |
| 5 | 两人同时领/交最后一个名额，计数与预算不超发 | 迁移03 |
| 6 | 任务关闭/参与者停用 → 明确结束（permanent_failures） | 插件 v3.2 |

## 回滚策略

- 每文件末尾附回滚 SQL
- 函数级：`drop function crowd_submit_proof(text, jsonb)` 后用 `crowd_submit_proof_live_v2.sql` 原版重放
- 数据级：从 `*_bak_20261003` 表恢复

## 状态

- [ ] 迁移01 已执行并验证
- [ ] 迁移02 决策（启用 Auth？）
- [ ] 迁移03 已执行并验证

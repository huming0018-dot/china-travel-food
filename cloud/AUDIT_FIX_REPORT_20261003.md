# 众包美食家 · 外部审阅修复报告

> 版本：v3.2.0（git `a018bd4`）· 2026-10-03
> 输入：外部 bot《审阅报告.md》（14 项高优先级 + 交付缺口表 + 重构建议 + 验收用例）
> 范围：插件端（Chrome 扩展）、服务端（Supabase RPC/表）、工具链（cloud/*.py）、分发（Storage）

---

## 一、审阅结论 → 修复对照

### 插件端 P0（已修复，v3.2.0 已打包上传）

| # | 审阅问题 | 修复 |
|---|---|---|
| 1 | MV3 CSP 阻止 onboarding/popup 内联脚本 | 交互逻辑拆到 `src/onboarding.js` / `src/popup.js`，HTML 改 `<script src>` 外链加载 |
| 2 | 报名编号三方格式冲突（`P-时间戳-随机串`） | 统一 `^P-[A-Z0-9]{8}$`：apply.html 生成、onboarding.js 注册、background.js participantGate 三处同步 |
| 3 | content.js 不读 `msg.keyword`、多卡片复用同一正文/作者、任务-数据错配 | content.js 重写：搜索页 `pageMatchesKeyword`（URL/搜索框/页面关键词三重匹配）、详情页 note_id+相关度校验、每卡片独立提取、移除 `location.pathname` 兜底、返回 `mode: search\|detail` |
| 4 | 队列满（水位 100）才回传，首次回传要攒多个日配额周期 | background.js 改为**每批采集后立即 uploadProofs()**；满队列仅作暂停信号 |
| 5 | 多关键词永不轮转（done 从未置 true）+ 前后端完成标准冲突 | uploadProofs 里 `accepted >= kpi_min` 置 `done=true`；完成判定=所有关键词 done；服务端迁移01 引入 `kw_progress` per-kw 计数 |
| 6 | 参与编号当身份凭证（anon 可调、不验 ownership） | 迁移01 加入绑定前置校验钩子；完整 Auth 绑定在迁移02（需产品决策） |
| 7 | accepted 不等价真实数据（URL/note_id 只查形状、matched_store 直接信客户端、8 个重复汉字理由可通过） | 迁移01：**URL 内提取 24hex 必须等于 note_id**、rating 理由要求 ≥8 去重字符且非全同字；matched_store/anchor_score 仍信任客户端（服务端无门店实体校验，属受限改进，见未决） |
| 8 | 标题做全局唯一键（改标题绕 proof_seq、同名误杀、先删非小写英文） | 迁移01：新建 `note_id` 唯一部分索引（kind=note 且 accepted）、rating 部分索引（participant+note_id），停用标题 dedupe |
| 9 | 拒收率风控没落库（恒 accepted、gate_status 不允许 duplicate_skipped） | 迁移01：`gate_status` 扩展枚举（accepted/rejected/duplicate_skipped/task_closed/invalid/error）、每条 verdict 落库、拒收率=非 accepted 计数 |
| 10 | 重试丢成果/永久重试 | background.js：区分 `PERMANENT_REASONS`（task_not_open/task_closed/participant_suspended 等）移出队列记 `permanent_failures`；临时失败保留重试；服务端幂等返回原结果 |
| 11 | 安全线未接线/方向错 | background.js 遵守 `canSearch().waitMs`、详情模式 `ensureViewStay` 补齐停留；safety_engine.js `cooldown_min` 由 `Math.min` 反转为 `Math.max`（远程不短于本地 30min）、`currentLimits/_sessionGuard` 同步；新增 `restoreRemote()`（SW 重启不丢 `remote_limits_applied`） |
| 12 | 一机一号名不副实（localStorage 盐可清除、getDeviceSalt 未进链路、RPC 不校验） | v3.2 信封加入 `device_salt`（getDeviceSalt 进提交链路）；服务端绑定校验在迁移02/03 范围；作者字段服务端 `left(...,50)` 截断保留 |
| 13 | 评分/入库/结算无闭环 | 本轮未做大重构（见"未决事项"）；content.js 仍只产 note |
| 14 | 行锁不能防任务名额/预算超发 | 迁移01 加入租约预检（任务须 open 且 claimed_by 为空或等于本人）；原子 `assignment+lease` 完整实现迁移03 |

### 服务端 SQL（已写迁移，01 可立即部署，02/03 待决策）

| 文件 | 内容 | 状态 |
|---|---|---|
| `cloud/sql/crowd_migration_v3.2_01_evidence.sql` | URL-ID 一致性、note_id 去重、拒收落库、per-kw 完成判定、租约预检钩子 | ✅ 已写，**未部署**（备份后整体单次提交） |
| `cloud/sql/crowd_migration_v3.2_02_identity.sql` | auth_user_id 绑定、crowd_register/crowd_bind_participant RPC、RLS 收紧、管理字段防直写 | ⚠️ 需先启用 Supabase Auth + 改报名流程 |
| `cloud/sql/crowd_migration_v3.2_03_lease.sql` | crowd_fetch_tasks 原子领取（FOR UPDATE SKIP LOCKED）、租约过期释放 | ⚠️ 依赖迁移01 |
| `cloud/sql/CROWD_MIGRATION_v3.2.md` | 总纲：执行顺序/备份/验收/回滚 | ✅ |

### 工具链 P2（已修复，已推送+服务器同步）

| 文件 | 审阅问题 | 修复 |
|---|---|---|
| `cloud/crowd_tracking.py` | `int(0.75)*100=0%`；`_ts` 去时区按本地解释（24h 窗口漂移） | 拒收率改 float 计算；`datetime.fromisoformat`+时区解析（Z/+00:00/无时区均处理） |
| `cloud/crowd_smoke_monitor.py` | 统计不存在的 `done` 枚举（schema 是 fulfilled）；锁未覆盖"读旧快照+抓当前数据" | status→`fulfilled`；`lock.acquire()` 提到 `read_snapshot()/snapshot()` 之前 |
| `cloud/crowd_admin.py` | 查询不存在的 `participants.id`（表无 id 列）；查询失败显示 0 | select→`participant_id`；失败显示"故障" |
| `cloud/crowd_scale.py` | load_covered 把所有现存餐厅算已覆盖（候选全被过滤）；from_seed list 输入 .get 异常 | 已覆盖=有 accepted 证据的店铺+已发布任务包；from_seed 先判输入类型 |

### 分发（已上线，公网 200）

- `crowd-extension-v3.2.0.zip`（41KB，含新 popup.js/onboarding.js）
- `apply.html` / `install.html` / `install-mobile.html` / `crowd-install-mac.command` / `crowd-install-win.bat` / `CROWD_CONTRACT.md` 全部升级到 v3.2.0
- 安装器版本号升 3.2.0；win 解压目录与加载目录不一致已修复；install-mobile 加 Kiwi 停维护警示

---

## 二、未决事项（需老板/PM 拍板）

| 项 | 说明 | 影响 |
|---|---|---|
| ① 迁移01 部署 | SQL 已写好，需备份后整体单次提交（plpgsql 拆行会 FAIL）。**执行窗口建议：001 smoke 期间不停服直接部署，插件 v3.2 已兼容** | 不部署则 URL-ID/dedupe/拒收/租约校验不生效 |
| ② 是否启用 Supabase Auth（迁移02） | 引入登录门槛，改变"报名即用"体验；换取身份真实绑定 | 不启用：编号仍是弱凭证（已用 device_salt+风控缓解） |
| ③ 结算闭环（审阅#13） | 评分/入库/结算仍未打通；报告建议"per-store 证据采集试点"重构 | 影响"按条计酬"承诺的可验证性 |
| ④ crowd_admin approve 非事务 | 复制同 salt 新行撞唯一索引 + 两 HTTP 非原子 | 待修（改主键原地 UPDATE） |
| ⑤ crowd_pack 降级写 task_queue、crowd_ingest 旧入口 | 双口径遗留 | 建议退役，以 RPC 为唯一入口 |
| ⑥ crowd_tables.sql 非幂等 | 建议有序迁移（本次已按迁移文件执行） | — |
| ⑦ 构建依赖锁文件 | 未提供 requirements.lock | 复现性风险 |

---

## 三、验收用例（对照审阅报告 §应交付的验收用例）

| # | 用例 | 依赖 |
|---|---|---|
| 1 | 同 note_id 改标题仍去重；不同 note_id 同标题可保留 | 迁移01 |
| 2 | URL 与 note_id 字段不一致 → invalid 拒收落库 | 迁移01 |
| 3 | 拒收率显示 75% 而非 0；rejected/invalid 行真实存在 | 迁移01 + tracking 修复 |
| 4 | 未认证者/他人身份/未领取任务不能绕过授权 | 迁移02/03 |
| 5 | 两人并发领/交最后一个名额不超发 | 迁移03 |
| 6 | 任务关闭/参与者停用 → 明确结束（permanent_failures） | 插件 v3.2 |
| 7 | 插件 v3.2.0 全新安装 → 报名 → 领任务 → 采集 → 回传 → 进度增长 | 端到端 |
| 8 | 001 smoke 回流真实 landing（crowd_proofs 行/任务 progress/tracking 变化） | 监听中 |

---

## 四、交付物清单

- 代码（git `a018bd4`，已 push + 服务器同步）
- 分发件（Storage public bucket `crowd`，全部公网 200）
- 迁移 SQL ×3 + 总纲 ×1（`cloud/sql/`）
- 本报告（`cloud/AUDIT_FIX_REPORT_20261003.md`）
- 契约文档已更新（`crowd_extension/CROWD_CONTRACT.md` §v3.2 外部审计修复）

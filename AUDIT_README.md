# 众包美食家 · 审计包总览

> 生成时间：2026-10-02 · 版本 v3.1.0（并发加固） · git HEAD 61f93ef
> 用途：供外部 bot/审查者对「众包美食家」众包采集分发模块做独立审计
> 架构一句话：Chrome 扩展全自动采集 → security definer RPC 回传 → Supabase 权威校验入库 → 服务端/插件端/监听端三层并发保护

---

## 一、项目介绍

「众包美食家」是上海美食图鉴项目的**众包采集分发模块**（替代高成本 Apify 采集方案）：

- **参与者**：用自有小红书账号/设备/网络，安装浏览器插件全自动采集小红书公开笔记与口味评分
- **安全线**：插件内置硬编码保守基线 + 服务端拟合参数**只降不升**（日搜索≤30次、间隔60-120s、会话≤15min、一机一号）
- **回流**：采集结果经 security definer RPC 回传，服务端权威校验（URL/去重/评分锚定/幂等）→ 真实入库 → 任务进度增长；插件端 v3 加回流检测（服务端确认 + 连续零有效告警），**防虚假通过**
- **计酬**：按有效收录条数计酬（笔记 ¥0.5-1/条、评分 ¥1/条），拒收率>0.6 自动 suspend
- **分发**：在线报名页 apply.html → 下载 zip → 电脑/Android(Kiwi) 一键安装
- **对抗**：已完成 10 类红队攻击加固（批量注册/伪造URL/垃圾灌库/任务DoS/去重绕过/伪评分/未来时间戳/并发配额竞态/幂等绕过/键混淆）

## 二、文件清单与审核要点

### A. 项目介绍与规范（md）

| 文件 | 作用 | 审核要点 |
|---|---|---|
| `crowd_extension/README.md` | 项目总览/目录/快速开始 | 结构与实际代码一致性 |
| `crowd_extension/CROWD_CONTRACT.md` | 数据契约 v2（格式/获取/回传/同步四方一致） | 字段名/类型/枚举是否与实际 schema 逐字一致 |
| `cloud/CONCURRENCY.md` | 三层并发模型（服务端/插件端/监听端） | 行锁/幂等/唯一索引/原子UPDATE 覆盖是否完整 |
| `cloud/REDTEAM_REPORT.md` | 红队 10 类攻击加固报告 | 漏洞→修复→回归闭环是否可证伪 |
| `cloud/CODE_AUDIT_V1_20261002.md` | Lean 审计①显性问题 | 是否还有漏网显性坑 |
| `cloud/CODE_AUDIT_V2_20261002.md` | Lean 审计②历史隐性坑 | 历史事故根因覆盖 |
| `cloud/CODE_AUDIT_V3_RADICAL.md` | Lean 审计③精简方案 | 过度工程/可砍模块 |
| `cloud/CRAWLER-MODULE-SPEC.md` | 采集模块规范 | 采集字段定义与契约一致性 |
| `cloud/COLLECTION_SOP.md` | 采集 SOP | 安全线依据（XHS 反爬调研） |
| `cloud/SOURCE-PLAN.md` | 数据源规划 | 覆盖策略 |
| `cloud/APIFY_OPTIMAL_PLAN.md` | Apify 替代方案调研（已弃用） | 参考价值 |

### B. 插件端代码（Chrome 扩展）

| 文件 | 作用 | 审核要点 |
|---|---|---|
| `crowd_extension/manifest.json` | manifest v3（v3.1.0，host_permissions 仅 xiaohongshu+supabase） | 权限最小化是否成立 |
| `crowd_extension/src/background.js` | Service Worker：RPC 拉任务/管控闸门/调度/回传/回流检测 | ①`_running` 互斥防 alarm 重入；②proof_seq 幂等；③回流检测 recordFlow 逻辑 |
| `crowd_extension/src/safety_engine.js` | 安全线引擎 v3（本地基线 + 远程只降不升 + 回流检测原语） | ①clamp 只降不升是否有绕过路径；②device_salt 一机一号；③FLOW_STALL_THRESHOLD 判定 |
| `crowd_extension/src/content.js` | 页面注入采集（搜索结果/笔记详情） | 采集字段与契约一致、无隐私字段 |
| `crowd_extension/src/popup.html` | 状态面板（含回流健康行） | UI 与 background 状态映射 |
| `crowd_extension/src/onboarding.html` | 知情同意书 + 正式编号填写 | 合规声明、编号校验 |
| `crowd_extension/apply.html` | 在线报名 + 插件下载 | RLS 报名逻辑、device_salt |
| `crowd_extension/install.html` / `install-mobile.html` | 安装引导（电脑/Android） | zip 引用版本一致性 |
| `crowd_extension/crowd-install-mac.command` / `crowd-install-win.bat` | 一键安装脚本 | 无注入/无密钥泄漏 |

### C. 云侧代码（PM/运维）

| 文件 | 作用 | 审核要点 |
|---|---|---|
| `cloud/crowd_build.py` | 打包构建（注入 anon key、校验 JS 语法） | 注入逻辑、版本管理 |
| `cloud/crowd_admin.py` | 参与者管理（审核/发放编号/suspend） | 权限控制 |
| `cloud/crowd_ingest.py` | 采集数据入库 | 与 RPC 校验一致性 |
| `cloud/crowd_pack.py` | 任务包生成 | 包格式与插件解析一致性 |
| `cloud/crowd_scale.py` | 规模化/配额拟合 | 阈值参数依据 |
| `cloud/crowd_smoke_monitor.py` | 回流 smoke 监听器（flock 并发锁） | 快照/diff 正确性 |
| `cloud/crowd_tracking.py` | 回流 tracking 报告（每小时聚合） | 聚合口径 |
| `cloud/crowd_tracking_cron.sh` | 服务器 cron wrapper（unset 代理直连） | 环境变量处理 |

### D. 服务端 SQL（Supabase）

| 文件 | 作用 | 审核要点 |
|---|---|---|
| `cloud/sql/crowd_tables.sql` | 建表（5 表：participants/tasks/proofs/packs/logs） | schema 完整性、索引、RLS |
| `cloud/sql/crowd_rpc_security.sql` | RPC 安全层（security definer + 校验） | 权限边界、SQL 注入面 |
| `cloud/sql/crowd_harden_redteam.sql` | 红队加固 SQL（唯一索引/行锁/去重升级） | 并发安全、去重逻辑 |
| `cloud/sql/crowd_submit_proof_live_v2.sql` | crowd_submit_proof 线上权威函数定义 | 校验完整性、行锁、原子 UPDATE |
| `cloud/sql/crowd_harden_redteam_v1_backup.sql` | 加固前备份 | diff 对比 |

## 三、关键凭据（供审查者理解，勿外发）

- Supabase ref：`bdwrhshgdeghgyzwpxnl`；REST `https://bdwrhshgdeghgyzwpxnl.supabase.co/rest/v1`
- RPC：`crowd_fetch_tasks(participant_id, exclude_task_ids)` / `crowd_submit_proof(participant_id, envelope)`
- anon key（公开可分发，打包进插件）：`sb_publishable_c93Xe...`（见 `app/.env.local`）
- **service_role / Management token 不在本包内**（机密，仅服务器 deploy.env / 本机会话）

## 四、已发布产物（公网，供验证）

- 插件包：`https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v3.1.0.zip`
- 报名页：`https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/apply.html`
- 安装引导：`.../crowd/install.html`、`.../crowd/install-mobile.html`

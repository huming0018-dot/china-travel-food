# 当前状态 · STATUS

> 最后更新：2026-10-02 02:05（PM窗口维护 · 夜间盘点第2轮）
> **🌙 夜间盘点·第2轮（02:00）**：工单37 | todo 23 | 进行中 5 | **done 9（00:00→02:00 +4）**。
> - ✅✅ **dev三组件+Apify开发侧全部完成**：#11 account_registry / #12 common_core / #13 data_gate / #15 apify_collect.py / #28 搜索引擎校准 → **done**（用户点名机制核心落地）
> - ✅ collector继续#1 Apify实跑（in_progress）
> - ✅ 云端脚本在跑：#23舰队catchup/#27findings/#29三段式cron；launchd调度器正常
> - ⏳ 待认领P0：#14/#26/#44(collector)；用户点名P1：#32-38/#45(collector) #36/#37/#39-43(dev)
> - 🔕 本轮nudge推送0条（dev P0已完成、其余nudge未到期，账本控制不刷屏=正常）
> **✅ 夜间执行计划已部署（2026-10-01 23:46，用户已审阅确认）**：
> - 3个定时任务已创建：00:00夜间盘点 / 02:00二次盘点 / 06:00夜间执行报告（TG+飞书推送）
> - C类12项窗口执行指令已写入 INBOX/collector.md + INBOX/dev.md（窗口唤醒即执行）
> - PM调度器（pm_dispatch.py + launchd 每15分钟）持续运行：P0/用户点名未认领自动推送+有界提醒
> - 用户入睡，夜间由PM自动调度监督；07:30后窗口执行，早间验收
> **✅ PM主动调度器上线（2026-10-01晚）**：`cloud/pm_dispatch.py` + launchd每15分钟自动扫描task_queue，发现P0/用户点名工单超SLA未认领 → 自动推送TG+飞书（已验证TG+飞书双通道真实送达）+写INBOX双保险。**用户无需去窗口喊话**，PM系统自动调度唤醒窗口。见 ROLE_SYNC.md「提醒机制」。
> **✅ Apify已充值成功+限额解锁（2026-10-01晚）**：Starter $19/月已生效（预付$19额度+64GB RAM/32并发/30数据中心代理/Bronze折扣），Mastercard 4395已绑定Primary。**平台限额已从$19调到$40（Update successful已验证）**：$19超额空间按量自动扣卡（$0.20/CU，超额达$20提前结算），opspilot 402已解除，采集可端到端实跑。task_queue #1 已解除blocked→todo。
> **✅ 方案B（2026-10-01）：四窗口→三窗口**：QA职责并入PM，原QA窗口停用。用户只在PM窗口说话。见 ROLE_SYNC.md / WINDOWS.md / role-task-allocation.md。
> **✅ sync.sh v3**：开工强制渲染统一状态卡（数据/任务/账号/配额+过时事实校验），三窗口看同一张卡。
> 各窗口开始工作时运行 `bash sync.sh <角色>`，结束时运行 `bash sync.sh push "说明"`
> 任务唯一真源：task_queue（Supabase）。窗口无独立待办文档。

## ⚠️ 服务器状态（2026-10-01 已查明，Q-013）
- **主机健康**：经香港节点SSH登录成功（HK_SSH_OK），sshd正常，容器food-cloud正常运行
- **真实原因**：deuce 本机运营商到腾讯IP（49.234.35.92）的直连路径/NAT 被拦（全端口refused），会自行恢复
- **作业方式**：经 Clash 代理（127.0.0.1:7897）或强制境外节点通道可正常 SSH/部署
- 影响：容器内 cron 任务暂停，需恢复后确认
- **下一步**：collector 窗口负责排查恢复；QA 跟踪状态

## 采集（CTFS_登录）
- 账号：A=cookie在服务器IP上被失效（probe=-100）/ B=parked
- 采集状态：**停摆**，已决定切换Apify云采集方案，不再用本地账号+IP
- 地图API：高德key#1正常（月配额765/4500），高德key#0月配额超限，腾讯key日配额超限（明天0点重置）
- 数据：1473家在营餐厅，电话空196家，营业时间空547家

## 开发（CTFS_开发）
- 已完成：前端P0修复、后端采集P0修复、提醒机制整顿、角色同步机制、公共状态模块、sync.sh v2
- 最近commit：1f37712（8逻辑角色→4窗口职责分配）
- 待做：由PM分配（见任务队列）
- 部署：腾讯云容器food-cloud运行中（当前SSH不可达待排查）

## QA（CTFS_QA · 本窗口）
- 问题台账：QUALITY_ISSUES.md（18条：open 7 / verifying 2 / closed 9）
- 本次完成：8逻辑角色→4窗口职责分配、task_queue归属核对修正
- 机制：qa_broadcast.py统一播报（TG唯一通道，飞书已关）
- 风险：采集停摆导致口味分无法补全（1152家空，78%）

## PM（CTFS_PM · 新增）
- 职责：项目总调度、任务分配、优先级管理、验收交付、进度推动
- 章程：`ROLE_PM.md`，职责分配：`role-task-allocation.md`
- 开工：`bash sync.sh pm`

## 任务队列（已按新分配修正归属）
| ID | 优先级 | 分配给 | 状态 | 任务 | issue |
|----|--------|--------|------|------|-------|
| 1 | P0 | **collector** | todo | Apify集成（原dev，已改） | Q-012 |
| 2 | P1 | collector | todo | 新腾讯地图key | Q-011 |
| 3 | P1 | **collector** | todo | 高德评论清理（原dev，已改） | Q-004 |
| 4 | P1 | collector | todo | frontier污染验证 | Q-010 |
| 5 | P1 | collector | todo | 口味分补全 | Q-005 |
| 8 | P1 | pm | todo | PM建立项目推进机制 | - |
| 6 | P2 | collector | todo | 营业时间补全 | Q-006 |

## 四窗口职责速览（详见 role-task-allocation.md）
- **collector** = CR爬虫 + OPS运维：信源/反爬/解析/深覆盖/质量门 + 账号/配额/IP/看门狗
- **dev** = ARCH + ALG + FE：表/迁移/部署 + 评分/算法 + 界面（冻结）
- **pm** = PM产品 + 验收口径：方向/优先级/验收/推进
- **qa** = QA测试 + 跨角色协调：A–H审计/回归/红队 + 播报/台账/机制
- **用户** = 付款/扫码/密钥/最终拍板
- **云端自动工人** = cron 19条 + 机械扫描，无人值守

## 下一步（由PM推进）
1. 【collector】排查服务器SSH不可达（P0，阻塞一切）
2. 【collector】Apify集成（P0，恢复采集的唯一路径）
3. 【collector】提供新腾讯key做轮换
4. 【pm】建立任务推进机制并分配本轮迭代
5. 【qa】Apify集成后验证采集恢复+口味分补全

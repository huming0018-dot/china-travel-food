# 当前状态 · STATUS

> 最后更新：2026-10-01 10:05（PM窗口维护）
> **四窗口职责分配已定稿**：`role-task-allocation.md`（8逻辑角色→4窗口）
> **2026-10-01 角色互换**：本窗口(CTFS_QA)任PM，原CTFS_PM任QA，见 ROLE_HANDOVER.md
> 各窗口开始工作时运行 `bash sync.sh <角色>`，结束时运行 `bash sync.sh push "说明"`
> 开工时 sync.sh 会显示本窗口职责边界，请严格遵守。

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

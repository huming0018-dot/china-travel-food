# 角色同步机制 · ROLE_SYNC

> 最后更新：2026-10-01（**方案B·三窗口收敛**：四窗口→三窗口，QA并入PM）
> 目的：PM/采集/开发 三窗口状态透明、交接无歧义、问题不遗漏。**用户只在PM窗口说话**。
> 协作工具：sync.sh（统一状态卡）+ task_queue（唯一真源）+ STATUS.md（状态快照）+ INBOX/信箱
> 完整角色分配：role-task-allocation.md | 角色工作标准：ROLE_STANDARD.md | 会话注册表：WINDOWS.md

## 三窗口职责边界（2026-10-01 方案B）

| 窗口 | 会话 | 职责 | 不做什么 |
|------|------|------|----------|
| **PM（本窗口）** | CTFS_PM (38444430093837826) | **唯一调度中枢**：任务分配/优先级/验收/红队/播报/体系总图/推动。吸收原QA职责（质量门禁release_audit A–H、回归、红队挑刺、问题台账）。用户只在此说话 | 不写业务代码、不采数据、不操作服务器 |
| **采集** | CTFS_爬虫工程师 (38440446099762434) | 小红书/Apify/B站/高德采集、账号维护、数据补全、采集通道SOP、LLM舰队/探针 | 不改前端UI、不决定产品方向、不做验收 |
| **开发** | CTFS_数据库及架构工程师 (38444479935001090) | 代码/组件/部署/schema/算法/前端(冻结)；三组件实现（account_registry/common_core/data_gate） | 不碰账号cookie、不决定采集策略、不做验收 |

## 状态同步机制（v3：单一真源）

```
用户 ──只在PM窗口说话──▶ PM
                          │ 登记 task_queue（唯一真源）
                          │ 渲染统一状态卡（sync.sh）
                          ▼
                    采集窗口 ──开工sync.sh──▶ 看同一张状态卡
                    开发窗口 ──开工sync.sh──▶ 看同一张状态卡
                          │
                          └──完成→sync.sh push→PM验收→done
```

**铁律**：
1. **task_queue是唯一真源**：任务/问题/状态只写task_queue，不双写md
2. **统一状态卡**：三窗口开工必须跑 `bash sync.sh <角色>`，强制渲染同一张卡（任务/事件/账号/配额/数据），不看卡不许干活
3. **窗口无独立待办文档**：HANDOFF.md等不再承担"待办"职能，待办一律在task_queue
4. **用户不传话**：用户只在PM窗口发指令，PM统一调度两执行窗口
5. 状态不更新=工作没做；问题不登记=不存在；P0不过夜
6. 部署后必须验证，不能"我觉得应该好了"

## 每日同步节奏

| 时间 | 动作 | 负责人 |
|------|------|--------|
| 开工 | 跑 sync.sh <角色> 看统一状态卡 | 各窗口 |
| 随时 | 发现P0问题→task_queue登记→PM推动 | 各窗口 |
| 每日 | PM盘点task_queue，更新STATUS.md | PM |
| 18:00 | 当日总结，更新STATUS+task_queue | 各窗口 |

## 提醒机制（柔和模式 · 2026-10-01升级为"PM主动调度"）

- **通道**：Telegram + 飞书应用双通道（notifier.py，已验证：TG status200 / 飞书 code=0）
- **PM主动调度器 `cloud/pm_dispatch.py`（新增，解决"窗口不读INBOX就静默"）**：
  - 每15分钟（launchd `com.doubao.pmdispatch`）扫描 task_queue
  - 发现 **P0 或 source=user** 且 status=todo 超SLA未认领 → 自动推送TG+飞书（"工单#N待认领"）
  - 有界提醒（30m/1h/2h/1d，用尽不刷屏）+ 写INBOX双保险
  - **用户无需去窗口喊话**：调度由PM系统自动完成，窗口收到推送即被唤醒
- **心跳**：每60分钟一次，仅数据摘要，无需操作
- **WARN**：系统自动处理中的问题，2小时冷却，无需操作
- **ACTION**：仅P0且必须用户亲自处理（如扫码登录），首次立即推，之后按计划有界提醒
- **RESOLVED**：问题解决，只推一次收尾

## 问题流转

```
发现问题 → PM登记task_queue（P0/P1/P2 + 唯一assignee）
    ↓
P0：PM立即通知对应窗口，当天修复
P1：对应窗口排期，本周内修复
P2：纳入迭代计划
    ↓
修复完成 → sync.sh push → PM验收 → 关闭或重开
```

## 协作工具（v3）

### sync.sh 自动同步脚本（v3：统一状态卡）
每个窗口**开始工作时**运行：
```bash
bash sync.sh collector   # 采集窗口
bash sync.sh dev         # 开发窗口
```
自动：git pull → **渲染统一状态卡**（我的任务/最新事件/账号/配额/数据/过时事实校验）→ 红字提示待认领。

**结束工作时**运行：
```bash
bash sync.sh push "完成了xxx"
```

### task_queue 任务队列（Supabase数据库表·唯一真源）
```bash
python3 cloud/task_helper.py stats           # 统计概览
python3 cloud/task_helper.py list dev         # 查看分配给开发的任务
python3 cloud/task_helper.py claim 5         # 认领任务#5
python3 cloud/task_helper.py done 5           # 完成任务#5
python3 cloud/task_helper.py add "xxx" dev P0  # 创建任务
```
字段：id / title / description / assignee(dev|collector) / status(todo|in_progress|done|blocked) / priority(P0|P1|P2) / source / issue_id

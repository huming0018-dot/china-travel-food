# 角色同步机制 · ROLE_SYNC

> 最后更新：2026-10-01（**角色互换：原CTFS_QA↔原CTFS_PM**）
> 目的：让ctfs开发、ctfs登陆（采集）、QA监管官、PM四窗口状态透明、交接无歧义、问题不遗漏。
> 协作工具：sync.sh（自动同步脚本）+ task_queue表（任务队列）+ STATUS.md（状态快照）+ QUALITY_ISSUES.md（问题台账）+ INBOX/信箱
> 完整角色分配：role-task-allocation.md | 角色工作内容：ROLE_WORK_SPEC.md | 会话注册表：WINDOWS.md

## 四角色职责边界（2026-10-01 互换后）

| 角色 | 窗口会话 | 职责 | 不做什么 |
|------|---------|------|----------|
| **PM（原CTFS_QA窗口）** | CTFS_QA (38444430093837826) | 项目总调度、任务分配、优先级管理、验收交付、进度推动、体系总图、跨窗口协调、催认领 | 不写代码、不采数据、不操作服务器 |
| **QA（原CTFS_PM窗口）** | CTFS_PM (38444969091640322) | 质量审计、问题跟踪、红队测试、release_audit A–H、回归抽样、播报/台账维护 | 不写业务功能、不替用户操作账号、不做产品决策 |
| **ctfs开发** | CTFS_数据库及架构工程师 (38444479935001090) | 前端/后端代码开发、Bug修复、功能迭代、部署；公共组件实现（account_registry/common_core/data_gate） | 不碰账号cookie、不决定采集策略 |
| **ctfs登陆（采集）** | CTFS_爬虫工程师 (38440446099762434) | 小红书/B站/高德采集、账号维护、cookie更新、数据补全；采集通道SOP | 不改前端UI、不决定产品方向 |

## 状态同步文件

所有角色共享 `STATUS.md`（项目根目录），每次工作开始时读取，结束时更新。

```markdown
## 当前状态（YYYY-MM-DD HH:MM）

### 采集
- 账号：A=在线/B=在线
- 昨日新增：笔记X篇 / 评论Y条 / 餐厅Z家
- 阻塞：无 / 具体问题

### 开发
- 正在做：XXX
- 待部署：XXX
- 最近commit：XXX

### QA
- 本周发现问题：X个（P0=a, P1=b, P2=c）
- 待验证：XXX
- 风险：XXX

### 下一步
1. ...
2. ...
```

## 交接流程

1. **开始工作**：读取 STATUS.md + QUALITY_ISSUES.md，了解当前状态和待办
2. **工作中**：发现问题立即写入 QUALITY_ISSUES.md，不积压
3. **结束工作**：更新 STATUS.md，commit并push
4. **阻塞升级**：如果某角色被阻塞超过2小时，在STATUS.md中标注并@其他角色

## 每日同步节奏

| 时间 | 动作 | 负责人 |
|------|------|--------|
| 09:00 | 检查采集状态+数据质量，更新STATUS | QA监管官 |
| 12:00 | 午间验证：部署的修复是否生效 | QA监管官 |
| 18:00 | 当日总结，更新问题台账，commit代码 | 各角色 |
| 随时 | 发现P0问题立即推送TG告警 | 系统自动 |

## 问题流转

```
发现问题 → 写入QUALITY_ISSUES.md（P0/P1/P2）
    ↓
P0：QA立即通知开发，开发当天修复
P1：开发排期，本周内修复
P2：纳入迭代计划
    ↓
修复完成 → QA验证 → 关闭或重开
```

## 提醒机制（柔和模式）

- **通道**：仅Telegram（飞书已关闭）
- **心跳**：每60分钟一次，仅数据摘要，无需操作
- **WARN**：系统自动处理中的问题，2小时冷却，无需操作
- **ACTION**：仅P0且必须用户亲自处理（如扫码登录），首次立即推，之后每天提醒一次，共3次
- **RESOLVED**：问题解决，只推一次收尾

## 铁律

1. 状态不更新=工作没做
2. 问题不登记=不存在
3. P0不过夜
4. 跨角色请求必须写在STATUS.md或task_queue表，不私聊
5. 部署后必须验证，不能"我觉得应该好了"

## 协作工具（2026-09-30新增）

### sync.sh 自动同步脚本
每个窗口**开始工作时**运行：
```bash
bash sync.sh dev         # 开发窗口
bash sync.sh collector   # 采集窗口
bash sync.sh qa          # QA窗口
```
自动：git pull → 显示STATUS.md → 显示P0问题 → 显示分配给自己的任务 → 显示最近commit。

**结束工作时**运行：
```bash
bash sync.sh push "修复了登录bug"
```
自动：git add -A → commit → push。

### task_queue 任务队列（Supabase数据库表）
建表SQL：`db/migrations/017_task_queue.sql`（需在Supabase SQL Editor执行一次）。

```bash
# 查看任务
python3 cloud/task_helper.py stats           # 统计概览
python3 cloud/task_helper.py list dev         # 查看分配给开发的任务
python3 cloud/task_helper.py list todo        # 查看所有待办

# 认领/完成任务
python3 cloud/task_helper.py claim 5         # 认领任务#5
python3 cloud/task_helper.py done 5           # 完成任务#5

# 创建任务
python3 cloud/task_helper.py add "修复登录bug" dev P0
```

字段：id / title / description / assignee(dev|collector|qa) / status(todo|in_progress|done|blocked) / priority(P0|P1|P2) / source / issue_id

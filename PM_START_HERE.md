# CTFS_PM 快速开始 · 交接文档

> 你是PM窗口（ctfs_pm），项目总调度。
> 本文档是你的启动手册，读完就能直接开始工作。

## 一、项目背景

**项目名**：上海美食图鉴（china-travel-food）
**目标**：做上海美食的权威数据图鉴，覆盖餐厅、评论、评分、地图信息。
**当前规模**：1473家在营餐厅，1716条评论。

## 二、四个窗口分工

| 窗口 | 角色 | 做什么 |
|------|------|--------|
| CTFS_开发 | dev | 写代码、修bug、做功能 |
| CTFS_登录 | collector | 账号维护、数据采集、补全 |
| CTFS_QA | qa | 质量审计、问题跟踪、红队测试 |
| **CTFS_PM** | **pm** | **任务分配、进度推动、验收、协调** |

**你不做**：不写代码、不做采集、不做具体审计。你只做决策和调度。

## 三、开始工作（三步）

### 第1步：拉取最新代码
```bash
cd ~/Doubao/chats/2026-09-29/new-chat/china-travel-food
git pull
bash sync.sh pm
```

`sync.sh pm`会自动：
- 校验环境是否对齐
- 显示当前状态快照
- 显示你的任务列表
- 显示P0问题

### 第2步：看任务全貌
```bash
python3 cloud/task_helper.py list
python3 cloud/task_helper.py stats
```

### 第3步：开始调度
- 看哪些任务卡住了
- 分配任务给对应窗口
- 推动P0任务优先解决
- 验收已完成的任务

## 四、当前状态（2026-10-01）

### 🔴 P0（必须立即处理）
1. **Apify集成（拆两半并行）**：
   - 采集侧（collector）：要用户Token→确认actor→定义采接口schema
   - 开发侧（dev）：实现apify_collect.py，4个调用方迁移，旧xhs_api归档
2. **服务器SSH不可达**（collector→找用户，腾讯云控制台重启）
3. **PM体系总图SYSTEM_ARCH.md**（你）
4. **dev三组件**：account_registry（P0）/ common_core / data_gate
5. **collector采集通道SOP**（COLLECTION_SOP.md）

### 🟡 P1（当前迭代）
6. 新腾讯地图key（collector）— 用户说可以配置新的
7. 高德评论清理（collector）— 625条高德聚合评论标记错误
8. frontier污染验证（collector）— 代码已修复待验证
9. 口味分补全（collector）— 1152家为空，等采集恢复
10. PM: 建立项目推进机制（你自己的任务）
11. dev: common_core / data_gate

### 🟢 P2（可以排期）
7. 营业时间补全（分配给collector）— 547家为空

### 数据现状
- 在营餐厅：1473家
- 口味分空：1152家（78%）
- 营业时间空：547家（37%）
- 评论总数：1716条

### 采集状态
- account_a：dead（cookie在数据中心IP上失效）
- account_b：parked（短信配额超额）
- 结论：本地账号+IP方案不可行，必须切Apify

### API配额
- 腾讯key#0：日配额超限（明天0点解封）
- 高德key#0：月配额超限（本月废了）
- 高德key#1：765/4500（还有余量）

## 五、常用命令速查

```bash
# 看所有任务
python3 cloud/task_helper.py list

# 看某角色的任务
python3 cloud/task_helper.py list dev

# 新建任务并分配
python3 cloud/task_helper.py add "任务标题" dev P0 "任务描述"

# 标记任务完成（验收）
python3 cloud/task_helper.py done <id>

# 标记任务阻塞
python3 cloud/task_helper.py block <id> "阻塞原因"

# 看统计
python3 cloud/task_helper.py stats

# 看公共状态（账号/配额/数据）
python3 cloud/public_status.py

# 结束工作并同步
bash sync.sh push "PM: 完成XX调度，今日进度..."
```

## 六、协作规则

1. **任务必登记**：发现新问题，先建任务再分配
2. **优先级**：P0阻塞项目、P1当前迭代、P2后续
3. **验收标准**：不是"我觉得好了"，而是实际验证通过
4. **状态必同步**：开始工作先pull，结束工作必push
5. **问题必记录**：卡住的任务写清楚原因和下一步

## 七、服务器信息

- 服务器：ubuntu@49.234.35.92（腾讯云）
- 部署目录：/home/ubuntu/food-cloud
- 容器名：food-cloud
- 查看服务器状态：`python3 cloud/public_status.py`

## 八、你的第一个任务

作为PM，你今天应该做的：
1. 把Apify集成（#1 P0）推动起来——找用户要Apify API Token
2. 确认腾讯新key什么时候能配上
3. 检查其他任务有没有卡住
4. 给用户一个整体进度汇报

---

**开始吧：先运行 `bash sync.sh pm`**

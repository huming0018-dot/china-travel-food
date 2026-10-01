# 全项目审计与优化方案 · AUDIT

> 发布：2026-10-01 | QA窗口统筹 | 依据：用户全部需求 + 代码彻查 + 任务分配审查
> 目标：精益精简、责任到人、不遗漏遗忘

---

## 第一部分：用户需求清单（全部需求，防止遗漏）

| # | 需求 | 状态 |
|---|------|------|
| R1 | 美食图鉴双角色（采集/开发）分工，解决"代码有坑难察觉、虚假通过" | 已建4窗口 |
| R2 | 项目被监管、有人推动（不按周，立刻上手） | 部分（认领未落地） |
| R3 | QA模拟多重身份残忍挑刺→汇总意见→用户审阅→开发迭代 | 已做一轮，需制度化 |
| R4 | 全流程标准化自动工作流，快速迭代 | 部分（无迭代节奏） |
| R5 | 采集问题+报错代码+解决方式，分两个md | 未交付（待做） |
| R6 | 多窗口协作体系（公共状态/账号/流量/费用拉平） | 已建public_status |
| R7 | sync模块可扩展接入更多窗口 | 已支持 |
| R8 | sync运行前校验：窗口对齐/环境治理/边界清晰 | 已建校验 |
| R9 | 提醒挪到QA：停飞书、TG唯一、QA整合播报、掌握全局进度 | 已建qa_broadcast |
| R10 | 自检自巡提示 + 自动调度 | 已建19条cron |
| R11 | 修复失败序列（gap_pool空转/米其林重复/日志重复） | 已修复 |
| R12 | 8逻辑角色→按4窗口分配（PM/开发/采集/QA） | 已分配 |
| R13 | 各窗口确认职责 + 问题负责人说明解决办法 | 待各窗口回复 |
| R14 | 服务器SSH不可达由collector负责，找用户 | 已登记Q-013 |
| R15 | **工作认领/模块合并/模块衔接不满意** → 彻查优化（本次） | 见下 |

---

## 第二部分：彻查发现（代码 + 分配 + 衔接）

### A. 工作认领：8个任务全部"躺平"

**现状**（task_queue，2026-10-01 实查）：
- 8个任务 **全部 status=todo**，0个认领、0个完成
- 分配倾斜：collector 6个 / pm 1个 / **dev 0个**
- 任务创建9-30，至今无人认领

**根因**：
1. 认领是"自愿"的，sync.sh没有强制提示待认领任务
2. PM的"推动"职责没有执行（PM自己的任务#8也未认领）
3. 无逾期升级机制：todo躺多久都没人管
4. dev完全空转——最需要人的窗口没有任务

### B. 模块收敛：80个py文件，实际调度仅19个

**现状**（cloud/目录实查）：
- 共80+个.py
- cron/entrypoint实际调度：19个
- import工具库（health/notifier/map_helpers/map_quota/task_helper/common等）：约10个
- **孤儿/一次性脚本**：_diag_tree / _inspect_pool / _stop_pool / fix_paths 等（下划线前缀诊断脚本）
- 已有一次精简（commit d5f40bf删1578行），但不彻底，无模块分类清单

**风险**：模块边界模糊 → "合并但保持功能不变"没有清单、没有回归验证 → 合并=隐患

### C. 模块衔接：3处断链

1. **xhs_api依赖链**：被 account_repair / gap_runner / review_ugc_fill / ugc_longrun 4处引用
   → Apify切换时4处要改，未定义切换边界和统一接口
2. **文档不同步**：
   - ROLE_SYNC.md 仍写"三角色"（缺pm）❌
   - PM_START_HERE.md 写"Apify集成分配给dev"（实际已改collector）❌
3. **双轨记录**：QUALITY_ISSUES.md（18条）与 task_queue（8条）并行，无同步关系 → 会遗漏

### D. 责任到人：表述不统一

- Q-001负责人写"用户+采集角色"、Q-002写"开发角色"、Q-004写"开发角色"
- task_queue中Q-004已assignee=collector → **文档和队列打架**
- 无"唯一负责人"硬规则

---

## 第三部分：优化方案

### 方案一：认领机制改造（让任务不躺平）

| 措施 | 落地 |
|------|------|
| 1. 强制提示 | sync.sh开工时：本角色有todo任务 → 红字提示"请认领，未认领将上报PM" |
| 2. 认领锁定 | claim后 assignee+in_progress+claimed_by；done必须QA验证后生效 |
| 3. 逾期升级 | P0认领后8h未done / P1 24h → 自动进PM播报，PM推动 |
| 4. PM每日盘点 | pm窗口每天运行 stats，任务不进则问责 |
| 5. 平衡分配 | Apify集成拆两半：collector（Token+采接口）+ dev（apify_collect.py代码）并行 |

### 方案二：模块收敛（精益精简）

1. 新建 **MODULES.md** 四层分类：
   - L1 调度层（19个cron模块）— 不动
   - L2 服务层（被import库）— 不动
   - L3 一次性/诊断（_diag_tree/_inspect_pool/_stop_pool/fix_paths）— 移archive/
   - L4 待合并（功能重叠对，如 review_ugc_fill vs review_apify_fill）— 列合并清单
2. **合并必带回归验证**：每个合并动作跑一次 dry-run 对比输出，功能不变才commit
3. 目标：cloud/*.py 80 → 核心~60（一次性清走），含归档备份不丢功能

### 方案三：衔接治理（不遗漏）

| 措施 | 落地 |
|------|------|
| 1. 单一真源 | 任务以 task_queue 为准；QUALITY_ISSUES.md 改为摘要指向队列，不再双写 |
| 2. 文档同步规则 | 任何 assignee/状态变更 → 操作者同步更新 STATUS/PM_START_HERE/ROLE_SYNC |
| 3. xhs_api切换边界 | 新 apify_collect.py 提供同接口，4个调用方各改1行；切换后旧文件进archive |
| 4. 服务器监测 | 恢复SSH后，QA播报内置连通探测，不通立即ACTION告警 |

### 方案四：责任到人（四象限）

```
每个任务 = 唯一assignee + 唯一issue_id（task_queue真源）
发现问题 → 立即POST task_queue（不写md）
认领 → claim 锁定
完成 → done + QA验证 + 播报RESOLVED
逾期 → 升级PM → PM推动或用户介入
```

---

## 第四部分：立即落地清单（今天）

| # | 动作 | 负责人 | 状态 |
|---|------|--------|------|
| 1 | MODULES.md 四层分类 + 合并清单 | qa（我） | 待执行 |
| 2 | sync.sh 加"待认领强制提示" | qa（我） | 待执行 |
| 3 | Apify集成拆两半重新分配 | qa（我）→pm确认 | 待执行 |
| 4 | 服务器SSH恢复（P0） | collector→找用户 | 待认领 |
| 5 | 文档同步修正（ROLE_SYNC/PM_START_HERE） | qa（我） | 待执行 |
| 6 | QUALITY_ISSUES与task_queue合一 | qa（我） | 待执行 |
| 7 | R5需求：采集问题+报错代码两个md | collector+dev | 待认领 |

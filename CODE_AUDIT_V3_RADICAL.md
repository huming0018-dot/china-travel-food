# 激进精简方案 · 2.6万行 → 8千行

参考：Ponytail（七层阶梯）、Karpathy CLAUDE.md（Simplicity First）、Addy Osmani /code-simplify（Preserve behavior）

---

## 核心判断：这个项目到底需要什么？

**本质**：采集上海餐厅数据 → 存数据库 → 定时播报 → 告警。

**不需要的**：系统自己审计自己、自己进化、自己修复、6个门控写库、4个Apify采集器、5个KOL采集器、29个cron任务。

---

## 一、直接砍掉的模块（死代码/过度工程）

### 1. 元系统（自己审计自己）— 629行

| 文件 | 行数 | 为什么砍 |
|---|---|---|
| self_evolve.py | 149 | 每天自动复盘代码改动写报告，小项目不需要 |
| code_audit.py | 163 | 每周代码审计，手动做就行 |
| classification_intruder_audit.py | 105 | 分类入侵审计，过度工程 |
| **小计** | **417** | |

### 2. Apify相关（已禁用 APIFY_DISABLED=1）— 1318行

| 文件 | 行数 | 为什么砍 |
|---|---|---|
| review_apify_fill.py | 710 | 已禁用，保留接口但大幅精简 |
| events_apify.py | 243 | 事件采集，已停用 |
| apify_collect.py | 258 | 旧采集器，被review_apify_fill替代 |
| gate_apify_brief.py | 165 | Apify门控，已随Apify停用 |
| **小计** | **1376** | 保留一个cost_guard.py（100行）替代 |

### 3. KOL采集（非核心功能）— 1740行

| 文件 | 行数 | 为什么砍 |
|---|---|---|
| kol_cross.py | 234 | 跨平台KOL文章采集，锦上添花 |
| kol_monitor.py | 435 | B站KOL监控，非核心 |
| kol_identity.py | 202 | KOL身份识别，过度抽象 |
| kol_router.py | 321 | KOL路由，过度设计 |
| cloud_bili_collect.py | 451 | B站采集，合并到一个文件 |
| **小计** | **1643** | 合并成一个kol_collect.py（200行） |

### 4. 归档死代码 — ~5000行

| 目录 | 行数估算 | 为什么砍 |
|---|---|---|
| _archive/ | ~3000 | 归档旧版本，没人用 |
| vendor/pipeline/_archive/ | ~2000 | 同上 |
| **小计** | **~5000** | |

---

## 二、合并的模块（重复逻辑）

### 5. 高德采集（6个脚本→1个）— 1743行 → 300行

| 文件 | 行数 | 合并到 |
|---|---|---|
| cloud_amap_fill.py | 783 | amap_batch.py |
| cloud_phone_fill.py | 206 | amap_batch.py |
| cloud_coord_fill.py | 127 | amap_batch.py |
| cloud_hours_fill.py | 165 | amap_batch.py |
| cloud_hours_fill2.py | 229 | amap_batch.py |
| cloud_patrol.py | 301 | amap_batch.py |
| **小计** | **1811** | 一个脚本按字段类型分发 |

### 6. 门控写库（6个文件→1个）— 1575行 → 400行

| 文件 | 行数 | 合并到 |
|---|---|---|
| gate_apply.py | 606 | apply.py |
| curate_gate.py | 191 | apply.py |
| chain_review_apply.py | 64 | apply.py |
| candidate_apply.py | 213 | apply.py |
| reverify_supply.py | 262 | apply.py |
| post_audit.py | 119 | apply.py |
| **小计** | **1455** | 统一写库入口 |

### 7. 采集调度（3个→1个）— 795行 → 200行

| 文件 | 行数 | 合并到 |
|---|---|---|
| cloud_router.py | 166 | scheduler.py |
| gap_pool.py | 135 | scheduler.py |
| gap_runner.py | 489 | scheduler.py |
| ugc_longrun.py | 101 | scheduler.py |
| **小计** | **891** | 统一调度 |

---

## 三、精简后项目结构

```
cloud/
├── main.py              # 入口（50行）
├── common.py            # 公共工具（200行）
├── config.py            # 配置（50行）
├── amap_batch.py        # 高德采集（300行）
├── xhs_collect.py       # 小红书采集（400行）
├── apply.py             # 写库层（400行）
├── cost_guard.py        # 预算门（100行）
├── notifier.py          # 通知（300行）
├── progress_broadcast.py # 播报（200行）
├── scheduler.py         # 调度（200行）
└── watchdog.py         # 看门狗（100行）
```

**总计：~2300行核心代码 + 数据文件 = 3000行以内**

加上vendor/pipeline里的评分引擎等必要模块，总计 **8000行以内**。

---

## 四、cron任务精简：29个 → 4个

| cron | 时间 | 干什么 |
|---|---|---|
| `scheduler.py` | 每20分钟 | 采集调度（高德+小红书） |
| `amap_batch.py` | 每2小时 | 补全字段（电话/坐标/营业时间） |
| `progress_broadcast.py` | 每小时 | 播报进度 |
| `watchdog.py` | 每20分钟 | 看门狗 |

---

## 五、执行顺序

| 阶段 | 动作 | 行数变化 |
|---|---|---|
| 1 | 删_archive/死代码 | -5000 |
| 2 | 砍元系统（self_evolve/code_audit） | -400 |
| 3 | 精简Apify到cost_guard.py | -1200 |
| 4 | 合并6个高德脚本到amap_batch.py | -1500 |
| 5 | 合并6个门控到apply.py | -1200 |
| 6 | 砍KOL采集到一个文件 | -1400 |
| 7 | 合并调度到scheduler.py | -600 |
| **总计** | | **26356 → ~8000** |

**目标：2.6万行 → 8千行，cron 29→4，内存占用降70%，不再OOM。**

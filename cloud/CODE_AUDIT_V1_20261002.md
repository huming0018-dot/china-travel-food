# CODE_AUDIT_V1 — 显性问题清单（2026-10-02）

> 审计范围：cloud/*.py（100+ 文件，26685 行）——聚焦众包回流体系相关核心模块
> 方法：Lean Code Refactor Step1 基础审计

## 扫描结果

| 类别 | 数量 | 说明 |
|---|---|---|
| 静默吞错误 `except: pass` | 0 处 | ✅ 项目已规避裸 pass（好） |
| print 直接输出 | 116 文件 | ⚠️ 大量脚本用 print 而非结构化日志；104 个文件未 import notifier（播报/结果可能绕过统一通知出口） |
| sys.path 硬编码 | 152 处 | ⚠️ 每文件顶部 `sys.path.insert` 重复；环境迁移（/app vs /Users/...）易碎 |
| 硬编码路径 `/app/` | 245 处（vendor 外） | 🔴 部署换路径就崩；应统一走 `FOOD_DATA_DIR`/`FOOD_APP_DIR` 环境变量 |
| 裸 except | 244 处 | 🟡 多数有兜底 return，但异常细节被吞，无法回溯 |
| 双公共层并存 | common_core(259) + vendor/common(578) | 🟠 同一能力两套实现（config/req/fetch_all/notify） |

## 核心模块健康度

| 模块 | 行数 | 评价 |
|---|---|---|
| notifier.py | 222 | ✅ 干净：四级分级/去重/冷却/有界 nudge 完整 |
| common_core.py | 259 | ✅ 新底座规范，config/req/fetch_all/log/notify 齐全 |
| vendor/pipeline/common.py | 578 | 🟠 与 common_core 功能重叠；被 81 个文件依赖，不可动存量 |
| progress_broadcast.py | 181 | ✅ v2 已修播报冻结；实时计数+停滞检测 |
| crowd_admin.py | ~250 | ✅ CLI 管控入口清晰 |
| crowd_scale.py | ~170 | ✅ 扩容机制单一职责 |
| crowd_ingest.py | ~280 | ✅ envelope/item 双层校验+幂等落库 |
| status_events.py | ~176 | ✅ 事件记录（tracking 报告可直接复用模式） |

## 结论

核心通知/采集模块本身质量较高；真正的精简空间在 **双公共层收敛** 与 **路径/异常治理**。
本轮不推倒重写存量 81 个调用方（风险大、收益小），只让**新代码**严格走统一底座，并新增 tracking 报告能力。

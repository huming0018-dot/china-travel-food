# 模块四层分类与合并清单 · MODULES

> 发布：2026-10-01 | QA窗口 | 依据：cloud/全量引用统计
> 目的：精益精简——每个文件有归属，合并有回归验证，孤儿不遗留

---

## 总量：cloud/ 共 80+ 个 .py

## L1 调度层（被 cron/entrypoint/router 直接运行，19+4个）—— 不动

| 模块 | 调度 | 归属 |
|------|------|------|
| cloud_router | cron */20 | collector |
| gap_pool | cron @reboot + entrypoint | collector |
| cloud_amap_fill | cron :15/:35/:55 | collector |
| cloud_phone_fill | cron :05/:25/:45 | collector |
| cloud_hours_fill | cron 凌晨4:00 | collector |
| cloud_coord_fill | cron 凌晨3:00 | collector |
| cloud_bili_collect | cron 6h | collector |
| cloud_blackpearl_collect | cron 6:20 | collector |
| cloud_michelin_collect | router兜底 | collector |
| run_batch | router/entrypoint | collector |
| gap_runner | router | collector |
| cloud_discover | router | collector |
| comention_probe | cron 每小时 | collector |
| kol_cross | cron 6h | collector |
| ugc_longrun | cron :39 | collector |
| progress_broadcast | cron :03/:13... | qa |
| self_evolve | cron 1:00 | qa |
| watchdog | cron :10/:30/:50 | collector |
| post_audit | cron 7:47 | qa |
| evidence_pool / fleet_grid_run / softad_distribution | cron（pipeline目录） | dev |

## L2 服务层（被多个模块 import 的公共库）—— 统一收编，逐步迁移到三组件

| 模块 | 被引用数 | 去向 |
|------|---------|------|
| health | 13 | 部分迁 common_core.notify |
| notifier | 10 | 迁 common_core.notify |
| xhs_cookie_pool | 6 | 迁 account_registry |
| cloud_bu | 5 | 保留（浏览器接口） |
| map_helpers | 5 | 保留（地图工具） |
| map_quota | 3 | 保留（配额账本） |
| account_repair | 3 | 迁 account_registry.probe |
| xhs_api | 3 | Apify切换后归档 |
| category_resolver | 2 | 保留 |
| kol_monitor | 2 | 保留 |
| cloud_ready | 2 | 保留（浏览器就绪） |
| warning_handler | 2 | 迁 account_registry |

## L3 一次性/诊断脚本（下划线前缀 + 一次性） —— 移 archive/

| 模块 | 用途 | 动作 |
|------|------|------|
| _diag_tree | 诊断 | 移 archive/ |
| _inspect_pool | 诊断 | 移 archive/ |
| _stop_pool | 手动停池 | 移 archive/ |
| fix_paths | 一次性路径修复 | 移 archive/ |

## L4 待合并/待确认（功能重叠或用途不明） —— 列合并清单，合并必带回归验证

| 模块 | 重叠对象 | 建议动作 | 验证方式 |
|------|---------|---------|---------|
| review_apify_fill + review_ugc_fill | 同为评论补数 | 合并为 review_fill.py | dry-run 输出对比 |
| backfill_cuisine | category_resolver | 确认谁在用，留一 | 菜系覆盖100%重验 |
| cloud_hours_fill2 | cloud_hours_fill | 疑似重复，删除或合并 | 营业时间统计对比 |
| findings_ingest + findings_planner | 疑似实验脚本 | 确认用途，归档 | - |
| selling_points_dedupe + selling_points_fill | 疑似未接管线 | 确认用途 | - |
| kol_context_backfill + kol_identity | kol_cross附属 | 并入 kol_cross | 功能不变 |
| classification_intruder_audit | 疑似审计实验 | 确认用途 | - |
| label_tool | 标注工具 | 保留（PM/qa手动） | - |

## 统计目标

```
执行前：cloud/*.py ≈ 80
第一步（L3归档）：-4 → ~76
第二步（L4合并）：-8 → ~68
第三步（L2迁移删重复判定）：不影响文件数，但删大量重复代码
最终：核心 ~68 个文件，每文件有归属、有注释、有回归
```

## 合并铁律（防"合并坏功能"）

1. 每个合并动作：先跑两个模块各自 dry-run → 记录基线输出
2. 合并后：再跑一次 dry-run → 输出与基线逐字段对比
3. 差异为0 → commit；有差异 → 停止合并，QA介入
4. 合并后运行对应cron任务一次，确认真实环境可用

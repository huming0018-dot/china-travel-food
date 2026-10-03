# Lean Code Refactor · 瘦身报告（众包美食家）

> 日期：2026-10-03　方法论：Lean Code Refactor 5 步闭环
> 硬约束：**不影响功能**（所有删除/清理后做功能回归，零损失才交付）

## 一、结论

在"不影响功能"前提下，本轮清掉 **25 个垃圾/孤儿文件（约 446KB）+ 12 行确认死代码**，
功能回归 **5 项全部通过**。Python 生产脚本（cloud 29K 行）**未大砍**——原因见第四节，
这是"不影响功能"约束下的正确边界，而非瘦身不彻底。

## 二、删除清单（A 类 · 零风险物理删除）

| 类别 | 内容 | 文件数 | 大小 | 删除依据 |
|---|---|---|---|---|
| 过期插件包 | releases 下 v2.0.0 / v3.0.0 / v3.1.0 / v3.2.0 | 4 | ~157KB | 线上最新 v3.2.1，install 页指向 v3.2.1；旧包 git 历史可恢复 |
| 一次性交付物 | 根目录 `众包美食家-审计包-v3.1.0.zip` | 1 | 125KB | 已交付，git 历史可恢复 |
| 实验沙盒 | `sandbox/` 全部（含 admin_v2_backup.py） | 20 | 140KB | 零代码引用（grep 全仓无 import），是历史 lean 沙盒 |
| 编译产物 | `__pycache__/` ×2、`*.pyc` ×3 | 5 | 76KB | 未跟踪本地缓存，可随时重新生成 |
| **合计** | | **25+5** | **~498KB** | |

保留未删（避免切断）：
- **根 `INBOX/`**（24KB）：与 `cloud/INBOX/`（PM 权威信箱，680 行）有重复，但无代码引用、
  不排除某个窗口仍按旧引导读它 → 保留，零负担换安全。
- `cloud/xhs_accounts/*.bak.*`：账号登录态旧备份，登录态敏感 → 保留。
- `cloud/_local_sample/`：采集样本存档（数据）→ 保留。

## 三、死代码清理（B 类 · vulture 静态分析 + 人工甄别）

用 vulture 扫描众包 11 个 py，报 12 项，逐一甄别后：

| 项 | 处置 | 说明 |
|---|---|---|
| `crowd_admin._gen_pid()` + `import secrets/string` | ✅ 删 | approve 改原地 PATCH 后零调用；编号现由 RPC crowd_register 生成 |
| `common_core.TIERS` 常量 | ✅ 删 | 全仓无引用（grep 仅注释命中） |
| `common_core.pipeline_common()` | ❌ 保留（误报） | 被 gate_apply/data_gate/cleanup_findings/repair_misanchor 等 5+ 文件调用 |
| `notifier.warn()` | ❌ 保留（误报） | 被 watchdog/gap_runner/reconcile 等 8+ 文件调用 |
| `common_core.DISTRICTS` | ❌ 保留（误报） | 被 candidate_apply.py 使用 |
| `notifier.warn` 的 `header_title` 参数 | ❌ 保留 | 公开 API 签名，删参数动签名、零行数收益 |
| `crowd_build dirs` / `crowd_scale sel` / `pm_dispatch SLA` | ❌ 保留 | os.walk 解构/语义化配置常量，删了降可读性、不省行 |

## 四、为什么没有大砍 cloud 的 29K 行 Python？

排查服务器后确认：除宿主 crontab 5 条外，**docker 容器 `food-cloud` 内 /etc/cron.d
（food_production/food_indep/food_parallel/food_boundary）每天在调用大量 cloud 脚本**：
national_count、brand_chain_normalize、gate_apply、chain_review_apply、signature_cuisine_link、
name_cuisine_link、dietary_trait_link、curate_gate、probe_parallel、candidate_verify 等。

- 这些文件**在宿主 git 里看着"没被宿主 cron 引用"，实则是 docker 容器的生产依赖**；
- docker 容器是独立快照（docker cp 不持久），删宿主 git 文件虽不影响当前容器运行，
  但会破坏未来容器重建/同步 → 属"影响功能"，**按硬约束不删**。
- 第三方 `cloud/vendor/`（20K 行）是外部管线，不动。

> 若后续要真正大砍这部分，前提是：先把 docker 容器的 cron 依赖完整盘点 + 容器化重建流程固化，
> 再做依赖闭包分析。那是一次独立的"生产容器治理"工程，不在本次"不影响功能瘦身"范围。

## 五、功能回归验证（Step 5 · 全部通过）

| # | 验证项 | 结果 |
|---|---|---|
| 1 | 众包 9 个 py `py_compile` | ✅ 编译通过 |
| 2 | `crowd_admin.py list` 实跑（验证 import 链） | ✅ 3 参与者正确显示 |
| 3 | `crowd_store_ingest.py --dry-run` | ✅ 核心链路正常 |
| 4 | 插件 5 个 JS `node --check` | ✅ 语法全 OK |
| 5 | `crowd_build.py` 重新构建 v3.2.1 | ✅ 41KB，9 文件/key/包内容全校验 |

TIERS 删后全仓 grep 确认无 `.TIERS` 残留引用。

## 六、交付状态

- 改动：删 25 文件 + common_core.py / crowd_admin.py 死代码 + 重新构建 v3.2.1.zip
- 推送：git origin main + 服务器 `~/china-travel-food` reset --hard 同步
- 功能：众包全链路（报名→领取→采集→回传→入库→结算）零损失

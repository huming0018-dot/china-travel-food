# Docker 生产容器治理报告

> 日期：2026-10-03 ｜ 服务器：腾讯云 49.234.35.92 ｜ 治理 commit：791f04c
> 配套文档：[CONTAINER_REBUILD_RUNBOOK.md](CONTAINER_REBUILD_RUNBOOK.md)（一键重建手册）
> 工具：[container_closure_audit.py](container_closure_audit.py)（依赖闭包审计）

## 一、治理目标

上一轮 Lean Refactor 未大砍 cloud 29K 行，因它们是 docker 容器 `food-cloud` 的生产依赖。
本轮系统治理：①盘点容器真实依赖；②固化一键重建、根治 docker cp；③闭包分析找真死肉；
④在不破坏生产前提下安全清理。

## 二、容器架构（盘点结论）

| 项 | 现状 |
|---|---|
| 生产容器 | `food-cloud`（镜像 food-cloud:local，restart:always，常驻） |
| 辅助容器 | `searxng`（搜索引擎，独立，每日 03:14 与 food-cloud 同重启） |
| 容器内 | **无 git**；代码构建时 COPY 进镜像；python `/usr/local/bin/python` |
| 数据持久化 | volume `food-cloud_fooddata` → /app/data（断点/日志，重建不丢） |
| 密钥挂载 | bind `~/food-cloud/xhs_accounts`、`xhs_cookies.json` → /secrets（ro） |
| 容器 cron | 声明式 `crontab.txt`（entrypoint 加载），32 条 py 任务，非手工编辑 |
| 权威源 | GitHub main：cloud/*.py、cloud/vendor/pipeline/*.py、Dockerfile、compose |
| 一键重建 | `bash ~/food-cloud/build_sync.sh`（pull→rsync→build→compose up） |

## 三、一键重建机制：已固化，并修复两个隐性坑

`build_sync.sh` 已能一条命令从 GitHub 完整重建。排查中发现并修复两个会让"一键重建"
悄悄失效的坑：

1. **rsync 缺 `--delete`** → 构建上下文残留手工 cp 的旧脚本，镜像与 git 不一致。
   已加 `--delete`（仅删多余 .py；deploy.env/xhs_accounts 受 exclude 保护）。
   修复后：cloud 143→**136**（清 7 个根目录残留）、pipeline 71→**70**（清冗余 warning_handler）。
2. **脚本不更新自身** → for 列表只 cp Dockerfile/crontab 等，构建上下文里的 build_sync.sh
   永远是旧版，新逻辑（--delete）不被执行。已把 `build_sync.sh` 加入同步列表（可随 git 自更新）。

另：`web_chat_providers.py`（LLM 舰队网页层，容器手工 cp、未入 git）已纳入
cloud/vendor/pipeline，重建不再丢失。

## 四、依赖闭包分析：126 静态孤儿 → 真死肉 13 个

- 从 59 个生产入口（容器 crontab + 宿主 /etc/cron.d + 宿主 crontab sh）AST 递归 import，
  得**活代码闭包 93 个**；cloud 全量 219，列出**疑似孤儿 126**。
- 静态分析会漏动态 import / 手动工具 / 未接线新功能。对 126 逐个做**全仓 grep 交叉验证**：
  59 个其实被代码引用（保留），剩余零引用的再人工分三类。

### 已删除（真死肉，13 个，3048 行）
- `vendor/_archived/` 8 个 *.retired（明确退役，含 price_band 3 个）
- `vendor/pipeline/_archive/oneoff/` 5 个一次性脚本（build_raw_900/gen_raw/migrate/rebuild/correction）
- 另删除构建中间容器 `sleepy_carson`（docker build apt 步骤遗留，OOM 停止，非服务）

### 保留：手动运维工具箱 / 备用通道（零 cron 引用但有存在价值）
- 运维按需跑：repair_misanchor、replay_anchors、cleanup_findings、recalc_scores、
  validate_schema、security_regression、gen_ts_types、apply_sql、inbox、tool_router 等
- Apify 备用通道：apify_collect/priority、events_apify（review_apify_fill 仍在 cron）
- 这些不是垃圾，删了会让运维/回退无工具。

## 五、核心发现：13 个功能模块"建了但零接线"（功能未生效）

这是比死代码更严重的问题，也是"各自为战、看似完成实则没生效"的根因。
以下模块已开发、但**没有任何 cron / 主流程 / 其他模块调用**，功能实际未运行。
**不删除，应派 dev 工单"接线"让功能真正生效**：

| 模块 | 对应工单 | 用途 | 建议接线方式（dev 接线时核对 CLI 参数） |
|---|---|---|---|
| chain_identify | #37 | 连锁识别 | 入库前置：gate_apply 前对候选店调用，写连锁标签 |
| chain_gate | #41 | 商业连锁门槛 | 与 chain_identify 串联，命中连锁走门槛/降权，cron 每小时 |
| menu_traits | #36 | 菜单特质（无麸质/清真） | 入库管线 hook：store ingest/点评富化时提取并落标签 |
| premade_takedown | #39 | 预制馆下架 | 每日低频 cron（如 03:3x），基于预制标签批量下架/标记 |
| prefill_governance | #39 配套 | 预制治理总控 | 每日 cron，编排 chain_audit/negative_audit 后触发下架 |
| softad_learn | #42 | 软广概率自学 | 每日/每周 cron，更新软广模型供 1b3_anti_softad 使用 |
| label_tool | 标签机制 | 标签统一管理 | 作为公共工具被上述模块调用（非独立 cron） |
| coverage_matrix | 覆盖率 | 覆盖率矩阵 | 每日一次 cron，输出覆盖率报告并喂 gap_pool |
| independence_probe | 独立性 | 独立性探针 | 每日 cron，结果入 findings/独立性标签 |
| findings_planner / findings_ingest | findings | 线索规划/入库 | 串接采集→gate：planner 排期、ingest 入库，每小时 |
| selling_points_fill / _dedupe | 卖点 | 卖点填充/去重 | 入库后 hook + 每日去重 cron |
| scene_ingredient_coverage | 场景食材 | 场景/食材覆盖 | 每周 cron，输出覆盖缺口喂采集 |
| national_scale | 全国规模 | 全国规模统计 | 每周 cron（上海主线之外的扩展视图） |

> 接线原则（避免再次各自为战）：统一从 `crontab.txt` 编排；公共能力（标签/连锁/预制）
> 走公共模块调用，不重复实现；接线后须在真实数据上验证产出，再纳入 release_audit。

## 六、验证结果（重建后，逐项通过）

- 容器 `food-cloud` Up、restart 计数正常；compose restart:always 生效
- py 数本地与容器严格一致：cloud **136**、pipeline **70**
- 全量 `py_compile` 通过；crontab 加载 32 条 py 任务
- /proc 确认 cron daemon 在跑；高频任务日志持续产出（11:40 hae_grid、11:43 broadcast、11:30 watchdog）
- 数据卷历史断点/日志/通道开关保留；冗余 warning_handler 已消失
- 容器环境清理：仅余 food-cloud、searxng

## 七、待用户拍板

1. **接线工单**：第五节 13 个模块是否按建议派 dev 接线（建议优先 #37/#41 连锁、
   #39 预制下架、#36 菜单特质、#42 软广自学——直接关系数据真实性）。
2. **`~/food-cloud-v2`**：非 git 早期实验沙盒（扁平 crawler/discover/scheduler/test_*），
   非构建上下文、无引用。因不可恢复，未删除；确认无用后可整体 `rm -rf`。
3. 未决技术债（沿用）：crowd_tables.sql 非幂等、requirements.lock 缺失。

## 八、交付物

- `cloud/CONTAINER_REBUILD_RUNBOOK.md` — 一键重建手册（架构/步骤/验证/密钥/排查/红线）
- `cloud/container_closure_audit.py` — 依赖闭包审计工具（可定期复跑）
- 本报告 `cloud/DOCKER_GOVERNANCE_REPORT_20261003.md`

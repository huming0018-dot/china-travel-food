# ponytail_cutlist — cloud/ 过度工程 / 死代码精简清单

只读审计（ponytail-audit，MIT）。范围：`cloud/` 与 `cloud/vendor/pipeline/`（含 `_archive` 现状）。
不审 `app/` 前端、不碰密钥、不打印凭据。本次只出清单，**不 apply、不 commit**。
判死前已全仓 Grep 引用：import、`crontab*.txt`、`entrypoint.sh`、`Dockerfile`、`build_sync.sh` / `build_on_server.sh` / `deploy.sh`、subprocess/`os.system` 脚本名字符串、HANDOFF/docs。仍被引用者不标 delete。

排序按可删行数从大到小。格式：`<tag> <要删什么>. <替代>. [路径:行]`

---

delete 删除 cloud 根的 `subcategory_noodle_coverage.py`（与 vendor/pipeline 下那份**字节级完全相同**的快照，diff 为空）。canonical 副本随 `COPY vendor/pipeline /app/pipeline` 落在 `/app/pipeline`（紧邻 common.py）；`/app/cloud` 这份是误拷的重复，无 import / 无 cron / 无 subprocess。替代：保留 `vendor/pipeline/subcategory_noodle_coverage.py`。 [cloud/subcategory_noodle_coverage.py] (445 行)

delete 删除 vendor 版 `warning_handler.py`（351 行）。watchdog:147 / account_repair:144 均 `sys.path.insert(0, HERE=/app/cloud)` 后 `import warning_handler`，解析到的是 **cloud 根那份 172 行版**（确有 `poll()`/`request_login()`）；vendor 版无人 import、无 cron、无 subprocess，是「云端 headless 二维码」旧设计前身（cloud 版 docstring 明言“不再拉云端二维码”）。替代：`cloud/warning_handler.py`。 [cloud/vendor/pipeline/warning_handler.py] (351 行)

delete 删除 `source_registry.py`（302 行）。全仓无任何 `import source_registry`；其 P5 信源注册 + 门职责已由 cron(W2) 里的 `wechat_source_registry.py` 承担。现存引用仅为 wechat_source_registry:383 的一行日志标签 `[P5 source_registry]` 与自列 connector 字符串，非可执行调用。替代：`wechat_source_registry.py`。 [cloud/source_registry.py] (302 行，中置信——apply 前再确认无手工 runbook 期待它打印注册表)

delete 删除 `cloud_review_fill.py`（261 行）。HANDOFF:1040 明确“旧 cloud_review_fill.py 已被 cloud_amap_fill.py 取代”；现存引用只剩 watchdog:29 的进程名 watchlist、build_on_server.sh 打包清单与若干 docstring，无 import / cron / subprocess。替代：`cloud_amap_fill.py`（cron 第5条）。 [cloud/cloud_review_fill.py] (261 行)

delete 删除 `web_chat_providers.py`（152 行）。全仓零 import；hae_engine.py:50 只接 `model_providers`（API 通道），`grep web_chat hae_engine.py` 为空。网页浏览器模型通道是规划了但从未接线的投机功能。替代：无（如未来启用再恢复）。 [cloud/vendor/pipeline/web_chat_providers.py] (152 行)

shrink 删 `common.py` 的 `_JP2CN` 繁简兜底尾部（约 36 行）。opencc-python-reimplemented 已是 requirements 硬依赖且在容器内可用，`_t2s.convert()` 已覆盖这一整段（注释自承“OpenCC 多会转，重复映射无害”）。**保留** 166–173 行的和制汉字/新字体块（菓→果、麺→面、沢→泽 等 OpenCC t2s 不转的部分），只删 174–209 的繁体兜底映射。替代：依赖 OpenCC，表只留和制字。 [cloud/vendor/pipeline/common.py:174-209] (约 36 行)

delete 归档/删除 `make_deploy_env.py`（31 行）。一次性 deploy.env 生成器，内写原作者 Mac 绝对路径 `/Users/hubowen/Desktop/...`，本机构建已不使用；system-map §5 已列其为“一次性 helper（候选归档）”。替代：无。 [cloud/make_deploy_env.py] (31 行)

---

## 已核对、**不要动**（防误报清单）

- `_diag_tree.py` / `_inspect_pool.py` / `_stop_pool.py`：虽无自动化调用，但被 `build_on_server.sh` 显式打包、是运维手工 `docker exec` 诊断工具，保留。
- `fact_verify.py`：仅 cloud/ 有（vendor 下并无同名文件，system-map §5 那条“同名重复”已过时）；是 HANDOFF 记录的手工 `--apply` 引擎，保留。
- `group_chef_tree.py`（cloud 399 行 vs vendor 252 行）：两份内容**不同**且均为文档化手工/skill 工具，无自动调用方；证据不足以判哪份死，本次不删（建议人工比对后保留一份）。
- `social_discovery.py`：看似被 discovery_engine 取代，实则 discovery_engine.py:474 仍调用 `D._gather_one_query(...)`，活。
- `model_providers.py`：6 provider 均配置驱动、无 key 自动跳过，是合理多源舰队，非 yagni。
- `_archive/`（29 文件 / 1.0MB）：已隔离归档，按“归档不删除、保留 git 历史”原则保持现状。

## 备注

- crontab 第9行引用 `/app/pipeline/softad_distribution.py` 但该文件在仓库中**不存在**（broken cron），属正确性问题，不在本次过度工程范围内，仅记录。
- 本次未发现可释放的第三方依赖：被删文件均不独占 requirements.txt 里的包（opencc/xhs/xhshow/playwright 仍被活代码使用）。

net: -1578 lines, -0 deps possible.
（高置信可删：445+351+261+152+31+36 = 1276 行；计入中置信的 source_registry 302 行后为 1578 行。）

# 小红书 reviews 自动认证批采退出

恢复点：`af957dfa60c22c8b0b7b95db17a808a9bf4eaf62`。只改源码，不部署、不修改历史数据、不声称线上任务已停。

- 退出 `cloud/run_batch.py` 和 `cloud/vendor/pipeline/xhs_to_reviews.py`。同步取消 router 的 reviews 分支、容器 RUN_ON_START 配置/批采和旧入口登记，不留下断裂调用。
- 保留原字节 `entity_match.py`、`atlas_write.py` 及其其他域消费者；`xhs_collect.py` 仅保留原始信息提取参考，不是已验收完整爬虫。账号健康、米其林兜底及其他 cron 不改。
- 原包装能转换正常笔记，但会将“品牌官方邀请免费试吃”直接写为已验证食客；21 字作者名先截断导致自评漏过滤；非法日期 `2026-99-99` 原样进入 visit_date。不能把候选或关键词命中当食客认证。
- 原浏览器编排在布局重试耗尽后仍返回相同点击坐标，失败打开不清场。没有当前网站实测，不把历史经验称为在线可用保证。
- 匹配/清洗函数已独立保留，不为保住这套自动包装重建反广框架。后续退出无现行生产者和仓内调用者的 `cloud/unmatched_bridge.py`：它曾可显式回放旧 `unmatched_shops.jsonl` 与 `raw_xhs.jsonl`，本次不迁移或删除历史数据；可从 `f5cdbcf23ce2945a8daf671e1a576a66ae106fb6` 查旧程序。共享 `admission_gate.py` 和现行发现链保留。
- COLLECTION_SOP、CRAWLER-MODULE-SPEC、历史审核与交接中的旧入口描述保留作历史，不能当作当前启动命令；实际入口以现行源码和本文为准。

离线验收：`python -m unittest discover -s tests -p test_xhs_auto_review_retirement.py -v`。仅验证路由不派旧批采、冷却账号下米其林时效分支保留、启动脚本不调用退出入口、独立核心原字节不变。不调用浏览器或业务网络。

进度播报保留实时计数、增量、账号状态、费用及心跳；不再将静止的 raw_xhs/评价数判成 collect_stall，也不催修旧链或虚报恢复。BATCH 仍由 production_runner 消费，保留。历史通知工单和线上配置未操作。

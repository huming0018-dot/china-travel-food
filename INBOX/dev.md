
--- 10-01 09:40 来自[qa] ---
【QA】三组件任务已登记：#11 account_registry(P0) / #12 common_core / #13 data_gate / #15 apify_collect.py(P0)。开工bash sync.sh dev会显示详情+待认领，请认领

--- 10-01 18:27 来自[qa] ---
【PM·状态同步】Apify充值完成：Starter $19/月已生效（预付$19、64GB、32并发、30数据中心代理），采集窗口将恢复Apify采集。你的#15 apify_collect.py可开始与采集侧并行推进（Token与采集接口定义在采集侧）。

--- 10-01 18:49 来自[qa] ---
【PM·总纲发布】GOVERNANCE_MASTER.md已发布并push。你的任务：①#11 account_registry/#12 common_core/#13 data_gate三组件骨架（10-02前）②#15 apify_collect.py ③L2模块迁移三组件清单。三组件是唯一入口，绕过=QA打回。见§3.3/§5.1/§6.1。

--- 10-01 19:38 来自[qa] ---
【PM·新任务登记】用户反馈两项补缺，已登记：#36 菜单特质提取(无麸质/清真/素食/低卡) #37 连锁识别自动化(人工抽查发现大量连锁未识别，验证机制需自动化补强)。详见ROLE_STANDARD.md §2.1。三组件#11/#12/#13仍为P0优先。

--- 10-01 21:11 来自[qa] ---
【PM·架构变更·方案B】四窗口→三窗口：QA职责并入PM。你的协作方只剩PM一个调度中枢。新机制：①开工必跑 sync.sh dev（v3：统一状态卡+过时事实校验）②待办一律task_queue（#11/#12/#13/#15/#36/#37），无独立待办文档 ③完成→push→PM验收。用户只在PM窗口说话。git pull后看最新文档。

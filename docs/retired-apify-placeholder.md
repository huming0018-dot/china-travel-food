# 退出占位 Apify 入口

`cloud/apify_ingest.py` 已退出活动树，恢复点 `62961712d8fa7fc7e6e96be504677e0dd2a386e5`。

实际鉴别：main 只解析参数并打印 ready；没有调用 run_search，也没有预算扣减、checkpoint fsync 或 JSONL 写出。CHECKPOINT 与成本常量是声明，不是实现。其normalize只是旧actor字段映射，未形成CLI闭环。不能把“有文件”“有token”算成采集交付。

保留的项目实现是 `cloud/apify_collect.py`：已有 start_run→wait_for_run→get_dataset→normalize→data_gate→JSONL 的代码路径；此轮不运行、不修改它，也不保证外部actor当前可用、费用正确或线上采集通过。

同步去掉SOP旧入口，release.sh改查真实入口文件，并明确只检查文件存在。其数据输出目录中 `apify_ingest` 是历史目录名，不是对退出脚本的依赖，本次不改路径或数据。其余历史设计文档保留当时记录，以本说明为当前去向。

经验：验收必须追踪入口是否真正调用执行链，注释承诺、常量和占位输出不能替代执行逻辑。没有新适配层，没有生产、数据库或部署动作。

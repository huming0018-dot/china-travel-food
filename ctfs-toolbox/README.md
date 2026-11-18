# CTFS 拆分后的项目配置与待筛选来源

此目录已不是可安装/可运行的 CTFS 包。旧 pyproject、CLI、包入口及重复通用核心已退出；不要运行遗留测试、执行旧安装命令或声称旧流水线仍可用。

## 已迁入工具类

- [证据版本仓](https://github.com/huming0018-dot/agent-data-toolbox/tree/13f2dd650bfa06456dc96754edae2bcbf41297eb/packages/evidence-store)：原始字节、幂等派生版本和精确父链。
- [证据处理链](https://github.com/huming0018-dot/agent-data-toolbox/tree/13f2dd650bfa06456dc96754edae2bcbf41297eb/packages/evidence-pipeline)：清洗、四算子评分、重演审计及必要配置合同。

使用新包自身 README 和测试。此处不提供旧接口兼容层、不自动迁移旧数据库/审计收据，也未改变生产。

## 保留的配置和待筛选来源

- packs/ 下24份领域配置原字节保留：cuisines 与 software-releases，各0.3.2/0.3.3。它们是领域样本，不打包进通用工具；软件发布样本并非美食业务，后续另行归位。
- toolbox/ 剩余8个模块仅作为**待逐项筛选来源**：connector.py、connector_http.py、connector_snapshot.py、crawler.py、jobs.py、consumer.py、postgres.py、storage_factory.py。分别包含连接器合同、网络/文件读取边界、事务采集记录、持久恢复、交付门、PG适配及存储选择，尚未迁入或验收为独立工具。
- tests/ 剩余12份历史测试保留反例，不是当前可执行套件；其旧 toolbox 导入已无完整依赖。M7-PG-READONLY-0.5.1.md 是历史验证经验，不是当前能力保证。

本轮不为残余模块补兼容层，也不把它们当无价值代码删除。不能据此宣称所有剩余资产已筛选完成。

## 删除与恢复

固定完整恢复点：`b870dab6d4b62a50329dae7fadcc1d60cd613fb5`（china-travel-food）。
42文件退出：12个已迁核心Python副本、旧__init__/CLI/pyproject三个入口、24份schema、两份旧runtime映射及已迁test_storage.py。保留的其他文件不改字节。
24份schema中，11份现行合同随两个工具包保留；其余13份只保留Git历史，不是待迁实现：
- schemas/archive-0.1.0/audit.schema.json
- schemas/archive-0.1.0/clean.schema.json
- schemas/archive-0.1.0/manifest.schema.json
- schemas/archive-0.1.0/raw.schema.json
- schemas/archive-0.1.0/scored.schema.json
- schemas/archive-bba6ad2-0.1.0/audit.schema.json
- schemas/archive-bba6ad2-0.1.0/clean.schema.json
- schemas/archive-bba6ad2-0.1.0/manifest.schema.json
- schemas/archive-bba6ad2-0.1.0/raw.schema.json
- schemas/archive-bba6ad2-0.1.0/scored.schema.json
- schemas/archive-bba6ad2-0.1.0/view-previously-mislabelled.schema.json
- schemas/archive-bba6ad2-0.1.0/view.schema.json
- schemas/schema-history.json

恢复单个历史文件可用 `git show b870dab6d4b62a50329dae7fadcc1d60cd613fb5:ctfs-toolbox/相对路径`。不要将恢复历史当生产部署。删除仅涉及仓库活动树。

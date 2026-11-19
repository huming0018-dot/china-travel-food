# 文本工具边界

这是美食项目内部解耦，不是独立工具仓交付。

`vendor/pipeline/text_normalization.py` 是 norm_name/cjk_unify/cjk_norm/addr_core 的唯一实现，无数据库、凭据文件、餐厅枚举依赖。原 common 保留兼容导出；map_helpers 直接调用文本工具，不再为文本匹配导入 common。既有 OpenCC 可选行为、日文映射与标点/中文地址匹配规则保持，不能当成通用语言规范。

复现：`cd cloud && python -m unittest -v test_text_normalization`。3项离线测试涵盖真实地图匹配消费者、无common导入、原有文本合同与可选转换顺序。提取的4个函数AST与原版一致。未请求地图服务、未读写数据库、未运行采集。

部署布局不变：既有 Docker COPY vendor/pipeline 与 build_sync 的 pipeline/*.py 包含新增文件，无新包/私有依赖。未构建镜像或部署；不宣称地图API、生产或四类跨仓整理通过。上海范围、地标权重、地图账户/配额仍属原项目，未搬入纯文本工具。

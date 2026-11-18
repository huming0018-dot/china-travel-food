# 项目出餐裁决核心

固定基线 361f76723a0ef10cfdbcff85e8250ddb6e03478d，原 production_model_probe.py blob e11ea2dff73a4ac15feeb4054cbe2ffa71f29e29。

保留为项目，不迁工具：production_policy.py 完整接收已给定 signals，输出 production_model/central_kitchen/premade_risk/sources/rationale；仅标准库 re，无数据库、模型、搜索、文件操作。业务规则仍属于美食。原 probe 显式导入并保留原同名接口，runner/parallel 调用路径不变。原七个定义 AST 不变，非新算法。

不是完整证据链：来源真实性、引文是否支持结论、同源转载、许可字段的证据绑定由上游负责，模块没有验证。原 n_ind=max(不同域名数,不同证据类数) 是旧契约，不等于真正独立来源；本次不加严、不修规则。固定结论正确不表示线上餐厅事实正确。

已审覆盖：原769–1314行证据约束/严重复核/先验/确定性扫描/裁决/写findings；并查602–672 probe_brand与1326–1414 run、production_runner实际调用。只提取裁决依赖闭包（164行），不称1414行全模块完整验收。前半HTTP重试、模型池、取证缓存及agent循环未完成深审。

历史06f5fdf引入确定性扫描/矛盾复核；1675ea91引入低置信知识先验且probe_parallel仍调用，均保留。没有凭无直接run调用删除有效消费者。

最小验证：在cloud运行 python -m unittest -v test_production_policy；单独 python -I -S 仍可导入production_policy并裁决。真实probe整模块导入仅将外部I/O依赖替换为空模块，随后真实adjudicate→write_findings验证字段与数量。没有取证、模型请求、库写入。Docker COPY *.py 与 build_sync cloud/*.py 覆盖新文件，未构建/部署。候选须非作者独审。

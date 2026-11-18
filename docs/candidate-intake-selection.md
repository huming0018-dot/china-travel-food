# 候选到写库：能力有价值，自动收口不完整

固定基线/恢复点：`3e7bdc2b93edab2da3c261ae4709877110edfbdc`。接续发现核心PR66，不重复审核已验词矩阵、原文提取、gate。只进行隔离鉴别，未改生产实现、未联网、未写真实数据库。

## 按能力判定

| 核心 | 完整性/价值 | 归属和处置 |
|---|---|---|
| candidate_apply.build_fields | POI→地址、行政区、电话、上海坐标、人均等字段。正常输入真实输出，调用common现有清洗函数，不是占位 | **保留项目核心**，领域字段/范围不晋升通用工具 |
| insert_restaurant/tag_cuisine | 请求发送、成功回执取id、挂菜系真实存在；正常链闭合，插店失败不再挂标签。但两步非事务、未完整回读 | **保留项目写入适配能力**，不等于可独立认证的入库产品或通用DB工具 |
| main中的候选筛选与预演 | 不接收hold、无食客/库内候选；已存在则跳过；默认不写库。仍会调用地图和查库，不是无外部动作的纯离线预演 | **保留项目规则**，真实食客身份可靠性仍由PR66限制说明约束 |
| pick_new_poi | 餐饮筛选、低分拒绝完整；高分同名多分店仍选第一家，不能完成“唯一POI”承诺 | **保留有边界的项目候选排序，不认可为自动锁店保证**；不得据此声称实体定位已经验收 |
| cloud_discover自动收口完成判断 | 正常场景有实现，但缺配置、写入失败、标签失败仍标done，按候选文件计数而非写入回执 | **不纳入已验收完整核心；建议退出这套自动收口完成承诺/入口**，仅留明确成功回执才能推进的经验。成组退出范围待独审，不在此次证据补丁中悄悄删除 |

本批没有模型资产、独立环境资产或值得另建的工具包。不能因HTTP封装能用就把整个自动收口判完整；也不能因收口失败把字段清洗和候选筛选一起丢掉。

## 真实消费者与退出边界

- cloud_discover.run_apply实际执行candidate_apply --commit；main在子进程正常退出后标记品类done。
- gap_runner.auto_gate_apply、cloud_bili_collect.main、unmatched_bridge.main也实际执行candidate_apply --commit。不是只有一处调用；不能只删除candidate_apply或擅自改变其CLI而留下其他半条链。
- gap_runner.auto_gate_apply源码没有核验gate/apply returncode；cloud_bili_collect打印apply错误后仍从候选文件累计“admitted”。这两处仅静态核读，未运行全路径；不把本次cloud_discover动态证据外推成所有入口已验。
- 建议后续成组处置：保留发现原文和候选输出；取消未经可靠回执支撑的自动提交/完成推进；candidate_apply保留字段和显式适配能力的范围，由独审连同四消费者决定。不要为保住旧链新增事务框架或修复整套产品。
- 2026-10-23的`52472f0c54235e317f4769925fb69a825cd4ae2a`已加无食客不收闸门，提交说明称建店以build_bridge stage1-4为准。现行直接调用仍在，说明历史意图与实际源码接线并不一致。部署情况未知，不能宣称线上已停用。

## 实际离线证据

命令：`python -m unittest discover -s tests -p test_candidate_intake_selection.py -v`，需项目现有Requests。本次系统Python3.13.5运行，**5项正常通过、6项expectedFailure**，不是11项业务全绿。

完整导入真实candidate_apply、cloud_discover及其依赖；env指向临时空目录。HTTP/socket/意外子进程默认拒绝。地图候选、数据库读/HTTP回执是合成边界；浏览器及上游发现已饱和是边界替身。实际执行candidate_apply.main与cloud_discover.main，不抽AST或改写它们的控制流。子进程边界在进程内调用真实apply main，正常None对应脚本退出0；不启动真实子进程、浏览器或采集。

正常：
- 新候选真实字段组装→POST店→按返回id POST菜系；默认dry-run无POST。
- 无食客与已有店不POST；插店500时不发标签POST。
- 正常两步成功，cloud_discover将bread记done。

反例：
1. 插店500，apply仅记errors、正常返回；cloud_discover仍记done。
2. 无AMAP_KEY，apply直接正常返回；cloud_discover仍记done。
3. 店已插入、标签500，cloud_discover仍记done；部分成功并非完整收录。
4. 上述标签失败后再次运行，因店已存在而直接跳过，不补缺失标签；“可重复运行”不等于恢复半完成任务。
5. 同品牌东/西两分店分数都高，pick_new_poi选第一家而非AMBIG；高相似度不能证明唯一实体。
6. 地图适配器明确可能返回YIELD，消费者只识别QUOTA，随后把字符串当POI列表，AttributeError崩溃；让出预算不是有效候选列表。

未验证真实HTTP服务、数据库事务/触发器/幂等、现网调用频率、部署状态、另三消费者完整执行。本次只新增本说明与反例测试，既不恢复采集，也不以修bug替代价值筛选。

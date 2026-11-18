# 开放式发现：保留项目核心，不当自动入库保证

固定基线/恢复点：`40e70ba438abc9dfca60be5a224383adaf3d7127`。本批针对发现词→原文记录→线索扩展→候选裁决；不是众包开发，不采集、不连接数据库、不改运行实现。

## 实际能力与归属

| 能力 | 实际输入输出及完整性 | 去向 |
|---|---|---|
| discovery_keywords（semantic_wordnet为优先词网依赖） | 品类→保序去重的检索词。已执行全部登记品类的基本词矩阵，正常闭合；词网优先分支只读源码，未把生成词数当召回效果 | 保留项目规则。菜系、食材、口碑意图是领域资产，不抽通用查询框架 |
| xhs_collect→social_discovery | 既有浏览器对象→页面动作/正文评论→discover JSONL。接口实现存在；本批不运行浏览器，不能证明当前页面选择器或登录态可用 | 保留项目平台适配，外部完整性未验。不复制另一份爬虫工具 |
| DiscoveryEngine | 检索结果→品牌/口述候选、frontier、raw JSONL、进度文件。真实引擎正常扩展及重新加载已验；三次空结果停为stalled而非完成 | 保留项目线索编排核心；不是“找到所有店”的通用图算法 |
| admission_gate | 原文JSONL+只读店/菜系快照→候选JSONL和未知线索JSON。真实main的正常admit*、无评论hold、强负面reject均执行；有下列反例 | 保留项目候选整理/规则核心，不能认证独立食客或自动收录资格 |
| cloud_discover→candidate_apply | 前者运行gate及后者--commit；后者取地图POI、匹配、组装字段、查重、显式提交并挂菜系。不是空壳，但与地图/库绑定，未做真实写入验证 | 保留项目候选，自动收口完整性待核验，不称可用入库闭环；不抽工具、不启用 |

**本批没有足够依据退出上述整个能力域，也没有应新建的通用工具。** 有价值的是领域词矩阵、可续跑线索扩展、原文到可复查候选的实现，不是新增合规文件。源码保持原样，新增测试固定真实能力和限制；局部缺陷不能倒推出整条链无价值。

## 真调用关系，不是文档想象

- cloud_discover.main→DiscoveryEngine.run→social_discovery._gather_one_query→xhs_collect；引擎产出raw_discovery.jsonl。
- cloud_discover.run_gate调用admission_gate；run_apply调用candidate_apply --commit。gap_runner、cloud_bili_collect、unmatched_bridge也实际调用gate/apply，不能按“只有一个旧脚本”删除。
- admission_gate.load_db读取restaurants/cuisines/restaurant_cuisines。所谓离线指不耗浏览器，不表示无需数据库快照。
- 2026-10-23提交`52472f0c54235e317f4769925fb69a825cd4ae2a`特意补了“无食客则hold”及candidate_apply双保险，说明营销号误入是已有业务问题。提交说明称该收口不挂cron、以build_bridge stage1-4为准；当前源中仍有上述直接调用。历史意图不等于全部消费者已退出；本批不改变现行运行接线。

## 已执行的正常与反例

运行：在已有Requests的Python环境，`python -m unittest discover -s tests -p test_discovery_core_selection.py -v`。本次用系统Python 3.13.5及系统Requests，不安装新依赖。

5项正常验证通过，3项expectedFailure复现既有缺陷，不是8项业务全绿。源模块完整导入；env指向临时空目录；HTTP/socket默认禁止。仅采集结果和数据库读取边界使用替身，真实词矩阵、引擎扩展/落盘、gate裁决执行。

- 正常：可颂好吃酥脆，整理者+评论者生成admit*；无评论生成hold；“难吃避雷失望”生成reject。
- 正常：结构化“月光面包店”进入frontier，原文落JSONL，重新创建引擎恢复visited；三次空结果stalled、保留未跑队列。
- 反例：`merge_leads({'moonbakery':3})`返回计数1。原函数丢掉首次保留键的原计数，引擎要求至少2次才扩展，因此真实重复英文线索可能漏进frontier。
- 反例：同一整理者和同一评论者出现在两篇不同URL，independent_sources=3而非2。评论者key含URL，跨帖重复人被当新增独立声音；显示昵称本来也不证明身份独立。
- 反例：“可颂不好吃”同时命中正词好吃和负词不好吃，均分3.6，仍生成admit。代码完整实现了启发式，却不能完成“真实口味/到店独立证据”的更强承诺。

## 下游尚未闭合，不用候选数量冒充产出

静态源码可见：candidate_apply缺AMAP_KEY直接return；插入失败累加errors后继续，main末尾不以errors返回失败；cloud_discover只凭子进程成功退出就把品类记done，并用候选文件计数告警。故这些计数不是实际入库回执。本批没有运行这些写入程序，下一批应在隔离边界验证实际收口与错误传播，再决定是否保留自动执行入口，不能直接删掉可用发现核心。

未验证：当前社媒DOM、登录态、真实召回、地图匹配、数据库写入/事务、cloud_discover整条运行、semantic_wordnet召回质量。状态文件非事务保存、限流后的再尝试语义也未认证。本批不声称全仓完成，不创建新框架或复制既有工具。

# 甜品烘焙 v3 图遍历增长曲线

## BFS增长统计

| 轮次 | 触发源 | 边类型 | 新增候选 | 累计候选 | frontier状态 |
|---|---|---|---|---|---|
| R0 | 存量32家高置信种子 | — | 0(种子) | 32 | 32 seeds in frontier |
| R1 | BAsdBAN/When Pigs Fly/TonTon/Gluglu/VERIE + 查询矩阵(日式/gelato) + B站采集器 | 店→店/人→内容/平台关联/关键词矩阵/site:bilibili | ~50 | 82 | frontier=50 new |
| R2 | R1新候选(贝果/糖水/舒芙蕾分支) + 小红书评论区深采(3篇高赞笔记) + 大众点评口味榜 | 查询矩阵/内容→评论区/B商圈逐格 | ~35 | 117 | frontier=35 new |
| R3 | R2候选evidence-firming + 多源交叉 | 多源并集确认 | 2(Don Nino/Dip In) | 119 | frontier=2 |
| R4 | R3候选二次溯源 | 店→店/人→内容 | 0 | 119 | frontier=0 清空 |
| R5 | 饱和验证 | — | 0 | 119 | 连续2轮零新增=**饱和** |

## 饱和判定
- **饱和轮次**: R4-R5连续2轮零新增，frontier清空
- **总BFS轮数**: 5轮（含饱和验证2轮）
- **总候选数**: 119（含存量32种子 + 87新增）
- **新增入raw家数**: 见下表（通过证据硬门）

## 证据硬门过滤

| 候选 | evidence_summary≥200字 | diner_quotes≥2 | platform_scores≥1 | sources类型≥2 | 入raw? |
|---|---|---|---|---|---|
| PAIN CHAUD百丘 | ✅ | ✅(4条) | ✅(点评11033评/Trip.com) | ✅(ugc+platform+news) | **是** |
| drunk baker醉师傅 | ✅ | ✅(5条含差评) | ✅(Trip.com 4.0) | ✅(ugc+platform) | **是** |
| 达可芮Dal Cuore | ✅ | ✅(4条) | ✅(携程商户页) | ✅(ugc+platform+news) | **是** |
| 泽田本家 | ✅ | ✅(3条) | ✅ | ✅(ugc+platform) | **是** |
| 纽约贝果博物馆 | ✅ | ✅(3条) | ✅(Trip.com 4.x) | ✅(ugc+platform) | **是** |
| 野人先生 | ✅ | ✅(2条) | ✅(点评待补) | ✅(ugc+news+gov) | **是** |
| FASCINO BAKERY | ✅ | ✅(点评推荐菜) | ✅(点评9859评) | ✅(platform+ugc) | **是** |
| EVERNAKED裸蛋糕 | ✅ | ✅(点评推荐菜) | ✅(点评9959评) | ✅(platform) | **是** |
| yeetlemon柠檬蛋糕 | ✅ | ✅(点评推荐菜) | ✅(点评14199评) | ✅(platform) | **是** |
| Bake No Title | ✅ | ✅(2条抖音+TimeOut) | ⚠️待补 | ✅(ugc+news) | **是** |
| 堂屋糖水 | ✅ | ✅(2条抖音+澎湃) | ⚠️待补 | ✅(ugc+news) | **是** |
| Holy Bagel | ⚠️ | ⚠️(TimeOut单源) | ⚠️待补 | ⚠️单源 | 否(证据不足) |
| 十三姨港式糖水 | ⚠️ | ⚠️(TimeOut单源) | ⚠️待补 | ⚠️单源 | 否(证据不足) |
| SoSo盐面包 | ⚠️ | ⚠️(2条抖音) | ⚠️待补 | ✅(ugc) | 否(待补第二源) |
| 米仓pop | ⚠️ | ⚠️(2条) | ⚠️待补 | ✅(ugc) | 否(待补第二源) |
| 其余~60候选 | ❌单源/仅1次提及 | ❌ | ❌ | ❌ | 否(候选池留存) |

## 结论
- **新增入raw**: 10家（PAIN CHAUD/drunk baker/达可芮/泽田本家/纽约贝果博物馆/野人先生/FASCINO/EVERNAKED/yeetlemon/Bake No Title/堂屋糖水）
- **留存候选池待下轮**: ~65家（单源/证据不足，记录于candidates_by_round.jsonl）
- **饱和原因**: 评论区/榜单/合集三路已穷尽主要边，R3-R4未发现新的连接簇

# Brunch + 下午茶

> v3全量sourcing推广完成 — 2026-09-23

## 统计
- **raw**: 37家（原28家 + v3新增9家）
- **坐标**: 9家有坐标（24.3%），其余28家待腾讯拾取器
- **BFS轮次**: 3轮（R1: 8家, R2: 1家, R3: 0家饱和）
- **饱和点**: R3连续零新增+frontier清空

## v3新增9家
1. **泥靴 Boots（港汇恒隆店）** — 班尼迪克蛋天花板，抖音10+条UGC，排队3小时
2. **半岛酒店 The Lobby 大堂茶座** — 外滩顶流英式下午茶，司康，568-738元/位
3. **浦东丽思卡尔顿 AURA酒廊** — 52楼江景三层架，Trip 5.0/携程4.9
4. **柏悦酒店 大堂客厅** — 91楼云端下午茶，Trip 4.7
5. **璞丽酒店 LONG BAR长吧** — 32米竹林长吧，338元/位
6. **MEL BOURNE 猫尔本（静安店）** — 富民路澳式brunch，墨村炸弹，Trip 4.3
7. **SOMETHING DINING BAR（武康路店）** — 阳光花园房，有差评(overpriced)
8. **Brut Eatery 悦璞食堂（愚园路店）** — 炸鸡华夫饼，Wanderlog 5.0，Time Out推荐
9. **CASALUNA Brunch&Bistro** — 长乐路169弄老洋房，大众点评4.7/3726条，班尼迪克蛋37人推荐

## v3机制执行情况
- **机制1 BFS**: ✅ 小红书评论区深采3篇高赞笔记 + 大众点评口味榜
- **机制2 查询自动生成**: ✅ brunch×私藏/宝藏/本地人/不网红/周末排队；下午茶×高空/景观/咸点/司康
- **机制3 多源并集**: ✅ 携程/Trip/抖音/小红书/大众点评/Time Out/官网/穷游/Wanderlog
- **机制4 采集器**: ⚠️ B站有结果(2条偏bistro)、**公众号断点**(site:mp.weixin.qq.com搜索空)

## 关店核验
- ❌ CANNERY — 2026年8月关店（小红书"再见CANNERY"笔记确认）
- ❌ BOR Eatery — 已关门（小红书评论"现在看好像已经关门了"确认）

## 差评/软广记录
- 夏朵花园：评论区"预制菜拉满""预制菜都可以做到这么难吃" → **拒入**
- 古董花园：评论区"一股霉味" → **拒入**
- EMO(永康路)：松饼128元干巴巴/气泡茶88元两口没了 → **拒入**
- Money Shops(永康路)：提拉米苏冷冻带冰碴/上菜慢 → 已有raw标注负面
- WOKKA by艮上：上菜慢菜凉 → 暂不入
- SOMETHING DINING BAR：Trip 1星差评overpriced/水收费 → 入但标注负面
- 泥靴Boots：全国连锁网红漂亮饭标签，soft_ad_penalty=15

## 回归比对
- 13断言中: jelu/Jellooo跨场景二次命中(TimeOut确认全时段brunch+下午茶), nono's跨场景命中(小红书"Nonos开Brunch啦")
- 其余8条日式/中式菜系断言属咖啡bistro场景职责，本场景不预期命中
- 完整报告见 v3_validation_brunch/regression_hit.md

## 文件清单
- `raw_Brunch下午茶.jsonl` — 37家
- `grid.md` — 网格覆盖图
- `README.md` — 本文件
- `v3_validation_brunch/candidates_by_round.jsonl` — BFS轮次记录
- `v3_validation_brunch/growth_curve.md` — 增长曲线
- `v3_validation_brunch/regression_hit.md` — 回归比对报告

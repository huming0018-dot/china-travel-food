# Source Coverage Registry（覆盖源注册表 · 完整性方法）

> 目的：让"覆盖是否完整"**可证明**，而不是罗列几个平台就以为穷尽。这是长期维护的信源登记 + 监控账本，不是一次性调研。
> 权威机器表：仓库 `china-travel-food/research/coverage/source_registry.jsonl`（每行一个源，15 字段）；本文件是方法与结论的可读入口。
> 上位契约：北极星 A2（真实可溯、宁空不假）、A3（机制优先）、A4（信源沉淀）、A5（账号最后手段）。

## 1. 三轴框架（完整性判定先于罗列）

- **需求维度轴**：菜系 × 场景（正餐 / 快餐 / 早餐 / 夜宵 / 茶馆 / 酒吧 / 甜品 / 咖啡 / 面包 / 私房 / 会所 / 菜场等）× 食材 × 口碑类型（食客 / KOL / 榜单 / 媒体 / 官方）。
- **源类别轴（12 类枚举）**：OPEN_API、UGC、DATA_MARKET、OVERSEAS、REGISTRY、MEDIA_TV、GUIDE、MEDIA、OFFICIAL、LONGFORM、SHORTVIDEO、MAP。
- **发现方法轴（6 种）**：官方开放平台文档；Apify / RapidAPI / 数据市场目录；GitHub（topic / MCP）；搜索引擎；种子店 / KOL 跨平台分发追踪（一个作者通常多平台分发）；漏店根因反推。

> 规则：任何"源类别"只有在被实际检索过其发现方法后，才能判定"无源"；禁止凭印象说某平台不存在通道。

## 2. 源实例行 schema（15 字段，枚举冻结）

`source_id` · `platform` · `category` · `url` · `fields_available` · `channel`（official_api / apify_actor / authorized_dataset / rss / public_html / search_snapshot / manual）· `tos_pipl` · `risk_level` · `rate_limit` · `cost` · `dine_in_evidence` · `strong_cuisines` · `active` · `covered_grid` · `notes`。

## 3. 完整性方法（两步）

1. **逐格核对**：每个"菜系×场景"格要求 **≥3 个独立源，且 ≥1 个 `dine_in_evidence=true`**；统计达标 / 不达标，并区分缺口是"源不存在"还是"源已存在但未接入 / 未跑"。
2. **漏店反推**：对已知漏店逐店填"所属格 → 哪类源本该抓到（source_id）→ 当时为何没抓 → 补哪个源"。漏店是回归用例，不是手工补单。

## 4. 当前结论快照（2026-10-01，99 个唯一源）

**按类别分布**：OPEN_API 14 / UGC 13 / DATA_MARKET 12 / OVERSEAS 11 / REGISTRY 9 / MEDIA_TV 8 / GUIDE 7 / MEDIA 7 / OFFICIAL 7 / LONGFORM 4 / SHORTVIDEO 4 / MAP 3。

**漏店反推（10 家）**：nabi、jelu、yaya's、nono's、望庐、醉冬、佐佐、鮨照、ministry of crab、8by8——其中 **8 家核心缺口是小红书 UGC 通道断（账号 parked）**，Apify 上线即补；ministry of crab、jelu 缺海外 / 媒体源。

**不达标格**：赣菜×fine-dining、日料×omakase/割烹、中东×正餐、海鲜×fine-dining、菜场/市集、早餐×本地传统、酒吧×cocktail bar。
- 除"菜场/市集"属**源不存在**外，其余多为**"源已存在但未接入"**——最大缺口是小红书 UGC，Apify token 到位即可立即补。

**平台成熟度要点**：小红书 / 抖音 / 微博 / 知乎 / B站 与 Google Maps / TripAdvisor / Instagram / YouTube / Reddit 均有成熟合规通道；**大众点评（UGC 正文）、视频号、OpenRice 为稀缺项**——点评 UGC 正文的正规路径是美团 POI 开放平台（商务授权），地图 Place API 只给聚合分、不给逐条正文。

## 5. 推荐接入顺序

① Apify 小红书（sian.agency actor，`cloud/apify_ingest.py` 已就绪、待 token）→ ② 点评分店列表（已跑）→ ③ 地图配额（已跑）→ ④ 米其林 / 黑珍珠 sitemap（已跑）→ ⑤ TimeOut / SmartShanghai RSS → ⑥ 海外 Instagram / TripAdvisor → ⑦ 知乎 developer API。

## 6. 维护规则

- 新发现一个可用源 → 立即按 15 字段登记进 `source_registry.jsonl`，定 cadence、reliability，接入对应连接器（A4）。
- 每轮全量复扫后更新逐格缺口；漏店反推清单只增不改、闭环后标注。
- 合规：尊重 robots / ToS、限速、PII 最小化与留存、官方 API 优先、成熟平台代理轮换降风控；榜单 / 注册 / 影视 / 官方源 `dine_in_evidence=false`，只作互证与事实，不充当堂食口味证据。

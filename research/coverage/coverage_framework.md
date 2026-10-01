# Source Coverage Registry · 覆盖完整性框架（冻结）

> 本文件是后续 3 个填充 agent 的硬约束：每个源实例按下方 schema 一行落 JSONL，禁止自创字段。
> 上位契约：north-star 宪法 A2（真实可溯）、A4（信源资产化）、P5 信源注册表。

## 1. 三轴框架

### 1.1 需求维度轴（我们要找什么）
- **菜系**：本帮/江浙/川/粤/湘/闽/徽/西北/东北/云南/贵州/新疆/西藏/清真/日料/韩餐/东南亚/印度/意/法/西/中东/拉美/融合/素食/咖啡/面包/甜品/酒吧/茶/早餐/夜宵/菜场/私房/会所/快餐小吃
- **场景**：正餐 fine-dining / 休闲 bistro / 快餐 / 早餐 / 夜宵 / 茶馆 / 酒吧 / 甜品 / 咖啡 / 面包 / 私房 / 会所 / 菜场/市集
- **食材垂直**：和牛/海鲜/蟹/菌菇/面食/烧鸟/火锅/烧烤
- **口碑类型**：真实食客 UGC / KOL / 专业榜单 / 媒体 / 官方品牌

### 1.2 源类别轴（从哪找）
| code | 类别 |
|---|---|
| UGC | UGC 社区（小红书/微博/抖音/知乎/B站/大众点评） |
| MAP | 地图/点评（高德/腾讯/百度） |
| SHORTVIDEO | 短视频/直播（抖音/B站/视频号/快手） |
| LONGFORM | 长图文/博客（公众号/知乎专栏/Medium/Substack） |
| GUIDE | 专业榜单/指南（米其林/黑珍珠/Asia's 50Best/携程美食林） |
| OFFICIAL | 官方/品牌（官网/公众号/新闻稿） |
| REGISTRY | 企业与监管注册（企查查/天眼查/市监/食安） |
| MEDIA | 行业媒体（TimeOut/SmartShanghai/美食美酒） |
| MEDIA_TV | 影视综/纪录片/书籍（一饭封神/黑白厨房/舌尖） |
| OVERSEAS | 海外/外语社区（Google Maps/TripAdvisor/Instagram） |
| DATA_MARKET | 数据市场/采集平台（Apify/RapidAPI/SocialDataX） |
| OPEN_API | 官方开放 API（developer.zhihu.com/open.bilibili.com 等） |

### 1.3 发现方法轴（怎么找到这些源）
- 官方开放平台文档
- Apify/RapidAPI/数据市场目录
- GitHub topic / MCP server 目录
- 搜索引擎 site: 检索
- 种子店/KOL 跨平台分发追踪
- 漏店根因反推（见 §4）

## 2. 冻结行 Schema（每源实例一行）

JSON Schema（落 `/app/data/coverage/sources.jsonl`，每行一个对象）：

```json
{
  "source_id": "string, 稳定 slug，如 xhs_apify_sian",
  "platform": "string, 如 小红书/大众点评/高德/抖音",
  "category": "enum[UGC, MAP, SHORTVIDEO, LONGFORM, GUIDE, OFFICIAL, REGISTRY, MEDIA, MEDIA_TV, OVERSEAS, DATA_MARKET, OPEN_API]",
  "url": "string, 可访问入口 URL",
  "fields_available": ["string, 可取字段名，如 post_id, content, likes, author"],
  "channel": "enum[official_api, apify_actor, authorized_dataset, rss, public_html, search_snapshot, manual]",
  "tos_pipl": "enum[low, medium, high], 合规姿态（low=官方授权/robots友好；high=需限速/PII最小化/版权注意）",
  "risk_level": "enum[low, medium, high], 风控等级",
  "rate_limit": "string, 如 <=2/min, 1000/day",
  "cost": "string, 如 free, $0.02/post, $5/1k",
  "dine_in_evidence": "boolean, 是否能产出真实堂食口味证据",
  "strong_cuisines": ["string, 该源擅长的菜系/场景"],
  "active": "boolean, 2026-10 是否在用",
  "covered_grid": ["string, 覆盖的 菜系×场景 格 key"],
  "notes": "string, 自由备注"
}
```

**枚举冻结**（后续 agent 不得新增，需新增提审）：
- category: UGC / MAP / SHORTVIDEO / LONGFORM / GUIDE / OFFICIAL / REGISTRY / MEDIA / MEDIA_TV / OVERSEAS / DATA_MARKET / OPEN_API
- channel: official_api / apify_actor / authorized_dataset / rss / public_html / search_snapshot / manual
- tos_pipl: low / medium / high
- risk_level: low / medium / high

## 3. 完整性方法

- **每格要求**：每个「菜系 × 场景」格至少 **N=3 个独立源**（独立源=不同平台/不同 channel 类型）；其中至少 1 个能产出真实堂食口味证据（dine_in_evidence=true）。
- **缺口计算**：covered_grid 反推每格源数；<3 即缺口；dine_in_evidence=false 的格标「口味证据缺」。
- **证明方式**：`cloud/coverage_audit.py`（待写）输出每格源数/类型分布、缺口清单。

## 4. 漏店反推模板（判定哪类源本该抓到）

已知漏店：nabi、jelu、yaya's、nono's、望庐、醉冬、佐佐、鮨照、ministry of crab、8by8。

每店反推填空：
- 该店菜系×场景 = ?
- 本该由哪类源抓到（UGC? GUIDE? OFFICIAL? MEDIA_TV?）
- 为何没抓到（该源未注册 / 已注册但未跑 / 跑了但限速 / 字段不匹配 / name→rid 闸门拒）
- 结论：补哪个源实例 + 优先级

模板示例（望庐·精细江西菜）：
- 格：赣菜×正餐 fine-dining
- 应抓源：GUIDE（黑珍珠已 hold）+ UGC（小红书）+ MEDIA（TimeOut）
- 未抓到原因：UGC 侧小红书关键词「望庐 江西 上海」未跑（XHS 账号 parked）
- 结论：Apify XHS 通道上线后优先补该店。

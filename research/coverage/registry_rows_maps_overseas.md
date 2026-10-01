# Source Coverage Registry · 点评/地图 + 海外/外语美食社区 源实例

> 调研日期：2026-10-01（Asia/Shanghai）｜仅调研，未接入/未购买/未写库。
> 配套机器可读文件：`registry_rows_maps_overseas.jsonl`（严格 15 字段 schema，21 行已校验）。
> 框架：`coverage_framework.md`（冻结）。本批不重复 market_directory 已编目的 actor。

---

## 1. 通道一句话矩阵（点评/地图侧）

| 源 | 合法通道（一句话） | 可取什么 | 能否出逐条堂食声音 | 风控/合规 |
|---|---|---|---|---|
| **大众点评 POI 开放平台** `poiopen.dianping.com` | B2B 签约数据合作（authorized_dataset），非自助 | poi 元数据 + reviewCount + ugcs 逐条（昵称/星级/正文/图片/是否优质） | ✅ 真堂食 | low（自带授权链路） |
| **大众点评公开网页** `dianping.com/shanghai/ch10` | public_html 仅小样本人工/搜索快照 | shop 页聚合分 + 评论正文 + 作者等级 | ✅ 真堂食 | **high**（大众点评诉百度案判赔 323 万，robots 严格） |
| **美团到餐/外卖评价开放 API** `developer.meituan.com` | official_api，但**只能读我方已授权/已入驻门店** | avgPoiScore/serviceScore/productScore + comment/query | ✅ 真堂食（限自家店） | low |
| **高德 Web Service Place API** `restapi.amap.com/v3/place/*` | official_api，个人 100/日、企业 1000/日 | POI 元数据 + biz_ext.rating **聚合分** | ❌ 只给聚合分，无评论正文 | low |
| **百度地图 Place API** `lbsyun.baidu.com` | official_api | POI + comment_num/overall_rating/content_tag **聚合字段** | ❌ 无评论正文（百度自己因搬点评评论败诉，故不再外吐正文） | low |
| **腾讯位置服务 WebService** `lbs.qq.com` | official_api，个人免费/商业授权 ¥5 万/年 | POI 名录 + 坐标 | ❌ 无评分无评论 | low |

**关键区分（按任务要求）**：高德/百度/腾讯三家 Place API 是**聚合分（MAP 类，dine_in_evidence=false）**，只解决"店在哪、叫什么、几分"；大众点评 B2B/公开网页才是**逐条食客声音（UGC 类，dine_in_evidence=true）**。两者不可互相替代——地图 API 做 name→rid 闸门与分店寻址，点评做口味证据。

---

## 2. 通道一句话矩阵（海外/外语侧）

| 源 | 合法通道（一句话） | 可取什么 | 真堂食声音 | 风控/合规 |
|---|---|---|---|---|
| **Google Places API** `developers.google.com/maps/documentation/places/web-service/place-details` | official_api，按次付费（GCP） | 聚合 rating + 最多 5 条近期评论（author/rating/text/time） | ✅ 英文/游客评论正文 | low |
| **TripAdvisor Content API** `developer-tripadvisor.com` | authorized_dataset，需客户经理签约 | 每 location 最近 3~5 条评论 + Feed 近 2 周全量 | ✅ 英文评论正文 | low（合同） |
| **TripAdvisor 公开网页** `tripadvisor.com/Restaurants` | public_html，强反爬+CAPTCHA | 餐厅页 + 评论串 | ✅ | medium |
| **Instagram Graph API** | official_api，但只能读我方拥有/管理的 Business 账号；hashtag 搜索限 30 个 tag/7 天、24h 窗口 | 媒体元数据 + 互动数 | ✅（仅限自有/管理账号） | low（能力极窄） |
| **Instagram 公开搜索** | search_snapshot，登录态严格限速 | hashtag/profile 公开帖 | ✅ | high（Meta 执法严） |
| **TikTok Research API** | official_api，**仅美/欧/英/瑞士学术机构**，商业主体无资格 | 视频/评论全字段 | ✅（但我们用不上） | low（资格门槛） |
| **TikTok 公开搜索** | search_snapshot，必须 US 住宅 IP + X-Bogus/a_bogus 签名 | 视频元数据 + 文案 | ✅ | high |
| **YouTube Data API v3** | official_api，10k quota units/日；search 耗 100 单位 ≈ 100 次搜索/日 | 视频元数据 + 评论串 | ✅ 长视频探店证据 | low |
| **Reddit Data API** | official_api OAuth，100 QPM；免费档限非商业，商业约 $0.24/1k 或 $12k/年 | subreddit 帖子 + 评论串 | ✅ r/Shanghai、r/chinesefood 真实推荐 | low（商业需谈授权） |
| **OpenRice 上海站** `openrice.com/zh-cn/shanghai` | public_html，无开放 API | 港式/粤式食评 | ✅ | medium（**当前 active=false，上海站稀疏**） |
| **Tabelog 上海站** `s.tabelog.com/china/A5102/` | public_html，无开放 API | 日文食评 + 3.0~3.8 评分体系 | ✅ 在沪日料/omakase 硬参考 | medium |
| **SmartShanghai** `smartshanghai.com/listings/dining/` | public_html，robots 友好 | 外籍编辑目录 + 月度新开专栏 | ❌（编辑/商家叙事，非 UGC） | low |
| **That's Shanghai** `thatsmags.com/shanghai/dining` | public_html | 外籍编辑活动/节日指南 + 年度 Awards | ❌ | low |
| **Time Out Shanghai** `timeoutshanghai.com` | public_html | 外籍编辑目录 + Critics' Pick | ❌ | low |
| **Nomfluence** `rachelgouk.com` | public_html，单人博客 | 作者亲测长评 + 月度 Shanghai Scoop | ✅ 英文堂食长证据 | low |

---

## 3. 海外源对哪些菜系/场景不可替代

按"中文平台拿不到、必须靠海外源"的原则排序：

1. **在沪日料 / omakase / 烧鸟 / 怀石** → **Tabelog 上海站（s.tabelog.com/china/A5102）** 不可替代。
   理由：Tabelog 的 3.0~3.8 评分体系是日本籍食客用母语味觉投出来的；中文大众点评对日料 omakase 的评价常被"性价比/环境"稀释，Tabelog 是上海高端日料口碑的硬标尺。
2. **外籍 expat 口耳相传的隐藏 bistro / 新店首发** → **Reddit r/Shanghai + Nomfluence（rachelgouk.com）** 不可替代。
   理由：r/Shanghai 是在沪外籍人群真实推荐，常爆中文平台没收录的小众店；Nomfluence 作者亲写，框架 §4 漏店清单里的 **nabi、jelu、yaya's、nono's、Obscura、Rambu、GEN Guizhou** 都被该站覆盖——是补"新派融合/地方菜 fine-dining"缺口最直接的英文堂食证据。
3. **西餐 / 异国菜（法、意、西、中东、拉美、东南亚）+ brunch + 酒店餐饮的游客视角** → **Google Places API + TripAdvisor** 不可替代。
   理由：这是海外源里仅有的两个"官方授权 + 逐条英文评论正文"通道；Google Places 直接返回 review text，覆盖上海外籍游客消费的西餐厅最全。
4. **外籍 KOL 探店短视频 / viral 新店** → **TikTok（公开搜索）+ YouTube Data API** 不可替代。
   理由：中文抖音/B站是中文食客语境；YouTube 上的在沪外籍 vlogger、TikTok 英文探店提供中文平台稀缺的"外籍视角长证据"。注意 TikTok Research API 商业主体拿不到，只能走搜索快照。
5. **外籍生活方式媒体的开业信号与编辑 pick** → **SmartShanghai + That's Shanghai + Time Out Shanghai** 三角不可替代。
   理由：三家月度/周更的新开餐厅、节日指南、年度 Awards 是上海外籍餐饮圈的早期信号源；它们是编辑视角（dine_in_evidence=false），但对"漏店反推"里"为何没抓到"的新店发现环节不可缺。
6. **港式/粤式茶餐厅的港澳视角** → OpenRice 上海站可补，但当前 active=false（条目稀疏），不做主力。

---

## 4. 风险与合规要点

- **大众点评公开网页抓取 = high risk**：上海知产法院大众点评诉百度案（判赔 323 万）确立"即使 robots 允许，全文批量搬运并实质性替代点评服务也构成不正当竞争"。我方只走 B2B 签约（dianping_poiopen_b2b），公开网页仅做搜索快照/人工核对，不做规模化。
- **PIPL 姿态**：所有海外 UGC 评论含 author_name/头像/hometown，留存时只存聚合字段 + 评论正文片段，不落 PII 到可关联人；Google Places/TripAdvisor 的授权 API 自带展示条款（不可脱离地图 UI 做纯文本转售）。
- **TikTok Research API 对商业不开放**：已登记 `tiktok_research_api` 行说明"此路不通"，实际发现走 `tiktok_public_search`（搜索快照 + 第三方 actor，见 apify_design/part2）。
- **地图聚合分 ≠ 食客声音**：高德/百度/腾讯三行的 `dine_in_evidence=false`，只用于 name→rid 闸门与分店寻址；口味证据必须由点评/海外 UGC 行承担。

---

## 5. 文件清单

- 机器可读：`research/coverage/registry_rows_maps_overseas.jsonl`（21 行，已通过 15 字段 + 枚举校验）
- 本说明：`research/coverage/registry_rows_maps_overseas.md`

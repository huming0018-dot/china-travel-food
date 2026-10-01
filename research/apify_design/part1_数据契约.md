# Part 1 · 采集数据契约（Apify 通道第一部分）

> 范围：只定义「采什么、字段怎么落、LLM 做什么/不做什么」。不涉及 Apify 选型、调度、预算（见总集成）。
> 上位契约：north-star 宪法（A2 真实可溯、A3 机制优先、A5 账号最后手段）。

## 0. 现有表（只读核对要点）

| 表 | 关键字段（已存在） | Apify 通道写入方式 |
|---|---|---|
| `restaurants` | id, name, name_en, district, address, lat/lng, phone, price_avg, chain_type, central_kitchen, premade_risk, investor_info, is_curated, curate_reason | 门店层事实 PATCH（只动 6 字段，电话/坐标/营业时间不自动写） |
| `reviews` | id, restaurant_id, source_platform, source_url, author_name, user_id, visit_date, created_at, aspect_taste, aspect_json, content, is_hidden | 笔记/帖子层 = reviews 行；每帖一行 |
| `diner_seed_labels` | restaurant_id, tier, taste, labeler | 人工标注监督集，Apify 不写 |
| `restaurant_awards` | restaurant_id, award_name, year | 榜单层，Apify 增量补 |
| `restaurant_chefs` / `restaurant_chef` | restaurant_id, chef_id, role | 主厨层，Apify 新闻/KOL 线索入 gap |
| `food_events` | restaurant_id, event_type, start/end, is_overseas_brand, origin_market | 跨源/另类线索（快闪/联名/新开店） |
| `food_kol_watchlist` / `food_kol_mentions` | canonical_kol_id, platform, handle, post_id, context | KOL 提及层 |

## 1. 分层数据类型

### 1.1 门店层（store profile）
- name / name_en / aliases[]
- 分店锚定：brand_id（连锁品牌归一）、branch_tag（如「静安嘉里店」）、address、district、lat/lng
- 电话 phone（最小化：只存公开商家号码，不采个人）
- 营业时间 opening_hours（结构化 open_days/time）
- 营业状态 status（active/closed/relocated）+ closed_date + closed_source
- 人均 price_avg（只采平台明示人均或菜单价，宁空不假）
- chain_type（独立店/小型连锁/大型连锁/资本化连锁）
- investor_info（集团/控股）

### 1.2 笔记/帖子层（核心口味证据 = reviews 行）
- platform（xiaohongshu/douyin/weibo/zhihu/bilibili/meituan/dianping/web_media）
- post_id（平台原生）、source_url（必带）
- title / content（正文；PII 最小化：不采私信、不全文转载版权长文，存摘要+URL）
- 作者：author_id, author_name, follower_band（<1k/1k-1w/1w-10w/>10w）, is_verified, is_official_shop
- 发布日期 publish_date、到店日期 visit_date
- 互动：likes, collects, comments, shares
- 是否真实堂食 is_dine_in（LLM 判定：有具体菜品+堂食语境）
- 定位 POI：poi_id / poi_name（小红书笔记带的店铺定位）
- 媒体数：image_count, video_duration

### 1.3 菜品层（dish mentions）
- dish_name（提及菜品）
- aspect_taste（口味分 1-5，LLM 从正文抽取）
- sentiment（正/中/负）
- is_signature（招牌菜）
- 证据片段 evidence_quote（≤200 字原文）+ source_url

### 1.4 评论层（comment 独立食客声音）
- commenter_id / commenter_name
- content、comment_date、likes
- 是否被作者回复（UGC 互动）

### 1.5 作者可信度 / 软广信号
- author_type（verified_diner / kol / official_shop / astroturf_candidate / media）
- 商业标记：has_groupbuy, is_sponsored, mentions_recruitment, mentions_franchise
- burst_score（短时集中发帖）
- cross_duplicate（跨作者近重复正文）

### 1.6 跨源 / 另类线索
- 网综/网剧节目名 + 集数 + 提及餐厅
- 榜单：米其林/黑珍珠/Asia's 50 Best/携程美食林 + 年份
- KOL 提及（food_kol_mentions）
- 新闻：新开店/搬迁/主厨变动/快闪/联名（入 food_events）

## 2. 数据规范

- **存储**：JSONL 落 `/app/data/apify_ingest/<platform>/<date>.jsonl`，再由 ingest 脚本幂等写 DB。
- **去重主键**：(platform, post_id) 或 (platform, comment_id)；门店事实用 (restaurant_id, field, source_url)。
- **时间锚点**：publish_date / visit_date / captured_at（UTC）。
- **name→rid 闸门**：finding_name 核心必须与 DB restaurant.name 核心重叠，否则 REJECT（已在 findings_extractor 固化）。
- **confidence 枚举**：0.0–1.0；硬负面（预制/中央厨房）≥2 独立 TRUSTED 源才 ingest。
- **PII 最小化**：不采私信/手机号/身份证；评论正文存摘要（≤200 字）+ 原 URL；不全文转载版权长文。
- **宁空不假**：拿不到就不写，禁止模型补全。

## 3. LLM 参与边界

**LLM 只做**（已采集原文 → 结构化）：
- 菜品抽取（dish_name + sentiment + 堂食语境判定）
- aspect_taste 打分（从正文推断 1-5）
- 商业标记分类（团购/推广/招募/加盟）
- 菜系/子品类/场景归一
- 冲突仲裁与去重辅助

**确定性代码做**（LLM 不碰）：
- 硬门槛（n_ind≥2、口味均分≥3.5、≥2 独立声音）
- 半衰期加权、独立作者计数、confidence 计算
- DB 写库、PATCH、幂等去重
- name→rid 闸门

**禁止**：LLM 凭记忆/先验直接收录门店或打分；所有事实必须附 evidence_quote + source_url，schema 校验不过即丢弃。

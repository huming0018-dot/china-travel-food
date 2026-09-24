# Social Listening × 主厨/荣誉追踪 × 首页 Feed —— 关联机制设计 v3

> 视角：数据/机制工程师。本文是「上海美食图鉴」三套联动机制的**单一设计真相**，对齐 004 迁移已建的 `chefs / restaurant_chefs / restaurant_awards / food_events` 四张空表，并给出可扩展的 005 增量。
> 案例定位：**Nuits 搬迁恒隆二期、原址关闭 = Social Listening 漏报的回归测试用例；DV × 遇外滩 = 联合快闪的回归用例。** 修机制，不补单店——把这两家店跑通后，同类店必须被机制自动捞到。
> 边界：本文只做机制设计，不实际采集数据、不写前端代码。一切事实可溯源；写入口收敛到 raw → stage → service_role。

---

## 0. 设计原则（承接 architecture-v2 §0）

1. **修机制不补单店**：Nuits 不是"去补一条 Nuits 记录"，而是回答"为什么 T1 官方源（公众号/小红书）发了搬迁公告，监听管线没有触发原址 closed + 新址 active + relocate 事件"。修好源矩阵与词根后，机制应把 Nuits 和**一批同类搬迁店**一起自动捕获。
2. **一切事实可溯源**：每条事件 / 荣誉 / 主厨关联 / 卖点都带 `source_url` + `source_platform` + `date`；指不出来源的不写。
3. **写入口收敛**：采集器只产 raw JSONL → stage 校验 → 人工审核队列（rumor/mid 必经）→ `atlas_write.py`（service_role）写库。**禁止模型/前端直接写 REST**。
4. **时间是一等公民**：事件有 event_date，关店有 closed_at，主厨有 started/ended，荣誉有年份与 is_current，店铺有 last_listened_at / freshness_due。
5. **状态语义不污染**：`restaurants.status` 只取 active/closed；搬迁不"原地改地址"，而是原址 closed + 新址 active + 一条 relocated 事件互联，历史可追溯、地图不丢老店。

---

## 1. 总览：三套机制如何咬合

```
            ┌──────────────────────── SOCIAL LISTENING（供给层）────────────────────────┐
            │  源矩阵 T1官方→T2权威→T3 KOL→T4地图状态                                      │
            │  词根配置(搬迁/闭店/新店/换主厨/飞行/联名/快闪/荣誉) + Vercel Cron 巡检          │
            └───────┬───────────────────────────────────────┬──────────────────────────┘
                    │ raw_event / raw_chef / raw_award       │
        ┌───────────▼──────────┐                ┌──────────▼───────────┐
        │ B. 主厨/荣誉追踪      │                │ A. 事件/状态处理      │
        │ chefs + restaurant_   │                │ restaurants.status   │
        │ chefs + awards 建档   │                │ + closed三要素 + 对齐  │
        │ （师承/流动/荣誉/卖点）│                │ 同名异址/relocated事件 │
        └───────────┬──────────┘                └──────────┬───────────┘
                    └──────────────────┬───────────────────┘
                                       ▼
                          ┌──────── C. 首页 Feed（消费层）────────┐
                          │ food_events 按 event_date desc，       │
                          │ category 分 tab，high 优先、rumor 标注  │
                          │ feed_cadence 自控（日/周/月）           │
                          └─────────────────────────────────────────┘
```

一句话：**Social Listening 是传感器，主厨/荣誉是实体档案，Feed 是这两者对外的时间线视图。** 三者共用同一套置信度规则与写库管线。

---

## A. Social Listening 管线设计

### A.1 源矩阵（按优先级分层）

> 原则：T1 一手源即可定 high；T3 KOL 单源只够 mid/rumor；T4 地图状态只作**关店/在营的旁证触发器**，不作正面荣誉。

| 层 | 源 | 解决什么 | 采集方式 | 能否单独定 high |
|---|---|---|---|---|
| **T1 一手官方** | 品牌**官方公众号**（mp.weixin，经搜狗微信 weixin.sogou.com 入口）、**官方小红书蓝V/企业号**、**官方抖音企业号**、**官网/官网新闻页**、**微博认证蓝V**、官方预订/小程序公告 | 搬迁/闭店/新店/换主厨/联名/快闪/荣誉的**第一事实** | browser-use 订阅 + 关键词；公众号走搜狗微信低频次（5–10 次/轮），验证码交真人 | **是**（1 个 T1 即可 high） |
| **T2 权威/新闻稿** | 米其林指南官方、黑珍珠官方、主流媒体（澎湃/上观/人民网）、海外英文媒体（TimeOut/That's Shanghai/SmartShanghai/Conde Nast/Nomfluence）、PR 新闻稿 | 荣誉发布、海外首店、主厨变动、关店事实核验 | general_search 限定域名 + web.fetch 正文 | 是（≥2 个独立 T2 互证） |
| **T3 KOL/老饕** | 小红书老饕（非挂车）、抖音探店（剔除团购挂车）、B 站美食 UP、即刻/豆瓣同城/知乎老帖、收藏夹合集 | 飞行厨房/快闪/主厨动向/民间口碑的**早期信号** | browser-use 深采，必看评论区；挂车视频按软广处置 | **否**（单源只 mid；与 T1/T2 互证才升 high） |
| **T4 地图/POI 状态** | 大众点评"已关闭/歇业"标记、高德/百度地图营业状态、电话邦停机、企查查注销/吊销 | **营业状态保鲜**：在营/关店/地址变更的自动巡检 | 高德/点评 browser-use 列表脚本化；坐标 coord_source=amap | 否（仅作旁证触发器；触发后必须回 T1/T2 找公告） |

**关键反例（不算在营证据，禁止用于"还开着"的正面判断）：**
- 聚合预订站（DiningCity、OpenTable 残留）；
- 招聘网站（BOSS/猎聘）仍在招该店岗位；
- 外卖平台仍可下单；
- 通稿/聚合站转载。
> 这些只能触发"存疑待核"，不能把一家已关店判回 active。

### A.2 监测词根配置（配置驱动，可扩展）

> 词根表是配置文件 `research/social/listen_keywords.yaml`，**不写死在代码里**。事件类型 × 店名/主厨名种子 × 词根矩阵。新事件类型只需加一段配置。

| 事件 category | 种子 | 监测词根（中文，含方言/俗称） |
|---|---|---|
| `relocated` 搬迁 | {店名} | 搬迁、搬去、迁址、乔迁、新店址、原址、搬到、新址见、装修升级、重新出发、搬离 |
| `closed` 闭店 | {店名} | 闭店、停业、关了、歇业、关门、最后一天、告别、不再营业、结束、租赁合同到期 |
| `new_open` 新店/首店 | {店名} / {主厨名} | 开业、新开、试营业、开业典礼、即将开业、预约、首店、中国首店、上海首店、登沪、落沪、揭幕 |
| `chef_changed` 换主厨 | {店名} + {主厨名} | 主厨、换主厨、厨师长、主理人、卸任、离任、加入、新任、掌舵、挂帅、告别厨房 |
| `guest_kitchen` 飞行厨房 | {主厨名} | guest chef、客座、飞行厨房、菜单之夜、chef's table、限定晚宴、remix、客座主厨、快闪菜单 |
| `collaboration` 跨界联名 | {店名} | 联名、合作、collab、×（如 DV×遇外滩）、携手、限定合作、联名菜单 |
| `popup` 联合快闪 | {店名} | popup、快闪、限时、快闪店、限定席位、一轮游、only this week |
| `award` 荣誉 | {店名} | 米其林、黑珍珠、必比登、一饭封神、黑白厨房、榜单、三星、二星、一星、三钻、冠军、入选 |

配置字段示例：
```yaml
- category: relocated
  seeds: ["{restaurant_name}", "{alias}", "{name_en}"]
  roots: ["搬迁","搬去","迁址","乔迁","原址","新址"]
  negative_roots: ["搬迁记","搬迁vlog攻略"]   # 排除旅游类噪声
  sources: [T1, T2, T3, T4]
  t4_trigger: true     # 地图"已关闭"标记自动进此队列
```

- **别名扩展**：搜索种子自动带上 `restaurants.aliases`（异写/简称/拼音/英文名），避免"Nuits / NUITS / 努伊 / 那屋"漏召。
- **负向词**：排除"搬迁攻略""搬迁vlog"等旅游/搬家公司噪声。
- **同门扩展**：同一主厨/品牌系下所有店，主厨名变更会连带触发同门店巡检（nabi/WULI 同 Tom Ryu）。

### A.3 采集频率与保鲜策略

采集（raw 产生）与 Feed 发布（用户看到的动态）是**两条频率线**，解耦：

**(1) 采集频率（系统后台，Vercel Cron）**

| 巡检对象 | 周期 | 跑哪些源 | 说明 |
|---|---|---|---|
| T1 官方源（已收录的高端/米其林/黑珍珠店） | **每日** | 公众号 + 官方小红书 + 官方抖音 | 高价值店，公告当天捕获（Nuits 类漏报主要靠这一档补） |
| T4 地图状态巡检 | **每周** | 高德/点评营业状态 + 点评"已关闭"标记 | 批量扫全库，"已关闭"→进 closed 核验队列 |
| T2/T3 全量词根 sweep | **每周** | 新闻稿 + KOL + B站/抖音/小红书 | 跑 §A.2 词根矩阵，捕新店/飞行/联名/快闪早期信号 |
| 荣誉季（米其林/黑珍珠发布窗口） | **每日** | T2 权威源 | 发布日前后加密监听 |
| 新收录店 | **开业后 30 天内每日** | T1+T4 | 新店地址/营业状态易变 |

**(2) 保鲜期（freshness，决定一家店多久必须复检一次在营状态）**

| 店型 | 保鲜期 | 依据 |
|---|---|---|
| 新收录店 | 30 天 | 新店存活率低、地址易变 |
| 高端/米其林/黑珍珠店 | 180 天 | 主厨/搬迁/荣誉变动影响大，重点盯 |
| 平价连锁 | 90 天 | 关店/换址频率中等 |

落库字段（005 扩展）：`restaurants.last_listened_at DATE`、`restaurants.freshness_due DATE`。Cron 每次巡检刷新 `last_listened_at`；`freshness_due < today` 的店强制进下一轮 T4+T1 复检。`v_data_freshness` 视图列出超期未检店。

**(3) Feed 发布频率（用户自控 `feed_cadence`）**

- 采集照常跑（日/周后台），但**喂给用户的 Feed 聚合节奏**由 `feed_cadence` 决定：`daily` / `weekly`(默认) / `monthly`。
- 高置信 high + 重大事件（海外首店、荣誉发布、主厨变动）**不等待 cadence**，即时上浮首页；mid/rumor 攒到下一个 cadence 周期统一进审核队列。

### A.4 事件置信度评分

> 确定性规则，不交给模型拍脑袋。一条候选事件落库前先算分。

| 置信度 | 条件 | 状态 | 首页处理 |
|---|---|---|---|
| **high** | ① ≥1 个 T1 官方源；**或** ② ≥2 个互相独立的 T2/T3 源（不同账号、非互转）且内容一致 | `verified` | 直接展示 |
| **mid** | 仅 1 个 T2 源；或 1 个 T3 KOL 源但有 T4 旁证（地图已关） | `rumor` 待核 | 进人工审核队列，标"传闻"，审核通过转 verified |
| **low / 丢弃** | 单 T3 且无旁证、内容矛盾、通稿/聚合站/招聘残留 | `rumor` 或丢弃 | 不展示，留痕备查 |

**加分/减分明细：**
- +T1 官方源 = 直接 high（官方公告即事实，Nuist 搬迁公告若被捕获即 high）；
- + 独立源数量（不同平台、不同发布主体、非转载）；
- − 同一内容被 N 个账号转载 = 只算 1 个独立源；
- − 团购挂车 / 营销号 / 模板文案来源 → 降一级或丢弃；
- **不算证据**：通稿、聚合站、招聘、预订站残留（见 A.1 反例）。

写库时 `food_events.sources` 数组必须列出**每个独立源**的 `{platform, title, url, date}`，置信度由这些源的层位与数量函数化得出，不留主观。

### A.5 搬迁/关店完整处理流程（Nuits 回归用例）

> 这是机制的核心闭环。以 Nuits 为例：原址关闭、迁至恒隆二期（Plaza 66 Phase II），官方公众号/小红书应有公告但系统未捕获。

**Step 1 — 触发（传感器层）**
- 任一触发器命中即入队列：T1 官方公告（"Nuits 搬去恒隆二期了"）/ T4 点评标记"已关闭" / T3 老饕"原址没了"。
- 产出 raw_event（category=relocated 或 closed），带 raw sources。

**Step 2 — 证据固化（证据层）**
- 抓取官方公告正文 + URL + 发布日期；T4 截图/状态作旁证；
- 确认两件事：①原址是否真关；②新址在哪、是否已在库。

**Step 3 — 原址处理（建模层）**
```sql
UPDATE restaurants SET
  status = 'closed',
  closed_at = '2026-XX-XX',                 -- 公告/最后营业日
  closed_source_url = 'https://mp.weixin...', -- 公告直链
  closed_note = '搬迁至恒隆广场二期',
  last_listened_at = CURRENT_DATE
WHERE id = :nuits_old_id;
```
> closed 三要素齐备：**日期 + 来源 + 公告说明**。原址行保留在地图（置灰），历史评价/荣誉不丢。

**Step 4 — 新址建/对齐（建模层）**
- 若恒隆二期新址**已在库**：按 A.6 实体对齐判为"同名异址续营"，对齐到该行；
- 若**不在库**：新建一行 `status='active'`，写全地址/坐标/电话（高德 coord_source=amap），并设 `lineage_parent_id = :nuits_old_id`（血缘指针）。
- **主厨关联继承**：把原址主厨 `restaurant_chefs` 复制到新址行（`started`=新址开业日，`is_current=true`），原址关联保留为 `is_current=false, ended=搬迁日`。
- **荣誉继承**：星/钻跟厨房走，复制到新址行（source 注明"品牌搬迁继承"）；**口味评价不自动迁移**——新 dining room 需重新积累堂食证据，新行 `review_count=0, review_confidence=0`。

**Step 5 — 互联事件（事件层）**
```json
{"scope":"local","category":"relocated","title":"Nuits 搬迁至恒隆广场二期",
 "event_date":"2026-XX-XX","restaurant_id":":nuits_old_id","related_restaurant_id":":nuits_new_id",
 "summary":"原址关闭，迁至上海恒隆广场二期（Plaza 66 Phase II）","district":"静安区",
 "sources":[{"platform":"官方公众号","title":"Nuits 新址公告","url":"https://mp.weixin...","date":"..."}],
 "confidence":"high","status":"verified"}
```
> 一条 `relocated` 事件把原址与新址双向互联：详情页老店显示"已搬迁 → 新店"，新店显示"原址于 X 关闭"。

**Step 6 — 回归断言**
- 跑完后断言：原址 closed 三要素齐全 ∧ 新址 active ∧ 存在一条 relocated 事件互联二者 ∧ 主厨/荣誉已继承。任一缺失 = 机制未闭环，回修。

### A.6 去重与实体对齐

| 情形 | 判定规则 | 处理 |
|---|---|---|
| **同名异址（搬迁）** | 同名 + 主厨/品牌一致 + 公告/事件佐证搬迁 | 原址 closed + 新址 active + relocated 事件 + lineage_parent_id |
| **同名异址（分店新开）** | 同名 + 不同商圈 + 无搬迁公告 + 品牌系一致 | 两行都 active，写 new_open 事件，related 互链，挂同一 brand_group |
| **品牌更名** | 同址 + 同厨房 + 新旧名并列出现 | 同一行改名，旧名进 `aliases`，写一条 closed_menu/更名说明事件 |
| **同址异名** | 同地址坐标 + 名称不同 | 进人工核对：是换老板/换品牌还是误记；写 notes |
| **海外品牌上海首店** | 海外知名店 + 上海地址 + new_open 公告 | scope=overseas 事件；若海外总店已建档，chef_id/brand 关联 |

- 实体对齐键：`(normalized_name, address_hash)` 模糊匹配；`aliases` 参与召回；冲突一律进人工审核队列，不自动合并。

---

## B. 主厨 / 荣誉追踪体系

### B.1 主厨档案模型（对齐 chefs 表，005 扩展）

004 已建 `chefs` 基础列。追踪体系需要补：

```
chefs（004 已有 + 005 扩展）:
  id, name, name_en, title, bio, origin,
  is_traveling,                          -- 飞行主厨/Guest Chef
  social_xhs, social_douyin, social_weibo,
  reputation jsonb,                      -- {summary, source_url}
  -- 005 新增：
  mentor_ids    INT[],                   -- 师承（导师 chef_id 数组）
  tracking_seeds jsonb,                  -- 搜索种子 [{type:"name"/"name_en"/"restaurant", value}]
  last_listened_at DATE,                 -- 上次跑 social listening
  data_updated_at, created_at, updated_at

restaurant_chefs（004 已有）:
  restaurant_id, chef_id, role,          -- 主厨/联合主厨/主理人/顾问/前主厨
  is_current, started, ended, source_url,
  PK(restaurant_id, chef_id, role)
```

- 一位主厨一行，跨店全部挂在 `restaurants[]` 里；前店 `is_current=false, ended=日期`。
- **师承/同门**（nabi / WULI 同 Tom Ryu）：不另建复杂关系表，用 `chefs.mentor_ids` 指向共同导师即可表达"同门"；界面可由"同一 mentor_ids"反查同门店。

### B.2 主厨流动追踪（三类事件）

| 流动 | 动作 | 事件 | 表变更 |
|---|---|---|---|
| 主厨**新店开业** | 新店开业 → 自动关联主厨 | `new_open`（chef_id 指向新店主厨） | 新 restuarant + restaurant_chefs(is_current=true) |
| 主厨**离职/换帅** | 官方公告/媒体披露 | `chef_changed` | 旧 restaurant_chefs.is_current=false, ended=日期；新店挂新关联 |
| **飞行客座** | guest chef 来沪/出去客座 | `guest_kitchen`（chef_id, 起止日期, menu 说明） | 不改动主职 is_current；事件留痕 |

> 所有流动都**同时**写一条 food_events——人事表变了，Feed 时间线才有内容。

### B.3 荣誉结构化（对齐 restaurant_awards）

004 表已够用，关键是**写入规则**：

```
restaurant_awards（004 已有）:
  restaurant_id, award_type, level, year, season,
  is_current, source_url, source_name, created_at
```

- `award_type` 枚举：`michelin_star` / `bib_gourmand`(必比登) / `black_pearl` / `media_show`(综艺声誉) / `other_list`。
- `media_show` 覆盖一饭封神、黑白厨房、舌尖、主厨的荣耀等——**节目热度只作发现/声誉，不作口味背书**。
- **每届一行**：米其林/黑珍珠发布年，旧记录 `is_current=false` 保留历史，新记录插入；标签 cid159/160 仍挂作筛选，但权威星/钻**以本表为准**。
- `source_url` 必填：米其林以 `research/authority/michelin_shanghai_153.json` 为准；黑珍珠补官方页。

### B.4 主要卖点建档（restaurants.selling_points）

```json
selling_points: [
  {"point":"招牌关东煮，昆布鲣鱼双出汁","type":"signature_dish","source_url":"https://..."},
  {"point":"主厨 Tom Ryu 怀石出身，omakase 流程","type":"technique","source_url":"..."},
  {"point":"食材每日筑地/浦东空运","type":"ingredient","source_url":"..."},
  {"point":"仅 8 席吧台，预约制","type":"experience","source_url":"..."}
]
```
- 每店 3–6 条；每条带来源；类型 ∈ `signature_dish / technique / ingredient / experience / atmosphere`。
- 卖点不是营销话术，必须有堂食/官方来源支撑。

### B.5 追踪机制

1. **搜索种子**：每位已建档主厨自动生成种子 = 主厨名 + 英文名 + 现关联店名，进 §A.2 词根 sweep；`last_listened_at` 记录上次扫描时间。
2. **触发**：种子命中 relocated/closed/chef_changed/guest_kitchen/new_open 词根 → 产 raw_chef / raw_event。
3. **同门扩散**：Tom Ryu 类导师一旦有新动作，其 `mentor_ids` 反向查出的所有同门主厨店连带进巡检队列。
4. **荣誉季**：米其林/黑珍珠发布窗口，T2 权威源每日扫，自动产 raw_awards（is_current 翻转）。

---

## C. 首页动态栏目（Feed）设计

### C.1 Feed 分类 tab → category 映射

| 首页 tab | food_events.category | scope | 备注 |
|---|---|---|---|
| 主厨新店 | `new_open`（chef_id 非空） | local/overseas | 主厨主理新店 |
| 海外米其林·热门店首店 | `new_open`（scope=overseas） | overseas | 海外名店上海首店 |
| 主厨变化 | `chef_changed` | local | 换帅/离职/上任 |
| 飞行厨房 | `guest_kitchen` | local | guest chef 客座 |
| 跨界联名 | `collaboration` | local | 品牌×品牌联名 |
| 联合快闪 | `popup` / `collaboration` | local/overseas | **DV×遇外滩** 回归用例 |
| 荣誉发布 | `award` | local/overseas | 米其林/黑珍珠/综艺 |
| （默认全部） | 全部 | 全部 | event_date 倒序 |

### C.2 事件数据模型（对齐 food_events，005 扩展）

004 已有：`scope / category / title / summary / event_date / restaurant_id / related_restaurant_id / chef_id / city / district / sources(jsonb) / confidence / status`。

005 为 Feed 与审核队列补：

```
food_events 005 扩展:
  dedup_hash          TEXT UNIQUE,   -- (category+主体+event_date) 去重键
  review_status        TEXT DEFAULT 'pending',  -- pending/approved/rejected（人工审核队列）
  reviewed_by          TEXT, reviewed_at TIMESTAMPTZ,
  expires_on           DATE NULL,    -- 快闪/限时活动结束日（过期后自动下沉）
```

- **scope × category × 关联实体 × 多源 × 置信 × 状态** 六元组完整描述一条 Feed 项。
- 联合快闪（DV×遇外滩）：`category=collaboration/popup`，`restaurant_id=Da Vittorio`，`related_restaurant_id=遇外滩`，两家都在 sources 里，scope=local。
- 快闪有时效：`expires_on` 过后从首页自动下沉，不删库。

### C.3 首页展示逻辑

1. 排序：`event_date DESC, id DESC`（v_feed_recent 已是此序）；同日期内 **high 置信优先于 mid/rumor**。
2. 筛选：按 category tab 过滤；可叠加 scope（本地/海外）。
3. 标注：
   - `status=rumor` 或 `confidence=mid` → 卡片角标"传闻 / 待证实"；
   - `expires_on` 临近 → "限时中"；
   - 每条可点开看 sources 多源引用（溯源）。
4. 只展示 `review_status=approved`（high 自动 approved；mid/rumor 经人工审核后 approved）。

### C.4 更新频率控制

- 用户侧 `feed_cadence` = daily / weekly(默认) / monthly，控制 Feed 聚合推送节奏。
- 后台采集不等人：high 重大事件即时上浮；mid/rumor 攒批到 cadence 周期进人工审核队列，审核通过后随下一期 Feed 发布。

### C.5 海外内容策略

- `scope=overseas` 专档：监测**海外米其林/热门店的上海首店、海外主厨来华客座、海外品牌与本地店联名快闪**。
- 种子：米其林全球榜单变动 + 海外媒体（TimeOut/That's Shanghai/Conde Nast）"coming to Shanghai"类报道。
- 重点：海外三星/知名店落沪（首店）、guest chef 来华、DV 级别的跨国联名。

---

## D. 可执行采集 SOP（运维手册）

> 目标：什么时间、跑哪个源、产出哪个 raw 文件、如何校验写库。采集器只产 raw，写库收敛到 `atlas_write.py`（service_role）。

### D.1 调度日历（Vercel Cron）

| Cron | 时间(UTC+8) | 跑什么 | 产出 raw 文件 |
|---|---|---|---|
| `listen:t1-daily` | 每日 09:00 | T1 官方源（高端/米其林/黑珍珠店公众号/小红书/抖音） | `research/social/raw_events_YYYYMMDD.jsonl`、`raw_chefs.jsonl` |
| `listen:t4-weekly` | 每周一 10:00 | T4 高德/点评营业状态全库扫；"已关闭"进 closed 队列 | `research/social/raw_status_YYYYWww.jsonl` |
| `listen:t23-weekly` | 每周三 10:00 | T2 新闻稿 + T3 KOL/B站/抖音词根 sweep | `raw_events_*.jsonl`、`raw_awards_*.jsonl` |
| `listen:award-season` | 米其林/黑珍珠发布窗口期每日 10:00 | T2 权威源荣誉扫 | `raw_awards_*.jsonl` |
| `listen:freshness` | 每周日 22:00 | 刷 last_listened_at；freshness_due 超期店下轮复检队列 | `listen_runs.json`（运行日志） |
| `feed:aggregate` | 按用户 feed_cadence | 聚合 approved 事件 → 首页；mid/rumor 进审核队列 | （不产 raw，驱动 v_feed_recent） |

### D.2 产出 raw 文件契约（对齐 COLLECTION_CONTRACT.md）

每次 run 产出三类 JSONL（UTF-8，一行一对象）：
- **raw_events.jsonl**：relocated/closed/new_open/chef_changed/guest_kitchen/collaboration/popup/award——字段同 §C.2，`sources` ≥1 个 T1 或 ≥2 独立源。
- **raw_chefs.jsonl**：主厨档案 + 关联店（前店 is_current=false）。
- **raw_awards.jsonl**：每届一行，is_current 翻转。
- 每条 raw 顶部 `notes` 写 discovery 来源（"由『Nuits 搬迁 恒隆二期』经搜狗微信官方公众号捕获"）。

### D.3 校验 → 写库流水线

```
采集器 → raw JSONL
   ↓ stage1 校验（机器门）：
     · 必填 source_url/platform/date 非空
     · URL 可访问、非转载聚合站
     · dedup_hash 不重复
     · confidence 按 §A.4 规则函数化重算（不采信模型自报）
   ↓ stage2 实体对齐：
     · 同名异址/分店/更名按 §A.6 判定，冲突进人工
   ↓ 人工审核队列：
     · high → 自动 approved
     · mid/rumor → review_status=pending，人工核对后 approved/rejected
   ↓ atlas_write.py（service_role）：
     · 按 §A.5 闭环写 restaurants.status / closed三要素 / lineage / food_events / chefs
   ↓ recalc + 回归断言：
     · recalc_taste_for(受影响店)；跑 regression_set 命中核对
```

**铁律：采集器/模型禁止直接 REST 写库；一切写入经 `atlas_write.py`（service_role）+ RLS 只读公开面。**

### D.4 Nuits / DV 回归断言（每次改机制后必跑）

| 回归用例 | 断言（机制必须自动产出） |
|---|---|
| **Nuits 搬迁** | 原址 status=closed 且 closed_at/source_url/note 三要素齐；恒隆二期新址 active；存在 relocated 事件互联；主厨关联继承、荣誉继承、口味分不迁移 |
| **DV × 遇外滩** | 存在一条 collaboration/popup 事件，双店 related，sources 含双方官方/媒体，confidence=high，有 expires_on |
| **机制泛化** | 同批 run 应自动捞出 ≥1 家同类搬迁/联名店（证明不是单点打补丁） |

---

## E. 数据扩展提案（005 增量，幂等可重跑）

> 004 已建四空表；以下为支撑本机制的最小增量，DDL 走 Supabase SQL Editor。

```sql
-- restaurants：状态保鲜 + 血缘
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS closed_at DATE;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS closed_source_url TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS closed_note TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS lineage_parent_id INT REFERENCES restaurants(id);
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS brand_group TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS last_listened_at DATE;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS freshness_due DATE;

-- food_events：去重 + 审核队列 + 快闪时效
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS dedup_hash TEXT;
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'pending';
ALTER TABLE food_events ADD COLUMN IF NOT EXISTS expires_on DATE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_dedup ON food_events(dedup_hash) WHERE dedup_hash IS NOT NULL;

-- chefs：师承 + 追踪种子
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS mentor_ids INT[];
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS tracking_seeds JSONB;
ALTER TABLE chefs ADD COLUMN IF NOT EXISTS last_listened_at DATE;

-- 审核状态 CHECK
ALTER TABLE food_events ADD CONSTRAINT ch_event_review
  CHECK (review_status IN ('pending','approved','rejected'));
```
> 写库收敛不变：以上表全部公开 SELECT（RLS），写仅 service_role。

---

## F. 验收 DoD

- [ ] 源矩阵 T1–T4 分层落地；Nuits 类搬迁能被 T1 官方源当日捕获（不再漏报）。
- [ ] 词根配置表 `listen_keywords.yaml` 配置驱动，新增事件类型只加配置不改代码。
- [ ] 置信度函数化：1 个 T1 或 ≥2 独立源=high；单 KOL=rumor；通稿/招聘/预订残留不算在营证据。
- [ ] Nuits 闭环断言全绿（原址 closed 三要素 + 新址 active + relocated 互联 + 主厨/荣誉继承）。
- [ ] 主厨档案含师承 mentor_ids、流动三事件（new_open/chef_changed/guest_kitchen）落 food_events。
- [ ] 荣誉每届一行、is_current 翻转、source_url 必填；综艺声誉入 media_show。
- [ ] Feed 七 tab 映射正确，event_date 倒序、high 优先、rumor 标"传闻"、快闪有 expires_on。
- [ ] 写库全走 raw → stage → 人工队列 → atlas_write.py(service_role)，无模型直写 REST。
- [ ] 每次机制改动后 Nuits + DV×遇外滩回归断言通过，且同批自动捞出同类店（修机制不补单店）。

# 上海美食图鉴「最新动向」Feed — 抓取机制 / 代码 / 更新规则（实现方案）

> 配套机制设计：`research/design/social-listening-chef-feed-v3.md`；本文是其**可运行实现**，2026-09-24。
> 技术栈：Supabase / PostGIS + Next.js 14 (Pages Router) + Vercel + GitHub；采集运行在本机浏览器登录态。

## 0. 一句话

用「配置驱动的地毯搜索 **sweep** 发现未知 + 按店名巡检 **watch** 保鲜已知」，经确定性转换器把真实食客 / 官方 / 权威媒体证据归并为**带时效**的事件写入 `food_events`；前端读 `feed_view`，自动获得「已审核 + 未过期 + 时间倒序」的首页时间线。

---

## 1. Feed 栏目（事件 category → 首页 tab）

| category | 首页栏目 | 说明 | 限时(expires) |
|---|---|---|---|
| `new_open` | 新店 / 首店 | 新开餐厅、海外米其林·热门店上海首店 | 否（事实） |
| `coming_soon` | 即将开业 | 开业预告 | 否 |
| `relocated` | 搬迁 | 迁址（原址 closed、新址 active） | 否 |
| `closed` | 闭店 | 关店 | 否 |
| `chef_changed` | 主厨变化 | 主厨更换 | 否 |
| `guest_kitchen` | 飞行厨房 | 客座主厨 / 四手联弹晚宴 | 是（默认 3 天） |
| `collaboration` | 跨界联名 | 联名菜单 / 品牌合作 | 是（默认 45 天） |
| `popup` | 联合快闪 | 限时快闪店 | 是（默认 14 天） |
| `menu_update` | 菜单更新 | 季节 / 新菜单 | 是（默认 90 天） |
| `award` | 荣誉发布 | 米其林 / 黑珍珠 / 50Best 等 | 否 |

---

## 2. 三套咬合机制

1. **传感器**：`sweep`（发现未知）+ `watch`（已知店保鲜）—— `events_collect.py`
2. **实体档案**：`chefs` / `restaurant_chefs` / `restaurant_awards`（主厨、师承 mentor_ids、每届荣誉一行、卖点建档）
3. **时间线**：`food_events` + 数据库视图 `feed_view`

---

## 3. 抓取机制

### 3.1 源矩阵（分层，决定置信度）

| 层 | 来源 |
|---|---|
| T1 官方 | 品牌 / 餐厅 / 主厨官方公众号、小红书·抖音官方号、官网、新闻稿 |
| T2 权威指南 / 媒体 | 米其林、黑珍珠、World's 50 Best、Gault&Millau、Timeout、澎湃、界面、Eater |
| T3 KOL / 食客 UGC | 小红书探店（**含评论区**）、抖音、B 站、大众点评长评 |
| T4 地图状态 | 高德、腾讯地图、大众点评商户状态 |

### 3.2 平台覆盖

- **小红书（主通道）**：sweep 搜索 + 真实坐标点击 + 正文 + 评论区。
- **微信公众号 / 视频号 / 抖音 / B 站**：沿用同一套词根平移（采集器适配见 §10）。
- **米其林 / 黑珍珠**：发布季专项（`michelin_collect.py` / authority 流程）。

### 3.3 两种采集模式

- **sweep**：读 `listen_keywords.json` 每类的 `sweep` 搜索词（**已含餐饮语境**）+「上海」地毯搜索，发现未知。
- **watch**：按重点店名（米其林 / 黑珍珠 / 高关注店）巡检，做状态保鲜。

### 3.4 采集铁律

- 必须**真实坐标点击**让 URL 带 `xsec_token`（教训 #54），禁止 JS `.click()`（否则风控 error 300031）。
- **单浏览器登录态串行**，不开并行子代理（多代理抢同一 Chrome 会互相关闭 overlay）。
- **断点续跑**：按 `query`（sweep）/ `watch_name`（watch）去重。
- 登录失效（跳登录 / blocked=auth）→ `interaction.request_action(type=browserControl)` 请用户登录，不硬刷。

---

## 4. 转换器 `events_build.py` 的确定性机制（九道）

1. **分类**：事件词根命中（长词 / 专属词在前）。
2. **餐饮域闸**：命中服装 / 潮玩 / 钟表 / 桌游 / 地产等非餐饮强信号且无食物信号 → 丢弃；「面料」的「面」不算食物（食物词不用「面 / 餐 / 汤 / 包」这类宽单字）。
3. **合集不锚**：正文 ≥2 个店、≥2 处「地址：」、或标题为盘点词 + 列举 → 丢弃（联名 pair 除外）。
4. **每篇独立锚主体：不按搜索批次整批锚定（教训 #56）。
5. **主体位置判定**：海外品牌在正文出现位置比库内店名更靠前 → `restaurant_id=null`，库内店名作 `related_restaurant_id`（防「正文顺带提场地」被误锚）。
6. **海外限时放宽**：`new_open / coming_soon / popup / collaboration / guest_kitchen` 有拉丁品牌 + 餐饮信号时，**允许 rid 为空也成事件**（品牌写进标题，先 `rumor`，多源再 `verified`）。
7. **锚定校验**：品牌 forms / core_unique（库内唯一指向）/ 商场分店冲突保护。
8. **时效**：`parse_end`——「限时 N 个月」按 30N 天、「限时 N 天」优先于结束日月日；结束日月日须晚于 event_date，否则顺延一年；无明确时长用默认窗口。**过期的限时事件直接丢弃**。
9. **源分层 + 多源合并 + 置信度**：≥1 个 T1 或 ≥2 个独立 T2/T3 → `high`；单个 T2/T3 → `mid`；同平台同作者 / 转载只算 1 个独立源。

附：rid=null 时用 `guess_district` 推断商圈（外滩→黄浦、静安寺 / 张园→静安、古北 / 黄金城道→长宁、陆家嘴 / 前滩→浦东等）。

---

## 5. 入库 `atlas_write.py`

- `--domain events`，**默认 dry-run**，加 `--commit` 才写库。
- **幂等**：事件按 `title + event_date` 查重，可安全重跑。
- 字段 `EVENT_COLS`（已含 `expires_on`）；POST 带 `Prefer: return=representation`，写后回读。
- 锚不到库内主体的**中文新店** → `new_shops_unmatched.jsonl`，核实（确为餐饮、在营）后再补收录，不硬建。

---

## 6. 前端呈现

- 数据库视图 **`feed_view`（005 已建并授权 anon / authenticated）**：自动只选 `status='verified'` 且（`expires_on` 为空或 ≥ CURRENT_DATE），按 `event_date DESC, id DESC`，LEFT JOIN 出餐厅名 / 主厨名。
- 前端直接 `SELECT * FROM feed_view` 即得到「已审核 + 未过期 + 时间倒序」Feed；**过期事件自动下沉、不删库**。
- `rumor` 不进 `feed_view`，多源合并升级为 `verified` 后才显示。
- 首页「最新动向」栏目 + tab 映射（组件待建，见 §10）。

---

## 7. 更新规则（调度 / 保鲜 / cadence 自控）

### 7.1 为什么不用 Vercel Cron

采集依赖本机小红书登录态 + 真实鼠标事件（反爬要求），Vercel 无登录态、无浏览器。→ 用 **doubao-cron-scheduler 在本机定时跑 `plane=bu` 的 cell**（与「小红书 reviews 批量采集」任务同模式）。

### 7.2 调度日历（建议，可自控）

| 任务 | 频率 | 口径 |
|---|---|---|
| sweep | 每日 1 批（如 10:43） | `run_batch(max_queries=8)`，按 category_priority 轮转到当批的类 |
| watch | 每周 1 轮 | 巡检米其林 / 黑珍珠 / 高关注店，分批（每批约 12 家） |
| 荣誉专项 | 发布季加跑 | 黑珍珠（约 1 月）、米其林（约 4 月名单 + 年中更新） |

每批采集后自动 `events_build` 转换 + 入库。

### 7.3 保鲜周期

新店 **30** 天 / 高端店 **180** 天 / 平价连锁 **90** 天（字段 `freshness_due`、`last_listened_at`）。

### 7.4 cadence 可自控

设置项 `feed_cadence`（每日 / 每周）控制 sweep 批次频率；默认每日。

### 7.5 状态联动

- `closed / relocated / chef_changed / award` 等**事实事件**入库后，应联动更新 `restaurants`（status / closed_date / closed_source）、`restaurant_chefs`、`restaurant_awards`：高置信半自动、其余人工确认。
- 限时类事件（popup / collaboration / guest_kitchen / menu_update）只展示、不改营业状态。

---

## 8. 代码清单与一键命令

| 文件 | 作用 | 位置 |
|---|---|---|
| `listen_keywords.json` | 10 类事件 sweep / roots / negative / 默认窗口 + 餐饮域词表 | `research/social/` |
| `events_collect.py` | 采集器：`run_sweep` / `run_watch` / `run_batch` | PIPE |
| `events_build.py` | 转换器（§4 九道机制） | PIPE |
| `atlas_write.py` | 幂等写库（events / reviews / chefs / awards） | PIPE |
| `raw_events_collected.jsonl` | 采集原始落盘（append，断点） | `research/social/` |
| `raw_events.jsonl` | 转换输出 | `research/social/` |
| `new_shops_unmatched.jsonl` | 未锚新店线索 | `research/social/` |

> PIPE = `~/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline`

**定时任务 cell 内一键（推荐）**：

```python
E.run_batch(bu, CONFIG, RAW, max_queries=8, commit=True)
```

**手动分步**：

```bash
# 1) cell 内采集（plane=bu）
E.run_sweep(bu, CONFIG, RAW, max_queries=8)
# 2) 转换
python3 events_build.py
# 3) 预演 / 写库
python3 atlas_write.py --domain events --input research/social/raw_events.jsonl
python3 atlas_write.py --domain events --input research/social/raw_events.jsonl --commit
```

---

## 9. 验证记录（2026-09-24）

- v2 小样本：4 个精准餐饮 query（客座主厨 / 餐厅快闪 / 餐厅联名菜单 / 新餐厅开业）→ 3 个有效 `popup` 事件（Yakido 上海限定预览、Burger & Lobster 两篇）；过期事件、合集、非餐饮噪声正确过滤。
- `atlas_write` dry-run = `event_new=3`（后续批次为 4）；机械闭环成立。
- `run_batch` 编排链路（采集 → build → write subprocess）验证通过。
- 上述事件**目前仅 dry-run，尚未 --commit**。

---

## 10. 待办 / 已知优化

1. **同源活动合并**：同品牌同活动、不同报道日期（如 Burger & Lobster 09-13 与 08-06 两篇）应合并为一个事件、多源升 high —— 扩展 `brand_registry` + agg key 弱化日期。
2. **主厨建档**：`chefs` / `restaurant_chefs` 仍为空，建档后 `chef_id` 才能锚定。
3. **前端首页 Feed 组件 + 七 tab**：读 `feed_view`，含点击进详情 / 地图。
4. **多平台采集适配**：公众号 / 视频号 / 抖音 / B 站，词根平移。
5. **`feed_cadence` 设置项与前端开关**（更新频率可自控）。
6. **事实事件 → 库状态联动**自动化。
7. 首批 3–4 个事件 `--commit` 并建立每日 sweep 定时任务。

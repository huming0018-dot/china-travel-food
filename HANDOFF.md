# HANDOFF・上海美食图鉴（china-travel-food）交接文档

> 版本：2026-09-26 ｜ 本文档目标：让另一个 AI bot 
>
> **仅凭本文档 + 代码**
>
>  即可审阅、复现、继续推进本项目。
> 所有命令均在本机（macOS）实测过；所有数字均为当日对 Supabase 现网实测拉取。
> **严禁**
>
> 在任何提交 / 截图 / 产物中出现明文密钥；本文档只写变量名与读取位置。



***

## ① 项目目标与最高原则

**一句话**：做一份「上海美食图鉴」—— 口味优先、只认真实食客堂食 UGC、对抗软广的餐厅榜单。



* **口味优先**：评分引擎以 `score_taste`（真实食客口味）为最高权重（0.35），不是平台人均 / 媒体榜单。

* **真实食客堂食 UGC**：只采信 `review_kind='diner'`、`is_fake_suspect=false`、`is_hidden=false` 的评价；外卖 / 媒体稿不计入口味分。

* **对抗软广**：中央厨房 / 预制菜 / 资本化连锁 → 自动派生 `soft_ad_flag` 并扣分（confirmed 扣 25 /suspected 扣 10）；非正餐（咖啡 / 面包 / 甜品 / Bar / 茶饮）豁免连锁供应链扣分。

* **宁空不假**：电话、坐标、营业时间宁可留空也不编；坐标宁空不猜（上海 bbox 硬约束）；关店三要素（status/closed\_date/closed\_source）齐。

* **淘汰软标记不物理删除**：关店店保留记录（status='closed'），不 DELETE；软广店降级不删库。

* **一条线做精再复用**：机制跑通后再扩品类；用户点名的店是**回归测试用例**，不是待补清单（漏店 = 机制有断点，修机制而非手补）。

* **榜单只收真正好吃的店**：候选池 = 全量发现 + 实测补充，≥2 条可溯源堂食评价、≥2 个独立渠道才入精选。



***

## ② 技术栈与整体架构



| 层        | 技术                                                                                                 | 位置                                                                            |
| -------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 前端       | Next.js 14.1 (Pages Router) + TypeScript + Tailwind + Leaflet/markercluster + @ducanh2912/next-pwa | `app/`                                                                        |
| 前端部署     | Vercel（GitHub push main 自动构建，**Root Directory 必须显式设为&#x20;**`app`）                                 | 生产：[https://app-lyart-eta-22.vercel.app](https://app-lyart-eta-22.vercel.app) |
| 数据库      | Supabase / PostgreSQL 17 + PostGIS，REST API（PostgREST）                                             | project ref `bdwrhshgdeghgyzwpxnl`                                            |
| 云端采集     | 腾讯云轻量服务器 `49.234.35.92`（Ubuntu，amd64），Docker 容器 `food-cloud`，cron 常驻                               | `cloud/`                                                                      |
| 反代 / 告警  | 告警走 Telegram Bot / 飞书自定义或应用机器人（国内服务器直连 TG 不通时填 `TELEGRAM_API_BASE` 反代）；容器内 `telegram_proxy/`       | `cloud/health.py`                                                             |
| 方法论 / 管线 | city-food-guide skill（SKILL.md + references/ + scripts/food\_pipeline/）                            | 见下方路径                                                                         |

**方法论 skill 路径**（不在本仓库内，是外部 skill）：



```
\~/.doubao/agent\_mode/workspace/.user\_skills/city-food-guide/

├── SKILL.md                 # 总 playbook（六步工作流 + 交付自检清单）

├── references/              # 23 份方法论文档（data-pipeline / scoring-rubric / discovery-playbook /

│                            #   cuisine-map / chain-premade-audit / lessons-learned 等）

├── scripts/food\_pipeline/   # 确定性管线脚本（stage1\~7 + 采集/分类/评分/补全）

└── templates/               # 新品类冷启动空白模板
```

本机展开路径：`/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/`

**ASCII 架构图**：



```
&#x20;                       ┌─────────────────────────────────────────────┐

&#x20;                       │              用户浏览器 (PWA)               │

&#x20;                       │   Next.js (app/, Vercel)  Leaflet 地图      │

&#x20;                       └───────────────┬─────────────────────────────┘

&#x20;                                       │ HTTPS · anon key · 只读 RLS

&#x20;                                       ▼

&#x20;       ┌───────────────────────────────────────────────────────────┐

&#x20;       │        Supabase Postgres + PostGIS (rest/v1)             │

&#x20;       │  restaurants / reviews / chefs / food\_events / cuisines  │

&#x20;       │  触发器：derive\_restaurant(算 tier/score\_total/soft\_ad)  │

&#x20;       │         trg\_reviews\_taste(口味分) trg\_awards\_endorse(背书)│

&#x20;       │  视图：v\_feed\_recent / restaurant\_detail\_view / feed\_view │

&#x20;       └───────▲───────────────────────────────▲───────────────────┘

&#x20;               │ service\_role key (写)          │ anon key (读)

&#x20;               │                                │

&#x20;  ┌────────────┴───────────┐         ┌────────┴─────────┐

&#x20;  │  本机管线 (skill/       │         │  /api/sync 心跳   │

&#x20;  │  scripts/food\_pipeline)│         │  (Vercel Cron 3am)│

&#x20;  │  stage0..7 确定性入库   │         └──────────────────┘

&#x20;  └────────────▲──────────┘

&#x20;               │ REST (common.req)

&#x20;               │

&#x20;  ┌────────────┴───────────────────────────────────────────────┐

&#x20;  │  腾讯云 49.234.35.92 · Docker 容器 food-cloud (cron 常驻)  │

&#x20;  │  每20min run\_batch.py → xhs\_collect(无头Chromium)          │

&#x20;  │    → xhs\_to\_reviews.py → atlas\_write.py --commit → Supabase│

&#x20;  │  另: phone\_fill(每20min错峰) / coord\_fill(每天3am)          │

&#x20;  │        / hours\_fill(每天4am)                                │

&#x20;  └─────────────────────────────────────────────────────────────┘
```



***

## ③ 目录结构与职责

整理后（2026-09-26）项目根：



```
china-travel-food/

├── app/                      # 【前端】Next.js Pages Router + PWA，Vercel Root Directory=app

│   ├── pages/                # \_app/\_document/index/map/login/auth-callback

│   │   ├── restaurants/index.tsx, \[id].tsx   # 列表页 / 详情页

│   │   └── api/sync.ts       # Vercel Cron 只读保鲜心跳（写 sync\_log，不改 status）

│   ├── components/           # ClusterGroup(地图聚合) / EventModal(事件弹窗) / FeedSection

│   ├── lib/                  # supabase.ts(client+类型) / auth.tsx / favorites.ts / geo.ts / format.ts

│   ├── public/ styles/ next.config.js(tailwind+PWA) vercel.json(Vercel Cron)

│   └── .env.local            # 前端+本地管线密钥（见⑦，不入库）

├── cloud/                    # 【云端采集】腾讯云 Docker 常驻服务

│   ├── Dockerfile docker-compose.yml entrypoint.sh crontab.txt build\_on\_server.sh deploy.sh

│   ├── run\_batch.py          # 一轮采集编排（断点续跑：采→转→入库）

│   ├── xhs\_collect.py 等     # 实际采集脚本在 vendor/pipeline（镜像内 /app/pipeline）

│   ├── cloud\_bu.py health.py# 无头浏览器封装 + 登录态探测/告警

│   ├── cloud\_phone\_fill.py / cloud\_coord\_fill.py / cloud\_hours\_fill.py  # 云端补齐

│   ├── vendor/pipeline/     # 管线快照（skill scripts/food\_pipeline 的拷贝，build 时 COPY）

│   ├── deploy.env(.template) # 云端环境变量（密钥，不入库）

│   └── xhs\_cookies.json      # 小红书登录态（只读挂载进容器，不入库）

├── db/migrations/            # 【DB Schema】001\_init → 010\_chef\_group\_hours\_events，按顺序在 SQL Editor 执行

├── research/                 # 【调研数据】atlas(小红书原始)/authority(米其林黑珍珠召回)/social/

│                            #   scene/scene\_v3/poi/private\_dining/regional/continents/design(设计文档)

│                            #   + 各菜系目录(川菜/粤菜/...) + 大量 \_\*.jsonl 过程稿（gitignored 工作区）

├── backups/                 # 【备份】写库前快照（restaurants/reviews/cuisines 等 JSON）

├── pipeline\_work/           # 【近期工作产物】如 recall\_20260926/（Ministry of Crab 召回）

├── archive/                 # 【本次整理】历史过程稿归档（audit-2026-09-22/23、coverage-tasks、cross\_cuisine\_report）

├── data/                    # 旧深度调研工作区（gitignored，体量大，可忽略）

├── scripts/                 # 空目录（旧飞书同步脚本已删，写库统一走 skill/scripts/food\_pipeline）

├── reviews\_priority.expanded.json   # 小红书采集优先级清单（1100 家，云端读取驱动采集顺序）

├── review-coverage-report-2026-09-26.md  # 最新采集/覆盖报告（保留在根）

├── audit-semantic-hours-2026-09-26.md    # 最新语义简介/营业时间审计（保留在根）

├── README.md DEPLOY.md       # 旧版说明（README 仍提"飞书表格"为历史残留，实际写库已走 food\_pipeline）

└── HANDOFF.md                # 本文档
```

**注意**：`research/` 下有大量 `_*.jsonl`、`_*.py`、`plan_*.json`、`write_b*.json` 等 9/23\~9/24 的过程稿，它们是管线分片产物，**保留不删**（属 gitignored 工作区，体量大但含证据链）；有效数据子目录为 `atlas/ authority/ social/ scene/ design/`。



***

## ④ 完整 DB Schema

> 现网实测行数（2026-09-26，service_role count=exact）：restaurants 
>
> **1519**
>
> 、reviews 
>
> **136**
>
> 、chefs 
>
> **56**
>
> 、restaurant_groups 
>
> **10**
>
> 、food_events 
>
> **25**
>
> 、cuisines 
>
> **332**
>
> 、restaurant_awards 
>
> **157**
>
> 。
> 注意：
>
> **没有独立的&#x20;**
>
> `sources`
>
> **&#x20;表**
>
> ——
>
> `sources`
>
>  是 
>
> `food_events`
>
>  上的 JSONB 列。
>
> `restaurant_cuisines`
>
>  / 
>
> `restaurant_chefs`
>
>  / 
>
> `restaurant_group_members`
>
>  是
>
> **复合主键、没有&#x20;**
>
> `id`
>
> **&#x20;列**
>
> 。

### 4.1 表清单



| 表                                                                           | 主键                               | 说明                                        |
| --------------------------------------------------------------------------- | -------------------------------- | ----------------------------------------- |
| `restaurants`                                                               | id SERIAL                        | 餐厅核心表（见下）                                 |
| `reviews`                                                                   | id UUID                          | 食客点评（只计堂食）                                |
| `cuisines`                                                                  | id SERIAL                        | 三维分类字典（菜系 / 食材 / 形式 / 标签 / 时段 / 认证）       |
| `restaurant_cuisines`                                                       | (restaurant\_id, cuisine\_id)    | 餐厅↔分类多对多，**无 id 列**                       |
| `chefs`                                                                     | id SERIAL                        | 主厨档案                                      |
| `restaurant_chefs`                                                          | (restaurant\_id, chef\_id, role) | 餐厅↔主厨任职关系                                 |
| `restaurant_awards`                                                         | id SERIAL                        | 米其林 / 黑珍珠等荣誉                              |
| `food_events`                                                               | id SERIAL                        | 动态 feed（新开店 / 搬迁 / 主厨更替 / 快闪…）            |
| `restaurant_groups`                                                         | id SERIAL (UNIQUE name)          | 餐饮集团 / 品牌矩阵                               |
| `restaurant_group_members`                                                  | (group\_id, restaurant\_id)      | 集团↔餐厅                                     |
| `price_band_thresholds`                                                     | (scene, band)                    | 各价格场景 5 带固定数值边界                           |
| `negotiations` / `price_benchmarks` / `sync_log` / `profiles` / `favorites` | —                                | 001 建的议价 / 价格锚点 / 同步心跳 / 用户 / 收藏（当前业务量很小） |

### 4.2 `restaurants` 关键字段与枚举



```
id, name, name\_en, aliases(text\[])

price\_avg(int), price\_range, tier(派生), business\_area(商圈), address, district

location GEOGRAPHY(POINT,4326)   -- PostGIS 坐标；REST 读写用 lng/lat，见 upsert\_restaurant RPC

phone, booking\_method, signature\_dishes JSONB\[]

\-- 反软广 / 工业化

chain\_type        TEXT  CHECK IN ('独立店','小型连锁','大型连锁','资本化连锁')

central\_kitchen   TEXT  CHECK IN ('无','疑似','确认')

premade\_risk      TEXT  CHECK IN ('无','低','疑似','高')

price\_position    TEXT  CHECK IN ('入门','主流','进阶','高端','旗舰')   -- 已停用，前端不再展示

price\_scene       TEXT  -- 正餐/快餐小吃/酒吧/咖啡茶饮/面包/甜品（管线回填）

price\_band        INT   CHECK 1..5（按 price\_band\_thresholds 由 price\_avg+scene 算）

is\_chain\_standardized BOOLEAN GENERATED ALWAYS (008，前端隐藏连锁/角标依据)

soft\_ad\_flag / soft\_ad\_flag\_reviews TEXT CHECK IN ('none','suspected','confirmed')

soft\_ad\_penalty   NUMERIC 0..30（派生：confirmed=25/suspected=10/none=0，禁止手填）

\-- 评分（四项 0..100）

score\_objective, score\_diner, score\_taste, score\_endorsement, score\_total(派生)

review\_count INT, review\_confidence NUMERIC(4,3) 0..1（口味贝叶斯置信度）

\-- 状态

status TEXT CHECK IN ('active','closed') DEFAULT 'active'

closed\_date, closed\_source  -- closed 时必填（ch\_rest\_closed\_triple）

\-- 010 新增

opening\_hours JSONB, open\_days TEXT, semantic\_description TEXT, chef\_name TEXT(反范式冗余)

selling\_points JSONB, last\_listened\_at, freshness\_due, taste\_prior\_source

data\_updated\_at DATE, created\_at, updated\_at
```

`tier` 派生规则（`tier_for_price`）：`<50 经济 / <100 平价 / <200 中档 / <500 高档 / else 奢华`。

### 4.3 关键约束（CHECK / 派生）



* `ch_rest_score_complete`：四项评分（objective/diner/taste/endorsement）**要么全有、要么全空**（NOT VALID，只拦新增 / 更新）。

* `ch_rest_coord_shanghai`：坐标要么空，要么 SRID=4326 且 `lng ∈ [120.80,122.20]`、`lat ∈ [30.65,31.95]`（上海 bbox）。

* `ch_rest_closed_triple`：status='closed' 必须同时有 closed\_date + closed\_source。

* `ch_rest_status`：只能 `active`/`closed`（前端勿用旧值 "推荐"）。

* `uq_rest_name_addr`：同名 (norm\_shop\_name)+ 同址 (norm\_addr) 唯一，仅约束有地址的店。

* `search_vector`：GENERATED ALWAYS tsvector（店名 / 英文名 A 权重、商圈 / 行政区 B、地址 C），数据库强制维护。

* `is_chain_standardized`：GENERATED STORED（008）。

### 4.4 触发器与派生（写库时数据库自动算，**勿手填**）



* `trg_restaurants_derive` (BEFORE INSERT/UPDATE) → `derive_restaurant()`：


  * `tier` 由 price\_avg 算；

  * `soft_ad_flag = greatest(chain硬信号, soft_ad_flag_reviews)`（非正餐豁免连锁扣分）；

  * `soft_ad_penalty` 由 flag 派生；

  * `score_total = round(0.35·score_taste + 0.25·score_objective + 0.25·score_diner + 0.15·score_endorsement − soft_ad_penalty, 1)`**，clamp\[0,100]**。

    （注：早期 002 文档写的是 0.4/0.3/0.2/0.1，已被 005 升级为 taste 核心的 0.35/0.25/0.25/0.15，以现网触发器为准。）

* `trg_reviews_taste` (AFTER reviews 增改删) → `recalc_taste_for(restaurant_id)`：口味分 = 时间衰减 (半衰期 180 天) + 贝叶斯收缩到**品类先验**(`cuisine_prior`，m=8)，只算 diner / 非软广 / 未隐藏评价；同时回写 `review_count`、`review_confidence`。

* `trg_awards_endorsement` (AFTER restaurant\_awards) → `recalc_endorsement_for`：背书分由荣誉派生（米其林三星 100 / 二星 90 / 一星 80，黑珍珠三钻 90 / 二钻 75 / 一钻 60，必比登 65，媒体 50，其他 40）。

### 4.5 RPC（幂等写入口，service\_role 专属）



* `upsert_restaurant(p jsonb)`：传 `{name, address, lng, lat, price_avg, ...}`，内部按归一名称 + 地址查存在则 UPDATE 否则 INSERT，所有触发器 / 约束生效。REST 端用 `POST /restaurants` 也可，但推荐 RPC。

* `recalc_taste_all()` / `recalc_endorsement_all()`：全库重算。

### 4.6 视图（前端只读）



* `v_feed_recent` / `feed_view`：首页动态 feed（event\_date 倒序，含 restaurant\_name/chef\_name）。

* `restaurant_detail_view`：详情聚合（cuisine\_arr/form\_arr/ingredient\_arr/awards/chefs/recent\_reviews）。

* `v_restaurant_enriched`：lng/lat + 菜系数组 + ugc\_count/ugc\_avg。

* `v_tag_coverage`：每标签挂店数（含 0 店漏挂）。

* `v_audit_gaps` / `v_data_freshness`：**仅 service\_role**（不向前端暴露缺口），stage4 体检用。

### 4.7 关键枚举速查



* `food_events.scope`: local/overseas/industry ｜ `category`: new\_open/relocated/closed/chef\_changed/guest\_kitchen/collaboration/popup/award/menu\_update/coming\_soon ｜ `confidence`: high/mid/low ｜ `status`: verified/rumor

* `reviews.review_kind`: diner/takeaway/press ｜ `trust_level`: high/mid/low

* `restaurant_awards.award_type`: michelin\_star/bib\_gourmand/black\_pearl/media\_show/other\_list

* `cuisines.dimension`: 菜系 / 食材 / 形式 / 标签 / 时段 / 认证



***

## ⑤ 数据管线全流程

**铁律：任何写数据任务禁止绕过脚本手拼 REST，必须走 skill 里的&#x20;**`scripts/food_pipeline/`**。** 模型只做 "发现 + 判断"，产出符合 `raw_place.schema.json` 的证据 JSONL；机械环节全部脚本化。

### 5.1 建库主流程（stage0 → stage7）



| stage | 脚本                         | 职责                                                |
| ----- | -------------------------- | ------------------------------------------------- |
| 0     | （人工 / 网格）                  | 把菜系拆成「细分叶子 × 档位」网格，每格定配额（中餐 = 地域子流派 × 品类双轴）       |
| 1     | `stage1_validate.py`       | 入库质量门：不合格打回                                       |
| 2     | `stage2_prepare.py`        | 实体对齐 / 标签解析 / 地理编码（dry-run 默认）                    |
| 3     | `stage3_upsert.py`         | 幂等写库 + 回读（默认 dry-run，`--commit` 才写）               |
| 4     | `stage4_audit.py`          | 全库只读体检 / 保鲜（查单店字段 / 硬伤）                           |
| 5     | `stage5_recalc.py`         | score\_total 漂移检测（total 现由 DB 触发器算，只读比对）          |
| 6     | `stage6_coverage.py`       | 网格覆盖审计（空格 / 薄格 / 薄证据 → coverage\_tasks.json 驱动回采） |
| 7     | `stage7_price_position.py` | 价格分位回扫（后被 009 price\_band 取代）                     |

### 5.2 小红书采集闭环（云端常驻）



```
reviews\_priority.json(1100家)

&#x20; → run\_batch.py（每20min，BATCH=15，flock 断点续跑）

&#x20;   → xhs\_collect.py（无头 Chromium + cookie 登录态，逐家采笔记）

&#x20;     → 落盘 research/atlas/xhs/raw\_xhs.jsonl

&#x20;   → xhs\_to\_reviews.py（全量重算 raw\_reviews；无口味信号词不打分）

&#x20;   → atlas\_write.py --domain reviews --commit（幂等入 reviews 表）

&#x20;     → DB 触发器 trg\_reviews\_taste 自动重算 score\_taste / review\_count
```

登录态失效时 `health.check_login` 探测 → Telegram / 飞书告警 → 本轮跳过（不硬刷）。

### 5.3 权威召回闭环



* `authority_sitemap.py`：拉米其林 sitemap 全量索引，与官方总数对账，产出 missing 清单。

* `authority_compare.py`：missing 店强制 "详情取证→够门槛入库"；近名异店排除、同名异址分店保留。

### 5.4 分类与补全脚本（skill/scripts/food\_pipeline/）



* `private_kitchen_detector.py`：会所 vs 私房菜拆分（010）。

* `signature_dish_classifier.py`：招牌菜分类。

* `semantic_profile_generator.py`：语义简介（菜系 + 商圈 + 荣誉 + 主厨 + 招牌菜 + 人均，已全库 1519/1519）。

* `opening_hours_collector.py`：从 evidence\_summary 正则提取营业时间（当前 69/1519）。

* `chef_tracker.py` / `build_chefs.py` / `finish_chefs.py`：主厨建档。

* `events_build.py` / `events_collect.py`：food\_events feed。

* `price_band_assign.py`：按 009 阈值表回填 price\_scene/price\_band。

* `nondiner_main.py`：非正餐识别（豁免连锁扣分）。

* `release_audit.py`：发版前只读串联各质量门。



***

## ⑥ 部署命令

### 6.1 前端（本地开发）



```
cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/app"

npm install        # node\_modules 已在，359M

npm run dev        # http://localhost:3000
```

### 6.2 前端（生产部署）



```
\# 本地推送 main，Vercel 自动构建（Root Directory 已设为 app）

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"

git add -A && git commit -m "..." && git push origin main

\# 验收：Vercel 最新部署状态为 Ready；生产 https://app-lyart-eta-22.vercel.app
```

Vercel 环境变量需配 `NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY`、`CRON_SECRET`（/api/sync 鉴权用）。`SUPABASE_SERVICE_ROLE_KEY` 也在 Vercel 配（/api/sync 心跳用）。

### 6.3 云端采集容器（**必须在服务器原生 amd64 构建**）



```
\# 一键脚本（本机执行，自动打包上传 + ssh 到服务器 build + compose up）

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/cloud"

./build\_on\_server.sh
```

等价手动步骤（**勿在本机 arm64 build，勿用&#x20;**`docker compose build`）：



```
\# 1) 上传 cloud/ 上下文到服务器（含 vendor/pipeline、deploy.env、xhs\_cookies.json）

\# 2) ssh 到服务器：

ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92

cd /home/ubuntu/food-cloud

sudo docker build -t food-cloud:local .      # ★ 服务器原生 amd64 build

sudo docker compose up -d

sudo docker compose ps                        # 验证 food-cloud Up
```

服务器 SSH：`ubuntu@49.234.35.92`，私钥 `~/.ssh/food_cloud_deploy`，部署目录 `/home/ubuntu/food-cloud`。

### 6.4 云端 cron（容器内 `/app/cloud/crontab.txt`，entrypoint.sh 安装）



```
\*/20 \* \* \* \*  run\_batch.py          >> /app/data/cron.log        (小红书采集，flock /tmp/xhs.lock)

5,25,45 \* \* \* \* cloud\_phone\_fill.py >> /app/data/phone\_fill.log (电话补齐，错峰5min)

0 3 \* \* \*    cloud\_coord\_fill.py    >> /app/data/coord\_fill.log (坐标补齐，每日)

0 4 \* \* \*    cloud\_hours\_fill.py    >> /app/data/hours\_fill.log (营业时间补齐，每日)

15,35,55 \* \* \* cloud\_amap\_fill.py --apply >> /app/data/amap\_fill.log (高德全字段，取代旧 review\_fill)
```

全部 `. /app/cloud/env.sh`（cron 不继承 docker -e，由 entrypoint.sh 固化）+ `flock -n` 防重叠。

### 6.5 数据库迁移



```
\# Supabase Dashboard → SQL Editor → 按文件名顺序粘贴执行（幂等可重跑）

db/migrations/001\_init.sql

db/migrations/002\_harden.sql

... 依次到 ...

db/migrations/010\_chef\_group\_hours\_events.sql

\# DDL 无法走 REST，只能 SQL Editor。
```



***

## ⑦ 环境变量清单与凭据位置

> **严禁明文 token/secret/service role**
>
> 。下表只列变量名与读取位置。



| 变量名                                                                                                               | 用途                                          | 读取位置                             |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | -------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`                                                                                        | Supabase 项目 URL                             | `app/.env.local`（前端 + 本地管线共用）    |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`                                                                                   | 前端公开 anon key                               | `app/.env.local`                 |
| `SUPABASE_SERVICE_ROLE_KEY`                                                                                       | 服务端写库密钥（绕过 RLS）                             | `app/.env.local`；云端 `deploy.env` |
| `FOOD_APP_DIR`                                                                                                    | 覆盖默认 app 目录（common.py 找 .env.local）         | 本地可选，默认仓库 app/                   |
| `XHS_COOKIE_FILE`                                                                                                 | 小红书登录态文件路径（容器内 `/secrets/xhs_cookies.json`） | 云端 `deploy.env`                  |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `TELEGRAM_API_BASE`                                                   | cookie 失效 / 任务完成告警                          | 云端 `deploy.env`                  |
| `FEISHU_WEBHOOK` / `FEISHU_SECRET` / `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_CHAT_ID` / `FEISHU_API_BASE` | 飞书机器人告警                                     | 云端 `deploy.env`                  |
| `ALERT_WEBHOOK` / `ALERT_COOLDOWN_SEC`                                                                            | Bark/Server 酱兜底告警、冷却                        | 云端 `deploy.env`                  |
| `BATCH`                                                                                                           | 每轮采集店数（默认 15，从10提速）                      | 云端 `deploy.env` / compose        |
| `AMAP_KEY`                                                                                                        | 高德 Web 服务 key（全字段采集，无 SK/sig）             | 云端 `deploy.env`                  |
| `CRON_SECRET`                                                                                                     | Vercel /api/sync 心跳鉴权                       | Vercel 环境变量                      |

**凭据文件位置**：



* 本地前端 + 管线：`app/.env.local`（3 个 Supabase key）。根目录 `.env.local` 是 Vercel CLI 的 OIDC token，与管线无关。

* 云端：容器内 `/app/cloud/env.sh`（entrypoint.sh 从环境变量固化生成，cron source 它）；构建期 `cloud/deploy.env`（compose `env_file`）；小红书 cookie 只读挂载 `/secrets/xhs_cookies.json`（宿主机 `cloud/xhs_cookies.json`）。

* 模板：`app/.env.local.example`、`cloud/deploy.env.template`。

`.gitignore`**&#x20;应包含**（现状已含）：`node_modules/`、`.next/`、`.env*.local`、`.env`、`.vercel/`、`*.tsbuildinfo`、`app/public/sw.js`+workbox-\*.js、`__pycache__/`、`.venv/`、`/backups/`、`/data/`、`/pipeline_work/`、`/data_subagent_work/`、`/geocode_progress/`、历史一次性 `build_*.py`/`push_*.py`、`*.bak`。



***

## ⑧ 当前进度、关键数字与已知缺口（2026-09-26 实测）

**规模**：餐厅 **1521**（active 1514 / closed 7）、reviews **136** 条、主厨 **56** 位、餐饮集团 **10** 个、food\_events **25** 条、cuisines 标签 **346**、restaurant\_awards **157** 条。

**最大短板 —— 评价覆盖**：



* `review_count=0` 的店约 **1459 家**（1519 中仅 60 家有评价），云端小红书采集推进中。

* 云端已采 **614/1100**（优先级清单 `reviews_priority.expanded.json`），BATCH 从 10 提至 **15**（300031 零触发后提速 50%），剩余约 486 家待采。

* 高端 / 奢华店（price\_band 4-5 共 404 家）几乎 0 评价；欧洲菜 / 湘菜 / 闽菜 / 融合菜是空白区。

* **新来源（2026-09-26 P0-1，已升级见⑧.8）**：
  * 旧 `cloud_review_fill.py`（只补评分、错误 sig）**已被 `cloud_amap_fill.py` 取代**（cron 第5条，:15/:35/:55）：一次高德 place/text extensions=all 同时回填评分/人均/电话/营业时间/坐标，地址锚定锁定正确分店；AMAP_KEY 已配、端到端写库验证通过。
  * 腾讯位置服务 WebService API **不返回评论文本/评分**（已实测：search/detail 仅返回 POI 基本字段），不可用于评价采集。
  * 大众点评强反爬 + 登录墙，REST 不可行；需登录态 RPA 时 blocked=auth 再找用户。

* **visit_date 已接入**：`xhs_to_reviews.py` 现解析笔记日期写入 `visit_date`，DB 触发器 trg\_reviews\_taste 时间衰减（半衰期180天）据此回算。新增评价自动带 visit_date；历史 136 条不回溯。

**字段完整率**（来自 audit-semantic-hours-2026-09-26）：



* ✅ name/address/district/signature\_dishes/price\_avg/tier/semantic\_description(100%, 1521/1521)

* ⚠️ 坐标 99.7%（6 家无坐标：id=1854,1939 待核实；1985-1988 已于本轮用腾讯 place suggestion 补齐）

* ⚠️ 电话 67.0%（约 502 家无电话，云端 `cloud_phone_fill.py` 每小时 :05/:25/:45 补，腾讯 place suggestion 精确锁定分店）

* ⚠️ 营业时间仅 69 家（4.5%，云端 `cloud_hours_fill.py` 每日补）

* ⚠️ chef\_name 反范式列空（restaurant\_chefs 有 56 位主厨但未回写冗余列）

* ✅ 评分四项 99.8%（3 家无评分）

**分类与收录**：



* 会所 3 家 / 私房菜 14 家已拆分；裕莲茶楼分类已修正。

* **Ministry of Crab 已入库（id=2002）**，评分 82.3，地址 / 电话 / 坐标 / 招牌菜 / 语义简介齐全，仅营业时间待补。

* **EIGHT UNDER（rid=1905）已确认为用户说的「八by8/8byeight」**：徐汇区永康路73号，主厨 Gabo，Chifané 跨文化创意菜（麻酱油泼辣子意面、鸭cannelloni担担酱），aliases 已补 ["八eight","EIGHT","8by8","八by8"]，融合菜/私房菜标签齐全。

* 米其林 0 缺失（sitemap 对账闭环）；黑珍珠 7 家证据不足待补。

**其他**：`score_taste` 对单条评价做了贝叶斯收缩（n=1 的 5 星不给 100，给～80）；软广事后扫描 21 条命中经人工复核无一例确证，`is_fake_suspect=0`。大众点评未接入（强反爬 + 登录墙，REST 不可行；需登录态 RPA 时 blocked=auth 再找用户）。高德评分采集脚本 cloud_review_fill.py 已就位，待配置 AMAP_KEY/AMAP_SK 后自动启动。

### ⑧.5 负面清单三字段跑全（2026-09-26 P0-3，已完成）

`chain_type / central_kitchen / premade_risk` 三字段**非 NULL 率 100%（1519/1519）**。枚举以库 CHECK 约束为准（非任务书里的"直营/加盟/有/中"字样，那些是示意）：

```
chain_type      : 独立店 1242(81.8%) / 小型连锁 209(13.8%) / 大型连锁 61(4.0%) / 资本化连锁 7(0.5%)
central_kitchen : 无 1308(86.1%) / 疑似 185(12.2%) / 确认 26(1.7%)
premade_risk    : 无 1308(86.1%) / 低 171(11.3%) / 疑似 17(1.1%) / 高 23(1.5%)
is_chain_standardized(派生): true 210 / false 1309   ← 前端"隐藏连锁/预制"开关过滤的就是 true 且非正餐的店
```

**做法**：
- 批量：1231 家 `chain_type=独立店 且 ck/pr 均 NULL` 一次过滤 PATCH 为 `ck=无, pr=无`（独立小店无中央厨房无预制，`is_chain_standardized` 仍为 false，不被隐藏）。
- 人工：21 个 chain_type=NULL（7 关店 + 14 家 id≥1989 新店）+ 3 个 pr=低 异常独立店，逐家看 evidence_summary 判定，共 24 条 PATCH。
- 写前备份：`backups/negative_fill_2026-09-26/restaurants_3fields_before.json`（1519 行）。
- 脚本：`food_pipeline/fill_negative_fields.py`（dry-run / `--commit`，只 PATCH 这三列）。

**用户点名店（已全部正确标记，std=true 可被隐藏）**：小菜园=资本化连锁/确认/高；望湘园=大型连锁/确认/高；盖饭邦=大型连锁/确认/高；FAT PHO 大發越南粉=小型连锁/疑似/低；西贡妈妈 Saigon Mama=小型连锁/疑似/低。

**前端"隐藏连锁/预制"端到端验证（线上实测）**：`app/pages/restaurants/index.tsx` L310 `if(hideChain) result=result.filter(r=>!r.is_chain_standardized||isNonDiner(r))`，取数 `select='*'` 含派生列，逻辑正确、无需改码部署。线上 https://app-lyart-eta-22.vercel.app/restaurants 实测：搜"小菜园"默认显示 2 家（带"预制菜/连锁"角标）→ 点"隐藏连锁/预制"→ 0 家"没有找到"；关闭后御宝轩/Da Vittorio/8½ Otto 等独立高端店正常保留。非正餐（咖啡/面包/甜品/Bar/茶饮）即使连锁也被 `isNonDiner` 豁免不隐藏。

**已知缺口/保守判定**：
- 14 家 id≥1989 新店中，横县鱼生连锁（渔八公/粤桂發）、胡老头鱼丸、少山集/隐溪/黄庭茶馆 按"现做/茶饮、无中央厨房"标 `小型/大型连锁 + ck=无 + pr=无`，故 `is_chain_standardized=false` 不被隐藏——这是有意为之（现做多店、茶饮业态），非漏标。
- 高端餐饮集团（新荣记/甬府/大董/鲁采等）多店但 ck=无/pr=无，std=false 保留入精选。
- 24 家人工判定里关店 7 家的连锁分级仅为补齐枚举，不影响线上（status=closed 本就不展示）。



### ⑧.6 方法论回滚·八大菜系（2026-09-26 P0-2，第一批完成）

**核心机制修复：第二轴（品类/店型）叶子从 0 到 14**

此前八大菜系只有地域子流派叶子，火锅/串串/冒菜/小面/早茶/烧腊等店型完全没有独立叶子。本批新建 14 个 dimension=菜系 的第二轴叶子（id 355-368，355重庆火锅此前已存在）：

| 叶子 | 归属 | 现挂店数 |
|---|---|---|
| 重庆火锅(355) | 川菜 | 5 |
| 串串香/冷锅串(356) | 川菜 | 5 |
| 冒菜/麻辣烫(357) | 川菜 | 2 |
| 川味面馆(358) | 川菜 | 12 |
| 烤鱼/酸菜鱼专门(359) | 川菜 | 8 |
| 广式早茶点心(360) | 粤菜 | 4 |
| 潮汕牛肉火锅(361) | 粤菜 | 8 |
| 潮汕打冷/生腌排档(362) | 粤菜 | 5 |
| 砂锅粥/粿条(363) | 粤菜 | 4 |
| 苏式汤面(364) | 苏菜 | 7 |
| 淮扬茶社/细点(365) | 苏菜 | 5 |
| 胶东海饺/面点(366) | 鲁菜 | 13 |
| 闽菜Fine Dining(367) | 闽菜 | 9 |
| 湖南米粉(368) | 湘菜 | 8 |

**现有店回挂 93 条** `restaurant_cuisines`（手工 curated，只挂主营店型明确的专门店，避免正则过度触发把高端粤菜馆误标烧腊）。备份 `backups/second_axis_leaves_before.json`。

**新增店 2 家（走完整管线 stage1→stage2→stage3）**：
- 蜀南面馆（rid=2003，闵行莘沥路39-43号，宜宾燃面，《孤独的美食家》五郎打卡，川南·宜宾菜+川味面馆）
- 觉味燃面（rid=2004，浦东商城路2000号，开了15年的宜宾苍蝇馆子，川南·宜宾菜+川味面馆）
两家坐标已用腾讯 place suggestion 补齐，评分四项齐全。

**stage6 覆盖审计结果**：active 1514 家，**空格 0**，薄格 10（川菜5：冒菜/海派改良/内江/泸州/绵阳；浙菜1：金华衢州；闽菜1：闽北；广西1：桂林米粉；河南1：开封洛阳；创新菜1），深采任务 10 项。川菜叶子从 11 增至 16，川南·宜宾菜从 2 家增至 4 家。

**回归用例核验**：鸟鸟(id=1434)✓、张记川味苑(id=601,已挂川南·宜宾菜)✓、帅帅(id=1892)✓、聪菜馆(id=1843)✓、nagi凪(id=1887)✓。鮨照/Proustmoment/time&flour 属日料/面包批，留待下一批。

**教训**：正则自动挂标签会过度触发（云南火锅/台湾牛肉面/上海面馆被误收），必须手工 curated 主营店型；stage1_validate.py 全库实体匹配可能超时，需加 watchdog 超时保护。

### ⑧.7 模糊召回/口述逼近层（2026-09-26，机制新增）

已写入 `references/discovery-playbook.md` §7（v2.2），解决"精确关键词=0就放弃"的缺陷：
- **店名归一扩展**：数字↔英文↔中文互转（8↔eight↔八）、去连接符、分店名剥离、中英文混排、口述变体
- **召回=0时的模糊扩展流程**：归一扩展→叠加地标→叠加主厨/形态→UGC评论区反查→待核实标注
- **候选多信号排序**：店名30%+地址25%+主厨20%+菜系15%+热度10%，阈值<0.6不确认
- **库内别名联动**：`restaurants.aliases` JSONB 数组存储口述名，检索时匹配 name+name_en+aliases
- 触发案例：用户说"8by8"→库内 EIGHT UNDER(rid=1905)，aliases 已补全

### ⑧.8 高德统一全字段采集（2026-09-26，已部署，取代旧 cloud_review_fill）

**一次 place/text（extensions=all）同时回填 评分+人均+电话+营业时间+坐标**，替代此前腾讯/高德分散、旧 cloud_review_fill 带错误 sig、只补评分的方案。脚本 `cloud/cloud_amap_fill.py`（容器 /app/cloud）。

**店名↔POI 匹配引擎（地址锚定优先，宁 hold 不错配）**：
- `amap_text`：返回全部 POI 不预过滤（地名/非餐饮在 match 阶段排除）；限流指数退避，infocode 10003=日配额(5000)超限立即停并告警；间隔≥0.4s。
- `is_dining_poi`：以高德 keytag 语义为主（不硬编码 typecode 大类，因 08 含酒吧/部分蛋糕）；地名 POI 硬排除。
- `split_name/core_norm`：拆主名+括号、跨字形归一、ramen=拉面、近形（膳/善）。
- **地址锚定（核心）**：库有具体地址/地标或锁分店时，候选必须地址/分店/地标一致（confirm≥0.9）：
  - `road_number`：先去开头行政区（含"区"），枚举路名，对门牌号取前方间隙≤4 且不跨越"路/街/道"的最近路名（治"江苏路街道凯旋路1398"误锚江苏路）。
  - `addr_anchor`：同路名 + 门牌号交集/号段范围重叠（189-193 vs 191-193）/原始 sim≥0.8 → confirmed≥0.9；路名不同（错分店）→ 排除。
  - 强确认(0.95)时店名 ratio 放宽到 0.4（治"拉面满吉/满吉拉面"语序相反）；否则 ratio≥0.55。
  - 地标 LANDMARKS（龙之梦/来福士/恒隆/合生汇…）；库只有泛区域（"古北地区"）靠主名+业态，泛品牌不采。
- 只补空：price_avg（tier 触发器算）、phone（过 clean_phone）、opening_hours({raw})、location(point_ewkt+in_shanghai)；评分→reviews（高德地图, trust_level=low）；keytag/tag 仅线索不改菜系。
- 当天 POI 缓存（rid+日期）+ 断点 + 配额计数；默认 dry-run，`--apply`/`--limit`。

**实测（正确分店，无一错配）**：御千代(rid4)→诺雅 凯旋路1398长宁国际T8（非信联公寓）；酉町(rid8)→番禺路390；满吉(rid20)→广元西路（非前滩晶耀）；小景门(rid10)→招商局广场；晚餐馆(rid16)→古北金狮花园；天天天妇罗(rid36)→五角场合生汇；天嘉(rid37)→虹梅路3194；一滨(rid45)→世博天地。rid1939 北外滩私宴（地址"预约后告知"）正确 hold、不锚地名。

**部署**：AMAP_KEY 已写入云端 deploy.env（env_file 传入、env.sh 固化）；Dockerfile COPY 加 cloud_amap_fill.py；crontab 第5条由 cloud_review_fill 改为 `cloud_amap_fill.py --apply`（:15/:35/:55，flock /tmp/amap_fill.lock）。容器 dry-run 与 `--apply --limit 10` 均实测通过、字段落库。全库缺营业时间(~1445)/电话(~499) 在 5000/天配额内 1 天左右补全。


***

## ⑨ 一键复现步骤



```
\# 0) clone 仓库后进入

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food"

\# 1) 装前端依赖

cd app && npm install

\# 2) 配置密钥：复制模板填真实值

cp .env.local.example .env.local

\#   编辑 .env.local 填入 NEXT\_PUBLIC\_SUPABASE\_URL / NEXT\_PUBLIC\_SUPABASE\_ANON\_KEY / SUPABASE\_SERVICE\_ROLE\_KEY

\# 3) 本地跑前端

npm run dev          # http://localhost:3000

\# 4) 连接数据库验证（用 skill 共享层，已实测可跑）

SKILL="/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent\_mode/workspace/.user\_skills/city-food-guide"

python3 -c "

import sys; sys.path.insert(0, '\$SKILL/scripts/food\_pipeline')

import common as C, requests

h=C.headers(); h\['Prefer']='count=exact'

for t in \['restaurants','reviews','chefs','food\_events','cuisines']:

&#x20;   r=requests.get(f'{C.BASE}/{t}', params={'select':'id','limit':1}, headers=h, timeout=30)

&#x20;   print(t, r.headers.get('content-range'))

"

\# 预期输出：restaurants 0-0/1519、reviews 0-0/136、chefs 0-0/56、food\_events 0-0/25、cuisines 0-0/332

\# 5) 继续采集：确认云端容器在跑（cron 自动推进，无需本机干预）

ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92 \\

&#x20; "sudo docker compose ps && tail -5 /home/ubuntu/food-cloud/data/cron.log"

\# 6) 补齐数据：云端 cron 已自动跑 phone/coord/hours fill；本机可手动跑 stage 审计

cd "\$SKILL/scripts/food\_pipeline" && python3 stage4\_audit.py        # 只读体检

cd "\$SKILL/scripts/food\_pipeline" && python3 stage6\_coverage.py    # 网格覆盖

\# 7) 前端部署：git push main → Vercel 自动构建

cd "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food" && git push origin main
```



***

## ⑩ 独立回验方法与 release regression 清单

### 10.1 数据回验（REST / SQL）



```
\-- 数量

SELECT count(\*) FROM restaurants;                       -- 1519

SELECT count(\*) FROM restaurants WHERE status='active'; -- \~1512

SELECT count(\*) FROM reviews;                           -- 136

\-- 维度覆盖缺口（service\_role 才能查）

SELECT issue, count(\*) FROM v\_audit\_gaps GROUP BY issue ORDER BY 2 DESC;

\-- 保鲜

SELECT count(\*) FROM v\_data\_freshness WHERE stale;

\-- 评分漂移（应为 0）

SELECT count(\*) FROM restaurants WHERE score\_total IS NOT NULL

&#x20; AND abs(score\_total - greatest(0,least(100,round(

&#x20;     0.35\*score\_taste+0.25\*score\_objective+0.25\*score\_diner+0.15\*score\_endorsement

&#x20;     -coalesce(soft\_ad\_penalty,0),1))))>0.1;

\-- 无坐标营业店（应为 6 家）

SELECT id,name FROM restaurants WHERE status='active' AND location IS NULL;
```

REST 速查：`GET /restaurants?select=id&limit=1` 看响应头 `content-range` 总数。

### 10.2 前端验收（以浏览器真实渲染为准，`next build` 通过不算完）



* 首页统计数字、根 / 二 / 三级菜系导航（**动态从 cuisines 表构建，无硬编码**）。

* 亮点标签筛选（米其林 / 黑珍珠 / Off Menu / 纯素 / 分子）。

* 列表页排序、价格带区间标签（price\_band\_thresholds）。

* 详情页：语义简介、营业时间、内嵌 Leaflet 地图（瓦片 + marker）、荣誉 / 主厨 / 最近评价。

* 地图页聚合（ClusterGroup）、Feed 事件 Modal（EventModal）。

* 改了前端先注销 PWA service worker + 清缓存再判断。

### 10.3 云端验收



```
ssh -i \~/.ssh/food\_cloud\_deploy ubuntu@49.234.35.92

sudo docker compose ps                       # food-cloud Up, restart=always

tail -20 /home/ubuntu/food-cloud/data/cron.log       # 采集进度

tail -5 /home/ubuntu/food-cloud/data/phone\_fill.log  # 电话补齐

docker exec food-cloud crontab -l            # 4 条 cron 在
```

### 10.4 release regression 通识清单（历次踩坑汇总，发版前逐条过）



1. **iCloud&#x20;**`.next`**&#x20;锁定**：`app/.next` 若为 iCloud dataless 占位目录，删除报 `EDEADLK/Resource deadlock avoided` 时**勿硬删**，等它落地或忽略（gitignored，不影响部署）。本次整理中 `__t_root`/`data_subagent_work`/`geocode_progress`/`cloud/__t_cloud`/`cloud/chunks` 即此类空占位目录，删不掉属正常，已在本档注明。

2. **PostgREST 204 / 空响应**：带错误 header 或 select 不存在列会 400；`Prefer: count=exact` 才返回总数。

3. `restaurant_cuisines`**&#x20;无&#x20;**`id`**&#x20;列**：复合主键 `(restaurant_id,cuisine_id)`，客户端拉取必须 `order=restaurant_id`，否则 400 且 `Promise.all` 整体 reject、整页静默归零。

4. **枚举值以库 CHECK 约束为准**：status 用 `active/closed`，勿用旧值 "推荐"；加载失败要让错误上浮，不渲染空壳。

5. **虚拟根 8 个**：中餐 / 亚洲 / 欧洲 / 非洲 / 北美洲 / 南美洲 / 融合菜 / 非正餐是虚拟根（cuisines 表无同名行），URL `?cuisine=` 定位、点根筛选、二三级展开都要先判虚拟根。

6. **坐标 EWKT/GeoJSON**：DB 存 `GEOGRAPHY(POINT,4326)`；写库走 `upsert_restaurant` 传 `lng/lat`（RPC 内部 `ST_SetSRID(ST_MakePoint(lng,lat),4326)`），勿手拼文本。

7. **评分四项全有或全无**：`ch_rest_score_complete` 约束；不完整时 `score_total` 自动为 NULL，不展示官方分。

8. **大表分页**：restaurant\_cuisines 约 1.4 万行，客户端分页十余页、首屏数秒属正常，勿误判死循环。

9. **PWA 残留**：曾因残留旧 workbox 致 build 失败；`app/public/sw.js` 等已 gitignore，每次构建重新生成。

10. **云端 build 必须服务器原生 amd64**：本机 arm64 构建跨架构跑不起来；用 `build_on_server.sh`，勿用 `docker compose build`。

11. **cookie 失效**：小红书 cookie 会过期，health 探测失效后告警并跳过，需人工重新导出 `xhs_cookies.json` 重新部署。

12. **写库不手填派生列**：tier/score\_total/soft\_ad\_flag/soft\_ad\_penalty/is\_chain\_standardized/review\_count/review\_confidence 全由触发器生成，手填会被覆盖或破坏一致性。

13. **compose 无 build 段**：docker-compose.yml 只写 `image: food-cloud:local`、无 `build:`，故 `docker compose build` 空操作、`up` 沿用旧镜像；更新代码必须显式 `sudo docker build -t food-cloud:local .` 再 `compose up -d`。



***

## 附：本次项目整理记录（2026-09-26）



* **整理前体积**：592M（其中 app/node\_modules 359M、app/.next 102M、.git 93M，均为 gitignored / 版本控制目录，未动）。

* **整理动作**：


  * 新建 `archive/`，移入 24 个根目录历史过程稿（audit-2026-09-22/23 共 10 份、coverage-\* 共 10 份、coverage-tasks\*.json 3 份、cross\_cuisine\_report.\* 4 份），共约 380K。

  * 根目录只保留最新两份报告（`review-coverage-report-2026-09-26.md`、`audit-semantic-hours-2026-09-26.md`）+ `reviews_priority.expanded.json` + README/DEPLOY。

  * 尝试删除空临时目录 `__t_root`、`data_subagent_work`、`geocode_progress`、`cloud/__t_cloud`、`cloud/chunks`，全部报 `EDEADLK (Resource deadlock avoided)`—— 系 iCloud dataless 占位空目录，**按约定不硬删，留空占位**。

  * `cloud/.venv`、`cloud/.venv312` 为空 venv 骨架（gitignored），保留。

  * `app/.next`（102M）为真实构建缓存（非 iCloud 占位，含 cache/server/static），gitignored，**保留不删**（删了会触发下次 `npm run build` 全量重建）。

  * `research/`、`data/`、`backups/`、`pipeline_work/` 为工作数据区，未动。

* **整理后体积**：仍为 592M（大头是 node\_modules/.next/.git，本就不该入库；过程稿仅 380K 移到 archive，净释放可忽略）。根目录文件从 20+ 个过程稿精简到 5 个根级 md/json + 配置。
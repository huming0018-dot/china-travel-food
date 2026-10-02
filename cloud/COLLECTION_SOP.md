# 采集通道 SOP（Collection SOP）

> 角色：collector（采集/CR，爬虫工程师 / 采集运维与效率负责人）。
> 上位契约：`north-star-constitution.md`（口味唯一最高、宁空不假、机制优先、信源沉淀、账号最后手段、闭环自检）。
> 本文件是「数据从哪来、能否稳定/完整/准确拿到、成本与封号风险」的权威操作手册；所有通道事实均经实测（2026-10-02，deuce）。
> 机制绑定见 `mechanism-master-v4.md`；发版质量门见 `release-regression-loop.md`。

---

## 1. 采集对象（数据宇宙）

按「菜系子流派 × 品类/店型 × 场景 × 食材垂直 × 形式」枚举叶子，叶子=可决策单元。每类数据对应固定字段族：

| 数据族 | 目标字段 | 主通道（见 §3） |
|---|---|---|
| F-A 宇宙/全集 | 目标分母、缺口、发现路径 | 地图 POI + 权威 sitemap + 集团/主厨树 + 社交发现 |
| F-B 店铺事实 | name/aliases、address、location、phone、opening_hours、price_avg、chain/group/chef 链接 | 地图 Web API（L0） |
| F-C 口味/评价 | reviews（aspect_taste、content、source_url、trust、verified_diner）、score_taste、review_count、review_confidence | 真实食客 UGC（L3 / Apify） |
| F-D 动向/事件 | 新店、关店/搬迁、主厨变动、飞行厨房、联名快闪、荣誉/通告 | 官方 + 社媒 + KOL（L0/L2） |
| F-E 分类/语义 | cuisine 叶、sub 标签、scene、ingredient、is/serves | 招牌菜联动 + 语义引擎（确定性） |

---

## 2. 通道分级总原则（降级阶梯，自上而下优先）

> 目标：**先耗尽免费/官方/匿名通道，付费只花在免费覆盖不到的店；能不用自己的登录账号就不用。**

| 级别 | 通道 | 鉴权 | 成本 | 封号风险（我方账号） |
|---|---|---|---|---|
| **L0** | 官方/公开 API：高德/腾讯地图 Web 服务、官方公众号/新闻稿、权威榜公开页 | key（地图）/ 无 | 免费（日配额） | 无 |
| **L1** | 匿名签名直连（xhshow 等） | 设备签名 | 免费 | 无（不登录） |
| **L2** | 网页只读（SmartShanghai/TimeOut 等媒体、B 站） | 无 / 轻 cookie | 免费 | 无–低 |
| **L3** | 登录账号 / 付费采集器（Apify actors） | 登录 cookie / 付费 | 登录=免费但封账号；Apify=按结果付费 | **自采登录=高；Apify=零（用 actor 的账号）** |

**核心结论（实测，回答"更省钱且不封号"）：**
1. **小红书/点评的"关键词搜索"没有免费稳定途径**：匿名搜索返回 `-101`；主流搜索引擎（Bing 实测 157 链接、0 条小红书）不收录小红书内容（小红书对搜索引擎 noindex + 登录/token 墙）。任何能给你小红书搜索结果的人（Apify actor）都在为账号/代理付费，这就是价格来源。
2. **多账号轮换注册薅 Apify 免费额度 = 违反 ToS、关联封号，已否决，永不采用。**
3. **去封号风险的关键**：把小红书访问全部交给 **Apify（跑在 actor 的账号上，我方账号零风险）**，**停用"我方登录账号自跑搜索"——唯一会封我们自己账号的做法**。
4. **去成本的关键**：先用 L0/L2 覆盖头部（地图聚合分 + 媒体/权威 + B 站），Apify 只对"免费覆盖不到的店"用 **atomus 按结果计费（0 结果=$0）**，把付费面压到最小。

---

## 3. 通道清单（逐项：能拿什么 / 成本 / 封号 / 节奏 / 模块 / 边界）

### L0 官方/公开（免费、无封号）

- **高德 Web 服务 `place/text extensions=all`**（模块 `cloud/cloud_amap_fill.py`，经 `map_quota` 池）
  - 一次返回：`biz_ext.rating`（**聚合星级**）、`biz_ext.cost`（人均）、`tel`、`biz_ext.opentime2/open_time`（营业时间）、`location`、`keytag`。
  - 只需 key、**不带 sig**；日配额约 5000/key；只补空字段、不覆盖非空。
  - **边界：只有聚合星级，没有点评正文。** 历史 921 条"高德评论"是用聚合分生成的低信任评价（`trust=low`、`is_verified_diner=False`、content="高德地图聚合食客评分 X/5.0"），**不是真实食客文字**，只作兜底/背书信号，不得在口味分中占主导。
- **腾讯位置服务**（模块 `map_helpers.tencent_suggestion/search`、`cloud_phone_fill`）：suggestion/search/geocoder，补电话/坐标；日配额，SK 签名。**search 与 geocoder 配额分开。**
- **权威榜全量召回**（`cloud_michelin_collect.py`、`cloud_blackpearl_collect.py`、pipeline `authority_sitemap/authority_compare`）：米其林 sitemap、黑珍珠全量索引，与官方总数对账；纯 `requests` 返 202 空体时**用浏览器**。属背书/发现，不替代口味。
- **集团/品牌/主厨树**（`group_chef_tree.py`）：从集团、品牌、主厨反向枚举所有门店（抽样框 F3），补 group/chef 链接。
- **官方公众号/新闻稿/品牌官方渠道**：新店、搬迁、关店、活动的权威源（动向，不冒充食客）。

### L1 匿名签名直连（免费、不登录）

- **xhshow 签名 HTTP**（`cloud/xhs_api.py`）：
  - **匿名/受限账号实测**：浏览器里被标 `restricted(300011)` 的账号走签名 HTTP 仍 `code=0`；
  - **匿名"搜索"= `-101` 死路**；`feed`（笔记详情）/`comments`（评论）**必须带 `xsec_token`+`xsec_source=pc_search`，否则 `300031`**；
  - 因此 L1 只能"取指定笔记"，且需先从别处拿到 note id + token，不能独立做发现。
  - 安全节奏：搜索 ≤2 次/分（间隔 28s），速率码永久翻倍（上限 120s）；`code=0 空 data`=软限流，长冷却自恢复；每账号 `/tmp` flock 跨进程串行。

### L2 网页只读（免费）

- **SmartShanghai / TimeOut / That's Shanghai / Nomfluence**：编辑评测/榜单，经 Clash 可抓（首页实测 200/216KB）。属**媒体（media），非独立 UGC**——作发现/背书，不记为真实食客证据。
- **B 站**（`cloud_bili_collect.py`、`bili_enrich.py`）：美食 vlog、弹幕、评论可提取口味。**搜索 API 匿名实测 `412`（需 wbi 签名 + 真实 buvid/cookie）**，走既有签名/浏览器采集器；单视频评论接口更开放。
- **网页公开列表/详情**：只读、限速、不登录。

### L3 登录账号 / 付费（兜底）

- **Apify actors（不使用我方账号 → 零封号）**，2026-10 实测计费：
  | actor | actId / slug | 计费 | 实测单位经济（A/B） | 适用 |
  |---|---|---|---|---|
  | **opspilot** | `JECW4SdwsOOgtuobc` | **固定 $0.10/启动**，返 20 条 | 每条口味 **$0.036（最低）**，采信率 15% | 精准/外文词、招牌菜 q2 |
  | **atomus** | `hze9g9xvmpSRztttq` | **0 结果=$0**；帖子 $0.02、评论 $0.01、详情 $0.04 | 采信率 **16.7%（最高）**，每条口味 $0.20 | 默认兜底、空跑免费 |
  | **sian** | `sian.agency~xiaohongshu-rednote-scraper` | 启动 $0.014、搜索结果 $0.004/条、详情 $0.05 | 召回最大、每条口味 $0.099 | 中文消歧、要量 |
  | toolzerhub | `kfgMzktMt3KsJfGf6A` | $0.021/启动 | 相关性不稳、0 采信 | 不作默认 |
  | zenstudio | `hO5NqsA6C1byt3jra` | $0.17 | — | 备选 |
  - 禁选：`svGBZz6n79YbeA3uS`（$1.97）、`pGalzQTVAZFRaL6L`（$0.36）。
  - 三家均**不需我方 cookie**；`maxTotalChargeUsd` 兜底；opspilot 只认单数 `keyword`（复数 keywords 数组被静默忽略）。
- **我方登录账号自采（封账号风险高，仅在无 Apify 预算时兜底）**：池化、每账号独立出口 IP、健康探测，过期才扫码；`account_a=ahuhu`、`account_b=猪蛤蛤`。

---

## 4. 每类数据的标准采集路径（routing）

1. **店铺全集/存在性**：高德按区+品类拉 POI（F5）→ 权威 sitemap（F2）→ 集团/主厨树（F3）→ 社交发现（F4）；多框或 ≥2 独立声音才从 frontier 收录。地图单平台声音只建池。
2. **事实字段**：高德 `extensions=all` 一次补人均/电话/时间/坐标/聚合分 → 缺项腾讯兜底；电话过 `clean_phone`、坐标 `in_shanghai`、强地址锚定正确分店；**正确分店无电话则留空，绝不回退其他分店号码**。
3. **口味证据**：
   - 先 L2（B 站/媒体）与库内已采；
   - 再 Apify：查询阶梯 q1（品牌 分店 上海）→0 采信则 q2（品牌 分店 招牌菜 堂食 上海，招牌菜取自 `signature_dishes`）；
   - 路由：精准/外文/招牌菜→opspilot；默认/可能空→atomus；中文消歧/要量→sian；
   - 只采信真实食客堂食；媒体/官方不得冒充 UGC；`entity_match.anchor_note` 判合集/非目标店，合集入 `roundup_queue` 不计口味。
4. **动向/事件**：官方渠道 + KOL/公众号监控 + 媒体；活动须含起止日期与报名入口；新店（主厨新店/海外米其林/海外热门）、主厨变动、飞行厨房、联名快闪分类打标。
5. **分类/语义**：招牌菜→菜系叶联动（`signature_cuisine_link`）；**is=主营定菜系、serves=含有仅标签**；形式（FineDining/Bistro）独立；地名/招牌陷阱词典 + 跨根审计。

---

## 5. 多源校准与去重

- **一店一 canonical id**；`aliases[]` 收异写/旧名/外文名；跨字形用 `cjk_unify`（繁简 OpenCC + 日文和制字），店名匹配用 `cjk_norm`。
- **判重（`duplicate_audit`）**：按 规范名/别名/去业态核心名 聚类，用 `addr_core` 归一后地址集合判定——恰为 1（非空）=同址真重复（合并）；地址不同=异址分店，保留。现状：同址真重复 0、异址分店组 92。
- **名称召回**：支持 exact / 连续包含 / 去中间字缩写（首尾同 + 序比分≥0.5 + 唯一）；对不上先地图 suggestion 取规范全称，不凭字面猜合并。
- **变更留历史**：地址/电话/主厨/搬迁做 change detection，旧值入 history 不直接覆盖（治 Nuits 搬家、南兴园重复）。
- **字段保鲜**：关键字段由"主张"构成（value+source_url+kind+captured_at+confidence）；超期标 stale（新店 30 / 高端 180 / 平价连锁 90 天）。

---

## 6. 数据规范（硬门）

- 统一 `raw_place.schema.json`；入库前 `stage1_validate` / `stage2_prepare`。
- 地址到门牌；坐标 GCJ02、写库用 `point_ewkt`（`SRID=4326;POINT(lng lat)`，GeoJSON 对象 PATCH 会 500）；读坐标用 `parse_location`。
- 电话过 `clean_phone`（宁空不假；占位/测试号判非法；总机/分机记 note）。
- 营业时间结构化进 `opening_hours`（`{raw:...}`）。
- `price_avg` 为 **integer**（发浮点报 22P02）；tier 由 DB 触发器按 price_avg 算，不手填。
- 评价：`review_kind=diner`、`source_platform`、`source_url`、`trust_level`、`is_verified_diner`、`aspect_taste`(1–5)；无口味信号不打分。

---

## 7. 配额 / 账号 / 封号管理

- **地图配额**：多 key 池（`map_quota`，AMAP_KEYS 多账号回退 AMAP_KEY；账本里 amap keys 是 list）；任一源耗尽**不短路**，跨源故障转移，仅当所有源尽且零命中才报 `quota_exceeded`（`map_helpers.resolve_poi._chain`）。
- **Apify 预算**：硬上限走 REST `GET/PUT /v2/users/me/limits`（flat limits 对象，包 {"limits":...} 返 400）；`remaining_credit` 权威口径=`limits.maxMonthlyUsageUsd − used`（不读 `me.plan`）；日预算闸门 `daily_allowance`，`APIFY_DAILY_CAP` 可覆盖；持久熔断指数退避，每店 attempts 封顶。
- **账号健康**：存活权威判据 = `GET /api/sns/web/v2/user/me` `code==0 且 guest==false`（禁止用搜索 POST/get_search_id 判活）；账号独立只看永久 `user_id`；搜索空 `code=0`=软限流，放慢等自恢复；真 `-100` 需双出口 user/me 均过期才判死、扫码重登。
- **独立出口 IP**：每账号独立出口（account_b→广州 139.199.90.169）；同账号跨进程 flock 串行（多进程同 IP 并发是 -100 诱因）。
- **密钥纪律**：key/token 只进 gitignored `cloud/deploy.env`、主机 `fill.env`，绝不外发、不写进任何产物/提交。

---

## 8. 失败处理 SOP（错误码 → 动作）

| 现象/码 | 判定 | 动作 |
|---|---|---|
| Apify `used≥maxMonthlyUsageUsd` | 真无额度 | NO_CREDIT 长睡（4h 轻探）；充值或月度重置后自动恢复，不硬刷 |
| Apify 日预算达 | DAILY_CAP | 睡到次日 00:05 |
| `code=0 空 data`（XHS） | 软限流 | 放慢（间隔翻倍）长冷却自恢复，不重登/换号 |
| XHS `-101`（匿名搜索） | 未登录死路 | 放弃匿名搜索，走 Apify |
| XHS `300031` | 缺 xsec_token/source | 补 token + `xsec_source=pc_search` |
| XHS `-100` 双出口 user/me 均过期 | 登录真过期 | 发起扫码重登（一次有界提醒） |
| 地图 `QUOTA_EXCEEDED`（单源） | 单源配额 | 跨源继续，不整轮停 |
| B 站 `412` | 风控/缺 wbi | 补 wbi 签名 + buvid/cookie 或走浏览器 |
| 纯 requests 抓米其林 202 空体 | 需渲染 | 用浏览器 |
| 看门狗 unknown-双出口失败 | 基础设施（非账号） | 只记日志、不推 action、不重复播报 |

---

## 9. 全部爬虫模块清单（按家族）

- **F-A 宇宙/全集**：`group_chef_tree.py`、`cloud_discover.py`、`gap_runner.py`、`gap_pool.py`、`coverage_matrix.py`、`cloud_amap_fill.py`、`cloud_coord_fill.py`、`cloud_michelin_collect.py`、`cloud_blackpearl_collect.py`；pipeline `authority_sitemap.py`、`authority_compare.py`、`stage6_coverage.py`。
- **F-B 店铺事实**：`cloud_phone_fill.py`、`cloud_coord_fill.py`、`cloud_hours_fill.py`、`cloud_hours_fill2.py`、`cloud_amap_fill.py`、`fact_verify.py`、`map_helpers.py`、`map_quota.py`、`map_key_repair.py`；pipeline `fill_negative_fields.py`、`negative_audit.py`。
- **F-C 口味/评价**：`review_apify_fill.py`、`apify_collect.py`、`apify_ingest.py`、`review_ugc_fill.py`、`ugc_longrun.py`、`xhs_api.py`、`cloud_bili_collect.py`、`bili_enrich.py`、`cloud_dianping_phone.py`、`dianping_daily.py`、`dianping_branch_list.py`、`ab_compare.py`；pipeline `xhs_to_reviews.py`、`atlas_write.py`。
- **F-D 动向/社媒**：`kol_monitor.py`、`kol_identity.py`、`kol_cross.py`、`kol_context_backfill.py`、`wechat_source_registry.py`、`status_events.py`、`findings_extractor.py`、`findings_ingest.py`、`findings_planner.py`、`serp_producer.py`、`cloud_patrol.py`、`patrol_classify.py`、`watchdog.py`、`warning_handler.py`（`external_watchdog/`）。
- **F-E 分类/语义**：`category_resolver.py`、`subtype_distributor.py`、`signature_cuisine_link.py`、`private_kitchen_club_resolver.py`、`scene_ingredient_coverage.py`、`classification_intruder_audit.py`、`backfill_cuisine.py`、`curate_v4.py`、`reconcile.py`。
- **F-F 编排/质量门/通知**：`pm_dispatch.py`、`inbox.py`、`task_helper.py`、`gate_apply.py`、`candidate_apply.py`、`repair_misanchor.py`、`data_gate.py`、`apify_fill_controller.sh`、`cloud_router.py`、`notifier.py`、`notify_cli.py`、`progress_broadcast.py`、`qa_broadcast.py`、`self_evolve.py`、`recalc_scores.py`、`account_repair.py`、`account_registry.py`、`xhs_cookie_pool.py`、`xhs_qr_login.py`、`work_progress.py`、`public_status.py`；pipeline `release_audit.py`。

---

## 10. 验收（闭环自检）

- 发版前跑 pipeline `release_audit.py`（串联各质量门，A–H：覆盖/证据/软广连锁/实体/分类/定价/时效/前端），**全绿才写库/部署**；前端 H 类用 browser-use 单独回归。
- 每次写后回读；新增字段/评价统计真实数量与口径；电话/坐标等非目标字段一律不动。
- 新踩的坑回写 `lessons-learned.md`，能固化为脚本/质量门的直接落地。
- 每日 02:00 自进化复盘：采集增量、覆盖率、告警与处理、机制改动、仍待人工项，经 notifier 双通道（Telegram + 飞书）合并推送一条、不刷屏。

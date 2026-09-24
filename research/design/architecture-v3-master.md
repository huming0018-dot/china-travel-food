# 上海美食图鉴 · 架构总纲 v3（分类·监听·主厨·Feed·评分·数据库）

> **本文是 v3 升级的单一设计真相入口**，整合三份详细设计文档。取代 architecture-v2-atlas.md 的旧版 user journey / 评分 / social listening 章节。
> 日期：2026-09-24。数据库：Supabase `bdwrhshgdeghgyzwpxnl`，restaurants 1497 家。
> 配套迁移：`db/migrations/005_scoring_v3.sql`（幂等可重跑，前置 001–004）。

---

## 0. 五大问题 → 解决方案总览

| # | 用户问题 | 根因 | v3 解决方案 | 详细设计 |
|---|---|---|---|---|
| 1 | 分类逻辑有问题：馄饨/饺子/锅贴/生煎无独立轴；饼下混入精品店；用户搜索意图解读不明 | 食材轴扁平无层级；"主营vs含有"判定不严；无 query→维度映射 | 四维正交分类（菜系×食材×形式×场景）；食材轴两级化（包馅面食9子叶、饼3子叶、甜品6子叶）；12条搜索意图映射表；6阶段用户旅程 | `classification-user-journey-v3.md` |
| 2 | Nuits 搬恒隆二期、原址关店未捕获——social listening 缺失 | 无自动化监听管线；无官方源矩阵；无搬迁闭环流程 | T1–T4源矩阵（官方→新闻→KOL→地图）；8类事件词根配置；双频率巡检；Nuits六步闭环（原址closed+新址active+relocated事件互联） | `social-listening-chef-feed-v3.md` |
| 3 | 已收录店主厨/卖点/荣誉/声誉（一饭封神/黑白厨房）未建档追踪 | chefs/awards表已建但全空；无追踪机制 | chefs补mentor_ids/tracking_seeds；荣誉每届一行is_current；卖点jsonb每条带来源；主厨名+店名作搜索种子定期监听 | `social-listening-chef-feed-v3.md` |
| 4 | 首页需新栏目：定期更新新店/主厨变化/飞行厨房/跨界联名/联合快闪 | 无food_events消费层；无Feed交互设计 | food_events七tab（主厨新店/海外首店/主厨变化/飞行厨房/跨界联名/联合快闪/荣誉）；feed_view按event_date倒序；expires_on自动下沉；feed_cadence自控 | `social-listening-chef-feed-v3.md` |
| 5 | 评分机制：只采信真实评价/评价越多置信越高/近期权重高/负面语义甄别不扣口味 | 004初版用全局先验（寿司拉面共享）；综合分权重旧0.4/0.3/0.2/0.1；背书分手填 | 评分引擎v3：品类先验+上溯；贝叶斯收缩m=8；时间衰减HALF_LIFE=180；方面级aspect_taste只含菜品；综合分0.35/0.25/0.25/0.15；背书分awards触发器自动派生 | `scoring-db-architecture-v3.md` |

---

## 1. 设计原则（不变）

1. **一切事实可溯源**：每条评价/荣誉/事件/主厨关联带 source_url + 平台 + 日期。
2. **派生数据由数据库计算**：评分/置信度/背书分走函数/触发器/视图，禁止手填。
3. **多维度正交**：菜系(where)×食材(what)×形式(how)×场景(when/why)，一家店各维度多挂。
4. **时间是一等公民**：评价时间衰减、荣誉is_current、事件event_date、实体保鲜期。
5. **写入口收敛**：采集→raw JSONL→stage校验→service_role写库；无公开写策略。
6. **修机制不补单店**：Nuits/DV×遇外滩是回归测试用例，机制修好后同类店自动捕获。

---

## 2. 分类机制 v3（问题1）

### 2.1 四维正交体系

| 维度 | 回答 | 叶子结构 | 挂叶规则 |
|---|---|---|---|
| **菜系轴** | 吃哪国/哪派？ | 8虚拟根→二级菜系→三级子流派 | 主营风味，1主+多挂 |
| **食材轴** | 想吃什么？ | 父叶→子叶两级（v3新增） | 主营才挂子叶，含有折叠 |
| **形式轴** | 多正式/什么店型？ | Fine Dining/Casual/Bistro/快餐/大排档/Brunch/下午茶/夜宵/自助/酒吧/茶馆/私宴/美食广场 | 1主形式 |
| **场景轴** | 什么场合/时段？ | 时段(早/午/晚/夜宵)×场合(宴请/约会/一人食/家庭/团建) | 可多挂 |

### 2.2 食材轴两级化（核心修复）

```
包馅面食 ★（新父叶，跨菜系）
├─ 饺子（水饺/煎饺/蒸饺）
├─ 馄饨（川式抄手/广式云吞）
├─ 锅贴
├─ 生煎（上海生煎）
├─ 小笼包（苏式/无锡小笼）
├─ 汤包（淮安/镇江/靖江）
├─ 烧卖（粤式干蒸）
├─ 包子（鲜肉大包/叉烧包）
└─ 汤圆（宁波汤团）

饼 ★（细化，清理精品店）
├─ 中式烙烤饼（葱油饼/手抓饼/烧饼/煎饼）← 正餐/早餐
├─ 咸galette（布列塔尼荞麦）← 轻食
└─ 【甜可丽饼/舒芙蕾松饼 → 转甜品叶，不进正餐饼】

甜品（父叶）
├─ 法式甜品（闪电泡芙/马卡龙/蛋糕）
├─ 意式Gelato
├─ 日式和果子/抹茶/刨冰
├─ 广式糖水/潮汕甜汤
├─ 甜可丽饼 ★（从饼移入）
└─ 舒芙蕾松饼 ★（从饼移入）
```

**跨轴挂法**：无锡小笼店 = 菜系"苏菜·无锡菜" + 食材"包馅面食·小笼包" + 形式"快餐简餐"。用户在食材轴点"小笼包"可搜到所有小笼店，点菜系"无锡菜"时侧边栏推荐"包馅面食·小笼包/汤包"。

### 2.3 主营 vs 含有（量化判据）

- **主营**：招牌菜/菜单主体 ≥一半，或店名/食客心智明确指向 → 挂菜系叶子
- **含有**：≤1/3 且非店名所指 → 不挂菜系叶，必要时食材/形式标签体现
- **真融合**：两类出品都成体系、招牌并列 → 挂多菜系叶+融合菜根

### 2.4 搜索意图映射（12条典型query）

| 用户输入 | 命中维度 | 排序逻辑 |
|---|---|---|
| "想吃饺子" | 食材轴·包馅面食·饺子 | score_taste DESC |
| "无锡菜" | 菜系轴·苏菜·无锡菜 + 推荐包馅子叶 | score_total DESC |
| "附近生煎" | 地理×食材·生煎×营业中 | 距离 ASC, score_taste DESC |
| "Fine Dining约会" | 形式·Fine Dining(人均≥250)×场景·约会 | score_total DESC |
| "米其林一星" | 认证·米其林一星 | endorsement DESC |
| "今天新开" | Feed·new_open×event_date=今天 | event_date DESC |
| "飞行厨房" | Feed·guest_kitchen | event_date DESC |
| "DV联名" | Feed·collaboration×店名搜索 | relevance |

---

## 3. Social Listening 管线（问题2）

### 3.1 源矩阵 T1–T4

| 层 | 源 | 能否单独定high |
|---|---|---|
| **T1 一手官方** | 官方公众号/官方小红书蓝V/官方抖音企业号/官网/微博蓝V | ✅ 1个即可 |
| **T2 权威新闻** | 米其林/黑珍珠官方、澎湃/上观、TimeOut/That's Shanghai | ✅ ≥2独立互证 |
| **T3 KOL老饕** | 小红书老饕/抖音探店/B站UP/即刻豆瓣 | ❌ 单源只mid/rumor |
| **T4 地图POI** | 点评"已关闭"/高德营业状态/电话停机 | ❌ 仅旁证触发器 |

**反例（不算在营证据）**：聚合预订站残留、招聘网站仍在招、外卖可下单、通稿转载。

### 3.2 监测词根（8类事件，配置驱动）

搬迁/闭店/新店/换主厨/飞行厨房/跨界联名/联合快闪/荣誉——每类配中文词根+店名/主厨名种子。配置文件 `research/social/listen_keywords.yaml`。

### 3.3 双频率巡检

- **采集后台**：高端店T1每日、T4地图每周、词根sweep每周、荣誉季加密
- **保鲜期**：新店30天 / 高端店180天 / 平价连锁90天
- **用户自控**：feed_cadence（日/周/月）

### 3.4 Nuits 六步闭环（回归用例）

1. **触发**：T1官方公众号发搬迁公告 → 词根"搬迁/新址"命中
2. **证据固化**：截图+URL+日期写入 raw_event
3. **原址处理**：restaurants.status=closed + closed_at + closed_reason + source_url
4. **新址处理**：建/对齐同名异址行 status=active + lineage（prev_restaurant_id）+ 主厨/荣誉继承（口味分不迁移）
5. **事件互联**：food_events category=relocated, restaurant_id=原址, related_restaurant_id=新址
6. **回归断言**：机制重跑能自动捕获Nuits及同类搬迁店

---

## 4. 主厨/荣誉追踪（问题3）

### 4.1 主厨档案

- `chefs` 表：name/name_en/title/bio/origin(师承流派)/is_traveling/social账号/reputation/**mentor_ids**(同门)/**tracking_seeds**(搜索种子)
- `restaurant_chefs`：restaurant_id+chef_id+role+is_current+started/ended+source_url
- 主厨流动 → 同时写 food_events（new_open/chef_changed/guest_kitchen）

### 4.2 荣誉结构化

- `restaurant_awards`：每届一行，is_current翻转；award_type=michelin_star/bib_gourmand/black_pearl/media_show(一饭封神/黑白厨房)/other_list
- 背书分由 awards 触发器自动派生（米其林三星=100、二星=90、一星=80、黑珍珠三钻=90…）

### 4.3 卖点建档

- `restaurants.selling_points` jsonb：3–6条，每条带 evidence + source_url
- 招牌菜/独特技法/食材来源/用餐体验

---

## 5. 首页 Feed 栏目（问题4）

### 5.1 七 Tab 映射

| Tab | food_events.category | 说明 |
|---|---|---|
| 主厨新店 | new_open（chef_id非空） | 知名主厨新开 |
| 海外首店 | new_open（scope=overseas） | 海外米其林/热门店上海首店 |
| 主厨变化 | chef_changed | 离职/新任 |
| 飞行厨房 | guest_kitchen | 客座主厨/menu之夜 |
| 跨界联名 | collaboration | DV×遇外滩类 |
| 联合快闪 | popup | 限时快闪，expires_on自动下沉 |
| 荣誉发布 | award | 米其林/黑珍珠/综艺 |

### 5.2 展示逻辑

- `feed_view`：event_date DESC，high置信优先，rumor标"传闻"，expires_on<today自动隐藏
- 首页Feed区 + 独立Feed页（可按tab筛选）
- 更新频率：feed_cadence用户自控（日/周/月），系统按周期跑监听+人工审核队列

---

## 6. 评分引擎 v3（问题5）

### 6.1 五原则落地

| 原则 | 实现 |
|---|---|
| ①只采信真实评价 | `review_kind='diner' AND is_fake_suspect=false AND is_hidden=false` 才纳入 |
| ②评价越多置信越高 | 贝叶斯收缩 `review_confidence = v/(v+m)`，m=8；<0.2打"评价尚少" |
| ③近期权重略高 | `w = 0.5^(age_days/180)`，半年半衰期 |
| ④负面语义甄别 | aspect_taste只含菜品评价（腥/老/柴/咸/预制味）；服务/等位/环境/性价比/情绪→service/env/value，**不扣taste** |
| ⑤去软广 | 6条软广判定规则打is_fake_suspect直接排除；soft_ad_penalty扣综合分 |

### 6.2 算法

```
单条折0-100: q = (aspect_taste-1)/4*100
时间权重:    w = 0.5^(age/180)
衰减均值:    R = Σ(w·q)/Σ(w)，有效评论数 v = Σw
品类先验:    C = 同菜系叶子均值（样本<20上溯父类，最终兜底70）
口味分:      score_taste = (v/(v+8))·R + (8/(v+8))·C
置信度:      review_confidence = v/(v+8)
综合分:      score_total = 0.35·taste + 0.25·objective + 0.25·diner + 0.15·endorsement − soft_ad_penalty
```

### 6.3 数值示例（已验证）

5条近期4.5★ + 20条远期3.8★ → v=9.45, R=78.25, **score_taste=75.38, confidence=0.542**
薄样本2条好评 → confidence=0.182 → 触发"评价尚少"标，不与高置信店并列

### 6.4 v3 对 004 的三处关键修正

1. **先验C**：全局均值 → 同品类叶子+上溯父类
2. **综合分权重**：0.4/0.3/0.2/0.1 → 0.35/0.25/0.25/0.15（taste升为核心）
3. **背书分**：人工手填 → awards触发器自动派生

---

## 7. 数据库架构升级

### 7.1 005 迁移内容（`db/migrations/005_scoring_v3.sql`）

| Batch | 内容 |
|---|---|
| 1 | 食材轴补全：汤包/包子/中式烙烤饼/咸galette/甜可丽饼/舒芙蕾松饼 |
| 2 | Social Listening列：last_listened_at/freshness_due/taste_prior_source/soft_ad_flag；chefs加mentor_ids/tracking_seeds；food_events加expires_on；awards CHECK+唯一索引 |
| 3 | derive_restaurant() 升级综合分权重 0.35/0.25/0.25/0.15 |
| 4 | cuisine_prior() 品类先验+递归上溯 |
| 5 | recalc_taste_for() 贝叶斯收缩到品类先验 |
| 6 | recalc_endorsement_for() 背书分自动派生 |
| 7 | 触发器：reviews→taste、awards→endorsement |
| 8 | 索引：列表部分索引/GIN aliases/评价热集部分索引/pg_trgm中文模糊/expires_on |
| 9 | 视图：restaurant_detail_view（聚合评分/荣誉/主厨/近期评价）、feed_view（过期自动下沉） |
| 10 | 回填：recalc_taste_all() + recalc_endorsement_all() |

### 7.2 中文搜索

Supabase 不支持 zhparser/pg_jieba（需编译），务实方案：`pg_trgm` GIN索引 + `aliases`数组 + simple配置search_vector三路并用。1497店规模下召回率足够。

---

## 8. 实施路线图

```
阶段1：数据库迁移（已就绪）
  └─ 执行 005_scoring_v3.sql → 验证表/函数/触发器/视图

阶段2：分类重挂（需采集）
  ├─ 跑 cuisine_classify_audit.py 识别包馅面食/饼错放店
  ├─ 无锡小笼/上海生煎/饺子店批量挂"包馅面食"食材叶
  ├─ 甜可丽饼/舒芙蕾松饼店从"饼"移到"甜品"
  └─ 验证：食材轴"包馅面食"可检索到所有小笼/生煎/饺子店

阶段3：数据回填（Atlas v2采集，并行）
  ├─ raw_chefs.jsonl（200–300位主厨）
  ├─ raw_awards.jsonl（米其林+黑珍珠+综艺声誉）
  ├─ raw_events.jsonl（含Nuits搬迁、DV×遇外滩快闪）
  └─ raw_reviews.jsonl（400–600家精选店，3–8条/家）
  └─ stage校验 → atlas_write.py写库 → recalc_taste_all()

阶段4：Social Listening 上线
  ├─ 配置 listen_keywords.yaml
  ├─ Vercel Cron 调度（T1每日/T4每周/词根sweep每周）
  ├─ 人工审核队列（rumor/mid必经）
  └─ 回归测试：Nuits搬迁、DV联名自动捕获

阶段5：前端升级
  ├─ 首页Feed栏目（七tab，feed_view驱动）
  ├─ 食材轴两级导航（包馅面食/饼/甜品父叶展开）
  ├─ 搜索意图解读（query→维度映射）
  ├─ 评分展示（score_taste + confidence标 + "评价尚少"）
  └─ 详情页主厨/荣誉/卖点模块

阶段6：回归验收
  └─ release_audit.py 全绿 + 前端浏览器实测 + 回归集100%命中
```

---

## 9. 详细设计文档索引

| 文档 | 路径 | 内容 |
|---|---|---|
| 分类+用户旅程 v3 | `research/design/classification-user-journey-v3.md` | 542行：联网研究(7方向19来源)、四维分类树、12条搜索映射、6阶段旅程、faceted浏览规格 |
| 社交监听+主厨+Feed v3 | `research/design/social-listening-chef-feed-v3.md` | 428行：T1–T4源矩阵、8类词根、Nuits六步闭环、主厨档案、Feed七tab、采集SOP |
| 评分+数据库架构 v3 | `research/design/scoring-db-architecture-v3.md` | 1229行：评分算法+数值示例、16个SQL代码块、索引策略、视图/函数/触发器、005完整SQL |
| 005迁移 | `db/migrations/005_scoring_v3.sql` | 可直接在Supabase执行的幂等SQL |
| 采集契约 | `research/atlas/COLLECTION_CONTRACT.md` | raw_chefs/awards/events/reviews 四类字段定义 |

---

## 10. 验收 DoD

- [ ] 005迁移执行成功，独立SELECT验证表/函数/触发器/视图
- [ ] 包馅面食9子叶齐全，无锡/上海生煎饺子馄饨店在食材轴可检索；"饼"下无精品甜店错放
- [ ] Nuits：原址closed三要素 + 新址active + relocate事件互联
- [ ] 抽样店主厨/卖点/荣誉（含一饭封神/黑白厨房）已建档，来源齐全
- [ ] score_taste由真实堂食派生（时间衰减+贝叶斯+品类先验+方面甄别），review_confidence落库
- [ ] 服务/等位/环境/性价比差评不扣taste（抽查aspect_json证据）
- [ ] 首页Feed七tab按category更新，expires_on过期自动下沉
- [ ] release_audit全绿 + 前端浏览器实测 + 回归集100%命中

# 上海美食图鉴 · 评分引擎 v3 + 数据库架构升级设计

> 视角：架构工程师 / 数据建模。本文是「去软广找真实好店」定位下评分机制 v3 与数据库架构升级的**单一设计真相**。
> 前置迁移：`001_init.sql` + `002_harden.sql` + `003_mechanism_v2.sql` + `004_atlas_v2.sql`（已在 Supabase 项目 `bdwrhshgdeghgyzwpxnl` 执行）。
> 本文档配套新迁移文件为 `005_scoring_v3.sql`（文末附录给出可直接在 Supabase SQL Editor 执行的完整幂等 SQL）。
> 铁律延续 v2：**模型只做发现与判断，数据库用结构保证正确，派生数据由函数/触发器/视图计算，禁止手填评分。**

---

## 0. 设计目标与五原则落地

| 原则 | 落地手段 | 落库位置 |
|---|---|---|
| ① 只采信真实评价 | `review_kind='diner' AND is_fake_suspect=false AND is_hidden=false` 才纳入聚合；press/takeaway 排除 | reviews 行级过滤 |
| ② 评价越多置信度越高 | 贝叶斯收缩 + 显式置信度 `review_confidence = v/(v+m)` | restaurants.review_confidence |
| ③ 近期权重略高于远期 | 指数时间衰减 `w = 0.5^(age_days/180)`，半年半衰期 | 聚合函数内计算 |
| ④ 负面评价语义甄别 | 方面级分类：服务/等位/环境/性价比/个人情绪 → service/env/value，**不扣 taste**；只有针对菜品的负面才进 taste | reviews.aspect_* |
| ⑤ 去软广（隐含） | 软广判定规则打 `is_fake_suspect=true` 直接排除；`soft_ad_penalty` 扣综合分 | reviews.is_fake_suspect + restaurants.soft_ad_penalty |

**v3 相对 004 初版的三处关键修正：**
1. **先验 C 从「全局均值」升级为「同品类均值，样本不足上溯父类」**——004 的 `recalc_taste_for` 用全库所有有效评价的均值当先验，导致寿司店和拉面店共享一个先验，失去品类内可比性。v3 改为按主菜系叶子聚合，叶子样本不足时上溯 `parent_category`。
2. **`score_total` 权重从 0.4/0.3/0.2/0.1 改为 0.35/0.25/0.25/0.15**——taste 成为核心（从 0.2 升到 0.35），客观分降权（平台分可被刷）。
3. **背书分 `score_endorsement` 从人工手填改为由 `restaurant_awards` 触发器自动派生**——消除人工口径漂移。

---

# A. 评分引擎 v3

## A1. 评论级预处理管道

### A1.1 真实性过滤（纳入条件）

一条 review 只有同时满足以下条件，才进入口味聚合：

```sql
review_kind = 'diner'            -- 只算堂食；takeaway(外卖)/press(媒体通稿) 排除
AND COALESCE(is_fake_suspect, false) = false   -- 软广/假评嫌疑排除
AND is_hidden = false            -- 被举报隐藏的排除
AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL  -- 有口味分才纳入
```

**设计理由**：外卖评价反映的是打包后的口感（坨了/凉了/撒了），不等于堂食口味；媒体通稿是 PR 不是食客证据；被隐藏的评价已经过社区审核。这三条把「真实堂食评价」这个概念在数据库层面钉死，任何上游写脏数据都不会污染 taste 分。

### A1.2 软广判定规则（采集阶段打标，不进聚合）

以下规则在 **stage1/stage2 采集管线**判定，结果写入 `reviews.is_fake_suspect` 或 `trust_level='low'`。数据库不做 NLP（那是采集器的活），数据库只负责**信任打标后不纳入**。

| 规则 | 判定逻辑 | 打标结果 |
|---|---|---|
| R1 模板文案 | 正文命中「必吃/天花板/绝绝子/YYDS/封神/打卡圣地」≥2 个且**不含任何具体菜名**（`signature_dishes` 交集为空） | `is_fake_suspect=true` |
| R2 评分-情感背离 | `rating_total=5` 但正文含负面菜品词（腥/老/柴/咸/预制/翻车/踩雷/不新鲜）≥1 | `is_fake_suspect=true` |
| R3 评分分布异常 | 单店近 90 天评价中 5 星占比 >95%（正常店必有服务/等位/性价比差评） | 标记 soft_ad_flag，人工复核后打标 |
| R4 集中轰炸 | 同一店 48h 内出现 >5 条来自相似作者模式（新号/IP 集中/话术雷同）的好评 | `is_fake_suspect=true` |
| R5 无差评异常 | 全店评价无一条负面方面分（aspect_service/env/value 全部 ≥4）且评价数 >20 | 标记 soft_ad_flag，不自动排除（可能真的好，但触发人工审计） |
| R6 团购挂车 | 正文含「团购链接/优惠/代金券」且无任何负面细节 | `trust_level='low'`（降权而非排除） |

**注意**：R3/R5 是**信号**不是**判决**——数据库只存 `is_fake_suspect`，是否置 true 由采集器（LLM + 规则）综合判断后写入。数据库不自动改这个标记（避免误杀真好评）。

### A1.3 方面级情感甄别（核心：不把服务差评扣在口味上）

每条评价的正文经 LLM 拆成方面级打分。**铁律：负面句按它真正骂的方面归类，不允许把对服务/等位/环境/性价比/个人情绪的不满记到 `aspect_taste`。**

**方面关键词/语义规则表**：

| 方面 | 正向关键词（→ aspect_X 高分） | 负向关键词（→ aspect_X 低分） | 典型句式 |
|---|---|---|---|
| **taste（菜品本身）** | 惊艳/入味/嫩/鲜/弹糯/酥脆/酱汁浓郁/火候刚好/正宗/地道/必点/XXX（具体菜名）绝了/汤底醇厚/面劲斗/油脂香 | 腥/膻/老/柴/干/咸/淡而无味/腻/油哈味/预制味/料理包/翻车/踩雷/不新鲜/有异味/没熟/过咸/发苦/面坨了/米硬/汤头寡淡/回甜不对/肉老得咬不动 | "和牛入口即化"→taste 5；"鱼太腥了"→taste 2 |
| **service（服务/等位）** | 热情/周到/耐心/贴心/讲解专业/预约顺利 | 服务冷淡/服务员不理人/催菜/上菜慢/等位太久/排队两小时/预约被取消/买单慢/翻台催/停车没人管 | "等位排了2小时"→service 2，**不扣 taste** |
| **env（环境）** | 安静/雅致/干净/氛围好/桌间距宽/景观位 | 嘈杂/吵/挤/老旧/脏/油烟重/灯光暗/位置偏/桌间距小/卫生间脏 | "环境太嘈杂聊天听不清"→env 2，**不扣 taste** |
| **value（性价比）** | 物超所值/分量足/性价比高 | 不值/贵/量少/价格虚高/服务费不值/茶位费贵/团购缩水/人均和标价不符 | "人均400但量很小"→value 2，**不扣 taste** |
| **（个人情绪，丢弃）** | — | "今天心情不好""和对象吵架""服务员长得丑" | 不写入任何 aspect，整条评价不因此扣分 |

**LLM 裁决契约**（采集器 stage1 调用，输出写入 `reviews.aspect_json`）：

```json
{
  "taste": {
    "score": 5,
    "evidence": "和牛入口即化，酱汁层次丰富",
    "dish_mentioned": ["和牛", "寿司"]
  },
  "service": {
    "score": 2,
    "evidence": "等位排了40分钟，没人引导入座"
  },
  "env": null,
  "value": null,
  "soft_ad_signals": ["团购挂车"],
  "is_template": false
}
```

裁决规则：
1. 每个方面只在正文有**明确针对该方面**的句子时才给分；无证据 → `null`（不臆造）。
2. 一句话跨多个方面时拆分（"上菜慢但是味道好" → service 低分 + taste 高分）。
3. 个人情绪/外貌/与菜品无关的抱怨 → 丢弃，不写入任何 aspect。
4. `aspect_taste` 只取**直接评价菜品口味/食材/做法/火候**的句子；凡是「服务慢/等得久/环境吵/不值这个价」一律不进 taste。
5. 输出必须带 `evidence` 原句（可追溯）；无 evidence 的分不写。

**落库优先级**：聚合时 `q = COALESCE(aspect_taste, rating_taste, rating_total)`——优先用 LLM 拆出的 taste 方面分，退化到原平台 taste 分，再退化到总分。这保证即使 LLM 拆分失败，旧数据也能跑。

---

## A2. 时间衰减加权

### 公式

$$w_i = 0.5^{\,age\_days_i \,/\, HALF\_LIFE}, \quad HALF\_LIFE = 180 \text{ 天}$$

其中 `age_days = CURRENT_DATE - COALESCE(visit_date, created_at)::DATE`。

| 评价时间 | 权重 w | 含义 |
|---|---|---|
| 今天 | 1.000 | 最新鲜 |
| 30 天前 | 0.891 | 近期，权重略高 |
| 90 天前 | 0.707 | 三个月前，仍有七成权重 |
| 180 天前（半年） | 0.500 | 半衰期，权重腰斩 |
| 360 天前（一年） | 0.250 | 去年此时，四分之一权重 |
| 720 天前（两年） | 0.063 | 两年前，约 1/16，几乎不影响 |
| 1080 天前（三年） | 0.016 | 三年前，可忽略 |

### 为什么是 180 天

1. **餐馆口味会漂移**：换主厨、换菜单、换食材供应商、季节性菜品——半年前的评价对今天的口味仍有参考价值，但一年前的可能已经过时。
2. **打开业营销期**：新店开业头 1–2 个月常有集中好评（含软广/尝鲜滤镜）。180 天半衰期意味着这些评价一年后权重只剩 0.25，两年后 0.06——营销噪音自然衰减，不需要硬删。
3. **不过激**：90 天半衰期太激进（三个月前权重就腰斩，慢热店一年才 8 条评价会几乎没有有效证据）；365 天太慢（开业轰炸一年后仍有 0.85 权重，去软广失效）。180 天是「近期略高、远期不归零」的平衡点。
4. **软衰减而非硬截断**：不像「只取近 180 天评价」那样一刀切——三年前的评价仍有 0.016 权重，保留长尾信号（一家店三年前就好吃 ≠ 今天突然好吃）。

### 如何调参

- HALF_LIFE 在 SQL 函数中以常量 `c_half_life CONSTANT numeric := 180;` 声明，调参只改一处。
- **如果新店分数被开业好评冲高**：降到 120（半年变 4 个月）。
- **如果老店分数随每条新评价剧烈跳动**（说明有效样本太薄）：升到 270。
- 调参后跑一次 `SELECT recalc_all_tastes();` 全量回填。
- 不建议做成 GUC（每连接配置）——评分口径必须全库统一，不能因连接不同而变。

---

## A3. 贝叶斯收缩聚合

### 数学公式

对一家餐厅 r：

1. **衰减加权口味均值**（只对纳入过滤的有效评价）：

$$R_r = \frac{\sum_{i \in eff_r} w_i \cdot q_i}{\sum_{i \in eff_r} w_i}, \qquad q_i = \frac{(aspect\_taste_i - 1)}{4} \times 100$$

2. **有效评论数**（衰减权重之和，不是条数）：

$$v_r = \sum_{i \in eff_r} w_i$$

3. **品类先验** C（同品类衰减加权均值，样本不足上溯父类）：

$$C = \text{cuisine\_prior}(r)$$

4. **收缩后的口味分**（m=8 为伪样本数）：

$$score\_taste_r = \frac{v_r}{v_r + m} \cdot R_r + \frac{m}{v_r + m} \cdot C$$

5. **置信度**：

$$review\_confidence_r = \frac{v_r}{v_r + m}$$

### 为什么用贝叶斯收缩

- 一家店只有 2 条好评就给 95 分是误导——2 条好评可能是开业营销。收缩公式把它拉向品类均值，且置信度只有 0.18，前端打「评价尚少」标。
- 一家店有 50 条真实评价，v≈40+，置信度≈0.83，分数几乎完全由它自己的评价决定（R 权重 83%），先验只占 17%。
- **m=8 的含义**：大约相当于 8 条「半年内的有效评价」的权重，是「多少条评价才够形成可靠判断」的先验。样本不足时自动退到品类均值，不冒进。

### 品类先验 cuisine_prior 的上溯逻辑

```
1. 取该店主菜系叶子（restaurant_cuisines.is_primary=true 对应 cuisines.dimension='菜系' 的最深叶子）
2. 算该叶子下所有餐厅有效评价的衰减加权均值 C_leaf
3. 若 C_leaf 的有效样本数 v_leaf < 20，上溯到 cuisines.parent_category，重算 C_parent
4. 若仍不足，继续上溯到「中餐/亚洲菜/西餐/其他」根
5. 最终兜底：全库有效评价均值（全局先验）
```

**设计理由**：寿司店（高端、人均 500+）和兰州拉面（平价）共享一个先验是荒谬的——拉面店口味分天然偏低。按品类叶子收缩，新拉面店不会因为品类均值 75 而被拉到 75，而是和同品类的拉面店比。叶子样本太少时上溯，避免「这个叶子只有 3 条评价，先验本身就是噪音」。

### SQL 实现（PL/pgSQL）

```sql
-- 品类先验：按菜系叶子聚合，样本不足上溯父类，兜底全局均值
CREATE OR REPLACE FUNCTION cuisine_prior(p_rest INTEGER)
RETURNS TABLE(c_prior numeric, v_prior numeric) AS $$
DECLARE
  v_leaf_id INTEGER;
  v_leaf_name TEXT;
  v_parent TEXT;
  v_sql TEXT;
BEGIN
  -- 1. 取主菜系叶子
  SELECT c.id, c.name, c.parent_category
    INTO v_leaf_id, v_leaf_name, v_parent
  FROM restaurant_cuisines rc
  JOIN cuisines c ON c.id = rc.cuisine_id
  WHERE rc.restaurant_id = p_rest
    AND c.dimension = '菜系'
  ORDER BY rc.is_primary DESC, c.id
  LIMIT 1;

  -- 2. 递归上溯：从叶子开始试，样本不足就用 parent_category
  --    关键：每上一层按「父类名字」回查 cuisines 拿到父类的 parent_category，
  --    才能继续上溯（寿司→日料→亚洲菜→NULL）。
  RETURN QUERY
  WITH RECURSIVE chain AS (
    -- 叶子层：cuisine_id 指向具体叶子
    SELECT c.id AS cuisine_id, c.name::text AS lvl, c.parent_category::text AS parent, 1 AS depth
    FROM cuisines c WHERE c.id = v_leaf_id
    UNION ALL
    -- 上一层：lvl=当前 parent（如「日料」）；按 name=parent 回查拿到祖父类（如「亚洲菜」）
    SELECT NULL, ch.parent, c2.parent_category::text, ch.depth + 1
    FROM chain ch
    LEFT JOIN cuisines c2 ON c2.name = ch.parent AND c2.dimension = '菜系'
    WHERE ch.parent IS NOT NULL
  ),
  layer_stats AS (
    SELECT ch.depth,
           (SELECT COALESCE(SUM(w*q)/NULLIF(SUM(w),0), 70.0)
            FROM reviews rv
            JOIN restaurant_cuisines rc2 ON rc2.restaurant_id = rv.restaurant_id
            JOIN cuisines c2 ON c2.id = rc2.cuisine_id
            WHERE rv.review_kind='diner'
              AND COALESCE(rv.is_fake_suspect,false)=false
              AND rv.is_hidden=false
              AND COALESCE(rv.aspect_taste, rv.rating_taste, rv.rating_total) IS NOT NULL
              AND (ch.cuisine_id IS NOT NULL AND c2.id = ch.cuisine_id
                   OR ch.cuisine_id IS NULL AND c2.parent_category = ch.lvl)
           ) AS c_val,
           (SELECT COALESCE(SUM(w),0)
            FROM reviews rv
            JOIN restaurant_cuisines rc2 ON rc2.restaurant_id = rv.restaurant_id
            JOIN cuisines c2 ON c2.id = rc2.cuisine_id
            WHERE rv.review_kind='diner'
              AND COALESCE(rv.is_fake_suspect,false)=false
              AND rv.is_hidden=false
              AND COALESCE(rv.aspect_taste, rv.rating_taste, rv.rating_total) IS NOT NULL
              AND (ch.cuisine_id IS NOT NULL AND c2.id = ch.cuisine_id
                   OR ch.cuisine_id IS NULL AND c2.parent_category = ch.lvl)
           ) AS v_val
    FROM chain ch
  )
  SELECT ls.c_val, ls.v_val
  FROM layer_stats ls
  ORDER BY (ls.v_val >= 20) DESC, ls.depth ASC
  LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;
```

> 注：上面 `w`/`q` 子查询里需要补 `w = POWER(0.5, (CURRENT_DATE - COALESCE(rv.visit_date, rv.created_at)::DATE)/180.0)` 和 `q = (COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total)-1)/4.0*100`。完整可执行版见附录 §D 的 `recalc_taste_for`。

### 单店重算主函数

```sql
CREATE OR REPLACE FUNCTION recalc_taste_for(p_rest INTEGER) RETURNS void AS $$
DECLARE
  c_half_life CONSTANT numeric := 180;   -- 半衰期天数，调参只改这里
  m           CONSTANT numeric := 8;     -- 贝叶斯伪样本数
  v_R numeric; v_v numeric; v_cnt int;
  v_C numeric; v_vprior numeric;
BEGIN
  -- 1. 品类先验（含上溯）
  SELECT cp.c_prior, cp.v_prior INTO v_C, v_vprior
  FROM cuisine_prior(p_rest) cp;

  -- 2. 该店有效评价的衰减加权聚合
  WITH eff AS (
    SELECT (COALESCE(aspect_taste, rating_taste, rating_total)-1)/4.0*100 AS q,
           POWER(0.5, (CURRENT_DATE - COALESCE(visit_date, created_at)::DATE)
                      / c_half_life) AS w
    FROM reviews
    WHERE restaurant_id = p_rest
      AND review_kind = 'diner'
      AND COALESCE(is_fake_suspect,false) = false
      AND is_hidden = false
      AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL
  )
  SELECT SUM(w*q)/NULLIF(SUM(w),0), SUM(w), COUNT(*)
    INTO v_R, v_v, v_cnt
  FROM eff;

  -- 3. 落库：有评价则收缩，无评价则仅标低置信（保留原人工 taste 分）
  IF v_v > 0 THEN
    UPDATE restaurants SET
      score_taste = ROUND((v_v/(v_v+m))*v_R + (m/(v_v+m))*v_C, 2),
      review_count = v_cnt,
      review_confidence = ROUND(v_v/(v_v+m), 3)
    WHERE id = p_rest;
  ELSE
    UPDATE restaurants
      SET review_count = 0, review_confidence = 0
    WHERE id = p_rest;
  END IF;
END;
$$ LANGUAGE plpgsql;
```

```sql
CREATE OR REPLACE FUNCTION recalc_taste_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_taste_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;
```

---

## A4. 数值示例（手算验证）

### 示例 1：5 条近期 4.5★ + 20 条远期 3.8★

假设某日料店：
- 5 条评价，30 天前就餐，口味分 4.5
- 20 条评价，360 天前就餐，口味分 3.8
- 该品类（寿司）先验 C = 72，m = 8，HALF_LIFE = 180

**逐条计算：**

| 项 | 近期（5条） | 远期（20条） |
|---|---|---|
| 分 q = (rating−1)/4×100 | (4.5−1)/4×100 = **87.5** | (3.8−1)/4×100 = **70.0** |
| 权重 w = 0.5^(age/180) | 0.5^(30/180) = 0.5^(1/6) = **0.891** | 0.5^(360/180) = 0.5² = **0.250** |
| w·q（单条） | 0.891×87.5 = 77.95 | 0.250×70.0 = 17.50 |
| 条数小计 Σ(w·q) | 5×77.95 = **389.77** | 20×17.50 = **350.00** |
| 条数小计 Σw | 5×0.891 = **4.45** | 20×0.250 = **5.00** |

**聚合：**

- Σ(w·q) = 389.77 + 350.00 = **739.77**
- Σw = v = 4.45 + 5.00 = **9.45**
- R = 739.77 / 9.45 = **78.25**（原始衰减加权均值）

**贝叶斯收缩：**

- score_taste = (9.45/(9.45+8))×78.25 + (8/(9.45+8))×72
- = 0.542×78.25 + 0.458×72
- = 42.38 + 32.98
- = **75.38**
- review_confidence = 9.45/(9.45+8) = **0.542**

**解读**：这家店 raw 均值 78.25（近期好评拉高），但收缩到品类先验 72 后落到 75.38。置信度 0.54——中等可信，因为远期 20 条老评价虽然条数多但衰减后只贡献 5.0 个有效权重。前端正常展示。

### 示例 2：只有 2 条近期 4.5★（薄样本）

- v = 2×0.891 = 1.78
- R = 87.5
- score_taste = (1.78/(1.78+8))×87.5 + (8/(1.78+8))×72 = 0.182×87.5 + 0.818×72 = 15.94 + 58.91 = **74.82**
- review_confidence = 1.78/9.78 = **0.182**

**解读**：两条炸裂好评只把分数拉到 74.82（基本被品类先验压住），置信度 0.182 < 0.2 → 前端打「评价尚少」标签，不与高置信店并列。这就是贝叶斯收缩的价值——**2 条好评不会让一家店冒进上榜**。

---

## A5. 综合排序分 score_total

```sql
score_total = clamp[0,100](
  round(
      0.35 * score_taste          -- v3 核心：真实堂食评价派生（权重从 0.2 上调到 0.35）
    + 0.25 * score_objective      -- 平台分折算×可信度系数（人工 curate）
    + 0.25 * score_diner          -- 食客证据厚度（人工 curate）
    + 0.15 * score_endorsement   -- 背书分（v3 改为 awards 触发器自动派生）
    - COALESCE(soft_ad_penalty, 0)
  , 1)
)
```

| 维度 | v2 权重 | v3 权重 | 变化理由 |
|---|---|---|---|
| taste（口味） | 0.20 | **0.35** | 核心：从真实堂食评价派生，是去软广定位的根本 |
| objective（客观平台分） | 0.40 | **0.25** | 降权：平台分可被刷（见 scoring-rubric 可信度系数），不再主导 |
| diner（食客证据） | 0.30 | **0.25** | 略降：具体菜名/体验细节仍重要，但与 taste 有重叠 |
| endorsement（背书） | 0.10 | **0.15** | 略升：米其林/黑珍珠是硬信号，且 v3 改为自动派生 |
| soft_ad_penalty | −0~30 | −0~30 | 不变 |

**`derive_restaurant()` 触发器同步更新权重**（替换 002 旧函数，见附录）。

---

## A6. 低置信处理

| review_confidence | 前端展示 | 排序行为 |
|---|---|---|
| ≥ 0.5 | 正常展示口味分 | 默认排序 |
| 0.2 ~ 0.5 | 展示分 + 小字「样本积累中」 | 正常排序但默认折叠到高置信店之后 |
| < 0.2 | **不展示具体分**，打「评价尚少」标签 | 默认不与高置信店并列；用户可手动展开「看薄样本店」 |

前端排序切换（后端 RPC `search_restaurants` 支持）：
- 默认：`score_total DESC`
- 按置信度：`review_confidence DESC`
- 按价位：`price_avg ASC/DESC`
- 按评价数：`review_count DESC`

**SQL 侧配合**：列表查询默认加 `WHERE review_confidence >= 0.2 OR review_count = 0`（无评价的店也允许出现但排后面），前端 tab 切换时放宽。

---

## A7. 评分刷新机制

### 触发器（reviews 增删改后自动刷新关联餐厅）

004 已有 `trg_reviews_taste`，v3 保留同名触发器但函数已升级（A3 的 `recalc_taste_for`）：

```sql
CREATE OR REPLACE FUNCTION trg_reviews_taste() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM recalc_taste_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_taste_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_taste ON reviews;
CREATE TRIGGER trg_reviews_taste
  AFTER INSERT OR UPDATE OR DELETE ON reviews
  FOR EACH ROW EXECUTE FUNCTION trg_reviews_taste();
```

### 背书分触发器（awards 增删改后刷新 endorsement）

```sql
CREATE OR REPLACE FUNCTION recalc_endorsement_for(p_rest INTEGER) RETURNS void AS $$
  -- 按当前有效荣誉算背书分：取最高档
  -- michelin_star 三星=100/二星=90/一星=80
  -- black_pearl 三钻=90/二钻=75/一钻=60
  -- bib_gourmand=65, media_show=50, other_list=40
DECLARE
  v_endorse numeric;
BEGIN
  SELECT MAX(CASE
    WHEN award_type='michelin_star' AND level LIKE '%三%' THEN 100
    WHEN award_type='michelin_star' AND level LIKE '%二%' THEN 90
    WHEN award_type='michelin_star' AND level LIKE '%一%' THEN 80
    WHEN award_type='black_pearl' AND level LIKE '%三%' THEN 90
    WHEN award_type='black_pearl' AND level LIKE '%二%' THEN 75
    WHEN award_type='black_pearl' AND level LIKE '%一%' THEN 60
    WHEN award_type='bib_gourmand' THEN 65
    WHEN award_type='media_show' THEN 50
    WHEN award_type='other_list' THEN 40
    ELSE 40 END)
    INTO v_endorse
  FROM restaurant_awards
  WHERE restaurant_id = p_rest AND is_current = true;

  UPDATE restaurants SET score_endorsement = COALESCE(v_endorse, 0)
  WHERE id = p_rest;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_awards_endorsement() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM recalc_endorsement_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_endorsement_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_awards_endorsement ON restaurant_awards;
CREATE TRIGGER trg_awards_endorsement
  AFTER INSERT OR UPDATE OR DELETE ON restaurant_awards
  FOR EACH ROW EXECUTE FUNCTION trg_awards_endorsement();
```

**设计理由**：荣誉是结构化事实（米其林几星、黑珍珠几钻），完全可以由数据库从 awards 表自动派生背书分，不需要人工 curate。换奖/掉星时旧记录 `is_current=false`，触发器自动重算。

### 级联注意

`recalc_taste_for` 内部 `UPDATE restaurants SET score_taste=...` 会触发 `trg_restaurants_derive`（BEFORE UPDATE），后者自动用新权重重算 `score_total`。**不需要在 taste 触发器里手动算 total**——Postgres 触发器天然链式执行。

---

# B. 数据库架构设计

## B1. 完整表结构清单

### B1.1 现有表（001–004 已建，列关键 + 约束）

#### `restaurants`（1497 行，核心表）

| 列 | 类型 | 约束/默认 | 设计理由 |
|---|---|---|---|
| id | SERIAL | PK | |
| name | VARCHAR(200) | NOT NULL, ch_rest_name_nonempty | 店名非空 |
| name_en | VARCHAR(200) | | 英文名（搜索召回） |
| tier | VARCHAR(20) | CHECK 五档，触发器按 price_avg 自动算 | 人均分档，派生列 |
| price_avg | INT | CHECK 0–99999 | 人均 |
| price_range | VARCHAR(50) | | 文字价格区间 |
| address | TEXT | | 地址 |
| district | VARCHAR(50) | | 行政区（筛选） |
| business_area | VARCHAR(50) | | 商圈（002 search_vector 用到） |
| location | GEOGRAPHY(POINT,4326) | CHECK 上海 bbox | PostGIS 坐标，GiST 索引 |
| phone | VARCHAR(50) | | 电话（宁空不假） |
| booking_method | TEXT | | 预订方式 |
| signature_dishes | JSONB | CHECK 是数组 | 招牌菜数组 |
| **score_objective** | NUMERIC(5,2) | CHECK 0–100 | 客观平台分（人工 curate） |
| **score_diner** | NUMERIC(5,2) | CHECK 0–100 | 食客证据分（人工 curate） |
| **score_taste** | NUMERIC(5,2) | CHECK 0–100 | **v3：由 reviews 触发器自动派生** |
| **score_endorsement** | NUMERIC(5,2) | CHECK 0–100 | **v3：由 awards 触发器自动派生** |
| soft_ad_penalty | NUMERIC(5,2) | CHECK 0–30 | 软广扣分 |
| score_total | NUMERIC(5,2) | CHECK 0–100，BEFORE 触发器算 | 综合排序分，派生列 |
| evidence_summary | TEXT | | 证据摘要 |
| status | VARCHAR(30) | DEFAULT 'active', CHECK active/closed | 在营/关店 |
| closed_date / closed_source | DATE/TEXT | closed 时必填（三要素） | 关店保鲜 |
| data_updated_at | DATE | | 数据保鲜 |
| **selling_points** | JSONB | （004 加） | 卖点数组，3–6 条 |
| **aliases** | TEXT[] | （004 加） | 异写/简称/拼音，搜索召回 |
| **review_count** | INT DEFAULT 0 | （004 加） | 有效堂食评价条数（派生） |
| **review_confidence** | NUMERIC(4,3) DEFAULT 0 | CHECK 0–1（004 加） | 评分置信度（派生） |
| chain_type / central_kitchen / premade_risk / price_position | TEXT | （003 加，CHECK 枚举） | 工业化餐饮识别 |
| search_vector | TSVECTOR | GENERATED ALWAYS STORED | 全文搜索，GIN 索引 |

#### `cuisines`（分类字典：菜系/食材/形式/标签/时段/认证）
- id PK, name, dimension（CHECK 六类）, parent_category, price_low/mid/high, …
- 唯一索引：`uq_cuis_name_dim_parent(name, dimension, COALESCE(parent_category,''))`

#### `restaurant_cuisines`（餐厅×分类多对多，约 1.4 万行）
- (restaurant_id, cuisine_id, is_primary)，PK(restaurant_id, cuisine_id)
- 外键级联 ON DELETE CASCADE

#### `reviews`（食客评价）
| 列 | 类型 | 设计理由 |
|---|---|---|
| id | UUID PK | 随机主键，防枚举 |
| restaurant_id | INT FK | 级联删除 |
| user_id | UUID FK auth.users | 登录用户评价；外部采集为 NULL |
| author_name | TEXT | 采集评价的作者名 |
| rating_total / rating_taste | INT CHECK 1–5 | 原始平台分 |
| content | TEXT | 逐字原话 |
| visit_date | DATE | 就餐日期（时间衰减基准） |
| is_hidden | BOOL DEFAULT false | 社区隐藏 |
| **source_platform / source_url** | TEXT（004 加） | 来源可追溯 |
| **review_kind** | TEXT DEFAULT 'diner'（004 加，CHECK diner/takeaway/press） | 只 diner 进口味 |
| **is_verified_diner** | BOOL（004 加） | 平台已就餐验证 |
| **trust_level** | TEXT（004 加，CHECK high/mid/low） | 信任等级 |
| **is_fake_suspect** | BOOL DEFAULT false（004 加） | 软广/假评标记 |
| **aspect_taste/service/env/value** | INT CHECK 1–5（004 加） | 方面级分 |
| **aspect_json** | JSONB（004 加） | LLM 拆分原始结果（含 evidence） |

#### `chefs` / `restaurant_chefs` / `restaurant_awards` / `food_events`（004 新建，当前全空）
- 见 004 迁移，结构不变。

### B1.2 v3 新增/修改列

| 表 | 列 | 类型 | 理由 |
|---|---|---|---|
| restaurants | `taste_prior_source` | TEXT | 记录该店收缩用的先验来自哪一层（leaf/parent/global），便于审计调参 |
| restaurants | `soft_ad_flag` | TEXT | 软广信号人工复核状态（none/suspected/confirmed），R3/R5 信号不自动扣分只标记 |
| reviews | `decay_weight` | NUMERIC(6,4) | （可选）缓存最近一次重算时的衰减权重，避免每次重算重算 w；1497 店×万条 review 量级不大，不缓存也可 |

> **不新增列**：`score_taste`/`review_count`/`review_confidence` 004 已加；v3 只改计算逻辑。

---

## B2. 索引策略

### B2.1 查询模式分析

| 查询场景 | WHERE / JOIN | ORDER BY | 当前索引够不够 |
|---|---|---|---|
| 列表页：按菜系筛选 + 排序 | rc.cuisine_id=? AND r.status='active' | r.score_total DESC | 需组合索引 |
| 列表页：按行政区/价位 | r.district=? AND r.tier=? | r.score_total DESC | 需组合 |
| 地图页：附近餐厅 | r.location <@> POINT | ST_Distance | GiST(location) 已有 |
| 搜索：店名/别名 | r.search_vector @@ query 或 aliases @> | 权重排序 | GIN(search_vector) 已有；aliases 需 GIN |
| 详情页：单店 | r.id=? | — | PK |
| 详情页：该店评价 | rv.restaurant_id=? AND rv.is_hidden=false | rv.visit_date DESC | 需部分索引（热集） |
| Feed：事件流 | fe.status='verified' | fe.event_date DESC | 已有 idx_events_date |

### B2.2 推荐索引（v3 新增）

```sql
-- 1. 列表页主索引：active 店按综合分排序（部分索引只索引 active，体积小）
CREATE INDEX IF NOT EXISTS idx_rest_list
  ON restaurants (score_total DESC)
  WHERE status = 'active';

-- 2. 菜系筛选 + 排序：restaurant_cuisines 按 cuisine_id 命中后回表排序
--    已有 idx_rc_cuisine(cuisine_id)；补充 (cuisine_id, is_primary) 让主菜系关联更快
CREATE INDEX IF NOT EXISTS idx_rc_cuisine_primary
  ON restaurant_cuisines (cuisine_id, is_primary DESC);

-- 3. aliases 数组 GIN：搜别名/简称/拼音
CREATE INDEX IF NOT EXISTS idx_rest_aliases
  ON restaurants USING GIN (aliases);

-- 4. 评价热集部分索引：只索引参与聚合的有效评价，recalc_taste_for 的 WHERE 直接命中
CREATE INDEX IF NOT EXISTS idx_reviews_effective
  ON reviews (restaurant_id, visit_date DESC)
  WHERE review_kind = 'diner'
    AND COALESCE(is_fake_suspect, false) = false
    AND is_hidden = false
    AND COALESCE(aspect_taste, rating_taste, rating_total) IS NOT NULL;

-- 5. 行政区 + 档位 + 排序（facets 筛选常用）
CREATE INDEX IF NOT EXISTS idx_rest_district_tier
  ON restaurants (district, tier, score_total DESC)
  WHERE status = 'active';
```

### B2.3 已有索引（保留，不重复建）

- `idx_restaurants_location` GiST(location) — 地图查询
- `idx_restaurants_search` GIN(search_vector) — 全文搜索
- `idx_restaurants_status` / `tier` / `district` — 单列过滤
- `idx_reviews_restaurant` — 按店查评价
- `idx_awards_rest` / `idx_awards_current` — 荣誉
- `idx_events_date` / `idx_events_rest` / `idx_events_cat` — Feed

### B2.4 避免过度索引原则

1. **1497 行是小表**：Postgres 对 1500 行的 seq scan 极快（<5ms）。上述索引主要为**未来增长到 1–2 万行**预留。
2. **不建低选择性单列索引**：`status`（只有 active/closed 两个值）不单独建 B-tree——已并入部分索引 `WHERE status='active'`。
3. **写放大权衡**：reviews 表写入频繁（每次采集都插评价），部分索引 `idx_reviews_effective` 只索引热集，写成本小。
4. **GIN/GiST 比 B-tree 贵 3–5 倍**：只在真正需要数组/地理/全文时用，不滥用。
5. **EXPLAIN ANALYZE 验证**：上线后用实际慢查询反推索引，不预防性堆索引。

---

## B3. 约束与数据完整性

### B3.1 CHECK 约束（v3 新增/调整）

```sql
-- score_taste 现在是派生列，但仍允许 NULL（无评价店）
-- 调整 ch_rest_score_range 已覆盖（0–100）。

-- review_confidence 0–1 已有（ch_rconf）。

-- awards award_type 枚举（004 未加 CHECK，v3 补）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_awards_type') THEN
    ALTER TABLE restaurant_awards ADD CONSTRAINT ch_awards_type
      CHECK (award_type IN ('michelin_star','bib_gourmand','black_pearl','media_show','other_list'));
  END IF;
END $$;
```

### B3.2 唯一索引

```sql
-- awards：同一店同类型同年不重复
CREATE UNIQUE INDEX IF NOT EXISTS uq_awards_rest_type_year
  ON restaurant_awards (restaurant_id, award_type, COALESCE(year,0));
```

### B3.3 外键与级联

| 关系 | 级联策略 | 理由 |
|---|---|---|
| reviews → restaurants | ON DELETE CASCADE | 店删了评价无意义 |
| restaurant_cuisines → restaurants/cuisines | CASCADE | 关联表 |
| restaurant_chefs → restaurants/chefs | CASCADE | |
| restaurant_awards → restaurants | CASCADE | |
| food_events.restaurant_id → restaurants | CASCADE | 事件主体删除则事件删 |
| food_events.related_restaurant_id → restaurants | ON DELETE SET NULL | 关联店删除不影响事件本身 |
| food_events.chef_id → chefs | ON DELETE SET NULL | 主厨删除不删事件 |

### B3.4 RLS 策略

| 表 | SELECT | INSERT/UPDATE/DELETE | 说明 |
|---|---|---|---|
| restaurants/cuisines/RC | public (anon+authenticated) | 无策略（仅 service_role） | 已在 001 |
| reviews | public WHERE is_hidden=false | authenticated 仅本人（auth.uid()=user_id） | 外部采集 user_id=NULL 由 service_role 写，绕过 RLS |
| chefs/awards/events | public (anon+authenticated)（004 已加） | 无策略（仅 service_role） | |
| negotiations/price_benchmarks | authenticated | 无公开写 | 已在 001 |
| favorites/profiles | 本人 | 本人 | 已在 001 |

**v3 不新增 RLS 策略**——现有模型已满足「公开读、写仅 service_role、reviews 本人 RLS」。

---

## B4. 视图与函数

### B4.1 只读视图：`restaurant_detail_view`

详情页聚合：评分 + 荣誉 + 主厨 + 最新事件。

```sql
CREATE OR REPLACE VIEW restaurant_detail_view
WITH (security_invoker = on) AS
SELECT
  r.*,
  ST_X(r.location::geometry) AS lng,
  ST_Y(r.location::geometry) AS lat,
  -- 菜系/形式数组
  (SELECT array_agg(c.name ORDER BY rc.is_primary DESC, c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='菜系') AS cuisine_arr,
  (SELECT array_agg(c.name ORDER BY c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='形式') AS form_arr,
  -- 当前有效荣誉
  (SELECT jsonb_agg(jsonb_build_object(
      'award_type', a.award_type, 'level', a.level,
      'year', a.year, 'source_name', a.source_name)
    ORDER BY a.year DESC NULLS LAST)
   FROM restaurant_awards a
   WHERE a.restaurant_id=r.id AND a.is_current=true) AS awards,
  -- 当前主厨
  (SELECT jsonb_agg(jsonb_build_object(
      'name', ch.name, 'title', ch.title, 'role', rc2.role)
    ORDER BY rc2.is_current DESC)
   FROM restaurant_chefs rc2 JOIN chefs ch ON ch.id=rc2.chef_id
   WHERE rc2.restaurant_id=r.id AND rc2.is_current=true) AS chefs,
  -- 最近 5 条有效评价
  (SELECT jsonb_agg(jsonb_build_object(
      'author', rv.author_name, 'rating', rv.aspect_taste,
      'source', rv.source_platform, 'url', rv.source_url,
      'visit_date', rv.visit_date, 'excerpt', left(rv.content,120))
    ORDER BY rv.visit_date DESC NULLS LAST)
   FROM (SELECT * FROM reviews
         WHERE restaurant_id=r.id AND review_kind='diner'
           AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
         ORDER BY visit_date DESC NULLS LAST LIMIT 5) rv) AS recent_reviews
FROM restaurants r;

GRANT SELECT ON restaurant_detail_view TO anon, authenticated;
```

### B4.2 只读视图：`feed_view`（扩展现有 v_feed_recent）

```sql
CREATE OR REPLACE VIEW feed_view
WITH (security_invoker = on) AS
SELECT fe.id, fe.scope, fe.category, fe.title, fe.summary, fe.event_date,
       fe.restaurant_id, fe.related_restaurant_id, fe.chef_id,
       r.name AS restaurant_name,
       ch.name AS chef_name,
       fe.district, fe.confidence, fe.status
FROM food_events fe
LEFT JOIN restaurants r ON r.id = fe.restaurant_id
LEFT JOIN chefs ch ON ch.id = fe.chef_id
WHERE fe.event_date IS NOT NULL AND fe.status = 'verified'
ORDER BY fe.event_date DESC, fe.id DESC;

GRANT SELECT ON feed_view TO anon, authenticated;
```

### B4.3 搜索 RPC：`search_restaurants`

前端列表/地图统一入口，支持 facet 筛选 + 排序 + 分页。

```sql
CREATE OR REPLACE FUNCTION search_restaurants(
  p_query      TEXT DEFAULT NULL,         -- 店名/别名搜索
  p_cuisine_id INT DEFAULT NULL,          -- 菜系叶子 id
  p_district   TEXT DEFAULT NULL,
  p_tier       TEXT DEFAULT NULL,
  p_price_min  INT DEFAULT NULL,
  p_price_max  INT DEFAULT NULL,
  p_lat        FLOAT DEFAULT NULL,         -- 地图附近
  p_lng        FLOAT DEFAULT NULL,
  p_radius_m   INT DEFAULT 3000,
  p_min_conf   NUMERIC DEFAULT 0.0,        -- 置信度下限（默认 0.2 前端传）
  p_sort_by    TEXT DEFAULT 'score_total', -- score_total/confidence/price/review_count
  p_limit      INT DEFAULT 30,
  p_offset     INT DEFAULT 0
) RETURNS SETOF restaurant_detail_view AS $$
  SELECT dv.*
  FROM restaurant_detail_view dv
  WHERE dv.status = 'active'
    AND dv.review_confidence >= p_min_conf
    AND (p_query IS NULL OR dv.search_vector @@ plainto_tsquery('simple', p_query)
         OR dv.aliases @> ARRAY[p_query])
    AND (p_cuisine_id IS NULL OR EXISTS (
          SELECT 1 FROM restaurant_cuisines rc
          WHERE rc.restaurant_id=dv.id AND rc.cuisine_id=p_cuisine_id))
    AND (p_district IS NULL OR dv.district = p_district)
    AND (p_tier IS NULL OR dv.tier = p_tier)
    AND (p_price_min IS NULL OR dv.price_avg >= p_price_min)
    AND (p_price_max IS NULL OR dv.price_avg <= p_price_max)
    AND (p_lat IS NULL OR p_lng IS NULL OR
         dv.location <-> ST_SetSRID(ST_MakePoint(p_lng, p_lat),4326) < p_radius_m)
  ORDER BY
    CASE WHEN p_sort_by='score_total'   THEN dv.score_total END DESC NULLS LAST,
    CASE WHEN p_sort_by='confidence'    THEN dv.review_confidence END DESC,
    CASE WHEN p_sort_by='price'         THEN dv.price_avg END ASC,
    CASE WHEN p_sort_by='review_count'  THEN dv.review_count END DESC,
    dv.id
  LIMIT p_limit OFFSET p_offset;
$$ LANGUAGE sql STABLE;

GRANT EXECUTE ON FUNCTION search_restaurants(TEXT,INT,TEXT,TEXT,INT,INT,FLOAT,FLOAT,NUMERIC,TEXT,INT,INT)
  TO anon, authenticated;
```

> 注：PostGIS `<->` 是距离运算符（geography 下单位米）。实际部署时 `restaurant_detail_view` 是视图，`<->` 在视图列上可用。

---

## B5. 迁移策略

### B5.1 新迁移文件：`005_scoring_v3.sql`

**不修改已执行的 004**。所有 v3 变更走新文件，幂等可重跑。

### B5.2 幂等设计原则

- 所有 `CREATE TABLE` → `CREATE TABLE IF NOT EXISTS`
- 所有 `ALTER TABLE ADD COLUMN` → `ADD COLUMN IF NOT EXISTS`
- 所有 `CREATE INDEX` → `CREATE INDEX IF NOT EXISTS`
- 所有 `CREATE FUNCTION` → `CREATE OR REPLACE FUNCTION`
- 所有 `CREATE TRIGGER` → `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`
- CHECK 约束 → `DO $$ BEGIN IF NOT EXISTS ... END $$` 包裹
- 视图 → `CREATE OR REPLACE VIEW`
- 插入字典数据 → `ON CONFLICT DO NOTHING`

### B5.3 数据回填顺序

```
1. ALTER TABLE 加新列（taste_prior_source / soft_ad_flag）
2. 升级 derive_restaurant() 权重（0.35/0.25/0.25/0.15）
3. 升级 recalc_taste_for()（品类先验 + 上溯）
4. 新建 recalc_endorsement_for() + awards 触发器
5. 新建索引（部分索引 + GIN aliases）
6. 新建视图 restaurant_detail_view / feed_view
7. 新建 RPC search_restaurants
8. 全量回填：
   - SELECT recalc_taste_all();        -- 重算所有店 taste/confidence
   - SELECT recalc_endorsement_all();  -- 重算所有店 endorsement（awards 为空则 0）
9. 验证（见 B5.5）
```

### B5.4 回滚方案

v3 的变更都是**函数/触发器/视图/索引**，不破坏表结构：

- 回滚权重：把 `derive_restaurant()` 改回 002 旧版（0.4/0.3/0.2/0.1）。
- 回滚 taste 算法：把 `recalc_taste_for` 换回 004 版本（全局先验 C=70）。
- 回滚 endorsement：删除 awards 触发器，恢复人工 curate。
- 新索引：`DROP INDEX IF EXISTS`。
- 新列：`ALTER TABLE DROP COLUMN`（新列无数据时安全）。
- **表结构本身不动**，所以回滚风险低。

### B5.5 验证 SQL（执行后独立跑）

```sql
-- 1. 新列存在
SELECT column_name FROM information_schema.columns
  WHERE table_name='restaurants' AND column_name IN ('taste_prior_source','soft_ad_flag');

-- 2. 触发器存在
SELECT tgname FROM pg_trigger
  WHERE tgname IN ('trg_reviews_taste','trg_awards_endorsement','trg_restaurants_derive');

-- 3. 函数存在
SELECT proname FROM pg_proc
  WHERE proname IN ('recalc_taste_for','recalc_taste_all','recalc_endorsement_for','cuisine_prior','search_restaurants');

-- 4. 抽样核对：5 家店 taste/confidence 已算
SELECT id, name, score_taste, review_count, review_confidence
FROM restaurants WHERE status='active'
ORDER BY review_confidence DESC NULLS LAST LIMIT 10;

-- 5. 低置信店（<0.2）数量
SELECT count(*) FROM restaurants WHERE review_confidence < 0.2;

-- 6. score_total 口径漂移检查（应为 0）
SELECT count(*) FROM restaurants
WHERE score_total IS NOT NULL
  AND abs(score_total - greatest(0,least(100,
      round(0.35*score_taste+0.25*score_objective+0.25*score_diner
            +0.15*score_endorsement-coalesce(soft_ad_penalty,0),1)))) > 0.1;
```

---

## B6. 性能与扩展

### B6.1 1497 家餐厅的查询性能

- 当前数据量极小（restaurants 1497、RC 约 1.4 万、reviews 当前近空、awards/chefs/events 近空）。
- 列表页即使全表 seq scan 也 <10ms。上述索引是为增长到 **1–2 万店、10 万条评价**预留。
- 分页：`search_restaurants` RPC 强制 LIMIT/OFFSET，前端不允许拉全量。1497 店 × 30/页 = 50 页，无深翻页问题。
- 计数优化：不精确 COUNT（前端用「共约 N 家」），避免每次列表都 `SELECT count(*)` 全表扫描。需要精确计数时走 `EXPLAIN` 估算或物化 `pg_class.reltuples`。

### B6.2 restaurant_cuisines 约 1.4 万行

- 客户端（Next.js）分页时通过 PostgREST 或 RPC，不一次性拉全量。
- `idx_rc_cuisine(cuisine_id)` + `idx_rc_restaurant(restaurant_id)` 两个方向都有索引，双向 JOIN 快。
- 新增 `(cuisine_id, is_primary DESC)` 让「取某菜系下主店」查询覆盖索引。

### B6.3 Supabase 连接池与 RPC

- Supabase 连接池（PgBouncer）transaction 模式：短连接友好，不要在前端保持长连接。
- **列表/搜索走 RPC**（`search_restaurants`）而非 PostgREST 裸查视图——视图里有子查询聚合（awards/chefs/recent_reviews），裸查会对每行做子查询，RPC 可以一次性用 JOIN LATERAL 优化。
- **详情页**走 PostgREST 直接查 `restaurant_detail_view?id=eq.X`（单店无性能问题）。
- service_role 写库走 `upsert_restaurant` RPC（002 已有），不绕过触发器。

### B6.4 中文全文搜索方案

**现状**：`search_vector` 用 `to_tsvector('simple', ...)`，对中文不分词——整段中文被当作一个 token，只能前缀匹配，不能子串搜索。

**Supabase 现实**：
- Supabase 默认扩展列表含 `pg_trgm`、`unaccent`、`postgis`。
- `zhparser` / `pg_jieba` 是 PostgreSQL 中文分词扩展，**需要编译安装，Supabase 共享实例不支持**（除非提工单申请，大概率被拒）。

**推荐方案（务实）**：
1. **保留 `simple` 配置的 search_vector**（店名/英文名/拼音前缀搜索够用）。
2. **新增 pg_trgm GIN 索引**做中文模糊子串搜索：

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_rest_name_trgm
  ON restaurants USING GIN (lower(name) gin_trgm_ops);
```

3. 搜索时双路并用：
   - `search_vector @@ plainto_tsquery('simple', q)` — 精确/前缀（店名、英文名）
   - `lower(name) % q` 或 `lower(name) ILIKE '%q%'` — trigram 模糊（中文子串）
   - `aliases @> ARRAY[q]` — 别名命中

4. **不引入 zhparser**——在 1497 店规模下，trigram 模糊 + 别名数组的召回率已足够；真要上中文分词等数据量到 5 万+再考虑自建 Postgres。

---

# 附录 D. 完整可执行 SQL（005_scoring_v3.sql 草案）

> 以下代码块可直接按顺序粘贴到 Supabase SQL Editor 执行。幂等可重跑。

```sql
-- =====================================================================
-- 005_scoring_v3.sql — 评分引擎 v3 + 数据库架构升级
-- 幂等可重跑；前置：001+002+003+004 已执行
-- =====================================================================

-- BATCH 1 — restaurants 加 v3 新列
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS taste_prior_source TEXT;
ALTER TABLE restaurants ADD COLUMN IF NOT EXISTS soft_ad_flag TEXT
  DEFAULT 'none';

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_rest_softadflag') THEN
    ALTER TABLE restaurants ADD CONSTRAINT ch_rest_softadflag
      CHECK (soft_ad_flag IS NULL OR soft_ad_flag IN ('none','suspected','confirmed'));
  END IF;
END $$;

-- awards award_type 枚举 CHECK
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ch_awards_type') THEN
    ALTER TABLE restaurant_awards ADD CONSTRAINT ch_awards_type
      CHECK (award_type IN ('michelin_star','bib_gourmand','black_pearl','media_show','other_list'));
  END IF;
END $$;

-- awards 唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_awards_rest_type_year
  ON restaurant_awards (restaurant_id, award_type, COALESCE(year,0));

-- BATCH 2 — 升级综合分权重（0.35/0.25/0.25/0.15）
CREATE OR REPLACE FUNCTION derive_restaurant() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS NULL THEN NEW.status := 'active'; END IF;
  NEW.updated_at := now();
  IF NEW.price_avg IS NOT NULL THEN
    NEW.tier := tier_for_price(NEW.price_avg);
  END IF;
  IF NEW.score_objective IS NULL OR NEW.score_diner IS NULL
     OR NEW.score_taste IS NULL OR NEW.score_endorsement IS NULL THEN
    NEW.score_total := NULL;
  ELSE
    NEW.score_total := greatest(0, least(100, round(
        0.35*NEW.score_taste
      + 0.25*NEW.score_objective
      + 0.25*NEW.score_diner
      + 0.15*NEW.score_endorsement
      - coalesce(NEW.soft_ad_penalty,0), 1)));
  END IF;
  RETURN NEW;
END $$;

-- BATCH 3 — 品类先验函数（含上溯）
CREATE OR REPLACE FUNCTION cuisine_prior(p_rest INTEGER)
RETURNS TABLE(c_prior numeric, v_prior numeric) AS $$
DECLARE
  v_leaf_id INTEGER;
BEGIN
  SELECT c.id INTO v_leaf_id
  FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
  WHERE rc.restaurant_id=p_rest AND c.dimension='菜系'
  ORDER BY rc.is_primary DESC, c.id LIMIT 1;

  RETURN QUERY
  WITH RECURSIVE chain AS (
    -- 叶子层
    SELECT c.id AS cuisine_id, c.name::text AS lvl, c.parent_category::text AS parent, 1 AS depth
    FROM cuisines c WHERE c.id = v_leaf_id
    UNION ALL
    -- 上一层：按父类名回查 cuisines 拿到祖父类，才能继续上溯
    SELECT NULL, ch.parent, c2.parent_category::text, ch.depth+1
    FROM chain ch
    LEFT JOIN cuisines c2 ON c2.name = ch.parent AND c2.dimension = '菜系'
    WHERE ch.parent IS NOT NULL
  ),
  stats AS (
    SELECT ch.depth,
      (SELECT COALESCE(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
         * (COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total)-1)/4.0*100
       ) / NULLIF(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
       ),0), 70.0)
       FROM reviews rv
       JOIN restaurant_cuisines rc2 ON rc2.restaurant_id=rv.restaurant_id
       JOIN cuisines c2 ON c2.id=rc2.cuisine_id
       WHERE rv.review_kind='diner'
         AND COALESCE(rv.is_fake_suspect,false)=false
         AND rv.is_hidden=false
         AND COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total) IS NOT NULL
         AND (ch.cuisine_id IS NOT NULL AND c2.id=ch.cuisine_id
              OR ch.cuisine_id IS NULL AND c2.parent_category=ch.lvl)
      ) AS c_val,
      (SELECT COALESCE(SUM(
         POWER(0.5,(CURRENT_DATE-COALESCE(rv.visit_date,rv.created_at)::DATE)/180.0)
       ),0)
       FROM reviews rv
       JOIN restaurant_cuisines rc2 ON rc2.restaurant_id=rv.restaurant_id
       JOIN cuisines c2 ON c2.id=rc2.cuisine_id
       WHERE rv.review_kind='diner'
         AND COALESCE(rv.is_fake_suspect,false)=false
         AND rv.is_hidden=false
         AND COALESCE(rv.aspect_taste,rv.rating_taste,rv.rating_total) IS NOT NULL
         AND (ch.cuisine_id IS NOT NULL AND c2.id=ch.cuisine_id
              OR ch.cuisine_id IS NULL AND c2.parent_category=ch.lvl)
      ) AS v_val
    FROM chain ch
  )
  SELECT s.c_val, s.v_val FROM stats s
  ORDER BY (s.v_val >= 20) DESC, s.depth ASC LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

-- BATCH 4 — 单店口味重算（贝叶斯收缩到品类先验）
CREATE OR REPLACE FUNCTION recalc_taste_for(p_rest INTEGER) RETURNS void AS $$
DECLARE
  c_half_life CONSTANT numeric := 180;
  m           CONSTANT numeric := 8;
  v_R numeric; v_v numeric; v_cnt int; v_C numeric;
BEGIN
  SELECT cp.c_prior INTO v_C FROM cuisine_prior(p_rest) cp;

  WITH eff AS (
    SELECT (COALESCE(aspect_taste,rating_taste,rating_total)-1)/4.0*100 AS q,
           POWER(0.5,(CURRENT_DATE-COALESCE(visit_date,created_at)::DATE)/c_half_life) AS w
    FROM reviews
    WHERE restaurant_id=p_rest AND review_kind='diner'
      AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
      AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL
  )
  SELECT SUM(w*q)/NULLIF(SUM(w),0), SUM(w), COUNT(*)
    INTO v_R, v_v, v_cnt FROM eff;

  IF v_v > 0 THEN
    UPDATE restaurants SET
      score_taste = ROUND((v_v/(v_v+m))*v_R + (m/(v_v+m))*v_C, 2),
      review_count = v_cnt,
      review_confidence = ROUND(v_v/(v_v+m), 3)
    WHERE id = p_rest;
  ELSE
    UPDATE restaurants SET review_count=0, review_confidence=0 WHERE id=p_rest;
  END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_taste_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_taste_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

-- BATCH 5 — 背书分自动派生
CREATE OR REPLACE FUNCTION recalc_endorsement_for(p_rest INTEGER) RETURNS void AS $$
DECLARE v_endorse numeric;
BEGIN
  SELECT MAX(CASE
    WHEN award_type='michelin_star' AND level LIKE '%三%' THEN 100
    WHEN award_type='michelin_star' AND level LIKE '%二%' THEN 90
    WHEN award_type='michelin_star' AND level LIKE '%一%' THEN 80
    WHEN award_type='black_pearl' AND level LIKE '%三%' THEN 90
    WHEN award_type='black_pearl' AND level LIKE '%二%' THEN 75
    WHEN award_type='black_pearl' AND level LIKE '%一%' THEN 60
    WHEN award_type='bib_gourmand' THEN 65
    WHEN award_type='media_show' THEN 50
    WHEN award_type='other_list' THEN 40
    ELSE 40 END) INTO v_endorse
  FROM restaurant_awards
  WHERE restaurant_id=p_rest AND is_current=true;

  UPDATE restaurants SET score_endorsement = COALESCE(v_endorse, 0)
  WHERE id=p_rest;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalc_endorsement_all() RETURNS void AS $$
BEGIN
  PERFORM recalc_endorsement_for(id) FROM restaurants;
END;
$$ LANGUAGE plpgsql;

-- BATCH 6 — 触发器
CREATE OR REPLACE FUNCTION trg_reviews_taste() RETURNS trigger AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    PERFORM recalc_taste_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_taste_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_reviews_taste ON reviews;
CREATE TRIGGER trg_reviews_taste
  AFTER INSERT OR UPDATE OR DELETE ON reviews
  FOR EACH ROW EXECUTE FUNCTION trg_reviews_taste();

CREATE OR REPLACE FUNCTION trg_awards_endorsement() RETURNS trigger AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    PERFORM recalc_endorsement_for(OLD.restaurant_id);
  ELSE
    PERFORM recalc_endorsement_for(NEW.restaurant_id);
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_awards_endorsement ON restaurant_awards;
CREATE TRIGGER trg_awards_endorsement
  AFTER INSERT OR UPDATE OR DELETE ON restaurant_awards
  FOR EACH ROW EXECUTE FUNCTION trg_awards_endorsement();

-- BATCH 7 — 索引
CREATE INDEX IF NOT EXISTS idx_rest_list
  ON restaurants (score_total DESC) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_rc_cuisine_primary
  ON restaurant_cuisines (cuisine_id, is_primary DESC);
CREATE INDEX IF NOT EXISTS idx_rest_aliases ON restaurants USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_reviews_effective
  ON reviews (restaurant_id, visit_date DESC)
  WHERE review_kind='diner'
    AND COALESCE(is_fake_suspect,false)=false
    AND is_hidden=false
    AND COALESCE(aspect_taste,rating_taste,rating_total) IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rest_district_tier
  ON restaurants (district, tier, score_total DESC) WHERE status='active';

-- pg_trgm（中文模糊搜索）
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_rest_name_trgm
  ON restaurants USING GIN (lower(name) gin_trgm_ops);

-- BATCH 8 — 视图
CREATE OR REPLACE VIEW restaurant_detail_view
WITH (security_invoker=on) AS
SELECT r.*,
  ST_X(r.location::geometry) AS lng,
  ST_Y(r.location::geometry) AS lat,
  (SELECT array_agg(c.name ORDER BY rc.is_primary DESC, c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='菜系') AS cuisine_arr,
  (SELECT array_agg(c.name ORDER BY c.name)
   FROM restaurant_cuisines rc JOIN cuisines c ON c.id=rc.cuisine_id
   WHERE rc.restaurant_id=r.id AND c.dimension='形式') AS form_arr,
  (SELECT jsonb_agg(jsonb_build_object('award_type',a.award_type,'level',a.level,'year',a.year)
                    ORDER BY a.year DESC NULLS LAST)
   FROM restaurant_awards a WHERE a.restaurant_id=r.id AND a.is_current=true) AS awards,
  (SELECT jsonb_agg(jsonb_build_object('name',ch.name,'title',ch.title,'role',rc2.role))
   FROM restaurant_chefs rc2 JOIN chefs ch ON ch.id=rc2.chef_id
   WHERE rc2.restaurant_id=r.id AND rc2.is_current=true) AS chefs,
  (SELECT jsonb_agg(jsonb_build_object('author',rv.author_name,'rating',rv.aspect_taste,
       'source',rv.source_platform,'url',rv.source_url,'visit_date',rv.visit_date,
       'excerpt',left(rv.content,120)))
   FROM (SELECT * FROM reviews
         WHERE restaurant_id=r.id AND review_kind='diner'
           AND COALESCE(is_fake_suspect,false)=false AND is_hidden=false
         ORDER BY visit_date DESC NULLS LAST LIMIT 5) rv) AS recent_reviews
FROM restaurants r;
GRANT SELECT ON restaurant_detail_view TO anon, authenticated;

CREATE OR REPLACE VIEW feed_view
WITH (security_invoker=on) AS
SELECT fe.id, fe.scope, fe.category, fe.title, fe.summary, fe.event_date,
       fe.restaurant_id, fe.related_restaurant_id, fe.chef_id,
       r.name AS restaurant_name, ch.name AS chef_name,
       fe.district, fe.confidence, fe.status
FROM food_events fe
LEFT JOIN restaurants r ON r.id=fe.restaurant_id
LEFT JOIN chefs ch ON ch.id=fe.chef_id
WHERE fe.event_date IS NOT NULL AND fe.status='verified'
ORDER BY fe.event_date DESC, fe.id DESC;
GRANT SELECT ON feed_view TO anon, authenticated;

-- BATCH 9 — 回填（执行一次）
-- SELECT recalc_taste_all();
-- SELECT recalc_endorsement_all();

-- =====================================================================
-- 验证
-- =====================================================================
-- SELECT id,name,score_taste,review_count,review_confidence
--   FROM restaurants WHERE status='active'
--   ORDER BY review_confidence DESC NULLS LAST LIMIT 10;
-- SELECT count(*) FILTER (WHERE review_confidence<0.2) AS low_conf,
--        count(*) FILTER (WHERE review_confidence>=0.5) AS high_conf,
--        count(*) AS total FROM restaurants;
```

---

## 设计要点总结

1. **score_taste 是唯一核心**：从真实堂食评价（diner + 非软广 + 未隐藏）经时间衰减加权 → 贝叶斯收缩到品类先验 → 落库。服务/等位/环境/性价比差评不扣 taste。
2. **置信度是一等公民**：review_confidence 显式暴露给前端，<0.2 打「评价尚少」，不冒进。
3. **派生数据全在数据库**：taste 由 reviews 触发器算、endorsement 由 awards 触发器算、total 由 BEFORE 触发器算。无手填路径。
4. **迁移幂等可重跑**：005 不破坏 004，所有 DDL 用 IF NOT EXISTS / DO 判存。
5. **性能为增长预留**：1497 店当前无压力，部分索引 + GIN trigram + PostGIS GiST 覆盖列表/地图/搜索三模式。
6. **中文搜索务实**：Supabase 不支持 zhparser，用 pg_trgm + aliases 数组替代，不强行装分词扩展。

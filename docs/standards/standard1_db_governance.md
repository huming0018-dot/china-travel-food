# 规范1 · 数据库架构与治理标准

> 唯一权威 DB 规范；机器可读版见 `db_schema_spec.json`，校验脚本 `cloud/validate_schema.py`（非阻断）。
> 上位契约：north-star A2 真实可溯、P2 事实主张、A6 闭环自检。

## 1. 表登记（反向读取线上库）

| 表 | 用途 | 责任窗口 | 主键 | 关系 |
|---|---|---|---|---|
| restaurants | 门店主表 | 采集/reconcile | id (BIGSERIAL) | 被 reviews/awards/chefs/food_events 引用 |
| reviews | 原始口味证据 | Apify/点评采集 | id | -> restaurants.id |
| diner_seed_labels | 人工 ground truth | 用户标注 | (restaurant_id, labeler) | -> restaurants.id |
| restaurant_awards | 榜单/奖项 | 权威对账 | id | -> restaurants.id |
| restaurant_chefs | 主厨关联 | chef_tracker | id | -> restaurants.id |
| food_events | 事件（新开/快闪/联名） | 新闻/采集 | id | -> restaurants.id |
| food_kol_watchlist / mentions | KOL 追踪 | kol_monitor | id | mentions -> watchlist.id |
| food_kol_identity | KOL 平台身份 | kol_cross | id | -> watchlist.id |

## 2. 字段分层法

| 层 | 含义 | 示例 | 治理 |
|---|---|---|---|
| 原始证据 | 平台直接采集 | reviews.content/aspect_taste/source_url | 只读追加，不覆盖 |
| 启发式先验 | LLM/规则推断 | chain_type, central_kitchen, premade_risk | 必带 confidence+source_url |
| 计算派生 | 公式/模型输出 | curate_score, curate_badge, score_* | 由 reconcile 重算 |
| 人工 ground truth | 人工标注 | diner_seed_labels.tier/taste | 只读，用户裁定 |

**每个非平凡值必须带**：source_url + confidence + captured_at。无证据不写。

## 3. 枚举注册表（以 CHECK 约束为准）

| 字段 | 枚举值 |
|---|---|
| restaurants.chain_type | 独立店 / 小型连锁 / 大型连锁 / 资本化连锁 |
| restaurants.central_kitchen | 无 / 疑似 / 确认 |
| restaurants.premade_risk | 无 / 低 / 疑似 / 高 |
| restaurants.food_safety | 无 / 疑似 / 确认 |
| restaurants.tier（全局，触发器据 price_avg 派生） | 经济 / 平价 / 中档 / 高档 / 奢华 |
| restaurants.price_band（场景内绝对 1–5，边界 P25/50/75/90） | 1 / 2 / 3 / 4 / 5 |
| restaurants.price_position（场景内相对分位，P20/40/60/80） | 入门 / 主流 / 进阶 / 高端 / 旗舰 |
| restaurants.status | active / closed / relocated |
| diner_seed_labels.tier | must_eat / worth_eating / average |

价位三字段定义（回答「何为旗舰/进阶」，均绑定该场景真实数值，非主观）：
- `tier`＝跨场景全局档，由触发器按 price_avg 全局分布派生（经济≈≤45 / 平价 / 中档 / 高档 / 奢华≥≈500）；
- `price_band`＝同场景内绝对档，边界取该场景 price_avg 的 P25/P50/P75/P90（取整 5）；
- `price_position`＝同场景内相对位置，P20/40/60/80 切 入门/主流/进阶/高端/旗舰；
  非正餐（快餐小吃/咖啡茶饮/面包/甜品/酒吧）各用各自分布，不套正餐。

禁临时字符串；新增枚举走迁移 + CHECK。

## 3.1 单写入者与冗余字段停用（多窗口唯一来源）

每个决策/派生字段只有一个写入者，其他窗口只读，避免多窗口写冲突：

| 字段 | 唯一写入者 | 说明 |
|---|---|---|
| chain_type / central_kitchen / production_model / is_reheat_served | production_model_probe → gate_apply | 出餐方式链 |
| premade_risk / food_safety / soft_ad_flag / soft_ad_penalty | gate_apply（findings 门） | 风险/软广 |
| price_band / price_position | price_realign | 双轨价位 |
| tier | DB 触发器 tier_for_price | 脚本不写 |
| score_taste / score_diner / score_endorsement / score_objective | scoring_engine | 组件分 |
| score_total / score_evidence_level | DB 触发器 trg_restaurants_derive | 组件 blend |
| is_curated / curate_badge / curate_reason | curate_gate | 精选唯一决策门 |

停用（停止写入，只读兼容，后续迁移删除；以 canonical 字段为准）：
- `central_kitchen_prior` → central_kitchen；`premade_prior` → premade_risk；
- `astroturf_score`（全 NULL 未启用）→ soft_ad_flag / soft_ad_penalty；
- `curate_confidence`、`curate_score` → curate_badge + curate_reason；
- `price_range`、`price_scene`（旧）→ price_band / price_position；
- `score_evidence`（旧）→ score_evidence_level。

## 4. 身份/去重

- restaurant_id 为权威；
- name↔rid 闸门（findings_extractor 已固化）；
- 分店锚定：brand_id + branch_tag，同名异址保留；
- reviews 去重：(platform, post_id)；
- 无证据不建店（宁空不假）。

## 5. 迁移治理

- 编号迁移 db/migrations/NNN_*.sql，集中 apply；
- 禁临时 ALTER；向后兼容（IF NOT EXISTS）；
- PATCH 白名单列：chain_type/central_kitchen/premade_risk/price_avg/investor_info/is_curated/curate_*；
- 锁定字段：phone/lat/lng/opening_hours 不自动 PATCH；
- PII 最小化：不采私信，评论摘要≤200字+URL。

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
| restaurants.price_position | 经济 / 平价 / 中端 / 高端 / 奢华 |
| restaurants.status | active / closed / relocated |
| diner_seed_labels.tier | must_eat / worth_eating / average |

禁临时字符串；新增枚举走迁移 + CHECK。

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

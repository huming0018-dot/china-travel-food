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
| restaurants.price_band（场景内 1–5，由已批准阈值配置派生） | 1 / 2 / 3 / 4 / 5 |
| restaurants.price_position（price_band 对应标签，不另算分位） | 经济 / 平价 / 中端 / 高端 / 奢华 |
| restaurants.status | active / closed / relocated |
| diner_seed_labels.tier | must_eat / worth_eating / average |

价位三字段定义（2026-09-30 五档标准；旧双轨定义停用）：
- `tier`＝跨场景全局档，由触发器按 price_avg 全局分布派生（经济≈≤45 / 平价 / 中档 / 高档 / 奢华≥≈500）；
- `price_band`＝同场景内档位，以 `price_band_thresholds` 的 lo 含、hi 不含区间为唯一运行时权威；
- `price_position`＝band 1–5 对应 经济/平价/中端/高端/奢华，与 band 同口径；
- 重新标定按各场景 active 且有效整数 price_avg 的 P20/P40/P70/P90，等于分位值留在较低档。
  整数价格用 `floor(分位值)+1` 表示 hi 不含边界，不再取整到 5。非正餐各算各自分布。
- 日常 `price_realign.py` 只读阈值，不自动重算/改写配置。阈值重标定必须独立审阅，
  与受影响餐厅在同一个数据库事务提交；不能先 PATCH 阈值、再逐店 PATCH。
- 重标定前必须停掉所有价格写入任务并等在途运行退出，完成事务及回读后再恢复。
  REST 的阈值检查与餐厅 PATCH 不是原子操作；仅靠行原值条件和最终回读不能消除该并发窗口。
- 默认 dry-run，巡逻也默认只检测价格。`--apply` 还必须在数据变更单独获批后设置
  `FOOD_PRICE_ALIGNMENT_WRITES_ENABLED=1` 才可写入；代码发布不代表允许修正生产数据。
  `--apply` 只对齐 active 且价格/场景有效的餐厅。未知场景/缺价列出并保留，
  无效阈值/价格中止。逐行带原值条件更新并回读，失败非零退出，先前成功行可能已提交。
  `--snapshot FILE --report FILE` 支持离线审阅，`--snapshot` 与 `--apply` 互斥。

禁临时字符串；新增枚举走迁移 + CHECK。

## 3.1 单写入者与冗余字段停用（多窗口唯一来源）

每个决策/派生字段只有一个写入者，其他窗口只读，避免多窗口写冲突：

| 字段 | 唯一写入者 | 说明 |
|---|---|---|
| chain_type / central_kitchen / production_model / is_reheat_served | production_model_probe → gate_apply | 出餐方式链 |
| premade_risk / food_safety / soft_ad_flag / soft_ad_penalty | gate_apply（findings 门） | 风险/软广 |
| price_band / price_position | price_realign | 已批准阈值对应的统一五档 |
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

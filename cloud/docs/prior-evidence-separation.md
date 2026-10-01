# 先验 / 证据 分离约定（Prior–Evidence Separation）

> 配套：`db/migrations/024_prior_evidence_separation.sql`、`cloud/prior_separate.py`。
> 上位契约：`fact-evidence-mechanism.md`（四轴独立、硬标签必须有 source_url）。
> 确立于 2026-10-01。

## 一、为什么要分离

历史上 `central_kitchen='疑似'`、`premade_risk='低'` 两个桶里，**绝大多数是 chain_audit
按连锁档位（小型连锁 / REGIONAL_HINT 词表）批量推的启发式先验**，没有逐店 source_url。
但这些值和真证据写在同一列 `central_kitchen / premade_risk`，导致：

- `reconcile.py`（精选硬门）把未取证的「疑似」当成负向信号；
- `curate_v4.py` 评分把「低 / 疑似」映射成固定扣分项；
- 本质上是「按连锁规模推断工艺」，违反四轴独立铁律。

而 `central_kitchen='确认'`、`premade_risk='高'` 是有 `fact_claims`（同 type + source_url）
背书的硬证据，必须原样保留、绝不能被清洗误伤。

## 二、两套列、两套消费方

| 类型 | 列 | 含义 | 谁可以消费 |
|---|---|---|---|
| **证据列** | `central_kitchen` / `premade_risk` | 仅当有逐店或品牌证据（`fact_claims` 同 type 且带 `source_url`，或 `findings*.jsonl` 同 rid/field 且带 source_url）时才允许非空 | **硬门**（reconcile 精选移出、goalkeeper、发版审计）**只准读这里** |
| **先验列** | `central_kitchen_prior` / `premade_prior` + `prior_provenance` / `prior_confidence` | 连锁档位推断出的启发式猜测，低置信（≈0.30） | **仅作评分模型弱特征**（curate_score / curate_v4），**禁止进硬门** |

## 三、消费铁律（写代码时必须遵守）

1. **硬门只消费证据列。** `reconcile.py` 里 `central_kitchen=='确认'`、
   `premade_risk=='高'` 的精选移出判断，只读证据列；**永不读 `*_prior`**。
2. **先验列不参与任何硬闸门。** 不得在 goalkeeper、reconcile、发版审计里用
   `central_kitchen_prior / premade_prior` 做「移出 / 拒绝 / 判负」。
3. **先验列是软特征。** 评分模型可以把 `*_prior` 当弱信号，但必须乘低权重并随证据保鲜；
   一旦该店后续取证，证据列覆盖、先验列可留作对照。
4. **硬标签晋升仍走原闸门。** `确认 / 高` 只能由 `fact_verify.py`（claims_seed 取证后）写入，
   禁止由先验或词表直接晋升。

## 四、清理口径（prior_separate.py）

逐行、逐字段独立判定：

- `central_kitchen='确认'` → 永久跳过（硬证据保护）。
- `central_kitchen='疑似'` 且无同 type 证据 → 纯先验：值搬入 `central_kitchen_prior`，
  证据列回置 `无`。
- `central_kitchen='疑似'` 且有证据 → 保留证据列原值。
- `premade_risk='高'` → 永久跳过（硬证据保护）。
- `premade_risk='低'` 且无证据 → 纯先验：值搬入 `premade_prior`，证据列回置 `无`。
- `premade_risk='低'` 且有证据 → 保留证据列原值。
- `premade_risk='疑似'` 不在本轮范围（negative_audit 候选封顶），保持原样。

回写时统一打 `prior_provenance='heuristic'`、`prior_confidence=0.30`。脚本幂等：
已分离行（prior 列非空）自动跳过、不覆盖。

## 五、执行顺序（本轮 dry-run，不 apply）

1. 用户在 Supabase SQL Editor 逐条执行 `024_prior_evidence_separation.sql`（加列 + CHECK）。
2. 容器内先 `python3 -u cloud/prior_separate.py`（dry-run），核对分类计数与样例。
3. 确认无误后才 `--apply`（脚本会先探测 024 列是否存在，缺列即中止）。

## 六、反模式（禁止再犯）

1. 把连锁规模直接写成中央厨房 / 预制的证据值。
2. 用 `*_prior` 列做硬门移出精选。
3. 清洗时触碰 `确认 / 高` 硬标签。
4. 给先验打高置信或伪造 source_url。

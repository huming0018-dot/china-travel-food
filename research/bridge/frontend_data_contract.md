# 前端数据契约 / 最小接线规格（只读审计，不改视觉、暂不合并）

- 审计日期：2026-10-01
- 仓库根：`/Users/deuce/Doubao/chats/2026-09-28/new-chat/china-travel-food`
- 前端根：`app/`（Next.js Pages Router，Supabase JS 直连，无 BFF/聚合层）
- 范围：只做断点审计 + 契约 + 最小接线 diff 规格。**不改视觉、不动 UI 样式、不实际改代码。**

---

## 0. 结论速览（一句话）

前端是 Supabase 直连、`select('*')` 拉全列，所以新列在线路上**已经回来**；真正的断点是**精选层 6 列（021）在 TS 接口与 UI 里零引用**，而"隐藏连锁/预制"按钮绑定的是派生列 `is_chain_standardized`（008），它只在"连锁×中央厨房/预制"为真时才置真——独立店预制高风险不被隐藏，且上游信号一旦为 NULL 派生列即 NULL、按钮等于空转。

---

## 1. 对外数据层：前端/后端 route 怎么查 restaurants

### 1.1 查询点全量清单（grep `.from('restaurants')` 实证）

| # | 文件:行 | 实际 select | 用途 |
|---|---|---|---|
| Q1 | `app/pages/restaurants/index.tsx:116` | `fetchAll<Restaurant>('restaurants', '*', 'id')` | 列表页全量拉取（分页 1000/页） |
| Q2 | `app/pages/index.tsx:43` | `fetchAll<Restaurant>('restaurants', '*', ['status','active'])` | 首页全量（仅 active） |
| Q3 | `app/pages/restaurants/[id].tsx:87` | `supabase.from('restaurants').select('*').eq('id',id).single()` | 详情页单店 |
| Q4 | `app/pages/map.tsx:34,39` | 显式列：`'id,name,name_en,price_scene,price_band,price_avg,address,district,status,location'` | 地图打点（精简列） |
| Q5 | `app/components/FeedSection.tsx:163-165` | `.select('id,name').in('id', ids)` | 事件流补餐厅名（仅 id/name） |
| Q6 | `app/pages/api/sync.ts:63,67` | `.select('*', {count:'exact',head:true})` | 保鲜巡检只数 count，不取行 |

**关键事实**：Q1/Q2/Q3 都是 `select('*')`，所以 `is_curated/curate_badge/curate_score/curate_reason/chain_type/central_kitchen/premade_risk/price_avg/status` 在线路上**都已返回**。不存在"API 漏列"；断点在 TS 类型与 UI 消费层。Q4 是唯一显式列白名单，主动裁掉了连锁/精选列（地图无需，见 §4）。

### 1.2 权威列是否被读（按列逐项）

权威列定义来源：`db/migrations/001_init.sql`、`003_mechanism_v2.sql`、`008_chain_standardized.sql`、`009_price_band_standard.sql`、`016_scoring_v4_alignment.sql`、`021_goalkeeper_curate.sql`。

| 权威列 | DB 定义（文件:行） | TS 接口声明 `app/lib/supabase.ts` | 前端实际读取位置 |
|---|---|---|---|
| `is_curated` bool | `021_goalkeeper_curate.sql:21` | **未声明** | **零引用** |
| `curate_badge` varchar(16)（必吃/值得/精选，NULL=未入选） | `021:22` | **未声明** | **零引用** |
| `curate_score` numeric 0-100 | `021:23` | **未声明** | **零引用**（连 `021:29` 建的索引都没人用） |
| `curate_confidence` numeric 0-1 | `021:24` | **未声明** | **零引用** |
| `curate_reason` text | `021:25` | **未声明** | **零引用** |
| `astroturf_score` numeric 0-1 | `021:26` | **未声明** | **零引用** |
| `chain_type` text enum | `003:19,26-28` | 已声明 `:39` | 仅详情 `[id].tsx:341` InfoRow；列表逻辑**不读** |
| `central_kitchen` text enum（无/疑似/确认） | `003:20,35-36` | **类型错**：声明为 `boolean`（`:40`），DB 实为 text | 详情 `[id].tsx:342` 当字符串渲染；列表逻辑**不读** |
| `premade_risk` text enum（无/低/疑似/高） | `003:21,42-44` | 已声明 `:41` | 列表角标 `index.tsx:829`（仅 `==='高'`）；详情 `[id].tsx:343` |
| `is_chain_standardized` bool generated STORED | `008_chain_standardized.sql:9-16` | 已声明 `:42` | 列表筛选 `index.tsx:331`、列表角标 `:830`、首页 `index.tsx:121` |
| `price_avg` integer | `001_init.sql:45` | 已声明 `:14` | 排序 `index.tsx:322-323`、预算 `:348`、展示 `:854` / `[id].tsx:296` |
| `status` varchar（active/closed） | `001:63` | 已声明 `:33` | 列表过滤 `:330`、首页拉取 `index.tsx:43`、详情 `[id].tsx:185` |
| `score_total` numeric | `001:56`（016 触发器算） | 已声明 `:25` | 默认排序 `index.tsx:321`、首页 picks `index.tsx:102,110,127`、详情 `[id].tsx:312` |
| `score_evidence_level` text | `016:53,56,64,69`（verified/provisional/insufficient） | 已声明 `:32` | 首页"新上好店" `index.tsx:121` |

> 注：全仓 grep `is_curated|curate_badge|curate_score|curate_reason|curate_confidence|astroturf_score` 在 `app/**/*.{ts,tsx}` **0 命中**。精选层（021）是一条完全没接线的死数据。

### 1.3 公共 payload / 视图是否漏权威列

- 前端**没有**走 restaurants 的公共视图，全部直查表 `restaurants`（Q1–Q5）。
- `v_audit_gaps` / `v_data_freshness`（`002_harden.sql:283,327`）只被 `api/sync.ts` 用于巡检 count，且 `REVOKE ... FROM anon`（`002:358-359`），与展示无关。
- `v_feed_recent` 建在 `food_events` 上（`004:248`、`014:36`、`022:49`），不含 restaurants 列。
- **结论：不存在"后端视图把权威列裁掉"的问题；漏列发生在前端 TS 类型 + UI 消费，不在 SQL。**

---

## 2. 筛选 / 排序：按钮到底绑了什么

### 2.1 "隐藏连锁/预制"按钮

- UI：`app/pages/restaurants/index.tsx:576-579`
  ```tsx
  <button onClick={() => setHideChain((v) => !v)} data-active={hideChain} ...>
    隐藏连锁/预制
  </button>
  ```
- state：`index.tsx:110` `const [hideChain, setHideChain] = useState(false);`
- 实际过滤：`index.tsx:331`
  ```tsx
  if (hideChain) result = result.filter((r) => !r.is_chain_standardized || isNonDiner(r));
  ```
- 它读的字段：**`is_chain_standardized`**（008 的 GENERATED STORED 派生列），**不是** `chain_type`/`premade_risk`/`central_kitchen` 本身。
- 派生口径（`008:11-16`）：
  ```sql
  chain_type = '资本化连锁'
  OR ( chain_type IN ('大型连锁','小型连锁')
       AND ( central_kitchen IN ('确认','疑似')
             OR premade_risk IN ('高','疑似','低') ) )
  ```

**是否空转？——不是绑定错字段，但有两层"看起来没联动"的真实原因：**

1. **口径缺口（按钮名大于实际能力）**：按钮叫"隐藏连锁/**预制**"，但 008 只把"连锁 + 中央厨房/预制"判为标准化。一家 `chain_type='独立店'` 且 `premade_risk='高'` 的店，`is_chain_standardized` 为 false，**按钮不会隐藏它**。列表角标 `index.tsx:829` 会给它挂"预制菜"红签，但开关删不掉它。
2. **上游信号为 NULL 时等于空转**：当某店 `chain_type`/`central_kitchen`/`premade_risk` 全为 NULL（尚未打标），生成式表达式 `NULL='资本化连锁' OR (NULL IN (...) AND ...)` 结果是 NULL（不是 false）。前端 `!r.is_chain_standardized` → `!null === true` → 该店被保留。即：**没打标的店永远躲不过这个开关**，用户点了之后若大部分店还没回填连锁信号，列表几乎不变——这就是"按钮空转"的体感根因。
3. 豁免逻辑 `isNonDiner(r)`（`index.tsx:202-205`）按菜系树判定"非正餐"，对咖啡/面包等连锁常态品类放行，符合 008:7 的设计。

### 2.2 排序

- state：`index.tsx:99` `sortBy: 'score' | 'price_asc' | 'price_desc'`
- 实现：`index.tsx:320-325`
  ```tsx
  if (sortBy === 'score') arr.sort((a,b) => (b.score_total||0) - (a.score_total||0));
  else if (sortBy === 'price_asc') arr.sort((a,b) => (a.price_avg??9999) - (b.price_avg??9999));
  else arr.sort((a,b) => (b.price_avg??0) - (a.price_avg??0));
  ```
- 评分排序读 **`score_total`**（016 触发器算的反软广总分）；价格升降读 **`price_avg`**。两列都是权威列，绑定正确。
- **缺口**：精选排序分 `curate_score`（021:23，且建了 `idx_rest_curate_score` 索引 `021:29`）完全没进排序；当前没有"精选优先"这一档。

### 2.3 预算 / 位置 / 菜系筛选

- 预算读 `price_avg`（`index.tsx:347-352`，区间见 `:10-16`），绑定正确。
- 位置读 `district` / `business_area`（`:353-354`）。
- 菜系/标签走 `restaurant_cuisines` 关联表，与 restaurants 列无关。

---

## 3. 列表 vs 详情：各自依赖哪些字段

### 3.1 列表页 `pages/restaurants/index.tsx`
- 拉：`select('*')`（Q1）。
- 行卡片渲染（`RestaurantRows` `:812-862`）实际用到：`name`、`signature_dishes`、`business_area`、`district`、`price_scene`+`price_band`（配合 `price_band_thresholds` 视图）、`price_avg`、`score_total`、`premade_risk==='高'`（红签 `:829`）、`is_chain_standardized`（连锁灰签 `:830`）、菜系 id 标签（米其林 159 / 黑珍珠 160，来自关联表）。
- **不展示也不排序 `is_curated/curate_badge/curate_score`**。精选层在列表页不可见。

### 3.2 详情页 `pages/restaurants/[id].tsx`
- 拉：`select('*')`（Q3）。
- 展示：价格带（`price_scene/price_band` `:286-294`）、`price_avg`（`:296`）、`score_total`（`:312`）、`semantic_description`（`:320`）、InfoRow 组（`:330-343`，含 `chain_type/central_kitchen/premade_risk`）、SCORE_BARS 子分（`:17-22`，读 `score_taste/score_objective/score_diner/score_endorsement`）。
- **不展示 `is_curated/curate_badge/curate_score/curate_reason`**。详情页没有任何"精选/必吃/值得"徽标或入选理由。

### 3.3 首页 `pages/index.tsx`
- "新上好店" `:119-124` 实际口径是 `score_evidence_level==='verified' && is_chain_standardized!==true`，再按 `score_total>=50` 排序取 8。
- "EDITOR'S PICK 高分推荐" `:108-114` 按 `score_total>=50 && review_count>=1` 排序取 6。
- **两处都没用 `is_curated` / `curate_badge` / `curate_score`**。首页文案 `:364` 自称"预制菜、连锁工业化店标注但不进精选"，但这个"精选"目前是 `score_total` 启发式，不是 021 建的精选层。

---

## 4. 断点清单（逐条带证据）

- **B1｜精选层 6 列零消费**：`is_curated/curate_badge/curate_score/curate_confidence/curate_reason/astroturf_score` 在 `app/` 内 0 引用；`lib/supabase.ts:9-52` 的 `Restaurant` 接口也没声明它们。证据：`grep` 全仓 0 命中；定义在 `021_goalkeeper_curate.sql:21-26`。
- **B2｜"编辑推荐/新上好店"仍用旧启发式**：首页 picks 按 `score_total` + `score_evidence_level`（`pages/index.tsx:102,110-114,119-131`），未切到 `is_curated=true` + `curate_score` 排序。
- **B3｜"隐藏连锁/预制"按钮口径不全 + 上游 NULL 时空转**：绑 `is_chain_standardized`（`pages/restaurants/index.tsx:331`），独立店 `premade_risk='高'` 不被隐藏（008 口径 `:11-16`）；上游三信号为 NULL 时派生列 NULL、`!null===true` 导致该开关删不掉未打标店。
- **B4｜排序未接精选分**：列表默认"评分最高"读 `score_total`（`index.tsx:321`），`curate_score` 索引（`021:29`）无人用；没有"精选优先"档。
- **B5｜`central_kitchen` TS 类型错误**：`lib/supabase.ts:40` 声明 `boolean`，DB 实为 text enum `('无','疑似','确认')`（`003:35-36`）；详情 `[id].tsx:342` 却当字符串渲染。类型与数据不一致。
- **B6（轻微，非缺陷）｜地图列白名单裁掉连锁/精选列**：`pages/map.tsx:34` 只取 10 列，不含 `chain_type/premade_risk/is_chain_standardized/is_curated/curate_badge`，地图弹窗无法挂"预制/连锁/精选"签。若暂不改视觉可不动。

---

## 5. 数据契约（单一事实来源：前端只读权威列，不自建状态）

> 以下列以后端 DB 为准。前端不得再用本地启发式另造"精选/连锁"判定；要做的只是把按钮/排序接到这些列上。

### 5.1 restaurants 权威列（前端可读白名单）

| 列 | 类型 | 枚举 / 范围 | 来源 | 前端用途 |
|---|---|---|---|---|
| `id` | int | PK | 001:41 | key/路由 |
| `name`, `name_en` | text | — | 001:42-43 | 展示 |
| `status` | text | `active` / `closed` | 001:63 | 列表/首页过滤 |
| `price_avg` | int? | 0–99999 | 001:45；约束 002:111 | 预算过滤、价格排序、展示 |
| `price_scene` | text? | 正餐/快餐小吃/咖啡茶饮/面包/甜品/酒吧 | 009:36 | 价格带文案 |
| `price_band` | int? | 1–5 | 009:37；约束 009:41 | 价格带配色 |
| `district`, `business_area`, `address` | text? | — | 001:48,002,047 | 位置过滤/展示 |
| `chain_type` | text? | `独立店`/`小型连锁`/`大型连锁`/`资本化连锁` | 003:19；约束 003:27 | 连锁判定（权威源） |
| `central_kitchen` | text? | `无`/`疑似`/`确认` | 003:20；约束 003:35 | 中央厨房判定（权威源，**非 boolean**） |
| `premade_risk` | text? | `无`/`低`/`疑似`/`高` | 003:21；约束 003:43 | 预制判定（权威源） |
| `is_chain_standardized` | bool? | generated STORED（可能为 NULL） | 008:9-16 | 列表隐藏/角标的派生依据 |
| `score_total` | numeric? | 0–100 | 001:56；016 触发器 | 非精选排序兜底 |
| `score_evidence_level` | text? | `verified`/`provisional`/`insufficient` | 016:53,56,64,69 | "新上好店"门槛 |
| **`is_curated`** | bool | 默认 false | **021:21** | **精选层总开关（新增接线）** |
| **`curate_badge`** | text? | `必吃`/`值得`/`精选`，NULL=未入选 | **021:22** | **徽标文案（新增接线）** |
| **`curate_score`** | numeric? | 0–100 | **021:23** | **精选排序键（新增接线）** |
| **`curate_confidence`** | numeric? | 0–1 | **021:24** | （可选）置信度 |
| **`curate_reason`** | text? | 自由文本 | **021:25** | **详情页入选/落选理由（新增接线）** |
| `signature_dishes` | jsonb/text[] | — | 001:52 | 展示/搜索 |
| `location` | geography | — | 001:49 | 地图 |

### 5.2 前端状态纪律
- 列表/首页**不再**用 `score_total>=50` 等启发式冒充"精选"；精选入口一律以 `is_curated=true` 为门槛、`curate_score DESC` 为序。
- 连锁/预制判定以 `chain_type/central_kitchen/premade_risk` 为准，`is_chain_standardized` 只是其派生、可直接读；不要再在前端另写连锁正则。
- `central_kitchen` 一律按 **text 枚举**处理，禁用 boolean。

---

## 6. 最小接线规格（diff 规格，不实际改、不改视觉）

> 原则：只补"读列 + 绑字段"，不新增视觉组件、不改样式类。下列均为**建议改法**，供下一轮落地。

### 6.1 `app/lib/supabase.ts`（先把类型补齐）
在 `Restaurant` 接口（`:9-52`）追加，并修正 `central_kitchen`：

```diff
   chain_type?: string;
-  central_kitchen?: boolean; // 中央厨房
+  central_kitchen?: '无' | '疑似' | '确认' | null; // 中央厨房（DB text 枚举，003）
   premade_risk?: string;
   is_chain_standardized?: boolean | null;
+  // —— 精选层（021），此前前端零引用 ——
+  is_curated?: boolean;            // 是否进入真美食精选
+  curate_badge?: '必吃' | '值得' | '精选' | null;
+  curate_score?: number | null;    // 精选排序分 0-100
+  curate_confidence?: number | null;
+  curate_reason?: string | null;
```

### 6.2 `app/pages/restaurants/index.tsx`（筛选/排序绑定权威列）

(a) 排序键加一档"精选优先"，并让默认评分排序优先用 `curate_score`：
```diff
- const [sortBy, setSortBy] = useState<'score' | 'price_asc' | 'price_desc'>('score');
+ const [sortBy, setSortBy] = useState<'curated' | 'score' | 'price_asc' | 'price_desc'>('curated');

  const doSort = (arr: Restaurant[]) => {
+   if (sortBy === 'curated')
+     arr.sort((a,b) => (Number(b.curate_score)||0) - (Number(a.curate_score)||0));
+   else if (sortBy === 'score') arr.sort((a,b) => (b.score_total||0) - (a.score_total||0));
    else if (sortBy === 'price_asc') arr.sort((a,b) => (a.price_avg??9999) - (b.price_avg??9999));
    else arr.sort((a,b) => (b.price_avg??0) - (a.price_avg??0));
    return arr;
  };
```
并在 `SORTS`（`:515-519`）把 `{ key:'curated', label:'精选优先' }` 放第一位。**不新增样式**，复用现有 `.sort-seg`。

(b) "隐藏连锁/预制"过滤从"只看派生列"扩成"派生列 OR 独立店高预制"，对齐按钮文案：
```diff
- if (hideChain) result = result.filter((r) => !r.is_chain_standardized || isNonDiner(r));
+ if (hideChain) result = result.filter((r) =>
+   (r.is_chain_standardized === true) ? isNonDiner(r)            // 标准化连锁：非正餐豁免，正餐隐藏
+   : (r.premade_risk === '高') ? false                           // 独立店高预制：也隐藏（对齐"预制"二字）
+   : true);
```
> 说明：这仍只读权威列（`is_chain_standardized`/`premade_risk`），不新增前端状态；若产品认为独立店高预制应保留，则不改此条，仅把按钮文案改为"隐藏标准化连锁"。二选一，不双改。

### 6.3 `app/pages/index.tsx`（首页精选切到权威列）
```diff
  const topRestaurants = useMemo(
    () => [...restaurants]
-     .filter((r) => r.score_total != null && r.score_total >= 50 && (r.review_count || 0) >= 1)
-     .sort((a,b) => (b.score_total||0) - (a.score_total||0))
+     .filter((r) => r.is_curated === true)
+     .sort((a,b) => (Number(b.curate_score)||0) - (Number(a.curate_score)||0))
      .slice(0, 6),
    [restaurants]
  );

  const verifiedStores = useMemo(
-   () => restaurants.filter((r) => r.score_evidence_level === 'verified' && r.is_chain_standardized !== true),
+   () => restaurants.filter((r) => r.is_curated === true),
    [restaurants]
  );
```
（"新上好店" `newStores` 仍可保留 `score_total` 兜底排序，但门槛换成 `is_curated`。）

### 6.4 `app/pages/restaurants/[id].tsx`（详情补精选信息，纯展示既有列）
在"基本信息"网格（`:341-343` 附近）追加，复用现有 `<InfoRow>`，不新增样式：
```diff
  {r.chain_type && <InfoRow label="连锁类型" value={r.chain_type} />}
  {r.central_kitchen && <InfoRow label="中央厨房" value={r.central_kitchen} />}
  {r.premade_risk && <InfoRow label="预制菜风险" value={r.premade_risk} />}
+ {r.is_curated && <InfoRow label="精选" value={r.curate_badge || '已入选'} />}
+ {r.curate_reason && <InfoRow label="入选理由" value={r.curate_reason} />}
```

### 6.5 `app/pages/map.tsx`（可选，地图要挂精选/预制签时才动）
```diff
- const cols = 'id,name,name_en,price_scene,price_band,price_avg,address,district,status,location';
+ const cols = 'id,name,name_en,price_scene,price_band,price_avg,address,district,status,location,is_curated,curate_badge,premade_risk,is_chain_standardized';
```
（不改可接受：地图当前不挂这些签。）

---

## 7. 不在本次范围
- 不改任何视觉/样式/文案布局。
- 不写后端补数脚本（`chain_type/central_kitchen/premade_risk` 回填属管线）。
- 不合并代码；本文仅作接线规格。

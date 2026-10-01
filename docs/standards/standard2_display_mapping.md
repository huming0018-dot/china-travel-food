# 规范 2 · 数据库 ↔ 前端显示对应规则（Standard 2：Display Mapping）

> 版本：v0.1（2026-10-01 订立） ｜ 维护者：前端/数据 owner
> 本规范**只立标准 + 提供非阻断生成脚本**。本轮不做视觉改版、不做破坏性变更、不改 live crontab、不动 DB。
> 上位契约：规范1 `standard1_db_governance.md`（DB 权威）；机器可读 schema 见 `db_schema_spec.json`。
> 配套物：非阻断脚本 `cloud/gen_ts_types.py`（默认 dry-run，打印 TS 枚举类型片段，不覆盖现有文件）。
> 凡本仓库未 100% 证实的，标 **【待确认】**，不臆造。

---

## 0. 总原则

1. **单一事实来源**：DB 列 = 权威；前端只读，不在 UI 层另造业务状态或硬编码枚举。展示文案（价位 label、badge 中文）由后端版本化数据 + 确定性函数生成，前端只做映射。
2. **read model = 直查**：前端 Next.js（Root=`app/`）经 Supabase JS 直查表，无 BFF 聚合层。列表/详情用 `select('*')`；地图/卡片摘要用显式列白名单（见 §2）。
3. **空值即"无/独立"**：信号列 NULL 一律按最保守、最不歧视的值处理（见 §3），**禁止**因 NULL 让筛选开关空转。
4. **类型同源**：TS 枚举类型由 `docs/standards/db_schema_spec.json` 生成（`cloud/gen_ts_types.py`），不手维护第二份枚举清单。

---

## 1. UI 元素 → API/read model → DB 列 → 类型/空值 → 筛选/排序

### 1.1 餐厅列表卡片（`app/pages/restaurants/index.tsx`，拉取 `:116` `select('*')`）

| UI 元素 | read model | DB 列 | 类型 / 空值默认 | 筛选/排序行为 |
|---|---|---|---|---|
| 店名 | restaurants | `name` / `name_en` | string 必填 / string? null→不显示 | 搜索 `:335` includes |
| 菜系胶囊 | restaurant_cuisines⨝cuisines | `cuisines.name`（dimension=菜系） | string | 菜系树筛选 `:343-346` |
| 商圈/区 | restaurants | `business_area` / `district` | string? null→占位 | 位置筛选 `:353-354` |
| 招牌菜 | restaurants | `signature_dishes` (jsonb) | string[]? null/非数组→不显示 | 搜索 `:338` |
| 价格带色块+区间 | price_band_thresholds（视图/表，`009`） | `price_scene`+`price_band`→阈值 `lo/hi` | scene text?，band int 1–5?；无阈值→`—` | 价位筛选 BUDGETS `:347-352` 读 `price_avg` |
| 人均 | restaurants | `price_avg` | int? null→`¥—` | 排序 `price_asc/price_desc` `:322-323` |
| 综合评分 | restaurants | `score_total` | numeric? null→`—` | 排序 `score` `:321`；默认门槛≥50 |
| 精选优先 | restaurants | `curate_score`（+ `is_curated`） | numeric? null→垫底 | 排序 `curated` `doSort`（新增） |
| "预制菜"红签 | restaurants | `premade_risk` | enum `无/低/疑似/高`；`==='高'` 才签 | hideChain 隐藏谓词见 §3.2 |
| "连锁"灰签 | restaurants（前端派生） | `chain_type`+`central_kitchen`+`premade_risk` | 见 §3.1 `isIndustrial()` | hideChain 隐藏谓词见 §3.2 |
|  Michelin/黑珍珠签 | cuisines（id 159/160） | 标签关联 | bool（标签存在） | 标签筛选 tagSel |

### 1.2 餐厅详情（`app/pages/restaurants/[id].tsx`，拉取 `:87` `select('*')`）

| UI 元素 | DB 列 | 类型/空值 |
|---|---|---|
| 价格带/人均 | `price_scene`+`price_band` / `price_avg` | 同上 |
| 综合评分 | `score_total` | numeric? |
| 语义简介 | `semantic_description` | text? null→不渲染 `:320` |
| 基本信息 InfoRow | `address/phone/booking_method/discount_info/investor_info` | string? 空→不渲染 |
| 业态/主厨/营业 | 关联 + `chef_name`/`open_days`/`opening_hours` | 见 `lib/supabase.ts` |
| 连锁类型 | `chain_type` | enum，空→不渲染 |
| 中央厨房 | `central_kitchen` | enum（**text，非 boolean**） |
| 预制菜风险 | `premade_risk` | enum |
| 精选徽标（新增） | `is_curated` + `curate_badge` | bool；badge `必吃/值得/精选`，null→"已入选"占位 |
| 入选理由（新增） | `curate_reason` | text? null→不渲染 |
| 反软广子分条 | `score_taste/score_objective/score_diner/score_endorsement` | numeric? null→该条不渲染（SCORE_BARS `:17-22`） |

### 1.3 地图 pin（`app/pages/map.tsx:34`，显式列白名单）
`id,name,name_en,price_scene,price_band,price_avg,address,district,status,location`。
- popup 文案：`name`、`price_scene · ¥price_avg/人`、`address`。
- 点过滤：`status` 非 closed/关店（`:74`）；坐标由 `location`（PostGIS）解析。
- 【待确认/不阻断】地图 popup 当前不挂"预制/连锁/精选"签；若要挂，需把 `premade_risk/is_chain_standardized/is_curated/curate_badge` 加进 `:34` 白名单（属后续视觉/功能迭代，本轮不做）。

### 1.4 活动 feed（`app/components/FeedSection.tsx`）
- 主拉：`food_events` `select('*')`（`:148`，按 `event_date` 倒序 limit 100）。
- 补餐厅名：`restaurants` 仅 `id,name`（`:163-165`）。
- Event 字段见 `lib/supabase.ts` `FeedEvent`：`scope/category/title/summary/event_date/expires_on/confidence/status/sources`。

### 1.5 主厨 profile（`app/pages/chefs/[id].tsx`）
- 主厨：`chefs` `select('*')`（`:34`）。
- 所属集团：`restaurant_groups` `select('*')` by `chefs.group_id`（`:37`）。
- 关联门店：`restaurant_chefs`⨝`chefs(name)`（详情页 `[id].tsx:96-99`）；轻量门店列表 `restaurants` 仅 `'id,name,district,business_area,status,price_avg,score_total'`（chefs/[id].tsx:45）。

### 1.6 集团 profile（`app/pages/groups/[id].tsx`）
- 集团：`restaurant_groups` `select('*')`（`:31`）。
- 成员：`restaurant_group_members` `select('*')`（`:32`）。
- 主厨：`chefs` `select('*')`；门店摘要同 1.5 的轻量列。

---

## 2. 权威只读模型字段清单（前端不得自创/硬编码）

### 2.1 Restaurant（列表/详情主模型，来源 `restaurants` 表）
必选渲染列：`id, name, name_en, status, price_avg, price_scene, price_band, district, business_area, address, location, signature_dishes, phone, booking_method, discount_info, investor_info, chef_name, open_days, opening_hours, semantic_description, score_total, score_taste, score_objective, score_diner, score_endorsement, soft_ad_penalty, evidence_summary, score_evidence_level`。
权威信号列：`chain_type, central_kitchen, premade_risk`。
精选层列：`is_curated, curate_badge, curate_score, curate_confidence, curate_reason, astroturf_score`。
派生/辅助：`is_chain_standardized`（DB generated STORED，008）、`review_count`（冗余）。

### 2.2 展示派生值（后端版本化确定性，前端只映射）
- **价位区间 label**：不由前端拍脑袋。后端 `price_band_thresholds`（表，`db/migrations/009_price_band_standard.sql:12`）存 `scene,band,lo,hi`；前端 `lib/supabase.ts` `bandLabel()` 仅做 `¥<lo / ¥lo–hi / ¥lo+` 拼接。新增价格带只改阈值表，不改前端。
- **精选 badge 文案**：直接用 DB `curate_badge`（必吃/值得/精选），前端不另造映射词。
- **连锁/预制隐藏判定**：用 §3.1 `isIndustrial()`，前端不另写正则或阈值。

### 2.3 其它 read model
`Cuisine`、`Review`、`FeedEvent`、`Chef`、`RestaurantGroup`、`GroupMember`、`ChefRestaurant`、`PriceThreshold` —— 定义一律以 `app/lib/supabase.ts` interface 为准；新增字段先入迁移 + `db_schema_spec.json`，再由 §4 脚本生成 TS。

---

## 3. 空值规则与枚举映射

### 3.1 空值规则（与已实现 `isIndustrial()` 一致）
位置：`app/pages/restaurants/index.tsx` 模块级函数 `isIndustrial(r)`。

| 信号列 | NULL 时前端按什么处理 |
|---|---|
| `chain_type` | 非连锁（既非小型/大型/资本化） |
| `central_kitchen` | 无 |
| `premade_risk` | 无（不签"预制菜"红签） |
| `price_avg` | 不进预算筛选、排序垫底/置后、展示 `¥—` |
| `score_total` | 不进"评分最高"前列、展示 `—` |
| `curate_score` | 精选排序垫底（`?? -1`），不阻断其余排序 |
| `is_curated` | false（未入选） |
| `status` | 非 closed（保守放行；以 DB 默认 active 为准） |

`isIndustrial()` 口径（权威列直算，不依赖可能缺失的 `is_chain_standardized`）：
```
ct = chain_type ?? null; ck = central_kitchen ?? null; pr = premade_risk ?? null
if ct ∈ {资本化连锁, 大型连锁} -> industrial
if ct == 小型连锁 AND (ck ∈ {确认,疑似} OR pr ∈ {高,疑似,低}) -> industrial
if pr == 高 -> industrial   # 独立店/未标注店高预制也隐藏
else -> 非工业化
```

### 3.2 "隐藏连锁/预制"开关（`hideChain`）精确谓词
UI：`restaurants/index.tsx:576`；过滤：`:331`
```
visible = !isIndustrial(r) OR isNonDiner(r)
```
`isNonDiner(r)` = 该店菜系树命中"非正餐"根（咖啡/面包/甜品/Bar/茶饮连锁常态，豁免隐藏）。

### 3.3 排序精确列与谓词（`doSort`）
| 档 | 键 | 谓词 |
|---|---|---|
| 精选优先（默认） | `curated` | `curate_score DESC NULLS LAST`，次级 `score_total DESC` |
| 评分最高 | `score` | `score_total DESC` |
| 人均低→高 | `price_asc` | `price_avg ASC NULLS LAST`（null 当 9999） |
| 人均高→低 | `price_desc` | `price_avg DESC NULLS LAST`（null 当 0） |

### 3.4 枚举 → 中文 label（与规范1 CHECK 约束同源）
| 列 | 枚举（DB CHECK） | 前端展示 |
|---|---|---|
| chain_type | 独立店/小型连锁/大型连锁/资本化连锁 | 原文直出（已是中文） |
| central_kitchen | 无/疑似/确认 | 原文直出 |
| premade_risk | 无/低/疑似/高 | 原文直出；仅"高"挂红签 |
| food_safety | 无/疑似/确认 | 原文直出 |
| status | active/closed/relocated | active→在营，closed→关店，relocated→已迁 |
| price_position | 经济/平价/中端/高端/奢华 | （前端已停用展示，见 supabase.ts:43 注释） |
| curate_badge | 必吃/值得/精选 | 原文直出；NULL=未入选不签 |
| score_evidence_level | verified/provisional/insufficient | verified→"已核验" |

---

## 4. 前后端类型同源

### 4.1 生成规则
- 机器唯一来源：`docs/standards/db_schema_spec.json`（规范1）。
- 生成器：`cloud/gen_ts_types.py`（**非阻断**）。读 JSON 的 `tables.restaurants.enums` → 输出 TS 联合类型片段。
- 默认 **dry-run**：只打印到 stdout，不写盘；加 `--write` 才写 `app/lib/generated_enums.ts`（新文件，**绝不**覆盖手写的 `app/lib/supabase.ts`）。
- `app/lib/supabase.ts` 的 enum 字段类型须与生成片段保持一致；发现漂移时以 JSON 为准，手改 JSON + 重跑生成器。

### 4.2 用法
```bash
# 只读预览（不写盘，CI/本地均可跑）
python3 cloud/gen_ts_types.py

# 落地类型片段到 app/lib/generated_enums.ts（可选，不强制）
python3 cloud/gen_ts_types.py --write
```
脚本不连网、不连 DB、无副作用；退出码恒 0（仅打印）。

### 4.3 缓存 / 数据版本失效
- 前端阈值缓存：`lib/supabase.ts` `_thCache`（`fetchThresholds`）进程内缓存，不持久化；`price_band_thresholds` 变更后下次部署/重启即刷新。
- 精选/连锁列随每次页面加载直查 DB（无前端持久缓存）；DB 重算 `curate_score` 后前端下次拉取即生效。
- **失效规则**：DB 迁移新增列/改枚举 → ① 更新 `db_schema_spec.json` → ② 跑 `gen_ts_types.py --write` → ③ 前端 `select` 列白名单（尤其 `map.tsx:34`）按需补列 → ④ 发布清单勾稽 G3（规范3）。
- 不做前端本地版本号硬编码；以 DB `data_updated_at` / `updated_at` 为新鲜度信号（详情页已用 `data_updated_at` 算"数据更新于 N 天前"）。

---

## 5. 红线（本规范约束）
- 不在前端硬编码枚举中文映射词；新增枚举先迁移 + CHECK + JSON。
- 不为筛选开关另写业务状态；连锁/预制判定只走 §3.1。
- 不改 `select('*')` 既有行为；地图/摘要白名单补列需在发布清单登记。
- 本轮不做视觉改版、不部署、不改 crontab、不动 DB。

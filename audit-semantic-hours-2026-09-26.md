# 语义简介 + 营业时间 + 字段完整性审计报告

日期：2026-09-26
餐厅总数：1519

## Part A: 语义简介（semantic_description）

| 指标 | 补全前 | 补全后 |
|------|--------|--------|
| 全库覆盖率 | 0/1519 (0%) | **1519/1519 (100%)** |
| score_total>70 高分店 | 0% | **845/845 (100%)** |
| 简介长度区间 | — | 24–76 字，平均 42 字 |

**生成规则**：菜系标签 + 位置商圈 + 荣誉(米其林/黑珍珠) + 历史 + 主厨 + 招牌菜(前3道) + 人均价格。
基于 signature_dishes / evidence_summary 引用 / restaurant_awards 三源确定性推导，无软广话术。

**典型示例**：
- id=6 吉兆 KITCHO: `日料/日本料理，位于静安寺，米其林一星，招牌金枪鱼中腹、鳗鱼、地金目，人均2460元`
- id=1137 海鲜店: `海鲜，位于外滩，黑珍珠1钻，招牌黑松露鹅汉堡、香草烤鹌鹑、招牌雪花牛里脊，人均1200元`
- id=1000 德兴馆: (老字号历史已从引用提取) `...`
- id=2002 Ministry of Crab: `斯里兰卡菜，位于人民公园/南京西路，招牌香蒜辣椒蟹、手磨黑胡椒蟹、黄油蟹，人均336元`

脚本：`semantic_profile_generator.py`（dry-run / --commit / --high-score）

## Part B: 营业时间（opening_hours + open_days）

| 指标 | 补全前 | 补全后 |
|------|--------|--------|
| 全库覆盖率 | 0/1519 (0%) | **69/1519 (4.5%)** |
| 其中 score>75 重点店 | 0 | 22 家 |

**采集方式**：从 evidence_summary 引用中正则提取 `HH:MM-HH:MM` / `周X至周X` / `周X休`。
来源多为高德地图/点评引用自带营业时间。宁空不假，未提取到的 1449 家留空待后续搜索补充。

**典型示例**：
- id=794 鲁一品: `open_days=周一至周日, opening_hours={"周一":"07:30-18:30",...}`
- id=854 老绍兴: `{"周一":"10:30-13:30; 16:00-20:30",...}`（午晚市分段）

脚本：`opening_hours_collector.py`

> 注：69 家低于 300-500 目标，因 evidence 中营业时间信息天然稀缺。
> 补充需对重点店逐家搜大众点评/高德，建议后续用 browser-use RPA 批量采集。

## Part C: 字段完整性审计

| 字段 | 覆盖率 | 状态 |
|------|--------|------|
| name | 100% | ✅ |
| address | 100% | ✅ |
| district | 100% | ✅ |
| signature_dishes | 100% | ✅ |
| price_avg / tier | 100% | ✅ |
| semantic_description | **100%** | ✅ 本次补全 |
| location 坐标 | 99.3% (1508/1519) | ⚠️ 6家无坐标 |
| score_total 及四项子分 | 99.8% (1516/1519) | ✅ 3家无评分 |
| phone | 63.5% (964/1519) | ⚠️ 555家无电话 |
| business_area 商圈 | 84.3% | ✅ |
| opening_hours | 4.5% | ⚠️ 待搜索补充 |
| open_days | 4.5% | ⚠️ 待搜索补充 |
| chef_name | 0% | ⚠️ restaurant_chefs 表空 |

**无坐标的6家营业中店**：id=1854, 1939, 1985, 1986, 1987, 1988（需地理编码补坐标）
**Ministry of Crab (id=2002)**：地址/电话/坐标/招牌菜/语义简介均已齐，评分82.3，仅营业时间待补。

## Part D: 写库与验证

- 全部走 REST API PATCH（common.req），未直连 SQL
- 写前备份：`backups/semantic_desc_backup_2026-09-26.jsonl`、`backups/opening_hours_backup_2026-09-26.jsonl`
- 每批50家后回读 GET 验证：
  - semantic_description: 1519/1519 写入成功
  - opening_hours: 69/69 写入成功，回读验证 69/69
- 前端 `app/pages/restaurants/[id].tsx` 已支持 semantic_description / opening_hours / open_days / chef_name 展示（空值不渲染）

## 交付物
- `scripts/food_pipeline/semantic_profile_generator.py`
- `scripts/food_pipeline/opening_hours_collector.py`
- `references/semantic-profile-and-hours.md`（方法论写回 skill）

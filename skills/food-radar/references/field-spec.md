# food-radar 字段规范（Field Spec）

## 一、输出结构

```json
{
  "query_context": {
    "city": "上海",
    "time_window": "近6个月",
    "benchmarks": ["遇外滩联弹", "头灶"],
    "generated_at": "2026-10-16",
    "generator": "food-radar v1.0"
  },
  "items": [ /* 见下方单条 schema */ ],
  "excluded": [ /* 被剔除项及原因，如攏好粤菜：2024年已退出上海 */ ]
}
```

## 二、单条 item schema

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| name | string | 是 | 店名/事件名 |
| type | enum | 是 | `new_opening` / `collab_event` / `closure_alert` |
| status | enum | 是 | `open` / `closed` / `upcoming` / `unknown` |
| cuisine | string | 是 | 菜系路线 |
| city, district, address | string | 是* | *new_opening 必填 |
| opened_date | date | 是* | 精确到日；unknown 填 null，禁止猜 |
| closed_date | date | 否 | 闭店专用 |
| chef | object | 否 | `{name, title, background}` 主厨履历 |
| price_per_head | number | 否 | 人均（元），拿不到填 null |
| honors | array | 否 | `[{award, year}]` 如 `{award:"米其林二星", year:2026}` |
| kol_mentions | array | 否 | `[{platform, account, url, date, summary}]` |
| platform_signals | object | 否 | `{dianping:{rating, review_count, fetched_at}, xhs:{note_count, fetched_at}}` |
| collaboration_angle | string | 否 | 可借鉴/可合作的切入点 |
| sources | array | 是 | `[{url, publisher, date, tier}]`，tier ∈ S/A/B/C |
| confidence | enum | 是 | `high`（双S/A信源）/ `medium`（单S/A+UGC）/ `low`（仅C级） |
| verified_at | date | 是 | 本条校验完成时间 |
| notes | string | 否 | 异常说明、假设、待确认项 |

## 三、枚举与硬约束

- `type=closure_alert` 时**必须区分三种状态**，不得一律当作已关闭：
  - `status=closed`（**已确认闭店**）：有 S 级或两个独立 A 级信源 → `closed_date` 必填
  - `status=suspected`（**疑似停业**：长期无更新、仅单条 UGC 提及、员工/店主帖等弱信号）→ `closed_date` 为 `null`，必须写明触发怀疑的具体线索，**不得直接移出推荐位**
  - `status=upcoming`（**已公告将关闭**：有明确关店时间或房东/官方公告）→ 可标注计划关店日期，与 `closed_date` 区分
  - 原规范把三者强制合并为 `closed`，会把"疑似"误报成"事实"，已修订。
- `confidence=high` 必须满足：≥2 个**独立**信源（同一通稿的转载不算独立）且落在查询时间窗内，其中至少 1 个 S/A 级。
- `sources` 为空或 `confidence=low` 的条目禁止出现在正式推荐位，只能进"待核实"区。
- 所有日期格式 ISO `YYYY-MM-DD`；抓取时间精确到日。
- 禁止编造：评分、人均、榜单年份拿不到就 null + notes 说明。

## 四、示例（2026-10-16 实战条目）

```json
{
  "name": "潮玖（上海首店）",
  "type": "new_opening",
  "status": "open",
  "cuisine": "新派潮汕菜",
  "city": "上海",
  "district": "虹口区",
  "address": "新建路200号 P1-L4-01",
  "opened_date": null,
  "chef": {
    "name": "任海鹏",
    "title": "潮玖主理人、2025黑珍珠年轻主厨奖",
    "background": "2013年入杭州解香楼，2020年任解香楼主厨；创始人俞斌为解香楼主理人、2026沪苏浙米其林二星、导师厨师奖"
  },
  "price_per_head": null,
  "honors": [{"award": "黑珍珠年轻主厨奖", "year": 2025}],
  "kol_mentions": [{"platform": "微信公众号", "account": "槟客文化", "date": "2026-10-13", "summary": "10.24香槟晚宴，5980元/位限10席，创始人俞斌亲临"}],
  "collabor_angle": "新店亮相期+主厨可接近，联弹/晚宴合作窗口期",
  "sources": [{"url": "https://chihe.sohu.com/a/1087398977_710690", "publisher": "搜狐吃喝", "date": "2026-10-13", "tier": "A"}],
  "confidence": "medium",
  "verified_at": "2026-10-16",
  "notes": "开业具体日期未在信源中明确，需向门店确认"
}
```

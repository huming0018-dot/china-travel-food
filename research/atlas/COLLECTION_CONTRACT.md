# Atlas v2 采集契约（chef / award / event / review）

> 子代理 / 采集器只产出结构化 raw 文件，**禁止直接写库**；主代理收回后校验、用 `atlas_write.py` 统一写库。
> 铁律：宁空不假；每条事实带可访问 `source_url` + 平台 + 日期；一手信源优先；press/通稿不进口味；去软广。
> 输出目录：`research/atlas/<domain>/`。所有文件为 UTF-8 JSONL，一行一对象。

## 通用字段约定
- 日期：`YYYY-MM-DD`；不确定年份用可考证的，留空不猜。
- 评分：1–5（外部平台口径）；aspect_* 只在能从内容判明时填，否则 null。
- 来源 URL 必须是原帖 / 商户页 / 官方页直链；聚合转载不算一手。
- 找不到：该字段留 null，并在 `notes` 说明，禁止编造。

---
## 1) raw_chefs.jsonl — 主厨 / 主理人
一行一位主厨，挂店放在 `restaurants`：
```json
{"name":"...","name_en":"...","title":"主厨/主理人/饼长/创始人","bio":"...","origin":"出身/师承/流派","is_traveling":false,
 "social_xhs":"...","social_douyin":"...","social_weibo":"...","reputation":{"summary":"...","source_url":"..."},
 "restaurants":[{"restaurant_id":123,"role":"主厨","is_current":true,"started":"2021-05","source_url":"https://..."}],
 "data_updated_at":"2026-09-24","notes":""}
```
- 同一主厨跨 / 换店：一位主厨一行，`restaurants` 列全部关联（前店 is_current=false）。
- 重点范围：米其林 / 黑珍珠店、知名高端、知名主理人 / bistro、飞行主厨，约 200–300 人。
- 师承同门（如 nabi / WULI 同 Tom Ryu）通过共同主厨或品牌系表达。

## 2) raw_awards.jsonl — 荣誉（直接对齐 restaurant_awards）
```json
{"restaurant_id":123,"award_type":"michelin_star","level":"一星","year":2025,"season":"2025","is_current":true,
 "source_url":"https://guide.michelin.com/...","source_name":"米其林指南"}
```
- award_type：`michelin_star` / `bib_gourmand`(必比登) / `black_pearl` / `media_show`(一饭封神/黑白厨房等综艺) / `other_list`。
- level：三星/二星/一星/必比登/三钻/二钻/一钻/冠军/入选。
- 每届一行；最新一届 is_current=true，往届保留为 false。
- 米其林以 `research/authority/michelin_shanghai_153.json` 为准；黑珍珠全量需补采官方页。

## 3) raw_events.jsonl — 事件 / Feed（直接对齐 food_events）
```json
{"scope":"local","category":"new_open","title":"...","summary":"...","event_date":"2026-08-01",
 "restaurant_id":null,"related_restaurant_id":null,"chef_id":null,"district":"静安区",
 "sources":[{"platform":"官方公众号","title":"...","url":"https://mp.weixin.qq.com/...","date":"2026-08-01"}],
 "confidence":"high","status":"verified"}
```
- scope：`local`(上海店) / `overseas`(海外名店动态、海外热门店) / `industry`。
- category：`new_open` / `relocated` / `closed` / `chef_changed` / `guest_kitchen`(飞行厨房) /
  `collaboration`(跨界联名/联合快闪) / `popup` / `award` / `menu_update` / `coming_soon`。
- 置信：官方源 1 个或独立源 ≥2 → high；单 KOL → mid、status=rumor。
- **搬迁**：原址 restaurant_id、新址 related_restaurant_id（Nuits：原址 closed + 恒隆二期新址）。
- 重点：主厨新店、海外米其林 / 热门店上海首店、主厨变化、飞行厨房、联名快闪（DV×遇外滩）。

## 4) raw_reviews.jsonl — 真实食客堂食评价（直接对齐 reviews，user_id=null）
```json
{"restaurant_id":123,"user_id":null,"author_name":"...","source_platform":"小红书","source_url":"https://www.xiaohongshu.com/...",
 "rating_total":5,"rating_taste":5,"content":"逐字原话，含菜名与体验，30字以上",
 "visit_date":"2026-06-12","review_kind":"diner","is_verified_diner":true,"trust_level":"high",
 "aspect_taste":5,"aspect_service":4,"aspect_env":4,"aspect_value":4,"aspect_json":{"taste_evidence":"...","service_evidence":"..."},
 "is_fake_suspect":false,"is_hidden":false}
```
- 只采 **堂食（diner）**；外卖 takeaway、媒体 press 单独标，不进口味引擎。
- 每家精选 / 重点店目标 **3–8 条**真实堂食评价，优先近 18 个月、含具体菜名 / 做法 / 口感。
- **方面级**：等位 / 服务态度 / 环境 / 性价比 / 个人情绪 → aspect_service/env/value，**不写 aspect_taste**；
  明确针对菜品（腥 / 老 / 柴 / 咸 / 预制味 / 翻车 / 惊艳）才写 aspect_taste。
- 软广 / 模板文案 / 团购挂车 / 集中轰炸 → is_fake_suspect=true 或 trust_level=low。
- 正常店保留少量真实差评（不藏），全好评异常。
- 优先范围：各菜系精选 + 米其林黑珍珠 + 高 score 店（约 400–600 家）。

---
## 分片建议（供 organizer）
- award：1（结构化米其林 + 补黑珍珠 + 综艺声誉）。
- chef：3–4（中餐 / 亚洲日料 / 西餐 / 其他·主理人）。
- event：2（新店·搬迁·关店 / 主厨变化·飞行·联名·快闪）。
- review：5–6（日料 / 川菜等 / 粤菜·苏菜 / 其他中餐 / 西餐 / 非正餐咖啡甜品酒吧）。
- 每个子代理在文件顶部 notes 记录 discovery 来源；产出后自做 JSON 校验，主代理全量复核。

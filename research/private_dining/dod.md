# Slice B 私宴 · 验收 DoD

## 配额
- 候选 ≥30（含甄别样本），精选 ≥15。
- 8 个叶子无空格；供给稀缺叶（L2/L3/L4/L6）≥1 即达标并标注"供给稀缺"。

## 证据厚度（每店 raw 硬门，stage1 拦截）
- evidence_summary ≥200 字。
- diner_quotes ≥2 条不同食客堂食原话，含具体菜名/做法 + 原帖 URL + 日期；空话不计。
- platform_scores ≥1 带评论数；评论<50 却 4.5+ 高分 → platform_credibility ≤0.7。
- ≥1 条差评/负面信号（negative_signals），全好评异常。
- soft_ad_flags / traffic_signals 如实记录。
- sources ≥2 类独立渠道（官方指南/海外媒体/UGC/地图跨两类）。
- 预订方式必写清（微信/电话/熟人介绍/小程序）。
- 名称验证：name=权威正名，name_verified=true（≥2 个 L1–L5 权威源一致），name_source_urls，aliases[]。
- 地址：预约制可写"预约告知"但需可核大致楼栋/区域；电话/坐标宁空不猜，坐标本片留空（按任务要求）。

## 三门标准
1. **stage1 质量门**：raw_private_dining.jsonl 跑 stage1_validate.py，rejected 逐条说明或修复清零。
2. **回归集门**：5 个回归用例（Cheeva Thai/聪菜馆/豪生/黄公子/AmoyA）机制自动命中，能指出发现路径。
3. **反软广门**：团购挂车/模板文案/博主集中轰炸店扣分或剔除；私宴评论<50 高分降权。

## 不做的事（子代理边界）
- 不写库、不改标签、不碰前端、不部署。
- 只产 raw + candidates_list.md + discovery_log.md。
- 库内8家疑似误挂店仅在日志标注，不迁移。

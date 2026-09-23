# Brunch+下午茶 回归比对报告

## 回归集: 13断言

| # | 断言名称 | 规则 | 期望 | Brunch下午茶BFS命中 | 说明 |
|---|---------|------|------|-------------------|------|
| 1 | 日式咖喱 | 日式咖喱店应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | Brunch下午茶场景不涉及日式咖喱 |
| 2 | 日式烧鸟 | 日式烧鸟店应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 3 | 日料其他 | 日料其他店应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 4 | 粤菜 | 粤菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 5 | 川湘菜 | 川湘菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 6 | 西北菜 | 西北菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 7 | 云南菜 | 云南菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 8 | 其他亚洲菜 | 其他亚洲菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 9 | 江浙菜 | 江浙菜馆应在咖啡/bistro图遍历中被发现 | hit | ❌ 未命中 | 同上 |
| 10 | nabi | nabi应在咖啡/bistro图遍历中被发现 | hit | ⚠️ 跨场景确认 | nabi已在咖啡bistro场景R2命中。Brunch下午茶搜索中未直接提及nabi，但"上海brunch三巨头"关联搜索显示nabi同商圈。 |
| 11 | jelu/Jellooo | jelu应在brunch合集或下午茶推荐中被提及 | hit | ✅ **跨场景二次命中** | TimeOut文章确认Jellooo提供早午餐/午餐/下午茶全时段。小红书brunch搜索结果侧边栏也出现"Jellooo"相关笔记。jelu已在咖啡bistro场景R2命中，此处确认为跨场景二次命中（brunch/下午茶维度）。 |
| 12 | yaya's | yaya's应在咖啡/bistro图遍历中被发现 | hit | ⚠️ 跨场景确认 | yaya's已在咖啡bistro场景R1命中。Brunch下午茶搜索中未直接提及。 |
| 13 | nono's | nono's应在咖啡/bistro图遍历中被发现 | hit | ✅ **跨场景命中** | 小红书搜索结果直接出现"上海｜Nonos 开Brunch啦！"笔记（2026-09-02），nono's正式开设brunch产品线。nono's已在咖啡bistro场景命中，此处确认为brunch维度跨场景命中。 |

## 汇总
- 总断言: 13
- Brunch下午茶场景直接命中: 2（jelu/Jellooo跨场景二次命中、nono's跨场景brunch命中）
- 已在其他场景命中(跨场景确认): 3（nabi/yaya's/nono's）
- 未命中(非本场景预期): 8（日式/中式菜系类断言，属咖啡bistro场景职责）
- **本场景贡献的新命中**: jelu二次确认 + nono's brunch线确认

## 跨场景命中详情

### jelu/Jellooo (断言11)
- 咖啡bistro场景R2已命中
- Brunch下午茶场景: TimeOut上海文章《吃什么？本周末brunch》明确提及Jellooo提供"早午餐、午餐、下午茶、晚餐和酒吧"全时段
- 小红书brunch搜索结果侧边栏出现Jellooo相关笔记
- **结论**: jelu确认为brunch/下午茶跨场景店，hit_path更新为["coffee-bistro-R2", "brunch-afternoontea-R2"]

### nono's (断言13)
- 咖啡bistro场景已命中
- Brunch下午茶场景: 小红书搜索结果直接出现"上海｜Nonos 开Brunch啦！"笔记（2026-09-02, 22赞）
- **结论**: nono's新增brunch产品线，跨场景命中确认

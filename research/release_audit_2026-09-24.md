# 版本回归扫描报告 2026-09-24

汇总：PASS=7 CHECK=1 ERROR=0 SKIP=0

**结论：存在待查/错误，按 release-regression-loop 修复机制后重扫**

前端 H 类（导航/筛选/排序/详情地图/打卡）需 browser-use 单独回归。

### [PASS] D/G 单店字段/硬伤 — `stage4_audit.py` (return=0)
> 全库只读体检，ERROR 应为 0

```
- [字段空] id=1144 虹盐RED SALT新派印巴餐厅(禧瑞广场店) 缺 phone
- [字段空] id=1146 Kaveen's Kitchen印度餐厅(虹桥店) 缺 phone
- [字段空] id=1148 Indian Kitchen(南印) 缺 phone
- [字段空] id=1149 Dakshin南印餐厅 缺 phone
- [字段空] id=1151 Dev Bhoomi Curry House 缺 phone
- [字段空] id=1153 Bombay Bistro 缺 phone
- [字段空] id=1157 Vedas Indian Restaurant 缺 phone
- [字段空] id=1159 Delhi Darbar 缺 phone
- [字段空] id=1161 Punjabi Bistro旁遮普 缺 phone
- [字段空] id=1163 安比斯印度餐厅 缺 phone
- [字段空] id=1165 Otantik黎凡特美食(吴江路店) 缺 phone
- [字段空] id=1167 Otantik黎凡特美食(西藏中路店) 缺 phone
- [字段空] id=1169 MAKAN阿拉伯餐厅 缺 phone
- [字段空] id=1172 Brothers Kebab(奉贤路店) 缺 phone
- [字段空] id=1174 Brothers Kebab(长寿路店) 缺 phone
- …另有 299 条，分类计数见标题

## ℹ️ INFO 0

[stderr]

汇总: ERROR=0 WARN=499
```

### [CHECK] A 网格覆盖 — `stage6_coverage.py` (return=1)
> 空格/薄格/薄证据，strict 不达标返回1

```
| 叶子 | 总 | 经济 | 平价 | 中档 | 高档 | 奢华 | 状态 |
|---|---|---|---|---|---|---|---|
| 创新菜 | 1 | 0 | 0 | 0 | 0 | 1 | 薄 |

## 三、深采任务清单（10 项）

按此清单逐格补采：每格走「候选≥2×下限 → 反软广评分 → ≥2条含菜名点评 → 多渠道交叉 → 管线入库」。

- **川菜 / 川南·宜宾菜**（薄，现 2）：补采至下限
- **川菜 / 海派改良川菜**（薄，现 2）：补采至下限
- **川菜 / 川南·内江菜**（薄，现 1）：补采至下限
- **川菜 / 川南·泸州菜**（薄，现 1）：补采至下限
- **川菜 / 川北·绵阳菜**（薄，现 1）：补采至下限
- **浙菜 / 金华/衢州菜**（薄，现 2）：补采至下限
- **闽菜 / 闽北菜**（薄，现 1）：补采至下限
- **广西菜 / 桂林米粉**（薄，现 2）：补采至下限
- **河南菜 / 豫菜·开封洛阳**（薄，现 2）：补采至下限
- **创新菜 / 创新菜**（薄，现 1）：补采至下限

[stderr]

汇总：空格 0 / 薄格 10 / 深采任务 10
```

### [PASS] E 跨菜系根 — `cross_cuisine_audit.py` (return=0)
> dry-run，误挂根检查

```
自动判定 0 家 | 需人工 1 家 | 待删关联 0 笔
# 跨菜系根误挂检测报告

自动判定 **0** / 需人工 **1** / 待删 **0** 笔

## 一、自动判定（dry-run 不删）


## 二、需人工裁决

- id1409 BASTARD小酒馆: 根['川菜', '粤菜'] 店名命中[] 细叶根[]

【DRY-RUN】确认判定无误后加 --commit 删除（人工项不在自动范围）。
```

### [PASS] C 连锁/预制 — `chain_audit.py` (return=0)
> dry-run，连锁/中央厨房/预制标注

```
连锁审计：0 家待更新
chain_type: {}
premade_risk: {}
已落 chain_plan.json
[dry-run] 确认后加 --commit
```

### [PASS] E 分类引擎 — `cuisine_classify_audit.py` (return=0)
> dry-run，主营/地名陷阱/冲突

```
分类审计：涉及 1 家、1 个动作、0 个待裁决

#1526 大富贵酒楼(中华路总店)
  ADD    本帮菜  (R3 大富贵实际归属, medium)

已落 classify_plan.json / classify_conflicts.tsv
[dry-run] 确认后加 --commit 成对执行
```

### [PASS] D 实体对齐 — `entity_align.py` (return=0)
> 权威名单 high/medium/unmatched/need_review

```
 X 入选 外滩 · 林家一 
 X 入选 云 
 X 入选 徽季 
 X 入选 临江宴 
 X 入选 悦轩 
 X 入选 扒 
 X 一星 粤海棠 
 X 一星 周舍 (闵行) 闵行区
 X 必比登 宁海食府 
 X 必比登 阿勇面馆 (东书房路) 
 X 入选 Arva 

--- 需人工/复核 ---
 ? 新荣记 (南京西路) 自动匹配多候选 [871, 1370, 1376, 1377, 1380]
 ? 家全七福 自动匹配多候选 [656, 1468]
 ? 老正兴 自动匹配多候选 [1004, 1592]
 ? Polux 自动匹配多候选 [1152, 1810]
 ? 南兴园 自动匹配多候选 [478, 1447]
 ? Il Ristorante - Niko Romito 自动匹配多候选 [1389, 1746]
 ? 遇外滩 (中山东二路) 自动匹配多候选 [523, 524, 903]

已写 research/authority/alignment_result.json
```

### [PASS] A 权威名单比对 — `authority_compare.py` (return=0)
> 米其林全量与库 hit/missing

```
  - 随堂里 （时尚中国菜） slug=sui-tang-li
  - 永兴 （沪菜） slug=yong-xing
  - Shaughnessy （扒房） slug=shaughnessy
  - 皖宴 (长宁) （徽菜） slug=wan-yan
  - 壳里 （法国菜） slug=coquille
  - 沼田双 （天妇罗） slug=numata-sou-1215509
  - 翡翠36 （时尚法国菜） slug=jade-on-36
  - Mr & Mrs Bund （时尚法国菜） slug=mr-mrs-bund
  - 川粤海棠 (长宁) （川菜） slug=chuan-yue-hai-tang-changning
  - 白茸 （鲁菜） slug=bai-rong
  - 老干杯 (黄浦) （烧烤） slug=kanpai-classic-506687
  - 外滩 · 林家一 （台州菜） slug=lin-family-of-one-the-bund
  - 云 （创新菜） slug=les-nuages
  - 徽季 （徽菜） slug=hui-ji
  - 临江宴 （江浙菜） slug=lin-jiang-yan
  - 悦轩 （江浙菜） slug=dining-room-1196349
  - 福承 （闽菜） slug=fucheng
  - 扒 （扒房） slug=the-meat
  - 逸道 (北京东路) （淮扬菜） slug=tea-culture-east-beijing-road
  - Arva （意大利菜） slug=arva-563644

已写 research/authority/authority_missing.json
```

### [PASS] B 总分漂移 — `stage5_recalc.py` (return=0)
> score_total 只读漂移检测

```
total 与触发器公式一致 1390 家；不符 0 家；评分残缺 0 家

只读校验完成，未写库；报告 recalc_report.json
```

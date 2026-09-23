# 上海精品咖啡 采集报告

## 概览
- **场景**：精品咖啡 specialty coffee
- **总家数**：35（31通过 + 3存疑 + 1 closed）
- **数据更新日期**：2026-09-23（stage1打回补强）
- **网格叶子数**：18格（6类型 × 3档位），其中3格标注"供给稀缺"

## Stage1 打回补强结果（2026-09-23）

### 打回原因
1. evidence_summary 字段全空（0字），需≥200字真正风味综合
2. diner_quotes 用新华网/澎湃/上观/文汇/人民网等媒体稿充数（source_kind=media不计入UGC）
3. 多家缺 platform_scores
4. sources 无ugc类型或类型不足2类

### 补强结果
- **通过补强：31家** — 全部满足4项硬门：
  - evidence_summary ≥200字（真实风味综合，非PR通稿）
  - diner_quotes ≥2条真实食客UGC堂食原话（抖音/B站/携程/穷游/马蜂窝/Trip.com食客）
  - platform_scores ≥1（Trip.com/高德/大众点评评分）
  - sources 含 ugc 类型且总类型≥2

- **存疑：3家**（口碑不足，未硬凑UGC）
  1. **LANERS老虎灶喫咖啡**（永嘉路293号）— 仅找到1条抖音UGC，缺大众点评/小红书深度食客评价
  2. **田咖啡**（新乐路70弄66号201室）— 仅媒体报道，无公开可检索的食客堂食原话
  3. **ONIRICO CAFÉ**（思南路）— 2026年7月新开店，口碑数据沉淀不足

- **关闭：1家** — Seesaw Coffee（创始人失联/总部解散，已closed通过）

### 需真人登录补充的清单
以下店铺的大众点评/小红书商户页需登录态访问，目前用Trip.com/携程笔记/抖音替代：

| 店铺 | 需补充平台 | 原因 |
|------|-----------|------|
| 小半咖啡 | 大众点评 | 仅知"曹杨咖啡第一"，缺具体评分/评论数 |
| 0566咖啡製作所 | 大众点评 | 仅海外站4.2分/2048条，缺国内点评详情 |
| LANERS老虎灶喫咖啡 | 大众点评/小红书 | 存疑店，需食客评价补充 |
| 田咖啡 | 大众点评/小红书 | 存疑店，位置隐蔽需食客评价 |
| ONIRICO CAFÉ | 大众点评/小红书 | 新开店，需口碑数据沉淀 |
| DEARYOU 咖啡豆研究所 | 大众点评 | 缺具体商户评分 |
| 赤瑕咖啡 | 大众点评 | 缺陈姐手冲的具体评分 |
| 且乐 cheer | 大众点评 | 缺社区咖啡店评分详情 |

### UGC来源分布
- 抖音探店视频（iesdouyin.com）：最主要UGC来源，覆盖20+家
- 携程笔记（ctrip.com）：第二大来源，食客图文探店
- Trip.com食客评价（trip.com）：英文/中文食客评分
- 穷游/马蜂窝（qyer/mafengwo）：深度食评
- B站（bilibili.com）：补充来源

## 网格覆盖

| 类型 | 亲民(¥20-35) | 中端(¥35-60) | 高端(¥60+) |
|------|-------------|-------------|-----------|
| 主理人品牌独立店 | Radar Coffee、NIFTY、且乐cheer | O.P.S CAFE、3又二分之一、MONO、ONIRICO、Pincle | Captain George、aftertaste、AtticLab、Brew Island、New Lane |
| 烘焙一体自烘店 | 白鲸咖啡、pocket口袋、小半咖啡 | 有容乃大、月球咖啡、Café del Volcán、BIG SUR、雨山咖啡 | 堀口咖啡、0566、VOYAGE |
| 日式手冲专门 | THREE THIRDS、the cave（稀缺） | 赤瑕咖啡、田咖啡、DEARYOU | 鲁马滋 |
| 社区亲民咖啡 | LANERS、且乐、pocket | 一期一会、弥豆 | （稀缺，未硬凑） |
| 精品连锁(工业化) | Manner、Seesaw、M Stand | 星巴克臻选烘焙工坊、% Arabica | 星巴克臻选高端线（稀缺） |
| 咖啡+甜品复合 | SMAKA、BAsdBAN（未收入） | HUGO HUSKY、DayDreaming、IKIGAI、城是、Gregorius | Butterful&Creamorous（稀缺） |

## 档位分布
- **亲民(¥20-35)**：约10家（Manner、Radar、小半、pocket、LANERS、白鲸、且乐等）
- **中端(¥35-60)**：约18家（OPS、有容乃大、月球、Volcán、BIG SUR、Metal Hands、HUGO、DayDreaming等主力）
- **高端(¥60+)**：约7家（Captain George、aftertaste、Brew Island、New Lane、鲁马滋、堀口、0566）

## 降档/存疑清单

### 1. Seesaw Coffee — status=closed
- 2026年7月曝创始人失联、总部解散、3年关店上百家、商标待拍卖
- 供应链转第三方，部分门店可能仍在运营
- 软广扣分15，objective降至50
- 来源：每经网、人民日报/中国城市报

### 2. Manner Coffee — 工业化降档
- 2015年南阳路2平米起家→数百家连锁
- central_kitchen/premade_risk标"疑似"
- 软广扣分8，连锁化标签
- 来源：day9.coffee、Wanderlog

### 3. 星巴克臻选烘焙工坊 — 工业化旗舰
- 2700㎡工业化体验店，非主理人型
- central_kitchen/premade_risk明确为连锁
- 软广扣分10
- 来源：SmartShanghai、携程

### 4. BIG SUR COFFEE — 多店品控存疑
- 已开出多家门店，线上豆品评价褒贬不一
- 已在negative_signals标注

## 各来源实际命中

| 来源层 | 类型 | 命中情况 |
|--------|------|---------|
| A 老饕私藏 | 小红书/豆瓣/即刻 | 豆瓣探店日记、抖音私藏名单 |
| B 商圈逐格 | 大众点评/高德 | 高德评分（Captain George 4.7、Brew Island 4.7） |
| C 事实核验 | 高德/企查查/公众号 | 高德地址电话核验 |
| D 背书层 | 海外媒体 | SmartShanghai、TripChina、Filter Notes、Eatbook、cascara.cafe、Wanderlog |
| E 堂食证据 | 小红书/点评/抖音/携程 | 携程笔记、抖音探店、穷游、马蜂窝 |
| F 关店保鲜 | 搜索"关店/停业" | Seesaw破产核验 |
| G 影视综艺 | B站/抖音 | 抖音探店系列、Bilibili BIG SUR瑰夏 |
| H 名厨/主理人图谱 | 咖啡赛事 | 彭近洋(WBrC中国冠军)、赵彬(Q-Grader)、中山惠一(日式深烘) |
| I 权威名单 | 咖啡媒体 | TripChina 10 Roasters、remembrew 24家 |
| J 本地老饕 | 穷游/篱笆 | 穷游OPS探店、携程老饕推荐 |

## 缺口标注

1. **视频号**：无公开网页，采不到，标缺口
2. **SMAKA / BAsdBAN / Butterful&Creamorous**：咖啡+甜品复合空间高端档，证据不足未收入
3. **AtticLab**：武康路预约制手冲店，仅抖音提及，详细门牌号待核
4. **Pincle拼一口**：永康路世界烘焙冠军店，证据较少未独立成行
5. **M Stand**：连锁工业化识别，与Manner同类，未独立成行（已在grid标注）
6. **NIFTY**：南阳路216号，仅澎湃新店指南提及，证据不足
7. **多家详细门牌号**：ONIRICO、Gregorius、且乐、3又二分之一等待高德/点评回填

## 反软广处理
- 连锁咖啡（Manner/Seesaw/星巴克）均标注工业化标签
- 网红打卡店（HUGO、OPS、Captain George）软广扣分3-5
- Seesaw破产后软广扣分15
- 所有门店negative_signals均填写，无全好评异常

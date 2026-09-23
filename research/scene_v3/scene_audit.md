# Scene V3 审计报告：非正餐四分开（咖啡/面包/甜品/Bar）

> 采集日期：2026-09-23 ｜ 采集片：Slice C ｜ 仅产 raw，不写库/不改标签/不碰前端

---

## 一、库内现状盘点（DB 只读审计）

| 标签 id | 名称 | 维度 | 库内挂店数 | 问题 |
|---|---|---|---|---|
| 48 | 咖啡/甜品专门店 | 菜系 | 118 | 旧合并标签，v3 须拆为咖啡/面包/甜品三个独立二级 |
| 67 | 甜品/点心 | 食材 | 144 | 混入面包店（见下） |
| 68 | 面包/烘焙 | 食材 | 70 | 库内基本无独立面包品类，多挂在甜品/咖啡下 |
| 73 | Bistro/小酒馆 | 形式 | 85 | 含居酒屋/烧肉/夜宵/ Fine Dining 误挂 |
| 81 | 酒吧/清吧 | 形式 | 65 | 混入德餐/美式餐厅/中东餐等正餐店 |
| 71 | Finedining | 形式 | 126 | 正确 |
| 77 | 下午茶 | 形式 | 155 | 正常 |

---

## 二、核心纠错：混入非正餐的正餐 / Fine Dining 店

### 2.1 Bistro(73) 中疑似 Fine Dining 误挂（须从 Bistro 移除）

| 库 id | 店名 | 人均 | 问题 | 应改 |
|---|---|---|---|---|
| **1147** | **1929 by Guillaume Galliot** | **800** | **同时挂了 Finedining(71) 和 Bistro(73)**；Guillaume Galliot 为米其林名厨，长乐路套餐制法餐 | **删除 Bistro(73) 挂接，仅保留 Finedining(71)** |

> 说明：1929 已正确挂了法餐Fine Dining(187) 和 Finedining(71)，Bistro(73) 是历史误挂，须由主代理在写库阶段 DELETE。

### 2.2 Bistro(73) 中其他"人均≥250"但属高端正餐/烧肉（非 Fine Dining 套餐制，保留 Bistro 但非本片职责）

| id | 店名 | 人均 | 性质 |
|---|---|---|---|
| 12 | 炉端一番 | 400 | 高端日料炉端烧 |
| 50 | 三川烧肉 Mikawa | 632 | 和牛烧肉 |
| 51 | AJIYA味屋 | 300 | 和牛烧肉 |
| 53 | 烧肉·至心 | 500 | 和牛烧肉 |

> 这些是高端正餐但非套餐制 Fine Dining，保留 Bistro 形式可接受，不归本片处理。

### 2.3 旧 BistroBar raw 中"不是 Bar"的店（已从 bar raw 剔除，移交正餐片）

以下 33 家在旧 `raw_Bistro酒吧夜宵.jsonl` 中，但实为正餐/Bistro/夜宵/居酒屋，**不应出现在 Bar 品类**：

nabi（韩式套餐Fine Dining）、Jellooo（北欧bistro）、Yaya's Pasta Bar（意面bistro）、Nono's Ristorante（意餐）、gula bistro、Yeats Bistro、Fiamo Bistro、Bella Vita Bistro、Le Verre à vin（法式bistro，非纯酒吧）、大酉 The Merchants（熟成鸡bistro）、壳里 Coquille（海鲜法餐）、Alimentari Grande（意式杂货）、Juke、SOSA（昼餐厅夜酒吧，边界）、游牧Bistro、LEYAS（黎巴嫩）、有喜屋深夜食堂（居酒屋）、烤匠麻辣烤鱼、WULI（韩餐）、三山野云南傣家菜、煤球 Charcoal（炭烤）、壮壮酒馆、Polux by Paul Pairet（法餐bistro）、Le Saleya（南法bistro）、半醉山岚（海鲜）、纯阳六两（中餐bistro）、段氏龙虾、食六区夜宵、顶特勒粥面馆、肥仔文猪骨煲、香巴岛小龙虾、弄口里烧烤、西塔老太太烤肉、哥哥の深夜食堂（居酒屋）。

> 居酒屋（有喜屋/哥哥の深夜食堂）按分类法归"日料×夜宵"，不归 Bar。

### 2.4 乔尔卢布松/唐阁/Ling Long 排查结果

| 店 | 库 id | 当前分类 | 是否混入非正餐 |
|---|---|---|---|
| L'Atelier de Joël Robuchon（人均1600） | 1139 | 法餐+Finedining(71)+法餐Fine Dining(187) | **否，已正确归类** |
| 乔尔卢布松美食坊Boulangerie（人均75） | 1774 | 咖啡/甜品专门店(48)+面包/烘焙(68)+快餐简餐 | **合法面包counter店**，非Fine Dining，本片归入 Bakery |
| 唐阁 T'ang Court（人均1000） | 496 | 粤菜+Finedining(71)+广府菜 | **否** |
| 凌珑 Ling Long（人均2368） | 1391 | 融合菜+Finedining(71)+分子先锋 | **否** |

---

## 三、四分开结果

### 3.1 咖啡 Coffee（36 家，stage1 全过）
- 工业化连锁（标 chain_type，不进精选）：Manner Coffee、Seesaw Coffee、星巴克臻选上海烘焙工坊
- 手冲/自烘豆专门：18 家
- 创意特调咖啡：8 家
- 社区精品咖啡：7 家
- 新增发现：DOU COFFEE ROASTERS（嘉善路早咖）

### 3.2 面包 Bakery（20 家，stage1 全过）—— 库内从零建立
- 酸种/起酥专门：O'Mills Sourdough、BAsdBAN、Bebaked、PAIN CHAUD、Le Pain Sense 等
- 日式面包：ISAN BAKERY、银座仁志川、苹果花园
- 贝果专门：纽约贝果博物馆
- 社区烘焙坊：FASCINO、drunk baker、Bake No Title、When Pigs Fly 等
- 新增发现：ISAN BAKERY（26层日式）、银座仁志川（生吐司连锁）

### 3.3 甜品 Dessert（26 家，stage1 全过）
- 蛋糕/法式甜品：柴田西点、Lady M、L'eclair de Genie、yesOcake、EVERNAKED、yeetlemon、法田鹿、聚福
- 冰淇淋 Gelato：麻布屋、HUFFY、MIMILATO、Sit Gelato、Spiceman、达可芮、野人先生
- 糖水/甜汤：香港华心、双喜老铺、小团圆、汕鹤潮式、贵州冰浆、堂屋糖水
- 铜锣烧/和果子：辛一、泽田本家、四叶和果子本铺（新增）
- 刨冰：Kaki Mania
- 松饼：FINE pancake

### 3.4 Bar 酒吧（24 家，stage1 全过）—— 区分真 Bar vs Bistro
- 鸡尾酒吧：Speak Low、Sober Company、Pony Up、COA、The Odd Couple（新增）、ZION（新增）
- 葡萄酒/自然酒吧：SOiF、Wine Universe、Le Verre à vin、Nora's、Vinism、DTE、Le Saleya、Kartel、Justgrapes、PuR'aisin、葡道、Sip
- 威士忌吧：Tourbillon、ABA WHISKEY、Lab whisky、Project W
- 精酿啤酒吧：明日酿造、Goose Island、飲适、ONE WAY STREET、PLAN B
- 清吧/lounge：武宫酒吧

---

## 四、证据达标率

| 品类 | 总数 | stage1 通过 | 打回 | 带警告（需复核） |
|---|---|---|---|---|
| coffee | 36 | 36 | 0 | 27 |
| bakery | 20 | 20 | 0 | 15 |
| dessert | 26 | 26 | 0 | 17 |
| bar | 24 | 24 | 0 | 21 |
| **合计** | **106** | **106** | **0** | **80** |

警告主要为：电话缺失（宁空不假）、坐标留空（待真人/腾讯拾取器补）、部分店 platform_scores 评论数偏少需可信度系数下调。

---

## 五、待真人登录补证清单

1. **坐标补齐**：106 家 raw 中绝大多数坐标留空（按"宁空不猜"铁律），需真人开腾讯位置服务坐标拾取器逐店拾取。
2. **大众点评长评深采**：部分店 platform_scores 来自搜索快照，需登录点评 App 取真实评论数与长评。
3. **小红书评论区图遍历**：本次以 general_search 为主，未做 browser-use 深采评论区；老饕私藏型店（ISAN/ZION/田咖啡）建议真人开小红书深采评论区二次发现。
4. **ZION / The Odd Couple 具体门牌**：ZION 门牌待补；The Odd Couple 营业状态 Nomfluence 标 Closed 但多源 2026 仍在营，需真人核实。
5. **面包品类仍薄**：20 家中日式面包仅 3 家、酸种专门仅 4 家，建议二轮补 Moofin、Lost Bakery、BAKTRO、山崎面包（连锁）等。

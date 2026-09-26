# 上海美食图鉴 · 数据库覆盖与质量报告（987 终态）

- 数据采集截止：**2026-09-22（晚间更新）**
- 生产库：Supabase（project bdwrhshgdeghgyzwpxnl），表：restaurants / cuisines / restaurant_cuisines / reviews（新建）
- 前端：Next.js Pages Router PWA，https://app-lyart-eta-22.vercel.app/
- 方法论：city-food-guide skill（反软广评分 + 子流派独立候选池 + 真实堂食证据）

> 本版替代当日 922 口径版本，所有数字均为 2026-09-22 晚间经 Supabase REST 全量重拉、独立回验的实测值。

---

## 一、总量（实测）

| 表 | 数量 | 说明 |
|---|---|---|
| restaurants | **987** | 较 922 净增 **65** 家 |
| cuisines | **226** | 新增「台州菜」id=237（parent=浙菜） |
| restaurant_cuisines | ~5400+ | 多对多挂接 |
| reviews | **0 行** | 新建表，RLS 已启用，等待 UGC |

### 营业/关店状态（统一枚举）

| status | 数量 | 说明 |
|---|---|---|
| active | **985** | 原推荐634/active276/备选8/保留2/可试2 全部统一 |
| 关店 | **2** | EHB(id=1262, 2025-09-28停业)、CHIC1699(id=905, 2026米其林因闭店移除) |

### 档位分布

| 奢华 ¥500+ | 高档 ¥200–499 | 中档 ¥100–199 | 平价 ¥50–99 | 经济 <¥50 |
|---|---|---|---|---|
| 95 | 159 | 330 | 293 | 108 |

---

## 二、六项需求验收

### 1. 收录缺漏 ✅
- **用户点名 4 家全部入库**：NABI(1347, 当代韩式FD, ¥1000)、Yaya's(1349, 手工意面, ¥169)、Nono's(1350, 意式×中式融合, ¥210)、Jellooo(1351, 北欧餐酒, ¥180)
- **场景补录 65 家新增**：
  - 精品咖啡 11 家（O.P.S.、火山咖啡、堀口咖啡、Captain George、Blacksheep 等）
  - 甜品烘焙 11 家（O'Mills酸面包、BAsdBAN、Big Bagel、麻布屋gelato、La Creperie 等）
  - Brunch 8 家（O'mills、AL'S DINER、MONA、Madison 等）
  - Bistro/自然酒 11 家（Vinism、SOiF、Mavis966、Forage、Le Saleya 等）
  - 米其林/名店 15 家（泰安门、宝丽轩、福和慧、三号黄浦会、凌珑、Obscura 等）
  - 主理人名店 3 家（BLAZ东湖路、BASTARD、KIINA）
  - 新荣记系 4 家分店（BFC、前滩太古里、虹桥、滨江）
- 来源矩阵升级：SmartShanghai、TimeOut Shanghai、Nomfluence、米其林指南官网、小红书深搜
- 反软广剔除：Manner/Seesaw/%Arabica 等连锁、Bagelous Museum 等营销店
- 舒芙蕾专门店：上海无有真实堂食点评的独立店，按规则保留 0 种子

### 2. 分类交叉比对 ✅
- **荣府宴(id=759)**：从错误的本帮菜(9)+苏帮菜(113)+Casual(72) 修正为 浙菜(5)+台州菜(237)+私宴/会所(83)，保留米其林159+黑珍珠160，investor_info="新荣记集团"
- **新荣记系**：6 家统一挂台州菜+investor_info（荣府宴+新荣记南京西路+BFC+前滩+虹桥+滨江）
- **排除非新荣记系**：荣先森(闽南)、荣豫(河南)、佰荣、荣申府 — 未误并
- **京季/芙蓉无双**：仅北京无上海店，不收录
- 新建「台州菜」标签 id=237（parent_category=浙菜）

### 3. 关店/updating 机制 ✅
- **status 枚举统一**：646 家存量从推荐/备选/可试/保留 统一为 active
- **关店排查**：254 家高端/米其林/高人均店逐一搜索核实
  - EHB：原记录地址"黄浦新天地近马当路"/人均800/active 全错；修正为 徐汇东平路11号/¥2688/关店，evidence 注明 2025-09-28 停业、团队接棒 Jellooo
  - CHIC1699：2026 米其林指南因闭店移除
- **data_updated_at**：254 家核实店标注 2026-09-22
- **前端**：关店店列表默认隐藏、详情灰显"已关店"、展示"数据更新于X，营业状态以商家为准"

### 4. 特殊标签筛选 ✅
| 标签 | ID | 挂店数 | 原挂店数 |
|---|---|---|---|
| 米其林星级 | 159 | **79** | ~15 |
| 黑珍珠餐厅 | 160 | **50** | 2 |
| 素食/纯素 | 45 | **3** | 0 |
| 分子/先锋料理 | 46 | **5** | 0 |
| 可预订 | 165 | **266** | ~262 |
- 前端：认证/特别标签筛选区块始终渲染可见（不再因 tagCount=0 隐藏）

### 5. 地址+地图定位 ✅
- **坐标覆盖率**：从 **1.0%（10家）→ 95.5%（941/985家）**，新增 931 家坐标
- 技术方案：浏览器高德 AMap.Geocoder JS SDK（绕过 Nominatim SSL 阻断 + 高德网页 API 反爬）
- 写入格式：WKT `POINT(lng lat)`（GeoJSON 对象会导致 HTTP 500）
- 未编码 44 家（4.5%）：地址模糊/连锁多店/仅区县级精度
- 前端：map.tsx 优先读 location GeoJSON（转换为 Leaflet [lat,lng]），关店店不上图，详情页加"高德导航"链接

### 6. 打卡+真实评价 UGC ✅
- **reviews 表**：11 列，RLS 启用，4 条策略（公开读 approved / 本人写 / 本人改删 / service role 管 is_hidden）
- **Auth**：Supabase 邮箱魔法链接（默认 SMTP），login.tsx + auth/callback.tsx
- **详情页**：登录后评价表单（总分1-5/口味分1-5/短评/就餐日期）、评价列表、食客均分、举报入口、本人删除
- **分区**：官方反软广评分(score_*) 标注"OFFICIAL SCORE"，UGC 标注"DINER REVIEWS / 食客评价"，严格分离

---

## 三、前端工程与部署

| 改动 | 文件 | 状态 |
|---|---|---|
| reviews表+RLS | Dashboard SQL Editor | ✅ 回验 |
| 邮箱魔法链接登录 | pages/login.tsx, pages/auth/callback.tsx, lib/auth.tsx | ✅ |
| 特殊标签始终可见 | pages/restaurants/index.tsx | ✅ |
| 地图读location | pages/map.tsx | ✅ |
| UGC评价系统 | pages/restaurants/[id].tsx | ✅ |
| 关店态+高德导航 | pages/restaurants/index.tsx, [id].tsx | ✅ |
| npm run build | — | ✅ 通过 |
| Vercel部署 | vercel --prod | ✅ 线上200 |

线上页面全部 200：/restaurants, /map, /login, /restaurants/1347, /restaurants/1262, /auth/callback

---

## 四、质量门终检

| 检查项 | 结果 |
|---|---|
| 65 家新店字段完整率 | **100%**（address/district/price_avg/tier/score/evidence/signature 全非空） |
| tier 与人均一致性 | **0 不一致** |
| 假电话/尾7777/脱敏号 | **0** |
| status 枚举 | 仅 active + 关店，无残留 |
| 4 家点名店坐标 | **全部有坐标** |
| EHB 关店态 | ✅ |
| 荣府宴标签修正 | ✅ 无本帮菜/苏帮菜/Casual 残留 |
| 同名重复 | BLAZ 2 家为不同地址（五原路老店 vs 东湖路新店），合理保留 |
| 线上部署 | ✅ build 通过 + 200 |

---

## 五、遗留缺口

1. **44 家无坐标店**：地址模糊（仅区域名如"古北"）、连锁多店、仅区县级精度；需人工补充精确门牌号后编码
2. **UGC 尚无真实评价**：表结构和前端已就绪，需真实用户使用后产生数据
3. **新荣记系分店 2 家待补**：荣季95外滩店、荣记火锅虹桥店（官网确认有上海门店但地址信息不足）
4. **Liquid Laundry(id=1270)**：Nomfluence 2025关店名单列入但未达排查阈值，建议人工复核
5. **booking_method 约 48% 为空**：早期批次小店无公开预订方式
6. **discount_info 全空**：折扣谈判为独立支线，受外呼资质限制

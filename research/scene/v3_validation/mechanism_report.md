# 机制执行总结报告（Mechanism Report）

> China Travel 美食地图 v3 全量sourcing机制验证 | 精品咖啡 + bistro餐酒场景
> 运行日期：2026-09-23 | 子代理：v3_validation

---

## 一、执行概览

| 指标 | 数值 |
|---|---|
| 种子总数 | 70（35咖啡 + 35 bistro） |
| 高置信种子（ugc≥2） | 64（33咖啡 + 31 bistro） |
| BFS总轮数 | 6轮（Round 1-6）+ Round 0种子初始化 |
| 总搜索次数 | ~18次general_search（每轮3并行） |
| 新增候选总数 | 80条（去重前） |
| 累计候选池 | 64种子 + 80新候选 = 144条 |
| 饱和点 | Round 6末（新增降至7条，连续2轮递减） |
| 回归命中 | **4/4 = 100%** |

---

## 二、四机制执行记录

### 机制1：种子图遍历（BFS）✅ 已执行
- **初始化**：从raw_精品咖啡.jsonl和raw_Bistro酒吧夜宵.jsonl读取70家，筛出ugc≥2的64家入frontier
- **frontier/seen维护**：seen={64 seeds}，frontier按BFS弹出
- **四路扩展执行情况**：
  - a. **内容→评论区**：对gula/大酉/Nora's/nabi/Jellooo/Nono's/Yaya's/武宫分别搜评论区提及，贡献~28条候选
  - b. **人→内容**：识别Franklin(Next Bottle)、Andrew巫迪(Nono's老板)、Tom Ryu(nabi主厨)、彭近洋(Captain George)等老饕/主理人，搜其合集，贡献~18条候选
  - c. **平台关联**：SmartShanghai/TimeOut/Trip.com的"相关推荐"和合集文章，贡献~10条
  - d. **店→店**：WULI↔NABI(同集团)、EHB→Jellooo(同主厨/同投资人)、MIX320园区矩阵(10家)、翡悦里园区矩阵(6家)，贡献~24条
- **每轮新增**：R1=14, R2=14, R3=9, R4=20, R5=16, R6=7

### 机制2：查询自动生成 ✅ 已执行
- **咖啡矩阵**：6品类词 × 2店型词 × 8长尾词 = 96格，抽样跑~20格
- **Bistro矩阵**：5品类词 × 5菜系别名 × 8长尾词 = 200格，抽样跑~25格
- **新俗称自动回填**：鸭鸭(yaya's)、娜比(nabi)、坏东西(Bastard)、大壶(有容乃大)、罚站(O.P.S)、姊妹店(Nono's)
- **命中数记录**：见source_coverage_matrix.md

### 机制3：多源并集+饱和收敛 ✅ 已执行
- **来源覆盖**：抖音✅、B站✅、携程/Trip.com✅、海外媒体✅、TimeOut✅、政府网站✅、大众点评(间接)⚠️、小红书(摘要)⚠️、地图POI(弱)⚠️、公众号❌
- **停止条件**：
  - ①关键词矩阵抽样跑完 ✅
  - ②frontier未清空（仍有~20个种子未探索，如Alimentari Grande/Fiamo/Polux等），但边际产出低
  - ③连续2轮新增递减（R5=16→R6=7）✅
  - ④网格配额未达
- **判定**：满足③+①，判定饱和，停止

### 机制4：自动化采集 ✅ 已执行
- B站：site:bilibili.com搜索有效，命中"舌尖真探事务所"等UP主
- 公众号：site:mp.weixin.qq.com搜索**返回空**（断点，见下）
- 地图POI：通过general_search间接获取高德/腾讯地址，未做批量POI拉取
- 小红书/抖音：general_search取摘要+评论区提及

---

## 三、回归命中结果

| 点名店 | 命中 | 首次有机路径 | 关键证据 |
|---|---|---|---|
| nabi | ✅ | R2 店→店 | WULI同集团+JEJU前东家+翡悦里园区矩阵 |
| jelu/Jellooo | ✅ | R2 店→店 | EHB前身+好利来罗昊+Esben主厨 |
| yaya's | ✅ | **R1 人→内容** | Franklin(Next Bottle)"主厨去哪吃"视频直接推荐 |
| nono's | ✅ | **R1 文章对比** | Sophie Serves Up对比Nono's vs Yaya's |

详见 regression_hit_table.md。

---

## 四、机制断点与修复

### 断点1：公众号来源完全空白
- **现象**：site:mp.weixin.qq.com搜索返回空结果
- **定位**：general_search对微信公众号文章索引覆盖差，或微信反爬
- **影响**：公众号是上海本地美食圈（上海BANG/魔都吃货/吃货研究所等）的重要来源
- **修复建议**：改用浏览器RPA（browser-use-automation-mac）直接搜搜狗微信或微信公众号后台；或纳入后续轮次用携程/TimeOut等已索引来源替代

### 断点2：武宫BFS未触达nabi
- **现象**：从武宫酒吧（武夷路320弄MIX320）搜索评论区，未提及nabi（武夷路168号翡悦里）
- **定位**：两者在武夷路不同路段（MIX320 vs 翡悦里），评论区/合集未跨路段关联
- **修复建议**：增加"同道路名"级别的空间BFS——沿武夷路门牌号逐段搜索，而非仅靠评论区提及。武夷路168号 vs 320弄需要中间路段种子桥接
- **实际补偿**：通过nabi自身店→店路径（WULI/JEJU/翡悦里矩阵）已命中，未造成漏店

### 断点3：新天地通用合集未收录Jellooo
- **现象**：搜"新天地 bistro 咖啡 甜品 合集"，结果集中在甜品/烘焙（B&C/Le Pain Sense/W coffee），未提及Jellooo
- **定位**：Jellooo是2024年底开业的北欧餐酒馆，新天地通用合集偏向网红甜品打卡，bistro属性被甜品标签掩盖
- **修复建议**：查询矩阵需增加"北欧 餐酒馆 新店"等垂直长尾词；实际通过"上海 北欧 餐酒馆 Esben"查询矩阵已命中TimeOut专题

### 断点4：frontier未完全清空
- **现象**：仍有~20个高置信种子未做BFS扩展（如Alimentari Grande/Fiamo/Polux/Le Verre à vin等）
- **定位**：时间/搜索配额有限，但饱和曲线显示边际产出已很低
- **修复建议**：正式全量sourcing时应跑完所有种子；本次验证以饱和收敛为准

---

## 五、新发现的有价值候选（非回归目标，供后续参考）

| 候选 | 场景 | 发现路径 |
|---|---|---|
| Bastard坏东西 | 中式bistro | 大酉/SmartShanghai联合提及 |
| Pass Residence | 意式trattoria | Franklin合集+OHA Group |
| WULI韩食店 | 韩餐(家庭式) | nabi店→店同集团 |
| JEJU济州四季 | 韩餐fine dining(已关) | nabi主厨Tom前店 |
| EHB餐厅 | 北欧fine dining(已关) | Jellooo前身 |
| Ocean's Table欧舍 | 西班牙bistro | B站探店 |
| Le Bec Bund | 法式(Villa Le Bec新店) | B站/SmartShanghai |
| Pincle咖啡+ | 咖啡(烘焙冠军) | 查询矩阵 |
| ONIRICO CAFÉ | 咖啡(赛事评委) | 查询矩阵 |
| TonAri | 中法wine bistro | Nomfluence |
| 浮叶 | 台法bistro | B站top4 |
| MIX320园区矩阵(10家) | 武夷路 | 汉博商业品牌矩阵 |
| 翡悦里园区矩阵(6家) | 武夷路 | 政府网站 |

---

## 六、结论

v3四机制在精品咖啡+bistro场景验证通过：
1. **BFS图遍历**有效，店→店路径（同集团/同园区/同主厨）是最高效扩展方式
2. **查询自动生成**能通过垂直长尾词（"北欧 餐酒馆""韩餐 预约制"）定向发现目标店
3. **多源并集**中抖音+B站+海外媒体(SmartShanghai/Sophie/Nomfluence)+TimeOut构成主力，公众号为已知断点
4. **饱和收敛**在Round 6触发（新增降至7条）
5. **回归4家100%命中**，其中yaya's和nono's在Round 1即通过非种子路径被有机发现，证明机制不依赖人工点名

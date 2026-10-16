# food-radar 知识库文档：本地新品餐饮情报雷达

> 版本 v1.1 ｜ 沉淀日期 2026-10-16 ｜ 来源：上海餐厅情报调研实战 + 踩坑复盘 + 工具链实测安装
> 用途：灌入知识体作为长期记忆，供任意 agent 复用

---

## 0. TL;DR

- **Skill 地址**：https://github.com/huming0018-dot/china-travel-food/tree/main/skills/food-radar （本地副本：~/.codebuddy/skills/food-radar/）
- **一句话方法论**：环境自检 → 对标解码 → 关键词矩阵 → 多通路分级检索（S/A/B/C）→ 时效与信源校验（三条铁律）→ 结构化输出与沉淀。
- **三条铁律**：①"新开/在营"必须双独立信源且均带当年日期；②引用文章前必须核对发布日期；③上榜≠在营，交付前必须做闭店/退出核查。
- **已修正错误**：攏好粤菜并非 2026 年 10 月新开——其信息源自 2024-10 文章，且该店 2024 年已退出上海，已从推荐位移除。
- **开工必做**：`bash scripts/preflight.sh`。工具"已克隆"≠"可用"，依赖缺失必须显式告知降级方案。

---

## 1. 方法论（六步工作流）

### Step 0 环境自检（v1.1 新增，不可跳过）
先跑 `bash scripts/preflight.sh`。有阻塞项先补齐；补不齐必须明确告知用户降级方案，**禁止静默降级**。
实测安装状态见第 2.6 节与 `references/environment.md`。

### Step 1 对标解码
用户给的对标物是最高价值输入。拆解维度：菜系路线、主厨履历、价位带、荣誉（米其林/黑珍珠/亚洲50佳/必吃榜）、玩法（omakase/联弹/会员制）、稀缺性、可合作性。
实战案例：头灶 = 中餐 omakase + 米其二星 + 主厨发办 + 高客单 + 提前数月预订；遇外滩联弹 = 高端地方菜系 × 米其林/亚洲50佳餐厅四手/六手联弹。
**无法确认的对标物必须显式声明假设**（实战中"永和遇外滩"公开渠道检索不到，已向用户声明）。

### Step 2 关键词矩阵
`城市 × 品类 × 时间 × 事件类型` 四维组合，≥6 组查询：
- 时间词：当年、近3个月、近6个月、具体月份
- 事件词：新开、首店、试营业、联弹、客座、快闪、晚宴、闭店、停业、退出
- 品类词：用户指定 + 对标同类 + 当季热门

### Step 3 多通路分级检索
信源分级（冲突时高级别赢）：

| 级别 | 信源 | 用途 |
|---|---|---|
| S | 官方公告、政府/官媒（上观等）、榜单官网 | 开业/闭店事实、荣誉 |
| A | 行业媒体、KOL 长文/视频 | 主厨背景、联弹事件、口碑 |
| B | 平台 UGC（大众点评、小红书、抖音） | 真实食客反馈、订位难度 |
| C | 聚合软文、百家号种草 | 仅线索，必须升级验证 |

检索顺序：S 定事实 → A 补故事 → B 验口碑 → C 只发现线索。

### Step 4 时效与信源校验
见第 4 节三条铁律，违反即返工。

### Step 5 结构化输出与沉淀
按字段规范输出，每条带 sources 数组和 confidence；交付后把信源、踩坑、用户口径偏好沉淀进长期记忆，形成复利。

---

## 2. 工具调用流程与技术规范

### 2.1 调用流程
```
Step0 环境自检        → bash scripts/preflight.sh，阻塞项先补齐或告知降级
Step1 对标解码        → 纯推理，产出筛选标准
Step2 关键词矩阵      → 产出 6-10 组查询
Step3 多通路检索      → web_search/web_fetch（S级事实）
                        wechat-article-search（KOL长文，依赖Node）
                        agent-reach CLI（小红书/抖音/B站/微博/Reddit/Twitter/YouTube）
                        media-crawler（批量抓取，Playwright+登录态）
                        agent-browser/playwright（点评店铺页、小红书详情页）
                        dianping-crawler（全上海店铺库，竞品盘点）
Step4 时效与信源校验  → 日期/双信源/在营核查
Step5 结构化输出      → JSON+摘要，知识沉淀
```

### 2.2 平台覆盖矩阵

| 平台 | 首选工具 | 备选 |
|---|---|---|
| 大众点评 | dianping-crawler（需 JDK+Maven） | agent-browser / web_search 拿 UGC 摘要 |
| 小红书 | media-crawler `xhs` | agent-reach（需手动导 Cookie）、web_search |
| 抖音 | media-crawler `dy`（**唯一主通路**） | web_search |
| B站 | agent-reach | web_search |
| 微博 | media-crawler `wb` / agent-reach | web_search |
| 微信公众号 | wechat-article-search（需 Node） | web_search |
| 新闻/政府/行业媒体 | web_search + web_fetch | — |
| 榜单官网 | web_fetch | web_search |

### 2.3 安装命令（v1.1 实测可用版）
> 说明：GitHub 仓库不包含 tools/ 下的第三方克隆（体积大且各自有许可），需按下列命令自行安装。
> ⚠️ **必须用 uv + python3.12**：系统 python3 为 3.9.6，不满足 MediaCrawler 的 `requires-python>=3.11`。

```bash
# 前置：uv 与 python3.12 在此目录
export PATH="/Users/deuce/.local/bin:$PATH"

# 开工自检（每次必跑）
bash scripts/preflight.sh

# Agent-Reach
cd tools/agent-reach && uv tool install .
agent-reach doctor          # 通路自检
agent-reach skill --install # 注册 skill 到 ~/.agents/skills/agent-reach

# MediaCrawler
cd tools/media-crawler
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/playwright install chromium
# 支持 xhs(小红书) dy(抖音) ks(快手) bili(B站) wb(微博) tieba(贴吧) zhihu(知乎)

# 点评爬虫（Java + Maven 工程，需本机有 JDK 与 mvn）
git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler
```

### 2.4 技术规范
1. 频率控制：同平台请求间隔 ≥3s，单次任务 ≤50 页面，失败退避 30s×3 次。
2. 登录态 cookie 只存本地，不进仓库、不进交付物。
3. 合规红线：仅学习研究，不商用、不大规模爬取，遵守平台条款。
4. 落盘分离：原始数据 `data/raw/日期-平台-关键词.json`，清洗结果 `data/clean/`。
5. 单通路失败降级备选，不阻塞主流程，notes 记录。

### 2.5 实战信源清单（上海场景）
- S 级：上观新闻、静安官媒、虹口区政府网、米其林/黑珍珠/必吃榜官方
- A 级：搜狐吃喝、网易、新浪、澎湃、界面；KOL：B站"特厨隋坡"、微博@卡米camille、公众号"食在十三""周末做啥""槟客文化"
- B 级：大众点评、小红书、Trip.com 游记
- C 级：百家号种草（仅线索）

### 2.6 环境实测基线（2026-10-16，macOS）

| 组件 | 状态 | 阻塞项 / 说明 |
|---|---|---|
| MediaCrawler | ✅ 可运行 | venv(py3.12) + 依赖完整 + chromium 已落地；**仍需人工扫码登录存 cookie** |
| Agent-Reach v1.5.0 | ⚠️ 4/16 通路 | 实测可用：B站、Jina Reader 任意网页、V2EX、RSS |
| dianping-crawler | ❌ 不可构建 | 已克隆但无 Java / 无 Maven |
| wechat-article-search | ❌ 不可运行 | 无 Node |
| gh CLI | ❌ 未安装 | 推送走 SSH（`~/.ssh/ctfs_github`，账号 `huming0018-dot`） |

运行时：系统 python3 = 3.9.6（**不可用于 MediaCrawler**）；可用 python3.12 在 `/Users/deuce/.local/bin/`；uv 0.12.23。

**四个必须记住的通路事实**：
1. **抖音不在 agent-reach 覆盖范围**，只能走 MediaCrawler 的 `dy` 平台。
2. **小红书**双通路：MediaCrawler `xhs`（主）+ agent-reach（需Cookie-Editor 手动导出 `xhs` cookie，无法自动完成）。
3. **点评**因缺 JDK/Maven 暂不可构建，降级方案 = `agent-browser` / `playwright-cli` 打开店铺页 + `web_search` 取 UGC 摘要，取到的评分/人均必须标注来源与抓取时间。
4. **Node 缺失**导致微信公众号通路不可用，需先装 Node 才能补上。

---

## 3. 字段规范（输出 Schema）

```json
{
  "query_context": {"city":"上海","time_window":"近6个月","benchmarks":["遇外滩联弹","头灶"],"generated_at":"2026-10-16","generator":"food-radar v1.0"},
  "items": [{
    "name": "string 必填",
    "type": "new_opening | collab_event | closure_alert 必填",
    "status": "open | closed | upcoming | unknown 必填",
    "cuisine": "string 必填",
    "city/district/address": "string（new_opening必填）",
    "opened_date": "YYYY-MM-DD 或 null，禁止猜",
    "closed_date": "closure_alert必填",
    "chef": {"name","title","background"} 选填,
    "price_per_head": "number 或 null",
    "honors": [{"award","year"}],
    "kol_mentions": [{"platform","account","url","date","summary"}],
    "platform_signals": {"dianping":{"rating","review_count","fetched_at"},"xhs":{"note_count","fetched_at"}},
    "collaboration_angle": "string 选填",
    "sources": [{"url","publisher","date","tier":"S|A|B|C"}] 必填,
    "confidence": "high（双S/A信源）| medium | low（仅C级）必填",
    "verified_at": "YYYY-MM-DD 必填",
    "notes": "假设/待确认事项"
  }],
  "excluded": [{"name":"string","reason":"string"}]
}
```
硬约束：closure_alert 必须 status=closed 且 closed_date 必填；sources 为空或 confidence=low 的条目禁止进正式推荐位；日期一律 ISO 格式；拿不到的数据填 null 并说明，禁止编造。

---

## 4. 校验规范（三条铁律）

1. **双信源+日期规则**："新开/在营"结论必须两个独立信源且都带当年日期；只有一个 → confidence 降 medium 并标注待核实。
2. **发布日期核对规则**：引用任何文章前必须核对并记录发布日期；搜索引擎摘要不带年份时必须打开原文确认，禁止凭内容语感判断新旧。
3. **在营核查规则**：上榜/获奖 ≠ 在营；每家店交付前检索"店名+闭店/停业/退出"，有闭店信号移入 excluded 并注明原因。

补充规则：
- 信源冲突：S>A>B>C；同级别取日期新者；仍冲突双方都写 notes 并降一级 confidence。
- 数值信息（评分/人均/榜单）必须带"来源平台+抓取日期"；米其林/黑珍珠荣誉必须带年份。
- 交付前 checklist 七项全过才可交付（详见 skill 的 references/checklist.md）。

**失败案例登记**：
| 日期 | 案例 | 违反规则 | 后果 |
|---|---|---|---|
| 2026-10-16 | 攏好粤菜误列"2026年10月新开" | 铁律2（2024-10文章误判）+铁律3（未做在营核查，实际2024年已退出上海） | 用户纠正后移出推荐位，沉淀为本规范 |
| 2026-10-16 | tools/ 下三工具"已克隆"但均不可运行 | 缺少开工环境自检；把"已克隆"误当"可用" | 新增 Step 0 + `preflight.sh` + `environment.md` |
| 2026-10-16 | `preflight.sh` 用 `command -v java` 判定 JDK | macOS `/usr/bin/java` 存根无 JRE 时仍返回 0，误报 OK | 改为匹配 `java -version` 输出中的版本号 |

---

## 5. Prompt 模板与检索 Checklist

### 5.1 主 Prompt 模板（变量化）
```
你是本地餐饮情报分析师。请按以下要求调研：
【城市】{city}  【时间窗】{time_window}  【品类范围】{categories}
【对标物】{benchmarks} —— 若公开渠道无法确认，先声明假设并请用户确认，不得默认
【输出要求】
 - 分两类：①新开/在营商户（主厨背景、荣誉、口碑证据）②联弹/客座/快闪事件（时间、参与方、参与方式）
 - 每条带信源（url+发布方+发布日期+信源级别）和 confidence
 - 交付前完成在营核查（闭店/停业/退出），有问题的移入"已剔除"区并注明原因
 - 评分/人均等精确数据标注来源平台与抓取时间，拿不到填 null，禁止编造
 - 口碑多通路交叉：官方媒体 + KOL + 平台UGC（大众点评/小红书/抖音）
【交付格式】JSON（按字段规范）+ 人类可读摘要
```

### 5.2 每日抓取模式
```
以 food-radar 规范执行每日增量扫描：
1. 关键词矩阵跑 web_search："{city} 新开餐厅/首店/联弹/客座/快闪/闭店"+时间词
2. 命中条目做在营与日期校验
3. 与昨日去重，只输出：新增、状态变化（开→关）、口碑异动（新上榜/新KOL提及）
4. 输出精简日报（≤20条/天），必填字段齐全
```

### 5.3 检索 Checklist（摘要）
- 准备：城市/时间窗/品类确认；对标解码；**已跑 `preflight.sh` 且阻塞项已补齐或已明确告知降级**；关键词矩阵≥6组
- 检索：web_search≥8组；高价值页 web_fetch 读原文记日期；微信检索≥2组；[deep] agent-reach/media-crawler/agent-browser
- 校验：日期显式；双信源；在营核查；数值带来源；软文未直接引用
- 输出：JSON 必填齐全；分两类+口碑证据+合作切入点；已剔除区；假设声明
- 沉淀：新信源入清单；新踩坑入案例表；用户偏好入长期记忆

---

## 6. 实战校准记录（2026-10-16，上海）

### 6.1 已修正
- **攏好粤菜**：初判"2026年10月新开"错误。实为 2024-10 首店信息，且 2024 年已退出上海 → 移出推荐位。

### 6.2 校准后的推荐位（均核对当年信源）
新开/在营：潮玖（虹口新建路200号，解香楼主理人新作，主理人任海鹏2025黑珍珠年轻主厨奖，10.24香槟晚宴）；头家夜粥（外滩大来大楼，广州三次米其林推荐，2026-06-18试营业）；Club Bâtard 上海（查公馆，Daniel Calvert+JJ Lin，2026年11月揭幕）；Le Bec Bund（外滩老市府，Nicolas Le Bec，2026-05）；西里尔 KIRILLITSA（外滩老市府5楼，俄罗斯最年轻米其林星厨）；Le Reflet（上海大厦2楼，2026-06）；Nous（洛克·外滩源，主厨Ugo）；席上·福建料理（苏河湾万象天地）；Kylin 麒麟（外滩瑞吉，戴龙顾问）。
联弹/客座：迷上PRADA荣宅四手联弹（2026-10-30）；潮玖×槟客香槟晚宴（2026-10-24，5980元/位限10席）；遇外滩×广州文华东方「江」（2026-08）；遇外滩×三亚太阳湾柏悦（2026-09）；toyo eatery 快闪客座（2026-03）。
榜单锚点：2026米其林沪苏浙（头灶升二星；三月醉淮扬、Fabula新晋一星）；2026黑珍珠（上海61家）；2026必吃榜（上海160家全国第一）。

### 6.3 待确认
- "永和遇外滩"合作公开渠道未检索到，需用户确认所指。

---

## 7. 复用指南（换城市/品类）

1. 复制 skill 目录，改 `scripts/keyword-matrix.yaml` 的 variables。
2. 信源清单按城市替换本地官媒与 KOL（工具链、校验、字段规范不变）。
3. 首次使用先跑一次 standard 深度建立基线，之后走每日增量模式。
4. 每次实战后把新信源、新踩坑按格式追加进 references，保持知识体滚动更新。

---
name: food-radar
description: 本地新品/热门餐饮情报雷达。当用户想了解某城市最近新开的餐厅、主厨联弹晚宴、客座快闪（"飞行厨房"）、闭店预警，或需要做餐饮竞品/合作标的调研时使用。覆盖大众点评、小红书、抖音、B站、微博、微信公众号、新闻媒体等多通路检索，输出经时效与信源校验的结构化情报。触发词：新开餐厅、探店、美食情报、联弹、客座、快闪晚宴、黑珍珠、米其林、必吃榜、餐饮调研。
---

# food-radar 本地新品餐饮情报雷达

## 适用场景

- "最近上海有什么新开的餐厅/口碑好"
- "有没有主厨联弹、客座快闪（飞行厨房）活动"
- 对标调研（给一个对标物，如"遇外滩的合作""头灶"）
- 闭店/停业预警核查
- 每日/每周餐饮情报抓取

## 核心工作流（五步，顺序不可乱）

### Step 1 对标解码
把用户给的对标物翻译成可操作的筛选标准：
- 拆解对标物的：菜系路线、主厨背景、价位带、荣誉（米其林/黑珍珠/亚洲50佳/必吃榜）、玩法（omakase/联弹/会员制）、稀缺性（预订难度）。
- 产出筛选标准，写进输出里让用户确认口径。

### Step 2 关键词矩阵
按 `城市 × 品类 × 时间 × 事件类型` 组合，至少覆盖：
- 时间：当年、近3个月、近6个月、上月
- 事件：新开、首店、试营业、联弹、客座、快闪、晚宴、闭店、停业、退出
- 品类：用户指定 + 对标物同类 + 当前热门（潮汕菜、福建菜、法餐、bistro 等）

### Step 3 多通路检索（按优先级）
1. **web_search / web_fetch**：官方媒体、政府号、行业媒体（开业事实最快最可靠）
2. **wechat-article-search**：KOL 长文（周末做啥、食在十三等）
3. **agent-reach CLI**：小红书、抖音、B站、微博、YouTube、Twitter、Reddit、GitHub 搜索
4. **media-crawler**：小红书/抖音/B站/微博/知乎批量抓取（需登录态）
5. **agent-browser / playwright**：大众点评店铺页、小红书详情页
6. **dianping-crawler**：全量餐饮店铺库（竞品盘点用）

各工具安装与用法见 `references/toolchain.md`。

### Step 4 时效与信源校验（铁律，违反即返工）
- **任何"新开"结论必须有两个独立信源，且都带明确的当年日期。**
- 文章必须核对**发布日期**，不能只看内容像"最近"。
- 闭店/退出必须单独核查，上榜餐厅≠在营（见 `references/validation.md`）。

### Step 5 结构化输出与沉淀
- 按 `references/field-spec.md` 输出 JSON/Markdown。
- 通过 `references/validation.md` 全部硬规则后才交付。
- 用户认可后，把方法论、信源、踩坑沉淀到长期记忆/知识库。

## 平台覆盖矩阵

| 平台 | 首选工具 | 备选 |
|---|---|---|
| 大众点评 | dianping-crawler + agent-browser | web_search 拿 UGC 摘要 |
| 小红书 | media-crawler / agent-reach | web_search |
| 抖音 | media-crawler / agent-reach | web_search |
| B站 | agent-reach | web_search |
| 微博 | media-crawler / agent-reach | web_search |
| 微信公众号 | wechat-article-search（独立 skill） | web_search |
| 新闻/政府/行业媒体 | web_search + web_fetch | — |
| 榜单官网 | web_fetch（米其林/黑珍珠/必吃榜） | web_search |

> 依赖说明：`wechat-article-search` 为同机独立 skill（`~/.codebuddy/skills/wechat-article-search/`）；media-crawler / agent-reach / dianping-crawler 需按 `references/toolchain.md` 自行克隆安装，本仓库不含 tools/。

## 红线

- 爬虫仅用于学习研究，控制频率，不商用、不大规模爬取（MediaCrawler 许可约束）。
- 无法验证的信息必须标注 `confidence: low` 并向用户说明，不得装作确认。

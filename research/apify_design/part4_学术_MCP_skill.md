# Part 4 — 学术调研 / MCP Server / 本地 Skill 评估

> 范围：仅调研，不实现、不采购、不写库。所有链接与本地路径均为 2026-10-01 实际检索/查找结果；找不到的对象如实标注「未找到」。

---

## 一、学术文献

### 1.1 餐饮 / 菜品级 ABSA（aspect-based sentiment）

| 工作 | 作者/年份 | 链接 | 可借鉴点 |
|---|---|---|---|
| **Beyond the Star Rating: A Scalable Framework for ABSA Using LLMs and Text Classification** | arXiv 2026 | https://arxiv.org/html/2602.21082 | LLM 先抽样人工/弱标 aspect，再用经典 ML 分类器在 470 万条 17 年餐厅点评上规模化打分——正好是我们「LLM 抽 aspect + 小模型批量推理」的范式样板。 |
| **Dynamic Sentiment Analysis with Local LLMs using Majority Voting: A Study on Factors Affecting Restaurant Evaluation** | arXiv 2024 (2407.13069) | https://arxiv.org/html/2407.13069v1 | 本地化小模型 + majority voting 控成本；明确量化「菜品口味 / 用餐体验 / 拥挤度」对评分的边际贡献，可直接对标我们的 aspect_* 字段设计。 |
| **ZZU-NLP at SIGHAN-2024 dimABSA Task: Coarse-to-Fine In-context Learning** | arXiv 2024 (2407.15341) | https://arxiv.org/html/2407.15341v1/ | SIGHAN dimABSA 是 restaurant review 上的细粒度情感强度（valence/arousal）评测，说明学术圈已把「菜品味觉」作为独立 aspect term 而不只是 food 大类。 |
| **细粒度情感分析在到餐场景中的应用（美团技术团队）** | 美团 2021（工业实践，SegmentFault 转载） | https://segmentfault.com/a/1190000041109186 | 明确拆解「菜品—属性—观点—情感」四元组，与我们 raw_review 里 aspect_taste / aspect_service / aspect_price 的字段口径一致；可直接拿来做标注 schema 对齐。 |

### 1.2 虚假 / 水军点评检测（fake review / opinion spam / astroturf）

| 工作 | 作者/年份 | 链接 | 可借鉴点 |
|---|---|---|---|
| **Unmasking Falsehoods in Reviews: An Exploration of NLP Techniques** | arXiv 2023 (2307.10617) | https://arxiv.org/pdf/2307.10617v3 | 直接在 Yelp Deceptive Opinion Spam Corpus（餐厅子集）上做 n-gram + 5 类 ML 基线，给我们一个可复现的 baseline，用于筛除明显水军点评。 |
| **Combat AI With AI: Counteract Machine-Generated Fake Restaurant Reviews on Social Media** | arXiv 2023 (2302.07731) | https://arxiv.org/pdf/2302.07731v1 | 微调 GPT-2 判别 AI 生成的假餐厅点评——2026 年小红书/抖音大量 AI 软文场景下，这条思路必须纳入「去软广」管线。 |
| **Recent state-of-the-art of fake review detection: a comprehensive review** | Cambridge University Press, 2024 (Natural Language Engineering) | https://www.cambridge.org/core/services/aop-cambridge-core/content/view/F02E8339C43A62BA63EBD54A1608F785/S0269888924000067a.pdf/recent-state-of-the-art-of-fake-review-detection-a-comprehensive-review.pdf | 最新综述，系统对比 supervised / unsupervised / graph-based / LLM-based 方法，可作为我们选型的决策树。 |
| **AiGen-FoodReview: A Multimodal Dataset of Machine-Generated Restaurant Reviews and Images on Social Media** | SciSpace 开放数据集 | https://scispace.com/pdf/aigen-foodreview-a-multimodal-dataset-of-machine-generated-2ai0gy45mo.pdf | 关键结论：OpenAI 文本检测器在食评上不如随机猜（<50%），必须走「图文多模态 + 自监督微调」；提示我们不能只靠现成 LLM detector。 |
| **FraudEagle: Opinion Fraud Detection in Online Reviews by Network Effects**（经典，2013） | Akoglu, Chandy, Faloutsos — ICWSM 2013 | 通过 Semantic Scholar 收录：https://www.semanticscholar.org/paper/Detecting-AI-Generated-E-Commerce-Reviews-with-and-Balc%C4%B1-Erdo%C4%9Fan/112944a11b5e880cfbff875c82fdb81881d0810e | 审稿网络（reviewer–product 二部图）抓合谋水军；当我们后面有跨店评论者重合度数据时可直接搬这套图算法。 |

### 1.3 跨平台社交媒体采集（技术侧）

> 学术同行评审文献偏少，工程界事实标准是开源爬虫框架。

| 工作/项目 | 年份 | 链接 | 可借鉴点 |
|---|---|---|---|
| **NanmiCoder/MediaCrawler**（开源框架，支持 xhs / douyin / kuaishou / weibo / zhihu / bilibili / tieba） | 2023 起持续维护 | https://socai.io/blog/xiaohongshu-automation-tools （横向对比文中列为第 7 号） | 目前国内跨平台采集事实上的开源底座；走「逆向 API」而非浏览器渲染，量大利薄但脆弱。我们对比 Apify Actor 时主要参照系。 |
| **Multilingual Compliance: A Comparative Study of Privacy Policies in Chinese, Japanese, and Korean** | OpenReview 2024 | https://openreview.net/pdf?id=6HYgXTidKR | 给出中日韩三语隐私政策合规维度编码表，可直接复用到我们采集前的合规 checklist。 |

### 1.4 PIPL / GDPR 合规数据采集

| 工作 | 作者/年份 | 链接 | 可借鉴点 |
|---|---|---|---|
| **EDPB Guidelines 03/2020 on web scraping in the context of generative AI**（2026 更新版） | European Data Protection Board, 2026-07 | https://www.edpb.europa.eu/system/files/2026-07/edpb_guidelines_2020603_webscraping_v1_en_0.pdf | 欧盟最新官方口径：抓取公开网页=处理个人数据，需合法利益基础、最小化、匿名化、遵守 robots/ai.txt。直接作为 GDPR 侧红线。 |
| **洪延青：AI 时代的数据爬取治理——法律冲突与利益平衡之道** | 中国政法大学法治政府研究院，2025-09 | https://fzzfyjy.cupl.edu.cn/info/1035/17360.htm | 国内最权威的爬取合规论述之一：即便个人信息已公开，处理者仍须在「合理范围」内，且不得损害个人权益。 |
| **On the Tort Liability of Scraping Publicly Available Personal Data**（论爬取公开个人信息的侵权责任） | 《法学家》2026 年第 3 期 | https://faxuejia.ruc.edu.cn/EN/Y2026/V0/I3/77 | 最新教义学结论：超出合理范围爬取公开个人信息，爬取方负过错推定责任，且遵守 robots.txt 不能免责——我们采集策略必须留痕、最小化、可删除。 |
| **Understanding Chinese Internet Users' Perceptions of, and Online Platforms' Compliance with, PIPL** | ACM 2023 (CHI/CSCW 系) | https://dl.acm.org/doi/pdf/10.1145/3637415 | 实证：PIPL 生效后 13 家平台隐私政策合规率上升，但跨境传输条款仍弱——提醒我们涉及境外账号/数据出口要单独评估。 |

---

## 二、MCP Server 调研

### 2.1 Apify 官方 MCP server

- **仓库**：https://github.com/apify/apify-mcp-server
- **托管端点**：`https://mcp.apify.com`（HTTP Streamable，自带 `.mcpb` 一键安装包：https://github.com/apify/actors-mcp-server/releases/latest/download/apify-mcp-server.mcpb ）
- **可用性**：官方维护，活跃。最新 release **v0.16.0，2026-09-17**（仅距调研日 14 天），changelog 见 https://www.freshcrate.ai/projects/apify-mcp-server
- **文档**：https://docs.apify.com/platform/integrations/mcp
- **调度 Actor 的方式**（关键机制）：
  1. MCP server 暴露一组内置工具：`search-actors` / `fetch-actor-details` / `start-actor` / `get-actor-run` / `get-actor-run-list` / `get-actor-run-log` / `get-dataset-items` 等。
  2. **白名单裁剪**：URL query `?tools=owner/actor-slug,another/actor` 即可只把指定 Actor 挂成一个 tool，避免把整个 Store 暴露给 agent。例：`https://mcp.apify.com?tools=apify/rag-web-browser`。
  3. 鉴权：`Authorization: Bearer <APIFY_TOKEN>`，按量走 Apify 平台账单。
- **结论**：官方 MCP 可用、活跃、文档完整；我们不需要自己写 Actor 调度胶水，直接以 `?tools=` 白名单接入「小红书/抖音/点评」相关 Actor 即可。

### 2.2 国内平台相关 MCP server（实际检索到的）

| 平台 | 仓库 / 服务 | 活跃度 | 说明 |
|---|---|---|---|
| 小红书 | https://github.com/xpzouying/xiaohongshu-mcp | 非常活跃，~16k stars，最新 v2.5.5（2026-09-22），Go+Playwright(go-rod) | 自建浏览器登录态，支持搜索/笔记/评论/发布；主流开源方案。 |
| 小红书 | https://github.com/J-ade-g/xiaohongshu-mcp | 中等，Python+Playwright | 让 Claude Code 在浏览器里浏览小红书内容，轻量。 |
| 小红书 | https://github.com/DevinChen2014/xiaohongshu-xhs-rednote-mcp（托管在 SocialDataX） | 2026-09-29 还在发版（v0.1.16） | 托管 streamable-http 端点 `https://mcp.socialdatax.com/xhs/mcp`，API key 鉴权，付费云服务。 |
| 抖音 | SocialDataX 托管的 Douyin MCP（DevinChen2014 系列） | 2026-08 仍在更新 | Bearer token 托管端点，免本地浏览器。 |
| 抖音 | Edisonzszs/douyin-end-to-end-mcp | 2026-09-09 更新 | 本地存 cookie 到 `~/.douyin/cookies.json`，支持发布/评论/分析。 |
| 知乎 | pypi 包 `huimei`（多平台发布 MCP，含 zhihu/toutiao/baijiahao/wechat MP） | 2026-05 | 偏「发文自动化」，采集能力弱。 |
| 知乎/小红书 | https://github.com/fateyetian/SocialRadar | v0.1 已发布，v0.2 计划中 | CLI + MCP，目前只做 xhs+zhihu 搜索聚合。 |
| B 站 | 222wcnm/bilibili-comments-mcp | 2026-08-31 | 需 `BILIBILI_COOKIE`，批量抓视频评论（含嵌套回复）。 |
| 微博 | SocialDataX 托管 Weibo MCP（DevinChen2014 系列） | 2026-08-30 | 托管付费，Bearer token。 |
| 微信（个人号） | https://github.com/BiboyQG/WeChat-MCP（pypi: `wechat-mcp-server` 0.2.0） | 2026-09-28 发版 | 基于个人微信桌面 hook，灰色地带，封号风险高。 |
| 微信（公众号） | tc6-01/wechat-mp-mcp（Go，Docker） | 2026-09-28 | 官方 access_token 路线，草稿/发布/素材，合规但只能管自己的公众号。 |
| 微信（生态） | Wechaty（https://wechaty.js.org/） | 长期项目 | RPA 聊天机器人框架，非纯采集，puppet 多为付费/灰产。 |

> 备注：微博「采集」类成熟 MCP 很少，大多是托管付费 API；微信侧没有合规的「公众号文章批量采集」MCP，需要走微信公众平台官方 API 或第三方数据站。

---

## 三、本地 Skill / 既有脚本评估（实际查找结果）

### 3.1 「xiaohongshu-cli」「xiaohongshu-mcp」本地查找

按要求在以下位置实际检索：
- 工作区 `/Users/deuce/Doubao/chats/2026-09-28/new-chat/`（含子目录到 depth 7）
- Skill 根：`~/.doubao/agent_mode/workspace/.skills/`、`~/.doubao/agent_mode/workspace/.user_skills/`、`~/Doubao/skills/`
- npm 全局 `~/.npm-global/bin` 与 `npm ls -g`
- pip `pip3 list`

**结论：本机没有安装任何名为 `xiaohongshu-cli` 或 `xiaohongshu-mcp` 的可执行包/全局命令/独立 skill 目录。** pip 里仅有一个无关包 `xhshow 0.2.0`。

实际命中的、与小红书相关的本地资产有三个，逐一评估：

#### (a) browser-use-automation-mac skill 里的小红书操作手册（不是独立 CLI/MCP）
- **路径**：`/Users/deuce/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.skills/browser-use-automation-mac/references/xiaohongshu/`
- 文件：`README.md`、`collect.md`、`interact.md`、`publish.md`、`travel.md`
- **能做什么**：给浏览器自动化 agent 的 workflow 说明书——搜索笔记、筛选广告、抽取作者结论/适用人群/局限、跨笔记交叉验证；明确「不发明互动数/价格/链接」，登录卡点走 `interaction.request_action`。
- **是否活跃**：文件 mtime 2025-09-28（与本会话工作区同步），是 skill 自带参考文档，不随项目迭代。
- **是否合规**：只读浏览 + 自己账号点赞/收藏/发布；明确要求记录直链、作者、发布时间、retrieval date，禁止编造——合规姿态最接近我们 raw→stage 契约。
- **与 Apify 方案取舍**：这是「人在环里的浏览器操作手册」，适合低频、深度、单店考据；Apify Actor 适合批量、无人值守、结构化导出。两者互补，不是替代关系。

#### (b) 父会话目录里的 `_xhs_*.py` CDP 登录辅助脚本（一次性探针，不是 CLI/MCP）
- **路径**：`/Users/deuce/Doubao/chats/2026-09-28/new-chat/_xhs_open_qr.py`、`_xhs_refresh_qr.py`、`_xhs_save_qr.py`、`_xhs_poll.py`、`_xhs_inspect_login.py`、`_xhs_probe.py`、`_xhs_wait_login.py`
- **能做什么**：通过 CDP（`127.0.0.1:9226`）驱动一个隔离 Chrome，打开 xiaohongshu 登录页、截取 `img.qrcode-img`、轮询登录态、探测 `/api/sns/web/v2/user/me` 存活。全部是登录态建立工具，不做搜索/抓取。
- **是否活跃**：文件 mtime 与本会话一致，是临时脚手架，未版本化进仓库。
- **是否合规**：只做自己账号的登录，不抓他人数据；但仍走账号 cookie，存在封号风险。
- **与 Apify 方案取舍**：Apify 的小红书 Actor 自带住宅代理 + 托管 cookie，不需要我们自己维护 CDP 登录；这套脚本只在「Apify Actor 不可用、必须用我们自己账号跑低频采集」时才留作 fallback。

#### (c) 仓库内 `cloud/xhs_qr_login.py`（项目自己的隔离登录器）
- **路径**：`/Users/deuce/Doubao/chats/2026-09-28/new-chat/china-travel-food/cloud/xhs_qr_login.py`
- **能做什么**：服务端 headless Chromium，每账号一个独立 context，二维码 40s 自动刷新，成功后导出 `web_session+id_token` cookie JSON。
- **是否活跃**：正在用，注释里有「曾把登录页遮罩文字当二维码」的踩坑记录。
- **是否合规**：自账号、隔离会话、cookie 落盘受控。
- **与 Apify 方案取舍**：这是仓库「自建账号池」路线的核心资产；Apify 是「租别人账号池 + 代理」路线。二选一即可，不要同时维护两套。

### 3.2 仓库内其他多平台采集 / 去软广相关既有资产

| 路径 | 作用 |
|---|---|
| `research/atlas/COLLECTION_CONTRACT.md` | 采集契约：raw→stage→`atlas_write.py`，铁律「宁空不假」「press/通稿不进口味」「去软广」，字段含 `social_xhs / social_douyin / social_weibo`。 |
| `research/design/social-listening-chef-feed-v3.md` | Social Listening v3 设计：源矩阵 T1 官方→T2 权威→T3 KOL→T4 地图；词根配置覆盖搬迁/闭店/新店/换主厨/飞行/联名/快闪/荣誉。 |
| `research/social/batch5_events_seed.py`、`research/social/batch6/build_seeds.py`、`track_events.py`、`apply_semdesc.py`、`apply_semdesc2.py` | 种子账号→事件追踪→语义描述标注的实际管线脚本。 |
| `research/social/negative_elimination_list.md` | 负向剔除清单（即「去软广」的现状规则集）。 |
| `cloud/xhs_qr_login.py` | 见 3.1(c)。 |

> 仓库内**没有**现成的「Apify 调度脚本」「跨平台 MCP 客户端」「ABSA 情感分类器」「fake review 分类器」——这些都是本次调研后待建的空白位。

---

## 附：四方向各一篇代表作（交付要求）

1. **ABSA 餐饮**：*Beyond the Star Rating: A Scalable Framework for ABSA Using LLMs and Text Classification* — https://arxiv.org/html/2602.21082
2. **虚假点评检测**：*Recent state-of-the-art of fake review detection: a comprehensive review*（Cambridge, 2024）— https://www.cambridge.org/core/services/aop-cambridge-core/content/view/F02E8339C43A62BA63EBD54A1608F785/S0269888924000067a.pdf/recent-state-of-the-art-of-fake-review-detection-a-comprehensive-review.pdf
3. **跨平台采集（技术）**：NanmiCoder/MediaCrawler（开源事实标准；学术侧同主题同行评审论文稀缺）— 见 https://socai.io/blog/xiaohongshu-automation-tools 的横向对比表
4. **合规（PIPL/GDPR）**：*On the Tort Liability of Scraping Publicly Available Personal Data*，《法学家》2026(3) — https://faxuejia.ruc.edu.cn/EN/Y2026/V0/I3/77

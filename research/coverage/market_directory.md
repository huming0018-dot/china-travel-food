# 跨平台采集通道总目录 (Market Directory)

> 调研日期：2026-10-01 (HKT)
> 范围：Apify Store、其他数据市场（Bright Data / Oxylabs / DataForSEO / ScrapeHero / RealDataAPI / SandBase / TikHub / JustOneAPI）、GitHub 开源仓库与 MCP server
> 约束：仅编目，未注册、未购买、未跑 actor、未写库。价格/用户数均来自实时页面快照，页面未披露处标注"未披露"。
> 用途：为 china-travel-food 项目评估各平台数据获取的成熟度、成本与合规风险。

---

## 0. 总览成熟度矩阵

| 平台 | Apify Store | 独立数据市场 API | GitHub 开源 | 成熟合规通道评级 |
|---|---|---|---|---|
| 小红书 RedNote | ✅ 多 actor，头部活跃 | ✅ RealDataAPI / SandBase / TikHub / JustOneAPI | ✅ MediaCrawler / XHS-Downloader | **成熟** |
| 抖音 Douyin | ✅ 多 actor，含星图报价 | ✅ SandBase / TikHub / Bright Data(TikTok) | ✅ MediaCrawler / Douyin_TikTok_Download_API | **成熟** |
| 微博 Weibo | ✅ 多 actor，热搜/评论免登录 | ✅ Bright Data(官方产品页) / SandBase / TikHub | ✅ MediaCrawler / WeiboSpider | **成熟** |
| 知乎 Zhihu | ✅ 多 actor，问答/文章 | ✅ TikHub / JustOneAPI / reach-mcp | ✅ MediaCrawler + 多个 MCP | **成熟** |
| B站 Bilibili | ✅ 多 actor，弹幕/字幕 | ✅ TikHub / reach-mcp | ✅ MediaCrawler / bilibili-mcp | **成熟** |
| 快手 Kuaishou | ✅ 少数 actor，维护参差 | ✅ TikHub / SandBase | ✅ MediaCrawler | **中等** |
| 微信公众号 | ✅ 搜狗中转 + 原生 | ✅ TikHub / JustOneAPI | ⚠️ 仅浏览器插件/ hook 方案 | **中等** |
| 豆瓣 Douban | ✅ 头部 actor（zhorex） | ⚠️ reach-mcp / 无专业 API | ⚠️ MediaCrawler 未覆盖 | **中等** |
| 大众点评/美团 | ❌ 无成熟 Apify actor | ✅ 美团官方 POI 开放平台 + RealDataAPI | ❌ 开源多已失效/高风险 | **稀缺（需走官方/商用 API）** |
| 视频号 | ❌ 无 Apify actor | ⚠️ TikHub 提及 WeChat 但未细分 | ⚠️ 仅安卓 hook / 本地下载器 | **稀缺** |
| Google Maps | ✅ 官方+第三方，极成熟 | ✅ DataForSEO / 官方 GMP API | ✅ 大量开源 | **极成熟** |
| TripAdvisor | ✅ 10+ actor，便宜 | ⚠️ 无专业数据集 | ✅ 通用爬虫 | **成熟** |
| Instagram | ✅ 官方 apify/instagram-api-scraper | ✅ Bright Data / TikHub | ✅ 大量开源 | **极成熟** |
| YouTube | ✅ streamers/youtube-scraper (4.8★) | ✅ Bright Data / TikHub / yt-dlp | ✅ yt-dlp 等 | **极成熟** |
| Reddit | ✅ 多 actor，Pushshift 替代 | ✅ Bright Data / TikHub | ✅ pushshift 生态 | **成熟** |
| OpenRice (HK) | ⚠️ 2 个 actor，其一已弃用 | ❌ 无专业 API | ❌ 无活跃仓库 | **稀缺** |

---

## 1. Apify Store 分平台明细

### 1.1 小红书 RedNote / 小红书

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `zen-studio/rednote-search-scraper` | https://apify.com/zen-studio/rednote-search-scraper | 笔记正文、作者(userid/red_id/nickname/verified)、点赞/评论/收藏/分享数、图片图集、视频多码率流 URL、发布时间；24 字段/笔记 | **$4.99–5.99 / 1,000 results**（PPE search-result=$0.00599） | 免 cookie、免登录；Apify 托管代理 | **6.6K 总用户，818 月活，9 分钟前更新**，评分 4.0，6 bookmarks |
| `viralanalyzer/rednote-search-scraper-pro` | https://apify.com/viralanalyzer/rednote-search-scraper-pro | 探索 feed、关键词过滤 | **$2.00 / 1K**（页面标题标注） | 未披露 | 未披露 |
| `atomus/xiaohongshu-scraper` | https://apify.com/atomus/xiaohongshu-scraper | 笔记、用户、评论；PGY 蒲公英达人报价卡 | 未披露具体单价（按结果） | **NO COOKIES** 宣传 | 未披露 |
| `sian.agency/xiaohongshu-rednote-scraper` | https://apify.com/sian.agency/xiaohongshu-rednote-scraper | 笔记详情、用户主页、全量笔记目录、评论、笔记+用户搜索 | 未披露 | 免 API key | 未披露 |
| `pro100chok/rednote-xiaohongshu-scraper` | https://apify.com/pro100chok/rednote-xiaohongshu-scraper | 分类 feed、笔记详情(图片+视频 URL+字幕轨道+语音转写+话题+互动)、创作者、评论串、关键词建议；8 种模式中 6 种免登录 | 未披露 | 6/8 模式免 cookie | 2026-08 更新 |
| `justoneapi/xiaohongshu-rednote-data-api` | https://apify.com/justoneapi/xiaohongshu-rednote-data-api | 帖子、主页、评论、回复、互动、趋势、关键词、话题、分享链接跳转；支持 MCP | 需自带 JustOneAPI token | 免 RedNote cookie | 2026-06 上架 |
| `crawloop/xiaohongshu-scraper` | https://apify.com/crawloop/xiaohongshu-scraper | 笔记、主页、搜索 | 未披露 | 未披露 | 2026-09-28 更新 |
| `technicaldost/xiaohongshu-rednote-scraper` | https://apify.com/technicaldost/xiaohongshu-rednote-scraper | 标题、作者、互动、图片、视频、评论 | 未披露 | 免官方 API | **9 总用户，4 月活，17 天前更新** |
| `memo23/xiaohongshu-rednote-scraper` | https://apify.com/memo23/xiaohongshu-rednote-scraper | 笔记详情、用户、分类发现、商城商品价格、评论、关键词搜索；8 模式 | 未披露 | 笔记详情/主页/发现/商品免登录 | 2026-07 更新 |
| `khadinakbar/xiaohongshu-search-scraper` | https://apify.com/khadinakbar/xiaohongshu-search-scraper | 笔记卡片（标题、作者、图、点赞、URL） | **$6.00 / 1,000 搜索结果** | **需授权 session/cookie** | 2026-07 更新 |
| `scrapesage/rednote-xiaohongshu-scraper` | https://apify.com/scrapesage/rednote-xiaohongshu-scraper | 趋势笔记、创作者 | 未披露 | 宣传"采集匿名访客可见公开数据，不登录、不绕访问控制" | 2026-07 更新 |

**合规说明**：多数 actor 声明"采集匿名访客可见公开数据，不登录、不绕访问控制"。`khadinakbar` 需自备 session，合规风险较高。

---

### 1.2 抖音 Douyin

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `atomus/douyin-scraper` | https://apify.com/atomus/douyin-scraper | 视频搜索/用户作品/视频详情/主页/评论/弹幕/热榜；**星图达人搜索、星图分析、星图报价卡(priceTiers 人民币)**；每条视频带 1080p 无水印 downloadUrl | 按模式：搜索 $0.010/视频(Gold $0.005)、用户作品 $0.003、视频详情 $0.004、主页 $0.004、评论/弹幕/热榜 $0.002、星图搜索 $0.01、星图分析 $0.04、星图报价 $0.08 | **免 cookie、免登录**；失败查询免费 | **120 总用户，71 月活，3 小时前更新** |
| `scrapers_lat/douyin-scraper` | https://apify.com/scrapers_lat/douyin-scraper/api | 视频描述、作者主页(昵称/Douyin ID/bio)、赞/评/转/藏、音乐、话题、封面、无水印下载 URL | 未披露（from …） | 未披露 | 2026-07 更新 |
| `bovi/douyin-scraper` | https://apify.com/bovi/douyin-scraper | 20+ 字段/视频（play/digg/URL/封面/音乐/话题）；纯 Python a_bogus 签名(SM3+RC4) | 未披露 | 免浏览器 | 2026-06 更新 |
| `burbn/douyin-video-downloader` | https://apify.com/burbn/douyin-video-downloader | 无水印 URL、封面、元数据、作者、音乐、话题、互动数；批量 by URL/aweme ID | **$5.00 / 1,000 results** | 未披露 | 2026-08 更新 |
| `memo23/douyin-scraper` | https://apify.com/memo23/douyin-scraper/api/javascript | 视频详情、创作者、评论；统一 JSON | **$3.00 / 1,000 results**（标题宣传 "Only $3"） | 免登录、免浏览器 | 2026-07 更新 |
| `scrapesage/douyin-scraper` | https://apify.com/scrapesage/douyin-scraper/api/python | 热搜板、精确互动数(非四舍五入)、评论带省份、抖音内容分类、KOL 线索带精确粉丝 | **$2.91 / 1,000** | 免登录、免浏览器 | 2026-07 更新 |
| `zen-studio/douyin-profile-scraper` | https://apify.com/zen-studio/douyin-profile-scraper | 博主主页、粉丝、获赞、bio、公开 IP 属地；28 字段/帖 + 22 字段/作者；支持 URL/分享链接/UserSecID/数字 ID；每 run 最多 25 主页 | **$4.49 / 1,000**（起） | 未披露 | 2026-05 更新 |
| `openclawai/tiktok-douyin-bilibili-scraper` | https://apify.com/openclawai/tiktok-douyin-bilibili-scraper | TikTok/Douyin/B站 统一 schema：视频、主页、帖子、评论、点赞、直播、趋势 feed；无水印 MP4 | 未披露 | 免 API key | 2026-04 上架 |
| `sian.agency/douyin-scraper` | https://apify.com/sian.agency/douyin-scraper.md | 视频数据、用户主页、评论、回复串、关键词搜索；7 种操作 | 未披露 | 免 API key | 2026-09-30 更新 |

**亮点**：`atomus/douyin-scraper` 是唯一公开售卖**星图(Xingtu)达人报价卡**的通道，对美食探店 KOL 选号极有价值。

---

### 1.3 微博 Weibo

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `zhorex/weibo-scraper` | https://apify.com/zhorex/weibo-scraper | 9 模式：搜索帖子、热搜板(带热度/新热爆标)、热搜 delta 监控、帖子评论、帖子详情、用户帖子(需 cookie)、用户主页、黑猫投诉；支持情感分析、delta 去重、跨品牌监控包 | **$35.00 / 1,000 items**（$0.035/条）；run start 另计 | 搜索/热搜/评论/详情/主页/投诉**免 cookie**；user_posts 需自备 cookieString（有效期数天）；纯 HTTP，256MB | **11 小时前更新**，maxResults 已提至 5000/run |
| `themineworks/weibo-scraper` | https://apify.com/themineworks/weibo-scraper | 用户粉丝数、认证、bio、全文时间线(转发/评论/赞) | **$2.25 / 1,000 profiles** | **中国住宅代理**，免登录、免浏览器 | 2026-09-30 更新 |
| `haketa/weibo-scraper` | https://apify.com/haketa/weibo-scraper | 公开评论、评论者线索、实时热搜、创作者主页、互动、作者 ID、认证、粉丝、地区、主页链接 | **$3.50 / 1,000 results** | 未披露 | 2026-08 更新 |
| `khadinakbar/weibo-scraper` | https://apify.com/khadinakbar/weibo-scraper | 免凭证热搜 + cookie 支持的关键词帖子与用户时间线 | **$8.00 / 1,000 records** | 热搜免凭证；关键词/时间线需 cookie | 2026-07 更新 |

**注意**：Weibo 无面向国际开发者的官方公开 API（需中国营业执照）。`zhorex` 是功能最全的公开通道。

---

### 1.4 知乎 Zhihu

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `sian.agency/zhihu-scraper` | https://apify.com/sian.agency/zhihu-scraper | 关键词搜索、问题回答串(完整 HTML body)、文章详情、专栏文章列表；4 种操作 | **$2.00 / 1,000 搜索结果** | 免 API key | 2026-05 上架 |
| `maximedupre/zhihu` | https://apify.com/maximedupre/zhihu | 关键词/问题/文章/专栏/视频/评论/创作者页；结构化记录带源链接、作者、互动、日期 | **$1.80 / 1,000 content matches** | 未披露 | 2026-09-09 更新 |
| `blackfalcondata/zhihu-scraper` | https://apify.com/blackfalcondata/zhihu-scraper | 热门问题列表、完整问答文本、作者主页；互动指标(赞同/评论/喜欢/粉丝) | 宣传"Just $3" | **免登录** | 2026-07 更新 |
| `ethereal_wool/zhihu-question-answers-scraper` | https://apify.com/ethereal_wool/zhihu-question-answers-scraper | 问题下全部回答：完整 HTML body、纯文本摘要、作者名/handle/粉丝数、赞同、评论数、时间戳 | **$10.00 / 1,000 results** | 未披露 | **Under maintenance** |

---

### 1.5 B站 Bilibili

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `vulnv/bilibili-scraper` | https://apify.com/vulnv/bilibili-scraper/api | 关键词视频搜索、视频详情、UP主主页、UP主作品、评论；播放/点赞/投币/弹幕/评论 | **from $5.…/1k**（截断） | **免登录、免 cookie、免代理** | 2026-07 更新 |
| `atomus/bilibili-scraper` | https://apify.com/atomus/bilibili-scraper/input-schema | 视频搜索、详情、评论、UP主主页、**弹幕**、**原生字幕转写**、趋势；失败查询免费 | 未披露具体（按结果） | **NO COOKIES、免登录** | 2026-08 更新 |
| `automation-lab/bilibili-scraper` | https://apify.com/automation-lab/bilibili-scraper | 视频、创作者、搜索结果、互动指标、可选评论 | **$0.04 / 1,000 results**（异常低价，评分 0.0） | 未披露 | 2026-06 上架 |
| `openclawai/tiktok-douyin-bilibili-scraper` | https://apify.com/openclawai/tiktok-douyin-bilibili-scraper | 三平台统一 schema | 未披露 | 免 API key | 2026-04 |

---

### 1.6 快手 Kuaishou

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `stackrelay/kuaishou-scraper` | https://apify.com/stackrelay/kuaishou-scraper | 视频元数据 + 评论(按 URL/photo ID)；按事件分别计费 | **$6.00 / 1,000 视频详情**；评论单独计价 | 未披露 | 2026-06 |
| `ethereal_wool/kuaishou-scraper` | https://apify.com/ethereal_wool/kuaishou-scraper/api | 点赞、观看、作者；按关键词/URL/ID | **$10.00 / 1,000 results** | 未披露 | 2026-06 |
| `hgservices/kuaishou-video-scraper` | https://apify.com/hgservices/kuaishou-video-scraper | 无水印 MP4 下载 + 元数据(caption/作者/赞/观看/评论) | **$2.00 / 1,000 results** | 未披露 | 2026-07 |
| `bovi/kwai-kuaishou-scraper` | https://apify.com/bovi/kwai-kuaishou-scraper/api | 关键词搜索短视频：观看/赞/转/评/时长/caption/创作者 | **from $0.01/video** | **CN 住宅代理，免登录** | **Under maintenance** |

**评级**：快手 actor 数量少、维护参差（一个 under maintenance），成熟度中等。

---

### 1.7 微信公众号

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `haketa/wechat-official-account-scraper` | https://apify.com/haketa/wechat-official-account-scraper | 公众号搜索、主页、公开索引文章历史；标题/日期/全文/HTML/Markdown/图/链 | **$9.00 / 1,000** | 未披露 | 2026-07 |
| `sian.agency/wechat-official-account-data-scraper` | https://apify.com/sian.agency/wechat-official-account-data-scraper | 文章内容/详情、账号主页/注册信息、今日+历史文章、评论、互动；文章/热榜/小程序/指数/账号搜索；**wxid-native** | **$20.00 / 1,000 文章搜索结果** | 免登录 | **Rising star，评分 5.0**，2026-09-25 更新 |
| `parseforge/sogou-wechat-search-articles-scraper` | https://apify.com/parseforge/sogou-wechat-search-articles-scraper | 通过搜狗搜索公众号文章：标题/摘要/账号名/发布日期/解析后的 mp.weixin.qq.com 链接 | **$11.88 / 1,000 results** | 走搜狗中转 | 2026-08 |
| `parseforge/weixin-sogou-search-scraper` | https://apify.com/parseforge/weixin-sogou-search-scraper/api/python | 同上（文章+账号） | **$9.56 / 1,000 results** | 走搜狗 | 2026-08 |

**注意**：公众号文章阅读数/在看数等互动字段，公开 web 端难以获取；搜狗中转只能拿摘要+链接。

---

### 1.8 豆瓣 Douban

| Actor ID | Store URL | 可取字段 | 计价 | 代理/Cookie | 活跃度 |
|---|---|---|---|---|---|
| `zhorex/douban-scraper` | https://apify.com/zhorex/douban-scraper | 5 模式：subject_reviews(长评 500-5000 字)、subject_comments(短评+星级)、subject_search(影视/书/音乐)、group_topic(小组讨论+回复, Beta)、group_search(按标题关键词搜小组) | 长评 **$0.030/条**($30/1k)、短评 **$0.005/条**($5/1k)、小组话题 $0.030、搜索 $0.005 | 纯 HTTP；**强烈建议住宅代理**(默认开启)；免登录；电影短评因 JS 渲染暂不可用 | **2 天前更新**，自称"Apify 上最常用的 Douban 采集器" |

**已知限制**：电影短评走 JS widget 采不到；小组话题大量登录墙；书籍搜索仅 ~10 条/query。

---

### 1.9 大众点评 / 美团

| 通道 | URL | 说明 | 计价 |
|---|---|---|---|
| Apify Store | — | **未找到成熟的专用 actor**。仅有一个 `apify.com/ideas/meituan-app-data-scraper-04954bfe` 的"想法"占位页，并非可运行 actor | — |
| 美团点评官方 POI 开放平台 | https://poiopen.dianping.com/instructions/doc/poi.html | 官方开放接口：POI 扫描、单/批量 POI 信息获取、POI 信息同步、变更实时通知；字段含商场美食人气榜等 | 需商务对接，页面未公开价格 |
| RealDataAPI Meituan API | https://www.realdataapi.com/meituan-api.php | 实时商户、代金券、外卖数据；**堂食评分与外卖评分分离返回**；自动轮换代理重试，仅成功请求计费；送 sandbox key | 未公开标价（注册后见） |

**结论**：点评/美团在 Apify 无成熟合规 actor；开源爬虫多数因签名(e.g. _lxl)和强反爬已失效。**应走官方 POI 开放平台或 RealDataAPI 这类商用 API**。

---

### 1.10 Google Maps

| Actor ID | Store URL | 可取字段 | 计价 | 活跃度 |
|---|---|---|---|---|
| `datascraperes/actor-google-maps` | https://apify.com/datascraperes/actor-google-maps | 商家名称、地址、电话、网站、评分、评论、类别、营业时间等 | **$1.00 / 1,000 results**（Free 档；Bronze $0.90 / Silver $0.80 / Gold+ $0.75） | 2026-09 更新 |
| `zen-studio/google-maps-scraper` | https://apify.com/zen-studio/google-maps-scraper | **40+ 字段**：评分、电话、网站、营业时间、热门时段、 amenities、照片、评论；**突破 Google 250 条上限**，每分钟数百家 | **$4.99 / 1,000 places** | 2026-05 |
| `crustapi/google-maps-scraper` | https://apify.com/crustapi/google-maps-scraper | 名称/地址/电话/网站/评分/评论/类别/营业时间；纯 HTTP 无浏览器 | **$3.30 / 1,000 results** | 2026-04 |
| `searchapi/google-maps-scraper` | https://apify.com/searchapi/google-maps-scraper/pricing | 搜索结果 | **$1.99 / 1,000**（各档同价）+ actor start $0.001 | 2026-07 |
| `agents/google-maps-search` | https://apify.com/agents/google-maps-search | 商家列表/线索；**Apify 官方 MCP server**(mcp.apify.com) | 未披露 | 2026-08 |
| `lentic_clockss/google-maps-scraper` | https://apify.com/lentic_clockss/google-maps-scraper | 名称/电话/网站/评分/地址；评论免费附带 | $0.005/actor start，按 business 计费 | 2026-04 |

**合规通道**：极成熟。另可走官方 Google My Business API / Google Places API（官方，需信用卡）。

---

### 1.11 TripAdvisor

| Actor ID | Store URL | 可取字段 | 计价 | 活跃度 |
|---|---|---|---|---|
| `themineworks/tripadvisor-reviews` | https://apify.com/themineworks/tripadvisor-reviews | **21 字段**：评论/评分/评论者主页/商家回复；酒店/餐厅/景点；支持 **MCP server**(Claude/AI agent) | **$0.30 / 1,000 reviews** | 2026-09-17 |
| `xtracto/tripadvisor-reviews-scraper` | https://apify.com/xtracto/tripadvisor-reviews-scraper | 标题/全文/评分/旅行日期/旅行类型/商家回复 | **$0.40 / 1,000 results** | 2026-09-25 |
| `delicious_zebu/tripadvisor-review-collector` | https://apify.com/delicious_zebu/tripadvisor-review-collector | **全 5 大类**(酒店/餐厅/景点/活动/游轮)；评分/旅行者类型/语言/日期过滤；API 无浏览器 | **$0.40 / 1,000 results** | 2026-09-13 |
| `trakk/tripadvisor-reviews-places-scraper` | https://apify.com/trakk/tripadvisor-reviews-places-scraper | 两种模式：批量搜索 / 完整列表提取；评分/评论/商家回复/联系/地址/照片/排名 | **$0.50 / 1,000 results** | 2026-08 |
| `gopalakrishnan/tripadvisor-reviews-scraper` | https://apify.com/gopalakrishnan/tripadvisor-reviews-scraper | 星级/子评分(清洁/服务/性价比)/旅行类型/评论者/商家回复；语言过滤 | **$1.00 / 1,000 reviews** | 2026-06 |
| `reviewly/tripadvisor-reviews-scraper` | https://apify.com/reviewly/tripadvisor-reviews-scraper | 餐厅/酒店评论 | **$1.00 / 1,000 records**；评分 3.0 | 2 个月前更新 |
| `one_house/tripadvisor-reviews-scraper` | https://apify.com/one_house/tripadvisor-reviews-scraper | 酒店/餐厅/景点评论、评分、商家回复 | **$0.75 / 1,000 results**；2 总用户/1 月活 | 2 个月前更新 |

**合规通道**：成熟，评论类 actor 单价低至 $0.30/1k。

---

### 1.12 Instagram

| Actor ID | Store URL | 计价 | 备注 |
|---|---|---|---|
| `apify/instagram-api-scraper` | https://apify.com/apify/instagram-api-scraper | **from $1.40 / 1,000 results** | **Apify 官方**，免登录，评分 4.x；支持帖子/主页/地点/话题/照片下载 |
| `apify/instagram-scraper` | https://apify.com/store?search=social | Free $2.70 / 1k，Business $1.50 / 1k | Apify 官方旗舰 |
| `apify/instagram-post-scraper` | 官方 | ~$1.00 / 1k (Business) | 帖子/reels/最近评论/赞助标记 |
| `prodiger/instagram-scraper` | https://apify.com/prodiger/instagram-scraper | PPE: post/profile/hashtag 各 $1.30/1k | 按事件 |
| `pro100chok/instagram-scraper-all-in-one` | https://apify.com/pro100chok/instagram-scraper-all-in-one | posts $3/1k、profiles $4/1k、followers/comments $1/1k (Free)；Gold 低至 $0.90/$0.40 | 全功能 |
| `supreme_coder/instagram-post-scraper` | https://apify.com/supreme_coder/instagram-post-scraper/api/cli | **$0.30 / 1,000 posts** | 免 cookie |

---

### 1.13 YouTube

| Actor ID | Store URL | 计价 | 备注 |
|---|---|---|---|
| `streamers/youtube-scraper` | https://apify.com/store?q=perplexity | 未披露（按结果） | **评分 4.8（196 条评价）**，频道名/赞/观看/订阅数，无配额限制的替代 API |
| `maximedupre/youtube-channel-search-scraper` | 同 store | 未披露 | 关键词/URL 找频道，导出频道身份+公开指标 |
| `epctex/youtube-video-downloader` | 同 store | 未披露 | 按质量下载视频 |

另：`yt-dlp`(GitHub) 是事实标准开源方案，免费。

---

### 1.14 Reddit

| Actor ID | Store URL | 计价 | 备注 |
|---|---|---|---|
| `trudax/reddit-scraper-lite` | https://apify.com/store?search=voyager%2Fbooking-scraper | 按结果 | 帖子/评论/社区/用户，免登录 |
| `prince.sh/reddit-search-scraper` | https://apify.com/prince.sh/reddit-search-scraper/pricing | post $0.0015、comment $0.0005、start $0.00005 | 平台使用费免费 |
| `scrapers-hub/reddit-scraper-enterprise` | https://apify.com/scrapers-hub/reddit-scraper-enterprise/api/python | **$0.99 / 1,000** | 最便宜档宣传 |
| `practicaltools/apify-reddit-api` | https://apify.com/practicaltools/apify-reddit-api | **$2.00 / 1,000** | 批量历史数据/情感分析 |
| `scrapesage/reddit-scraper` | https://apify.com/scrapesage/reddit-scraper/api/javascript | **$7.00 / 1,000** | 40+ 字段，免登录 |
| `logiover/reddit-historical-archive-scraper` | 同 store | 未披露 | **Pushshift 替代**，历史帖子/评论全文搜索 |
| `unseenuser/reddit-scraper` | https://apify.com/unseenuser/reddit-scraper | 未披露 | 帖子/评论/搜索 + AI 分析 |

---

### 1.15 OpenRice (香港)

| Actor ID | Store URL | 字段 | 计价 | 活跃度 |
|---|---|---|---|---|
| `claude_code_reviewer/openrice-scraper-en` | https://apify.com/claude_code_reviewer/openrice-scraper-en | 餐厅名/地区/菜系/评分/评论数/价格区间/地址/电话 | 未披露具体（页面未展示价格表） | **10 总用户，3 月活，21 天前更新**，1 bookmark |
| `precious_nucleus/openrice-scraper` | https://apify.com/precious_nucleus/openrice-scraper | 餐厅详情、评论、菜单照片 | **$150.00 / 1,000 restaurants** | **Deprecated（已弃用）** |

**结论**：OpenRice 通道极稀缺，仅一个低活跃 actor 在维护，且无评论正文深度提取（仅元数据）。

---

## 2. 其他数据市场

### 2.1 Bright Data (brightdata.com)

| 产品 | URL | 覆盖平台 | 说明 | 计价 |
|---|---|---|---|---|
| Weibo Scraper | https://brightdata.com/products/web-scraper/weibo | **微博**（官方产品页） | 主页、URL、推文、转发、会话串、粉丝/关注、位置、图片 | 企业级，未公开标价（按结果/订阅） |
| TikTok API Suite | https://docs.brightdata.com/api-reference/scrapers/social-media-apis/tiktok.md | TikTok（国际版） | Profile/Post/Comment 等多套 API | 企业级 |
| Social Media Scraper APIs | https://brightdata.com/products/web-scraper | Instagram / TikTok / LinkedIn / YouTube / X / Facebook | 公开帖子/主页/粉丝/互动/趋势话题 | 企业级 |
| Web Unlocker / Web Scraper | 同上 | 任意网站（含 Douyin/XHS/Douban，通过通用解锁） | JS 渲染、代理轮换、CAPTCHA 绕过 | 从 $49/mo 量级 |

**合规定位**：Bright Data 是企业级合规爬虫基础设施，**有公开的 Weibo 专用产品页**，但 Douyin/XHS/Douban 无专用 dataset，需走通用 Web Unlocker。

### 2.2 Oxylabs (oxylabs.io)

| 产品 | URL | 说明 | 计价 |
|---|---|---|---|
| Web Scraper API | https://oxylabs.io/products/scraper-api/web | 任意网站 raw HTML 或结构化 JSON，JS 渲染；可用 XPath/CSS 自定义解析；支持 AI agent 接入 | **$49/mo（98K results 起）**，2K 免费试用 |
| China Residential Proxy | https://www.saasultra.com/best-china-provider/ (第三方评测) | 175M+ 全球住宅 IP，含中国电信/联通/移动家庭 IP，城市级定向；适合中国社媒移动端平台 | 企业级，未公开 |

**注意**：Oxylabs 不提供中国社媒专用数据集，强项是**中国住宅代理池**+通用解锁。

### 2.3 DataForSEO (dataforseo.com)

| 产品 | URL | 覆盖 | 计价 |
|---|---|---|---|
| SERP API (Google Maps) | https://dataforseo.com/solutions/local-seo | Google Maps / local pack | **from $0.0006 / SERP** |
| Business Data API | 同上 | 商家列表 + 评论 | **from $0.0003 / listing** |
| Google Reviews API | https://chat4data.ai/ja-JP/blog/google-review-scraper (第三方评测) | Google 评论 | 标准队列 **$75 / 1M 评论**（~45 分钟）；优先队列 $150 / 1M（~1 分钟）；一次性充值 $50 起 |
| Google Hotels API | https://dataforseo.com/pricing/business-data/google-hotels-api | 酒店实体 | $0.0008–0.0016 / hotel |

**注意**：DataForSEO **不覆盖任何中国平台**（无 Weibo/Douyin/XHS/Dianping），纯 Google/SEO 场景。

### 2.4 ScrapeHero (scrapehero.com)

| 产品 | URL | 说明 |
|---|---|---|
| ScrapeHero Cloud | https://oxylabs.io/blog/best-web-scraping-tools (第三方对比) | 预置爬虫覆盖 Amazon/Walmart/Airbnb 等；**无中国社媒/点评专用爬虫**；起价 $5/月 |
| 托管数据采集 | 官网 | 可定制，但报价制，不适合自助 |

### 2.5 其他专精中国社媒的 API 服务商

| 服务商 | URL | 覆盖平台 | 规模 | 计价 |
|---|---|---|---|---|
| **RealDataAPI** | https://www.realdataapi.com/meituan-api.php ; /xiaohongshu-api.php | **美团（堂食/外卖评分分离）、小红书** | 专用 | 注册送 sandbox key + 试用额度，正式价格未公开 |
| **SandBase** | https://blog.sandbase.ai/social-media-data-apis-ai-agents-2026/ | TikTok(161 ops)、微博(64 ops)、小红书(36 ops) | AI agent 向 | **$0–0.25/call**（按操作） |
| **TikHub** | https://api.tikhub.io/ | 抖音 Web(76)+App(45)+搜索(20)+榜单(31)、小红书 Web(26)、B站、快手、皮皮虾、微博、微信、Instagram、YouTube、Twitter、Threads、Reddit、知乎、Lemon8、临时邮箱 | 超大全栈 | 未公开标价（Swagger 文档可见） |
| **JustOneAPI** | https://docs.justoneapi.com/openapi/social-media/cross-platform-search-v1-en.json | 跨平台搜索：微博/微信/知乎/抖音/小红书/B站/快手；也打包成 Apify actor `justoneapi/xiaohongshu-rednote-data-api` | 统一搜索 | 按调用，未公开 |

---

## 3. GitHub 开源仓库 & MCP Server

### 3.1 综合多平台采集

| Repo | URL | Stars | 语言 | 能做什么 | 合规风险 |
|---|---|---|---|---|---|
| **NanmiCoder/MediaCrawler** | https://github.com/NanmiCoder/MediaCrawler | **~63.8K**（2026-08 第三方统计；8 月仍活跃 issue 讨论） | Python + Playwright | **7 平台**：小红书/抖音/快手/B站/微博/贴吧/知乎；关键词搜索、指定帖子 ID、二级评论、创作者主页、登录态缓存、IP 代理池、词云；浏览器自动化而非逆向 JS | **非商业许可**（作者明确禁止商用）；需扫码登录；Pro 版收费 |
| **Evil0ctal/Douyin_TikTok_Download_API** | https://github.com/Evil0ctal/Douyin_TikTok_Download_API | **~16.4K**（2026-07） | Python | 自托管 TikTok/抖音 API：异步 REST + **MCP server** + CLI + Web 控制台；帖子/主页/评论/合集；无水印下载；Docker 一键部署；身份池自愈 + PostgreSQL 归档 | 自托管，需自备 cookie；个人研究用 |
| **JoeanAmier/TikTokDownloader** | https://github.com/JoeanAmier/TikTokDownloader | **~16.4K**（2026-07，GPL-3.0） | Python | 抖音/TikTok 作品下载+数据采集 | GPL-3.0；个人工具 |
| **JoeanAmier/XHS-Downloader** | https://github.com/JoeanAmier/XHS-Downloader | **~12.5K**（2026-08-22 仍有 push） | Python | 小红书笔记/图片/视频批量下载 | GPL-3.0；v2.7 (2026-02) |
| **xisuo67/XHS-Spider** | —（第三方对比页 ~1.4K stars） | ~1.4K | Python | 小红书数据采集、图片/视频批量下载 | 个人工具 |
| **CharesFang/WeiboSpider** | https://github.com/CharesFang/WeiboSpider | 历史高星（具体数未在本次抓取中确认） | Python/Scrapy | 基于微博 M 站的轻量高并发爬虫：用户博文、微博内容 | 老牌项目，维护状态需自行核对 |

### 3.2 MCP Server（AI agent 可直接调用）

| MCP | URL / 来源 | 覆盖平台 | 说明 |
|---|---|---|---|
| **reach-mcp** | https://pypi.org/project/reach-mcp/0.7.2/ | threads/tiktok/xiaohongshu/bilibili/youtube/pinterest/bluesky/linkedin/weibo/zhihu/douban/toutiao + github/HN/V2EX/RSS/arxiv | PyPI 包，统一 16+ web 平台接入 |
| **media-crawler-mcp-service** | https://glama.ai/mcp/servers/mcp-service/media-crawler-mcp-service | B站（搜索/视频/创作者/时间范围），基于 MediaCrawler | QR 登录持久化 |
| **zhihu-mcp-server** | https://himcp.ai/server/zhihu-mcp-server-yvn | 知乎 | Puppeteer + QR 登录，抓取热榜/网页转 Markdown |
| **chenmingkong bilibili API MCP** | https://lobehub.com/mcp (搜索 bilibili) | B站 | 通用搜索/用户搜索/精准搜索/弹幕获取 |
| **TikHub MCP / skill** | https://lobehub.com/skills/liangdabiao-tikhub_api_skill-tikhub-api-helper | 全栈（见 2.5） | 需 TikHub token |

### 3.3 合规风险备注

- **MediaCrawler**：非商业 license，作者已推出付费 Pro 版（断点续爬 + AI Agent Skill）；商用需联系授权。
- 未在本次检索中发现任何上述仓库因中国平台律师函而下架的公开报道（但开源仓库随时可能被 DMCA/平台投诉删除，使用前应自行核对仓库当前状态）。
- **大众点评/美团**：GitHub 上的老爬虫（如 `thu-cs-wiki` 周边 demo）多因 `_lxs`/签名升级和强验证码失效；**不建议作为生产通道**。
- **视频号**：无成熟 web 端采集方案，开源侧仅有安卓 LSPosed hook 或本地抓包下载器，合规风险高。

---

## 4. 高价值发现

1. **`atomus/douyin-scraper` 公开售卖抖音星图(Xingtu)达人报价卡**（`rate-card` 模式 $0.08/达人，返回 priceTiers 人民币刊例价/结算方式），这是美食探店 KOL 选号前预判预算的稀缺通道，其他平台几乎没有等价物。

2. **`zen-studio/rednote-search-scraper` 是小红书事实上的主力通道**：6.6K 总用户 / 818 月活 / 实时更新，$5.99/1k，24 字段含完整视频多码率流和 xsec_token，免 cookie——对美食笔记采集性价比最高。

3. **中国社媒"全家桶"式统一 API 已成熟**：TikHub（Swagger 可见 200+ 端点覆盖抖音/小红书/B站/快手/微博/知乎/微信）、JustOneAPI 跨平台搜索、SandBase（微博 64 + 小红书 36 ops）——不必为每个平台单独对接，可一家搞定多平台品牌监测。

4. **点评/美团是最大短板**：Apify 无成熟 actor，开源爬虫普遍失效，唯一正规路径是**美团点评官方 POI 开放平台**（poiopen.dianping.com，需商务对接）或 **RealDataAPI 商用 API**（堂食/外卖评分分离，送 sandbox）。OpenRice 也仅一个 10 用户的低活 actor 且另一已弃用。

5. **`zhorex` 一家打通微博+豆瓣+跨平台品牌监控**：weibo-scraper（$35/1k，9 模式含黑猫投诉+热搜 delta）、douban-scraper（长评 $30/1k、短评 $5/1k），并打包 "Chinese Brand Monitor"（微博+小红书+B站+豆瓣+雪球，$0.06/提及，Starter ~$110/月）——适合直接做品牌口碑监测。

6. **开源侧 MediaCrawler (~63.8K stars) 是自托管首选**：7 平台统一、Playwright 浏览器自动化（抗逆向升级），但**非商业 license**，商用须买 Pro 或联系授权。

7. **Google Maps / TripAdvisor / Instagram / YouTube / Reddit 在 Apify 极成熟且便宜**：Google Maps 低至 $0.75–1/1k，TripAdvisor 评论低至 $0.30/1k，Instagram 官方 actor $1.4/1k——这些国际点评/地图平台无需自研。

---

## 5. 检索方法说明

- Apify：通过 `general_search` 按平台名 + "scraper actor site:apify.com" 检索，再用 `web.fetch` 精读 `atomus/douyin-scraper`、`zen-studio/rednote-search-scraper`、`zhorex/weibo-scraper`、`zhorex/douban-scraper` 详情页，提取计价表/用户数/最后更新。
- 其他市场：检索 Bright Data / Oxylabs / DataForSEO / ScrapeHero 产品页及第三方对比文。
- GitHub：通过第三方星数统计站（mrkeyoor.com、repositorystats、deepwiki）交叉核对 MediaCrawler / Douyin_TikTok_Download_API / XHS-Downloader stars。
- 所有未在页面直接披露的价格/用户数均标注"未披露"，未做推算。

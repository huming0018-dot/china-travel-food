# Part 2 · Apify Marketplace 候选 Actor 清单（小红书为主，其他平台为辅）

> 调研时间：2026-10-01（Asia/Shanghai）
> 调研方式：`general_search`（`site:apify.com`）+ `web.fetch` 逐页精读 apify.com 实时页面。
> 声明：仅做调研，未注册、未购买、未跑 actor、未写库。所有价格/字段/用户数均来自 actor store 页面；页面未披露的项如实标注"页面未披露"。
> 重要前置结论：用户点名的 `clockworks/free-xiaohongshu-scraper` **在 Apify Store 不存在**（直接访问 `https://apify.com/clockworks/free-xiaohongshu-scraper` 返回 link dead；Clockworks 官方主页只做 TikTok，代表作是 `clockworks/free-tiktok-scraper`）。"xapi" 最接近的对应物是 `justoneapi/xiaohongshu-rednote-data-api`（API-first 连接器，BYO JustOneAPI token）。

---

## 1. 小红书（RedNote / XHS）Actor 详表

### 1.1 横向对比总表

| Actor ID | Store URL | 可取内容（速览） | 计价（usage，按结果） | Rental（月费） | 免费额度 | 代理 / 签名 / Cookie | 维护状态（截至 2026-10-01） |
|---|---|---|---|---|---|---|---|
| **atomus/xiaohongshu-scraper** | https://apify.com/atomus/xiaohongshu-scraper | 7 模式：关键词搜索、笔记详情（图文/视频）、评论、用户主页、商品搜索、热榜、蒲公英(PGY)达人价卡 | 按条：搜索笔记 $0.02 / 笔记详情 $0.04 / 用户主页 $0.04 / 商品 $0.04 / 评论 $0.01（每笔记最少 2 条）/ 热榜 $0.01（每次最少 2 条）/ PGY 达人 $0.05；Gold 及以上 8 折 | 页面未披露（按结果计费，无订阅） | 每模式每自然月 5 条结果，1 号重置 | **不需要 cookie / 登录 / xsec_token**；actor 自动签名并返回每条笔记的 `xsec_token`；失败查询不计费 | Rating 5.0 (1)；Total users **62**；MAU **41**；Last modified **3 天前**；Community maintained |
| **memo23/xiaohongshu-rednote-scraper** | https://apify.com/memo23/xiaohongshu-rednote-scraper | 8 操作：笔记详情、用户主页、频道 Feed（12 个品类）、商城商品/价格、用户笔记、笔记评论、搜索笔记、搜索用户 | 统一 **$5.00 / 1,000 results**（flat） | 页面未披露 | 页面未披露（有 "Try for free" 按钮，具体额度未在 README 披露） | 详情/主页/频道Feed/商城 **无需登录**；**搜索必须自备 `web_session` cookie**（小红书 code -104 硬封游客）；评论与用户笔记第 2 页起也建议带 cookie；**内置 residential 路由**，可覆盖 | Rating 5.0 (1)；Total users **34**；MAU **8**；Last modified **4 天前**；Community maintained |
| **sian.agency/xiaohongshu-rednote-scraper** | https://apify.com/sian.agency/xiaohongshu-rednote-scraper | 6 操作：noteDetail / userDetail / userNotes / noteComments / searchNote / searchUser | 启动费 $0.014/run；笔记详情 $0.05、用户主页 $0.04、用户笔记 $0.004、评论 $0.004、搜索笔记 $0.004、搜索用户 $0.003；Silver 9–88 折、Gold/Platinum/Diamond 5–75 折 | 页面未披露（按结果计费） | 免费版每次 run 最多 25 行，仅可在 Console / MCP 跑（API/定时需付费档） | "No API key, no setup, no proxies"——托管管线；支持 xsec_token passthrough；自动 backoff 重试；错误行不计费 | Rating 5.0 (1)；Total users **646**；MAU **82**；Last modified **3 小时前**（非常活跃）；支持 agentic payments（x402/Skyfire） |
| **crawloop/xiaohongshu-scraper** | https://apify.com/crawloop/xiaohongshu-scraper | 仅 2 模式：`explore`（公开推荐 Feed，约 30 条/刷）、`note_detail`（单条笔记正文+图集+视频）。**不支持关键词搜索 / 评论 / 用户主页**（这些页面未登录是空的） | **$2.99 / 1,000 items** 起 | 页面未披露 | 页面未披露 | 不需要登录、不接受 cookie；**要求 RESIDENTIAL 代理**（数据中心 IP 会撞小红书"安全限制 / 300011"墙）；自动翻 explore Feed | Rating 0.0 (0)；Total users **16**；MAU **5**；Last modified **3 天前**；Community maintained |
| **vulnv/xiaohongshu-scraper** | https://apify.com/vulnv/xiaohongshu-scraper | 5 操作：关键词搜索笔记、笔记详情、笔记评论、创作者主页、创作者已发笔记列表 | **$4.00 / 1,000 notes** 起 | 页面未披露 | 页面未披露 | "No login, cookies or proxy needed"——托管管线，无需自备中国 IP | Rating 0.0 (0)；Total users **94**；MAU **47**；Last modified **2 个月前**（更新频率一般） |
| **zen-studio/rednote-search-scraper** | https://apify.com/zen-studio/rednote-search-scraper | 关键词搜索笔记：每笔记 24 字段（作者档案、点赞/评论/收藏数、图集、可播放视频流 URL），30 秒 500 条；可按笔记类型过滤 | **$4.99 / 1,000 results** 起 | 页面未披露 | 页面未披露 | 页面未在摘要中披露 cookie/代理细节（Zen Studio 同系列 note-detail/user-profile actor 主打免 cookie） | Rating 4.0 (4)；Total users **6.6K**；MAU **818**；Last modified **9 分钟前**（**生态里最活跃、用户量最大**） |
| **justoneapi/xiaohongshu-rednote-data-api** | https://apify.com/justoneapi/xiaohongshu-rednote-data-api | 12 个 API 操作：hotSearch / searchNotes / searchUsers / userNotes / noteDetails / noteVideoDetails / noteComments / commentReplies / userProfile / keywordSuggestions / topicNotes / resolveShareUrl | "Pay per usage"——实际由 JustOneAPI（justoneapi.com）按 token 计费，Apify 页面未披露具体单价 | 页面未披露 | 页面未披露 | **BYO JustOneAPI token**（secret 输入）；不需要小红书 cookie/登录；签名/代理由 JustOneAPI 托管 | Rating 0.0 (0)；Total users **1**；MAU **0**；Last modified **4 天前**；新发 actor，尚无人用 |
| opspilot.cc/xiaohongshu-keyword-search-scraper | https://apify.com/opspilot.cc/xiaohongshu-keyword-search-scraper | 关键词搜索笔记，可按排序过滤 | **$0.10 / actor start**（按启动次数，非按结果） | 页面未披露 | 页面未披露 | 页面未披露 | Total users **31**；MAU **14**；Last modified **22 天前** |
| socialdatax/socialdatax-xhs-data-api | https://apify.com/socialdatax/socialdatax-xhs-data-api | 笔记搜索/详情、评论、评论回复、博主信息、博主笔记列表 | **from $4.99**（具体单价页面摘要未展开） | 页面未披露 | 页面未披露 | 第三方 API 封装（社媒数据助手 SocialDataX），签名/代理由其托管 | 页面未在本次精读中展开（用户量/评分未抓取） |

> 备注：上述 actor 几乎都是 **pay-per-result（按结果计费）** 模式，**没有一个在 store 首页披露月度 rental（订阅费）**；这与 Apify 生态里"成熟免费 actor（如 clockworks/free-tiktok-scraper）才有 rental 档"的惯例一致。Compute units（CU）消耗页面也未在 README 里直接给出，需进入 actor 的 Pricing tab 才看到（本次未登录 Apify，无法拉到按 CU 的明细，如实标注）。

---

### 1.2 重点 actor 字段细节（对"中国旅行美食"场景有用的部分）

#### A. `atomus/xiaohongshu-scraper` —— 免 cookie、覆盖最全（含 PGY 价卡）
- **可取**：
  - 笔记：`id / type / title / desc / url / liked_count / collected_count / comments_count / shared_count / view_count / nice_count / images[] / video_url / cover / video_duration / hashtags[] / topics[] / ip_location / timestamp / xsec_token`，嵌套 `user{user_id, red_id, nickname, avatar, verified}`
  - 评论：`id / content / like_count / sub_comment_count / ip_location / timestamp / note_id / user / at_users[]`，回复内嵌在 `sub_comments[]`（不另计费）
  - 用户主页：`user_id / red_id / nickname / desc / gender / fans / follows / interactions / notes_count / collected_count / liked_count / verified / verify_type / tags[] / location`
  - 商品：`id / title / price / origin_price / foreign_price / vendor / seller_id / sold / stock_status / link`
  - 热榜：`rank / title / hot_value / trend / item_id / url`
  - **蒲公英(PGY)达人价卡**：`fans_count / total_notes / picture_price / video_price / lower_price / current_level / content_tags[] / feature_tags[] / like_collect_count / coop_notes_30d / fans_30d_growth_rate` —— 这是市场上少有的能直接拿到 KOL 刊例价的 actor
- **计价**：见 1.1 表；Gold 档 8 折；失败查询免费
- **代理/签名**：全 7 模式均不需要 cookie/登录/`xsec_token`；actor 内置签名与代理；每条笔记返回其 `xsec_token` 给下游用
- **适配场景**：上海咖啡/餐厅关键词搜索 + 笔记正文 + 点赞收藏评论数 + 图片视频 URL + KOL 刊例价（如需做探店合作预算估算）

#### B. `sian.agency/xiaohongshu-rednote-scraper` —— 用户量最大、最活跃（646 users）
- **可取**：`noteId / noteType(normal|video|multi) / noteTitle / noteDesc / noteCoverUrl / noteImageUrls[] / likedCount / collectedCount / commentsCount / sharedCount / userId / userName / userRedId / userVerified / userAvatarUrl / postedAt / xsecToken / notePageUrl`；评论模式返回 `subCommentSample`（前 5 条回复内嵌）
- **计价**：见 1.1 表；启动费 $0.014；错误行免费；免费档每次 25 行
- **代理/签名**：托管管线，"No API key, no setup, no proxies"；xsec_token passthrough
- **适配场景**：中文/英文/混合关键词搜索 → 笔记正文 + 互动数 + 作者信息，做餐饮关键词舆情基线

#### C. `zen-studio/rednote-search-scraper` —— 量最大、最活跃（6.6K users, MAU 818）
- **可取**：关键词搜索 → 24 字段/笔记（作者档案 + 点赞/评论/收藏 + 图集 + 可播放视频流 URL）；支持按笔记类型过滤；30 秒 500 条
- **计价**：$4.99 / 1,000 results
- **代理/签名**：同系列 actor 主打免 cookie；本次精读摘要未展开代理细节
- **适配场景**：批量关键词（如"上海 本帮菜""前滩 咖啡"）拉笔记列表做语料，速度快、社区验证最充分

#### D. `memo23/xiaohongshu-rednote-scraper` —— 唯一覆盖小红书商城价格
- **可取**：除常规笔记/用户/评论外，独有 **mall-products** 操作：`price / salePrice / couponPrice / soldCount / stockStatus / sellerId / vendorName / brand / imageUrl / productUrl`；以及 **channel-feed**（12 个品类如 food/travel/fashion，免登录）
- **计价**：$5.00 / 1,000 results flat
- **代理/签名**：详情/主页/频道/商城免登录；**搜索必须自备 `web_session` cookie**（小红书对游客搜搜索 API 返 code -104）；评论和用户笔记第 2 页起也建议带 cookie；内置 residential 路由
- **适配场景**：如果需要监测小红书商城里的餐饮/食品 SKU 价格与销量，这是少数能做到的 actor；但做关键词搜索要先解决 cookie

#### E. `crawloop/xiaohongshu-scraper` —— 最便宜但能力窄
- **可取**：只有公开 explore Feed + note_detail；**不做关键词搜索、不做评论、不做用户主页**
- **计价**：$2.99 / 1,000 items（最便宜）
- **代理/签名**：要求 RESIDENTIAL 代理；不接受 cookie
- **适配场景**：只做"公开推荐流里出现了哪些上海美食笔记"的横向监测，不适合定向关键词调研

---

### 1.3 用户点名的两个 actor 的核实结论

| 用户提到的 id | 核实结果 |
|---|---|
| `clockworks/free-xiaohongshu-scraper` | **不存在**。直接访问 https://apify.com/clockworks/free-xiaohongshu-scraper 返回 link dead。Clockworks 工作室主页（https://apify.com/clockworks）只列了 TikTok 系列（`clockworks/free-tiktok-scraper` 等），没有小红书 actor。 |
| "xapi" | Apify Store 上没有以 `xapi` 为名的独立小红书 actor。最接近的是 `justoneapi/xiaohongshu-rednote-data-api`（API-first 连接器，BYO JustOneAPI token，https://apify.com/justoneapi/xiaohongshu-rednote-data-api）——它本身是个 wrapper，真实计费走 justoneapi.com，Apify 侧只标 "Pay per usage"，无单价。 |

---

## 2. 其他平台 Actor 简表（抖音 / 知乎 / B站 / 微博 / 微信公众号）

> 每个平台挑 1–2 个在 store 上有实际用户量、页面信息较完整的代表；同平台还有其他 actor（见搜索结果），此处不展开。

| 平台 | Actor ID | Store URL | 可取字段（简） | 计价（usage） | Rental | 免费额度 | 代理 / 签名 | 维护状态（2026-10-01） |
|---|---|---|---|---|---|---|---|---|
| 抖音 | **bovi/douyin-scraper** | https://apify.com/bovi/douyin-scraper | 4 模式：关键词搜索 / 用户视频 / 评论 / 视频详情；20+ 字段（aweme_id, desc, digg/comment/share/play/collect count, video_url, cover, music, hashtags, duration） | hot topics $0.48/1k；其他模式单价页面摘要未展开 | 页面未披露 | 页面未披露 | **必须 CN-residential 代理**（抖音封海外 IP/数据中心 IP）；纯 Python `a_bogus` 签名（SM3+RC4+自定义 Base64），自动注册 ttwid，无需手动 cookie | Rating 0.0；72 users；7 MAU；2 个月前更新 |
| 抖音 | memo23/douyin-scraper | https://apify.com/memo23/douyin-scraper | 视频详情、创作者主页、评论；无浏览器、无登录 | **$3.00 / 1,000 results** | 页面未披露 | 页面未披露 | 页面摘要未披露代理细节 | 2026-09-26 更新 |
| 知乎 | **sian.agency/zhihu-scraper** | https://apify.com/sian.agency/zhihu-scraper | 4 操作：关键词搜索 / 问题答案串 / 文章详情 / 专栏文章列表 | **$2.00 / 1,000 search results** 起 | 页面未披露 | 页面未披露 | 托管管线，"No API key" | Rating 0.0；216 users；31 MAU；17 天前更新 |
| 知乎 | blackfalcondata/zhihu-scraper | https://apify.com/blackfalcondata/zhihu-scraper | 热榜、问答答案（正文+互动数）、作者主页；增量模式 | **$3.00 / 1,000 results** | 页面未披露 | 页面未披露 | 无需登录 / API key | 2026-07-18 |
| B站 | **atomus/bilibili-scraper** | https://apify.com/atomus/bilibili-scraper | 8 模式：搜索 / 视频详情 / 评论 / **弹幕（带秒级时间戳）** / **原生字幕 transcript** / UP主主页 / UP主视频列表 / 热门；字段含 view/like/coin/favorite/share/danmaku_count | **$8.00 / 1,000 videos** 起；评论、弹幕、字幕按条另计 | 页面未披露 | 页面未披露 | 不需要 cookie / 登录；失败查询免费 | Rating 5.0 (1)；59 users；35 MAU；6 天前更新 |
| B站 | silentflow/bilibili-scraper | https://apify.com/silentflow/bilibili-scraper | 视频、弹幕文本、评论串、创作者目录、直播间状态，8 模式 | **$2.83 / 1,000 results** 起 | 页面未披露 | 页面未披露 | 无需登录 / API key | 2026-07-10 |
| 微博 | **themineworks/weibo-scraper** | https://apify.com/themineworks/weibo-scraper | 用户主页（粉丝/关注/认证/简介）+ 推文时间线（转发/评论/点赞数、配图、是否视频/转发） | Free $3.00 / Bronze $2.75 / Silver $2.50 / **Gold+ $2.25** per 1,000 results | 无启动费、无订阅 | Apify Free 月送 $5 额度 ≈ 1,666 条 | **中国 residential 代理**，无需登录、无浏览器；封锁/空时间线不收费 | Rating 0.0；4 users；2 MAU；**11 小时前**更新（很新） |
| 微博 | sian.agency/weibo-scraper | https://apify.com/sian.agency/weibo-scraper | 微博正文、用户主页、粉丝、关键词搜索 | **$18.75 / 1,000 weibo details**（贵） | 页面未披露 | 页面未披露 | 托管，无 API key | 2026-05-12 |
| 微信公众号 | **zen-studio/wechat-official-account-scraper** | https://apify.com/zen-studio/wechat-official-account-scraper | 15 操作、52 字段：文章/账号搜索、阅读数、点赞、分享、评论、认证主体公司、微信指数关键词趋势 | **$4.99 / 1,000 article results** 起 | 页面未披露 | 页面未披露（Rising star 标签） | 页面摘要未展开签名/代理细节 | Rating 5.0 (1)；**1.5K users；871 MAU**；5 天前更新；issues 响应 3.3h |
| 微信公众号 | sian.agency/wechat-official-account-data-scraper | https://apify.com/sian.agency/wechat-official-account-data-scraper | 文章内容/详情、账号档案/注册信息、今日/历史文章、评论、互动数、文章/热文/小程序/指数/账号搜索 | **$20.00 / 1,000 article search results**（贵） | 页面未披露 | 页面未披露 | "wxid-native, no login" | Rating 5.0；Rising star；2026-09-26 更新 |

---

## 3. 对 china-travel-food 项目的选型建议（仅基于本次调研事实，不含实现）

> 以下是事实归纳后的观察，不是实施决定。

1. **小红书关键词搜索 + 笔记正文 + 互动数 + 作者信息**：首选 `sian.agency/xiaohongshu-rednote-scraper`（用户量 646、3 小时前还在更新、支持中英文混合关键词、错误行不收费）或 `zen-studio/rednote-search-scraper`（用户量 6.6K 最大、30 秒 500 条、$4.99/1k）。两者都不需要自备 cookie。
2. **需要蒲公英 KOL 刊例价**（做探店合作预算）：只有 `atomus/xiaohongshu-scraper` 提供 `picture_price / video_price / lower_price`，且全 7 模式免 cookie；代价是单价偏高（笔记搜索 $0.02、PGY $0.05/达人）。
3. **需要小红书商城 SKU 价格/销量**：只有 `memo23/xiaohongshu-rednote-scraper` 的 mall-products 操作覆盖；但注意它的**关键词搜索必须自备 `web_session` cookie**，不能纯无登录跑。
4. **不需要关键词、只做公开推荐流趋势观察**：`crawloop/xiaohongshu-scraper` 最便宜（$2.99/1k），但能力窄，且要求 RESIDENTIAL 代理。
5. **抖音**：`bovi/douyin-scraper` 透明披露了 CN-residential 强制要求 + a_bogus 自签名，适合技术型团队；`memo23/douyin-scraper` $3/1k 更便宜。
6. **B站弹幕/字幕**：`atomus/bilibili-scraper` 是少数同时给弹幕时间戳 + 原生字幕 transcript 的 actor，做视频探店内容分析有用。
7. **微博**：`themineworks/weibo-scraper` $2.25–3.00/1k 便宜但只按 user ID 拉主页+时间线；要关键词搜索需看 `sian.agency/weibo-scraper`（$18.75/1k，贵）。
8. **微信公众号**：`zen-studio/wechat-official-account-scraper`（1.5K users、871 MAU、$4.99/1k）是生态里唯一能拿到阅读数/在看/微信指数的成熟 actor。

---

## 4. 关键来源 URL 列表

小红书：
- https://apify.com/atomus/xiaohongshu-scraper
- https://apify.com/memo23/xiaohongshu-rednote-scraper
- https://apify.com/sian.agency/xiaohongshu-rednote-scraper
- https://apify.com/crawloop/xiaohongshu-scraper
- https://apify.com/vulnv/xiaohongshu-scraper
- https://apify.com/zen-studio/rednote-search-scraper
- https://apify.com/justoneapi/xiaohongshu-rednote-data-api
- https://apify.com/opspilot.cc/xiaohongshu-keyword-search-scraper
- https://apify.com/socialdatax/socialdatax-xhs-data-api
- https://apify.com/clockworks （Clockworks 工作室主页，确认无小红书 actor）

其他平台：
- https://apify.com/bovi/douyin-scraper
- https://apify.com/memo23/douyin-scraper
- https://apify.com/sian.agency/zhihu-scraper
- https://apify.com/blackfalcondata/zhihu-scraper
- https://apify.com/atomus/bilibili-scraper
- https://apify.com/silentflow/bilibili-scraper
- https://apify.com/themineworks/weibo-scraper
- https://apify.com/sian.agency/weibo-scraper
- https://apify.com/zen-studio/wechat-official-account-scraper
- https://apify.com/sian.agency/wechat-official-account-data-scraper

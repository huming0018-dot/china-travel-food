# Part 3 · 各平台"合规优先、低风控"取数通道与另类线索

> 调研范围：仅做通道与合规性调研，**不实现、不购买、不写库**。
> 调研时间：2026-10-01（Asia/Shanghai）。所有 URL 均为本次联网核验的真实链接；查不到官方开放通道的，如实标注"无/未查到"。
> 合规总原则：① 官方 API 优先，且只在"本人/本主体授权数据"范围内使用；② 尊重 robots.txt 与平台服务条款；③ 限速 + 成熟代理池轮换降风控；④ 个人数据最小化、不留存可识别个人信息（PII）；⑤ 榜单/节目等公开名单仅做引用与聚合，标注来源。

---

## 0. 六平台推荐通道一句话汇总

| 平台 | 推荐合法通道（一句话） |
|---|---|
| 知乎 | 走 2026 年新上线的**知乎数据开放平台 developer.zhihu.com**（站内搜索/热榜/直答/本人内容，注册送约 1000 次/日），未授权抓取仅作补充。 |
| B站 | 官方 open.bilibili.com 仅服务"本人授权 UP 主"数据；公开视频元数据靠**成熟采集 actor（Apify 等）+ 限速**，官方非开放 web API 已被发律师函警告。 |
| 微博 | **open.weibo.com OAuth2 审核后接口**（150/500/1500 次/小时分级）或微博商业开放平台按量 Credit；公开热搜/帖子用第三方数据 API actor。 |
| 微信公众号 | 官方 API **只能读自己已授权公众号**（freepublish/datacube），无法合法批量抓他人号；跨号内容靠搜狗微信/搜索快照/人工。 |
| 微信视频号 | **基本无开放内容通道**——官方社区明确答复"没有提供观看/点赞/转发数据 API"；仅视频号小店/电商罗盘对自有商家开放，公开侧只能人工/搜索快照。 |
| 抖音 | 官方 open.douyin.com 所有数据 scope **均需用户授权、只能读授权账号自己的视频**（video.list 约 1000 次/日免费额度），且禁止转售数据服务；公开竞品分析靠合规采集 actor。 |

---

## 1. 知乎

### 1.1 官方开放平台 / API
- **平台名称**：知乎数据开放平台（2026 年随"知乎 AI Works"上线，配套 Zhihu CLI）。
- **开发者文档 / 入口 URL**：
  - 官方开发者门户：`https://developer.zhihu.com/`（据中国网/央广网 2026-09 报道，数据开放平台已有 17600+ 开发者接入）
    - 报道佐证：`http://tech.china.com.cn/internet/20260904/413793.shtml` 、`http://tech.cnr.cn/techgd/20260904/t20260904_527804663.shtml`
  - 结构化内容端点（第三方开发者 2026-07-31 实测枚举）：`GET https://developer.zhihu.com/api/v1/user/contents`（列出公开范围内的回答、文章、视频、想法、问题）。
  - 新开放的"搜索类"API（2026-05 起）：站内搜索、全网搜索、热榜（实时 Top30）、直答（流式），注册即送约 **1000 次/日**免费调用（社区短视频口径，非官方文档原文，落地前需在 developer.zhihu.com 核实配额）。
- **可获取数据**：站内问答/文章检索、实时热榜、AI 直答结果、（授权后）创作者本人公开内容列表。**不**开放任意他人主页/评论的批量导出。
- **授权方式**：开发者注册 + APP_ID/APP_KEY，OAuth 2.0 授权码流程；创作者侧数据需本人授权。
- **配额限制**：搜索类约 1000 次/日免费额度（待官方页核实）；历史上知乎对第三方采取"白名单许可"制，非白名单不得抓取。
- **历史背景**：老牌 `open.zhihu.com` 面向第三方内容获取早已实质停摆；知乎对未授权抓取长期采取白名单 + 发函态度（界面新闻 2026-04 报道"未向外部开放内容授权"）。

### 1.2 其次：合规采集平台 / 授权数据
- 成熟第三方数据中转（点名，不在此深挖 Apify）：
  - **TikHub**（覆盖 Zhihu web API：用户信息/关注/粉丝/文章）：`https://api.tikhub.io/#/Zhihu-Web-API`
  - **JustOneAPI**（Zhihu User Followees 等）：`https://docs.justoneapi.com/en/api/zhihu/user-followees-v1`
  - 说明：此类为"代抓取/API 转售"，合规责任仍在使用方，仅适合小样本、低留存、注明来源。

### 1.3 再次：搜索快照 / RSS / 人工
- 搜索引擎快照（site:zhihu.com 关键词）、知乎问题页公开 HTML 人工读取；无官方 RSS。

### 1.4 知乎通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| developer.zhihu.com 官方数据开放平台（搜索/热榜/直答） | 问题标题、摘要、热榜条目、直答文本 | **低** | 小 |
| 本人授权内容 API（/api/v1/user/contents） | 授权账号的回答/文章/视频列表 | **低** | 小-中 |
| TikHub / JustOneAPI 转售接口 | 他人用户/关注/文章元数据 | **中**（代抓取，需限速+不留 PII） | 中 |
| 未授权抓 api/v4 网页接口 | 回答正文、评论 | **高**（知乎反爬+白名单发函） | 大 |

---

## 2. B站（哔哩哔哩）

### 2.1 官方开放平台 / API
- **平台名称**：哔哩哔哩开放平台。
- **开发者文档 URL**：
  - 门户：`https://open.bilibili.com/` 、`https://openhome.bilibili.com/`
  - OAuth 2.0 接入：`https://openhome.bilibili.com/doc/4/aac73b2e-4ff2-b75c-4c96-35ced865797b`
  - 文档镜像（Apifox）：`https://bilibili.apifox.cn/`
- **可获取数据**：注意——官方开放能力**面向 UP 主/媒体机构/服务商**，是"内容生产与本人账号管理"：如查询**授权用户自己的视频稿件列表**（`https://member.bilibili.com/arcopen/fn/archive/viewlist`，scope `ARC_BASE`）、直播间基础信息/开播、Webhooks 事件回调、视频投稿。
- **授权方式**：注册 → 资质认证（企业/机构/UP 主实名）→ 创建应用拿 `client_id`/`app_secret` → OAuth2.0 用户授权 + B站签名算法（签名 2.0）。
- **配额限制**：按 scope 申请权限、按应用审核分级；非公开统一配额表。
- **重要风控信号**：知名开源仓库 `SocialSisterYi/bilibili-API-collect` 已于 2026-09 宣布**停止维护并删除**（作者发布收到律师函公告），说明 B站对**非开放网页 API（api.bilibili.com）的未授权采集正在强执法**。

### 2.2 其次：合规采集平台 / 授权数据（Apify 成熟 actor 点名）
- `openclawai/tiktok-douyin-bilibili-scraper`（视频/主页/评论/直播/热门）：`https://apify.com/openclawai/tiktok-douyin-bilibili-scraper`
- `scrapesage/bilibili-scraper`（关键词/热门/分区榜/评论/UP 主线索，纯 HTTP 免登录）：`https://apify.com/scrapesage/bilibili-scraper`
- `haketa/bilibili-scraper`（视频/弹幕/评论/UP 主）：`https://apify.com/haketa/bilibili-scraper`
- `zhorex/bilibili-scraper`（视频/弹幕/评论/创作者）：`https://apify.com/zhorex/bilibili-scraper`
- 用法：按关键词搜美食探店视频元数据（标题、播放、点赞、弹幕数、UP 主名），小样本、限速、仅存聚合字段。

### 2.3 再次：搜索快照 / RSS / 人工
- 站内公开视频页人工读取、搜索引擎快照；B站无对外 RSS。

### 2.4 B站通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| open.bilibili.com 官方（本人授权 UP 主） | 自己稿件列表/直播/回调事件 | **低** | 中（需资质认证） |
| Apify 成熟 actor（限速小样本） | 视频标题/播放/赞/弹幕/评论/UP 主 | **中** | 小-中 |
| 未授权直连 api.bilibili.com | 全量视频/评论/弹幕 | **高**（已发律师函、仓库下架） | 大 |

---

## 3. 微博

### 3.1 官方开放平台 / API
- **平台名称**：新浪微博开放平台（open.weibo.com）。
- **开发者文档 URL**：
  - 门户/Wiki：`https://open.weibo.com/wiki/`
  - 频次限制说明：`https://open.weibo.com/wiki/Rate-limiting`（历史版本快照仍有效）
  - FAQ：`https://open.weibo.com/wiki/常见问题`
- **可获取数据**：OAuth 授权用户的微博、评论、用户资料、关系链；热搜/公开帖子读取需对应接口权限并过审。
- **授权方式**：微博账号注册开发者 → 创建应用拿 AppKey/AppSecret → OAuth2.0；**未过审应用仅创建者+最多 15 个测试账号可调**。
- **配额限制（每授权用户/每小时）**：
  - 普通授权 **150 次/小时**；初级 **500**；高级 **1500**；合作伙伴不限。
  - 发博 30 次/小时、发评论 60 次/小时、加关注 60 次/小时（100 次/天）。
  - 可用 `account/rate_limit_status` 实时查余量。
- **商业开放平台**：微博商业 API 2026-08 升级为**全接口开放 + Credit 按量计费**（见官微 `https://m.weibo.cn/detail/5331429882857578`），适合付费、合规、规模化的数据读取。

### 3.2 其次：合规采集平台 / 授权数据
- `socialdatax/socialdatax-weibo-data-api`（微博搜索/热搜/评论导出/用户资料/帖子列表）：`https://apify.com/socialdatax/socialdatax-weibo-data-api`
- `atomus/weibo-scraper`（Apify MCP 生态，与 douyin/bilibili 同套件）：`https://apify.com/atomus/douyin-scraper`（同作者含 weibo-scraper）
- TikHub 亦覆盖微博（见 `https://api.tikhub.io/`）。

### 3.3 再次：搜索快照 / RSS / 人工
- m.weibo.cn 移动端公开页、搜索引擎快照；无官方 RSS。

### 3.4 微博通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| open.weibo.com OAuth2 过审应用 | 授权用户微博/评论/资料 | **低**（受配额约束） | 中（需过审） |
| 微博商业开放平台 Credit 按量 | 全接口公开数据读取 | **低** | 小（付费） |
| socialdatax / TikHub 转售 | 搜索/热搜/评论/用户 | **中** | 小-中 |
| 未授权抓 m.weibo.cn | 全量帖子/评论 | **高** | 大 |

---

## 4. 微信公众号

### 4.1 官方开放平台 / API
- **平台名称**：微信公众平台 / 微信开放文档。
- **开发者文档 URL**：
  - 服务端 API 总览：`https://developers.weixin.qq.com/doc/service/api/index.html`
  - 获取已发布图文：`https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublishgetarticle`
  - 数据统计接口：`https://developers.weixin.qq.com/doc/subscription/guide/product/analysis_data/analysis_data.html`
- **可获取数据（关键边界）**：
  - `freepublish/getarticle`（获取已发布图文信息）、`freepublish/batchget`（已发布消息列表）。
  - datacube 系列：`getuserread`/`getarticletotal`/`getarticleread`/`getusershare` 等阅读、分享、转发概况。
  - **这些接口只能读取"本主体自己的公众号"（或经第三方平台代授权的公众号）**。官方社区明确：群发列表/后台已群发文章**不支持接口获取**，且**无法通过 API 抓取任意第三方公众号的文章正文**。
- **授权方式**：公众号服务号/订阅号 → 服务器端 `access_token`；第三方平台（代开发）需公众号管理员授权绑定。2025-07 起个人/部分主体能力收紧。
- **配额限制**：access_token 日调用频次受微信全局限流；datacube 数据按账号自身维度，不开放跨账号。

### 4.2 其次：合规采集平台 / 授权数据
- 跨号公众号文章**无官方合规批量通道**。成熟做法是：通过搜狗微信（weixin.sogou.com，历史入口）或新榜/清博等**持牌第三方数据服务商**（商业授权，本报告不深挖）获取公开文章标题/摘要/阅读在看数。

### 4.3 再次：搜索快照 / RSS / 人工
- 公众号文章公开临时链接（mp.weixin.qq.com/s/...）人工读取、搜索引擎快照；无官方 RSS。转载/引用须标注出处与作者。

### 4.4 公众号通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| 官方 freepublish/datacube（自有号） | 本号已发布图文、阅读/分享统计 | **低** | 中 |
| 持牌第三方（新榜/清博等商业授权） | 跨号文章标题/摘要/阅读在看 | **中**（需商务授权） | 中 |
| 公开临时链接人工/快照 | 单篇正文、作者、公众号名 | **中**（限速、不批量） | 小-中 |
| 未授权批量抓 mp.weixin.qq.com | 全量他人文章库 | **高** | 大 |

---

## 5. 微信视频号（重点：封闭生态）

### 5.1 官方开放平台 / API —— 基本无公开内容通道
- **官方文档 URL**：`https://developers.weixin.qq.com/doc/channels/`（视频号助手 API）。
- **官方社区明确答复（原文口径）**：
  - "关于视频号数据获取的 API……官方文档未提供对应 API 接口"（浏览/访问/点赞/转发运营数据**未开放**）——`https://developers.weixin.qq.com/community/develop/doc/000e2848b0cdb084e603de97d66400`
  - "视频号可以通过 API 获取观看、转发、喜欢的数据吗？……**不能，官方没有提供相关 API**。"——`https://developers.weixin.qq.com/community/develop/doc/0004a459594e60481fb20c1d461000`
  - 小程序侧跳转类接口（`wx.reserveChannelsLive`、`wx.openChannelsUserProfile`）多标记为"不支持"。
- **唯一开放的是"电商/商家自有"侧**：
  - 视频号小店 / 罗盘达人版：如"获取带货人群数据" `https://developers.weixin.qq.com/doc/channels/api/channels/compass/api_getfindersaleprofiledata.html`
  - 第三方平台"视频号权限集"（留资组件、直播数据、达人数据、商品橱窗，权限集 ID 143/160/176/177）：`https://developers.weixin.qq.com/doc/oplatform/Third-party_Platforms/2.0/product/channel_authority.html`
  - 这些**仅对已认证的自有商家/达人主体开放**，不构成对外的内容数据获取通道。

### 5.2 其次：合规采集平台 / 授权数据
- **无成熟、低风控的第三方视频号公开数据采集 actor**（微信封闭生态，连 TikHub/Apify 都仅覆盖极有限的电商侧）。不要预期可批量抓取。

### 5.3 再次：搜索快照 / RSS / 人工
- 视频号内容**不被搜索引擎索引**，公开侧几乎只能：微信内人工浏览、官方创作者后台（自有号）、媒体报道间接引用。**如实说明：公开跨号取数基本无合法自动化通道。**

### 5.4 视频号通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| 视频号小店/罗盘（自有商家） | 带货人群、单场直播、商品橱窗数据 | **低**（限自有主体） | 中 |
| 自有创作者后台人工导出 | 本号播放/点赞/转发 | **低** | 小 |
| 公开跨号自动抓取 | 任意视频号内容 | **高 / 实际不可行** | 极大（不建议） |

---

## 6. 抖音

### 6.1 官方开放平台 / API
- **平台名称**：抖音开放平台。
- **开发者文档 URL**：
  - 文档根：`https://developer.open-douyin.com/` （调用域 `https://open.douyin.com/`）
  - 免费额度说明：`https://developer.open-douyin.com/docs/resource/zh-CN/dop/common-question/free-quota-common-question`
  - 查询特定视频数据（`/api/douyin/v1/video/video_data/`，scope `video.data.bind`）：`https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/search-video/video-data`
- **可获取数据（关键边界）**：视频列表（标题/封面/创建时间）、单条视频互动数据（播放/点赞/评论/分享/平均播放时长）。**但所有数据 scope 均"需要用户授权"，即只能读授权用户本人的视频**。能力中心明确："仅可在展示**授权用户自己**视频互动数据的场景，**不可用于搭建对外售卖的数据服务**"。
- **授权方式**：OAuth 2.0 登录授权（access_token）；经营侧用 business_token（需品牌号/员工号/合作号绑定，且千粉以上）。
- **配额限制**：按 scope 给每日免费额度（如 `video.list` 每日约 **1000** 次，次日 8 点恢复）；测试应用未转正按创建时间收紧（30 天内 100 次/天 → 120 天后 10 次/天）；额度用尽报错 `28003017 quota 已用完`。

### 6.2 其次：合规采集平台 / 授权数据
- `atomus/douyin-scraper`（含星图达人分析）：`https://apify.com/atomus/douyin-scraper`
- `openclawai/tiktok-douyin-bilibili-scraper`：`https://apify.com/openclawai/tiktok-douyin-bilibili-scraper`
- TikHub 覆盖抖音/TikTok（`https://api.tikhub.io/`）。
- 定位：用于竞品/美食博主公开视频元数据小样本分析，须限速、不留可识别个人信息。

### 6.3 再次：搜索快照 / RSS / 人工
- iesdouyin.com 分享页公开 HTML 人工读取、搜索引擎快照；无官方 RSS。

### 6.4 抖音通道表
| 推荐合法通道 | 可取字段 | 风控/合规等级 | 工作量 |
|---|---|---|---|
| open.douyin.com 官方（授权账号） | 本人视频列表/互动数据 | **低** | 中（需授权+额度申请） |
| Apify / TikHub 转售（小样本限速） | 公开视频标题/赞/评论/博主 | **中** | 小-中 |
| 未授权批量抓 iesdouyin | 全量视频/评论 | **高** | 大 |

---

## 7. 另类线索 A：美食综艺 / 纪录片（官方分集页 + 片尾字幕 → 餐厅/主厨）

> 思路：节目官方页会**集中披露参赛主厨名单**，片尾字幕/媒体复盘再补"主厨所在餐厅"，这是**公开、低风控、高信噪比**的餐厅+主厨种子来源。

### 7.1《一饭封神》（腾讯视频出品，中餐厨综，强相关）
- **官方分集/合集页（已核验真实）**：
  - 第 2 季合集页（2026-07-29 开播，共 10 集，评分 9.2）：`https://v.qq.com/x/cover/mzc00200lk7yd24.html`
  - 该页**官方列出全部参演主厨昵称/姓名**（裁判：谢霆锋、陈晓卿、张勇、郑永麒、李诞；选手：宴究生-屈雨瑜、杨艳彬、黎子安、邓华东、张雯雯、刘永康等数十人）。
  - 单集 URL 形如 `https://v.qq.com/x/cover/mzc00200lk7yd24/<vid>.html`（每集看点页可逐集抓主厨出场）。
- **主厨→餐厅映射**：官方合集页只给人，不给店名；需结合**片尾字幕 + 媒体复盘文章**：
  - 第一季"六强/九强餐厅合集"（媒体复盘，列：美佳时宴、福满楼、Neighborhood、Ortensia、新加坡 Saint Pierre、帅帅精致家常味 等）：`http://m.toutiao.com/group/7553904264234517018/`
  - 中国新闻周刊人物侧写（冠军屈雨瑜/宴究生）：`https://news.inewsweek.cn/observe/2025-09-15/26701.shtml`
- **可取字段**：主厨名、昵称、菜系、（媒体复盘补）所在餐厅名与城市。**合规等级：低**（公开节目信息+公开报道引用，注明来源）。

### 7.2《黑白厨师：料理阶级战争》（Culinary Class Wars，Netflix 韩国厨综，体裁参照）
- 说明：用户提及的"《黑白厨房》"对应 Netflix 节目《黑白厨师：料理阶级战争》（Culinary Class Wars，2024）。
- **官方/权威来源**：
  - 豆瓣条目（演职员/季数/播出）：第一季 `https://movie.douban.com/subject/36598424/`
  - 播出平台 Netflix（节目页），第二季 2025-12-16 上线、共 13 集（ELLE 报道 `https://www.elle.com/tw/entertainment/drama/g69465443/culinary-class-wars-s2/`）。
  - 界面新闻行业分析（冠军餐厅预约 11 万的餐饮带动效应）：`https://www.jiemian.com/article/13056512.html`
- **价值**：作为"厨综→主厨餐厅引流"的**方法论模板**；其主厨餐厅多在韩国，对中国餐厅库是**参照而非直接种子**。

---

## 8. 另类线索 B：行业榜单（官方指南站，可否合法获取名单）

> 三榜均为**公开发布、官网/ App 免费可查**，但**均无开放 API**；合规做法是人工/低频次读取官网公开名单并注明来源，不做高频批量抓取。

### 8.1 米其林指南（MICHELIN Guide）
- **官方来源 URL**：
  - 中国站：`https://www.michelin.com.cn/map-guide/`
  - 全球指南站（可按城市/星级筛）：`https://guide.michelin.com/`
  - 中国内地一星列表（示例）：`https://guide.michelin.com/en/cn/restaurants/1-star-michelin`
  - 新闻室榜单发布（如 2026 广州深圳合并 176 家）：`https://www.michelin.com.cn/news/2026/0818.html`
- **可否合法获取名单**：官方明确"完整名单在 MICHELIN 官网与免费 App 上**免费公开**"（`https://guide.michelin.com/en/article/michelin-guide-ceremony/michelin-guide-shanghai-jiangsu-zhejiang`）。**无开放 API**；名单字段（餐厅名、城市、菜系、星级/必比登/入选）属公开榜单信息，可低频次人工整理并注明"MICHELIN Guide"。
- **可取字段**：餐厅名、城市、菜系、人均区间、星级/必比登/绿星。

### 8.2 黑珍珠餐厅指南（美团点评）
- **官方来源 URL**：
  - 黑珍珠官网：`https://blackpearl.meituan.com/home/en/about` （榜单首页 `https://blackpearl.meituan.com/home/en/home/1`）
  - 美团新闻稿（2026 内地 263 家、32 城）：`https://www.meituan.com/zh-HK/news/NN260128167003529`
  - 美团指数报告页：`https://index.meituan.com/reports/meituan-black-pearl-2026/`
- **可否合法获取名单**：官网公开展示钻级餐厅名单，**无开放 API**；每年 1 月内地、3 月港澳台/海外颁奖后公开发布。低频次读取官网/新闻稿名单并注明来源即可。
- **可取字段**：餐厅名、城市、菜系、钻级（一/二/三钻）。

### 8.3 Asia's 50 Best Restaurants
- **官方来源 URL**：
  - Asia's 50 Best 官方榜单页：`https://www.theworlds50best.com/restaurants/best-in-asia/` （51–100 扩展页 `https://www.theworlds50best.com/restaurants/best-in-asia/list/51-100`）
  - 新域名（2026 版）：`https://www.the50.com/restaurants/best-in-asia/`
  - 新闻稿（2026 香港主办、The Chairman 第一）：`https://www.theworlds50best.com/stories/News/asias-50-best-restaurants-2026-hong-kong.html`
- **可否合法获取名单**：官网公开 1–50 及 51–100 完整排名，含餐厅名、城市、主厨、奖项；**无开放 API**。低频次读取官网榜单页、注明 "World's 50 Best Restaurants"。
- **可取字段**：排名、餐厅名、城市、主厨、所获奖项。

---

## 9. 逐平台风险与规避（合规原则落地）

| 平台 | 主要风险 | 规避动作 |
|---|---|---|
| 知乎 | 未授权抓 api/v4、白名单外使用 | 优先 developer.zhihu.com；转售接口仅小样本；不留 PII |
| B站 | 已发律师函、开源采集仓库被下架 | 不碰 api.bilibili.com 直连；用成熟 actor + 限速；官方仅做本人账号 |
| 微博 | 超频次、过审门槛 | 用 rate_limit_status 控速；规模化走商业 Credit 付费 |
| 公众号 | 无法合法抓他人号 | 只做自有号 API；跨号走持牌第三方或人工引用 |
| 视频号 | 封闭、无公开索引 | 不尝试公开批量抓取；仅自有商家后台 |
| 抖音 | 禁止转售数据、scope 限本人 | 官方 API 只读授权账号；竞品分析小样本限速、注明来源 |
| 榜单/节目 | 版权与署名 | 公开名单低频次人工整理，**注明出处**（MICHELIN Guide / 黑珍珠 / World's 50 Best / 腾讯视频） |

---

## 10. 关键 URL 索引（全部本次核验）

- 知乎数据开放平台：`https://developer.zhihu.com/` ；报道 `http://tech.china.com.cn/internet/20260904/413793.shtml`
- B站开放平台：`https://open.bilibili.com/` 、`https://openhome.bilibili.com/`
- 微博开放平台：`https://open.weibo.com/wiki/` ；频次 `https://open.weibo.com/wiki/Rate-limiting`
- 微信公众号服务端 API：`https://developers.weixin.qq.com/doc/service/api/index.html`
- 微信视频号（无公开 API 官方答复）：`https://developers.weixin.qq.com/community/develop/doc/0004a459594e60481fb20c1d461000`
- 抖音开放平台：`https://developer.open-douyin.com/`
- 一饭封神第 2 季腾讯视频官方页：`https://v.qq.com/x/cover/mzc00200lk7yd24.html`
- 米其林中国：`https://www.michelin.com.cn/map-guide/` ；全球 `https://guide.michelin.com/`
- 黑珍珠官网：`https://blackpearl.meituan.com/home/en/about`
- Asia's 50 Best：`https://www.theworlds50best.com/restaurants/best-in-asia/`

> 备注：知乎"搜索类 API 1000 次/日"、抖音各 scope 精确配额等数值来自社区/文档片段，**落地接入前须以官方开发者控制台实时显示为准**；本报告不构成购买或接入建议，仅作通道与合规性调研存档。

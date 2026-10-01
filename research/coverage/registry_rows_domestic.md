# Registry Rows · 国内 UGC/短视频/长图文/消费社区（填充小结）

> 日期：2026-10-01 ｜ 范围：仅调研，不接入/不购买/不写库
> 冻结 schema：见 `coverage_framework.md` §2（15 字段，枚举不可扩）
> 本目录尚未生成 `market_directory.md`，故本轮不做 actor 编目重复，重点列官方/公开/RSS 全通道。

## 1. 交付物
- JSONL 行：`./registry_rows_domestic.jsonl`（44 行，每行一个源实例，已过 json.loads + 15 字段齐检）
- 本小结：`./registry_rows_domestic.md`

## 2. 每平台推荐合法通道（一句话矩阵）

| 平台 | 首选合法通道 | 次选/补充 | 备注 |
|---|---|---|---|
| 微博 | 官方 REST API `open.weibo.com`（追已知 KOL feed） | 主站 `s.weibo.com` 搜索页（高风控） | 任意"搜餐厅"弱，靠 KOL 名单反查 |
| 知乎 | 主站搜索 + `api/v4/questions/{id}/answers`（web） | TikHub 第三方 | 长图文口味证据质量高 |
| B 站 | 开放平台 `open.bilibili.com`（企业授权视频数据） | 主站 `x/web-interface/search/type` + reply/danmaku web 接口 | 探店视频有真实堂食画面 |
| 抖音 | 开放平台 `developer.open-douyin.com`（仅自有企业号评论） | TikHub（高风险，调研用） | 本地探店最活跃但风控最严 |
| 快手 | 开放平台 `open.kuaishou.com`（自有内容） | 主站 / TikHub | 下沉/市井/北方更强 |
| 微信公众号 | 官方 `freepublish/batchget`（仅自有号） | **搜狗微信 `weixin.sogou.com`**（唯一公开跨号搜索） | 美食长文核心通道 |
| 微信视频号 | 官方 `developers.weixin.qq.com/doc/channels`（仅直播/橱窗带货数据） | 无公开通道，只能 app 内人工 | 无内容搜索 API，批量采集高风险 |
| 豆瓣 | 主站小组 `douban.com/group/`（高风控） | everyinfra 第三方 | 文艺/咖啡/私房菜 |
| 下厨房 | 主站 `xiachufang.com`（菜谱+作品） | gitee 非官方 API | **家庭做菜，不产堂食证据** |
| 什么值得买 | 官方 `openapi.smzdm.com` / `openapi.zhidemai.com` | 主站 | **网购消费决策，不产堂食证据** |
| 即刻 | 主站 `web.okjike.com`（需登录） | jikeapi.cn 第三方 | 上海高知圈新店早期信号 |
| 百度贴吧 | 主站 `tieba.baidu.com` | aiotieba 开源 SDK | 城市吧/大众口碑，高端店弱 |
| 虎扑 | 主站 `bbs.hupu.com`（SSR 公开） | Apify `hupu-scraper` | 男性视角性价比 |
| 马蜂窝 | 开放平台 `open.mafengwo.cn`（仅 POI 元数据，无 UGC 正文） | 主站游记/点评 | 旅游场景餐厅 |
| 携程美食林 | 主站榜单页（GUIDE，黑钻/钻石/铂金） | — | 无 API，专业评审榜单 |
| 美团外卖 | 官方 `developer.waimai.meituan.com`（B 端商家自有评价） | — | **外卖≠堂食，默认不作口味证据** |
| 大众点评 | `poiopen.dianping.com`（需商务合作授权） | — | 堂食口味证据主源（单独成行） |
| 饿了么 | 官方 `open-retail.ele.me`（商家侧） | RealDataAPI 第三方 | **外卖≠堂食，默认不作口味证据** |

## 3. 无堂食证据价值的平台/通道（明确标注）

以下行 `dine_in_evidence=false`，**不应**作为"某菜系×某场景"格的口味证据来源：

1. **下厨房**（3 行）：UGC 是家庭菜谱/作品，不是餐厅。可用于"某道菜流行度"，不进门店口味格。
2. **什么值得买**（2 行）：网购食品/厨具/食材消费决策，不产出门店堂食评价。
3. **美团外卖评价**（1 行）：配送场景，受包装/配送/温度影响，与堂食口味不同；仅作门店经营参考。
4. **饿了么**（2 行）：同上，外卖场景。
5. **视频号官方 API 行**（1 行 `wechat_channels_open`）：仅直播/橱窗带货数据，不覆盖餐厅 UGC。
6. 各平台 `active=false` 的占位行（知乎官方、豆瓣 legacy、下厨房官方、即刻官方、贴吧官方、虎扑官方）：开放通道实际已关停/未开放，仅作台账。

## 4. 结构统计（44 行）

- by channel: official_api 17 / public_html 16 / apify_actor 9 / search_snapshot 1 / manual 1
- by category: OPEN_API 14 / DATA_MARKET 12 / UGC 10 / SHORTVIDEO 4 / LONGFORM 3 / GUIDE 1
- dine_in_evidence=true: 29 行；false: 15 行

## 5. 缺口与风险提示

1. **大众点评 UGC 正文**：堂食口味证据最核心源，但 `poiopen.dianping.com` 需商务合作授权，无免费公开通道；本轮只注册了一行占位，实际数据获取需走合作或受限公开页。
2. **微信视频号**：内容完全封闭生态，无公开 web/RSS/API，批量采集合规风险最高；目前只能人工或高风险第三方。
3. **抖音/小红书式短视频发现**：官方开放平台只允许"自有授权账号"数据，跨账号任意搜餐厅的公开通道几乎没有；TikHub 等第三方是事实通道但合规姿态 high，仅调研不落地。
4. **小红书未在本轮点名清单内**（框架 §1.2 把它列在 UGC，但用户本轮未要求）；如需补，参照 Apify XHS 通道在 batch8 LEDGER 中已 parked。
5. **RSS 通道**：国内 UGC 平台几乎无官方 RSS（微博早期支持 rss/atom 现已收窄）；本轮 channel 中无 rss 行，是真实缺口。
6. **堂食证据最厚的格**：综合×正餐 / 综合×休闲（来自知乎长文+B站探店+微信公众号美食媒体+大众点评合作行）。
7. **仍薄的格**：高端 fine-dining（GUIDE 侧靠携程美食林+黑珍珠，UGC 侧只有公众号长文与即刻早期信号）；夜宵/酒吧格在 UGC 侧仅即刻+抖音探店，独立源 <3。

## 6. 未做事项（遵守"只调研"约束）

- 未申请任何 appkey / 未调用任何付费 API / 未写库。
- 第三方数据市场行（TikHub / JustOneAPI / RealDataAPI / Apify actor）仅登记入口与合规姿态，未购买、未实测余额。
- `active=false` 行是台账占位，后续若官方重新开放再激活。

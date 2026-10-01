# Source Coverage Registry · 权威/官方/注册/行业/影视综 源实例（authority 批次）

> 范围：**只调研，不接入/不购买/不写库**。每行严格按 `coverage_framework.md §2` 冻结的 15 字段 schema 输出。
> 生成日期：2026-10-01 ｜ 共 **34** 行 ｜ 本批 `dine_in_evidence` **全部 = false**（权威/互证类，非堂食口味证据）。

## 1. 三类一句话矩阵（通道 × 用途）

| 类 | 通道 | 一句话用途 |
|---|---|---|
| **榜单 GUIDE** | public_html（米其林/黑珍珠/美食林/Asia's50Best 官网榜单页） | 匿名评审/专家榜名单用于**漏店锚定与招牌菜事实互证**，不作品味证据；必比登专门补小吃面店格。 |
| **注册 REGISTRY** | 政府站 public_html（gsxt/SC许可/抽检/裁判/失信/商标）+ 商业查 public_html 带登录墙（企查查/天眼查/启信宝） | 主体/连锁/融资/工商司法/食安负面**事实层互证与爆雷预警**，全部与口味无关。 |
| **影视综 MEDIA_TV** | public_html（腾讯/B站/CCTV/tvN）+ manual（Netflix/字幕） | 纪录片/综艺**拍具体店与摊主，作漏店反推线索与主厨/招牌菜背书**，出品方制作非独立堂食证据。 |

## 2. 哪些只可互证、不可作口味证据

**本批 34 行全部 `dine_in_evidence=false`**。理由逐条：
- **榜单类（米其林/必比登/黑珍珠/美食林/Asia's50Best/Gault&Millau）**：评审榜单输出的是「入选事实」，不是可复现的食客口味评价 → 仅用于店名/菜系/价位/招牌菜互证。
- **注册类（企查查/天眼查/启信宝/gsxt/SC许可/食安抽检/裁判文书/失信/商标）**：法律与行政登记事实 → 仅用于主体归属、连锁结构、融资、食安/司法负面、假店识别，与口味零相关。
- **官方品牌类（公众号/微博/抖音/IG/小程序/官网/商场名录/夜市街区）**：品牌第一方营销口径 → 仅用于菜单/新店/停业/主厨更迭/存在性事实，营销天然偏正面，不可当口味证据。
- **影视综书籍类（风味人间/舌尖/一饭封神/黑白大厨/人生一串/早餐中国/街头美食斗士/美食著作）**：摄制组内容 → 用于漏店反推与主厨/菜品背书，不是独立食客 UGC；真正的堂食口味证据须由 UGC 批次（小红书/点评）补齐。

## 3. 源实例清单

| # | source_id | platform | category | channel | cost | active | url |
|---|---|---|---|---|---|---|---|
| 1 | `guide_michelin_main` | 米其林指南 MICHELIN Guide | GUIDE | public_html | free | ✓ | https://guide.michelin.com/cn/zh_CN/restaurants |
| 2 | `guide_bib_gourmand` | 米其林必比登推介 Bib Gourmand | GUIDE | public_html | free | ✓ | https://guide.michelin.com/cn/zh_CN/restaurants/bib-gourmand |
| 3 | `guide_blackpearl` | 黑珍珠餐厅指南 | GUIDE | public_html | free | ✓ | https://blackpearl.meituan.com |
| 4 | `guide_ctrip_gourmet` | 携程美食林 Trip.Gourmet | GUIDE | public_html | free | ✓ | https://m.ctrip.com/html5/you/foods/ |
| 5 | `guide_asia_50best` | Asia's 50 Best Restaurants | GUIDE | public_html | free | ✓ | https://www.theworlds50best.com/asia/en/list/1-50 |
| 6 | `guide_gault_millau` | Gault&Millau 高勒米罗美食指南 | GUIDE | public_html | free | ✗ | https://www.gaultmillau.com |
| 7 | `off_wechat_oa` | 微信公众号(品牌官方) | OFFICIAL | public_html | free | ✓ | https://mp.weixin.qq.com |
| 8 | `off_weibo` | 新浪微博(品牌官方蓝V) | OFFICIAL | public_html | free | ✓ | https://weibo.com |
| 9 | `off_douyin_brand` | 抖音/视频号(品牌官方号) | OFFICIAL | public_html | free | ✓ | https://www.douyin.com |
| 10 | `off_instagram` | Instagram(在华海外品牌官方) | OFFICIAL | public_html | free | ✓ | https://www.instagram.com |
| 11 | `off_wechat_mini` | 微信小程序(订座/点单/菜单) | OFFICIAL | manual | free | ✓ | https://mp.weixin.qq.com |
| 12 | `reg_qcc` | 企查查 | REGISTRY | public_html | 免费基础查询，深度付费 | ✓ | https://www.qcc.com |
| 13 | `reg_tianyancha` | 天眼查 | REGISTRY | public_html | 免费基础查询，深度付费 | ✓ | https://www.tianyancha.com |
| 14 | `reg_qixin` | 启信宝 | REGISTRY | public_html | 免费基础查询，深度付费 | ✓ | https://www.qixin.com |
| 15 | `reg_gsxt` | 国家企业信用信息公示系统 | REGISTRY | public_html | free | ✓ | https://www.gsxt.gov.cn |
| 16 | `reg_sc_prod_license` | 食品生产许可获证企业信息查询 | REGISTRY | public_html | free | ✓ | https://spaqjg.e-cqs.cn/spscxk/ |
| 17 | `reg_food_sampling` | 食品安全抽检公布结果查询 | REGISTRY | public_html | free | ✓ | https://spcjsac.gsxt.gov.cn/ |
| 18 | `reg_court_wenshu` | 中国裁判文书网 | REGISTRY | public_html | free | ✓ | https://wenshu.court.gov.cn |
| 19 | `reg_shixin` | 中国执行信息公开网(失信/被执行) | REGISTRY | public_html | free | ✓ | http://zxgk.court.gov.cn |
| 20 | `reg_trademark` | 中国商标网(国家知识产权局) | REGISTRY | public_html | free | ✓ | https://sbj.cnipa.gov.cn/trademark-query |
| 21 | `media_hongcan_hongchu` | 红餐网/红厨网 | MEDIA | public_html | free | ✓ | https://www.canyin88.com |
| 22 | `media_mingchu` | 名厨 MINGCHU | MEDIA | public_html | free(社区)/活动付费 | ✓ | https://www.mingchu.co |
| 23 | `media_canyinneican` | 餐饮老板内参 | MEDIA | search_snapshot | free | ✓ | https://weixin.sogou.com/weixin?type=1&query=%E9%A4%90%E9%A5%AE%E8%80%81%E6%9D%BF%E5%86%85%E5%8F%82 |
| 24 | `media_foodaily` | Foodaily每日食品 | MEDIA | public_html | free | ✓ | https://www.foodaily.com |
| 25 | `tv_fengwei` | 风味人间(陈晓卿团队/腾讯视频) | MEDIA_TV | public_html | free(会员) | ✓ | https://v.qq.com |
| 26 | `tv_shejian` | 舌尖上的中国(CCTV) | MEDIA_TV | public_html | free | ✓ | https://tv.cctv.com |
| 27 | `tv_yifan` | 一饭封神(腾讯视频) | MEDIA_TV | public_html | 会员 | ✓ | https://v.qq.com |
| 28 | `tv_heibai` | 黑白大厨：料理阶级大战(Netflix) | MEDIA_TV | manual | 会员 | ✓ | https://www.netflix.com |
| 29 | `tv_rensheng` | 人生一串(B站) | MEDIA_TV | public_html | free | ✓ | https://www.bilibili.com |
| 30 | `tv_zaoguo` | 早餐中国(腾讯/东南/海峡卫视) | MEDIA_TV | public_html | free | ✓ | https://v.qq.com |
| 31 | `tv_streetfighter` | 街头美食斗士(tvN/白钟元) | MEDIA_TV | public_html | 部分Netflix | ✓ | https://www.tvnasia.net |
| 32 | `tv_foodbooks` | 美食作家/美食家著作(豆瓣读书) | MEDIA_TV | search_snapshot | free | ✓ | https://book.douban.com |
| 33 | `offline_mall_directory` | 购物中心官网租户名录 | OFFICIAL | public_html | free | ✓ | https://www.plaza66.com |
| 34 | `offline_night_block` | 夜市/美食街区官方名录 | OFFICIAL | public_html | free | ✓ | https://www.shanghai.gov.cn |

## 4. 风控/合规速览

- **可低摩擦抓（tos=low）**：米其林、Asia's50Best、Gault&Millau、gsxt、SC许可、食安抽检、失信执行、商标网、Foodaily、影视官方页、商场/夜市官方名录。
- **需限速/反爬（tos=medium）**：黑珍珠、携程美食林、微博、名厨、红餐、腾讯/B站/CCTV/tvN 页面。
- **高摩擦/版权（tos=high）**：微信公众号、抖音/视频号、企查查/天眼查/启信宝（登录墙+用户协议）、裁判文书网（2021后收紧）、Netflix（地区+版权）、餐饮老板内参（仅搜狗微信快照）。
- **成本**：本批全部 **free**（商业查深度字段、视频会员为按需付费，调研阶段未购）。

## 5. 说明与未决

- 用户清单中「G&G」按 **Gault&Millau（高勒米罗）** 核实：其全球站可达，但**截至 2026-10 无中国大陆/港澳独立版**，已标 `active=false`，covered_grid 留空，待提审是否启用。
- 「黑白厨房」实为 2024 Netflix **《黑白大厨：料理阶级大战》(Culinary Class Wars)**，已按正名登记并保留别名备注。
- 商场租户名录/官方公众号/小程序为**渠道模式行**：官网域名为代表入口，实际逐店/逐 mall 实例化时再补具体子页。
- 本批不满足 §3「每格 ≥1 个 dine_in_evidence=true」——那是 UGC 批次的责任；本批只贡献互证与事实层。

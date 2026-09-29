# 多平台爬虫后端评估（上海服务器 49.234.35.92，2GB RAM）

> 日期：2026-09-29 晚。目标：为微博/知乎/抖音采集选后端。
> 服务器约束：food-cloud 常驻约 443MB，整机可用约 1.1GB（含 buff/cache），无 swap 余量约 1.7GB。
> 服务器直连 github https 不通（TLS），ctfs_github 是 china-travel-food 专用 deploy key，不能克隆其他仓库。

## 一、逐平台 keyless 实测（服务器本机 requests，非 README 转述）

| 平台 | 端点 | 状态 | 结果 | 结论 |
|---|---|---|---|---|
| 微博 m.weibo.cn 搜索 | `/api/container/getIndex?containerid=100103type=1&q=川菜` | 200 | 返回 **Sina Visitor System** HTML；访客流程 incarnate→crossdomain 返回 `retcode 50111257 "tid 不合法"` | **keyless 不可用**，数据中心 IP 被新浪访客系统拦；需登录 cookie |
| 知乎搜索 | `/api/v4/search_v3?q=...` | **401** | `{"error":{"code":101,"ZERR_NOT_LOGIN"}}` | **keyless 不可用**，需登录 |
| 抖音 web 搜索 | `/aweme/v1/web/general/search/single/?keyword=...` | 200 | `data:[]`（无 a_bogus/x-bogus 签名即空） | **keyless 不可用**，需 Playwright 签名或登录 |
| 抖音详情 | `iesdouyin.com/web/api/v2/aweme/iteminfo/` | 200 | 空响应 | 旧接口已废弃，需新版签名 |

样本目录：服务器 `/home/ubuntu/crawler-eval/`（weibo 因被拦未落样本 JSON；三平台均无 keyless 样本可落）。

## 二、候选项目

### 1. dataabc/weibo-crawler / weibo-search（requests 系，轻）
- 依赖仅 requests，可在服务器 venv 跑（内存 <100MB，可行）。
- **但**：其 keyless 能力依赖 m.weibo.cn 访客 cookie 流程，本次实测该流程已被新浪升级拦（50111257）。
- **结论**：代码可部署，但无登录 cookie 时**搜不出结果**；需登录态微博 cookie 才有产出。

### 2. NanmiCoder/MediaCrawler（抖音/知乎/微博/B站/快手/小红书，Playwright/DrissionPage）
- 需 Playwright Chromium（headless 约 300–500MB）+ 扫码登录。
- **2GB 服务器与 food-cloud(443MB) 同跑会 OOM 风险高**；且服务器无法从 github 拉取源码。
- **结论**：不在本机部署；如需用，建议另起独立容器并预留 ≥1GB，或在本机/其他设备跑后回传结果。

## 三、需扫码/登录平台清单（不要现在催，交 KOL 执行者合并一次）
- 微博：登录 cookie（m.weibo.cn）
- 知乎：登录 cookie
- 抖音：App/网页扫码（a_bogus 签名 + 登录）

## 四、建议
1. 近期以**已有小红书登录线**为主；微博/知乎/抖音在拿到登录 cookie 前不硬跑。
2. weibo-crawler 轻量 requests 壳已就绪（`probe` 脚本），拿到微博 cookie 即可切换；无需起重容器。
3. MediaCrawler 待 KOL 扫码合并时，另起独立内存容器评估，不在本 2GB 主机硬上。

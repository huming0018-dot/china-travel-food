# food-radar 工具调用流程与技术规范

> 依赖说明：本仓库（GitHub）**不包含** `tools/` 下的第三方克隆仓库（体积大且有各自许可），请按第 3 节命令自行克隆。
> `wechat-article-search` 为同机独立 skill（`~/.codebuddy/skills/wechat-article-search/`），不在本仓库内，需另行安装。
> **已实测的安装状态与踩坑见 `environment.md`；开工前请先跑 `bash scripts/preflight.sh`。**

## 一、工具调用流程（按序执行）

```
Step1 对标解码        → 无需工具，纯推理；产物：筛选标准
Step2 关键词矩阵      → 产出 6-10 组查询
Step3 多通路检索      → web_search / web_fetch（S级事实）
                       wechat-article-search（KOL长文）
                       agent-reach CLI（小红书/抖音/B站/微博/海外平台）
                       media-crawler（批量抓取，需登录态）
                       agent-browser / playwright（点评店铺页、小红书详情页）
                       dianping-crawler（全量店铺库，竞品盘点）
Step4 时效与信源校验  → 对每条候选做日期/双信源/在营核查（见 validation.md）
Step5 结构化输出      → 按 field-spec.md 生成 JSON/Markdown + 知识沉淀
```

## 二、平台覆盖与工具映射

| 平台 | 首选 | 命令/方式 | 备注 |
|---|---|---|---|
| 通用搜索 | web_search | 直接调用 | S级信源发现主力 |
| 网页读取 | web_fetch | 直接调用 | 政府/官媒/榜单页 |
| 微信公众号 | wechat-article-search skill | `node scripts/search_wechat.js "关键词" -n 15` | 依赖 Node；结果旧文多，须叠加时间词 |
| 小红书/抖音/B站/微博/知乎 | MediaCrawler | Playwright + 登录态，见 tools/media-crawler | 批量、结构化落盘 |
| 小红书/抖音/B站/Twitter/Reddit/YouTube/GitHub | Agent-Reach CLI | 一条命令装好，见 tools/agent-reach | 免 API 费用，适合单点搜索 |
| 大众点评 | dianping-crawler + agent-browser | `wongben/dianping-crawler`（Java，全上海店铺库） | 精确评分/人均须标注抓取时间 |
| 任意复杂页面 | agent-browser / playwright-cli skill | 浏览器自动化 | 兜底方案 |

## 三、安装命令

### 通用前置
```bash
export PATH="/Users/deuce/.local/bin:$PATH"   # uv 与 python3.12 所在目录
bash scripts/preflight.sh                     # 开工自检，优先于下面任何安装步骤
```

### Agent-Reach（推荐先装）
```bash
cd tools/agent-reach
uv tool install .                # 产出 /Users/deuce/.local/bin/agent-reach
agent-reach doctor               # 通路自检（实测基线：4/16）
agent-reach skill --install      # 注册 skill 到 ~/.agents/skills/agent-reach
```
小红书通路需手动 Cookie：浏览器装 Cookie-Editor 导出后 `agent-reach configure xhs-cookies "<json>"`。
抖音不在agent-reach 覆盖范围，须走 MediaCrawler 的 `dy` 平台。

### MediaCrawler
```bash
cd tools/media-crawler
uv venv --python 3.12 .venv       # 必须 3.11+；系统 python3.9 会装失败
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/playwright install chromium
# 首次使用需用 Playwright 登录各平台保存登录态（cookie），详见其README
```
支持平台：`xhs` `dy` `ks` `bili` `wb` `tieba` `zhihu`。

### 点评爬虫（竞品全量盘点用）
```bash
git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler
```
Java + Maven 工程，**需本机有 JDK 与 mvn**；未满足时点评数据走降级方案（见 `environment.md` 第五节）。

### 环境依赖检查（每次开工先跑）
```bash
bash scripts/preflight.sh
```

## 四、技术规范

1. **频率控制**：同一平台连续请求间隔 ≥ 3s；单次任务抓取页面上限 50；失败退避 30s 重试，最多 3 次。
2. **登录态**：MediaCrawler 的 cookie 只存本地，不进仓库、不进交付物。
3. **合规红线**：仅学习研究用途；不商用、不转卖、不大规模爬取；遵守各平台 robots 与服务条款；交付物中不包含爬得的原始个人信息。
4. **落盘规范**：原始抓取数据存 `data/raw/YYYY-MM-DD-平台-关键词.json`，清洗后的结构化结果存 `data/clean/`，两者分离，可追溯。
5. **失败处理**：单通路失败不阻塞主流程，降级到备选通路并在输出的 `notes` 里记录。

## 五、信源清单（本次实战沉淀）

| 通路 | 具体信源 | 级别 |
|---|---|---|
| 官媒/政府 | 上观新闻、静安官媒、各区商务委、虹口区政府网 | S |
| 行业媒体 | 搜狐吃喝、网易财经、新浪、澎湃、界面 | A |
| KOL | B站"特厨隋坡"、微博@卡米camille、公众号"食在十三""周末做啥""槟客文化" | A |
| 榜单 | 米其林指南官网、黑珍珠（美团公告）、大众点评必吃榜 | S |
| UGC | 大众点评、小红书、携程/ Trip.com 游记 | B |
| 聚合软文 | 百家号种草文 | C（仅线索） |

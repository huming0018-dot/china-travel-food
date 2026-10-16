# food-radar 工具调用流程与技术规范

> 依赖说明：本仓库（GitHub）**不包含** `tools/` 下的第三方克隆仓库（体积大且有各自许可），请按第 3 节命令自行克隆。
> `wechat-article-search` 为同机独立 skill（`~/.codebuddy/skills/wechat-article-search/`），不在本仓库内，需另行安装。

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

### Agent-Reach（推荐先装）
```bash
# 对 agent 说一句话即可安装：
# 帮我安装 Agent Reach：https://raw.githubusercontent.com/Panniantong/agent-reach/main/docs/install.md
# 本 skill 已浅克隆至 tools/agent-reach，可按其 docs/install.md 完成安装
```

### MediaCrawler
```bash
cd tools/media-crawler
pip install -r requirements.txt
playwright install
# 首次使用需用 Playwright 登录各平台保存登录态（cookie），详见其 README
```

### 点评爬虫（竞品全量盘点用）
```bash
git clone https://github.com/wongben/dianping-crawler.git   # Java，全上海餐饮店铺
```

### 环境依赖检查（每次开工先跑）
```bash
node -v 2>/dev/null || echo "需要 Node（wechat-article-search 依赖）"
python3 -v 2>/dev/null || echo "需要 Python3（MediaCrawler 依赖）"
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

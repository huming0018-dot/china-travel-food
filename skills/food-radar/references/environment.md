# food-radar 环境依赖与安装状态（实测基线）

> 实测日期：2026-10-16｜ 主机：macOS (darwin)｜ 校验命令：`bash scripts/preflight.sh`

本文件记录**实际验证过**的工具状态，与 `toolchain.md` 的"应然"分开，避免把"已克隆"误当"可用"。

## 一、总览

| 组件 | 路径 | 状态 | 阻塞项 |
|---|---|---|---|
| MediaCrawler | `tools/media-crawler` | ✅ 可运行 | 需人工登录保存 cookie |
| Agent-Reach | `/Users/deuce/.local/bin/agent-reach` | ⚠️ 部分可用 4/16 | 小红书需手动导 Cookie |
| dianping-crawler | `tools/dianping-crawler` | ❌ 不可运行 | 无 Java / 无 Maven |
| wechat-article-search | `~/.codebuddy/skills/wechat-article-search` | ❌ 不可运行 | 无 Node |
| gh CLI | — | ❌ 未安装 | 推送改用 SSH |

## 二、运行时基线

| 项| 值 | 说明 |
|---|---|---|
| 系统 python3 | 3.9.6 | **不满足** MediaCrawler 的 `requires-python>=3.11`，勿直接用它建 venv |
| 可用 python | `/Users/deuce/.local/bin/python3.12` (3.12.15) | MediaCrawler 实际使用的解释器 |
| uv | `/Users/deuce/.local/bin/uv` | 建venv / 装包统一走 uv |
| node | 未安装 | wechat-article-search 依赖 |
| PATH 提示 | 需 `export PATH="/Users/deuce/.local/bin:$PATH"` | uv 与 python3.12 都在此目录 |

## 三、MediaCrawler（✅ 已装好）

```bash
export PATH="/Users/deuce/.local/bin:$PATH"
cd tools/media-crawler
uv venv --python 3.12 .venv                                  # 必须 3.11+，勿用系统 3.9
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/playwright install chromium
```

已验证：`.venv/bin/python main.py --help` 正常输出。
支持平台：`xhs`(小红书) `dy`(抖音) `ks`(快手) `bili`(B站) `wb`(微博) `tieba`(贴吧) `zhihu`(知乎)。
浏览器已落地：`~/Library/Caches/ms-playwright/` 下 chromium-1248、chromium_headless_shell-1248、ffmpeg-1013。

**仍需人工一步**：各平台扫码登录保存登录态（cookie），否则抓取会被登录墙拦截。
cookie 只存本地，**不进仓库、不进交付物**。

## 四、Agent-Reach（⚠️ 4/16 通路）

```bash
export PATH="/Users/deuce/.local/bin:$PATH"
cd tools/agent-reach && uv tool install.        # 产出 ~/.local/bin/agent-reach
agent-reach doctor                               # 通路自检
agent-reach skill --install                      # 注册 skill 到 ~/.agents/skills/agent-reach
```

实测可用：B站搜索（bili-cli）、任意网页（Jina Reader `https://r.jina.ai/URL`）、V2EX、RSS/Atom。

**未解锁及原因**：

| 通路 | 原因 | 解决方式 |
|---|---|---|
| 小红书 | `configure --from-browser` 不支持，需 Cookie-Editor 导出 | 浏览器装 Cookie-Editor 扩展导出 `xhs` cookie → `agent-reach configure xhs-cookies "<json>"` |
| 全网语义搜索 | 缺 mcporter + Exa MCP | 需先装 Node，再 `npm i -g mcporter` |
| YouTube | yt-dlp 未在全局 PATH | `uv tool install yt-dlp` |
| GitHub | 无 gh CLI | 本仓库推送走 SSH（`~/.ssh/ctfs_github`），无需 gh |

> 抖音**不在** agent-reach 覆盖范围，须走 MediaCrawler 的 `dy` 平台。

## 五、dianping-crawler（❌ 被Java 阻塞）

```bash
git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler
```

已克隆（`pom.xml` + `src/`，Java/Maven 工程），但本机**无 Java 运行时、无 Maven**，当前无法构建。
在装好 JDK 前，**点评数据走降级方案**：`agent-browser` / `playwright-cli` 打开店铺页 + `web_search` 取 UGC 摘要。
降级取到的评分/人均必须按 `field-spec.md` 标注来源与抓取时间。

## 六、开工自检

```bash
bash scripts/preflight.sh
```

自检不通过时，按本文件对应章节补齐，**不要**在依赖缺失时静默降级而不告知用户。
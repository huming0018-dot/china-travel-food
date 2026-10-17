# food-radar 环境依赖与安装状态（实测基线）

> 实测日期：2026-10-17 ｜ 主机：macOS (darwin) ｜ 校验命令：`bash scripts/preflight.sh`
>
> 本文件记录**实际跑通过**的工具状态。凡与"应然"不符的，以本文件为准。

## 一、总览（2026-10-17 实测）

| 组件 | 状态 | 说明 |
|---|---|---|
| **MediaCrawler / 小红书** | ✅ **已跑通** | 扫码登录 + 采集 40 篇笔记 / 133 条评论，登录态已持久化 |
| **MediaCrawler / 抖音** | 🔄 扫码登录中 | 与小红书登录态不通用，需各扫一次 |
| **agent-reach** | ⚠️ 4/16 通路 | B站 / Jina Reader / V2EX / RSS 可用；小红书需手动导 Cookie；**不含抖音** |
| **dianping-crawler** | ❌ **已失效** | 依赖接口返回 403，见第五节 |
| **wechat-article-search** | ❌ 不可运行 | 无 Node |
| **JDK 21 / Maven 3.9.16** | ✅ 已装 | `/Users/deuce/CodeBuddy/Claw/toolchain/`（供 Java 类工具备用） |

## 二、运行时基线

| 项 | 值 | 说明 |
|---|---|---|
| 系统 python3 | 3.9.6 | **不满足** MediaCrawler 的 `requires-python>=3.11`，勿直接用它建 venv |
| 可用 python | `/Users/deuce/.local/bin/python3.12` (3.12.15) | MediaCrawler 实际使用的解释器 |
| uv | `/Users/deuce/.local/bin/uv` 0.12.23 | 建 venv / 装包统一走 uv |
| node | 未安装 | wechat-article-search 依赖 |
| JDK | `toolchain/jdk-21.0.12.1+1` | Temurin 21 LTS，2026-10-17 装 |
| Maven | `toolchain/apache-maven-3.9.16` | 2026-10-17 装 |
| PATH 提示 | `export PATH="/Users/deuce/.local/bin:$PATH"` | uv 与 python3.12 都在此目录 |

> Maven 官方 dlcdn 的 `3.9.9` 路径**不存在**（404），当前可用版本为 `3.9.16` / `3.10.0`。

## 三、MediaCrawler（✅ 实测跑通）

```bash
export PATH="/Users/deuce/.local/bin:$PATH"
cd tools/media-crawler
uv venv --python 3.12 .venv                    # 必须 3.11+
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/playwright install chromium
```

支持平台：`xhs` `dy` `ks` `bili` `wb` `tieba` `zhihu`。

### 3.1 登录：扫码，不是 Cookie 也不是 CDP

配置项 `LOGIN_TYPE = "qrcode"`、`SAVE_LOGIN_STATE = True`。
运行后浏览器弹出二维码 → 手机 App 扫 → 登录态写入 `browser_data/<平台>_user_data_dir/`，**后续运行直接复用，不再弹码**。

**登录态按平台隔离**：`xhs` 和 `dy` 各需各扫一次。cookie 过期（通常一两个月）才需重扫。

### 3.2 CDP 模式：本机不可用，不要在这上面浪费时间

配置里 `ENABLE_CDP_MODE` / `CDP_CONNECT_EXISTING` 是为复用 Chrome 设计的，但本机**三次尝试全部失败**：
- `chrome://inspect/#remote-debugging` 开启后，端口 9222 从未监听
- `~/Library/Support/Google/Chrome/DevToolsLocalState` 从未生成 → 开关实际未写入
- 根因：Chrome 155 采用 **App-Bound Encryption**，且 136+ 对默认 profile 限制 `--remote-debugging-port`

**已改为标准模式（独立浏览器 + 扫码），实测稳定。`config/base_config.py` 中 `ENABLE_CDP_MODE = False`。**

### 3.3 从 Chrome 提取 cookie：不可行

`agent-reach` 要求用 Cookie-Editor 手动导出，原因同上（App-Bound Encryption）。
且 `web_session` 是 **HttpOnly**，控制台 `document.cookie` 取不到。
**结论：不要尝试自动化提取，直接扫码。**

### 3.4 搜索关键词配置

`config/base_config.py` → `KEYWORDS`（英文逗号分隔）。
本机当前设为 `"当霁,四季江南菜"`，**换任务需改这里**。

## 四、Agent-Reach（⚠️ 4/16 通路）

```bash
cd tools/agent-reach && uv tool install .
agent-reach doctor
agent-reach skill --install
```

可用：B站搜索（bili-cli）、任意网页（Jina Reader `https://r.jina.ai/URL`）、V2EX、RSS/Atom。

**价值定位**：MediaCrawler 跑批量抓取，agent-reach 用于**零成本补搜**与原文抓取（Jina Reader 核对发布日期很好用）。
**不在 agent-reach 覆盖范围**：抖音。

## 五、大众点评：原爬虫已失效（2026-10-17 实证）

```bash
git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler
```

**仓库已克隆，但不可用，原因有两层：**

**（1）技术栈过时**：Java 8 + Spring Boot 1.5.2（2017 年项目），需 JDK 8；本机 JDK 21 未必兼容。

**（2）致命问题——依赖接口已关闭**：
项目裸调 `mapi.dianping.com/searchshop.json`（无签名、无 token、无 cookie）。实测：

```
$ curl "http://mapi.dianping.com/searchshop.json?...&cityid=1&categoryid=147..."
<html><head><title>403 Forbidden</title></head>...openresty</html>
[HTTP 403]

# 加浏览器 UA 仍为 403
```

**结论：编译成功也只会立即报错。已放弃该方案。**

**替代路径**（2026-10-17 起）：复用 MediaCrawler 的 venv + Playwright chromium，以真实浏览器访问点评页面。
注意：大众点评对自动化访问的风控强于小红书，评分/人均等精确数值必须按 `field-spec.md` 标注来源与抓取时间，拿不到填 `null`，**禁止估算**。

## 六、开工自检

```bash
bash scripts/preflight.sh
```

自检不通过时按本文件对应章节补齐，**不要在依赖缺失时静默降级而不告知用户**。
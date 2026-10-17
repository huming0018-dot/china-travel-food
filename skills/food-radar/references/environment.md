# food-radar 环境依赖与安装状态（实测基线）

> 实测日期：2026-10-17 ｜ 主机：macOS (darwin) ｜ 校验命令：`bash scripts/preflight.sh`
>
> 本文件记录**实际跑通过**的工具状态。凡与"应然"不符的，以本文件为准。

## 一、总览（2026-10-17 实测）

| 组件 | 状态 | 说明 |
|---|---|---|
| **MediaCrawler / 小红书** | ✅ **已跑通** | 扫码登录 + 采集 40 篇笔记 / 133 条评论，登录态持久化 |
| **MediaCrawler / 抖音** | ✅ **已跑通** | **需 Node** 生成签名；采集 69 条，总互动 92,910 |
| **大众点评（Playwright 直采）** | ✅ **已跑通** | `scripts/dianping_fetch.py`；评分/人均/推荐菜/团购全拿到 |
| **dianping-crawler** | ❌ 已失效 | 依赖接口 403，停止投入，仅留档 |
| **agent-reach** | ⚠️ 4/16 通路 | B站 / Jina Reader / V2EX / RSS；小红书需手动导 Cookie；**不含抖音** |
| **wechat-article-search** | ✅ 已可运行 | Node 已装（2026-10-17） |
| **JDK 21 / Maven 3.9.16** | ✅ 已装 | `/Users/deuce/CodeBuddy/Claw/toolchain/`（备用） |
| **Node 24.22.0** | ✅ 已装 | 同上；**抖音签名的必需依赖** |

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

### 3.5 抖音必须装 Node，装 Java 无效

抖音抓取需生成签名，走 `execjs`。实测报错链：

```
execjs._exceptions.ProcessExitedWithNonZeroStatus:
  The operation couldn't be completed. Unable to locate a Java Runtime
```

**极易误判为"缺 Java"，实际装 JDK 21 依然失败**。真实原因：

> `execjs` 依赖 **Nashorn**，而 **JDK 15+ 已移除 Nashorn**。Java 运行时在这条链路上根本不可用。

**正解：装 Node**（execjs 原生支持，且顺带激活 `wechat-article-search`）：

```bash
curl -sL -o node.tar.gz https://nodejs.org/dist/v24.22.0/node-v24.22.0-darwin-arm64.tar.gz
tar xzf node.tar.gz
export PATH="/Users/deuce/CodeBuddy/Claw/toolchain/node-v24.22.0-darwin-arm64/bin:$PATH"
node -v# v24.22.0

# 验证 execjs 已走 Node
python -c "import execjs; print(execjs.eval('1+2'))"   # 应输出 3
```

>小红书不需要这一步，仅抖音需要。

## 四、Agent-Reach（⚠️ 4/16 通路）

```bash
cd tools/agent-reach && uv tool install .
agent-reach doctor
agent-reach skill --install
```

可用：B站搜索（bili-cli）、任意网页（Jina Reader `https://r.jina.ai/URL`）、V2EX、RSS/Atom。

**价值定位**：MediaCrawler 跑批量抓取，agent-reach 用于**零成本补搜**与原文抓取（Jina Reader 核对发布日期很好用）。
**不在 agent-reach 覆盖范围**：抖音。

## 五、大众点评（✅ 2026-10-17 直采打通）

### 5.1 原爬虫已失效（留档，勿再尝试）

```bash
git clone --depth 1 https://github.com/wongben/dianping-crawler.git tools/dianping-crawler
```

该2017 年项目（Java 8 + Spring Boot 1.5.2）裸调 `mapi.dianping.com/searchshop.json`（无签名/token/cookie），实测：

```
$ curl "http://mapi.dianping.com/searchshop.json?...&cityid=1&categoryid=147..."
<html><head><title>403 Forbidden</title></head>...openresty</html>
[HTTP 403]
# 加浏览器 UA 仍为 403
```

**编译成功也只会立即报错。**

### 5.2 可用方案：Playwright 直采

```bash
# 依赖 playwright（复用 media-crawler 的 venv 即可）
cd tools/media-crawler && uv pip install --python .venv/bin/python playwright

# 使用
bash scripts/dianping_fetch.py --keyword 当霁 --detail --out dp.json
```

**四个必须条件**：
1. `headless=False` — 无头模式会被识别，返回no-result 模板
2. **持久化登录态** — `browser_data/dianping_user_data_dir/`，需人工登录一次（手机号+验证码）
3. **等待 9-11 秒** — 结果是懒加载
4. **选择器用 `a[href*='/shop/']`** — `div.shop-wrap` 是失效的历史类名

**两个致命误判点**（已在脚本注释中标注）：
- `.no-result` 元素（「商户没有被收录？添加商户」）**永远存在于 DOM**，不能用它判断无结果
- 详情页首屏信息**不在 `innerText` 前段**（实测全文仅 542 字符），需配合截图或正则兜底

**实测产出示例**（当霁·四季江南菜）：
```
shop_id H4GpiV5cA7moLb3r | 4.7分 | 98评价 | 人均¥388
口味4.7/环境4.7/服务4.7| 虹口区江浙菜新店榜·第1名
推荐菜37道（带推荐人数）| 团购双人宴¥998 / 六人宴¥2980
```

### 5.3 移动端不可用

`m.dianping.com` 搜索未登录静默跳 `/error/error_page`，**且标题仍是「大众点评网」**，靠标题判断会误判为成功。必须检测最终 URL。

## 六、开工自检

```bash
bash scripts/preflight.sh
```

自检不通过时按本文件对应章节补齐，**不要在依赖缺失时静默降级而不告知用户**。
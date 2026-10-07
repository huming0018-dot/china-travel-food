# 众包美食家扩展 E2E 测试 harness

当前版本为 v4。先在 `app/` 执行 `npm ci`，再在本目录执行 `npm test`，运行 `crowd_extension/tests/` 的当前验证。设置 `CROWD_TEST_TOOLS`（含 Playwright/@electric-sql/pglite）可增加真实浏览器 DOM 和隔离 PostgreSQL 诊断迁移检查；`CROWD_TEST_DATABASE_URL` 只能指向全新可丢弃数据库，`CROWD_PORTAL_TEST_ORIGIN` 用于已启动的本地网站。数据库/浏览器未运行时会明确跳过，不算通过；实机验收另行进行。

Puppeteer：本目录 `npm ci --ignore-scripts` 安装锁定的 puppeteer-core，再启动本地生产网站，执行 `CROWD_CHROMIUM=/完整/Chromium CROWD_PORTAL_TEST_ORIGIN=http://127.0.0.1:44127 npm run test:puppeteer`。使用独立临时浏览器 profile，点击真实入口和共享客户端界面；API、小红书网页及原生系统桥均为固定响应/模拟实现，调度时钟加速，不连接真实平台或写生产库。报告和截图默认在 `results/puppeteer-v4/`。可用 `CROWD_PUPPETEER_TOOLS` 指向独立工具目录、`CROWD_PUPPETEER_OUTPUT` 指定报告目录。

**下文及旧 run-*.js 为 v3 历史资料，依赖已退役的运行时，不能作为 v4 验收。**

对 MV3 插件做真实运行测试：chrome-for-testing 加载未打包扩展，CDP Fetch 域拦截 SW 的全部 Supabase RPC，页面层拦截小红书请求并回伪搜索页。**绝不触碰用户 Chrome profile，绝不真实请求生产 Supabase / 小红书**。

## 环境前提

- node 18+
- chrome-for-testing（品牌版 Google Chrome 会忽略 `--load-extension`，不能用）：
  ```bash
  npx puppeteer browsers install chrome
  ```
  默认路径 `~/.cache/puppeteer/chrome/mac_arm-*/chrome-mac-arm64/Google Chrome for Testing.app/...`，也可用 `CHROME_PATH` 环境变量指定。

## 运行

```bash
cd test-harness
npm install          # 首次，安装 puppeteer-core
node run-all.js      # 主场景 S0/A-E/F/G：回传、配额、退避、死信、任务领取、竞态、门禁
node run-extra.js    # 边界 X1-X13：null 响应、队列水位、互斥、回流 stall、UTC 配额日界等
node run-extra2.js   # X14 条目级永久 verdict 探测 + X15 onboarding 注册流
node run-fixes.js    # v3.4.6 修复回归 R1-R11（merge/看门狗/词表/重试上限/风控/同意流等）
node run-v347.js     # v3.4.7 独立验证 V1-V7（同意门解耦/401熔断/F14预检/last_sid去重/alarm不饿死/warmup NaN/done封顶）
```

退出码：主套件有 FAIL 时为 1。结果落在 `results/*.json`（SW console 全量、未捕获异常、RPC 调用流水、泄漏审计）。

## 结构

| 文件 | 作用 |
| --- | --- |
| `harness.js` | 启动浏览器（临时 user-data-dir）、双层 RPC mock、伪 xhs 页面、日志/异常/泄漏采集 |
| `run-all.js` | 主场景（回传/配额/退避/死信/领取/竞态/门禁） |
| `run-extra.js` / `run-extra2.js` | 边界路径补测 |
| `results/` | 每次运行的 JSON 结果 |

## 拦截机制

- **SW 侧**：对 service worker target 开 CDP `Fetch.enable`，按 `/rest/v1/rpc/<fn>` 路由到 `mockRoutes`（支持 `bodyFn(reqBody)` 动态响应、`status` 非 200、`fail: true` 模拟断网、`delayMs` 模拟慢 RPC）。探针失败时自动降级为 SW 内 fetch 包装。
- **页面侧**：`browser.on('targetcreated')` 给每个 page 挂 `setRequestInterception`；xhs 搜索页回内置伪 DOM（4 张 note 卡片），其余 xhs/supabase 一律拦截。`chrome.tabs.create` 在 SW 内被运行时包装（先建 about:blank、600ms 后再导航）以消除"拦截器未挂上请求已发出"的竞态。
- **泄漏审计**：任何走到真实网络的 xhs/supabase 回包都会记入 `state.leaks` 并在汇总中打印。

## 已知环境坑（排错用）

1. Chrome ≥137 的 headless 不再加载扩展 → 用 headed（默认）。会弹一个独立测试窗口，属正常。
2. 品牌版 Google Chrome 忽略 `--load-extension` → 必须用 chrome-for-testing。
3. `--host-resolver-rules` 在本机不生效，不能当拦截层；只作兜底。
4. 本机 `ExtensionInstallForcelist` 企业策略会被测试 profile 继承（策略更新请求已被拦截，无副作用）。
5. 凌晨 0–7 点跑采集场景会被插件的时段画像闸（circadian weight<0.05）拦下——这是设计行为；测试用运行时覆写 `safety.isCircadianAllowed` 等门控获得确定性。
6. 测试用 participant_id 必须匹配 `/^P-[A-Z0-9]{6,12}$/`（不能含 `-`），harness 用 `P-E2E0001`。

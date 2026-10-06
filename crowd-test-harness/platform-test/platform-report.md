# crowd-pages 跨平台真实页面测试报告

- 时间：2026-10-06 凌晨（本机 CST）
- 对象：**线上页面** `https://huming0018-dot.github.io/crowd-pages/`（index / submit / install-mobile）。开测前已 curl 拉取线上三页并与本地镜像 `pages-repo/` 逐字节比对**完全一致**——本报告全部结论基于线上版本。
- 方法：chrome-for-testing 154 + puppeteer-core；每平台独立 browser context；按矩阵注入真实 UA/视口/DPR/触摸；supabase RPC 全部请求拦截 mock（含 OPTIONS 预检），xhs 系域名全部拦截；github.io 静态资源真实加载。
- 总账：**174 项断言，171 通过，0 失败，3 项 UNVERIFIED**（同一个原因：本机网络把 supabase.co 过滤到 fake-ip 198.18.0.30 且 TLS 被切断，zip 的 HEAD 验证打不出去——这是本机网络状态，不是页面缺陷。同时也正因如此，"零真实生产请求"有双重保险）。
- runner：`platform-test/run-platform.js`；原始数据：`platform-report-data.json`；截图 60 张：`shots/<platform>/`。

## A. index.html 路由（每平台）

| 平台 | 实际结果 | 预期 | 结论 | 证据 |
|---|---|---|---|---|
| Android/Pixel 7 | "检测到：安卓手机"，主 CTA=开始参与（submit.html）+ Firefox xpi 次按钮；1.5s 内无 .command/.bat 请求 | 安卓→网页版主路径 | ✅ 符合，不错误触发下载 | shots/android/A-index.png |
| HarmonyOS 4 | 同上（UA 含 "Android 12" → 走安卓分支） | 安卓分支 | ✅ 符合 | shots/hm4/A-index.png |
| HarmonyOS NEXT | "未识别的设备"，给"网页版直接参与"+"查看全部安装方式"，无自动下载 | 任务点名观察项 | ✅ 落"未识别设备"——**NEXT 的 UA 去掉了 android 关键字，路由不认识它**；网页版可用，但无任何针对华为/鸿蒙的引导 | shots/hmnext/A-index.png |
| macOS | "检测到：Mac 电脑"，600ms 后自动触发 crowd-install-mac.command 下载（拦截记录证实） | Mac→Mac 安装器（自动下载是该设备的预期行为） | ✅ 符合 | shots/macos/A-index.png |
| Windows | "检测到：Windows 电脑"，自动触发 crowd-install-win.bat | 同上 | ✅ 符合 | shots/windows/A-index.png |
| Linux | "未识别的设备"，兜底"网页版直接参与"+"查看全部安装方式"，无自动下载 | 如实记录 | ✅ 落兜底分支，**可经网页版参与**（见 B 组 Linux 全链路通过） | shots/linux/A-index.png |

iPad 误判回归点：M3 修复（mac UA + maxTouchPoints>1 → iOS）在代码中在位（index.html:43-44）；本矩阵无 iPad 行，未直接回归。

**新发现（低-中，通用问题）**：index.html 安卓分支的次按钮仍是指向 `crowd-extension-v3.4.1-firefox-signed.xpi` 的"装 Firefox 后一键装插件"，而 install-mobile.html 明确写着"Firefox 通道升级中，暂不可用（旧版有启动 bug）"。**两个页面对 Firefox 通道的说法互相矛盾**，且 index 还链着 v3.4.1 旧版 xpi。建议 index 安卓分支的次按钮改指 install-mobile.html 或直接摘掉。

## B. submit.html 完整链路（6 平台全过）

步骤：加载（ping 探活 mock 200）→ 点「我要加入」（mock 注册 P-PLT001）→ 编号 pill 出现且写入 localStorage → 自动领任务（mock crowd_next_target：测试门店 #99，0/5）→ 粘贴笔记链接 → 900ms 内识别成功 → 手填标题 → 提交。

| 提交变体 | 结果（6 平台一致） | 证据 |
|---|---|---|
| accepted | ✅ 绿色 ok-note"已收录！测试门店 1/5"，字段清空，自动领下一目标 | shots/&lt;pf&gt;/B-accepted.png |
| duplicate | ✅ 绿色"这条已收录过（去重），不重复计酬" | shots/&lt;pf&gt;/B-duplicate.png |
| rejected（item_url_invalid） | ✅ 红色 err-note"❌ 链接格式不对（请复制小红书笔记的完整网址）"，**保留已填内容**便于改后重试，不换目标 | shots/&lt;pf&gt;/B-rejected.png |
| quota_exceeded | ✅ 红色"未入库：今日配额已满，明天再试" | console/数据见 platform-report-data.json |

6 个平台该链路逐项一致通过（注册/领任务/识别/四种回执展示/零 JS 异常/零泄漏）。**通用性结论：提交链路无平台差异。**

## C. 压力变体（3 个移动平台）

**C1 删除 crypto.randomUUID**（evaluateOnNewDocument 里 defineProperty 置 undefined）：全链路照样走完，提交的 submission_id 兜底手造 UUID v4 格式合法（正则验证通过），不再静默死。三平台一致 ✅。

**C2 localStorage 抛 SecurityError**：页面 JS 不崩；`storageBanner`（"禁用了本地存储…编号会丢失"）正常亮出（shots/&lt;pf&gt;/C2-storage-banner.png）；注册→领任务→提交 accepted 全流程走通（safeStorage 内存兜底）；**刷新后编号表单重新出现**（内存兜底确实只在当次会话有效，banner 文案属实）。三平台一致 ✅。

## D. install-mobile.html（3 个移动平台）

- Firefox 卡片 = "🦊 Firefox 安卓版（升级中，暂不可用）"占位说明，**卡内无 `<a>` 链接**（无死链）✅
- 狐猴卡片下载链接指向 `crowd-extension-v3.4.6.zip` ✅
- zip 的 HEAD 验证：**UNVERIFIED**——本机当前网络把 supabase.co 劫持到 198.18.0.30（fake-ip）且 TLS 握手被切（curl/Node/DoH 直连 1.1.1.1 同样失败），打不出真实 HEAD。这**不是页面缺陷**；链接格式与 bucket 命名规范一致，但文件存在性本轮未能证实，需要在网络正常的机器上补验：`curl -I https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v3.4.6.zip`

## 汇总对比表

| 维度 | 结论 |
|---|---|
| 平台特有问题 | ① HarmonyOS NEXT 落"未识别设备"（UA 去 android 化导致，预期内但无鸿蒙专属引导）；② Linux 无专属安装器（落兜底） |
| 通用问题 | index.html 安卓分支的 Firefox xpi 次按钮与 install-mobile 的"Firefox 通道升级中"互相矛盾，且链的是旧版 v3.4.1 xpi |
| 修复验证（今天中午的修复版） | H1 UUID 兜底 ✅ 全平台生效；H2 safeStorage 降级+banner ✅；H4 标题预检（链路上手填标题才放行）✅；H5 条目级 gate 分流（rejected 不染绿）✅；M3 iPad 识别代码在位（未回归）；Firefox 卡片占位 ✅ |
| 零生产请求 | 成立：所有 supabase RPC/storage、xhs 系请求 100% 拦截在浏览器内，无任何 continue 到真实网络 |

## Linux 的明确回答

Linux 桌面 Chrome 打开入口页 → 路由落"未识别的设备"兜底分支，展示「🚀 网页版直接参与」（submit.html）和「查看全部安装方式」（install.html），**不触发任何自动下载**。**Linux 可以作参与平台，但只能走网页版手动提交**（B 组 Linux 全链路实测通过）；没有、也不识别任何 Linux 原生安装器——因为 index.html 的路由表只有 android/iOS/mac/win 四个分支，Linux UA（X11）不匹配任何一条。如果要给 Linux 用户扩展安装路径，需要单独加分支（Chrome 扩展在 Linux 桌面完全可装，install.html 里有通用安装说明页可链）。

## 本轮模拟的局限（如实）

1. **单内核**：全部是 Chromium 154 渲染。华为浏览器的真实内核定制（字体/支付/WebView 差异）、iOS WebKit（Safari 内核，含 PWA 添加到主屏幕的真实行为）都不在覆盖范围——iPhone 分支本轮完全没测。
2. **UA/视口级仿真**：触摸是 `hasTouch` 标志仿真，不是真触摸事件链；DPR 影响截图但不改变布局断点。
3. **--disable-web-security**：Chromium 的请求拦截合成响应过不了 CORS 预检（拦截层预检不进 preflight 缓存），测试浏览器关闭了安全检查。因此本轮**没有验证**线上 supabase 的 CORS 头是否正确（生产环境 supabase 自带正确 CORS 头，此前网页版已有真实用户使用记录，风险低）。
4. **mock 服务端**：所有 RPC 响应是 mock，真实服务端行为（延迟、真实 quota、真实 task 分配）不在本轮范围。
5. zip 文件存在性 UNVERIFIED（本机网络过滤所致，需在网络正常环境补一刀 curl）。

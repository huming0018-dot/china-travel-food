# v3.4.8 → v4 修复验证 · 2026-10-06

基线：`cd10128`，包含 `1b4006b`。分支：`fix/crowd-distribution-v348`。Ponytail 按项目安装，复用此前验证的 v4 实现；保留现有服务器健康检查、回流监控修复及 v3 数据/账本。

交付前同步主分支新增的 `28f65d8`、`d61e0e1`。DEPLOY 保留 Pages 更新通道的历史故障记录；旧策略安装器、v3 自动升级清单和发布脚本被本次 v4 安装/验收流程替代，未重新引入已退役的策略写入路径。

## Puppeteer 补充验证

使用 Puppeteer Core 23.11.1 / Chromium 151，点击本地生产邀请入口及实际共享 controller/native-runtime 界面。首次执行发现 CrowdAPI 将浏览器 fetch 保存为实例方法后使用错误的 receiver，真实浏览器报 Illegal invocation，邀请接入失败；先前接口模拟未覆盖这个行为。已改为保留全局 fetch 调用上下文，并由真实浏览器回归。

10 个场景通过：短信邀请/安卓识别、未开放苹果渠道/缺邀请、桌面下载与坏摘要拒绝、未就绪发布入口、显式同意、不在注册中断后自动启动、同意后启动实际运行时、搜索/详情/字段/丢失回执保留、重启稳定 UUID 重试、验证码停批次与用户停止。核心测试重新执行通过；客户端安装包随共享 API 修复重新生成。

API 和小红书页面使用固定响应；系统桥模拟持久化/调度/网页操作，时钟加速。没有验证真实平台、实际操作系统原生桥、安装/锁屏或手机后台。`npm run test:puppeteer --prefix crowd-test-harness` 为复现入口，详细环境见 harness README。报告不记录凭据。

## 已执行

- 复现旧构建器缺失 background.js；新源码构建、内部包生成和脚本语法检查通过。
- `npm test --prefix crowd-test-harness`：状态机、Chrome/Firefox 后台适配、邀请 API、原生桥、证据导出及发布检查通过。旧 v3 测试保留作历史资料。
- 同一测试入口连接全新 PostgreSQL 17：真实迁移、权限、并发领取/续租、稳定回执、全局去重、严格核验、99/100 条奖励边界、付款不可改写及邀请名额并发/过期/撤销通过。
- Chromium 真实 DOM：自动搜索、访问详情、停留/滚动、标准/非标字段及回传通过。页面与 API 使用本地固定响应，未访问真实小红书。
- 本地生产网站浏览器流程：安卓识别、短信邀请、安装链接、桌面自动分片下载与摘要验证、校验失败和未开放渠道通过。
- Next.js 生产构建及 TypeScript 检查通过；依赖复用与本分支 package-lock 完全一致的已有安装树。
- Android SDK35/Java21 编译 APK；v2/v3 签名验证通过。Windows x64 用官方 SHA256 校验的 Electron runtime 打包通过。原生项目与共享资源随构建分发。
- 发布器验证包摘要、当前公开配置、解析器/界面源码与原生主程序源文件摘要；任何相关源码变动后旧包不能继续发布。默认检查不写生产、不生成假邀请。

## 验证边界

SQL 使用临时本地数据库，没有执行生产迁移。网站没有发布到生产，也没有可开工的生产邀请。未连接 Windows/Mac/Android/iOS/Harmony 实机；真实小红书登录、页面变化、锁屏/后台与系统协议关联仍待验收。

Android 产物为内部 debug 签名。Apple/Harmony 编译、发布签名和正式分发仍需对应环境/身份。当前管理员策略禁止 Chromium 加载未打包扩展，因此扩展后台适配由源码 API 检查验证；未绕过该策略，也未将其算作实机通过。

## 复现入口

安装 `app/` 的锁定依赖，运行 `npm test --prefix crowd-test-harness`。增加浏览器检查需 `CROWD_TEST_TOOLS` 指向含 Playwright 的开发工具目录；`CROWD_CHROMIUM` 指向完整 Chromium。`CROWD_PORTAL_TEST_ORIGIN` 指向已启动的本地生产网站。

数据库检查另需 pg，设置 `CROWD_TEST_DATABASE_URL` 指向**全新可丢弃库**；测试会拒绝已有 auth/crowd schema。示例工具版本：pg 8.23.1、Playwright 1.63.0。未设置变量时对应检查跳过，不能计作通过。

运行 `python3 cloud/crowd_build.py --dry` 检查公开配置，实际生成包用 `python3 cloud/crowd_build.py`。SDK/runtime/产物、私钥与本机会话不提交到源码仓库。

部署步骤和各端边界见 DEPLOY.md / README.md。先完成试点验收并提供可信部署环境，再用发布者脚本执行迁移/发布；参与者只收到链接或二维码。回滚停止 v4 客户端与调度，保留证据和已付账本。

> **2026-10-07 Mac 后台与唤醒续作（当前）**：私有轻量包约 31 KB。首次同意并启动后后台领取、搜索、采集和回传；浏览器启动/worker 加载自动补建周期调度，唤醒后续做未停止的任务。没有普通窗口时创建最小化、不主动抢焦点的工作窗口；睡眠或浏览器退出期间不执行。手动停止、退出、登录失效、验证码和限流保持暂停。恢复保留冷却、配额和待回传证据；重启或长调度中断时重新打开页面并计时。核心恢复检查和 12 项 Puppeteer 固定响应场景通过，真实 Mac 睡眠/唤醒和平台回传仍待验收。更新覆盖原插件目录后刷新，不先卸载。crowd-access v3 已上线，正式渠道和批量邀请仍关闭；历史大包说明不适用于本次实验。当前指引见 crowd_extension/DISTRIBUTION.md 顶部。

> **2026-10-07 正式网页已发布**：PR #1 已合并，Vercel 正式部署 `3bBqSP5GeS7sWM88HSjzdnnw1oSF` / 提交 `adce116` 为 Ready。正式域名 `https://app-lyart-eta-22.vercel.app` 的管理页和 manifest 实际返回 200；匿名回收 403、发布身份查看/导出 200。当前安装渠道为空，邀请返回 release_not_ready，尚不能声明可开工分发。三条真实试点任务 open，参与者/回传为 0；设备问题等待用户回复，Docker 入库流水线未启用。以下历史快照不能代替这一状态。

# v3.4.8 → v4 修复验证 · 2026-10-06

基线：`cd10128`，包含 `1b4006b`。分支：`fix/crowd-distribution-v348`。Ponytail 按项目安装，复用此前验证的 v4 实现；保留现有服务器健康检查、回流监控修复及 v3 数据/账本。

交付前同步主分支新增的 `28f65d8`、`d61e0e1`。DEPLOY 保留 Pages 更新通道的历史故障记录；旧策略安装器、v3 自动升级清单和发布脚本被本次 v4 安装/验收流程替代，未重新引入已退役的策略写入路径。

## Puppeteer 补充验证

使用 Puppeteer Core 23.11.1 / Chromium 151，点击本地生产邀请入口及实际共享 controller/native-runtime 界面。首次执行发现 CrowdAPI 将浏览器 fetch 保存为实例方法后使用错误的 receiver，真实浏览器报 Illegal invocation，邀请接入失败；先前接口模拟未覆盖这个行为。已改为保留全局 fetch 调用上下文，并由真实浏览器回归。

12 个场景通过：短信邀请/安卓识别、未开放苹果渠道/缺邀请、Windows EXE 分片下载与坏摘要拒绝、未就绪发布入口、整条短信与复制权限拒绝后的自动选中、内置浏览器复制系统浏览器入口、显式同意、不在注册中断后自动启动、同意后启动实际运行时、搜索/详情/字段/丢失回执保留、重启稳定 UUID 重试、验证码停批次与用户停止。核心测试重新执行通过；客户端安装包随共享 API 修复重新生成。

API 和小红书页面使用固定响应；系统桥模拟持久化/调度/网页操作，时钟加速。没有验证真实平台、实际操作系统原生桥、安装/锁屏或手机后台。`npm run test:puppeteer --prefix crowd-test-harness` 为复现入口，详细环境见 harness README。报告不记录凭据。

## 已执行

- 复现旧构建器缺失 background.js；新源码构建、内部包生成和脚本语法检查通过。
- `npm test --prefix crowd-test-harness`：状态机、Chrome/Firefox 后台适配、邀请 API、原生桥、证据导出及发布检查通过。旧 v3 测试保留作历史资料。
- 同一测试入口连接全新 PostgreSQL 17：真实迁移、权限、并发领取/续租、稳定回执、全局去重、严格核验、99/100 条奖励边界、付款不可改写及邀请名额并发/过期/撤销通过。
- Chromium 真实 DOM：自动搜索、访问详情、停留/滚动、标准/非标字段及回传通过。页面与 API 使用本地固定响应，未访问真实小红书。
- 本地生产网站浏览器流程：安卓识别、短信邀请、安装链接、桌面自动分片下载与摘要验证、校验失败和未开放渠道通过。
- Next.js 生产构建及 TypeScript 检查通过；依赖复用与本分支 package-lock 完全一致的已有安装树。
- Android SDK35/Java21 编译 APK；v2/v3 签名验证通过。Windows x64 用官方 SHA256 校验的 Electron runtime 打包，并用 NSIS 3.11 编译普通安装程序；PE 格式、摘要及发布检查通过。没有在 Windows 执行该安装程序。原生项目与共享资源随构建分发。
- 分发材料生成检查通过：短信/二维码/离线分享页只导出公开邀请资料，拒绝不合规 URL，不包含发布身份。分享页无需外部二维码服务。
- 发布器验证包摘要、当前公开配置、解析器/界面源码与原生主程序源文件摘要；任何相关源码变动后旧包不能继续发布。默认检查不写生产、不生成假邀请。

## 现有中台部署

2026-10-06 通过已连接的 Supabase MCP，在项目 `bdwrhshgdeghgyzwpxnl` 执行经本地 PostgreSQL 验证的两项迁移。远端记录为 `20261006145016_crowd_v4`、`20261006145030_crowd_v4_invites`；仓库文件名已同步远端版本，SQL 内容未变。独立 `crowd_v4` 空间保留旧 v3 表和账本。

只读回验：8 张表均启用 RLS，anon/authenticated 无直接 SELECT 权限；7 项 RPC 固定空 search_path，anon 不可执行，邀请/管理 RPC 仅 service_role；服务端邀请列表为空。未创建生产参与者、邀请、任务、证据或付款，未启用现网调度。

部署后执行安全 advisor。新对象包含 8 项 [RLS 无策略 INFO](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) 和 5 项 [authenticated 可执行 SECURITY DEFINER WARN](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)。这是当前 RPC 权限设计：私有表拒绝直读，参与者经有 auth.uid()/身份/租约校验的 RPC 执行指定操作；保持权限边界，不添加宽松表策略。既有库另有 public RLS、旧函数和视图等警报，不在本次修复范围，不能据新接口回验宣称整个存量库已完成安全整改。

## 服务端接入部署 · 2026-10-07

已通过 Supabase MCP 部署 `crowd-gateway` v1，保留原 `crowd-page`。平台 JWT 校验开启，函数还要求独立的随机服务端密钥；部署代码只包含其 SHA256，实际密钥保留在忽略提交的私有状态中。网关允许邀请 RPC；Auth 操作必须重新核对有效邀请、预留 UUID、安装凭证哈希和研究账号身份，拒绝任意管理 RPC，不返回管理员凭据、登录 token 或其他账号资料。

网关和实际网站服务端适配器测试通过：缺密钥、浏览器 Origin、任意 RPC、错误 UUID、错误安装密码、邀请过期、重试不重设密码及账号隔离。真实线上 HTTP 回验：无密钥/错密钥/浏览器请求 403、任意管理 RPC 400、服务端健康检查 200。Next.js 构建和类型检查通过；实际 Next 网站服务器经网关连接生产邀请 RPC，manifest 返回 HTTP 200、ready=false、空安装渠道；未授权发布请求返回 403，没有生成邀请。

当前公开配置匹配项目启用的 publishable key，旧 anon key 已禁用；没有改用旧 key。云环境 Node 24 的本地网站测试使用 `NODE_USE_ENV_PROXY=1`，保留现有代理和 CA 信任。首次真实网站检查暴露了适配器仅允许旧 JWT 的错误，已修复并回验现代 publishable key。未在生产创建参与者、邀请、任务或付款。

## 验证边界

### 参与接入与数据回收配置 · 2026-10-07

新增 `crowd-access` v1 已实际部署并启用自定义鉴权：公开清单只显示已验收渠道；参与注册必须持有效邀请与预留安装身份；任务发布/核验/读取/导出必须持独立随机发布者口令。网关共用的安装账号校验已抽为 helper，原服务鉴权边界不变。部署源码只包含发布者口令 SHA256，不包含口令或管理员凭据。

核心测试、Next.js 构建及 12 项 Puppeteer 场景通过；增加参与接入/权限/稳定 Auth 重试/数据字段保留测试。真实 HTTP 验证：公开清单 200 ready=false；匿名回收 403；发布身份回收 200 空记录；未验收渠道发邀请 400；恶意 Origin 403。实际 Next 服务端无私有配置也能连接线上接入服务，manifest/data/invite 返回相同预期。真实浏览器管理页经 Next API 连接线上中台，正确显示 0 条待核验和 0 条已核验证据。

已用发布接口创建三条现有餐厅研究任务，每家目标两条，数据库回验为 open。未创建生产参与者、模拟证据或付款；未启用 Docker 回流调度。本工作区真实导出 0 条 verified 记录。完整数据位置和入库条件见 DATA_RECOVERY.md。

### Vercel 缺少公开配置的构建修复 · 2026-10-07

用户提供部署日志，`_app.js` 导入 Supabase 客户端时报 `supabaseUrl is required`。只取已提交的 app 源码、不带本地 `.env`，复现同一错误。新增 `app/supabase.public.json` 保存现有项目的公开 URL 和启用的 publishable key，已重新与 Supabase 返回的 enabled key 比对；Next 构建与客户端打包脚本共用默认配置，显式环境变量仍可覆盖。相同无环境文件的源码构建修复后通过，核心测试通过；数据库/浏览器/设备检查未在本轮重跑。此修复不配置服务端网关密钥、安装渠道或生产邀请，不等于完整发布验收。

SQL 行为测试使用临时本地数据库；生产执行上文两项迁移、独立网关部署及只读回验。网站没有发布到生产，也没有可开工的生产邀请。未连接 Windows/Mac/Android/iOS/Harmony 实机；真实小红书登录、页面变化、锁屏/后台与系统协议关联仍待验收。

Android 产物为内部 debug 签名。Apple/Harmony 编译、发布签名和正式分发仍需对应环境/身份。当前管理员策略禁止 Chromium 加载未打包扩展，因此扩展后台适配由源码 API 检查验证；未绕过该策略，也未将其算作实机通过。

## 复现入口

安装 `app/` 的锁定依赖，运行 `npm test --prefix crowd-test-harness`。增加浏览器检查需 `CROWD_TEST_TOOLS` 指向含 Playwright 的开发工具目录；`CROWD_CHROMIUM` 指向完整 Chromium。`CROWD_PORTAL_TEST_ORIGIN` 指向已启动的本地生产网站。

数据库检查另需 pg，设置 `CROWD_TEST_DATABASE_URL` 指向**全新可丢弃库**；测试会拒绝已有 auth/crowd schema。示例工具版本：pg 8.23.1、Playwright 1.63.0。未设置变量时对应检查跳过，不能计作通过。

运行 `python3 cloud/crowd_build.py --dry` 检查公开配置，实际生成包用 `python3 cloud/crowd_build.py`。SDK/runtime/产物、私钥与本机会话不提交到源码仓库。

部署步骤和各端边界见 DISTRIBUTION.md / DEPLOY.md / README.md。先完成试点验收并提供可信网站部署环境，再用发布者脚本处理未执行迁移/发布；参与者只收到链接或二维码。回滚停止 v4 客户端与调度，保留证据和已付账本。
# Mac 内部验收准备 · 2026-10-07

用户选择 Mac，当前执行环境仍是 Linux。已生成双架构 Mac 离线内测包（约 252 MiB），两个官方 Electron 运行时通过 SHA256；ZIP 内脚本可执行权限、运行时及共享源码摘要、发布密钥不进入材料检查通过。脚本改用独立客户端，自动识别 CPU，在 Mac 本机临时签名并验证后安装；没有关闭 Gatekeeper 或写全局浏览器策略。不能据这些检查宣称 Mac 安装/签名已通过。

真实中台创建一份 max_people=1 / quota_day=2 / 48 小时报名期限的试点邀请。`crowd-access` v2 ACTIVE，部署摘要 `e1cd40c4dab74b4c030b8807e34a9821483df2ae952da8daa2ba064326421aa0`；只对配置中的邀请摘要允许 Mac 内测接入，数据库仍校验名额、撤销和安装身份。真实 HTTP：试点邀请 valid=true/full=false；Windows 使用同一邀请返回 release_not_ready，Mac 未同意返回 consent_required；正式 manifest ready=false，正式邀请仍被拒绝。数据库参与者、开户预留和回传均为 0，未做虚假开户/上传。

当前全部核心测试通过，新增试点过期/错 token/错平台/数据库过期及正式渠道不被打开的检查；Mac 包测试验证损坏 runtime 被拒绝和 shell 语法。还需要 Mac 上真实签名、首次启动/协议关联/登录/领取/上传/关窗后台/停止/恢复；只有这些完成才可以开放对应渠道。报名期限不会自动暂停已报名身份，试点结束需撤销邀请并暂停试点身份。

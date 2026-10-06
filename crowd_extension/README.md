# 众包公开笔记采集 v4

## 短信 / 二维码参与入口（默认产品流程）

发布完成后，邀请人只发送同一个链接或二维码。参与者打开入口，系统识别 Windows、Mac、安卓、兼容安卓的华为、原生鸿蒙或 iPhone/iPad；首次安装客户端后回到入口点“继续参与”，在客户端确认自愿参与并首次登录小红书，随后自动领取、搜索、采集和回传。无需注册中台邮箱、填写服务器配置或等待人工审批。进度自动刷新，停止始终可操作；注册途中停止不会在网络恢复后自动开工。

桌面默认使用独立客户端，避免浏览器开发者模式；浏览器扩展仅为高级部署选项。Android 直接下载安装包。用户当前没有商店发布账号，Apple 保留原生完整目标，待补齐 Apple 发布身份后通过 TestFlight/App Store 接入同一邀请；原生鸿蒙也必须有可用且通过验收的正式分发渠道。普通网页只做邀请入口，不能替代苹果跨应用采集或持续后台运行。

**当前为本地实现，尚无可开工的生产邀请。** 下一步在 Mac 完成客户端编译/设备验收，并连接正式网站的部署权限。未验收的渠道不会显示为可安装，也不能生成假就绪邀请。邀请默认 7 天、100 人、每人每天 20 条，转发同一个短信链接不会使名单无限增长。服务端只存邀请/安装凭证哈希，创建随机参与身份，不收集参与者真实手机号、姓名或邮箱；平台登录仍留本机。卸载或清空本机参与身份后，旧余额不会自动合并到新身份。

发布人页面 `/crowd/admin` 一键生成链接和本地二维码图片；参与页面 `/crowd`。二维码由本系统生成，没有把邀请发到外部二维码服务。安装后的 `foodcrowd://join` 链接恢复原邀请；打开链接本身不会消耗参与名额，也不会静默启动采集。安装确认和小红书验证仍由本人操作。

以下为部署负责人资料，不需要发给参与者：

- `cloud/crowd_launch.py` 默认只检查；部署环境连接后，`--apply` 一次处理未执行迁移、网站发布、真实入口检查及首次邀请/二维码生成。没有部署权限、绑定域名、有效安装渠道或最新客户端配置时会拒绝发出邀请。
- 入口默认复用 HANDOFF 记录的现有网站 `app-lyart-eta-22.vercel.app`，该站尚未发布本次入口。改域名才需设置 `CROWD_PUBLIC_ORIGIN`。发布环境提供 `SUPABASE_DB_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`VERCEL_TOKEN`，并连接现有 Vercel 网站项目；公开 Supabase 配置复用现有 app 配置。`CROWD_OPERATOR_KEY` 可自动生成并只存 `.crowd-launch/`；这些值不能放进参与链接或版本库。
- `CROWD_RELEASES_JSON` 按平台记录 channel/url/version/sha256/verified。verified 只能在真实设备验收后置 true。desktop/apk 渠道只能引用本站 `/crowd/releases/` 的匹配文件；首次构建务必设置真实 `CROWD_PUBLIC_ORIGIN`，部署检查同时验证包的配置、源码和哈希，拒绝发送旧包。
- 示例结构：`{"android":{"channel":"apk","url":"https://你的域名/crowd/releases/crowd-android-v4.0.0-debug.apk","version":"4.0.0","sha256":"构建产生的64位摘要","verified":false}}`。原生鸿蒙为 appgallery，iOS 为 testflight/appstore；只有通过验收的项开放。
- 构建独立桌面源码后，`python cloud/crowd_desktop_build.py --platform win32 --arch x64` 打包官方校验过的 Electron runtime；Mac 对应 darwin/arm64 或 x64，需在 Mac 重签。桌面默认没有添加商店依赖，仍需实际 OS 安装/协议关联/登录/后台验收。Windows 当前已产生可执行客户端 ZIP，未作 Windows 实机验收；Mac 当前没有完成打包。
- 邀请 API 显式检查同意、平台渠道和来源，服务端原子预留名额及身份；Auth 创建/回复中断后重试使用相同身份，不重设密码，也不恢复被停用者权限。原有每 100 条核验笔记 10 分账本保持独立；自动接入不代替真实性核验或自动转账。
- 桌面包较大，发布器自动生成 24 MiB 分片以适配网站单文件限制；入口自动下载、逐片与整包校验并生成一个 ZIP，参与者不拼文件。桌面浏览器需有足够内存处理约 150 MiB 安装包；实际目标设备仍需验收。邀请/审核 API 和安装包下载禁止离线缓存；同意/开户/停止与 native 桥的测试分别在 `tests/join.cjs`、`tests/native.cjs`，真实网页流程在 `tests/portal.mjs`，名额并发/过期/停用保护纳入 PostgreSQL 测试。它们不等于真实小红书或 OS 安装验收。

下面保留开发与高级安装说明。

Ponytail 技能已安装在项目 `.agents/skills/ponytail`。v4 自动领取任务、搜索、打开笔记、滚动与停留、提取公开正文、回传并领取下一任务。首次登录、同意参与、启动和处理验证由参与者完成。

**交付状态：本地重写与测试包，尚未部署线上。** Windows 独立客户端已打包，Mac 同源客户端待在 Mac 重签打包，桌面扩展作为备用；Android 有可编译的原生容器和内部测试 APK；iPhone/iPad、原生鸿蒙交付原生项目源码，未在各自 SDK 与实机验收。所有平台的小红书真实账号、实时页面、后台/锁屏行为仍需试点验收，不能把模拟页面通过当作线上可用。

## 旧包评估与重写范围

本次评估和整合基线为 `1b4006b` / `cd10128`；复用此前在 `4486b8c` 上实现的 v4 核心，保留 v3.4.8 的服务器健康检查及回流监控修复。详细可复现问题见 AUDIT_REPORT；历史“已闭环”的记录不能代替当前插件验收。

| 旧实现问题 | v4 实现 |
|---|---|
| background 用公开 API key 作 Bearer，未使用参与者登录会话 | 用户 Auth 会话与刷新；服务端绑定 auth.uid，匿名不能领取/提交 |
| 租约、任务完成和重试各自维护，关闭任务后重放可能丢失进度 | 原子租约、独立稳定请求 UUID、先返回原始回执再检查租约 |
| 正文截断为 200 字，难以保留证据及非标信息 | 原文最多 24000 字、明确截断标记、标准空值及扩展 JSON、逐字引用 |
| 把“频繁”正文也视为限流；停止不能可靠取消正在进行的工作 | 可见验证/错误界面优先检测；立即取消、单写者状态保存和暂停恢复 |
| 冷却、上传和 worker 重启容易互相阻塞 | 每个状态转换落盘；上传优先于采集冷却，断网保留证据 |
| 旧奖励包含笔记 ¥2/条和参与者评分，且旧流程直接回写食客评分 | 独立 v4 账本；100 条核验唯一笔记 10 分；原作者证据回流现有质量门 |

旧 `deep_coverage` 的联网豆包历史提交并不是当前实现的唯一权威；当前发现与 build_bridge 仍依赖现有 SearXNG/全文证据质量门。本次接入已核验证据，没有用自动采集替代真实性核验。

## 安装与启动

1. 中台通过 Supabase CLI 按顺序执行 `cloud/supabase/migrations/` 的两项迁移：`20261005142718_crowd_v4.sql`、`20261005152612_crowd_v4_invites.sql`。它们创建独立 schema、v4 RPC 及短信邀请机制，不改旧账。先在独立项目验证；重复安装交给迁移版本管理。
2. 发布者设置 `NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY`（也可读取现有 `app/.env.local`），运行 `python cloud/crowd_build.py`。构建仅分发 publishable/anon key，拒绝 service_role/secret key。源码中的 config 不包含凭据。
3. Windows 10/11、macOS：下载 `releases/crowd-extension-v4.0.0.zip`，解压。在 Chrome/Edge 120+ 的扩展管理页开启开发者模式，加载解压目录。辅助安装脚本和 ZIP 放同目录。Chrome 页面 `chrome://extensions`，Edge 页面 `edge://extensions`。旧版与新版不能同时启动采集。
4. 打开插件，登录/注册中台邮箱账户，确认参与。运营者审核批准后，在本机登录小红书，再点“启动自动采集”。中台账号和小红书账号是两套账户；小红书 cookie 不上传。
5. 关闭浏览器会暂停；重启保留任务和待回传证据。用户停止、平台限流/验证、认证失败都会停止。处理验证时打开工作标签页；处理后重新启动。页面不兼容时保留错误并等待，不假报采集成功。

## 中台操作

操作端设置 `NEXT_PUBLIC_SUPABASE_URL` 和 `SUPABASE_SERVICE_ROLE_KEY`。密钥只能在可信运营环境设置，不放进插件、文档或日志。CLI 默认只预览写操作，`--apply` 才写入；读操作无需此参数。

```sh
python cloud/crowd_v4.py publish /app/data/coverage/need_ugc.jsonl
python cloud/crowd_v4.py publish /app/data/coverage/need_ugc.jsonl --apply
python cloud/crowd_v4.py admin list --payload-file participants.json
python cloud/crowd_v4.py admin approve --payload-file approval.json --apply
python cloud/crowd_v4.py admin list --payload-file proofs.json
python cloud/crowd_v4.py admin review --payload-file review.json --apply
python cloud/crowd_v4.py export /app/data/coverage/crowd_v4_verified.jsonl
python cloud/crowd_v4.py cycle --apply
```

文件内容示例：`participants.json` 为 `{"kind":"participants"}`；`proofs.json` 为 `{"kind":"proofs"}`；`approval.json` 为 `{"user_id":"实际账户 UUID","quota_day":20}`。

`cycle` 用既有 common_core 配置/HTTP，自动读取 need_ugc 发布幂等任务，再分页导出核验证据供 build_bridge 使用。crontab 已准备每小时 11/41 分运行，默认 `CROWD_V4_ENABLED=0`；生产迁移与试点验收后，运营配置为 1 才启用。这次没有修改现网调度。

`review.json` 必须包含 proof_id、decision（verified/rejected）、至少 8 字的 reason。通过核验还必须有 public_visible、relevant、personal_experience 三个布尔 true、实际独立检查原帖的 source_checked_at，以及正文中逐字存在的 quote。采集自动化不等于证据自动成立；目前独立核验由运营端完成，不用参与者自报评分充当核验。重复核验不会重复发奖励，最终核验状态不可反向改写。

`crowd_pack.publish` 旧调用已转 v4，不再回退 task_queue。新任务一条一个查询，source_key 幂等。`crowd_scale` 旧覆盖统计仍读 v3，不作为 v4 发布入口；直接使用以上 need_ugc 入口。导出的核验证据通过 `build_bridge.gather_pages` 进入现有 stage1–4 门槛，不直接改餐厅评分。地址、菜名、独立来源数量等条件仍由原管线检查；证据不足不会强行入库。旧 `crowd_ingest/crowd_settlement/crowd_store_ingest` 只处理 v3 数据。

奖励自动累计：每 100 篇经核验的全局唯一笔记生成 10 分人民币流水，99 篇不产生流水，余额继续累计。支付采用 `admin pay`，payload 为 user_id、batch_no、reference；这是**登记实际付款**，不连接支付渠道，也不自动转账。重复登记同一凭据幂等，已付金额和凭据不能重写。

## 移动端

`releases/crowd-mobile-sources-v4.0.0.zip` 含三个完整目录以及同一份核心/配置资源；APK 为 debug 签名，限内部试点，不是商店发行版。

| 环境 | 实现与后台边界 | 当前验证 |
|---|---|---|
| Windows、macOS | 独立客户端工作网页与后台调度；Chrome/Edge 扩展为备用 | Windows runtime 打包，核心/桥/Chromium 模拟页面通过；Mac 打包与各 OS 真实安装待验 |
| Android、兼容安卓的华为设备 | Java WebView 容器，用户启动可见前台服务，15 分钟一批，到期保存并暂停 | SDK 编译/签名验证；设备登录和后台行为待验 |
| iPhone/iPad iOS 26+ | WKWebView，用户启动有限批次，BGContinuedProcessingTask；系统拒绝/到期则暂停 | 原生源码；Xcode 26+ 编译、签名、WKWebView 后台网络待验 |
| iPhone/iPad iOS 16–25 | 前台自动采集；后台只给已有回传/保存短窗口，不能持续自动搜索 | 原生源码；Xcode/设备待验 |
| 原生 HarmonyOS 5+ | ArkWeb；前台自动采集，后台挂起宽限 + DATA_TRANSFER 仅回传已有证据；搜索恢复需回前台启动 | 原生源码；DevEco SDK/设备待验 |

Android 项目可用 Android Studio + SDK35/Java17+ 构建。无 Gradle 依赖的构建路径：

```sh
python cloud/crowd_build.py
python cloud/crowd_android_build.py --sdk /你的/Android/Sdk
```

macOS 上解压移动源码，打开 `ios/CrowdCollector.xcodeproj`，选择自己的签名团队；要求 Xcode26+，支持 iOS16 起。可先用 `xcodebuild -project CrowdCollector.xcodeproj -target CrowdCollector -sdk iphonesimulator CODE_SIGNING_ALLOWED=NO build` 编译。鸿蒙用 DevEco 打开 `harmony/`，配置签名再编译 HAP。当前环境没有 Apple/Harmony SDK，不能给出已验证 IPA/HAP。

切换 Mac 工作区时，检出本次 `fix/crowd-distribution-v348` 分支。此前基于 `4486b8c` 的恢复包只用于保留旧工作，不能覆盖本次基于 `cd10128` 的整合。先在干净副本检出当前分支，再编译 iOS 模拟器和验证实际安装；原生鸿蒙仍需要 DevEco 及设备。

Android 测试签名默认保存在系统临时目录；需连续升级同一测试安装时用 `CROWD_ANDROID_DEBUG_KEYSTORE` 指定并保留同一密钥库，私钥不随迁移包分发。正式发行需换为发布者自己的签名和发行流程。

## 验证与回滚

安装 app 的锁定依赖后，可执行 `npm test --prefix crowd-test-harness` 运行当前核心验证。设置下述浏览器/数据库环境变量才包含对应集成检查；历史 v3 测试脚本不算 v4 验收。

```sh
node crowd_extension/tests/check.cjs
node crowd_extension/tests/worker.cjs
node crowd_extension/tests/join.cjs
node crowd_extension/tests/native.cjs
python crowd_extension/tests/check_operator.py
python crowd_extension/tests/check_launch.py
python cloud/crowd_build.py --dry
python -m py_compile cloud/crowd_v4.py cloud/crowd_build.py cloud/crowd_android_build.py cloud/build_bridge.py
```

开发依赖只装在测试工具目录：`npm install --prefix /tmp/crowd-v4-tools --ignore-scripts pg playwright @sparticuz/chromium`。`CROWD_TEST_TOOLS=/tmp/crowd-v4-tools node crowd_extension/tests/browser.mjs` 使用真实 Chromium，页面由本地响应模拟，不连接小红书。设置 `CROWD_TEST_DATABASE_URL` 指向**全新可丢弃**的 PostgreSQL 测试库，再运行 check.cjs，会创建测试 auth/角色并执行真实迁移、并发领取和 100 条奖励路径；禁止指向生产库。

完整 Chromium 的扩展加载检查受当前环境管理员策略阻止（DevTools 返回 unpacked extensions disabled by administrator），因此 MV3 适配目前由源码 API mock 检查，不能写成实际扩展引擎通过。没有修改或绕过该策略；切到用户的 Mac 工作区后验证实际安装。

需要实机逐项验收：全新安装与注册批准→自动搜索→连续 5 篇→断网重启→关闭/锁屏→停止/验证码/限流→唯一笔记去重→接收/核验/奖励分离。每端至少验收一台，不通过就不能宣称支持该端后台采集。

回滚先停止 v4 客户端和调度，保留 schema/证据/奖励以便审计，禁止删除已付账。v3.2.1 ZIP 仅历史归档，本文不推荐恢复它继续采集。v4 不迁移旧参与编号，不复制旧奖励金额，不自动启动旧任务。

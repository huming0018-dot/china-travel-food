> **2026-10-07 18:03 Mac v4.0.3 候选（最新，未实机验收）**：已核对用户指定 Kimi `crawler-extension v1.0.0` / `5b9e327` / Release（仅源码归档）。复用逐卡片范围与搜索词核对，页面消息等待有界，加载中/脚本断连/响应超时分开报告，连续失败三次暂停。新增仅 opt-in 的工作标签主页面导航阶段/错误码诊断，生产迁移 `20261007100305_crowd_v4_navigation_diagnostics` 已部署且兼容旧版。核心检查、Chromium 固定页面→隔离 PostgreSQL 入库/幂等及诊断权限/隐私检查通过；最新真实客户端仍4.0.1、v4 proofs=0，不能宣称已修复实机网络或可分发。私有包38,766 bytes，SHA256 `a889c49b021fc933fbb4be27fb7e9bf443f9c7f1696a93aa998845dee3ad0de4`。具体对照、权限范围、验证及更新方式见 [KIMI_REFERENCE_REVIEW.md](KIMI_REFERENCE_REVIEW.md)。以下为历史记录。

> **2026-10-07 16:57 Mac v4.0.2 候选版本复核（最新，尚未实机验收）**：真实远程快照确认已运行 v4.0.1，搜索页 document/tab_status=complete，search_note_links=56、links=0，仍 page_timeout，生产 v4 proofs=0。解析器仅接受 explore/discovery，漏掉结果页 search_result/<24位笔记ID>。v4.0.2 加入严格同域、HTTPS、24位十六进制 ID 的结果页详情链接，保留本机导航参数，回传仍使用无 token 的 canonical explore URL；关键词跳转和外站不计为笔记。另修复：完整页面探测器断连不再无限重开，连续三次超时暂停至本人继续；续租遇到配额保留同一证据/请求 ID；重启后缓存 tab ID 指向其他站点时不改动该用户标签页；Mac 助手不覆盖使用相同 public key 的旧 v3 运行时。界面按实际状态显示等待/错误，不能把 enabled 等同于已有采集成果。
>
> 验证已从浏览器 + 模拟成功回执改为实际 Chromium DOM → 共享采集器 → 隔离 PostgreSQL 原迁移中的 claim/submit/finish：结果页详情正文、标准字段/非标字段/证据落库，丢失首个回执后原 UUID 重放只保存一条。核心套件、Chrome/Firefox 适配器、停留/停止/恢复、验证码暂停、配额保留和助手 v3 隔离检查通过。固定网页及 Chrome API 模拟仍不能替代真实 Mac 安装、小红书回传及睡眠验收；正式渠道/Docker 调度保持关闭。已观察到的页面链接格式有直接诊断证据，未声称修复所有可能的 DOM 变更或平台限制。
>
> 私有候选包 `Mac轻量内测-v4.0.2.zip`：37,032 bytes，SHA256 `8b1340c88267551c461b7fe59ed0d0bddd865689c4b3fd385db49ac6131b433a`。相同扩展 ID/原邀请/原登录身份，日配额两条，旧包与摘要不改动。只更新原 v4 目录并刷新，不能卸载、换个人资料或重新报名；包含私有试点邀请，不上传公开仓库。生产中至少一条真实正文/标准/非标/证据核对，以及停止和睡眠恢复通过前，结论保持「内测候选，未验收」，不能写「可分发开工」。以下内容为历史快照。

> **2026-10-07 15:30 Mac 页面超时诊断与 v4.0.1 修复（最新）**：已收到本人开启的真实快照：v4.0.0、enabled=true、phase 在 search/idle 间重试、error=page_timeout、tab_status=loading、document/page_kind=unknown，队列和回传为 0。任务领取与诊断 RPC 均 HTTP 200；新 Mac 身份已于 14:51 接入并领取任务。源码确认 runtime.probe 在 loading 时直接返回，诊断也只探测 complete 标签页，无法区分页面打不开与已渲染但资源未加载完。v4.0.1 改为 document_end 安装探测器、加载期间尝试读 DOM、初始探测器未连接时等待而非反复导航；诊断保留 loading 状态同时报告可读 DOM，成功探测清除旧超时提示。真实 Chromium 卡住图片响应的固定场景与核心套件通过，验证码仍暂停，无新增权限、凭据采集或远程执行。尚不能断言本机已有可读 DOM、网络资源挂起根因已解决或实际笔记已回传；需要更新原插件目录并刷新后回验新版本诊断。
>
> 更新包 `Mac轻量内测-页面修复v4.0.1.zip`，36,621 bytes，SHA256 `387b2e8ca031454c947131d4ea70d7590eac940febceee8f511c7b45e2f46a16`；相同扩展 ID，保留邀请、会话和配额，不修改生产登记、租约或扩大报名。仅含现有私有内测邀请，不公开上传；旧诊断包保持原摘要。已有安装必须覆盖原目录后在原个人资料刷新，不能先卸载。云端没有 Mac 文件执行连接，无法静默替换已经装在 Mac 的代码。以下条目是历史快照。

> **2026-10-07 内测换浏览器/重装接续（当前）**：用户确认换过浏览器/个人资料或卸载重装，当前安装使用新凭证，原 1 个名额已被旧身份占用。已执行一次有审计的无证据试点换机：旧 Auth、enrollment、participant 和账本记录全部保留，旧 participant 暂停，旧租约释放；原邀请增加一个替换登记名额（物理上限 2，含已暂停旧身份），有效参与身份仍最多 1、每日 2 条。修复前后真实 proofs/rewards 均为 0；执行后旧身份 suspended、新安装尚待点击同意、available=1、audit=1。原邀请/有效期/Edge 配置不变，无需新下载或重装。不能把这次操作写成已完成新开户或回传。后续恢复有证据的身份不能照搬本次方案。

> **2026-10-07 Mac 运行诊断（当前）**：首次真实接入已完成，中台现有 1 个 approved 参与身份；真实笔记回传仍为 0，`page_timeout` 根因尚未确认。轻量插件新增默认关闭、本人可开关的运行诊断和「查看采集页面」按钮，每分钟上报严格限定的阶段/错误码/任务与队列数量/页面加载和元素数量，只保存最新快照，不发送密码、Cookie、正文、截图或完整网址，不提供远程执行命令。`20261007051154_crowd_v4_diagnostics` 已部署；私有表 RLS 开启且无匿名/参与者直接权限，RPC 按 auth.uid 校验本人参与身份，匿名 HTTP 401。关闭或退出时尝试清除状态，旧修订请求不能重新写入；离线清除须同一参与身份下次联网，退出后不再发送。当前快照 0，需原 Mac 更新并主动开启后才能远程定位。下文为历史快照，不能替代本条状态。

> **2026-10-07 Mac 首次接入修复（当前）**：实机反馈点击开始失败，线上 Auth 日志定位到现有 `handle_new_user` 将 78 字符研究邮箱作为 `profiles.username varchar(50)` 写入。共享接入/网关和可选 Next 直连注册现在提供基于预留 UUID 的 42 字符 profile 名称；完整研究邮箱、安装凭证、身份 UUID 不变，不改数据库列或触发器、不重置密码。`crowd-access` v4、`crowd-gateway` v2 已 ACTIVE 并回读源码确认。注册回归覆盖同一旧触发器限制和 Next 直连路径，核心检查及类型检查通过；真实 HTTP 预检 204、显式同意 400、网关健康 200、正式清单仍关闭。一个原报名预留尚未完成，需用户在原插件点同意并开始重试；尚无真实回传，不宣称开户或采集已成功。无需重装、更换邀请码或重发参与包。备用网页是正式安装入口，本次内测邀请须在插件内接续。

> **2026-10-07 Mac 后台与唤醒续作**：私有轻量包约 33 KB，新增双击助手：自动校验、保存文件、复制安装路径并打开浏览器安装页；首次仍需本人开启开发者模式并确认加载，不能静默安装。旧安装识别后更新原目录，不删除浏览器身份。助手的模拟命令流程/旧目录更新/摘要失败拒绝检查通过，Mac 原生双击和安装确认仍待验收。首次同意并启动后后台领取、搜索、采集和回传；浏览器启动/worker 加载自动补建周期调度，唤醒后续做未停止的任务。没有普通窗口时创建最小化、不主动抢焦点的工作窗口；睡眠或浏览器退出期间不执行。手动停止、退出、登录失效、验证码和限流保持暂停。恢复保留冷却、配额和待回传证据；重启或长调度中断时重新打开页面并计时。核心恢复检查和 12 项 Puppeteer 固定响应场景通过，真实 Mac 睡眠/唤醒和平台回传仍待验收。更新覆盖原插件目录后刷新，不先卸载。crowd-access v3 已上线，正式渠道和批量邀请仍关闭；历史大包说明不适用于本次实验。当前指引见 crowd_extension/DISTRIBUTION.md 顶部。

> **2026-10-07 正式网页已发布**：PR #1 已合并，Vercel 正式部署 `3bBqSP5GeS7sWM88HSjzdnnw1oSF` / 提交 `adce116` 为 Ready。正式域名 `https://app-lyart-eta-22.vercel.app` 的管理页和 manifest 实际返回 200；匿名回收 403、发布身份查看/导出 200。当前安装渠道为空，邀请返回 release_not_ready，尚不能声明可开工分发。三条真实试点任务 open，参与者/回传为 0；设备问题等待用户回复，Docker 入库流水线未启用。以下历史快照不能代替这一状态。

## 本次报名已满修复验证

在隔离 PGlite 中执行实际 v4/邀请迁移和本次有条件换机事务：修复前新凭证 invite_full；旧身份/记录保留并暂停、旧租约释放、替换后可接入一个新凭证、旧 complete 重放不重新批准、旧身份 claim 被拒绝、第三安装仍 invite_full、重复执行换机事务被拒绝、审计只记录一次。生产事务对既有 invitation/enrollment/participant 加锁，仅允许未撤销未过期、max_people=1/quota=2、唯一已完成 approved 身份且零证据/奖励的私有试点；无 DDL、无 Auth 密码重置或测试开户。

更新助手现在明确打开已识别的原 Chrome/Edge 个人资料，缓存 public key 匹配时可恢复已删除的源目录；同源目录出现在两个个人资料时也拒绝猜测，不读取或改写登录数据。已登录的控制页优先继续原身份，不因再次接收到邀请而重复报名。这些源码检查/真实 DOM 固定响应检查通过；本次服务端接续兼容用户已下载的诊断包，不要求再更新。后续生成包使用新助手。

## 本次运行诊断验证 · 2026-10-07

同步主分支安装器 v5 的同名冲突时保留其 `crowd-install-mac.command`、更新器和 plist；v4 原生备用内测安装器移至 `crowd-install-native-mac.command`，构建器/试点生成器只引用这一独立入口。当前轻量内测始终使用 `crowd-extension-mac.command`，不执行或分发主分支的 v3 自动更新安装器。本次 36 KB 私有包内容及摘要不受入口重命名影响。

- 当前核心套件、Chrome/Firefox 后台模拟、真实 Chromium DOM 与插件控制页开关检查通过；12 项 Puppeteer 入口/共享原生控制器固定响应场景通过。新增隔离 PGlite PostgreSQL 检查执行真实迁移，验证本人状态隔离、未同意/匿名拒绝、字段类型白名单、只保留最新状态、关闭清除、旧报告/旧开启请求被拒绝、暂停身份允许清除。完整业务数据库套件本次未重跑；PGlite 不替代线上 PostgREST 的 JWT 验证。
- 线上迁移由 Supabase MCP 执行，本地迁移文件名同步远端记录 `20261007051154`。只读回验 RLS=true、anon/authenticated 直接权限=false、anon RPC=false、authenticated RPC=true；匿名实际 RPC HTTP 401/code 42501。未插入生产测试快照/证据，不获取 Mac 登录凭据。
- 诊断上报独立于采集，3 秒超时，1 分钟浏览器闹钟；断网不启停采集。关闭后只重试清除，不发送快照；退出先尝试清除，再丢弃会话和诊断闹钟。云端清除保留 enabled=false/修订号/更新时间标记，state=NULL，防止迟到请求复活；离线退出的旧快照可能保留到同一身份下次登录联网清除。
- 安全 advisor 将新 RPC 列入 [authenticated 可执行 SECURITY DEFINER 提示](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)。这是有意的窄接口：固定空 search_path、auth.uid() 本人校验、私有表无直接权限、严格状态字段校验；不能改为匿名访问。已有旧模块告警不在本次修复范围。
- 私有 Mac ZIP 36,176 字节，SHA256 `5d99a5c4a798f697cfcee14cf540477f693a593703c39ab931b51b8ab093e886`。包内当前源码、可执行助手和所有摘要一致，无发布口令/网关密钥，插件 ID 与浏览器权限保持一致。包和私有邀请码不提交仓库或公开上传。
- 当前 Supabase `crowd_v4.diagnostics` 快照数量=0、approved 参与身份=1、真实 `crowd_v4.proofs`=0。诊断信息由授权研究管理者在中台读取，现有 `/crowd/admin` 尚无诊断展示页。必须原 Mac 更新并主动开启后才有真实诊断；页面超时尚未判定为网络、登录或解析器问题。`last_error` 是最近一次错误，须结合当前 phase/页面状态判断，不能单独当作实时故障。

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

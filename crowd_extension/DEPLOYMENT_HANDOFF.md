> **2026-10-08 v4.0.5 安全与调度增强（当前内测候选）**：服务端预扣四类动作额度、报名日龄预热、固定动作间隔、持久化会话/验证码/限流冷却；继续/重启/唤醒不清零，独立控制同步与配置失效停采，详情访问前全局笔记占用/去重。迁移 `20261008014820_crowd_v4_safety` 与 `crowd-access` v5 已部署。核心、Chromium固定页面→隔离PostgreSQL真实回传、冷却/断网/权限回归通过；最新真实客户端仍4.0.1、proofs=0，不能宣称实机成功或开放分发。私有包42,955字节，SHA256 `712df88fa0e17af63aee6b41995bc3668e684f84e76ef8a52e3e8caf8d8c8782`；规则、操作与验收边界见 [SAFETY_SCHEDULING.md](SAFETY_SCHEDULING.md)。以下为历史记录。

> **2026-10-07 v4.0.4 新增公开阅读量与评论（最新，未实机验收）**：`standard.view_count` 为公开阅读/浏览量，`extra.metric_labels` 保留原显示文本（如1.3万）；`extra.comments` 保存评论正文、公开昵称、点赞数、时间标签及父评论/回复关系。只读展开/滚动最多4轮、50条、每条2000字符，并受整个回传包预算约束；`complete=false`、`coverage=visible_loaded_only`，绝不宣称已抓完整评论区。隐藏内容不采，缺失字段null；点赞/回复发布按钮不会点击。正文缺失不能用评论顶替。详细字段与边界见 [DATA_RECOVERY.md](DATA_RECOVERY.md)。核心检查、Chromium固定页面→隔离PostgreSQL实际入库/幂等、父子隔离、滚动推进、截断、缺失值和验证码停止检查通过。生产迁移 `20261007120848_crowd_v4_view_count` 已部署且回验，无新表、权限变化或新浏览器权限。私有包 `Mac轻量内测-v4.0.4.zip`：41,246 bytes，SHA256 `4a438801c7284500dea45f6608d50c095303f6a45b8e0cb2b6935a603a73b340`。包内源码与摘要已核对；真实Mac/小红书字段适配仍待验收，正式分发未开放。以下为历史记录。

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

> **2026-10-07 正式网页已发布**：PR #1 已合并，Vercel 正式部署 `3bBqSP5GeS7sWM88HSjzdnnw1oSF` / 提交 `adce116` 为 Ready。正式域名 `https://app-lyart-eta-22.vercel.app` 的管理页和 manifest 实际返回 200；匿名回收 403、发布身份查看/导出 200。当前安装渠道为空，邀请返回 release_not_ready，尚不能声明可开工分发。三条真实试点任务 open，参与者/回传为 0；设备问题等待用户回复，Docker 入库流水线未启用。以下历史快照不能代替这一状态。

> **2026-10-07 续接**：用户选择继续云工作区，并已安装 Vercel；安装状态经查询确认。Vercel MCP 已暴露并可调用，但对权威项目/失败部署的读取返回 403 Not authorized（scope haha-hunter）；连接身份为 huming0018-1336，list_teams 返回空列表。这确认当前连接缺少目标团队访问权，不能据此断言部署失败的具体构建原因。CLI 后备也无登录凭据，未完成网站发布。已请求用户在插件连接中授权拥有目标团队权限的账号，或提供已迁移项目的地址；无需重复安装或刷新。
>
> 新增 `crowd-gateway` v1 已部署到现有 Supabase，真实 HTTP 权限/健康回验和实际 Next 服务端连接均通过；参与者/邀请/任务未创建，渠道保持关闭。详情见 REPAIR_VERIFICATION.md。当前私有 `.crowd-launch/gateway-token` 已保存随机网关密钥，发布脚本可自动读取；新部署模式无需 Supabase 管理员密钥、数据库密码或 Supabase CLI。跨工作区迁移该私有值应走可信环境配置，不放进源码包。
>
> 当前工作区已按 Vercel bot 的权威元数据准备 `app/.vercel/project.json`，CLI 在 `/tmp/crowd-vercel-tools/node_modules/.bin/vercel`。检查时指定 `VERCEL_CLI` 和现有 `VERCEL_GLOBAL_CONFIG`，仍缺账号授权及至少一个设备验收渠道；没有执行网站发布。中台不替代这些验收条件。

> 用户从部署 `Cngmb7BM1Rs2YHQQeB2GK4siWcgn` 提供实际日志：`_app.js` 在构建时抛出 `supabaseUrl is required`。无本地环境文件的干净源码复现后，已接入公开默认配置，完全相同的无 `.env` 构建通过；代码推送触发新的 Git 预览部署。不是凭空设置虚假 Supabase URL，也未把网关/管理员密钥写入版本库。最新自动部署结果需通过 GitHub 的 Vercel 状态确认。

# 部署续接记录 · 2026-10-06

用户已明确要求执行部署并开始短信/二维码分发；无需再询问是否部署。当前尚未部署成功，没有正式可开工邀请。用户选择继续云工作区；续接后由 Codex 执行操作，只把账号登录确认留给本人。

## 当前代码和中台

- 工作分支：`fix/crowd-distribution-v348`，功能提交 `3526bf4`；draft PR：https://github.com/huming0018-dot/china-travel-food/pull/1。
- 现有 Supabase 项目 `bdwrhshgdeghgyzwpxnl` 已安装迁移 `20261006145016_crowd_v4`、`20261006145030_crowd_v4_invites`，旧数据/账本保留；权限回验见 REPAIR_VERIFICATION.md。未启用任务调度。
- Windows EXE 与安卓 debug APK 已编译、校验并整理为内部测试包；包内容说明见 DISTRIBUTION.md。没有各端实机验收，不能把渠道 verified 设为 true 来跳过验收。
- Mac、苹果、原生鸿蒙没有可安装成品；必须在对应 SDK 环境完成构建、签名和验收。

## 本轮发布检查结果

- 现有 GitHub 仓库确实已接入 Vercel；并非完全没有自动发布连接。
- GitHub 对 `3526bf446566ba1744679fed76133c76036f120d` 返回 Vercel deployment failure。部署记录：https://vercel.com/haha-hunter/app/3MTXQHTr2RBWaocn8GaAohZpwrTd。失败的具体原因需要登录后读取日志，不推断为代码或配置的某一问题。
- Vercel bot 指向既有 app 项目，Root Directory 为 `app`。沿用这个项目，不新建无关网站。
- 正式站 `https://app-lyart-eta-22.vercel.app/api/crowd/manifest` 实际返回 HTTP 404，尚无本次参与接口。
- 当前云工作区只提供公开 Supabase URL/key，没有 Vercel 登录身份、服务端 Supabase key、数据库连接或发布身份。只报告变量是否存在，未输出凭据。
- 已安装 Vercel CLI 62.4.0 并尝试登录；网络代理对 `api.vercel.com` 和 `vercel.com` 返回 CONNECT 403 Forbidden，登录失败。没有改用直连、其他代理或绕过网络策略。

## 在可用 Mac 工作区继续

1. 检出上述分支，读取本文件及 DISTRIBUTION.md / REPAIR_VERIFICATION.md。先检查本机已有 Vercel 登录和项目连接，复用已有身份；需要本人登录时提供正常浏览器授权入口，不让用户在聊天里发送 token。
2. 读取失败部署日志，修复实际故障，并获取现有项目的服务端运行配置。密钥仅留在可信环境，禁止写入源码、参与页面、二维码或交付包。当前公共配置不够调用管理员身份创建接口。
3. 在 Mac 构建/签名桌面客户端，完成至少一个真实设备的安装、邀请打开、显式同意、首次登录、自动领取/搜索/采集/回传、风控停止与用户停止验收。未验收的设备保持渠道关闭；不声称苹果/鸿蒙后台不受系统限制。
4. 有有效安装渠道、服务端配置和网站部署身份后执行 `cloud/crowd_launch.py --apply`。迁移版本已与远端一致，脚本仅处理未执行迁移；先验证正式域名的 manifest，就绪后才生成真实邀请。
5. 配置并验证首批任务和中台回流，完成真实端到端试点，再交付 `.crowd-launch/发给朋友.html`、整条短信及二维码。把发布身份与参与链接分开。短信转发由用户进行，不擅自向别人发送消息。

当前阻塞是可用的发布环境和实机渠道验收；压缩包、GitHub PR 或本地浏览器通过均不能替代这些步骤。

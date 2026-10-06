# 部署续接记录 · 2026-10-06

用户已明确要求执行部署并开始短信/二维码分发；无需再询问是否部署。当前尚未部署成功，没有正式可开工邀请。用户可切换到 Mac Codex 工作区；续接后由 Codex 执行操作，只把账号登录确认留给本人。

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

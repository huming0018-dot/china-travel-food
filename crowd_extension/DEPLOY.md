# v4 部署与分发

网站沿用现有 Vercel app 项目，Root Directory 为 app；公开连接配置在 app/supabase.public.json，Git 推送可自动构建，无需本地 .env。

Supabase 项目 bdwrhshgdeghgyzwpxnl 已安装两项 v4 迁移，并部署 crowd-gateway 与 crowd-access。默认网站 API 使用 crowd-access：邀请有效期/名额/安装身份由中台校验，管理操作校验独立发布口令，不需要在 Vercel 配置管理员密钥。旧的私有网关/直连方式仅在显式 CROWD_DIRECT_BACKEND=1 时启用。

生成接入函数部署载荷：python3 cloud/crowd_access_build.py。私有口令只存 .crowd-launch/operator-key，部署载荷仅包含 SHA256。使用已连接的 Supabase 部署工具提交 .crowd-launch/access-deploy.json；该函数以有效邀请或发布口令做自定义鉴权，不能删除这些校验。不要把私有状态、管理员凭据或浏览器会话提交到仓库。

安装渠道默认关闭。实机验收通过后，发布者在私有 .crowd-launch/accepted-releases.json 记录设备验证、版本、文件 URL 和真实 SHA256；部署构建会复用原有产物、公开配置和源码一致性检查。必须先把下载文件发布到同一正式域名，再重新部署接入清单并完成一次真实邀请→安装→登录→领取→回传→停止检查。源码编译、模拟浏览器通过都不能代替实机验收。

发布管理页是 /crowd/admin。具备可用渠道后生成邀请，参与者只收到整条短信或二维码；不要发送发布口令。数据回收位置与质量门见 DATA_RECOVERY.md，各设备分发条件见 DISTRIBUTION.md，实际验证范围见 REPAIR_VERIFICATION.md。当前 Apple/原生鸿蒙的编译、签名和正式分发渠道尚未验收。

旧版安装器和发布器更新仍在 Git 历史中，指引见 legacy/V3_HANDOFF.md；这里不保留过期的全局策略/遥测安装说明。

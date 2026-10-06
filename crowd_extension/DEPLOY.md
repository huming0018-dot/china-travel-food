# 众包 v4 分发与部署（2026-10-06）

本次修复基线为 `1b4006b` + `cd10128`。默认入口复用既有网站 `/crowd`，发布者在 `/crowd/admin` 生成邀请链接和二维码；参与者安装、同意和首次登录后自动领取、搜索、采集与回传。权威实现和验收说明见 [README.md](README.md) 与 [CROWD_CONTRACT.md](CROWD_CONTRACT.md)。

最简分发路径见 [DISTRIBUTION.md](DISTRIBUTION.md)。Windows 普通 EXE 安装程序使用 per-user NSIS，正式清单优先指定 setup.exe；发布检查同时核验本地 `.exe.build.json`。首次部署会导出只含公开邀请的“发给朋友.html”和整条短信文本。

`publish.sh` 默认只构建。`--check` 检查部署条件，`--apply` 才执行已连接项目的迁移/发布/邀请生成。没有签名与实机验收的渠道不能标记 `verified`。公开下载包、服务端密钥、账户会话和签名私钥分开处理；源码仓库不含私人配置。旧扩展固定公钥和 Gecko ID 保留，但不发布指向未签名包的更新清单。

当前交付为可复现源码与内部测试包。2026-10-06 已在现有 Supabase 安装两项 v4 迁移并回验权限；网站未发布、无正式邀请、任务调度未启用。Android SDK 编译可以在此环境完成；Windows/macOS 独立客户端、iPhone/iPad 与原生鸿蒙仍需各自安装/签名和实机验收。用户已决定保留苹果完整目标并后续补齐发布账号。网页不能代替原生苹果后台自动采集，也不把旧手动提交页当作全自动渠道。

v4 使用独立的 `crowd_v4` 数据、邀请和奖励账本；旧 v3 RPC/历史数据不自动删除或重算。匿名 v3 写接口仍属于旧通道，应在迁移参与者后另行关闭；它们不能写入新 v4 私有数据。部署脚本只应用 `cloud/supabase/migrations/` 的新增迁移，不重新执行下列历史 v3 重算脚本。

源码构建：`python3 cloud/crowd_build.py`。Android 构建：`python3 cloud/crowd_android_build.py --sdk <SDK目录>`。桌面构建：`python3 cloud/crowd_desktop_build.py --platform win32|darwin --arch x64|arm64`（Mac 签名步骤需 Mac）。发布检查：`python3 cloud/crowd_launch.py`。完整测试命令见 README。

---

# 以下为 v3 历史部署记录（不用于 v4 发版）

# 众包美食家 v3.4 · 完整部署手册

> 版本：v3.4.6（队列竞态/死信词表/幂等重裁修复）· 2026-10-06
> 读者：PM / 继任开发者。目标：**不看代码也能完成部署、发布、回滚、熔断**。

---

## 一、系统总览

```
参与者端（Chrome 扩展 / 手机网页）          云端（全部 Supabase + GitHub Pages）
┌──────────────────────────┐      ┌─────────────────────────────────────┐
│ Chrome 扩展（桌面/狐猴）    │      │ Supabase 项目 bdwrhshgdeghgyzwpxnl   │
│  · 自动领任务/采集/回传      │ RPC  │  · crowd_* 表 + security definer RPC │
│  · 安全线 v2 类人节奏        │─────▶│  · Storage bucket crowd（产物托管）   │
│  · crx 自动升级通道         │      │  · Edge 函数 crowd-page（备用静态页）  │
│ 手机网页 submit.html       │      │ GitHub Pages（huming0018-dot/crowd-pages）│
│  · 中枢分配目标/粘贴提交      │      │  · submit/status/install 页面正式托管  │
└──────────────────────────┘      └─────────────────────────────────────┘
```

| 通道 | 托管位置 | 用途 |
|---|---|---|
| 插件 zip/crx/updates.xml | Supabase bucket `crowd` | 分发 + **自动升级** |
| 手机页/状态页/安装引导 | **GitHub Pages** | 正式页面（bucket 的 HTML 是 text/plain 无法渲染，仅作下载镜像） |
| 定时任务 | 腾讯云服务器 cron（ubuntu@49.234.35.92） | 回流监控（每小时 :07）、证据入库（06:30）、周结算（周一 09:00） |

## 一·五、代码真相源

**GitHub 主仓库 `huming0018-dot/china-travel-food` 已是正式真相源**（2026-10-06 起）：
`crowd_extension/`（插件源码，当前 3.4.8）· `cloud/sql/crowd_fix_v3*.sql`（迁移链）·
`cloud/crowd_tracking.py`、`cloud/health.py`（服务器脚本，与线上同步）· `crowd-test-harness/`（回归套件）。
安装产物在 `huming0018-dot/crowd-pages` 的 Releases。改代码后：本地 crowd-platform 提交 → 同步主仓库。

## 二、凭据索引（都不进 git）

| 凭据 | 位置 | 用途 |
|---|---|---|
| anon/publishable key | 随包分发（src/config.js） | 参与者端 API 访问，公开 |
| service_role key | `china-travel-food/app/.env.local`（SUPABASE_SERVICE_ROLE_KEY） | publish.sh 上传、PM 管理、沙盒 admin |
| Management 令牌（sbp_） | `~/.food_atlas_credentials.md`（SBP_TOKEN=） | 执行 SQL 迁移（Management API） |
| 扩展签名私钥 | `crowd_extension/key.pem`（gitignored） | **自动升级链的命根子，丢了全体参与者升级断链——立即备份！** |
| GitHub | `~/.config/gh/hosts.yml`（oauth_token，账号 huming0018-dot） | Pages 发布 |
| 服务器 | `~/.ssh/food_cloud_deploy`（ubuntu@49.234.35.92） | cron 与云端脚本 |

## 三、首次部署（全新环境）

```bash
# 1. SQL 迁移（按序，全部幂等）——用 Management API 或 Supabase SQL Editor 依次执行：
cloud/sql/crowd_tables.sql                 # 建表（基线）
cloud/sql/crowd_rpc_security.sql           # RPC 权限层
cloud/sql/crowd_harden_redteam.sql         # 红队加固
cloud/sql/crowd_submit_proof_live_v2.sql   # （历史基线，线上已是更新版）
cloud/sql/crowd_fix_v323_reconcile.sql     # v3.3 合并迁移（幂等回执/逐条裁决/去重口径）
cloud/sql/crowd_fix_v330_resolve.sql       # 短链解析（pg_net）
cloud/sql/crowd_fix_v330_assign.sql        # 中枢分配 crowd_next_target
cloud/sql/crowd_fix_v330_status.sql        # 状态汇总 crowd_status_summary
cloud/sql/crowd_fix_v340_pause.sql         # 全局暂停 + safety 下发
cloud/sql/crowd_fix_v344_quota_replay.sql  # ⓪b 幂等层：quota_exceeded 旧回执删除重裁 + reset_at 下发
cloud/sql/crowd_fix_v345_item_quota_replay.sql  # ⓪b 扩展到条目级配额拒收回执
# 执行前备份：select pg_get_functiondef('public.crowd_submit_proof');（备份样例见 cloud/sql/backup-pre-v323-functions.sql）

# 2. 发布插件 + 页面
cd crowd_extension
export CROWD_SERVICE_KEY=<service_role key>
./publish.sh            # 打包 zip+crx、生成 updates.xml、上传 bucket 全部产物

# 3. 发布 Pages 页面（submit/status/install*）
#    推送到 GitHub 仓库 huming0018-dot/crowd-pages 的 main 分支即可（Pages 自动构建）
```

## 四、日常发版（改代码后）

```bash
# 1. 改版本号：manifest.json 的 version（三位递增，如 3.4.0 → 3.4.1）
#    同步三个页面的 EXT_VERSION 常量：apply.html / install.html / install-mobile.html
sed -i '' "s/旧版本/新版本/g" crowd_extension/{apply,install,install-mobile}.html

# 2. 回归测试（Puppeteer 实测插件，mock 服务端不碰生产）
cd test-harness && npm install && node run-all.js && node run-extra.js && node run-extra2.js && node run-fixes.js

# 3. 一键发布（校验签名密钥 → 打包 → 上传；已装插件自动升级）
cd ../crowd_extension && ./publish.sh

# 4. 页面有改动则推 GitHub Pages（submit.html / status.html / install*.html）
```

**注意：改了 `src/` 下的文件必须发版；只改页面只推 Pages。**

## 五、参与者安装（分发给别人）

| 端 | 方式 | 入口 |
|---|---|---|
| Mac | 下载 `crowd-install-mac.command` 双击 → 输一次开机密码 → Chrome 自动装、自动升级 | 安装引导页 |
| Windows | 下载 `crowd-install-win.bat` 双击 → UAC 点是 → 同上 | 同上 |
| Android | 狐猴浏览器 → 本地加载 zip → 开「桌面版网站」 | install-mobile.html |
| 任何手机 | 免安装网页提交（submit.html） | 邀请卡扫码 |

线上地址（Pages）：`https://huming0018-dot.github.io/crowd-pages/{submit,status,install,install-mobile,apply}.html`

## 六、运维操作

```bash
# 全局熔断（风控信号/舆情/任何异常）：全员下个心跳（≤3 分钟）即停
update crowd_config set value='true' where key='global_pause';
# 恢复：... value='false' ...

# 远程收紧安全线（只紧不松，插件端永不放宽本地基线）：
update crowd_config set value='{"quota_day": 60, "gap_min": 180}' where key='safety_limits';  -- 不存在则先 insert

# 看运行状态：手机打开 status.html，或：
curl -s -X POST -H "apikey: <anon>" -H "Authorization: Bearer <anon>" -d '{}' \
  https://bdwrhshgdeghgyzwpxnl.supabase.co/rest/v1/rpc/crowd_status_summary

# 单参与者日配额调整（默认 20，Mac 主力设备 P-6KSZWXEG 现为 50）：
update crowd_participants set quota_day=50 where participant_id='P-XXXXXX';

# 参与者管理（服务器上）：python3 crowd_admin.py list|suspend|blacklist|stats
```

## 七、回滚

| 场景 | 操作 |
|---|---|
| 插件出问题 | manifest 版本回退 → `./publish.sh`（updates.xml 指向旧 crx，全员自动降级）；或全局熔断先停 |
| SQL 迁移出问题 | 函数备份在 `cloud/sql/backup-pre-v323-functions.sql`，用 Management API 恢复旧函数定义 |
| Pages 页面坏 | GitHub 仓库 crowd-pages 回滚 commit，Pages 自动重建 |

## 八、已踩过的坑（ troubleshooting ）

| 症状 | 根因 | 处置 |
|---|---|---|
| 插件按钮全灰/协议页点不动 | 内联脚本被 MV3 CSP 拦 | v3.1.1 起已抽离独立 js；新页面一律 `script src` |
| 注册失败:{} | SW 拦截器误伤页面自身 API 请求 | v3.3.3 已修：SW 只接管分享目标 POST |
| rpc_401 | importScripts 在 CONFIG 之后执行，SW 拿空 key | v3.3.4 起 key 硬编码进 CONFIG + importScripts 置顶 |
| 改了代码插件没变化 | Chrome 缓存 SW 脚本（同版本号+同文件名=内容变了也不重读，重启浏览器都没用） | **每次发版同时改名 SW 文件**（background_vXXX.js）+ 升版本号，双保险 |
| 队列卡死：重试永远拿到同一个 quota_exceeded | 幂等层把时效性拒绝当最终裁决永久缓存 | v344 起 quota 类回执重试时删除重裁；v345 扩展到条目级 |
| "已上传的被认为没上传" | 插件读 results[].verdict，服务端发的字段是 gate，已收录条目本地永不确认 | v3.4.5 起双读 (verdict||gate)；**写契约注释时必须与实现对齐** |
| 队列丢信封/假死 | 回传在途时新入队信封被旧快照覆盖（读-改-写竞态） | v3.4.6 写回前重读 merge；看门狗不再提前放锁 |
| 永久错误无限重试 | 死信正则与服务端 reason 词表漂移 | v3.4.6 已对齐；**服务端新增 reason 时必须同步插件词表** |
| bucket 托管的 HTML 打开是源码 | Supabase Storage 对 text/* 强制 text/plain | 页面一律走 GitHub Pages，bucket 只放下载物 |
| **Chrome 策略安装/自动升级全断** | bucket 把 updates.xml 强制成 text/plain+nosniff，Chrome 更新客户端拒收（静默无任何提示）；连 crx 的 octet-stream 也难保 | **Chrome 更新通道（updates.xml+crx）一律走 GitHub Pages**（application/xml + x-chrome-extension 都是对的）；manifest update_url/安装器 UPDATE_URL 已迁；publish.sh 自动同步 Pages |
| 匿名调新 RPC 报 PGRST202 | PostgREST schema 缓存未刷新 | 等 1 分钟或 `select pg_notify('pgrst','reload schema')` |
| 短链解析超时 | anon 角色 statement_timeout 默认 3s | 已放宽到 40s（alter role anon） |
| 状态页"最新 N 条"不对 | 同批插入 created_at 相同乱序 | 已改按自增 id 排序 |
| Firefox 安卓装上即死 | manifest 改成 event page 但代码首行 importScripts 在 window 上下文不存在 → ReferenceError 后台全灭 | v3.4.8 双形态 manifest + importScripts 守卫；**改形态必须连代码一起改** |
| iOS 快捷指令跑不通 | 手搓 plist 用了 6 层不存在的动作/键名 | 通道已下架（分发物料标记"已下架勿发"）；重建须用 cherri 等真实工具链 + 真机回归 |
| GitHub token 推送 401 | ~/.config/gh/hosts.yml 里有多个 token，grep 第一个可能是旧 token | 用 `gh auth token` 取钥匙串里的活 token |
| 状态页数字不更新 | 手机浏览器冻结后台标签的定时器 | 页面已加回到前台立即刷新 + no-store（2026-10-06） |
| TG 通知停了 | deno 中转额度超限挂起 + api.telegram.org 在 CN 直连不通 | 已切 Supabase RPC 中继（crowd_notify_tg + pg_net 数据库直连 TG，密钥在 crowd_private_config，调用方需 ops_secret）；服务器 deploy.env 需有 CROWD_OPS_SECRET |

## 九、版本地图

| 版本 | 内容 |
|---|---|
| v3.3.0 | 审计修复 + v3.2.3 对齐 + 自动升级分发 |
| v3.3.1 | 移动端域名适配（m.xiaohongshu.com） |
| v3.3.4 | SW 改名强刷 + key 硬编码 + 自动开搜索页（真·全自动） |
| **v3.4.0** | **安全线 v2 类人调度（双层抖动/时段画像/warmup/风控状态机）+ 全局暂停** |
| v3.4.1 | warmup 老设备豁免；标题软化（no_title 标记）+ 页面自动提取标题 |
| v3.4.3 | quota_exceeded 语义：停采到配额重置 + 信封排队，不再无限重试 |
| v3.4.4/3.4.5 | 幂等层 quota 回执重裁 + reset_at 精确排队；gate/verdict 字段双读；SW 改名强刷缓存 |
| **v3.4.6** | **队列写回竞态修复 + 看门狗锁修正 + 死信词表对齐 + 风控信号透传 + 同意门收紧（点"不同意"不采集）+ 重试上限 8 次 + 孤儿标签清理；Puppeteer 回归 96/96（test-harness/）** |
| v3.4.7 | 审计剩余项清零（agreed_at 门禁/last_sid 去重/401 熔断/warmup NaN 回退等）；独立回归 123/123 |
| v3.4.8 | Firefox 双修（manifest 双形态 background + importScripts 守卫 + gecko update_url）+ publish.sh 自动打 xpi + Mozilla updates-firefox.json；网页五连修（UUID 兜底/存储防护/URL 规范化/标题必填/gate 中文分流）；M4 熔断收口网页通道（crowd_fix_v348_global_pause_web.sql） |
| v7（沙盒中） | PM 后台自定义模糊关键词——`sandbox/v7-fuzzy-keywords` 分支，**未发布** |
| Firefox 通道 | AMO 非公开签名（账号 huming0018@gmail.com，凭据在 ~/.food_atlas_credentials.md：AMO_PASSWORD / AMO_TOTP_SECRET / 恢复码）；签名包 crowd-extension-vX-firefox-signed.xpi 上传 bucket；Firefox 自动更新用 Mozilla 格式 update manifest（待做，当前 Firefox 端手动更新） |

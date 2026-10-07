> **2026-10-07 18:03 Mac v4.0.3 候选（最新，未实机验收）**：已核对用户指定 Kimi `crawler-extension v1.0.0` / `5b9e327` / Release（仅源码归档）。复用逐卡片范围与搜索词核对，页面消息等待有界，加载中/脚本断连/响应超时分开报告，连续失败三次暂停。新增仅 opt-in 的工作标签主页面导航阶段/错误码诊断，生产迁移 `20261007100305_crowd_v4_navigation_diagnostics` 已部署且兼容旧版。核心检查、Chromium 固定页面→隔离 PostgreSQL 入库/幂等及诊断权限/隐私检查通过；最新真实客户端仍4.0.1、v4 proofs=0，不能宣称已修复实机网络或可分发。私有包38,766 bytes，SHA256 `a889c49b021fc933fbb4be27fb7e9bf443f9c7f1696a93aa998845dee3ad0de4`。具体对照、权限范围、验证及更新方式见 [KIMI_REFERENCE_REVIEW.md](KIMI_REFERENCE_REVIEW.md)。以下为历史记录。

> **2026-10-07 后续质量复核**：早期版本的源码/模拟页面测试未覆盖真实结果页链接、探测器断连与续租配额组合，导致反复试用仍无真实回传。当前真实诊断已确认漏识别 search_result 详情链接；v4.0.2 候选同时修复上述生命周期缺陷、缓存标签页误导航及 v3/v4 更新器混用风险。浏览器检查使用真实 DOM 与隔离 PostgreSQL 原入库函数，覆盖丢回执重放，不再用模拟成功回执证明该链路。Mac 生产 proofs 仍为 0，必须维持「未实机验收」结论。权威状态/候选包/具体验证见 [REPAIR_VERIFICATION.md](REPAIR_VERIFICATION.md) 顶部，以下为历史审阅。

# v4 整合审阅 · 2026-10-06

核对提交：`1b4006b55e390c093b5f8c347499b65deb8fb5a1`、`cd10128b764f74757a88668c88f674e28f408524`。

| 可复现的问题 | 本次处理 |
|---|---|
| 构建器停在 v3.2.1，引用被删掉的 src/background.js；`python cloud/crowd_build.py --dry` 实际报缺文件 | 构建器、清单与产物统一 v4，运行时文件白名单打包；服务端私钥不进包 |
| install.html 运行时把下载地址覆写成 v3.4.3，手机版页为 v3.4.8；旧脚本要求管理员写全局策略、强杀 Chrome | 统一设备入口和经验收的版本清单，独立桌面客户端为默认渠道；删除策略写入路径 |
| content.js 的域名校验只接受 www，清单却声明 m.xiaohongshu.com | 共享 URL 解析及各原生容器同时接受精确的 www/m HTTPS 域名，入库统一为标准 URL |
| 缓存 active_task 提前返回，心跳不刷新服务端暂停/租约；v340 领取按包 progress < kpi_min，和逐关键词完成口径不一致 | 独立 v4 原子领取、租约续期和每次活动心跳查暂停/参与者状态，不依赖旧 v3 口径 |
| 停止只清 alarm，正在等待/采集的操作仍继续；状态渲染固定显示运行中 | 持久化状态机和取消代次保护，停止后在途操作不会恢复采集或追加证据；UI 读实际状态 |
| 只抓搜索卡片标题，正文详情路径未接入；非标字段及正文证据不足 | 自动搜索、访问详情、首次停留和滚动后提取标准字段/非标字段/原文；缺失值为 null |
| 客户端按编号 + 匿名 RPC 提交；历史测试只模拟成功回执，不能证明身份边界或真实数据库行为 | v4 RPC 使用参与者 Auth JWT、私有表和原子回执/全局去重；SQL 并发/权限/100条奖励与邀请限额在独立 PostgreSQL 验证 |
| Firefox window 后台缺 importScripts/setAccessLevel | 保留双形态清单与能力检查，增加真实源码 event-page 加载检查 |
| 发布器无 CRX/签名 XPI 仍写自动升级清单，且可能生成与固定 ID 不符的新私钥 | 离线构建不生成私人签名、不伪造升级成功；正式渠道必须先验收再发布 |

Supabase 公开状态 RPC 的两种请求头已只读验证均返回 200；没有把 publishable key 的 Bearer 写法误报为故障。服务端密钥及现网调度未改动。v3.4.8 的 cloud/health.py 与 cloud/crowd_tracking.py 修复保留。

完整验收状态见 README。浏览器测试使用模拟公开页面与 API；源码测试和 SDK 编译不等于真实小红书或全端实机通过，当前没有可用的 v4 生产短信邀请。


旧 v3 审阅和安装器记录保留在 Git 历史；见 legacy/V3_HANDOFF.md。新接入和数据回收验收见 REPAIR_VERIFICATION.md、DATA_RECOVERY.md。

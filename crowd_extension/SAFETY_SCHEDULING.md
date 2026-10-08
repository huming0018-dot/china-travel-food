# v4.0.5 访问限制与调度

2026-10-08：迁移 `20261008014820_crowd_v4_safety` 已部署到既有 Supabase；`crowd-access` v5 ACTIVE。本版是原 Mac 私有试点的更新候选，未通过真实设备验收。正式分发渠道仍关闭。线上最近诊断仍为 4.0.1（2026-10-07 21:17:06 +08:00，page_timeout），真实 proofs=0；不能把固定页面测试写成真实采集成功。

## 生效边界

这些访问限制由 v4.0.5 每次动作前主动调用 `crowd_v4_guard` 执行。旧客户端、被修改的扩展和用户手动打开小红书不受此接口拦截；不能宣称服务端可以远程控制所有浏览器。旧版 submit/claim 保持兼容，原身份/邀请和未回传证据不删除。原 Mac 更新后才能验证完整效果。

沿用 Ponytail：共享 agent 中接入一个服务端检查，不引入新运行依赖、远程执行、模拟指纹或验证码破解。Kimi v1.0.0 提供了冷却、分阶段额度的设计参考；没有复制其实现。

## 默认规则

| 规则 | 行为 |
|---|---|
| 每日动作上限 | 搜索30、详情60、评论展开120、滚动120；均按尝试计数，与提交成功条数分开 |
| 新参与者 | 服务端报名日龄第1天20%，至第7天100%；未来报名时间按20%，本地重装不重新计算 |
| 日界线 | 服务端北京时间零点；客户端改时钟不能刷新额度 |
| 动作间隔 | 至少30秒，再加一次性0–15秒抖动；保存下次时间，轮询不反复抽样 |
| 连续执行 | 每轮最多20个动作或20分钟；达到后休息30分钟 |
| 平台限流 | 停止，至少冷却24小时；随后本人点击继续 |
| 验证码 | 停止，至少冷却30分钟；本人处理验证并点击继续 |
| 页面/解析失败 | 有界退避，连续3次暂停；登录失败要求本人处理；不把所有错误归为限流 |
| 控制同步 | 运行中每5分钟独立检查，不依赖当前任务是否缓存或是否处于等待；配置有效期10分钟，每次页面动作仍必须在线获准 |
| 总暂停 | 管理者暂停后不批准新动作，等待中的客户端可收到恢复；已获准的在途动作不承诺被撤销 |
| 数据回传 | 采集等待期间可继续交付已缓存证据；显式停止则停止采集及自动回传 |

控制参数可以降低额度、延长间隔；数据库约束和客户端硬上限都拒绝提高到上述边界以外。操作失败/回执丢失也不退动作额度，宁可少做一次，不重复获得未计数的访问。此处的数值是项目保守策略，不是小红书授予的安全阈值或许可。

风险先持久化到本机，再尝试上报。断网或进程中断时，下次继续必须完成风险上报才能开始新动作。服务端也持久化冷却。继续、重启、唤醒均不清除本机期限。显式停止保持停止，不会被服务端恢复命令重新开启。

## 去重与数据位置

详情打开前检查已回收笔记（不包括已拒绝证据），然后原子领取10分钟笔记占用；另一参与者正在处理的笔记本轮跳过。同一参与者可重开，但重开同样消耗动作额度。占用过期可重新领取；过期超过一天的占用在后续检查时清理。它是短期减少重复访问的措施，最终全局唯一性仍由原 proofs/receipts 保障。

- `crowd_v4.proofs.record`：标准字段、非标字段、原文证据；回收/核验/奖励逻辑沿用原版。
- `crowd_v4.safety`：每位参与者当天动作计数、下一动作时间、冷却和会话计数；用于执行限制，无网页内容、Cookie或完整网址。
- `crowd_v4.policy`：当前控制版本、暂停状态和额度。管理变更进入原 audit。
- `crowd_v4.note_reservations`：笔记ID、占用参与者和失效时间，无 URL token。
- 原诊断仍由本人主动开启，只保留最新允许字段快照；本次扩展固定错误码，不开放任意日志/远程命令。

## 管理者操作

继续使用原发布身份；不新增密钥。以下在项目目录运行，JSON文件不含任何凭据：

```sh
# 查看配置（只读，不增加版本）
printf '{}\n' > /tmp/crowd-control.json
python3 cloud/crowd_v4.py admin control --payload-file /tmp/crowd-control.json --apply
# 暂停
printf '{"paused":true}\n' > /tmp/crowd-control.json
python3 cloud/crowd_v4.py admin control --payload-file /tmp/crowd-control.json --apply
# 恢复允许自动运行的参与者，不清除风险冷却或本人停止
printf '{"paused":false}\n' > /tmp/crowd-control.json
python3 cloud/crowd_v4.py admin control --payload-file /tmp/crowd-control.json --apply
```

可附加 `search_cap`、`detail_cap`、`comment_cap`、`scroll_cap`、`gap_seconds`。不带 `--apply` 只显示待执行内容。匿名和参与者无权调用管理控制；管理员身份仅服务端保存。现有管理网页尚未新增控制按钮。

监控时区分：客户端版本、诊断时间、错误原因、动作计数与真实 proofs/verified 数。安全表提供计数，不提供完整历史成功率曲线；不能用开启状态当成产量。尚未完成大规模并发/跨设备实机验收。

## 验证与交付

`CROWD_TEST_TOOLS=/tmp/crowd-v4-tools node crowd_extension/tests/run.cjs` 通过：共享 agent 生命周期、继续/重启/唤醒冷却、断网风险上报、配置失效、任务缓存下暂停/恢复、显式停止、Mac助手完整性、Chromium固定DOM→隔离PostgreSQL实际claim/guard/submit/finish与丢回执幂等、诊断隐私，以及安全接口的预扣额度/日界线/预热/会话冷却/跨用户占用/权限/硬上限。浏览器夹具使用加速时钟，对隔离数据库安全时间作相同推进，不触碰生产任务。

外部空数据库完整业务套件未配置 `CROWD_TEST_DATABASE_URL`，因此跳过；隔离 PGlite 用例已执行。没有进行真实小红书采集或 Mac 睡眠/唤醒验收。

生产回验：三张私有表 RLS 开启，anon guard=false、authenticated guard=true、authenticated safety直接访问=false。预期 advisor 的 [authenticated SECURITY DEFINER 提示](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable) 由固定空search_path、本人auth.uid校验、无直接表权限限定。私有表的 [RLS无策略提示](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy) 属于刻意的默认拒绝：仅由窄RPC访问，不补开参与者直读权限。既有无关模块告警不在本次变更中修改。

实际HTTP回验：管理发布身份读取control为200且版本不变；匿名guard为401，匿名管理control为403，manifest仍ready=false。

私有包 `/workspace/Mac轻量内测-v4.0.5.zip`，42,955 bytes，SHA256 `712df88fa0e17af63aee6b41995bc3668e684f84e76ef8a52e3e8caf8d8c8782`。逐文件摘要及当前运行源码一致；无新增浏览器权限、无管理员密钥。包中包含原试点邀请，不上传公开仓库。使用原Chrome/Edge个人资料，运行更新助手并在扩展管理页刷新，核对4.0.5；不卸载、不重新报名。真实Mac验收前保持候选状态。

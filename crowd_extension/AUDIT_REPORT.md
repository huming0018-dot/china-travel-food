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

---

# 以下为 v3 历史审阅记录

# 众包美食家扩展 v3.4.5 深度静态审计报告

审计范围：crowd_extension/src/*.js + cloud/sql（crowd_fix_v344_quota_replay.sql 为现行服务端口径）
判定基准：仅报告读码确认的问题；标注【确定】/【可疑】。

## 致命

### F1【确定·致命】uploadProofs 读-改-写竞态：新采集信封被旧快照覆盖丢失
- 位置：background_v345.js L466（循环前一次性读 queue）→ L606（循环结束统一写回 remain）；入队侧 L367-372
- 问题：`_uploadProofsInner` 整个串行 RPC 循环（每信封最长 15s 超时，20+ 信封即数分钟）期间持有的是**旧快照 q**。`proof_queue` 的入队路径（L367-372 的读-改-写）**不受 `_uploading` 互斥保护**。窗口期内心跳采集入队新信封 → upload 循环结束用旧快照算出的 `remain` 写回 → **新信封（含从未提交的 submission_id）从 storage 被静默抹掉，采集数据永久丢失**。死信的移除效果同样可被反向覆盖（见 F9）。
- 触发：upload_retry(5min) 与 collect_heartbeat(3min) 并发；或 F2 的悬空 inner 并发。队列非空时每 3/5 分钟周期天然交错，属常态而非极端。
- 修法：入队/出队共用同一把异步锁；或写回前重读队列、按 submission_id 合并增量（只移除本轮已裁决的信封，保留新入队者）。

### F2【确定·致命】看门狗不取消悬空 promise：_running 释放后旧 inner 继续写 storage
- 位置：background_v345.js L208-217
- 问题：`Promise.race` 超时后 `_collectOnceInner()` 的 promise **没有被也无法被取消**，继续在后台跑（建 tab、markSearch、入队、uploadProofs）。`_running=false` 后下一心跳重入 → 两个 inner 并发：日配额计数翻倍、重复建搜索页、proof_queue 双重读-改-写（直接汇入 F1 的数据丢失）。且 inner 开头 L226 的 uploadProofs 本身就可能超过 90s（大队列×15s 超时），看门狗误报是常态。
- 修法：inner 各 await 检查点接取消令牌（watchdog 触发时置位，inner 在下一检查点自灭，且自灭前不得写 storage）；或看门狗只告警不释放锁，等 inner 真正结束。

## 高

### F3【确定·高】死信正则覆盖不了服务端实际 reason 集 → 永久错误信封无限重试
- 位置：background_v345.js L395 `PERMANENT_REASON_RE`；对照服务端 crowd_fix_v344_quota_replay.sql L137-191
- 现行服务端信封级 reason：`participant_unavailable`、`envelope_parse_error`、`stale_client`、`envelope_missing_task_or_seq`、`participant_id_mismatch`、`captured_at_future`、`captured_at_too_old`、`task_not_open`、`quota_exceeded`（特判）、`submission_in_progress`/`processing`（占位）。
- 正则只命中 `task_not_open` 一族。**`participant_unavailable`（暂停/拉黑/编号不存在）、`stale_client`、`envelope_parse_error`、`envelope_missing_task_or_seq`、`participant_id_mismatch`、`captured_at_too_old` 全部漏网** → 走 markRetry 无限退避。retry_count 无上限（`Math.min` 兜底不会 NaN/溢出，但也永不终止）。`captured_at_too_old` 尤其荒谬：时间戳不可变，7 天外的信封永远不可能成功却永远每 ≤30min 重试一次。
- 后果链：毒信封占队列 → 涨到 100 → queue_full 停采（插件对该参与者静默死亡）；被封号参与者永无休止地打 RPC。
- 修法：按 v344 SQL 枚举对齐正则（加 `participant_unavailable|stale_client|envelope_parse_error|envelope_missing_task|participant_id_mismatch|captured_at_`）；并加 retry_count 硬上限（如 ≥8 次强制死信兜底）。

### F4【确定·高】条目级 item_quota_exceeded 被幂等回执永久毒化（v344 修复只覆盖信封级）
- 位置：background_v345.js L579（reason 含 quota → 保留条目）；服务端 v344 SQL L86-91（⓪b 只删顶层 reason=quota_exceeded 的回执）、L437-447（条目级配额拒收）
- 场景：一批 6 条回传跨越配额边界（配额剩 3）→ 服务端返回 **ok:true** + 后 3 条 `gate:rejected, reason:item_quota_exceeded` → 该回执被幂等层**永久缓存**（顶层 reason 为 null，不命中 ⓪b 删除分支）。客户端把这 3 条留在信封里用**同一 submission_id** 重试 → 永远命中缓存 → 永远拿到同一张旧回执 → 这些条目**在配额重置后也绝无可能入库**。信封永不排空，每 ≤30min 空转一次 RPC，且 recordFlow 按 accepted=0 累计还会触发回流误报。
- 修法（二选一）：服务端对 results 内含 item_quota_exceeded 的回执同样删除重裁；或客户端把 quota 类残留条目拆出、换发新 submission_id 重新入队。

### F5【确定·高】风控信号在主路径上漏报：24–72h 冷却状态机对真实风控页不生效
- 位置：content.js L160-186；background_v345.js L315-324
- 问题：`rateLimited` **只在 ok:true 分支携带**（L185）。小红书触发「访问频繁/验证」时搜索页通常无任何卡片 → extractNoteCards=0 且非详情页 → 走 `UNSUPPORTED_PAGE`（ok:false）分支返回，**该分支不带 rateLimited** → background L315 直接 search_failed 返回，`onRateLimited` 永不调用；且该路径也不计 empty_streak（L348-352 只在 search.ok 后执行）。结果：插件在被平台风控状态下每个心跳继续撞搜索页，风控状态机形同虚设。另：rateLimited 检测只扫 body.innerText 前 500 字符，风控文案在 DOM 后部时同样漏检。
- 修法：ok:false 各分支统一带 rateLimited；background 对 search_failed 也检查该字段；风控文案检测放到 page_type 判定之前、全文扫描。

### F6【确定·高·合规】知情同意可被绕过：注册即采集，agreed_at 无人检查
- 位置：onboarding.js L56/L61（注册成功立即写 participant_id）、L85-87（refuse 只改文案不清数据）；background_v345.js L120-125（participantGate 不查 agreed_at）、L729-731（install 即 collector_running=true）
- 问题：点「我要加入」成功后 participant_id 立即持久化，协议页一关（或点「不同意」——refuse 分支不清除已写入的 participant_id、不停 alarm），插件照样自动采集回传。全代码库无任何地方读 agreed_at。同意流程实际不构成闸门。
- 修法：participantGate 要求 agreed_at 存在；refuse 时清除 participant_id 并 chrome.alarms.clear("collect_heartbeat") + collector_running=false。

## 中

### F7【确定·中】MV3 下 inline sleep 最长 3min，SW 约 30s 无事件即被杀 → 采集轮静默腰斩
- 位置：background_v345.js L258-261（`await sleep(gate.waitMs)`）
- 问题：纯 setTimeout 不重置 MV3 SW 空闲计时。lognormal µ=ln(90s) 意味着约一半间隔采样 >30s，叠加 last_search_at 后 waitMs>30s 是常态 → SW 在 sleep 中途被杀，本轮采集无日志、无结果地消失（_running 随上下文销毁，不残留锁）。表现为采集吞吐远低于安全线设计值、心跳大量空转。
- 修法：waitMs 超阈值（如 25s）一律改为一次性 alarm 延迟唤醒，不 inline sleep。

### F8【确定·中】SW 中途被杀留孤儿小红书标签页
- 位置：background_v345.js L278-313：tabs.create 到 tabs.remove 之间最长 ~37s（20s 轮询 + 2s + 15s content 超时）
- 问题：窗口期内 SW 被杀则 tab.id 丢失，后台搜索页永久残留并随运行累积。L313 `chrome.tabs.remove` 未 await/未 catch promise  rejection，tab 已被用户关闭时产生 unhandled rejection 噪音。
- 修法：initBackground/onStartup 时枚举 `tabs.query({url:"*://www.xiaohongshu.com/search_result*xsec_source=pc_crowd*"})` 清理；remove 加 `.catch(()=>{})`。

### F9【确定·中】死信写入与队列移除非原子 → 重复死信 + 无限重死循环
- 位置：background_v345.js L402-408（deadLetter 立即写）vs L606（队列移除延迟到循环结束）
- 问题：SW 在两者之间被杀 → 信封仍在队列 → 下轮幂等重放返回同一永久原因 → 再次 deadLetter：每轮死信表 +1 条（50 条上限滚动冲刷旧记录，申诉证据丢失）+ 1 次无效 RPC，无限循环。
- 修法：与 F1 同修（写回合并）；deadLetter 按 submission_id 去重。

### F10【可疑·中】syncKeywordProgress 兜底分支在幂等重放下重复累计 → 本地进度虚高提前归档
- 位置：background_v345.js L443-448
- 问题：`keyword_progress` 缺失或 active_task 不匹配（pack=null）时走 acceptedDelta 累加。同一信封重试命中服务端幂等缓存返回**同一回执**，fallback 每次都把 delta 再加一遍 → 本地 accepted 虚高 → 提前 done → finalizeTask 归档并不再认领 → 服务端该词实际未达 kpi，任务以 in_progress 挂到租约过期（默认 1440min）。现行服务端恒返回 keyword_progress，触发面主要是：信封所属任务已切换/归档后的滞留信封重试、旧版回执。另：recordFlow（L547）对重放回执的 accepted>0 也会重置 zero_count，产生假健康信号。
- 修法：fallback 分支按 envelope.submission_id 记账去重（kw_state 里记录 last_synced_submission），或仅首次回执累计。

## 低

### F11【确定·低】`d.task_status` 服务端从未下发 → L559-562 为死代码
v344 响应字段（SQL L647-655）：ok/submission_id/accepted/rejected/results/new_progress/keyword_progress，**无 task_status**。任务终结检测实际全靠 L595-604 本地 allDone（当前可用），但注释宣称的"服务端宣告"路径不存在，将来依赖它会踩空。另 L190 `r.safety_limits` 同样不存在于 crowd_fetch_tasks 响应（v340 SQL 只有顶层 safety.limits），恒 no-op。

### F12【确定·低】4xx 一律死信：配置事故会一次性 nuking 整个队列
background_v345.js L108-110：非 408/429/5xx 的 4xx（401/403/400/404）均 temp=false → 全队列死信。anon key 轮换/权限事故时所有未传数据进死信。建议 401/403 按临时处理或熔断告警。

### F13【确定·低】warmup 日期损坏 → 配额闸门 NaN 静默失效
device_profile.js L141-145 + safety_engine.js L330：first_run_date 被写坏时 Date.parse=NaN → day/fraction=NaN → `Math.min(quota, NaN, cap)`=NaN → `searches >= NaN` 恒 false → 日配额闸门失效。需存储损坏才触发。修法：fraction 非有限数回退 1。

### F14【可疑·低】选择器脆弱会向参与者封号连锁放大
content.js 列表页 excerpt 恒 null；服务端要求标题去标点 ≥2 字（否则 excerpt ≥10 字兜底），不满足 → item_content_empty 且 counts_for_reject=true（v344 SQL L373-385）。XHS 改版 `.title` 选择器 → 全量拒收 → 累计 >20 条且 reject_rate>0.6 → 参与者自动 suspended（SQL L614-620）。建议客户端在标题缺失时直接丢弃该条目而不是送上去烧拒收率。

### F15【确定·低】upload_retry alarm 在采集运行期间可能被反复重置而饿死
background_v345.js L762：每次 SW 唤醒都 `chrome.alarms.create("upload_retry")`（同名重建会重置计时）。心跳(3min) < 重传周期(5min) 且 SW 被频繁杀死重启时，upload_retry 永不触发。功能上被心跳路径 L226 的 upload_first 覆盖，影响有限；CROWD_STOP 后 upload_retry 是唯一唤醒源，此时工作正常。建议 initBackground 里先 alarms.get 存在则跳过。

### F16【确定·低】done_task_ids 无上限增长
background_v345.js L619-623：长期运行存储膨胀。建议封顶滚动。

## 复核为无问题（排除项）
- `_dayState`/risk_state/warmup 全部用 `toISOString()`（UTC 日界），与服务端 `date_trunc('day', now())`（UTC）一致；circadianWeight 用本地 getHours() 是设计意图。v3.4.4 的 UTC 修复无残留。
- markRetry 退避数学：`Math.pow(2,n-1)` 溢出为 Infinity 时被 `Math.min` 封顶 30min，不产生 NaN（但无次数上限，见 F3）。
- byPos/byId 双映射（L568-582）正确处理了部分重试时 results 与 items 长度不等的情形。
- 服务端 ⓪c 占位行 + 行锁串行化对并发提交是完备的；客户端 submission_id 复用正确。
- 配额 park 的 reset_at 解析与 UTC 兜底（L525-531）正确。

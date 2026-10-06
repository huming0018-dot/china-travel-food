# 众包美食家 v3.4.5 运行时排查报告

测试方式：chrome-for-testing 154 加载未打包扩展（临时 profile），SW 侧 CDP Fetch 拦截全部 Supabase RPC，页面侧拦截小红书并回伪搜索页。三个套件共 67 项断言：**66 通过，1 失败（即 BUG-1，稳定复现）**；另有 2 项单独抽查（submission_id 跨重试复用、CROWD_STATUS 往返）均通过。最终运行 0 未捕获 SW 异常、0 页面异常、0 生产请求泄漏。

## 发现的 bug

### BUG-1 【高】回传在途期间入队的信封被静默删除（数据丢失）

- **位置**：`src/background_v345.js:466`（`_uploadProofsInner` 开头读队列）+ `:606`（结尾无条件 `proof_queue = remain` 覆盖写）；触发对侧在 `:367-372`（采集路径 push 入队）
- **现象**：`uploadProofs` 执行期间（RPC 在途，最长可到 15s 超时窗口），若有新信封 push 进 `proof_queue`，上传结束时会用基于旧快照算出的 `remain` 整体覆盖队列——新信封直接从 storage 消失，无任何日志。
- **复现**（场景F）：mock `crowd_submit_proof` 延迟 1.5s 响应 → 启动 `uploadProofs()` → 400ms 后按采集路径的同款读-改-写 push 信封 `sub-e2e-9` → 上传返回 `{status:"uploaded", sent:1, queued:0}` → 队列里 `sub-e2e-9` 已不存在。
- **生产触发路径**：`upload_retry`（5min）与 `collect_heartbeat`（3min）两个 alarm 天然并发。`_uploading` 互斥锁只挡并发 upload，挡不住 collect 的 push；心跳里"先回传后采集"的串行也只在单次心跳内部成立。
- **次生问题**：`deadLetter()`（`:403-406`）对 `deadLetter` 数组同样是读-改-写，与在途 upload 并发时死信留档可互相覆盖（影响较小）。
- **修复方向**：606 行覆盖写之前重读队列做 merge（保留快照外新增的信封）；或把"读队列→处理→写回"整段和入队操作挂到同一把串行锁上。

### BUG-2 【中】条目级"事实永久"失败无死信出口，僵尸信封永久占队列

- **位置**：`src/background_v345.js:573-582`（keep 过滤器只认 4 个白名单终态）+ `:411-416`（`markRetry` 无 retry_count 上限）
- **现象**：服务端对某条目返回非白名单 verdict（如 `invalid`/`error` 且不带 `temp:true`、reason 不含 quota）时，条目被"保守保留"退避重试——退避封顶 30min 后每 30min 重试一次，**永不停止、永不进死信**。
- **复现**（X14）：mock 回 `{gate:"invalid", reason:"note_private"}`，强制到期连跑 3 轮 → retry_count 1→2→3，信封始终卡队列，`deadLetter` 为空。
- **影响**：坏条目（笔记转私、字段被服务端判非法等）会缓慢侵蚀队列水位（上限 100），长期占用 RPC 配额与存储。
- **修复方向**：retry_count 超阈值（如 ≥10）转死信，或把非白名单且非 temp 的 verdict 视为条目级终态。

### BUG-3 【低】`fetchActiveTask` 对 RPC 返回 `null` 崩溃

- **位置**：`src/background_v345.js:169`（`if (d.safety && ...)`）
- **现象**：`crowd_fetch_tasks` 返回 JSON `null` 时抛 `TypeError: Cannot read properties of null (reading 'safety')`。上层 `_collectOnceInner` catch 兜底（该轮返回 `status:"error"`），不会挂死调度，但服务端异常期间每个心跳（3min）都会刷一次 `last_error`。
- **修复方向**：`const d = rpc.data || {}`。

### 信息项（非 bug）

- **编号正则不含连字符**：`participantGate`（`:123`）要求 `/^P-[A-Z0-9]{6,12}$/`。任务建议的测试编号 `P-TEST-E2E` 会被门禁拒绝（场景G 已实测确认拦截与提示语正常）。线上编号规则一致，无问题；测试数据需避开 `-`。
- **quota 协议假设**：`quota_exceeded` 只在 HTTP 200 + `{ok:false}` 分支识别；若服务端哪天把配额回执改成 4xx，信封会按"HTTP 层永久错误"直接死信（`:502-510`）。建议在服务端契约里钉死"配额必须 200 返回"。

## 实测确认无问题的路径

| 路径 | 证据 |
| --- | --- |
| v3.4.4 gate 字段解析修复 | 场景A：`gate:"accepted"/"duplicate"` 正确判终态、队列排空；`verdict` 旧字段也兼容 |
| keyword_progress 同步 + 本地兜底 | 场景A：有 keyword_progress 时按服务端口径置 done；缺失时本地累计兜底正确 |
| submission_id 幂等 | 场景A/C：入队时生成、跨多次重试复用同一 UUID（含 500/断网两轮退避后） |
| 配额 park（今晚修的点） | 场景B/X11：park 到服务端 `reset_at`+5~15min 抖动；不烧 retry_count；无 `reset_at` 时兜底 UTC 下一零点而非本地午夜；`doCollectOnce` 正确返回 `quota_blocked` |
| 500/断网退避 | 场景C：60s→120s 指数退避、退避期内零请求、恢复后排空不丢数据 |
| 死信 | 场景D：`task_not_open`、HTTP 400 进死信留档可申诉；X9：408/429 走退避不误杀 |
| 任务领取/轮转/归档 | 场景E：领取映射 `keyword_pack`、`safety_limits` 只紧不松落地、`nextKwIndex` 0→1→-1、全链路采集（真开 tab + content.js 提取 + 即时回传）、达标后 `active_task` 归档并记 `done_task_ids` |
| 启动/初始化 | S0：SW 无异常、v3.4.4 自愈一次性执行、`onInstalled` 建 alarm 正确 |
| 门禁/熔断/水位 | X2 过期 park 自动解除、X3 `global_pause` 熔断、X4 队列满 100 → `queue_full` 暂停采集、X12 无编号 `no_participant` |
| 队列/信封健壮性 | X5 历史信封补 submission_id 并持久化、X6 部分终态信封瘦身保留 temp 条目、X7 条目级 quota 保留、X8 未知 reason 退避而非死信 |
| 回流检测 | X10：连续 3 次 accepted=0 → `zero_count=3` + `flow_stall_warned_at` 告警 |
| 并发互斥 | X13：第二个并发 `uploadProofs` 返回 `busy`（`_uploading` 锁有效） |
| 注册流 | X15：「我要加入」成功回填+落 storage、RPC 携带 `Dsalt*` 设备盐（一机一号）、已注册设备恢复旧编号、签署记 `agreed_at` |
| popup 生命线 | `CROWD_STATUS` 从扩展页往返正常（queueLen/flow/safety_v2/deadLetter 字段齐全） |

## 未覆盖项

- **SW 休眠重启续传**：`chrome.runtime.reload()` 后新 SW 不自发启动（MV3 事件驱动，设计如此），harness 未能稳定唤醒做断言。队列持久化本身由 chrome.storage.local 保证（各场景跨多次 evaluate 已间接验证）；`initBackground` 的 alarm 恢复逻辑仅静态核对。建议手工验证：插件页里"停止"后重启浏览器，确认 `upload_retry` 复活、`collect_heartbeat` 不复活。
- **content.js 详情页提取 / rateLimited 检测**：只覆盖了列表页路径。
- **真实闹钟周期触发**（3/5min 自然唤醒）：测试均为手动触发内部函数，未等真实 alarm 周期。

## harness 使用与产物

```bash
cd test-harness
npm install
node run-all.js      # 主场景（S0/A–E/F/G）
node run-extra.js    # 边界 X1–X13
node run-extra2.js   # X14/X15
```

- 结果：`test-harness/results/summary.json`、`extra.json`、`extra2.json`（SW console 全量、异常、RPC 流水、泄漏审计）
- 详细机制与环境坑：`test-harness/README.md`
- 重要前提：必须用 chrome-for-testing（品牌版 Chrome 忽略 `--load-extension`）；headed 模式运行（Chrome ≥137 headless 不加载扩展）；凌晨 0–7 点采集场景会被插件时段画像闸拦截（设计行为，测试用运行时覆写门控绕过）

# v3.4.6 修复实施与回归报告

基线：v3.4.5（上一轮 E2E 排查发现 BUG-1/2/3）+ 静态审计 F1–F9。全部客户端改动，未动 publish.sh、未动桌面目录。

## 改动清单

### src/background_v345.js（+/- 主要 9 处）

| 修复 | 位置 | 摘要 |
| --- | --- | --- |
| F1 队列写回竞态 | `:632-657` | `_uploadProofsInner` 写回前重读 `proof_queue` 做 merge：只追加"快照与 remain 中都没有"的新信封（submission_id 优先，无 id 用 task_id+proof_seq+captured_at+items.length 指纹）；本轮已发送/已死信的不复活 |
| F2 看门狗悬空重入 | `:200-219` | `_running` 释放从外层 finally 移到 inner promise 的 `.finally`——看门狗超时只返回 `watchdog_timeout` 状态，锁持有到 inner 真正 settle；超时日志注明"inner 仍持锁运行中" |
| F5 风控信号消费 | `:317-323` | `!search.ok` 提前返回前先检查 `search.rateLimited` 并送入 `safety.onRateLimited`（原代码先 return，信号被丢） |
| F3 死信词表 | `:407` | `PERMANENT_REASON_RE` 增补服务端 v344 真实词表：participant_unavailable、envelope_parse_error、stale_client、envelope_missing_task_or_seq、participant_id_mismatch、captured_at_future、captured_at_too_old；原子串保留 |
| F9 死信去重 | `:414-423` | `deadLetter()` 写入前按 submission_id 查重，已存在直接返回 |
| 条目级重试上限 | `:38`（CONFIG.RETRY_DEAD_AFTER=8）+ `:582-616` | keep 过滤器记录最后非终态 gate 与 quotaOnly 标记；非 quota 豁免条目在 retry_count+1≥8 时整封转死信 `retry_exhausted:<gate>`；quota 滞留条目豁免 |
| BUG-3 空指针 | `:168` | `rpc.data || {}`，fetch_tasks 返回 null 按"暂无任务"收场 |
| F7 inline wait 阈值 | `:39` | MAX_INLINE_WAIT_MS 180s→25s（低于 MV3 SW 30s 空闲杀死线；实际 config 在 background CONFIG，不在 config.js） |
| F8 孤儿标签清理 | `:804-816` | `initBackground` 启动时 `chrome.tabs.query` 小红书域，关闭 URL 含 `xsec_source=pc_crowd` 的遗留采集标签；try/catch 不阻塞启动 |
| 附加小修 | `:316` | `chrome.tabs.remove(tab.id)` 的 promise rejection 同步 try/catch 接不住，补 `.catch(()=>{})`（回归中实测到未处理拒绝） |
| F6 background 侧 | `:770-784` | `onInstalled("install")` 不再建 collect_heartbeat、collector_running=false——安装≠同意，采集由协议页「同意」显式启动 |

### src/content.js（F5）

`:127-132` 新增 `detectRateLimited()`（body 判空 + try/catch）；`:139/:150/:166/:175/:201` 全部 6 条返回路径（NOT_ON_XHS / MISSING_KEYWORD / PAGE_MISMATCH / UNSUPPORTED_PAGE / 成功 / EXTRACT_FAILED）统一透传 `rateLimited`。

### src/onboarding.js（F6）

- `:17-19` 新增 `pendingPid` 页面暂存变量
- `:60-69` 注册成功/已注册恢复只回填输入框 + 暂存，**不写 storage**
- `:22-30` `savePid`（仅「同意」触发）：落盘 participant_id+agreed_at 后发 `CROWD_START` 显式启动采集
- `:92-104` 「不同意」：清 participant_id/agreed_at/pendingPid，置 collector_running=false，发 `CROWD_STOP` 停 alarm

### manifest.json

`:4` version 3.4.5 → 3.4.6

## 回归结果（全部真实运行，96/96 通过）

| 套件 | 结果 | 覆盖 |
| --- | --- | --- |
| `run-all.js` | **47/47** | S0 启动（含 F6 新安装行为）、A 正常回传、B 配额 park、C 退避、D 死信、E 全链路采集、F 竞态（原 BUG-1 场景，现通过）、G 门禁 |
| `run-extra.js` | **15/15** | X1（BUG-3 修复后返回 no_task）–X13 边界 |
| `run-extra2.js` | **8/8** | X14 上限前行为、X15 注册流（同意前不落盘/同意后落盘+启动采集/已注册恢复） |
| `run-fixes.js`（新增） | **26/26** | R1 F1 正例 merge 保留、R2 F1 负例死信不复活、R3 F2 看门狗持锁、R4 F3 八词表全死信、R5 重试上限 retry_exhausted:error、R6 quota 条目重裁排空、R7 F9 去重、R8 F7 26s 立即返回 wait、R9 F8 孤儿标签清理、R10 F5 风控页信号送达状态机、R11 F6 拒绝清场 |

四个套件合计 SW 未捕获异常 0、页面异常 0、生产 Supabase 真实请求 0。

## 需要如实说明的点

1. **F5 不能只改 content.js**：任务清单只点名 content.js，但 background 原代码在 `!search.ok` 时直接 return，`rateLimited` 即使透传也到不了状态机。我在 background `:317-323` 补了消费逻辑（ok:false 分支先喂风控状态机再返回）。R10 实测：风控页（无卡片）→ `search_failed + rateLimited:true` → 当日停止 + 24–72h 冷却生效。
2. **F2 的取舍**：看门狗超时后锁持有到 inner settle——若 inner 真永久挂起（如 storage API 卡死），采集会保持 busy 跳过一个生命周期。这符合"宁可慢不可并发写"的修复意图，但意味着看门狗现在只是告警不是逃生舱。
3. **F1 merge 的无 id 判等**：用内容指纹兜底（proof_seq 按 task+kw 递增，实际不会撞）；所有 v3.2+ 信封都有 submission_id，指纹路径只服务历史信封。
4. **R3 的附带发现**：w3 探针在队列清空+任务归档后自然走到 `crowd_fetch_tasks`——当时没配 mock，被拦截层 599 兜底（未出网）。已在测试补上 mock，最终泄漏计数 0。
5. **X14 语义变化**：`gate:"invalid"` 未知条目前 7 轮仍保守退避（X14 通过），第 8 轮转死信（R5 通过）——僵尸信封有了出口。
6. **未覆盖**：SW 休眠重启续传仍未自动化（MV3 事件唤醒在 harness 中不稳定）；`chrome.runtime.reload()` 后 SW 需要消息/alarm 唤醒属平台行为，建议发布前手工验一次"停止→重启浏览器→upload_retry 复活、heartbeat 不复活"。
7. `node --check` 全部改动文件通过；manifest JSON 校验通过。
